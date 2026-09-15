import {
  AnalyzeResponse,
  AnalyzeMetadata,
  ProgressStatus,
  SearchResult,
  StarredGameDTO,
  StarredGamePayload,
  AnalysisResultResponse,
  LogTailResponse,
  DatabaseReviewsResponse,
  DatabaseGameOption,
  ComparisonSummarizeRequest,
  ComparisonSummary,
  ResearchReport,
  SemanticStatus,
  ResearchEngineReadiness,
  SemanticEngineReadiness,
} from "@/types";
import type { SamplingContract } from "@/types/acquisition";

declare global {
  interface Window {
    __SENTINEXT_API_BASE__?: string;
    __SENTINEXT_BACKEND_LOG_FILE__?: string;
    __SENTINEXT_BACKEND_BOOT_ERROR__?: string | null;
  }
}

function normalizeBase(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

function getApiBase(): string {
  if (typeof window !== "undefined" && window.__SENTINEXT_API_BASE__) {
    return normalizeBase(window.__SENTINEXT_API_BASE__);
  }
  // Packaged desktop must never fall through to the static /api path. The
  // Tauri command handshake is responsible for populating the dynamic URL.
  if (typeof window !== "undefined" && (window.location.protocol === "tauri:" || window.location.hostname === "tauri.localhost")) {
    return "";
  }
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return normalizeBase(process.env.NEXT_PUBLIC_API_BASE_URL);
  }
  // Dev mode fallback: any local Next.js port uses the local backend on 8000.
  // This also covers port 3001+ when another process already occupies 3000.
  if (
    typeof window !== "undefined" &&
    (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") &&
    window.location.port !== "8000"
  ) {
    return "http://127.0.0.1:8000";
  }
  // Local app default: UI served by backend, API mounted under /api.
  return "/api";
}

export function apiUrl(pathname: string): string {
  const base = getApiBase();
  if (!pathname.startsWith("/")) {
    throw new Error(`API path must start with '/': ${pathname}`);
  }
  if (base.startsWith("http://") || base.startsWith("https://")) {
    return new URL(pathname, base).toString();
  }
  return `${base}${pathname}`;
}

export function buildDashboardRunUrl(appId: number, runId: string): string {
  return `/dashboard?game=${encodeURIComponent(appId)}&run=${encodeURIComponent(runId)}`;
}

export function buildVersionReviewRunUrl(runId: string): string {
  return `/version-review?run=${encodeURIComponent(runId)}`;
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("无法连接 STRA 后端。请确认当前页面来自 127.0.0.1:3000，后端运行在 127.0.0.1:8000。", { cause: error });
    }
    throw error;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      const d = body?.detail;
      detail = typeof d === "string" ? d : d?.message || JSON.stringify(d);
    } catch {
      try {
        detail = await response.text();
      } catch { /* ignore */ }
    }
    if (response.status === 429) {
      throw new Error(detail || "You're making requests too quickly. Please wait a moment and try again.");
    }
    throw new Error(detail || `Request failed with status ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function searchGames(query: string): Promise<SearchResult[]> {
  const url = new URL(apiUrl("/search"), typeof window !== "undefined" ? window.location.origin : "http://localhost");
  url.searchParams.set("query", query);
  const response = await apiFetch(url.toString(), { cache: "no-store" });
  return handleResponse<SearchResult[]>(response);
}

export interface AnalyzePayload {
  app_id: number;
  /** New callers should provide this explicit population contract. */
  sampling?: SamplingContract;
  /** Legacy fields remain available for older UI flows and API consumers. */
  review_count: number;
  language: string;
  languages?: string[];
  filter: string;
  day_range?: number | null;
  persist?: boolean;
  refresh?: boolean;
  refresh_days?: number | null;
  output_language?: "zh" | "en" | "ja";
}

export async function analyzeGame(payload: AnalyzePayload): Promise<AnalyzeResponse> {
  const response = await apiFetch(apiUrl("/analyze"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<AnalyzeResponse>(response);
}

export async function fetchProgress(appId: number): Promise<ProgressStatus> {
  const response = await apiFetch(apiUrl(`/progress/${appId}`), {
    cache: "no-store",
  });
  return handleResponse<ProgressStatus>(response);
}

export async function cancelAnalysis(appId: number): Promise<{ cancelled: boolean; app_id: number }> {
  const response = await apiFetch(apiUrl(`/progress/${appId}/cancel`), {
    method: "POST",
  });
  return handleResponse<{ cancelled: boolean; app_id: number }>(response);
}

export interface ProgressStreamEvent {
  type: "progress" | "completed" | "error" | "timeout";
  processed?: number;
  total?: number;
  active?: boolean;
  status?: string;
  error?: string;
  phase?: "fetching" | "ingesting" | "research_core" | "classifying" | "building_insights" | "aggregating" | "finalizing" | "idle" | string;
  fetched_count?: number;
  eta_seconds?: number | null;
  run_id?: string | null;
  run_status?: string;
  run_phase?: string | null;
  immutable_result_available?: boolean;
}

export interface ProgressStreamCallbacks {
  onProgress?: (processed: number, total: number, active: boolean, phase?: "fetching" | "ingesting" | "research_core" | "classifying" | "building_insights" | "aggregating" | "finalizing" | "idle" | string, fetchedCount?: number, etaSeconds?: number | null, runStatus?: string, runPhase?: string | null, immutableResultAvailable?: boolean) => void;
  onCompleted?: () => void;
  onError?: (error: string) => void;
  onTimeout?: () => void;
}

/**
 * Detect whether an SSE error string is a connection-level issue
 * (as opposed to a backend-reported analysis failure).
 */
export function isSseConnectionError(error: string | undefined | null): boolean {
  if (!error) return true;
  if (error === "Connection lost" || error === "Connection failed") return true;
  const lower = error.toLowerCase();
  return (
    lower.includes("expected pattern") ||
    lower.includes("failed to construct") ||
    lower.includes("eventsource")
  );
}

function normalizeSseStartError(error: unknown): string {
  const message = error instanceof Error ? error.message : "Failed to start stream";
  if (isSseConnectionError(message)) return "Connection failed";
  return message;
}

/**
 * Subscribe to real-time progress updates via Server-Sent Events.
 * Returns a cleanup function to close the connection.
 */
export function subscribeToProgress(
  appId: number,
  callbacks: ProgressStreamCallbacks
): () => void {
  if (typeof EventSource === "undefined") {
    throw new Error("EventSource is not supported in this environment");
  }

  const base =
    typeof window !== "undefined" ? window.location.origin : "http://localhost";
  const url = new URL(apiUrl(`/progress/${appId}/stream`), base);

  let eventSource: EventSource | null = null;
  let aborted = false;

  const start = () => {
    try {
      if (aborted) return;
      if (url.protocol !== "http:" && url.protocol !== "https:") {
        callbacks.onError?.("Connection failed");
        return;
      }
      eventSource = new EventSource(url.toString());

      eventSource.addEventListener("progress", (event) => {
        try {
          const data = JSON.parse(event.data) as ProgressStreamEvent;
          callbacks.onProgress?.(
            data.processed ?? 0,
            data.total ?? 0,
            data.active ?? false,
            data.phase,
            data.fetched_count,
            data.eta_seconds,
            data.run_status,
            data.run_phase,
            data.immutable_result_available
          );
        } catch {
          // Ignore parse errors
        }
      });

      eventSource.addEventListener("completed", () => {
        callbacks.onCompleted?.();
        eventSource?.close();
      });

      eventSource.addEventListener("error", (event) => {
        if (event instanceof MessageEvent && event.data) {
          try {
            const data = JSON.parse(event.data) as ProgressStreamEvent;
            callbacks.onError?.(data.error ?? "Unknown error");
          } catch {
            callbacks.onError?.("Connection error");
          }
        } else {
          callbacks.onError?.("Connection lost");
        }
      });

      // The rest of this file is unchanged from the branch baseline.
    } catch (error) {
      callbacks.onError?.(normalizeSseStartError(error));
    }
  };

  start();
  return () => {
    aborted = true;
    eventSource?.close();
  };
}
