export interface SearchResult {
  appid: number;
  name: string;
  price?: string | null;
  url: string;
  image_url?: string | null;
}

export interface AnalyzeMetadata {
  app_id: number;
  requested: number;
  retrieved: number;
  requested_limit?: number | null;
  available_matching_reviews?: number | null;
  retrieved_count?: number | null;
  deduplicated_count?: number | null;
  analysis_population_count?: number | null;
  language: string;
  fetched_at?: string | null;
  mode?: string | null;
  source?: string | null;
  run_id?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  data_cutoff?: string | null;
  active_filters?: Record<string, unknown> | null;
  classification_population?: number | null;
  evidence_population?: number | null;
  header_image?: string | null;
  // Price fields
  price_initial?: number | null;       // Original price in major units (e.g., 29.99)
  price_final?: number | string | null; // Current price or "Free"
  price_initial_formatted?: string;     // e.g., "$29.99"
  price_final_formatted?: string;       // e.g., "$19.99"
  price_discount?: number;              // Discount percentage (0-100)
  price_currency?: string | null;       // e.g., "USD"
  is_free?: boolean;
}

export interface ResearchPopulation {
  review_count: number;
  sampling_contract?: SamplingContractSnapshot | null;
  collection_complete?: boolean | null;
  truncated_by_max_reviews?: boolean | null;
  stop_reason?: string | null;
  coverage_start_time?: number | null;
  coverage_end_time?: number | null;
  coverage_status?: string | null;
  coverage_end_inclusive?: boolean | null;
}

export interface SamplingContractSnapshot {
  app_id?: number;
  start_time?: number | null;
  end_time?: number | null;
  languages?: string[];
  review_type?: "all" | "positive" | "negative" | string;
  purchase_type?: "all" | "steam" | "non_steam_purchase" | string;
  collection_order?: "recent" | "updated" | "helpful" | string;
  include_offtopic_activity?: boolean | null;
  max_reviews?: number | null;
}

export interface RecommendationPopulation {
  valid_n?: number | null;
  recommended_n?: number | null;
  not_recommended_n?: number | null;
  missing_n?: number | null;
  recommendation_rate?: number | null;
}

export interface RecommendationInterval {
  lower?: number | null;
  upper?: number | null;
  confidence_level?: number | null;
  method?: string | null;
  estimate?: number | null;
}

export interface RecommendationInferenceValidity {
  inference_eligibility?: string | null;
  reason?: string | null;
  observed_metric_status?: string | null;
}

export interface RecommendationInferenceReport {
  population?: RecommendationPopulation | null;
  model_based_interval?: RecommendationInterval | null;
  inference_validity?: RecommendationInferenceValidity | null;
}

export interface ActivityPopulation {
  raw_review_count?: number | null;
  unique_review_id_count?: number | null;
  missing_timestamp_n?: number | null;
  missing_text_n?: number | null;
}

export interface ActivityTextRepetition {
  unique_text_share?: number | null;
  exact_duplicate_review_count?: number | null;
  exact_duplicate_share?: number | null;
  near_copy_additional_review_count?: number | null;
  near_copy_additional_share?: number | null;
  coordinated_expression_review_count?: number | null;
  coordinated_expression_share?: number | null;
}

export interface ActivitySummary {
  activity_spike_detected?: boolean | null;
  coordinated_expression_detected?: boolean | null;
  coordinated_expression_level?: string | null;
}

export interface ActivityMethodology {
  candidate_diagnostics?: { candidate_generation_complete?: boolean | null } | null;
}

export interface ActivitySpikeReport {
  spike_bin_count?: number | null;
  bins?: Array<Record<string, unknown>>;
}

export interface ReviewActivityReport {
  population?: ActivityPopulation | null;
  text_repetition?: ActivityTextRepetition | null;
  spikes?: ActivitySpikeReport | null;
  summary?: ActivitySummary | null;
  methodology?: ActivityMethodology | null;
  time_series?: { grain?: string; bins?: Array<Record<string, unknown>> } | null;
}

export interface UnavailableResearchSection {
  status?: "unavailable" | string;
  reason?: string | null;
}

export interface ResearchLimitations {
  steam_reviewer_selection?: boolean;
  not_all_players?: boolean;
  recommendation_is_not_text_sentiment?: boolean;
  observational_not_causal?: boolean;
  no_version_change_claim_from_snapshot?: boolean;
  reviewer_selection_limitation?: string;
}

export interface ResearchOrchestration {
  research_core_version?: string;
  stages_executed?: string[];
  stages_unavailable?: Record<string, string>;
  configuration?: {
    confidence_level?: number | null;
    requested_standardization_variables?: string[] | null;
    effective_standardization_variables?: string[] | null;
    standardization_target?: string | null;
    windows_days?: number[] | null;
    activity_grain?: string | null;
  };
}

export interface SnapshotResearchReport {
  schema_version: "research-report-v1";
  mode: "snapshot";
  population: ResearchPopulation;
  recommendation: RecommendationInferenceReport;
  activity: ReviewActivityReport;
  comparability: UnavailableResearchSection;
  standardization: UnavailableResearchSection;
  window_robustness: UnavailableResearchSection;
  limitations: ResearchLimitations;
  orchestration: ResearchOrchestration;
}

/** Forward-compatible envelope for unknown future Research Report schemas. */
export interface ResearchReport {
  schema_version: string;
  mode: string;
  population?: ResearchPopulation;
  recommendation?: RecommendationInferenceReport;
  activity?: ReviewActivityReport;
  comparability?: UnavailableResearchSection;
  standardization?: UnavailableResearchSection;
  window_robustness?: UnavailableResearchSection;
  limitations?: ResearchLimitations;
  orchestration?: ResearchOrchestration;
}

export type SemanticState = "pending" | "available" | "unavailable" | "failed" | string;

export interface SemanticStatus {
  status: SemanticState;
  reason?: string | null;
  provider?: string | null;
  model_id?: string | null;
}

export interface ResearchEngineReadiness {
  available: boolean;
  status?: string | null;
  reason?: string | null;
}

export interface SemanticEngineReadiness {
  available: boolean;
  status?: string | null;
  mode?: string | null;
  reason?: string | null;
}

export interface LogTailResponse {
  log_file: string;
  tail: string;
}

export interface TrendPoint {
  period: string;
  recommendation_rate: number;
  avg_compound: number;
  reviews: number;
}


export interface SentimentCount {
  sentiment: string;
  count: number;
}

export interface InsightSegments {
  early_access_vs_release: Record<string, unknown>[];
  free_vs_paid: Record<string, unknown>[];
  playtime_buckets: Record<string, unknown>[];
}

export interface AudienceSegments {
  reviewer_influence: Record<string, unknown>[];
  veteran_benchmarking: Record<string, unknown>[];
  market_quality: Record<string, unknown>[];
}

export interface RiskMetrics {
  refund_risk: number;
  core_fan_disappointment: number;
}


export interface ThemeDefinition {
  name: string;
  gradient: string[];
  palette: {
    accent: string;
    secondary: string;
    positive: string;
    neutral: string;
    negative: string;
    surface: string;
    surface_alt: string;
    border: string;
  };
}

export interface IssueCategory {
  category: string;
  count: number;
}

export interface ExperienceLevelSegment {
  count: number;
  recommendation_rate: number;
}

export interface ExperienceLevelIssues {
  newcomers: ExperienceLevelSegment;
  casual: ExperienceLevelSegment;
  experienced: ExperienceLevelSegment;
  veterans: ExperienceLevelSegment;
}

export interface PurchaseTypeSegment {
  count: number;
  feature_request_rate: number;
  recommendation_rate: number;
}

export interface PurchaseTypeInsights {
  steam_buyers: PurchaseTypeSegment;
  key_users: PurchaseTypeSegment;
  free_users: PurchaseTypeSegment;
}

export interface TopicWithCount {
  topic: string;
  count: number;
}

export interface EngagementSegment {
  count: number;
  recommendation_rate: number;
}

export interface EngagementBasedTopics {
  highly_engaged: EngagementSegment;
  moderately_engaged: EngagementSegment;
  low_engagement: EngagementSegment;
}

export interface ActivitySegment {
  count: number;
  recommendation_rate: number;
  issue_count: number;
}

export interface ActivityBasedFeedback {
  currently_active: ActivitySegment;
  recently_stopped: ActivitySegment;
  inactive: ActivitySegment;
}

export interface PlatformSegment {
  count: number;
  recommendation_rate: number;
  top_issues: IssueCategory[];
  issue_count: number;
}

export interface PlatformSegmentInsights {
  steam_deck: PlatformSegment;
  desktop: PlatformSegment;
}

export interface LanguageSegment {
  language: string;
  count: number;
  recommendation_rate: number;
  top_issues: IssueCategory[];
  issue_count: number;
}

export interface LanguageSegmentInsights {
  languages: LanguageSegment[];
  total_languages: number;
}

export interface WeightedIssue {
  category: string;
  weighted_count: number;
}

export interface QualityWeightedInsights {
  high_quality_reviews: number;
  avg_helpfulness: number;
  weighted_top_issues: WeightedIssue[];
  weighted_recommendation_rate: number;
}

export interface CrossSegmentData {
  label: string;
  segments: string[];
  count: number;
  recommendation_rate: number;
  top_issues: IssueCategory[];
}

export interface NotableFinding {
  segment: string;
  finding: string;
  count: number;
  recommendation_rate: number;
  overall_rate: number;
  diff?: number;
  severity?: 'info' | 'success' | 'warning' | 'critical';
  top_issues?: IssueCategory[];
  share_of_total?: number;
}

export interface CrossSegmentAnalysis {
  cross_segments: CrossSegmentData[];
  notable_findings: NotableFinding[];
}

export interface PlayerSegments {
  experience_level: ExperienceLevelIssues;
  purchase_type: PurchaseTypeInsights;
  engagement_topics: EngagementBasedTopics;
  activity_status: ActivityBasedFeedback;
  platform?: PlatformSegmentInsights;
  language?: LanguageSegmentInsights;
}

export interface SubcategoryInsight {
  subcategory: string;
  main_category: string;
  sub_category: string;
  count: number;
  recommendation_rate?: number;
  recommended?: number;
  not_recommended?: number;
  issue_count: number;
  request_count: number;
  issue_snippets?: string[];
  request_snippets?: string[];
}

export interface SubcategoryCount {
  subcategory: string;
  count: number;
}

export interface CategoryBreakdown {
  [mainCategory: string]: {
    [subcategory: string]: number;
  };
}

export interface CategoryRecommendationRate {
  rate: number;
  count: number;
  recommended: number;
  not_recommended: number;
}

export interface CategoryTrendPoint {
  period: string;
  count: number;
}

export interface VersionInsight {
  total_reviews: number;
  recommendation_rate: number;
  top_issue_subcategories: SubcategoryCount[];
  top_request_subcategories: SubcategoryCount[];
  top_categories: Record<string, number>;
}

export interface HealthOverviewData {
  summary: string;
  key_points: string[];
  actions: string[];
  health_score: number;
  sentiment_trend: "improving" | "stable" | "declining";
  top_strengths: string[];
}

export interface InsightsResponse {
  metrics: Record<string, number>;
  llm: LLMMetrics;
  category_breakdown: CategoryBreakdown;
  category_recommendation_rates?: Record<string, CategoryRecommendationRate>;
  category_trend?: Record<string, CategoryTrendPoint[]>;
  version_insights?: Record<string, VersionInsight>;
  subcategory_insights?: SubcategoryInsight[];
  playtime: Record<string, number>;
  helpful: Record<string, number>;
  recommendation: number;
  sentiment_counts: SentimentCount[];
  trend: TrendPoint[];
  segments: InsightSegments;
  audience: AudienceSegments;
  risk: RiskMetrics;
  player_segments?: PlayerSegments;
  quality_weighted?: QualityWeightedInsights;
  cross_segment?: CrossSegmentAnalysis;
  theme?: ThemeDefinition;
  health_overview?: HealthOverviewData | null;
  metric_provenance?: Record<string, MetricObservation>;
  five_questions?: FiveQuestionContract;
}

export interface FiveQuestionContract {
  mode?: string;
  run_id?: string | null;
  what_changed?: { status?: string; reason?: string; confidence_note?: string };
  current_snapshot?: {
    status?: string;
    recommendation?: Record<string, unknown> | null;
    strongest_positive_signal?: Record<string, unknown> | null;
    leading_problem_signal?: Record<string, unknown> | null;
    leading_request_signal?: Record<string, unknown> | null;
    observed_cohort_concentration?: Array<Record<string, unknown>>;
    note?: string;
  };
  what_matters?: { signals?: Array<Record<string, unknown>>; is_heuristic?: boolean };
  recommended_actions?: Array<{ action_class?: string; title?: string; taxonomy_key?: string; rationale?: string; uncertainty?: string; validation_plan?: string; evidence?: Array<Record<string, unknown>> }>;
}

export interface MetricObservation {
  metric_id: string;
  value: number | null;
  numerator: number | null;
  denominator: number | null;
  population_count: number | null;
  eligible_count: number | null;
  classified_count: number | null;
  coverage: number | null;
  source_type: string;
  denominator_type: string;
  is_sampled: boolean;
  run_id: string | null;
  formula_version: string;
  sampling_semantics: string | null;
  status: string;
  unavailable_reason: string | null;
}

export interface ReviewRow {
  review_id: string | number | null;
  review: string;
  language: string;
  voted_up: boolean;  // Steam's official thumbs up/down (the only sentiment indicator)
  votes_up: number;
  votes_funny: number;
  author_num_games_owned: number;
  author_num_reviews: number;
  author_playtime_forever: number;
  author_playtime_last_two_weeks: number;
  author_playtime_hours?: number;
  author_recent_playtime_hours?: number;
  created_at?: string;
  steam_purchase?: boolean;
  received_for_free?: boolean;
  primarily_steam_deck?: boolean;
  // v7 LLM insights (hierarchical)
  llm_main_category?: string;
  llm_subcategory?: string;
  llm_subcategories?: string[];
  llm_issue_subcategories?: string[];
  llm_request_subcategories?: string[];
  llm_subcategory_evidence?: Record<string, string[]>;
  llm_has_issue?: boolean;
  llm_has_request?: boolean;
}

export interface AnalyzeResponse {
  metadata: AnalyzeMetadata;
  insights: InsightsResponse | null;
  research_report?: ResearchReport | null;
  semantic_status?: SemanticStatus | null;
  reviews: ReviewRow[];
  stale?: boolean;
  stale_reason?: string | null;
  label_estimate?: LabelReuseEstimate | null;
  run_id?: string | null;
}

export interface LabelReuseEstimate {
  total_reviews: number;
  cached_reviews: number;
  llm_reviews: number;
  needs_refresh_reviews: number;
  empty_reviews: number;
  short_reviews: number;
  reasons: Record<string, number>;
}

export interface StarredGame {
  metadata: AnalyzeMetadata;
  insights: InsightsResponse | null;
  sample: ReviewRow[];
  name: string;
  genres?: string[];
  categories?: string[];
  updated_at?: string;
}

export type AnalysisJobStatus = "pending" | "running" | "completed" | "failed" | "unknown";

export interface AnalysisResultResponse {
  status: AnalysisJobStatus;
  metadata?: AnalyzeMetadata | null;
  insights: InsightsResponse | null;
  research_report?: ResearchReport | null;
  semantic_status?: SemanticStatus | null;
  reviews: ReviewRow[];
  error?: string | null;
  run_id?: string | null;
  snapshot_hash?: string | null;
  stale?: boolean;
  stale_reason?: string | null;
  data_refreshed?: boolean;
}


export interface LLMMetrics {
  feature_request_rate: number;
  issue_rate: number;
  coverage_rate?: number;   // Share of reviews with structured labels
}


export interface ProgressStatus {
  app_id: number;
  total: number;
  processed: number;
  updated_at: string | null;
  active: boolean;
  phase?: 'fetching' | 'ingesting' | 'research_core' | 'classifying' | 'building_insights' | 'aggregating' | 'finalizing' | 'idle' | string;
  fetched_count?: number;
  eta_seconds?: number | null;
  run_id?: string | null;
  run_status?: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'idle' | string;
  run_phase?: string | null;
  immutable_result_available?: boolean;
  analysis_population_count?: number | null;
}

export interface StarredGamePayload {
  app_id: number;
  name: string;
  metadata: AnalyzeMetadata;
  insights: InsightsResponse | null;
  sample: ReviewRow[];
}

export interface StarredGameDTO {
  app_id: number;
  name: string;
  metadata: AnalyzeMetadata;
  insights: InsightsResponse | null;
  sample: ReviewRow[];
  genres?: string[];
  categories?: string[];
  updated_at: string;
  is_favorite?: boolean;
}

export interface DatabaseReviewItem extends ReviewRow {
  app_id: number;
  app_name?: string | null;
}

export interface DatabaseReviewsResponse {
  items: DatabaseReviewItem[];
  total: number;
  offset: number;
  limit: number;
}

export interface DatabaseGameOption {
  app_id: number;
  name?: string | null;
}

export interface GameComparisonData {
  app_id: number;
  name: string;
  reviews: any[];
  metrics: {
    recommendation_rate: number;
    total_reviews: number;
    category_rates?: Record<string, number>;
  };
}

export interface ComparisonSummarizeRequest {
  games: GameComparisonData[];
  comparison_type: 'overview' | 'category' | 'subcategory';
  category?: string;
  subcategory?: string;
}

export interface ComparisonSummary {
  summary: string;
  winners: Record<string, number[]>;
  key_differences: string[];
  strengths_per_game: Record<number, string[]>;
  weaknesses_per_game: Record<number, string[]>;
  recommendations: Record<number, string>;
  cached: boolean;
}
