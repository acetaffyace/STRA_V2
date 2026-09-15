import { apiFetch, apiUrl } from '@/lib/api';
import type { VersionEventResponse } from '@/lib/api';

export type VersionComparisonCohort = 'A_PRE' | 'A_POST' | 'B_PRE' | 'B_POST';
export type VersionComparisonAnalysisMode = 'raw_only' | 'semantic';

export interface VersionComparisonRequest {
  app_id: number;
  event_a_id: string;
  event_b_id: string;
  window_days: 3 | 7 | 14;
  languages: string[];
  max_reviews_per_cohort: 500 | 1000 | 2000 | 5000 | 10000;
  analysis_mode: VersionComparisonAnalysisMode;
  semantic_budget: number;
}

export interface VersionComparisonWindow {
  cohort: VersionComparisonCohort;
  event_id?: string;
  event_name?: string;
  side: 'pre' | 'post';
  start_time: number;
  end_time_exclusive: number;
  window_days: number;
  boundary_mode: 'event_day_excluded' | 'exact_timestamp' | string;
}

export interface VersionComparisonPlan {
  schema_version: 'version-comparison-plan-v3' | string;
  app_id: number;
  event_a: VersionEventResponse;
  event_b: VersionEventResponse;
  orientation: string;
  window_days: number;
  acquisition_window_days: number;
  cohorts: Record<VersionComparisonCohort, VersionComparisonWindow>;
  acquisition_cohorts: Record<VersionComparisonCohort, VersionComparisonWindow>;
  analysis_mode: VersionComparisonAnalysisMode;
  max_reviews_per_cohort: number;
  languages: string[];
  semantic_sampling: {
    enabled: boolean;
    total_budget: number;
    dimensions: string[];
    target: string;
    equal_cohort_size: boolean;
    balances_recommendation_outcome: boolean;
    classifier_is_cohort_blind: boolean;
  };
  raw_metrics: string[];
  confounders: Array<{ event_id?: string; event_name?: string; event_type?: string; event_date?: string; severity: 'minor' | 'major' | string }>;
  confounder_risk: 'clean' | 'minor' | 'major' | string;
}

export interface VersionCohortSummary {
  reviews: number;
  outcome_valid_n: number;
  recommended: number;
  not_recommended: number;
  recommendation_rate: number | null;
  recommendation_ci95: [number | null, number | null];
  languages: Record<string, number>;
}

export interface VersionComparisonTopic {
  topic_id: string;
  display_name: string;
  family: 'problem' | 'request' | 'positive' | string;
  support: Record<VersionComparisonCohort, number>;
  rates: Record<VersionComparisonCohort, number | null>;
  a_change_pp: number | null;
  b_change_pp: number | null;
  difference_in_differences_pp: number | null;
}

export interface SemanticSampleManifest {
  schema_version: string;
  status: string;
  method: string;
  seed: string;
  total_budget: number;
  target_per_cohort: number;
  actual_total: number;
  balancing_dimensions: string[];
  outcome_balanced: boolean;
  common_support_strata: string[];
  target_distribution: Record<string, number>;
  quotas: Record<string, number>;
  selected_review_ids: Record<VersionComparisonCohort, string[]>;
}

export interface VersionComparisonMetrics {
  schema_version: 'version-comparison-v3' | string;
  event_a: VersionEventResponse;
  event_b: VersionEventResponse;
  orientation: string;
  window_days: number;
  acquisition_window_days: number;
  analysis_mode: VersionComparisonAnalysisMode;
  coverage_status: 'COMPLETE' | 'PARTIAL' | string;
  raw: {
    cohorts: Record<VersionComparisonCohort, VersionCohortSummary>;
    deltas: {
      a_pre_to_post_pp: number | null;
      b_pre_to_post_pp: number | null;
      b_post_minus_a_post_pp: number | null;
      difference_in_differences_pp: number | null;
    };
    interpretation: string;
  };
  comparability: Record<string, { comparability?: { level?: string; warnings?: string[] }; composition_comparability?: { level?: string } }>;
  standardization_sensitivity: Record<string, Record<string, unknown>>;
  window_sensitivity: Array<{
    window_days: number;
    a_pre_to_post_pp: number | null;
    b_pre_to_post_pp: number | null;
    b_post_minus_a_post_pp: number | null;
    difference_in_differences_pp: number | null;
    counts: Record<VersionComparisonCohort, number>;
  }>;
  confounders: VersionComparisonPlan['confounders'];
  confounder_risk: string;
  semantic_sample_manifest: SemanticSampleManifest | null;
  semantic: null | {
    status: string;
    sample_counts?: Record<VersionComparisonCohort, number>;
    classified_counts?: Record<VersionComparisonCohort, number>;
    topics: VersionComparisonTopic[];
    problems: VersionComparisonTopic[];
    requests: VersionComparisonTopic[];
    general?: VersionComparisonTopic[];
    positives: VersionComparisonTopic[];
    positive_topic_denominator?: string;
  };
  warnings: string[];
  progress?: { stage?: string; cohort?: string; completed?: number; total?: number };
}

export interface VersionComparisonRun {
  run_id: string;
  target_app_id: number;
  event_id: string;
  status: string;
  phase?: string | null;
  config: Record<string, unknown>;
  metrics?: VersionComparisonMetrics | Record<string, unknown> | null;
  error?: string | null;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = '';
    try {
      const payload = await response.json() as { detail?: string };
      detail = payload.detail || '';
    } catch {
      detail = await response.text().catch(() => '');
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function normalizePhase(phase?: string | null): string | null | undefined {
  if (!phase) return phase;
  const match = phase.match(/^acquiring_(?:population|primary|sensitivity_\d+d)_(a_pre|a_post|b_pre|b_post)$/);
  return match ? `acquiring_${match[1]}` : phase;
}

function normalizeRunForUi(run: VersionComparisonRun): VersionComparisonRun {
  // The current page polls while status === 'running'. Treat backend queue
  // states as active client states so a freshly-created run cannot strand the
  // UI before the BackgroundTask has had a chance to transition it.
  const status = run.status === 'created' || run.status === 'queued' ? 'running' : run.status;
  return { ...run, status, phase: normalizePhase(run.phase) };
}

export async function createVersionComparisonPlan(payload: VersionComparisonRequest): Promise<VersionComparisonPlan> {
  const response = await apiFetch(apiUrl('/version-comparison/plan'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<VersionComparisonPlan>(response);
}

export async function startVersionComparison(payload: VersionComparisonRequest): Promise<{ run: VersionComparisonRun; plan: VersionComparisonPlan }> {
  const response = await apiFetch(apiUrl('/version-comparison/start'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const result = await handleResponse<{ run: VersionComparisonRun; plan: VersionComparisonPlan }>(response);
  return { ...result, run: normalizeRunForUi(result.run) };
}

export async function fetchVersionComparisonRun(runId: string): Promise<VersionComparisonRun> {
  const response = await apiFetch(apiUrl(`/version-comparison/runs/${encodeURIComponent(runId)}`), { cache: 'no-store' });
  return normalizeRunForUi(await handleResponse<VersionComparisonRun>(response));
}

export async function fetchVersionComparisonRuns(appId?: number): Promise<VersionComparisonRun[]> {
  const query = appId ? `?app_id=${appId}` : '';
  const response = await apiFetch(apiUrl(`/version-comparison/runs${query}`), { cache: 'no-store' });
  const runs = await handleResponse<VersionComparisonRun[]>(response);
  return runs.map(normalizeRunForUi);
}
