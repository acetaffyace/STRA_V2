'use client';

import { FormEvent, Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { AppLayout } from '@/components/AppLayout';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageTransition } from '@/components/PageTransition';
import {
  createVersionReviewPlan,
  fetchVersionEvents,
  fetchVersionRun,
  fetchVersionComparison,
  searchGames,
  syncNewsVersionEvents,
  startVersionReview,
  fetchRecentAnalysisRuns,
  buildVersionReviewRunUrl,
  type VersionEventResponse,
  type VersionReviewPlanResponse,
  type VersionRunResponse,
  type VersionReviewV2Result,
  fetchVersionPopulationStrip,
  type VersionComparisonPopulationStrip,
} from '@/lib/api';
import type { SearchResult } from '@/types';
import { useLanguage } from '@/contexts/LanguageContext';
import { formatTaxonomyLabelZh } from '@/lib/taxonomyLabels';
import { displayZh, zhComparisonStatus, zhCoverageStatus, zhRunStatus, zhVersionState } from '@/lib/displayLabels';

function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`;
}

function score(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(1);
}

function countDisplay(value: number | null | undefined, unit = ''): string {
  return value === null || value === undefined ? '—' : `${value.toLocaleString()}${unit}`;
}

function trustworthyClassifiedDisplay(value: number | null | undefined): string {
  // The current V2 contract may use 0 as an unpopulated/default field.
  return value && value > 0 ? value.toLocaleString() : '—';
}

function confidenceZh(value: string | null | undefined): string {
  if (value === 'high') return '高置信度';
  if (value === 'medium') return '中置信度';
  if (value === 'low') return '低置信度';
  return value || '未评估';
}

function periodZh(value: string | null | undefined): string {
  if (value === 'pre') return '更新前';
  if (value === 'post') return '更新后';
  if (value === 'event_day') return '更新当天';
  return value || '未知时间段';
}

function actionTypeZh(value: string | null | undefined): string {
  if (value === 'product') return '产品处理';
  if (value === 'community') return '社区沟通';
  if (value === 'content') return '内容优化';
  if (value === 'product_and_community') return '产品与社区';
  return value || '待定';
}

function recommendationZh(subcategory: string, actionType: string): string {
  const main = subcategory.split('/', 1)[0];
  if (actionType === 'product') return '结合原文证据复现问题，确认受影响的平台或流程，并将修复候选项加入下一轮问题分诊。';
  if (actionType === 'community') return '发布范围明确的状态说明，写清已知影响、临时解决办法、负责人和下一检查节点，并持续观察后续反馈。';
  if (actionType === 'content') return '复核受影响的内容或表现部分，先与代表性玩家进行小范围验证，再决定是否扩大上线。';
  if (main === 'monetization_value') return '与负责团队确认问题，再根据证据选择产品修复或面向玩家的沟通方案。';
  return '与负责团队确认问题，再根据证据选择产品修复或面向玩家的沟通方案。';
}

function validationMetricZh(value: string): string {
  const labels: Record<string, string> = {
    'issue negative rate': '问题负面率',
    'crash/performance telemetry': '崩溃 / 性能监控',
    'support or bug-ticket volume': '客服或缺陷工单量',
    'repeat mention rate': '重复提及率',
    'follow-up sentiment': '后续情感倾向',
    'community/support volume': '社区 / 客服反馈量',
    'aspect negative rate': '方面负面率',
    'content engagement': '内容参与度',
    'repeat positive mentions': '重复正向提及率',
    'mention rate': '提及率',
    'support volume': '客服反馈量',
  };
  return labels[value] || value;
}

function warningZh(value: string): string {
  if (value.includes('observational')) return 'Steam 评论属于观察性数据，不能单独证明因果关系。';
  if (value.includes('Aspect-level sentiment is not available')) return '当前没有方面级情感数据，问题标签比例仅作为严重度代理指标。';
  if (value.includes('Aspect sentiment is model-derived')) return '方面级情感由模型推断，仍应结合原文证据复核。';
  return value;
}

function VersionReviewContent() {
  const { language } = useLanguage();
  const copy = language === 'zh'
    ? { eyebrow: '玩家声音智能分析', intro: '先选择游戏开始一次新的版本复盘；已有运行可在下方单独打开。', placeholder: '粘贴已有运行 ID', load: '打开已有复盘', loading: '加载中…', empty: '选择游戏后，系统会自动识别版本事件并生成复盘方案。', priority: '重点问题', evidence: '证据卡片', actions: '建议行动', topics: '新兴话题', limits: '局限性' }
    : language === 'ja'
      ? { eyebrow: 'プレイヤーの声インテリジェンス', intro: 'イベント前後の変化、重要課題、根拠、競合情報、検証アクションを確認します。', placeholder: '分析実行 IDを貼り付け', load: '実行を読み込む', loading: '読み込み中…', empty: '完了した実行を読み込み、根拠付きレビュー画面を開きます。', priority: '優先課題', evidence: '根拠カード', actions: '推奨アクション', topics: '新興トピック', limits: '制約' }
      : { eyebrow: 'PLAYER VOICE INTELLIGENCE', intro: 'Inspect event-anchored changes, priority issues, evidence, competitor context, and validation actions.', placeholder: 'Paste analysis run ID', load: 'Load run', loading: 'Loading…', empty: 'Load a completed run to open the evidence-backed review workspace.', priority: 'Priority issues', evidence: 'Evidence cards', actions: 'Recommended next actions', topics: 'Emerging topics', limits: 'Limitations' };
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialRunId = searchParams.get('run') || searchParams.get('run_id') || '';
  const initialAppId = Number(searchParams.get('app_id') || 0);
  const [runId, setRunId] = useState(initialRunId);
  const [run, setRun] = useState<VersionRunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gameQuery, setGameQuery] = useState('');
  const [games, setGames] = useState<SearchResult[]>([]);
  const [selectedAppId, setSelectedAppId] = useState<number | null>(null);
  const [events, setEvents] = useState<VersionEventResponse[]>([]);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [eventLoading, setEventLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [plan, setPlan] = useState<VersionReviewPlanResponse | null>(null);
  const [analysisMode, setAnalysisMode] = useState<'recent_impact' | 'version_comparison' | 'version_longitudinal' | 'public_opinion'>('version_comparison');
  const [windowDays, setWindowDays] = useState<3 | 7 | 14>(7);
  const [comparisonEventId, setComparisonEventId] = useState('');
  const [recentVersionReviews, setRecentVersionReviews] = useState<import('@/lib/api').AnalysisHistoryItem[]>([]);
  const [selectedWindow, setSelectedWindow] = useState(7);
  const [v2Comparison, setV2Comparison] = useState<VersionReviewV2Result | null>(null);
  const [populationStrip, setPopulationStrip] = useState<VersionComparisonPopulationStrip | null>(null);
  // Hide known-invalid historical runs from the user-facing recent list while
  // keeping their immutable database records available for audit/debugging.
  const hiddenRunIds = new Set([
    'af8f65fa56634926b6c4c1512ca87c95',
    '4d0015cb42554901a907aa45a3b03e61',
  ]);

  const loadEvents = async (appId: number) => {
    setEventLoading(true);
    setError(null);
    try {
      try {
        await syncNewsVersionEvents(appId, { news_count: 30 });
      } catch {
        // Existing local events are still usable when Steam News is unavailable.
      }
      const result = await fetchVersionEvents(appId);
      setEvents(result);
      setSelectedEventId(result[0]?.event_id || '');
      if (result[0]) {
        const nextPlan = await createVersionReviewPlan({ app_id: appId, event_id: result[0].event_id, semantic_limit: 1000, mode: analysisMode, window_days: windowDays });
        setPlan(nextPlan);
        setComparisonEventId(nextPlan.comparison_event?.event_id || '');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load version events.');
    } finally {
      setEventLoading(false);
    }
  };

  const findGame = async () => {
    if (gameQuery.trim().length < 2) return;
    setEventLoading(true);
    setError(null);
    try {
      setGames(await searchGames(gameQuery.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to search games.');
    } finally {
      setEventLoading(false);
    }
  };

  const startSelectedReview = async () => {
    if (!selectedAppId || !selectedEventId || executing) return;
    setExecuting(true);
    setError(null);
    try {
      const started = await startVersionReview({ app_id: selectedAppId, event_id: selectedEventId, comparison_event_id: comparisonEventId || undefined, semantic_limit: 1000, mode: analysisMode, window_days: windowDays, refresh_reviews: true });
      setPlan(started.plan);
      setRun(started.run);
      router.replace(buildVersionReviewRunUrl(started.run.run_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start version review.');
    } finally {
      setExecuting(false);
    }
  };

  const loadRun = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      setError(language === 'zh' ? '请输入分析运行 ID。' : language === 'ja' ? '分析実行 IDを入力してください。' : 'Enter an analysis run ID.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await fetchVersionRun(trimmed);
      setRun(result);
      const configuredWindow = Number((result.config?.analysis as { post_window_days?: unknown } | undefined)?.post_window_days);
      if (configuredWindow === 3 || configuredWindow === 7 || configuredWindow === 14) {
        setSelectedWindow(configuredWindow);
        setWindowDays(configuredWindow);
      }
      router.replace(buildVersionReviewRunUrl(trimmed));
    } catch (err) {
      setRun(null);
      setError(err instanceof Error ? err.message : language === 'zh' ? '无法加载该运行。' : language === 'ja' ? '実行を読み込めません。' : 'Unable to load this run.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecentAnalysisRuns(50).then((items) => setRecentVersionReviews(items.filter((item) => item.run_type === 'version_review'))).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (initialRunId) void loadRun(initialRunId);
    else if (initialAppId > 0) {
      setSelectedAppId(initialAppId);
      setGameQuery(String(initialAppId));
      void loadEvents(initialAppId);
    }
    // The URL is the only dependency intentionally; loadRun is stable for this page lifecycle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialRunId, initialAppId]);

  useEffect(() => {
    if (!run || run.status !== 'running') return;
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchVersionRun(run.run_id);
        setRun(next);
        if (next.status === 'failed') {
          setError(next.error || '版本复盘执行失败。');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '无法读取复盘进度。');
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [run]);

  useEffect(() => {
    const embedded = run?.metrics?.version_review_v2;
    if (!run || !embedded) { setV2Comparison(null); return; }
    // Always read the shared comparison projection, including when the
    // embedded compatibility payload already uses the selected window.  The
    // endpoint attaches research-comparison-v1 and owns official deltas.
    fetchVersionComparison(run.run_id, selectedWindow)
      .then((response) => setV2Comparison(response.comparison))
      .catch(() => setV2Comparison(embedded));
  }, [run, selectedWindow]);

  useEffect(() => {
    if (!run?.run_id || !run.metrics?.version_review_v2) {
      setPopulationStrip(null);
      return;
    }
    fetchVersionPopulationStrip(run.run_id).then(setPopulationStrip).catch(() => setPopulationStrip(null));
  }, [run?.run_id, run?.metrics?.version_review_v2]);

  const metrics = run?.metrics;
  const analysisGoal = String((run?.config?.analysis as { analysis_goal?: unknown } | undefined)?.analysis_goal || '');
  const v2 = analysisGoal === 'version_comparison' ? (v2Comparison || metrics?.version_review_v2) : undefined;
  const canonicalComparison = v2?.canonical_comparison;
  const canonicalLeft = canonicalComparison?.left.quantitative;
  const canonicalRight = canonicalComparison?.right.quantitative;
  const semanticDeltaAllowed = Boolean(canonicalComparison?.compatibility.semantic_delta_comparable);
  const hasV2 = Boolean(v2);
  const hasResultMetrics = Boolean(metrics && (metrics.issue_cards || metrics.evidence_cards || metrics.version_a || metrics.population_contract));
  const activeRunWindow = Number((run?.config?.analysis as { post_window_days?: unknown } | undefined)?.post_window_days);
  const activeWindowLabel = activeRunWindow === 3 || activeRunWindow === 7 || activeRunWindow === 14 ? `${activeRunWindow} 天` : `${selectedWindow} 天`;
  const phaseLabel: Record<string, string> = {
    resolving_events: '正在确认版本事件',
    planning: '正在生成 A/B 分析方案',
    fetching_historical_reviews: '正在抓取 A/B 生命周期窗口评论',
    validating_windows: '正在校验 A/B 窗口覆盖',
    building_windows: '正在构造 A/B 评论窗口',
    classifying_version_a: '正在分析版本 A 评论',
    classifying_version_b: '正在分析版本 B 评论',
    comparing: '正在计算 A/B 差异',
  };
  const versionA = metrics?.version_a?.metrics ?? metrics;
  const versionB = analysisGoal === 'version_comparison' ? metrics?.version_b?.metrics : undefined;
  const versionAEventDate = metrics?.version_a?.event?.event_date || versionA?.event_date || '—';
  const versionBEventDate = metrics?.version_b?.event?.event_date || versionB?.event_date || '—';
  const versionReviewDateA = v2 && v2.event_a_id === metrics?.version_a?.event?.event_id ? versionAEventDate : versionBEventDate;
  const versionReviewDateB = v2 && v2.event_b_id === metrics?.version_a?.event?.event_id ? versionAEventDate : versionBEventDate;
  const versionAWindow = versionA?.periods?.post || versionA?.periods?.pre;
  const versionBWindow = versionB?.periods?.post || versionB?.periods?.pre;
  const topIssues = useMemo(() => (metrics?.issue_cards || []).slice(0, 8), [metrics]);
  const recommendations = useMemo(() => (metrics?.recommendations || []).slice(0, 6), [metrics]);
  const gameLabel = String((run?.config?.target_game as { name?: unknown } | undefined)?.name || `App ${run?.target_app_id || '—'}`);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void loadRun(runId);
  };

  return (
    <AppLayout>
      <PageTransition>
        <div className="min-h-screen bg-[rgb(5,5,15)] px-4 py-8 text-slate-100 sm:px-8 lg:px-12">
          <div className="mx-auto max-w-7xl space-y-6">
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-cyan-400/70">{copy.eyebrow}</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">版本复盘</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
                {copy.intro}
              </p>
            </div>

            <Card variant="gradient">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
                <div className="flex-1">
                  <p className="text-xs uppercase tracking-wider text-cyan-300">第一步 · 创建新的版本复盘</p>
                  <label htmlFor="game-query" className="mt-2 block text-xs uppercase tracking-wider text-slate-500">选择游戏</label>
                  <div className="mt-2 flex gap-2">
                    <input
                      id="game-query"
                      value={gameQuery}
                      onChange={(event) => setGameQuery(event.target.value)}
                      onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void findGame(); } }}
                      placeholder="输入游戏名，例如 Apex Legends"
                      className="min-h-11 flex-1 rounded-md border border-cyan-400/20 bg-black/30 px-3 text-sm text-white outline-none transition focus:border-cyan-400/70"
                    />
                    <Button type="button" onClick={() => void findGame()} disabled={eventLoading} variant="primary">搜索</Button>
                  </div>
                  {games.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {games.map((game) => (
                        <button
                          key={game.appid}
                          type="button"
                          onClick={() => { setSelectedAppId(game.appid); setGameQuery(game.name); setGames([]); void loadEvents(game.appid); }}
                          className="block w-full rounded-md border border-white/10 bg-black/20 px-3 py-2 text-left text-sm text-slate-200 hover:border-cyan-400/40"
                        >
                          {game.name} <span className="text-xs text-slate-500">({game.appid})</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex-1">
                    <label htmlFor="analysis-mode" className="text-xs uppercase tracking-wider text-slate-500">分析方式</label>
                    <select
                      id="analysis-mode"
                      value={analysisMode}
                      onChange={(event) => { const value = event.target.value as typeof analysisMode; setAnalysisMode(value); if (selectedAppId && selectedEventId) void createVersionReviewPlan({ app_id: selectedAppId, event_id: selectedEventId, comparison_event_id: comparisonEventId || undefined, semantic_limit: 1000, mode: value, window_days: windowDays }).then((nextPlan) => { setPlan(nextPlan); setComparisonEventId(nextPlan.comparison_event?.event_id || ''); }).catch(() => undefined); }}
                      disabled={!selectedAppId || eventLoading}
                      className="mt-2 min-h-11 w-full rounded-md border border-cyan-400/20 bg-slate-950 px-3 text-sm text-white outline-none focus:border-cyan-400/70"
                    >
                      <option value="version_comparison">版本对比</option>
                    </select>
                  </div>
                  <div className="flex-1">
                    <label htmlFor="event-select" className="text-xs uppercase tracking-wider text-slate-500">当前版本事件（自动识别）</label>
                  <select
                    id="event-select"
                    value={selectedEventId}
                    onChange={(event) => { const value = event.target.value; setSelectedEventId(value); if (selectedAppId && value) void createVersionReviewPlan({ app_id: selectedAppId, event_id: value, semantic_limit: 1000, mode: analysisMode, window_days: windowDays }).then((nextPlan) => { setPlan(nextPlan); setComparisonEventId(nextPlan.comparison_event?.event_id || ''); }).catch(() => undefined); }}
                    disabled={!selectedAppId || eventLoading || events.length === 0}
                    className="mt-2 min-h-11 w-full rounded-md border border-cyan-400/20 bg-slate-950 px-3 text-sm text-white outline-none focus:border-cyan-400/70"
                  >
                      <option value="">{eventLoading ? '正在自动识别版本事件…' : events.length ? '请选择版本事件' : '暂无版本事件'}</option>
                    {events.map((event) => (
                      <option key={event.event_id} value={event.event_id}>
                        {event.event_date} · {event.event_name}
                      </option>
                    ))}
                  </select>
                </div>
                {analysisMode === 'version_comparison' && (
                  <div className="flex-1">
                    <label htmlFor="comparison-event-select" className="text-xs uppercase tracking-wider text-slate-500">对比版本（默认上一可比重大版本）</label>
                    <select
                      id="comparison-event-select"
                      value={comparisonEventId}
                      onChange={(event) => { const value = event.target.value; setComparisonEventId(value); if (selectedAppId && selectedEventId) void createVersionReviewPlan({ app_id: selectedAppId, event_id: selectedEventId, comparison_event_id: value || undefined, semantic_limit: 1000, mode: analysisMode, window_days: windowDays }).then(setPlan).catch(() => undefined); }}
                      disabled={!selectedAppId || eventLoading || events.length === 0}
                      className="mt-2 min-h-11 w-full rounded-md border border-cyan-400/20 bg-slate-950 px-3 text-sm text-white outline-none focus:border-cyan-400/70"
                    >
                      <option value="">自动选择上一可比版本</option>
                      {events.filter((event) => event.event_id !== selectedEventId).map((event) => <option key={event.event_id} value={event.event_id}>{event.event_date} · {event.event_name}</option>)}
                    </select>
                  </div>
                )}
                <div className="flex-1">
                  <label htmlFor="window-days" className="text-xs uppercase tracking-wider text-slate-500">评论分析窗口</label>
                  <select
                    id="window-days"
                    value={windowDays}
                    onChange={(event) => { const value = Number(event.target.value) as 3 | 7 | 14; setWindowDays(value); if (selectedAppId && selectedEventId) void createVersionReviewPlan({ app_id: selectedAppId, event_id: selectedEventId, comparison_event_id: comparisonEventId || undefined, semantic_limit: 1000, mode: analysisMode, window_days: value }).then(setPlan).catch(() => undefined); }}
                    disabled={!selectedAppId || eventLoading}
                    className="mt-2 min-h-11 w-full rounded-md border border-cyan-400/20 bg-slate-950 px-3 text-sm text-white outline-none focus:border-cyan-400/70"
                  >
                    <option value={3}>上线后 3 天</option>
                    <option value={7}>上线后 7 天</option>
                    <option value={14}>上线后 14 天</option>
                  </select>
                </div>
                <Button type="button" onClick={() => void startSelectedReview()} disabled={!selectedAppId || !selectedEventId || executing} variant="primary">
                  {executing ? '正在提取并分析…' : '开始版本复盘'}
                </Button>
              </div>
            </Card>
            {error && <p className="text-sm text-rose-300">{error}</p>}

            {recentVersionReviews.filter((item) => !hiddenRunIds.has(item.run_id)).length > 0 && (
              <Card variant="glass" padding="sm">
                <div className="flex items-center justify-between gap-3">
                  <div><h2 className="text-lg font-semibold text-white">最近版本复盘</h2><p className="mt-1 text-xs text-slate-500">从统一 Analysis Run 历史中打开，不需要记 Run ID。</p></div>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {recentVersionReviews.filter((item) => !hiddenRunIds.has(item.run_id)).slice(0, 6).map((item) => (
                    <div key={item.run_id} className="rounded-lg border border-white/10 bg-black/20 p-3">
                      <div className="flex items-start justify-between gap-3"><div><p className="font-medium text-white">{item.app_name}</p><p className="mt-1 text-xs text-cyan-300">{item.analysis_mode === 'version_comparison' ? '两个版本对比' : item.analysis_mode}</p></div><span className="text-[11px] text-slate-500">{item.completed_at ? `完成 · ${new Date(item.completed_at).toLocaleDateString('zh-CN')}` : item.status}</span></div>
                      <p className="mt-2 text-xs text-slate-400">{countDisplay(item.analysis_population_count, ' 条原始窗口评论')} · {countDisplay(item.classified_count, ' 条成功分类')}</p>
                      <Button type="button" size="sm" variant="primary" className="mt-3" onClick={() => router.push(buildVersionReviewRunUrl(item.run_id))}>打开复盘</Button>
                    </div>
                  ))}
                </div>
              </Card>
            )}


            {run?.status === 'running' && !hasResultMetrics && (
              <Card variant="gradient">
                <p className="text-sm font-medium text-cyan-300">{run.config?.analysis && String((run.config.analysis as { analysis_goal?: unknown }).analysis_goal || '') === 'version_comparison' ? `${activeWindowLabel} A/B 版本对比正在进行：${phaseLabel[run.phase || ''] || '正在处理'}` : `版本复盘正在进行：${phaseLabel[run.phase || ''] || '正在处理'}`}</p>
                <p className="mt-2 text-xs text-slate-500">Run ID：{run.run_id} · 页面每 3 秒自动刷新；评论数量较大时首次复盘可能需要更长时间。</p>
              </Card>
            )}

            {!metrics && !run && !loading && !error && (
              <Card variant="gradient">
                <p className="text-sm text-slate-400">{copy.empty}</p>
              </Card>
            )}

            {hasV2 && v2 && run && (
              <div className="space-y-6">
                {populationStrip?.available && (
                  <Card padding="sm">
                    <div className="grid gap-3 text-xs md:grid-cols-2">
                      <div className="rounded border border-white/10 bg-black/20 p-3"><p className="text-slate-400">{versionReviewDateA}</p><p className="mt-1 text-slate-200">原始 {countDisplay(populationStrip.raw_count_a)} · 语义 {countDisplay(populationStrip.semantic_sample_a)} · 分类 {countDisplay(populationStrip.classified_count_a)}</p><p className="mt-1 text-slate-500">覆盖：{displayZh(zhCoverageStatus, populationStrip.coverage_status_a)}</p></div>
                      <div className="rounded border border-white/10 bg-black/20 p-3"><p className="text-slate-400">{versionReviewDateB}</p><p className="mt-1 text-slate-200">原始 {countDisplay(populationStrip.raw_count_b)} · 语义 {countDisplay(populationStrip.semantic_sample_b)} · 分类 {countDisplay(populationStrip.classified_count_b)}</p><p className="mt-1 text-slate-500">覆盖：{displayZh(zhCoverageStatus, populationStrip.coverage_status_b)}</p></div>
                    </div>
                    <p className="mt-2 text-[11px] text-slate-500">覆盖门槛：{displayZh(zhCoverageStatus, populationStrip.coverage_gate)}</p>
                  </Card>
                )}
                <Card variant="gradient">
                  <div className="flex flex-wrap items-end justify-between gap-4">
                    <div><p className="text-xs uppercase tracking-[0.2em] text-cyan-300">{gameLabel} · Version Review V2</p><h2 className="mt-2 text-2xl font-semibold text-white">{versionReviewDateA} / {versionReviewDateB}</h2><p className="mt-1 text-sm text-slate-400">同一生命周期年龄的可比窗口；先通过覆盖门槛，再解释差异。</p></div>
                    <div className="flex gap-2">{[3, 7, 14].map((days) => <Button key={days} size="sm" variant={selectedWindow === days ? 'primary' : 'secondary'} onClick={() => setSelectedWindow(days)}>{days}天</Button>)}</div>
                  </div>
                  {v2.comparison_status !== 'READY' && <div className="mt-5 rounded-lg border border-amber-300/30 bg-amber-300/10 p-4 text-sm text-amber-100">{displayZh(zhComparisonStatus, v2.comparison_status)}：A/B 生命周期窗口尚未同时通过覆盖校验。A：{displayZh(zhCoverageStatus, v2.a_coverage_status)} · B：{displayZh(zhCoverageStatus, v2.b_coverage_status)}。{v2.coverage_gate?.reason || '请先补抓历史评论，或切换到更宽窗口。'}</div>}
                </Card>

                <Card>
                  <h2 className="text-lg font-semibold text-white">样本与核心指标</h2>
                  <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
                  {[['原始评论', countDisplay(canonicalLeft?.population_n ?? v2.raw_metrics_a.reviews), countDisplay(canonicalRight?.population_n ?? v2.raw_metrics_b.reviews)], ['评论量 / day', v2.raw_metrics_a.reviews_per_day.toFixed(1), v2.raw_metrics_b.reviews_per_day.toFixed(1)], ['推荐率', percent(canonicalLeft?.recommendation_rate ?? v2.raw_metrics_a.recommendation_rate), percent(canonicalRight?.recommendation_rate ?? v2.raw_metrics_b.recommendation_rate)], ['语义样本', countDisplay(v2.a_semantic_sample_count), countDisplay(v2.b_semantic_sample_count)], ['成功分类', trustworthyClassifiedDisplay(v2.a_classified_count), trustworthyClassifiedDisplay(v2.b_classified_count)]].map(([label, a, b]) => <div key={label} className="rounded-lg border border-white/10 bg-black/20 p-3"><p className="text-xs text-slate-500">{label}</p><div className="mt-2 grid grid-cols-2 gap-2 text-lg font-semibold"><span className="text-slate-200">{a}</span><span className="text-slate-400">{b}</span></div><div className="mt-1 grid grid-cols-2 text-[10px] text-slate-600"><span>{versionReviewDateA}</span><span>{versionReviewDateB}</span></div></div>)}
                </div>
                <p className="mt-4 text-sm text-slate-400">评论量变化：{v2.raw_metric_deltas.reviews_per_day >= 0 ? '+' : ''}{v2.raw_metric_deltas.reviews_per_day.toFixed(1)} / day · 推荐率变化：{canonicalComparison?.quantitative.recommendation_rate_delta_pp == null ? '—' : `${canonicalComparison.quantitative.recommendation_rate_delta_pp >= 0 ? '+' : ''}${canonicalComparison.quantitative.recommendation_rate_delta_pp.toFixed(1)}pp`}</p>
                {canonicalComparison && !semanticDeltaAllowed && canonicalComparison.compatibility.semantic_side_by_side_available && <p className="mt-2 text-xs text-amber-200/80">两次分析使用的语义标准不同，因此这里只分别展示结果，不直接计算语义变化。</p>}
                </Card>

                {v2.comparison_status === 'READY' && <>
                  <Card><div className="flex items-center justify-between"><div><h2 className="text-lg font-semibold text-white">版本差异</h2><p className="mt-1 text-xs text-slate-500">问题、需求与正向体验分别比较；不输出单版本重点问题。</p></div><Badge variant="success" size="sm">{v2.topic_comparisons.length} 个问题变化</Badge></div><div className="mt-4 space-y-3">{[...v2.topic_comparisons, ...v2.request_comparisons, ...v2.positive_comparisons].slice(0, 12).map((topic) => <div key={`${topic.topic_id}-${topic.family}`} className="rounded-lg border border-white/10 bg-black/20 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-medium text-white">{formatTaxonomyLabelZh(topic.topic_id)}</p><p className="mt-1 text-xs text-slate-500">{topic.family === 'request' ? '需求变化' : topic.family === 'positive' ? '正向体验变化' : '问题变化'}</p></div><Badge variant={topic.direction === 'up' ? 'warning' : topic.direction === 'down' ? 'success' : 'default'} size="sm">{displayZh(zhVersionState, topic.state)}</Badge></div><div className="mt-3 grid grid-cols-3 gap-3 text-sm"><span> A {percent(topic.a_rate)} · {topic.a_support}</span><span> B {percent(topic.b_rate)} · {topic.b_support}</span><strong className="text-cyan-300">{semanticDeltaAllowed && topic.delta_pp != null ? `${topic.delta_pp >= 0 ? '+' : ''}${topic.delta_pp.toFixed(1)}pp` : '分别展示'}</strong></div></div>)}{!v2.topic_comparisons.length && <p className="text-sm text-slate-500">当前窗口没有达到支持阈值的版本差异。</p>}</div></Card>

                  <Card><h2 className="text-lg font-semibold text-white">成对 Evidence</h2><p className="mt-1 text-xs text-slate-500">同一 Topic 下分别展示两个日期的玩家证据，后端已按 topic、period、review 去重。</p><div className="mt-4 space-y-4">{v2.paired_evidence.slice(0, 6).map((pair) => <div key={pair.topic_id} className="rounded-lg border border-white/10 p-4"><p className="font-medium text-white">{formatTaxonomyLabelZh(pair.topic_id)}</p><div className="mt-3 grid gap-4 md:grid-cols-2"><div><p className="text-xs text-cyan-300">{versionReviewDateA}</p>{pair.a.map((e) => <blockquote key={e.evidence_id} className="mt-2 border-l-2 border-cyan-400/50 pl-3 text-sm text-slate-300">“{e.snippet}”<footer className="text-[10px] text-slate-600">{e.review_id}</footer></blockquote>)}</div><div><p className="text-xs text-fuchsia-300">{versionReviewDateB}</p>{pair.b.map((e) => <blockquote key={e.evidence_id} className="mt-2 border-l-2 border-fuchsia-400/50 pl-3 text-sm text-slate-300">“{e.snippet}”<footer className="text-[10px] text-slate-600">{e.review_id}</footer></blockquote>)}</div></div></div>)}</div></Card>
                </>}

                <Card><div className="flex items-center justify-between"><div><h2 className="text-lg font-semibold text-white">窗口稳健性</h2><p className="mt-1 text-xs text-slate-500">切换窗口会重新取生命周期区间并计算 A/B 指标。</p></div><Badge variant="info" size="sm">当前 {selectedWindow} 天</Badge></div><div className="mt-4 grid gap-3 md:grid-cols-3">{(v2.window_sensitivity || []).map((row) => <button type="button" key={row.window_days} onClick={() => setSelectedWindow(row.window_days)} className={`rounded-lg border p-3 text-left ${selectedWindow === row.window_days ? 'border-cyan-400/60 bg-cyan-400/10' : 'border-white/10 bg-black/20'}`}><p className="text-sm text-white">上线后 {row.window_days} 天</p><p className="mt-1 text-xs text-slate-500">{row.coverage_status === 'COMPLETE' ? '覆盖完整' : '覆盖待验证'} · {row.a_raw_count ?? '—'} / {row.b_raw_count ?? '—'} 条</p></button>)}</div></Card>

                <details><summary className="cursor-pointer text-sm text-slate-400">分析口径</summary><Card className="mt-3"><p className="text-sm text-slate-400">比较窗口：上线后 {v2.window_days} 天 · A/B 覆盖：{displayZh(zhCoverageStatus, v2.a_coverage_status)} / {displayZh(zhCoverageStatus, v2.b_coverage_status)} · 语义样本：{v2.a_semantic_sample_count} / {v2.b_semantic_sample_count}</p></Card></details>
              </div>
            )}

            {hasResultMetrics && metrics && run && !hasV2 && (
              <>
                <div className="grid gap-4 md:grid-cols-4">
                  <Card padding="sm"><p className="text-xs uppercase tracking-wider text-slate-500">版本事件</p><p className="mt-2 text-lg text-white">{versionB ? `${versionAEventDate} vs ${versionBEventDate}` : versionAEventDate}</p></Card>
                  {versionB ? (
                    <>
                      <Card padding="sm"><p className="text-xs uppercase tracking-wider text-slate-500">版本 A 窗口</p><p className="mt-2 text-2xl font-semibold text-slate-200">{countDisplay(versionAWindow?.reviews)}</p><p className="text-xs text-slate-500">推荐率 {percent(versionAWindow?.recommendation_rate)}</p></Card>
                      <Card padding="sm"><p className="text-xs uppercase tracking-wider text-slate-500">版本 B 窗口</p><p className="mt-2 text-2xl font-semibold text-slate-200">{countDisplay(versionBWindow?.reviews)}</p><p className="text-xs text-slate-500">推荐率 {percent(versionBWindow?.recommendation_rate)}</p></Card>
                    </>
                  ) : (
                    <>
                      <Card padding="sm"><p className="text-xs uppercase tracking-wider text-slate-500">更新前评论</p><p className="mt-2 text-2xl font-semibold text-slate-200">{countDisplay(versionA?.periods?.pre?.reviews)}</p><p className="text-xs text-slate-500">推荐率 {percent(versionA?.periods?.pre?.recommendation_rate)}</p></Card>
                      <Card padding="sm"><p className="text-xs uppercase tracking-wider text-slate-500">更新后评论</p><p className="mt-2 text-2xl font-semibold text-slate-200">{countDisplay(versionA?.periods?.post?.reviews)}</p><p className="text-xs text-slate-500">推荐率 {percent(versionA?.periods?.post?.recommendation_rate)}</p></Card>
                    </>
                  )}
                  <Card padding="sm"><p className="text-xs uppercase tracking-wider text-slate-500">评论量指数</p><p className="mt-2 text-2xl font-semibold text-amber-300">{score(versionA?.post_vs_pre_volume_index)}</p><p className="text-xs text-slate-500">更新后 / 更新前基线</p></Card>
                </div>

                {metrics.population_contract && (
                  <Card variant="glass" padding="sm">
                    <div className="grid gap-3 text-xs sm:grid-cols-4">
                      <div><p className="text-slate-500">原始窗口样本</p><p className="mt-1 text-lg text-white">{countDisplay(metrics.population_contract.raw_window_count, ' 条')}</p></div>
                      <div><p className="text-slate-500">语义分析样本</p><p className="mt-1 text-lg text-slate-200">{countDisplay(metrics.population_contract.semantic_sample_count, ' 条')}</p></div>
                      <div><p className="text-slate-500">成功分类</p><p className="mt-1 text-lg text-slate-200">{trustworthyClassifiedDisplay(metrics.population_contract.classified_count)}{metrics.population_contract.classified_count ? ' 条' : ''}</p></div>
                      <div><p className="text-slate-500">抽样方式</p><p className="mt-1 text-white">确定性分层抽样</p></div>
                    </div>
                  </Card>
                )}

                <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
                  <Card>
                    <div className="flex items-center justify-between gap-4">
                      <div><h2 className="text-lg font-semibold text-white">{copy.priority}</h2><p className="mt-1 text-xs text-slate-500">一个评论可以同时命中多个分类；这里的数量是问题分类提及次数，不等于独立缺陷数量。</p></div>
                      <Badge variant="info" size="sm">{topIssues.length} 个重点</Badge>
                    </div>
                    <div className="mt-5 space-y-3">
                      {topIssues.length === 0 && <p className="text-sm text-slate-500">本次复盘没有发现可行动的问题。</p>}
                      {topIssues.map((issue, issueIndex) => (
                        <div key={`${issue.issue_id}-${issue.subcategory}-${issueIndex}`} className="rounded-lg border border-white/10 bg-black/20 p-4">
                          <div className="flex items-start justify-between gap-4">
                            <div><p className="font-medium text-white">{formatTaxonomyLabelZh(issue.subcategory)}</p><p className="mt-1 text-xs text-slate-500">更新后负面率 {percent(issue.post_negative_rate)} · {confidenceZh(issue.confidence)}</p></div>
                            <span className="text-xl font-semibold text-cyan-300">{score(issue.priority_score)}</span>
                          </div>
                          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-fuchsia-400" style={{ width: `${Math.min(100, Math.max(0, issue.priority_score))}%` }} /></div>
                        </div>
                      ))}
                    </div>
                  </Card>

                  <Card>
                    <div className="flex items-center justify-between gap-4"><div><h2 className="text-lg font-semibold text-white">{copy.evidence}</h2><p className="mt-1 text-xs text-slate-500">保留原评论片段，并关联到来源评论 ID，便于人工复核。</p></div><Badge variant="success" size="sm">{(metrics.evidence_cards || []).length} 条证据</Badge></div>
                    <div className="mt-5 space-y-3">
                      {(metrics.evidence_cards || []).slice(0, 6).map((evidence, evidenceIndex) => (
                        <blockquote key={`${evidence.evidence_id}-${evidence.review_id}-${evidence.period}-${evidenceIndex}`} className="border-l-2 border-cyan-400/50 pl-3 text-sm leading-6 text-slate-300">
                          “{evidence.snippet}”<footer className="mt-1 text-[11px] text-slate-500">原文证据 · {formatTaxonomyLabelZh(evidence.subcategory)} · {periodZh(evidence.period)} · 评论 {evidence.review_id}</footer>
                        </blockquote>
                      ))}
                    </div>
                  </Card>
                </div>

                <Card>
                  <div className="flex items-center justify-between gap-4"><div><h2 className="text-lg font-semibold text-white">{copy.actions}</h2><p className="mt-1 text-xs text-slate-500">建议是待验证假设，不是已经证明的因果结论。</p></div><Badge variant="warning" size="sm">待验证</Badge></div>
                  <div className="mt-5 grid gap-4 lg:grid-cols-2">
                    {recommendations.map((recommendation, recommendationIndex) => (
                      <div key={`${recommendation.recommendation_id}-${recommendationIndex}`} className="rounded-lg border border-amber-300/15 bg-amber-300/5 p-4">
                        <div className="flex items-center justify-between gap-3"><p className="font-medium text-white">{formatTaxonomyLabelZh(recommendation.subcategory)}</p><Badge variant="default" size="sm">{actionTypeZh(recommendation.action_type)}</Badge></div>
                        <p className="mt-3 text-sm leading-6 text-slate-300">{recommendationZh(recommendation.subcategory, recommendation.action_type)}</p>
                        <p className="mt-3 text-xs text-slate-500">验证指标：{recommendation.validation_metrics.map(validationMetricZh).join(' · ')}</p>
                      </div>
                    ))}
                  </div>
                </Card>

              </>
            )}
          </div>
        </div>
      </PageTransition>
    </AppLayout>
  );
}

export default function VersionReviewPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[rgb(5,5,15)]" />}>
      <VersionReviewContent />
    </Suspense>
  );
}
