'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  analyzeGame,
  cancelAnalysis,
  fetchAnalysisResult,
  fetchProgress,
  isSseConnectionError,
  saveStarredGame,
  subscribeToProgress,
  type AnalyzePayload,
} from '@/lib/api';
import { loadDefaultAnalysisReviewCount, saveDefaultAnalysisReviewCount } from '@/lib/analysisDefaults';
import type { AnalyzeResponse, ProgressStatus, SearchResult } from '@/types';
import type { SamplingContract } from '@/types/acquisition';
import { useStarredGames } from '@/contexts/StarredGamesContext';

interface ProgressWithEstimate extends ProgressStatus {
  remainingSeconds?: number | null;
}

interface AnalysisTask {
  game: SearchResult;
  status: 'queued' | 'analyzing' | 'completed' | 'error';
  progress: ProgressWithEstimate | null;
  result: AnalyzeResponse | null;
  error: string | null;
  waitingFor: string | null;
  requestedLimit: number;
}

export interface StartAnalysisOptions {
  refresh?: boolean;
  persist?: boolean;
  review_count?: number;
  language?: string;
  languages?: string[];
  filter?: string;
  day_range?: number | null;
  refresh_days?: number | null;
  output_language?: 'zh' | 'en' | 'ja';
  /** Explicit population contract for the new acquisition flow. */
  sampling?: SamplingContract;
}

interface QueuedEntry {
  game: SearchResult;
  options: StartAnalysisOptions;
}

interface AnalysisContextType {
  tasks: Map<number, AnalysisTask>;
  startAnalysis: (game: SearchResult, options?: StartAnalysisOptions) => Promise<void>;
  getTask: (appId: number) => AnalysisTask | undefined;
  clearTask: (appId: number) => Promise<void>;
}

const AnalysisContext = createContext<AnalysisContextType | null>(null);

function errorMessageFrom(error: unknown): string {
  let message = error instanceof Error ? error.message : 'Analysis failed';
  try {
    const parsed = JSON.parse(message);
    if (parsed?.message) message = parsed.message;
  } catch {
    // Plain string; keep it.
  }
  return message;
}

function normalizeOptions(options: StartAnalysisOptions): Required<Pick<StartAnalysisOptions, 'persist' | 'refresh' | 'output_language'>> & StartAnalysisOptions {
  const sampling = options.sampling;
  const reviewCount = sampling?.max_reviews ?? options.review_count ?? loadDefaultAnalysisReviewCount();
  const languages = sampling?.languages ?? options.languages;
  const language = sampling?.languages?.[0] ?? options.language ?? 'all';
  const filter = sampling?.collection_order ?? options.filter ?? 'recent';
  return {
    ...options,
    sampling,
    persist: options.persist ?? true,
    refresh: options.refresh ?? false,
    review_count: reviewCount,
    language,
    languages,
    filter,
    output_language: options.output_language ?? 'zh',
  };
}

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const { addGame } = useStarredGames();
  const addGameRef = useRef(addGame);
  addGameRef.current = addGame;

  const [tasks, setTasks] = useState<Map<number, AnalysisTask>>(new Map());
  const tasksRef = useRef(tasks);
  tasksRef.current = tasks;
  const queueRef = useRef<QueuedEntry[]>([]);
  const pendingRef = useRef<Set<number>>(new Set());
  const processQueueRef = useRef<() => void>(() => undefined);

  const activeTaskIds = useMemo(
    () => Array.from(tasks.entries())
      .filter(([, task]) => task.status === 'analyzing')
      .map(([appId]) => appId)
      .sort((a, b) => a - b)
      .join(','),
    [tasks],
  );

  const attachProgressEstimate = useCallback((progress: ProgressStatus): ProgressWithEstimate => ({
    ...progress,
    remainingSeconds: progress.eta_seconds ?? null,
  }), []);

  const markError = useCallback((appId: number, error: unknown) => {
    const message = errorMessageFrom(error);
    setTasks((previous) => {
      const next = new Map(previous);
      const existing = next.get(appId);
      if (existing) next.set(appId, { ...existing, status: 'error', progress: null, waitingFor: null, error: message });
      return next;
    });
  }, []);

  const submitAnalysis = useCallback(async (game: SearchResult, rawOptions: StartAnalysisOptions) => {
    const options = normalizeOptions(rawOptions);
    const appId = game.appid;
    const reviewCount = options.review_count ?? loadDefaultAnalysisReviewCount();
    if (reviewCount > 0) saveDefaultAnalysisReviewCount(reviewCount);

    // Keep every legacy field for API compatibility.  `sampling` is an additive
    // field already accepted by the backend AnalyzeRequest; assigning through
    // a variable avoids changing the legacy public AnalyzePayload interface.
    const payload: AnalyzePayload & { sampling?: SamplingContract } = {
      app_id: appId,
      review_count: reviewCount,
      language: options.language ?? 'all',
      languages: options.languages,
      filter: options.filter ?? 'recent',
      day_range: options.day_range ?? undefined,
      persist: options.persist,
      refresh: options.refresh,
      refresh_days: options.refresh ? options.refresh_days : undefined,
      output_language: options.output_language,
      sampling: options.sampling,
    };

    const result = await analyzeGame(payload);
    setTasks((previous) => {
      const next = new Map(previous);
      const existing = next.get(appId);
      if (existing?.status === 'analyzing') next.set(appId, { ...existing, result });
      return next;
    });
  }, []);

  const processQueue = useCallback(async () => {
    const running = Array.from(tasksRef.current.values()).some((task) => task.status === 'analyzing');
    if (running) return;
    const nextEntry = queueRef.current.shift();
    if (!nextEntry) return;

    const { game, options } = nextEntry;
    const appId = game.appid;
    setTasks((previous) => {
      const next = new Map(previous);
      const existing = next.get(appId);
      if (existing?.status === 'queued') {
        next.set(appId, { ...existing, status: 'analyzing', waitingFor: null, progress: null });
      }
      return next;
    });

    try {
      await submitAnalysis(game, options);
    } catch (error) {
      markError(appId, error);
      processQueueRef.current();
    }
  }, [markError, submitAnalysis]);
  processQueueRef.current = () => { void processQueue(); };

  const completeTask = useCallback(async (appId: number) => {
    const current = tasksRef.current.get(appId);
    if (!current || current.status !== 'analyzing') return;

    try {
      const analysis = await fetchAnalysisResult(appId);
      if (analysis.status === 'failed') {
        markError(appId, analysis.error || 'Analysis failed');
        processQueueRef.current();
        return;
      }
      if (analysis.status !== 'completed') return;

      const metadata = analysis.metadata ?? current.result?.metadata ?? {
        app_id: appId,
        requested: current.requestedLimit,
        retrieved: 0,
        language: 'unknown',
        fetched_at: '',
      };
      const result: AnalyzeResponse = {
        metadata,
        insights: analysis.insights,
        research_report: analysis.research_report,
        semantic_status: analysis.semantic_status,
        reviews: analysis.reviews,
      } as AnalyzeResponse;

      if (analysis.metadata && analysis.insights) {
        try {
          await saveStarredGame({
            app_id: appId,
            name: current.game.name,
            metadata: analysis.metadata,
            insights: analysis.insights,
            sample: analysis.reviews,
          });
          addGameRef.current({
            app_id: appId,
            name: current.game.name,
            metadata: analysis.metadata,
            insights: analysis.insights,
            sample: analysis.reviews,
            genres: [],
            categories: [],
            updated_at: new Date().toISOString(),
            is_favorite: false,
          });
        } catch (error) {
          console.error('Failed to persist analysis result', error);
        }
      }

      setTasks((previous) => {
        const next = new Map(previous);
        const existing = next.get(appId);
        if (existing) next.set(appId, { ...existing, status: 'completed', result, progress: null, error: null, waitingFor: null });
        return next;
      });
      processQueueRef.current();
    } catch {
      // Result may not be materialized at the same instant as the completion
      // signal.  The next SSE/poll event can retry.
    }
  }, [markError]);

  useEffect(() => {
    const appIds = activeTaskIds ? activeTaskIds.split(',').map(Number) : [];
    if (!appIds.length) return;

    const cleanups: Array<() => void> = [];
    const polling = new Map<number, ReturnType<typeof setInterval>>();

    const updateProgress = (appId: number, progress: ProgressStatus) => {
      setTasks((previous) => {
        const next = new Map(previous);
        const existing = next.get(appId);
        if (existing?.status === 'analyzing') next.set(appId, { ...existing, progress: attachProgressEstimate(progress) });
        return next;
      });
    };

    const startPolling = (appId: number) => {
      if (polling.has(appId)) return;
      const interval = setInterval(async () => {
        const current = tasksRef.current.get(appId);
        if (!current || current.status !== 'analyzing') {
          clearInterval(interval);
          polling.delete(appId);
          return;
        }
        try {
          const progress = await fetchProgress(appId);
          updateProgress(appId, progress);
          if (progress.run_status === 'completed' && progress.immutable_result_available === true) {
            await completeTask(appId);
          } else if (progress.run_status === 'failed' || progress.run_status === 'cancelled') {
            markError(appId, progress.run_status === 'cancelled' ? 'Analysis cancelled' : 'Analysis failed');
            processQueueRef.current();
          }
        } catch {
          // Polling is a fallback; keep trying while the task is active.
        }
      }, 1500);
      polling.set(appId, interval);
    };

    for (const appId of appIds) {
      try {
        const cleanup = subscribeToProgress(appId, {
          onProgress: (processed, total, active, phase, fetchedCount, etaSeconds, runStatus, runPhase, immutableResultAvailable) => {
            updateProgress(appId, {
              app_id: appId,
              processed,
              total,
              active,
              updated_at: new Date().toISOString(),
              phase,
              fetched_count: fetchedCount,
              eta_seconds: etaSeconds,
              run_status: runStatus,
              run_phase: runPhase,
              immutable_result_available: immutableResultAvailable,
            });
            if (runStatus === 'completed' && immutableResultAvailable === true) void completeTask(appId);
          },
          onCompleted: () => { void completeTask(appId); },
          onError: (error) => {
            if (isSseConnectionError(error)) startPolling(appId);
            else {
              markError(appId, error);
              processQueueRef.current();
            }
          },
          onTimeout: () => startPolling(appId),
        });
        cleanups.push(cleanup);
      } catch {
        startPolling(appId);
      }
    }

    return () => {
      cleanups.forEach((cleanup) => cleanup());
      polling.forEach((interval) => clearInterval(interval));
    };
  }, [activeTaskIds, attachProgressEstimate, completeTask, markError]);

  const startAnalysis = useCallback(async (game: SearchResult, rawOptions: StartAnalysisOptions = {}) => {
    const appId = game.appid;
    const options = normalizeOptions(rawOptions);
    const reviewCount = options.review_count ?? loadDefaultAnalysisReviewCount();
    const existing = tasksRef.current.get(appId);
    if (pendingRef.current.has(appId) || existing?.status === 'analyzing' || existing?.status === 'queued') return;

    const running = Array.from(tasksRef.current.entries()).find(([id, task]) => id !== appId && task.status === 'analyzing');
    if (running) {
      queueRef.current.push({ game, options });
      setTasks((previous) => {
        const next = new Map(previous);
        next.set(appId, {
          game,
          status: 'queued',
          progress: null,
          result: null,
          error: null,
          waitingFor: running[1].game.name,
          requestedLimit: reviewCount,
        });
        return next;
      });
      return;
    }

    pendingRef.current.add(appId);
    setTasks((previous) => {
      const next = new Map(previous);
      next.set(appId, {
        game,
        status: 'analyzing',
        progress: null,
        result: null,
        error: null,
        waitingFor: null,
        requestedLimit: reviewCount,
      });
      return next;
    });

    try {
      await submitAnalysis(game, options);
    } catch (error) {
      markError(appId, error);
      processQueueRef.current();
    } finally {
      pendingRef.current.delete(appId);
    }
  }, [markError, submitAnalysis]);

  const getTask = useCallback((appId: number) => tasks.get(appId), [tasks]);

  const clearTask = useCallback(async (appId: number) => {
    const task = tasksRef.current.get(appId);
    if (task?.status === 'analyzing') {
      try { await cancelAnalysis(appId); } catch (error) { console.error('Failed to cancel analysis:', error); }
    }
    if (task?.status === 'queued') {
      queueRef.current = queueRef.current.filter((entry) => entry.game.appid !== appId);
    }
    setTasks((previous) => {
      const next = new Map(previous);
      next.delete(appId);
      return next;
    });
    if (task?.status === 'analyzing') setTimeout(() => processQueueRef.current(), 500);
  }, []);

  return (
    <AnalysisContext.Provider value={{ tasks, startAnalysis, getTask, clearTask }}>
      {children}
    </AnalysisContext.Provider>
  );
}

export function useAnalysis() {
  const context = useContext(AnalysisContext);
  if (!context) throw new Error('useAnalysis must be used within AnalysisProvider');
  return context;
}
