export type CollectionOrder = 'recent' | 'updated' | 'helpful';
export type ReviewType = 'all' | 'positive' | 'negative';
export type PurchaseType = 'all' | 'steam' | 'non_steam_purchase';

export interface SamplingContract {
  app_id: number;
  start_time?: number | null;
  end_time?: number | null;
  languages: string[];
  review_type: ReviewType;
  purchase_type: PurchaseType;
  collection_order: CollectionOrder;
  include_offtopic_activity: boolean;
  /** 0 is unlimited; UI should normally offer bounded values on personal PCs. */
  max_reviews: number;
}

export interface CollectReviewsResponse {
  app_id: number;
  source: 'steam' | 'cache' | string;
  fetched_count: number;
  stored_count: number;
  matched_count: number;
  cache_hit: boolean;
  collection_complete: boolean;
  truncated_by_max_reviews: boolean;
  stop_reason?: string | null;
  sampling: SamplingContract;
  stats: Record<string, unknown>;
}

export interface CollectionWindow {
  id: number;
  app_id: number;
  start_time?: number | null;
  end_time?: number | null;
  languages: string[];
  review_type: ReviewType;
  purchase_type: PurchaseType;
  collection_order: CollectionOrder;
  include_offtopic_activity: boolean;
  requested_max_reviews: number;
  fetched_count: number;
  matched_count: number;
  collection_complete: boolean;
  truncated_by_max_reviews: boolean;
  stop_reason?: string | null;
  targeted_date_attempted: boolean;
  targeted_date_applied: boolean;
  collected_at: string;
}
