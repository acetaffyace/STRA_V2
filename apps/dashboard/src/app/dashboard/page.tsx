'use client';

import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import clsx from "clsx";
import {
  Chart as ChartJS,
  BarController,
  CategoryScale,
  LinearScale,
  LineElement,
  LineController,
  PointElement,
  BarElement,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Chart } from "react-chartjs-2";

import {
  searchGames,
  summarizeRecentReviews,
  summarizeSubcategory,
  summarizeWidget,
  SubcategorySummaryResponse,
  WidgetSummaryResponse,
  translateText,
  fetchSteamGameDetails,
  fetchAnalysisResult,
  fetchDashboardPayload,
  fetchRecentAnalysisRuns,
  fetchRecentAnalysisSummary,
  fetchDailyReviewVolume,
  fetchDailyRecommendationRate,
  fetchProvenanceStrip,
  buildDashboardRunUrl,
  DashboardReadiness,
  DashboardPresentation,
  SteamGameDetailsResponse,
} from "@/lib/api";
import { CurrentPlayersWidget, NewsWithSummary } from "@/components/SteamLiveContext";
import type {
  AnalyzeResponse,
  CategoryRecommendationRate,
  CrossSegmentAnalysis,
  PlayerSegments,
  PlatformSegmentInsights,
  LanguageSegmentInsights,
  ProgressStatus,
  QualityWeightedInsights,
  TrendPoint,
  ReviewRow,
  SearchResult,
  SubcategoryInsight,
  ThemeDefinition,
  InsightsResponse,
} from "@/types";
import { AppLayout } from "@/components/AppLayout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SteamImage } from "@/components/SteamImage";
import HealthOverviewCard from "@/components/HealthOverviewCard";
import { PageTransition } from "@/components/PageTransition";
import { Portal } from "@/components/Portal";
import { useAnalysis } from "@/contexts/AnalysisContext";
import { useGameContext } from "@/contexts/GameContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { buildCategoryRates, buildSubcategoryInsights } from "@/lib/derivedInsights";
import { LANGUAGE_OPTIONS } from "@/lib/languageOptions";
import { getRecommendationColor, hexToRgba } from "@/utils/colors";
import { formatSavedLabel } from "@/utils/format";
import { REVIEW_COUNT_OPTIONS } from "@/lib/analysisDefaults";
import { formatTaxonomyLabelZh, MAIN_CATEGORY_LABELS_ZH } from "@/lib/taxonomyLabels";
import { getMetricObservation, metricSecondaryLabel, metricValue } from "@/lib/metricProvenance";
import { CanonicalDashboard } from "@/components/research/CanonicalDashboard";

ChartJS.register(
  BarController,
  CategoryScale,
  LinearScale,
  LineElement,
  LineController,
  PointElement,
  BarElement,
  Tooltip,
  Legend,
  Filler,
);

const EMPTY_REVIEWS: ReviewRow[] = [];

const DEFAULT_THEME: ThemeDefinition = {
  name: "Twilight",
  gradient: ["#6366f1", "#22d3ee", "#0b1120"],
  palette: {
    accent: "#6366f1",
    secondary: "#22d3ee",
    positive: "#22c55e",
    neutral: "#94a3b8",
    negative: "#ef4444",
    surface: "#151635",
    surface_alt: "#0f172a",
    border: "rgba(129,140,248,0.25)",
  },
};

const MAIN_CATEGORY_LABELS = MAIN_CATEGORY_LABELS_ZH;

const CATEGORY_ACCENTS: Record<string, string> = {
  gameplay: "#6366f1",
  technical: "#ef4444",
  content_design: "#22d3ee",
  ui_ux_accessibility: "#8b5cf6",
  onboarding: "#38bdf8",
  presentation: "#f59e0b",
  online_community: "#10b981",
  developer_updates: "#f97316",
  monetization_value: "#ef4444",
  other: "#94a3b8",
};

// Map Steam language codes to our app language codes for translation
const STEAM_TO_APP_LANGUAGE: Record<string, string> = {
  english: 'en',
  italian: 'it',
  french: 'fr',
  german: 'de',
  spanish: 'es',
  portuguese: 'pt',
  brazilian: 'pt',
  russian: 'ru',
  japanese: 'ja',
  koreana: 'ko',
  schinese: 'zh',
  tchinese: 'zh',
  polish: 'pl',
  turkish: 'tr',
  dutch: 'nl',
  swedish: 'sv',
  norwegian: 'no',
  danish: 'da',
  finnish: 'fi',
  czech: 'cs',
  hungarian: 'hu',
  romanian: 'ro',
  ukrainian: 'uk',
  thai: 'th',
  vietnamese: 'vi',
  arabic: 'ar',
  indonesian: 'id',
  greek: 'el',
};

type DashboardSentimentFilter = "all" | "positive" | "negative";
type DashboardDateRangeFilter = "all" | "30d" | "90d" | "365d" | "custom";
type DashboardHelpfulFilter = 0 | 10 | 25 | 50;
type DashboardPlaytimeFilter = "all" | "lt2h" | "2to20h" | "20hplus";

interface DashboardFilters {
  sentiment: DashboardSentimentFilter;
  dateRange: DashboardDateRangeFilter;
  minHelpful: DashboardHelpfulFilter;
  playtime: DashboardPlaytimeFilter;
  language: string;
  customStartDate: string | null;
  customEndDate: string | null;
}

const DEFAULT_DASHBOARD_FILTERS: DashboardFilters = {
  sentiment: "all",
  dateRange: "all",
  minHelpful: 0,
  playtime: "all",
  language: "all",
  customStartDate: null,
  customEndDate: null,
};

function maxDaysFromDateRange(range: DashboardDateRangeFilter): number | null {
  if (range === "30d") return 30;
  if (range === "90d") return 90;
  if (range === "365d") return 365;
  return null;
}

function parseDate(value: unknown): Date | null {
  if (typeof value !== "string" || !value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

function matchesPlaytime(minutes: number, filter: DashboardPlaytimeFilter): boolean {
  if (filter === "all") return true;
  if (filter === "lt2h") return minutes < 120;
  if (filter === "2to20h") return minutes >= 120 && minutes < 1200;
  if (filter === "20hplus") return minutes >= 1200;
  return true;
}

function applyDashboardReviewFilters(reviews: ReviewRow[], filters: DashboardFilters): ReviewRow[] {
  if (!reviews.length) return [];

  const now = new Date();
  const maxDays = maxDaysFromDateRange(filters.dateRange);
  const lang = (filters.language || "all").trim().toLowerCase();

  // Parse custom date range if set
  const customStart = filters.customStartDate ? new Date(filters.customStartDate) : null;
  const customEnd = filters.customEndDate ? new Date(filters.customEndDate) : null;
  // Set customEnd to end of day
  if (customEnd) {
    customEnd.setHours(23, 59, 59, 999);
  }

  return reviews.filter((review) => {
    if (filters.sentiment !== "all") {
      const isPositive = isRecommended(review.voted_up);
      if (filters.sentiment === "positive" && !isPositive) return false;
      if (filters.sentiment === "negative" && isPositive) return false;
    }

    if (filters.minHelpful > 0) {
      const helpful = Number(review.votes_up ?? 0);
      if (!Number.isFinite(helpful) || helpful < filters.minHelpful) return false;
    }

    // Handle custom date range
    if (filters.dateRange === "custom" && (customStart || customEnd)) {
      const created = parseDate((review as { created_at?: unknown }).created_at);
      if (!created) return false;
      if (customStart && created < customStart) return false;
      if (customEnd && created > customEnd) return false;
    } else if (maxDays !== null) {
      const created = parseDate((review as { created_at?: unknown }).created_at);
      if (!created) return false;
      const diffDays = Math.floor((now.getTime() - created.getTime()) / (1000 * 60 * 60 * 24));
      if (diffDays > maxDays) return false;
    }

    if (filters.playtime !== "all") {
      const minutes = Number(review.author_playtime_forever ?? 0);
      if (!Number.isFinite(minutes)) return false;
      if (!matchesPlaytime(minutes, filters.playtime)) return false;
    }

    if (lang && lang !== "all") {
      const reviewLang = String((review as { language?: unknown }).language ?? "")
        .trim()
        .toLowerCase();
      if (!reviewLang) return false;
      if (reviewLang !== lang) return false;
    }

    return true;
  });
}

function dashboardFiltersActive(filters: DashboardFilters): boolean {
  const dateRangeActive =
    filters.dateRange !== "all" &&
    (filters.dateRange !== "custom" || !!filters.customStartDate || !!filters.customEndDate);

  return (
    filters.sentiment !== "all" ||
    dateRangeActive ||
    filters.minHelpful > 0 ||
    filters.playtime !== "all" ||
    (!!filters.language && filters.language !== "all")
  );
}

interface TrendSeriesPoint {
  label: string;
  date: Date | null;
  recommendation_rate: number;
  reviews: number;
}

interface TrendWeekSelection {
  key: string;
  start: Date;
  end: Date;
  label: string;
}

function parseReviewDate(value: unknown): Date | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "number" && Number.isFinite(value)) {
    const ms = value < 1e12 ? value * 1000 : value;
    const date = new Date(ms);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const numeric = Number(trimmed);
    if (Number.isFinite(numeric)) {
      const ms = numeric < 1e12 ? numeric * 1000 : numeric;
      const date = new Date(ms);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    const parsed = new Date(trimmed);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  return null;
}

function isRecommended(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value > 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (
      ["true", "1", "yes", "positive", "recommended", "recommend", "thumbs_up", "thumbsup", "up"].includes(normalized)
    ) {
      return true;
    }
    if (
      ["false", "0", "no", "negative", "not recommended", "not_recommended", "thumbs_down", "thumbsdown", "down"].includes(
        normalized,
      )
    ) {
      return false;
    }
  }
  return false;
}

function extractReviewDate(review: ReviewRow): Date | null {
  const fallback = (review as unknown as { [key: string]: unknown }) || {};
  return (
    parseReviewDate(review.created_at) ||
    parseReviewDate(fallback.timestamp_created) ||
    parseReviewDate(fallback.created_utc) ||
    parseReviewDate(fallback.timestamp) ||
    parseReviewDate(fallback.createdAt)
  );
}

function formatTrendLabel(date: Date): string {
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function startOfWeek(date: Date): Date {
  const copy = new Date(date);
  const day = copy.getDay();
  const diff = (day + 6) % 7; // Monday as start of week
  copy.setDate(copy.getDate() - diff);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function formatWeekRangeLabel(start: Date): string {
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return `${formatTrendLabel(start)} → ${formatTrendLabel(end)}`;
}

function buildTrendSeriesFromReviews(reviews: ReviewRow[]): TrendSeriesPoint[] {
  const buckets = new Map<string, { date: Date; total: number; recommended: number }>();
  let minTime: number | null = null;
  let maxTime: number | null = null;
  reviews.forEach((review) => {
    const created = extractReviewDate(review);
    if (!created) return;
    const weekStart = startOfWeek(created);
    const weekTime = weekStart.getTime();
    if (minTime === null || weekTime < minTime) minTime = weekTime;
    if (maxTime === null || weekTime > maxTime) maxTime = weekTime;
    const key = weekStart.toISOString().slice(0, 10);
    const bucket = buckets.get(key) || { date: weekStart, total: 0, recommended: 0 };
    bucket.total += 1;
    if (isRecommended(review.voted_up)) bucket.recommended += 1;
    buckets.set(key, bucket);
  });

  if (minTime === null || maxTime === null) return [];

  const series: TrendSeriesPoint[] = [];
  const cursor = new Date(minTime);
  while (cursor.getTime() <= maxTime) {
    const key = cursor.toISOString().slice(0, 10);
    const bucket = buckets.get(key);
    const total = bucket?.total ?? 0;
    const recommended = bucket?.recommended ?? 0;
    series.push({
      label: formatTrendLabel(cursor),
      date: new Date(cursor),
      recommendation_rate: total > 0 ? recommended / total : 0,
      reviews: total,
    });
    cursor.setDate(cursor.getDate() + 7);
  }
  return series;
}

function normalizeTrendSeries(trend: TrendPoint[] | undefined): TrendSeriesPoint[] {
  if (!trend || trend.length === 0) return [];
  const parsedPoints = trend
    .map((point, index) => {
      const parsed = parseReviewDate(point.period);
      const labelDate = parsed ? startOfWeek(parsed) : null;
      return {
        label: labelDate ? formatTrendLabel(labelDate) : point.period,
        date: parsed,
        recommendation_rate: Number(point.recommendation_rate ?? 0),
        reviews: Number(point.reviews ?? 0),
        order: parsed ? parsed.getTime() : index,
      };
    })
    .filter((point) => point.date);

  if (parsedPoints.length === 0) return [];

  parsedPoints.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const startTime = startOfWeek(parsedPoints[0].date as Date).getTime();
  const endTime = startOfWeek(parsedPoints[parsedPoints.length - 1].date as Date).getTime();
  const byDate = new Map<string, Omit<TrendSeriesPoint, "label"> & { label?: string }>();
  parsedPoints.forEach((point) => {
    const date = startOfWeek(point.date as Date);
    const key = date.toISOString().slice(0, 10);
    byDate.set(key, {
      date,
      recommendation_rate: point.recommendation_rate,
      reviews: point.reviews,
      label: point.label,
    });
  });

  const series: TrendSeriesPoint[] = [];
  const cursor = new Date(startTime);
  while (cursor.getTime() <= endTime) {
    const key = cursor.toISOString().slice(0, 10);
    const point = byDate.get(key);
    series.push({
      label: point?.label ?? formatTrendLabel(cursor),
      date: new Date(cursor),
      recommendation_rate: point?.recommendation_rate ?? 0,
      reviews: point?.reviews ?? 0,
    });
    cursor.setDate(cursor.getDate() + 7);
  }
  return series;
}

function normalizeDailyProjectionSeries(
  points: import("@/lib/api").DailyRecommendationRatePoint[],
): TrendSeriesPoint[] {
  const normalized: TrendSeriesPoint[] = [];
  points.forEach((point) => {
    const date = parseReviewDate(point.period);
    if (!date) return;
    normalized.push({
      label: formatTrendLabel(date),
      date,
      recommendation_rate: point.recommendation_rate ?? 0,
      reviews: Number(point.review_count ?? 0),
    });
  });
  return normalized;
}

export default function DashboardPage() {
  const { t } = useLanguage();
  return (
    <Suspense fallback={<div className="p-6 text-white">{t('common.loading')}</div>}>
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const { t, language: userLanguage } = useLanguage();
  const searchParams = useSearchParams();
  const router = useRouter();
  const gameParam = searchParams.get("game");
  const runParam = searchParams.get("run");
  const viewParam = searchParams.get("view");
  const { startAnalysis, getTask, tasks } = useAnalysis();
  const { games, loading: gamesLoading, refreshGames, selectGameById, setTemporaryGame, selectedStarredGame, toggleFavorite } = useGameContext();

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedGame, setSelectedGame] = useState<SearchResult | null>(null);

  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [dashboardPresentation, setDashboardPresentation] = useState<DashboardPresentation | null>(null);
  const [dashboardReadiness, setDashboardReadiness] = useState<DashboardReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updateSuccess, setUpdateSuccess] = useState<string | null>(null);
  const [pendingAnalyzeGame, setPendingAnalyzeGame] = useState<SearchResult | null>(null);
  const [setupGame, setSetupGame] = useState<SearchResult | null>(null);
  const [setupMaxReviews, setSetupMaxReviews] = useState<number>(1000);
  const [setupCustomMaxReviews, setSetupCustomMaxReviews] = useState<number>(1000);
  const [setupLanguages, setSetupLanguages] = useState<string[]>(["english"]);
  const [setupTimeScope, setSetupTimeScope] = useState<"all" | "7d" | "30d" | "90d" | "custom">("all");
  const [setupStartTime, setSetupStartTime] = useState<number | null>(null);
  const [setupEndTime, setSetupEndTime] = useState<number | null>(null);
  const [setupReviewType, setSetupReviewType] = useState<"all" | "positive" | "negative">("all");
  const [setupPurchaseType, setSetupPurchaseType] = useState<"all" | "steam" | "non_steam_purchase">("all");
  const [setupOrder, setSetupOrder] = useState<"recent" | "updated" | "helpful">("recent");
  const [setupOfftopic, setSetupOfftopic] = useState(false);
  const fetchFilter = "recent"; // Fixed to recent (latest reviews)
  const [mounted, setMounted] = useState(false);
  const [analysisHistory, setAnalysisHistory] = useState<import("@/lib/api").AnalysisHistoryItem[]>([]);
  const [recentAnalysisSummary, setRecentAnalysisSummary] = useState<import("@/lib/api").RecentAnalysisSummaryItem[]>([]);

  useEffect(() => {
    setMounted(true);
    fetchRecentAnalysisRuns().then(setAnalysisHistory).catch(() => undefined);
    fetchRecentAnalysisSummary().then((data) => setRecentAnalysisSummary(data.items)).catch(() => undefined);
  }, []);

  const currentTask = selectedGame ? getTask(selectedGame.appid) : undefined;
  const recentSummaryByApp = useMemo(
    () => new Map(recentAnalysisSummary.map((item) => [item.app_id, item])),
    [recentAnalysisSummary],
  );
  const isAnalyzing = currentTask?.status === "analyzing" || currentTask?.status === "queued";
  const progress = currentTask?.progress ?? null;

  useEffect(() => {
    if (!gameParam) return;
    const appId = parseInt(gameParam, 10);
    if (Number.isNaN(appId)) return;

    const game = games.find((entry) => entry.app_id === appId);
    if (gamesLoading) return;

    // Check if there's a completed in-memory analysis task as fallback.
    const task = getTask(appId);
    if (!runParam && task?.status === 'completed' && task.result) {
      setSelectedGame({
        appid: appId,
        name: task.game.name,
        price: null,
        url: `https://store.steampowered.com/app/${appId}`,
        image_url: task.game.image_url ?? null,
      });
      setAnalysis({
        ...task.result,
        run_id: task.result.run_id ?? task.progress?.run_id ?? null,
      });
      selectGameById(appId);
    }

    // In-memory task state is only an optimistic first paint. Always hydrate
    // the canonical dashboard payload so readiness, presentation, and exact
    // run identity come from the persisted result.
    let cancelled = false;
    let readiness: DashboardReadiness | null = null;
    const restoreFromSavedAnalysis = async () => {
      try {
        const payload = await fetchDashboardPayload(appId, runParam);
        if (cancelled) return;
        readiness = payload.readiness;
        setDashboardReadiness(payload.readiness);
        setDashboardPresentation(payload.presentation ?? null);
        const result = payload;
        const researchReady = result.readiness.research_ready === true;
        const semanticReady = result.readiness.semantic_ready === true;
        if ((researchReady || semanticReady) && result.metadata) {
          // The dashboard payload is the authoritative run-specific source.
          // For the app-level view, fetch the read-only status envelope too so
          // stale review-pool changes remain visible without recomputation.
          const statusResult = runParam ? null : await fetchAnalysisResult(appId).catch(() => null);
          const fallbackName = game?.name || task?.game?.name || `App ${appId}`;
          const fallbackImage =
            result.metadata.header_image
            || game?.metadata?.header_image
            || task?.game?.image_url
            || null;
          setError(null);
          setSelectedGame({
            appid: appId,
            name: fallbackName,
            price: null,
            url: `https://store.steampowered.com/app/${appId}`,
            image_url: fallbackImage,
          });
          setAnalysis({
            metadata: result.metadata,
            insights: statusResult?.insights ?? result.insights,
            research_report: statusResult?.research_report ?? result.research_report ?? null,
            semantic_status: statusResult?.semantic_status ?? result.semantic_status ?? null,
            reviews: result.reviews ?? [],
            stale: statusResult?.stale ?? false,
            stale_reason: statusResult?.stale_reason ?? null,
            run_id: result.readiness.run_id,
          });
          selectGameById(appId);
          refreshGames().catch(() => null);
          return;
        }
      } catch {
        // Ignore and show the not-found UI message below.
      }
      if (!cancelled) {
        if (readiness && !readiness.research_ready && !readiness.semantic_ready) {
          setError(`分析尚未就绪：${readiness.state}。已加载 ${readiness.review_count.toLocaleString()} 条原始评论；完成 Analyze 后才会显示洞察。`);
        } else {
          setError(runParam ? "该分析运行不存在或当前数据库不包含该运行。" : "已找到游戏，但暂无已完成分析。");
        }
      }
    };

    void restoreFromSavedAnalysis();
    return () => {
      cancelled = true;
    };
  }, [gameParam, runParam, games, gamesLoading, selectGameById, getTask, refreshGames]);

  useEffect(() => {
    if (runParam || !selectedStarredGame) return;
    if (selectedGame?.appid === selectedStarredGame.app_id && analysis?.metadata?.app_id === selectedStarredGame.app_id) {
      return;
    }
    setSelectedGame({
      appid: selectedStarredGame.app_id,
      name: selectedStarredGame.name,
      price: null,
      url: `https://store.steampowered.com/app/${selectedStarredGame.app_id}`,
      image_url: selectedStarredGame.metadata.header_image ?? null,
    });
    setAnalysis({
      metadata: selectedStarredGame.metadata,
      insights: selectedStarredGame.insights,
      reviews: selectedStarredGame.sample ?? [],
      run_id: selectedStarredGame.insights?.metric_provenance?.recommendation_rate?.run_id,
    });
  }, [runParam, selectedStarredGame, selectedGame, analysis]);

  // Legacy starred-game compatibility refresh.  The backend read endpoint is
  // now side-effect free; it may report stale data but never rebuilds it.
  useEffect(() => {
    if (runParam || !selectedStarredGame?.app_id || !selectedStarredGame.insights) return;
    let cancelled = false;
    fetchAnalysisResult(selectedStarredGame.app_id)
      .then((result) => {
        if (cancelled) return;
        if (result.data_refreshed && result.insights) {
          setAnalysis({
            metadata: result.metadata ?? selectedStarredGame.metadata,
            insights: result.insights,
            research_report: result.research_report ?? null,
            semantic_status: result.semantic_status ?? null,
            reviews: result.reviews ?? [],
            run_id: result.run_id,
          });
          setUpdateSuccess("Your dashboard has been updated with more recent reviews");
          setTimeout(() => setUpdateSuccess(null), 6000);
          refreshGames().catch(() => null);
        }
      })
      .catch(() => {
        // Silently ignore — cached data is still valid
      });
    return () => { cancelled = true; };
  }, [runParam, selectedStarredGame?.app_id, selectedStarredGame?.metadata, selectedStarredGame?.insights, refreshGames, setAnalysis]);

  useEffect(() => {
    // An explicit historical run is authoritative.  Do not let a newer
    // in-memory task completion replace the run selected by the URL.
    if (runParam) return;
    if (currentTask?.status === "completed" && currentTask.result) {
      setAnalysis(currentTask.result);
      refreshGames().catch(() => null);
      if (selectedGame) {
        selectGameById(selectedGame.appid);
      }
    }
  }, [currentTask, refreshGames, runParam, selectGameById, selectedGame]);

  async function handleSearch() {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const results = await searchGames(searchQuery);
      setSearchResults(results);
      if (!results.length) {
        setError(t('dashboard.noGamesFound'));
      }
    } catch (err) {
      setError((err as Error).message || "Search failed");
    } finally {
      setSearching(false);
    }
  }

  function openSamplingSetup(game: SearchResult, inherited?: Record<string, unknown> | null) {
    const scope = inherited || dashboardPresentation?.research_snapshot.collection_scope || null;
    const max = typeof scope?.max_reviews === "number" ? Number(scope.max_reviews) : 1000;
    setSetupMaxReviews([100, 500, 1000, 5000, 0].includes(max) ? max : -1);
    setSetupCustomMaxReviews(max > 0 ? max : 1000);
    const languages = Array.isArray(scope?.languages) ? scope.languages.filter((value): value is string => typeof value === "string") : [];
    setSetupLanguages(languages.length ? languages : ["all"]);
    const reviewType = scope?.review_type;
    setSetupReviewType(reviewType === "positive" || reviewType === "negative" ? reviewType : "all");
    const purchaseType = scope?.purchase_type;
    setSetupPurchaseType(purchaseType === "steam" || purchaseType === "non_steam_purchase" ? purchaseType : "all");
    const order = scope?.collection_order;
    setSetupOrder(order === "updated" || order === "helpful" ? order : "recent");
    setSetupOfftopic(scope?.include_offtopic_activity === true);
    const startValue = scope?.start_time;
    const endValue = scope?.end_time;
    const start = typeof startValue === "number" ? startValue : typeof startValue === "string" && Number.isFinite(Number(startValue)) ? Number(startValue) : null;
    const end = typeof endValue === "number" ? endValue : typeof endValue === "string" && Number.isFinite(Number(endValue)) ? Number(endValue) : null;
    setSetupStartTime(start);
    setSetupEndTime(end);
    if (start || end) setSetupTimeScope("custom");
    else setSetupTimeScope("all");
    setSetupGame(game);
  }

  async function handleAnalyze(game: SearchResult, requestedReviewCount: number) {
    setPendingAnalyzeGame(null);
    setError(null);
    setTemporaryGame(game);

    const reviewCount = requestedReviewCount === -1 ? Math.max(1, setupCustomMaxReviews) : requestedReviewCount;
    const timeRange = setupTimeScope === "7d" || setupTimeScope === "30d" || setupTimeScope === "90d"
      ? (() => { const end = new Date(); const start = new Date(end); start.setDate(start.getDate() - Number(setupTimeScope.replace("d", ""))); return { start_time: Math.floor(start.getTime() / 1000), end_time: Math.floor(end.getTime() / 1000) }; })()
      : { start_time: setupTimeScope === "custom" ? setupStartTime : null, end_time: setupTimeScope === "custom" ? setupEndTime : null };

    try {
      await startAnalysis(game, {
        refresh: true,
        review_count: reviewCount,
        language: "all", // Always analyze all languages
        languages: undefined,
        filter: fetchFilter,
        output_language: "zh",
        sampling: {
          app_id: game.appid,
          start_time: timeRange.start_time,
          end_time: timeRange.end_time,
          languages: setupLanguages.length ? setupLanguages : ["all"],
          review_type: setupReviewType,
          purchase_type: setupPurchaseType,
          collection_order: setupOrder,
          include_offtopic_activity: setupOfftopic,
          max_reviews: reviewCount,
        },
      });
    } catch (err) {
      const msg = (err as Error).message || "Failed to start analysis";
      setError(msg);
    }
  }

  const handleReset = useCallback(() => {
    setSelectedGame(null);
    setAnalysis(null);
    setSearchQuery("");
    setSearchResults([]);
    setError(null);
    setTemporaryGame(null);
    selectGameById(null);
    router.replace("/dashboard");
  }, [router, selectGameById, setTemporaryGame]);

  useEffect(() => {
    if (viewParam === "home") {
      handleReset();
      // Re-fetch starred games now that the backend is confirmed ready.
      // The initial provider fetch may have failed during app startup
      // (before the boot page finished its health check).
      refreshGames();
    }
  }, [handleReset, viewParam, refreshGames]);

  const loadingStarred = Boolean(gameParam && gamesLoading && !analysis);
  const recentAnalyses = games;
  const favoriteGames = useMemo(() => games.filter(game => game.is_favorite), [games]);
  const transitionKey = selectedGame ? `game-${selectedGame.appid}` : `home-${viewParam ?? "default"}`;

  const handleToggleFavorite = async (appId: number, currentStatus: boolean) => {
    try {
      await toggleFavorite(appId, !currentStatus);
    } catch (err) {
      setError("Failed to update favorite status");
    }
  };

  if (loadingStarred) {
    return (
      <AppLayout>
        <PageTransition key={`loading-${gameParam ?? "none"}`}>
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-6">
            <Card variant="glass" className="p-5">
              <div className="flex items-center justify-center gap-4">
                <div className="h-8 w-8 animate-spin spinner-blue" />
                <p className="text-lg text-slate-300">{t('common.loading')}</p>
              </div>
            </Card>
          </div>
        </PageTransition>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      {setupGame && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="analysis-setup-title">
          <div className="w-full max-w-2xl rounded-lg border border-white/10 bg-slate-900 p-5 shadow-2xl">
            <div className="flex items-start justify-between gap-4"><div><p className="text-xs uppercase tracking-widest text-slate-500">分析设置</p><h2 id="analysis-setup-title" className="mt-1 text-xl font-semibold text-white">采集评论</h2><p className="mt-1 text-sm text-slate-400">时间范围基于评论发布时间；提交后会进入现有分析队列。</p></div><button className="text-slate-400 hover:text-white" aria-label="Close" onClick={() => setSetupGame(null)}>×</button></div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="text-sm text-slate-300">评论数量<select className="mt-1 w-full rounded border border-white/10 bg-slate-950 p-2" value={setupMaxReviews} onChange={(e) => setSetupMaxReviews(Number(e.target.value))}><option value={100}>100</option><option value={500}>500</option><option value={1000}>1,000</option><option value={5000}>5,000</option><option value={0}>不限</option><option value={-1}>自定义</option></select>{setupMaxReviews === -1 && <input aria-label="自定义评论数量" type="number" min={1} value={setupCustomMaxReviews} onChange={(e) => setSetupCustomMaxReviews(Number(e.target.value))} className="mt-2 w-full rounded border border-white/10 bg-slate-950 p-2" />}</label>
              <fieldset className="text-sm text-slate-300"><legend>语言（可多选）</legend><div className="mt-1 grid grid-cols-2 gap-2 rounded border border-white/10 bg-slate-950 p-2">{[{ value: "all", label: "全部语言" }, { value: "english", label: "English" }, { value: "schinese", label: "简体中文" }, { value: "tchinese", label: "繁體中文" }, { value: "japanese", label: "日本語" }, { value: "koreana", label: "한국어" }].map((option) => <label key={option.value} className="flex items-center gap-2"><input type="checkbox" checked={setupLanguages.includes(option.value)} onChange={(e) => { if (option.value === "all") setSetupLanguages(e.target.checked ? ["all"] : []); else setSetupLanguages(e.target.checked ? [...setupLanguages.filter((value) => value !== "all"), option.value] : setupLanguages.filter((value) => value !== option.value)); }} />{option.label}</label>)}</div></fieldset>
              <label className="text-sm text-slate-300">时间范围<select className="mt-1 w-full rounded border border-white/10 bg-slate-950 p-2" value={setupTimeScope} onChange={(e) => setSetupTimeScope(e.target.value as typeof setupTimeScope)}><option value="all">全部时间</option><option value="7d">最近 7 天</option><option value="30d">最近 30 天</option><option value="90d">最近 90 天</option><option value="custom">自定义</option></select></label>
              <label className="text-sm text-slate-300">推荐状态<select className="mt-1 w-full rounded border border-white/10 bg-slate-950 p-2" value={setupReviewType} onChange={(e) => setSetupReviewType(e.target.value as typeof setupReviewType)}><option value="all">全部评论</option><option value="positive">推荐</option><option value="negative">不推荐</option></select></label>
              <label className="text-sm text-slate-300">购买来源<select className="mt-1 w-full rounded border border-white/10 bg-slate-950 p-2" value={setupPurchaseType} onChange={(e) => setSetupPurchaseType(e.target.value as typeof setupPurchaseType)}><option value="all">全部</option><option value="steam">Steam 购买</option><option value="non_steam_purchase">非 Steam 购买</option></select></label>
              <label className="text-sm text-slate-300">排序方式<select className="mt-1 w-full rounded border border-white/10 bg-slate-950 p-2" value={setupOrder} onChange={(e) => setSetupOrder(e.target.value as typeof setupOrder)}><option value="recent">最新发布</option><option value="updated">最近更新</option><option value="helpful">最有帮助</option></select></label>
              <label className="flex items-center gap-2 self-end text-sm text-slate-300"><input type="checkbox" checked={setupOfftopic} onChange={(e) => setSetupOfftopic(e.target.checked)} /> 包含与当前游戏无关的评论活动</label>
            </div>
            {setupTimeScope === "custom" && <div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-sm text-slate-300">开始日期<input type="date" value={setupStartTime == null ? "" : new Date(setupStartTime * 1000).toISOString().slice(0, 10)} onChange={(e) => setSetupStartTime(e.target.value ? Math.floor(new Date(`${e.target.value}T00:00:00Z`).getTime() / 1000) : null)} className="mt-1 w-full rounded border border-white/10 bg-slate-950 p-2" /></label><label className="text-sm text-slate-300">结束日期<input type="date" value={setupEndTime == null ? "" : new Date(setupEndTime * 1000).toISOString().slice(0, 10)} onChange={(e) => setSetupEndTime(e.target.value ? Math.floor(new Date(`${e.target.value}T23:59:59Z`).getTime() / 1000) : null)} className="mt-1 w-full rounded border border-white/10 bg-slate-950 p-2" /></label></div>}
            <div className="mt-5 rounded border border-white/10 bg-white/[0.03] p-3 text-sm text-slate-300"><p className="font-medium text-white">预计采集范围</p><p className="mt-1">{setupTimeScope === "all" ? "全部时间" : setupTimeScope === "custom" ? `${setupStartTime == null ? "未设置" : new Date(setupStartTime * 1000).toISOString().slice(0, 10)} → ${setupEndTime == null ? "未设置" : new Date(setupEndTime * 1000).toISOString().slice(0, 10)}` : `最近 ${setupTimeScope.replace("d", "")} 天`} · {setupLanguages.includes("all") || !setupLanguages.length ? "全部语言" : setupLanguages.join(" + ")} · {setupReviewType === "all" ? "全部评论" : setupReviewType === "positive" ? "推荐" : "不推荐"} · 最多 {setupMaxReviews === 0 ? "不限" : setupMaxReviews === -1 ? setupCustomMaxReviews : setupMaxReviews} 条{setupOfftopic ? " · 包含非主题活动" : ""}</p></div>
            <div className="mt-5 flex justify-end gap-2"><Button variant="secondary" onClick={() => setSetupGame(null)}>取消</Button><Button variant="primary" onClick={() => { const game = setupGame; setSetupGame(null); setPendingAnalyzeGame(null); void handleAnalyze(game, setupMaxReviews); }}>开始分析</Button></div>
          </div>
        </div>
      )}
      <PageTransition key={transitionKey}>
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-6 space-y-8 sm:space-y-6">
          {selectedGame ? (
            <div className="flex items-center justify-between">
              <button
                onClick={handleReset}
                className="group inline-flex items-center gap-2 text-sm text-slate-400 hover:text-sky-400 transition-colors"
              >
                <svg
                  className="w-4 h-4 transition-transform duration-200 ease-out group-hover:-translate-x-1"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M10 19l-7-7m0 0l7-7m-7 7h18"
                  />
                </svg>
                {userLanguage === 'zh' ? '返回总览' : 'Back to Home'}
              </button>
            </div>
          ) : null}

          {!selectedGame && (
            <>
              <div className={`px-1 py-2 ${mounted ? 'animate-fade-slide-up' : 'opacity-0'}`}>
                <div className="space-y-2">
                  <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">{t('dashboard.welcome')}</p>
                  <div>
                  <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                    <span className="text-white">
                      {t('dashboard.welcomeTo')}
                    </span>
                  </h1>
                  <p className="mt-2 text-sm text-slate-400">
                    {t('dashboard.subtitle')}
                  </p>
                  </div>
                </div>
              </div>

            <div id="new-analysis">
              <section className={`workspace-section p-5 ${mounted ? 'animate-fade-slide-up animation-delay-100' : 'opacity-0'}`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-white">{t('dashboard.newAnalysis')}</h2>
                    <p className="text-xs text-slate-400">{t('dashboard.newAnalysisDesc')}</p>
                  </div>
                </div>

                <div className="mt-4 space-y-4">
                  <div className="flex flex-col gap-4 sm:flex-row">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(event) => setSearchQuery(event.target.value)}
                      onKeyDown={(event) => event.key === "Enter" && handleSearch()}
                      placeholder={t('dashboard.searchPlaceholder')}
                      className="flex-1 rounded-xl border border-white/20 bg-slate-900/50 px-4 py-3 text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
                    />
                    <Button
                      onClick={handleSearch}
                      disabled={searching || !searchQuery.trim()}
                      variant="primary"
                      size="lg"
                      className="w-full sm:w-auto"
                    >
                      {searching ? t('dashboard.searching') : t('common.search')}
                    </Button>
                  </div>

                  {error && searchResults.length === 0 && (
                    <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3">
                      <p className="text-sm text-rose-400">{error}</p>
                    </div>
                  )}

                  {searchResults.length > 0 && (
                    <div className="mt-6 space-y-3">
                      <p className="text-sm text-slate-400">{searchResults.length} {userLanguage === 'zh' ? '个游戏' : 'games found'}</p>
                      <div className="grid gap-4 md:grid-cols-2">
                        {searchResults.map((game) => {
                          const gameTask = getTask(game.appid);
                          const isAnalyzingGame = gameTask?.status === "analyzing" || gameTask?.status === "queued";
                          const isAlreadyAnalyzed = games.some((entry) => entry.app_id === game.appid);
                          return (
                            <div
                              key={game.appid}
                              className="flex gap-4 rounded-xl border border-white/10 bg-slate-900/30 p-4 transition hover:border-sky-500/50"
                            >
                              <SteamImage
                                appId={game.appid}
                                variant="capsule"
                                alt={game.name}
                                className="h-16 w-28 rounded-lg object-cover flex-shrink-0"
                                imageUrl={game.image_url}
                              />
                              <div className="flex-1 min-w-0">
                                <h3 className="font-semibold text-white truncate">{game.name}</h3>
                                {game.price && <p className="mt-1 text-sm text-slate-400">{game.price}</p>}
                                {pendingAnalyzeGame?.appid === game.appid && !isAnalyzingGame ? (
                                  <div className="mt-3 flex items-center gap-2">
                                    <span className="text-xs text-slate-400">{userLanguage === 'zh' ? '评论数：' : 'Reviews:'}</span>
                                    {REVIEW_COUNT_OPTIONS.map((count) => (
                                    <Button
                                      key={count}
                                      onClick={() => { setSetupMaxReviews(count); setSetupGame(game); }}
                                        variant={isAlreadyAnalyzed ? "update" : "primary"}
                                        size="sm"
                                      >
                                        {count.toLocaleString()}
                                      </Button>
                                    ))}
                                  </div>
                                ) : (
                                  <Button
                                    onClick={() => { setPendingAnalyzeGame(game); setSetupGame(game); }}
                                    disabled={isAnalyzingGame}
                                    variant={isAlreadyAnalyzed ? "update" : "primary"}
                                    size="sm"
                                    className="mt-3"
                                  >
                                    {isAnalyzingGame
                                      ? t('dashboard.analyzing')
                                      : isAlreadyAnalyzed
                                        ? t('dashboard.update')
                                        : t('dashboard.analyze')}
                                  </Button>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </section>
            </div>

            {/* Favorites Section */}
            {favoriteGames.length > 0 && (
              <Card variant="glass" className={`p-4 sm:p-5 ${mounted ? 'animate-fade-slide-up animation-delay-200' : 'opacity-0'}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-base sm:text-lg font-semibold text-white flex items-center gap-2">
                      <span className="text-amber-400">★</span>
                      {userLanguage === 'zh' ? '收藏的游戏' : 'Favorite Games'}
                    </h2>
                  </div>
                  <span className="text-xs text-slate-500">{favoriteGames.length} game{favoriteGames.length !== 1 ? 's' : ''}</span>
                </div>

                <div className="mt-3 sm:mt-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2 sm:gap-3">
                  {favoriteGames.map((game) => {
                    const sample = game.sample ?? [];
                    const exactRun = analysisHistory.find((entry) => entry.app_id === game.app_id && entry.run_type === "general_analysis" && entry.status === "completed" && entry.result_available);
                    const projection = recentSummaryByApp.get(game.app_id);
                    const observation = getMetricObservation(game.insights, "recommendation_rate");
                    const rate = metricValue(game.insights, "recommendation_rate", game.insights?.recommendation);
                    return (
                      <div
                        key={game.app_id}
                        className="group relative rounded-lg sm:rounded-xl border border-amber-500/30 bg-amber-500/5 overflow-hidden transition active:scale-[0.98] hover:border-amber-500/50 hover:bg-amber-500/10"
                      >
                        <button
                          onClick={() => router.push(projection?.reopen_url ?? (exactRun ? buildDashboardRunUrl(game.app_id, exactRun.run_id) : `/dashboard?game=${game.app_id}`))}
                          className="w-full text-left"
                        >
                          <div className="aspect-[460/215] relative">
                            <SteamImage
                              appId={game.app_id}
                              variant="header"
                              alt={game.name}
                              className="h-full w-full object-cover"
                              imageUrl={game.metadata.header_image}
                            />
                          </div>
                          <div className="p-2 sm:p-2.5">
                            <p className="text-[11px] sm:text-xs font-semibold text-white line-clamp-1">{game.name}</p>
                            <div className="flex items-center justify-between mt-0.5 sm:mt-1">
                              <p className="text-[10px] sm:text-xs text-slate-500">{projection?.analysis_population_count != null ? `${projection.analysis_population_count.toLocaleString()} ${userLanguage === 'zh' ? '条评论' : 'reviews'}` : metricSecondaryLabel(observation) ?? `${sample.length.toLocaleString()} ${userLanguage === 'zh' ? '条评论' : 'reviews'}`}</p>
                              <p className="text-[11px] sm:text-xs font-semibold" style={{ color: getRecommendationColor(rate ?? 0) }}>
                                {formatPercentOrDash(projection?.recommendation_rate ?? rate)}
                              </p>
                            </div>
                          </div>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleFavorite(game.app_id, true);
                          }}
                          className="absolute top-1 right-1 p-1.5 sm:px-2 sm:py-1.5 rounded bg-black/50 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity hover:bg-black/70"
                          title="Remove from favorites"
                        >
                          <span className="text-amber-400 text-sm">★</span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}

            <section className={`workspace-section p-4 sm:p-5 ${mounted ? 'animate-fade-slide-up animation-delay-300' : 'opacity-0'}`}>
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base sm:text-lg font-semibold text-white">{t('dashboard.recentAnalyses')}</h2>
                  <p className="text-[11px] sm:text-xs text-slate-400">{t('dashboard.recentDesc')}</p>
                </div>
                {null}
              </div>

              <div className="mt-3 sm:mt-4">
                {gamesLoading ? (
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2 sm:gap-3">
                    {[...Array(4)].map((_, idx) => (
                      <div key={idx} className="h-28 sm:h-32 animate-pulse rounded-lg sm:rounded-xl border border-white/10 bg-slate-900/40" />
                    ))}
                  </div>
                ) : recentAnalyses.length === 0 ? (
                  <EmptyState
                    title={t('dashboard.noAnalyses')}
                    description={t('dashboard.noAnalysesDesc')}
                    variant="info"
                  />
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2 sm:gap-3">
                    {recentAnalyses.map((game) => {
                      const sample = game.sample ?? [];
                      const exactRun = analysisHistory.find((entry) => entry.app_id === game.app_id && entry.run_type === "general_analysis" && entry.status === "completed" && entry.result_available);
                      const projection = recentSummaryByApp.get(game.app_id);
                      const observation = getMetricObservation(game.insights, "recommendation_rate");
                      const rate = metricValue(game.insights, "recommendation_rate", game.insights?.recommendation);
                      const isFavorite = game.is_favorite ?? false;
                      return (
                        <div
                          key={game.app_id}
                          className="group relative rounded-lg sm:rounded-xl border border-white/10 bg-slate-900/30 overflow-hidden transition active:scale-[0.98] hover:border-sky-500/40 hover:bg-slate-900/50"
                        >
                          <button
                            onClick={() => router.push(projection?.reopen_url ?? (exactRun ? buildDashboardRunUrl(game.app_id, exactRun.run_id) : `/dashboard?game=${game.app_id}`))}
                            className="w-full text-left"
                          >
                            <div className="aspect-[460/215] relative">
                              <SteamImage
                                appId={game.app_id}
                                variant="header"
                                alt={game.name}
                                className="h-full w-full object-cover"
                                imageUrl={game.metadata.header_image}
                              />
                            </div>
                            <div className="p-2 sm:p-2.5">
                              <p className="text-[11px] sm:text-xs font-semibold text-white line-clamp-1">{game.name}</p>
                              <div className="flex items-center justify-between mt-0.5 sm:mt-1">
                                <p className="text-[10px] sm:text-xs text-slate-500">{projection?.analysis_population_count != null ? `${projection.analysis_population_count.toLocaleString()} reviews` : metricSecondaryLabel(observation) ?? `${sample.length.toLocaleString()} reviews`}</p>
                                <p className="text-[11px] sm:text-xs font-semibold" style={{ color: getRecommendationColor(rate ?? 0) }}>
                                  {formatPercentOrDash(projection?.recommendation_rate ?? rate)}
                                </p>
                              </div>
                            </div>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleToggleFavorite(game.app_id, isFavorite);
                            }}
                            className="absolute top-1 right-1 p-1.5 sm:px-2 sm:py-1.5 rounded bg-black/50 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity hover:bg-black/70"
                            title={isFavorite ? "Remove from favorites" : "Add to favorites"}
                          >
                            <span className={`text-sm ${isFavorite ? 'text-amber-400' : 'text-white/70 hover:text-amber-400'}`}>
                              {isFavorite ? '★' : '☆'}
                            </span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </section>
          </>
        )}

        {/* Keep the legacy status panel only when neither analytical layer is available. */}
        {dashboardReadiness && !dashboardReadiness.research_ready && !dashboardReadiness.semantic_ready && !isAnalyzing && (
          <div className="mx-auto max-w-5xl px-4 py-6">
            <Card className="border-amber-500/30 bg-amber-500/5 p-5">
              <p className="text-sm font-medium text-amber-200">分析状态：{dashboardReadiness.state}</p>
              <p className="mt-2 text-sm text-slate-400">
                原始评论 {dashboardReadiness.review_count.toLocaleString()} 条；已验证语义分类 {dashboardReadiness.classified_count.toLocaleString()} 条（{(dashboardReadiness.classification_coverage * 100).toFixed(1)}%）。
                在语义分析完成前，不显示健康度、问题、请求或用户分群的 0 值占位。
              </p>
            </Card>
          </div>
        )}

        {analysis && !analysis.insights && !analysis.research_report && !isAnalyzing && dashboardReadiness?.state === "ANALYSIS_READY" && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center space-y-4">
              <div className="animate-spin h-8 w-8 spinner-blue mx-auto" />
            <p className="text-slate-400">{userLanguage === 'zh' ? '正在加载分析结果…' : 'Loading analysis results...'}</p>
            </div>
          </div>
        )}

        {dashboardPresentation && selectedGame && !isAnalyzing && (
          <CanonicalDashboard presentation={dashboardPresentation} appName={selectedGame.name} appId={selectedGame.appid} showHeader={false} onConfigureSampling={() => openSamplingSetup(selectedGame)} />
        )}

        {analysis && analysis.insights && (!dashboardReadiness || dashboardReadiness.semantic_ready || (!dashboardReadiness.research_ready && dashboardReadiness.state === "ANALYSIS_READY")) && (
          <>
            {!analysis.research_report && (!dashboardReadiness || dashboardReadiness.semantic_ready) && (
              <div className="mx-auto max-w-6xl px-4 pb-4">
                <Card className="border-slate-400/20 bg-slate-500/5 p-4 text-sm text-slate-300">
                  {userLanguage === 'zh'
                    ? '此分析早于当前 Research Core 方法。该历史运行没有可用的 Deterministic Research Report。'
                    : 'This analysis predates the current Research Core methodology. A deterministic Research Report is unavailable for this historical run.'}
                </Card>
              </div>
            )}
            <AnalysisResults
              analysis={analysis}
              selectedGame={selectedGame}
              updateSuccess={updateSuccess}
              error={error}
              onUpdate={async () => {
              if (!selectedGame) return;

              setError(null);
              setUpdateSuccess(null);
              openSamplingSetup(selectedGame, dashboardPresentation?.research_snapshot.collection_scope || null);
              }}
            />
          </>
        )}
      </div>
      </PageTransition>

    </AppLayout>
  );
}

function DashboardFiltersBar({
  filters,
  onChange,
}: {
  filters: DashboardFilters;
  onChange: (patch: Partial<DashboardFilters>) => void;
}) {
  const { t } = useLanguage();

  const selectClass = "rounded border border-white/10 bg-slate-900/70 px-2 py-2 sm:py-1 text-xs text-slate-200 focus:border-sky-400 focus:outline-none w-full sm:w-auto";
  const dateInputClass = "rounded border border-white/10 bg-slate-900/70 px-2 py-2 sm:py-1 text-xs text-slate-200 focus:border-sky-400 focus:outline-none flex-1 sm:flex-none";

  return (
    <div className="rounded-lg border border-white/10 bg-slate-900/40 px-3 py-3 sm:py-2">
      <span className="text-xs uppercase tracking-wider text-slate-500 block sm:hidden mb-2">{t("common.filters")}</span>
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center sm:gap-2">
        <span className="text-xs uppercase tracking-wider text-slate-500 hidden sm:inline">{t("common.filters")}:</span>

        <select
          value={filters.sentiment}
          onChange={(event) => onChange({ sentiment: event.target.value as DashboardSentimentFilter })}
          className={selectClass}
        >
          <option value="all">{t("filters.allSentiment")}</option>
          <option value="positive">{t("common.recommended")}</option>
          <option value="negative">{t("common.notRecommended")}</option>
        </select>

        <select
          value={filters.dateRange}
          onChange={(event) => {
            const value = event.target.value as DashboardDateRangeFilter;
            if (value !== "custom") {
              onChange({ dateRange: value, customStartDate: null, customEndDate: null });
            } else {
              onChange({ dateRange: value });
            }
          }}
          className={selectClass}
        >
          <option value="all">{t("filters.allTime")}</option>
          <option value="30d">{t("filters.last30Days")}</option>
          <option value="90d">{t("filters.last90Days")}</option>
          <option value="365d">{t("filters.last12Months")}</option>
          <option value="custom">{t("filters.customRange")}</option>
        </select>

        <select
          value={filters.minHelpful}
          onChange={(event) => onChange({ minHelpful: Number(event.target.value) as DashboardHelpfulFilter })}
          className={selectClass}
        >
          <option value={0}>{t("filters.allHelpful")}</option>
          <option value={10}>{t("filters.helpfulVotes10")}</option>
          <option value={25}>{t("filters.helpfulVotes25")}</option>
          <option value={50}>{t("filters.helpfulVotes50")}</option>
        </select>

        <select
          value={filters.playtime}
          onChange={(event) => onChange({ playtime: event.target.value as DashboardPlaytimeFilter })}
          className={selectClass}
        >
          <option value="all">{t("filters.allPlaytime")}</option>
          <option value="lt2h">{t("filters.playtimeLt2h")}</option>
          <option value="2to20h">{t("filters.playtime2to20h")}</option>
          <option value="20hplus">{t("filters.playtime20hplus")}</option>
        </select>

        <select
          value={filters.language || "all"}
          onChange={(event) => onChange({ language: event.target.value })}
          className={`${selectClass} col-span-2 sm:col-span-1`}
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {filters.dateRange === "custom" && (
        <div className="flex flex-wrap items-center gap-2 mt-2 pt-2 border-t border-white/5">
          <span className="text-xs text-slate-500 w-full sm:w-auto">Date range:</span>
          <input
            type="date"
            value={filters.customStartDate || ""}
            onChange={(event) => onChange({ customStartDate: event.target.value || null })}
            className={dateInputClass}
          />
          <span className="text-xs text-slate-500">to</span>
          <input
            type="date"
            value={filters.customEndDate || ""}
            onChange={(event) => onChange({ customEndDate: event.target.value || null })}
            className={dateInputClass}
          />
        </div>
      )}
    </div>
  );
}

function FiveQuestionSummary({ insights }: { insights: InsightsResponse }) {
  const contract = insights.five_questions;
  if (!contract) return null;
  const topSignal = contract.what_matters?.signals?.[0];
  const firstAction = contract.recommended_actions?.[0];
  const snapshot = contract.current_snapshot;
  const cohorts = snapshot?.observed_cohort_concentration ?? [];
  const signalTitle = (signal?: Record<string, unknown> | null) => formatTaxonomyLabelZh(String(signal?.display_title ?? signal?.topic ?? "暂无"));
  const signalCount = (signal?: Record<string, unknown> | null) => signal?.count == null ? "" : `（${String(signal.count)} 条评论）`;
  return (
    <Card variant="glass" className="p-4 sm:p-6 border-cyan-400/20">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-wider text-cyan-300">决策摘要</p>
          <h3 className="mt-1 text-lg font-semibold text-white">基于当前 Run 的玩家反馈分析</h3>
        </div>
        <span className="text-xs text-slate-500">
          {contract.mode === "codex_offline_fixture" ? "离线开发 Fixture" : "基于当前 Run"}
        </span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-5">
        <SummaryTile title="1. 变化" value={contract.what_changed?.status === "unavailable" ? "暂无可比基线" : "已提供窗口差异"} />
        <SummaryTile title="2. 主要原因" value={signalTitle(snapshot?.leading_problem_signal) !== "暂无" ? `${signalTitle(snapshot?.leading_problem_signal)}${signalCount(snapshot?.leading_problem_signal)}` : "当前没有稳定问题信号"} />
        <SummaryTile title="3. 影响群体" value={cohorts.length > 0 ? cohorts.slice(0, 2).map((cohort) => String(cohort.label ?? cohort.name ?? "已观察群体")).join("、") : "暂未发现稳定集中群体"} />
        <SummaryTile title="4. 重点信号" value={`${signalTitle(topSignal)}${signalCount(topSignal)}`} />
        <SummaryTile title="5. 建议行动" value={firstAction ? `${firstAction.action_class}: ${formatTaxonomyLabelZh(firstAction.title)}` : "暂无行动建议"} />
      </div>
      {snapshot && <div className="mt-4 rounded-lg border border-white/10 bg-slate-950/30 p-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-cyan-300">当前快照</p>
        <div className="mt-2 grid gap-2 text-xs text-slate-300 sm:grid-cols-3">
          <span>正向信号：{signalTitle(snapshot.strongest_positive_signal)}{signalCount(snapshot.strongest_positive_signal)}</span>
          <span>问题信号：{signalTitle(snapshot.leading_problem_signal)}{signalCount(snapshot.leading_problem_signal)}</span>
          <span>需求信号：{signalTitle(snapshot.leading_request_signal)}{signalCount(snapshot.leading_request_signal)}</span>
        </div>
      </div>}
      {firstAction && <div className="mt-4 rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-white">{firstAction.action_class} — {formatTaxonomyLabelZh(firstAction.title)}</p>
          <span className="text-xs text-cyan-200">建议行动</span>
        </div>
        <p className="mt-2 text-xs text-slate-300">为什么优先：{firstAction.rationale ?? '透明启发式排序，需结合证据复核。'}</p>
        <p className="mt-1 text-xs text-slate-400">不确定性：{firstAction.uncertainty ?? 'Steam 评论是自选择观察样本。'}</p>
        <p className="mt-1 text-xs text-slate-400">验证计划：{firstAction.validation_plan ?? '暂无验证计划。'}</p>
      </div>}
      {contract.what_changed?.status === "unavailable" && <p className="mt-3 text-xs text-slate-500">当前仅展示单窗口观察，不判断近期变化。</p>}
      <p className="mt-3 text-xs text-slate-500">群体仅基于 Steam 评论可观测元数据，不代表完整玩家画像。</p>
      {contract.what_changed?.confidence_note && <p className="mt-1 text-xs text-amber-300/80">{contract.what_changed.confidence_note}</p>}
      {contract.what_matters?.is_heuristic && <p className="mt-1 text-xs text-slate-500">重点排序为启发式辅助，不是因果结论或正式优先级事实；点击问题或需求卡查看证据。</p>}
    </Card>
  );
}

function SummaryTile({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/5 p-3">
      <p className="text-xs text-slate-400">{title}</p>
      <p className="mt-2 text-sm text-slate-200 line-clamp-2">{value}</p>
    </div>
  );
}

function AnalysisResults({
  analysis,
  selectedGame,
  onUpdate,
  updateSuccess,
  error,
}: {
  analysis: AnalyzeResponse;
  selectedGame: SearchResult | null;
  onUpdate?: () => void;
  updateSuccess?: string | null;
  error?: string | null;
}) {
  const { t, language: userLanguage } = useLanguage();
  const router = useRouter();
  const insights = analysis.insights ?? null;
  const theme = (insights?.theme as ThemeDefinition | undefined) ?? DEFAULT_THEME;
  const [selectedSubcategory, setSelectedSubcategory] = useState<string | null>(null);

  // Game details state - fetched live (includes price, release date, developers, etc.)
  const [gameDetails, setGameDetails] = useState<SteamGameDetailsResponse | null>(null);
  const [gameDetailsLoading, setGameDetailsLoading] = useState(false);
  const [gameDetailsUnavailable, setGameDetailsUnavailable] = useState(false);
  const [dailyProjection, setDailyProjection] = useState<{
    volume: import("@/lib/api").DailyReviewVolumeResponse;
    recommendation: import("@/lib/api").DailyRecommendationRateResponse;
  } | null>(null);
  const [dailyProjectionUnavailable, setDailyProjectionUnavailable] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<import("@/lib/api").ProvenanceStrip | null>(null);

  useEffect(() => {
    const runId = analysis.run_id ?? analysis.metadata?.run_id;
    if (!runId) {
      setDailyProjection(null);
      setDailyProjectionUnavailable("当前结果没有可重放的 Run ID。");
      return;
    }
    let cancelled = false;
    Promise.all([fetchDailyReviewVolume(runId), fetchDailyRecommendationRate(runId)])
      .then(([volume, recommendation]) => {
        if (cancelled) return;
        if (!volume.available || !recommendation.available) {
          setDailyProjection(null);
          setDailyProjectionUnavailable(volume.unavailable_reason ?? recommendation.unavailable_reason ?? "该 Run 的完整时间序列不可用。");
          return;
        }
        setDailyProjection({ volume, recommendation });
        setDailyProjectionUnavailable(null);
      })
      .catch(() => {
        if (!cancelled) {
          setDailyProjection(null);
          setDailyProjectionUnavailable("每日 projection 暂时不可用。");
        }
      });
    return () => { cancelled = true; };
  }, [analysis.run_id, analysis.metadata?.run_id]);

  useEffect(() => {
    const runId = analysis.run_id ?? analysis.metadata?.run_id;
    if (!runId) { setProvenance(null); return; }
    fetchProvenanceStrip(runId).then((value) => setProvenance(value.available ? value : null)).catch(() => setProvenance(null));
  }, [analysis.run_id, analysis.metadata?.run_id]);

  // Fetch game details when game changes
  useEffect(() => {
    if (!selectedGame?.appid) {
      setGameDetails(null);
      setGameDetailsUnavailable(false);
      return;
    }
    let cancelled = false;
    setGameDetailsLoading(true);
    setGameDetailsUnavailable(false);
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timeoutId = setTimeout(() => reject(new Error('steam_details_timeout')), 5000);
    });
    Promise.race([fetchSteamGameDetails(selectedGame.appid), timeout])
      .then((data) => {
        if (!cancelled) setGameDetails(data);
      })
      .catch(() => {
        if (!cancelled) {
          setGameDetails(null);
          setGameDetailsUnavailable(true);
        }
      })
      .finally(() => {
        if (timeoutId) clearTimeout(timeoutId);
        if (!cancelled) setGameDetailsLoading(false);
      });
    return () => { cancelled = true; };
  }, [selectedGame?.appid]);
  const [selectedSubcategoryType, setSelectedSubcategoryType] = useState<'issue' | 'request' | 'general'>('general');
  const [selectedSubcategoryLanguage, setSelectedSubcategoryLanguage] = useState<{ key: string; label: string } | null>(null);
  const [selectedTrendWeek, setSelectedTrendWeek] = useState<TrendWeekSelection | null>(null);
  const [selectedSegment, setSelectedSegment] = useState<{
    type: 'experience' | 'purchase' | 'activity' | 'engagement' | 'language';
    key: string;
    label: string;
    description: string;
  } | null>(null);
  const [expandedReviews, setExpandedReviews] = useState<Set<string>>(() => new Set());
  const [filters, setFilters] = useState<DashboardFilters>(() => ({ ...DEFAULT_DASHBOARD_FILTERS }));
  const [reviewQuery, setReviewQuery] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [subcategorySummary, setSubcategorySummary] = useState<SubcategorySummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [trendWeekSummary, setTrendWeekSummary] = useState<WidgetSummaryResponse | null>(null);
  const [trendWeekSummaryLoading, setTrendWeekSummaryLoading] = useState(false);
  const [trendWeekSummaryError, setTrendWeekSummaryError] = useState<string | null>(null);
  const [segmentSummary, setSegmentSummary] = useState<WidgetSummaryResponse | null>(null);
  const [segmentSummaryLoading, setSegmentSummaryLoading] = useState(false);
  const [segmentSummaryError, setSegmentSummaryError] = useState<string | null>(null);
  const [topIssuesModalOpen, setTopIssuesModalOpen] = useState(false);
  const [topIssuesSummary, setTopIssuesSummary] = useState<WidgetSummaryResponse | null>(null);
  const [topIssuesSummaryLoading, setTopIssuesSummaryLoading] = useState(false);
  const [topIssuesSummaryError, setTopIssuesSummaryError] = useState<string | null>(null);
  const [topRequestsModalOpen, setTopRequestsModalOpen] = useState(false);
  const [topRequestsSummary, setTopRequestsSummary] = useState<WidgetSummaryResponse | null>(null);
  const [topRequestsSummaryLoading, setTopRequestsSummaryLoading] = useState(false);
  const [topRequestsSummaryError, setTopRequestsSummaryError] = useState<string | null>(null);
  const [healthOverviewRefreshing, setHealthOverviewRefreshing] = useState(false);
  const [healthOverviewOverride, setHealthOverviewOverride] = useState<{
    summary: string;
    key_points: string[];
    actions: string[];
    health_score: number;
    sentiment_trend: "improving" | "stable" | "declining";
    top_strengths: string[];
    review_count?: number;
    start_date?: string | null;
    end_date?: string | null;
  } | null>(null);
  const [lastMonthOnly, setLastMonthOnly] = useState(false);
  const [negativeOnly, setNegativeOnly] = useState(false);
  const [highPlaytime, setHighPlaytime] = useState(false);
  const [highHelpful, setHighHelpful] = useState(false);
  const [mounted, setMounted] = useState(false);
  const healthOverviewRequestIdRef = useRef(0);

  // Collapsible widget state (persisted in localStorage)
  type WidgetKey = 'healthOverview' | 'topIssuesRequests' | 'categoriesOverview' | 'sentimentTrend' | 'segmentation' | 'recentUpdates';
  const COLLAPSED_STORAGE_KEY = 'sentinext_collapsed_widgets';
  const [collapsedWidgets, setCollapsedWidgets] = useState<Set<WidgetKey>>(new Set());

  useEffect(() => {
    try {
      const stored = localStorage.getItem(COLLAPSED_STORAGE_KEY);
      if (stored) setCollapsedWidgets(new Set(JSON.parse(stored)));
    } catch { /* ignore */ }
  }, []);

  const toggleWidget = useCallback((key: WidgetKey) => {
    setCollapsedWidgets(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      try { localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify([...next])); } catch { /* ignore */ }
      return next;
    });
  }, []);

  // Trigger animations on mount
  useEffect(() => {
    setMounted(true);
  }, []);
  // Translation state: key is reviewKey, value is { text: string, loading: boolean, show: boolean }
  const [translations, setTranslations] = useState<Map<string, { text: string | null; loading: boolean; show: boolean }>>(new Map());

  const categoryRates = insights?.category_recommendation_rates;
  const subcategoryInsights = insights?.subcategory_insights;

  const reviewSample = analysis.reviews ?? EMPTY_REVIEWS;
  const filtersActive = useMemo(
    () => dashboardFiltersActive(filters) || reviewQuery.trim().length > 0 || lastMonthOnly || negativeOnly || highPlaytime || highHelpful,
    [filters, reviewQuery, lastMonthOnly, negativeOnly, highPlaytime, highHelpful],
  );

  // Helper to get rolling 30-day window
  const getLastMonthRange = useCallback(() => {
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 30, 0, 0, 0, 0);
    const end = now;
    return { start, end };
  }, []);

  const filteredReviewSample = useMemo(() => {
    let filtered = applyDashboardReviewFilters(reviewSample, filters);

    // Apply "last month only" filter
    if (lastMonthOnly) {
      const { start, end } = getLastMonthRange();
      filtered = filtered.filter((review) => {
        const created = parseDate((review as { created_at?: unknown }).created_at);
        if (!created) return false;
        return created >= start && created <= end;
      });
    }

    // Apply "negative only" filter
    if (negativeOnly) {
      filtered = filtered.filter((review) => !review.voted_up);
    }

    // Apply "20h+ playtime" filter
    if (highPlaytime) {
      filtered = filtered.filter((review) => {
        const playtime = (review as { author_playtime_hours?: number; author_playtime_forever?: number }).author_playtime_hours
          ?? ((review as { author_playtime_forever?: number }).author_playtime_forever || 0) / 60;
        return playtime >= 20;
      });
    }

    // Apply "10+ helpful" filter
    if (highHelpful) {
      filtered = filtered.filter((review) => ((review as { votes_up?: number }).votes_up || 0) >= 10);
    }

    const query = reviewQuery.trim().toLowerCase();
    if (!query) return filtered;
    return filtered.filter((review) => {
      const text = (review.review ?? "").toLowerCase();
      return text.includes(query);
    });
  }, [reviewSample, filters, reviewQuery, lastMonthOnly, negativeOnly, highPlaytime, highHelpful, getLastMonthRange]);
  const resetFilters = useCallback(() => {
    setFilters({ ...DEFAULT_DASHBOARD_FILTERS });
    setReviewQuery("");
    setLastMonthOnly(false);
    setNegativeOnly(false);
    setHighPlaytime(false);
    setHighHelpful(false);
  }, []);
  const updateFilters = useCallback((patch: Partial<DashboardFilters>) => {
    setFilters((prev) => ({ ...prev, ...patch }));
  }, []);
  const clearSelectedSubcategory = useCallback(() => {
    setSelectedSubcategory(null);
    setSelectedSubcategoryLanguage(null);
  }, []);
  const openSubcategory = useCallback(
    (subcategory: string, type: 'issue' | 'request' | 'general', language?: { key: string; label?: string }) => {
      const languageKey = language?.key?.toLowerCase() ?? null;
      const currentLanguageKey = selectedSubcategoryLanguage?.key?.toLowerCase() ?? null;
      const isSameSelection = selectedSubcategory === subcategory && currentLanguageKey === languageKey;
      if (isSameSelection) {
        clearSelectedSubcategory();
        return;
      }
      setSelectedSubcategory(subcategory);
      setSelectedSubcategoryType(type);
      if (languageKey) {
        setSelectedSubcategoryLanguage({
          key: languageKey,
          label: language?.label ?? toTitleCase(languageKey),
        });
      } else {
        setSelectedSubcategoryLanguage(null);
      }
    },
    [clearSelectedSubcategory, selectedSubcategory, selectedSubcategoryLanguage],
  );

  const trendSeries = useMemo(() => {
    if (filtersActive) {
      return buildTrendSeriesFromReviews(filteredReviewSample);
    }
    // The exact-run daily projection is the authoritative trend source. Do
    // not rebuild it from the review sample when the projection is available.
    if (dailyProjection?.recommendation.available) {
      return normalizeDailyProjectionSeries(dailyProjection.recommendation.points);
    }
    const normalized = normalizeTrendSeries(analysis.insights?.trend);
    if (normalized.length) return normalized;
    return dailyProjectionUnavailable ? [] : buildTrendSeriesFromReviews(reviewSample);
  }, [analysis.insights?.trend, dailyProjection, dailyProjectionUnavailable, filteredReviewSample, filtersActive, reviewSample]);

  const latestTrend = trendSeries.length ? trendSeries[trendSeries.length - 1] : null;
  const previousTrend = trendSeries.length > 1 ? trendSeries[trendSeries.length - 2] : null;
  const recDelta =
    latestTrend && previousTrend
      ? latestTrend.recommendation_rate - previousTrend.recommendation_rate
      : null;
  const volumeDelta = latestTrend && previousTrend ? latestTrend.reviews - previousTrend.reviews : null;
  const recDeltaLabel =
    recDelta === null ? "—" : `${recDelta >= 0 ? "+" : ""}${Math.round(recDelta * 100)}%`;
  const volumeDeltaLabel =
    volumeDelta === null ? "—" : `${volumeDelta >= 0 ? "+" : ""}${volumeDelta.toLocaleString()}`;
  const recDeltaClass =
    recDelta === null ? "text-slate-500" : recDelta >= 0 ? "text-emerald-400" : "text-rose-400";
  const volumeDeltaClass =
    volumeDelta === null ? "text-slate-500" : volumeDelta >= 0 ? "text-emerald-400" : "text-rose-400";
  const trendRangeLabel =
    trendSeries.length > 1 ? `${trendSeries[0].label} → ${trendSeries[trendSeries.length - 1].label}` : "";

  const activeSubcategoryInsights = useMemo(() => {
    if (!filtersActive && subcategoryInsights && subcategoryInsights.length) return subcategoryInsights;
    return buildSubcategoryInsights(filteredReviewSample);
  }, [filteredReviewSample, filtersActive, subcategoryInsights]);

  const activeCategoryRates = useMemo(() => {
    if (!filtersActive && categoryRates && Object.keys(categoryRates).length) return categoryRates;
    return buildCategoryRates(filteredReviewSample);
  }, [categoryRates, filteredReviewSample, filtersActive]);

  const subcatsByMain = useMemo(() => {
    const buckets = new Map<string, SubcategoryInsight[]>();
    (activeSubcategoryInsights ?? []).forEach((entry) => {
      const main = (entry.main_category || entry.subcategory?.split("/", 1)[0] || "other").toLowerCase();
      const list = buckets.get(main) ?? [];
      list.push(entry);
      buckets.set(main, list);
    });
    for (const [key, list] of buckets.entries()) {
      list.sort((a, b) => Number(b.count ?? 0) - Number(a.count ?? 0));
      buckets.set(key, list);
    }
    return buckets;
  }, [activeSubcategoryInsights]);

  const categories = useMemo(() => {
    const order = Object.keys(MAIN_CATEGORY_LABELS).filter((key) => key !== "other");
    return order.map((key) => {
      const payload = activeCategoryRates?.[key];
      const fallbackCount = (subcatsByMain.get(key) ?? []).reduce((sum, item) => sum + Number(item.count ?? 0), 0);
      const count = Number(payload?.count ?? fallbackCount);
      return {
        key,
        label: MAIN_CATEGORY_LABELS[key] ?? toTitleCase(key),
        accent: CATEGORY_ACCENTS[key] ?? theme.palette.accent,
        rate: payload?.rate,
        count,
        subcategories: subcatsByMain.get(key) ?? [],
      };
    });
  }, [activeCategoryRates, subcatsByMain, theme.palette.accent]);

  
  const issueItems = useMemo(() => {
    return (activeSubcategoryInsights ?? [])
      .filter((entry) => Number(entry.issue_count ?? 0) > 0)
      .sort((a, b) => Number(b.issue_count ?? 0) - Number(a.issue_count ?? 0))
      .slice(0, 5);
  }, [activeSubcategoryInsights]);

  const requestItems = useMemo(() => {
    return (activeSubcategoryInsights ?? [])
      .filter((entry) => Number(entry.request_count ?? 0) > 0)
      .sort((a, b) => Number(b.request_count ?? 0) - Number(a.request_count ?? 0))
      .slice(0, 5);
  }, [activeSubcategoryInsights]);

  const playerSegments = useMemo(() => {
    // Formal, unfiltered workbench segments must come from the persisted run
    // result. A capped review sample is not an equivalent denominator.
    if (!filtersActive) return insights?.player_segments ?? null;
    // Filtered views are explicitly exploratory and may be calculated from
    // the visible sample; the UI labels them as filtered below.
    return buildPlayerSegments(filteredReviewSample);
  }, [filteredReviewSample, filtersActive, insights?.player_segments]);
  const purchaseDataAvailable = Object.values(playerSegments?.purchase_type ?? {}).some(
    (segment) => Number((segment as { count?: number } | undefined)?.count ?? 0) > 0,
  );
  const experienceDataAvailable = filteredReviewSample.some((review) => review.author_num_games_owned != null);
  const activityDataAvailable = filteredReviewSample.some((review) => review.author_playtime_last_two_weeks != null);

  const selectedWeekReviews = useMemo(() => {
    if (!selectedTrendWeek) return [];
    const start = selectedTrendWeek.start;
    const end = selectedTrendWeek.end;
    return filteredReviewSample
      .filter((review) => {
        const created = extractReviewDate(review);
        if (!created) return false;
        return created >= start && created < end;
      })
      .sort((a, b) => Number(b.votes_up ?? 0) - Number(a.votes_up ?? 0));
  }, [filteredReviewSample, selectedTrendWeek]);

  const selectedReviews = useMemo(() => {
    if (!selectedSubcategory) return [];
    return filteredReviewSample
      .filter((review) => {
        const subcats = [
          ...(review.llm_subcategories ?? []),
          ...(review.llm_issue_subcategories ?? []),
          ...(review.llm_request_subcategories ?? []),
        ];
        const matchesSubcategory = Array.isArray(subcats) && subcats.includes(selectedSubcategory);
        if (!matchesSubcategory) return false;
        if (selectedSubcategoryLanguage?.key) {
          const reviewLang = (review.language || '').toLowerCase();
          return reviewLang === selectedSubcategoryLanguage.key.toLowerCase();
        }
        return true;
      })
      .sort((a, b) => Number(b.votes_up ?? 0) - Number(a.votes_up ?? 0));
  }, [filteredReviewSample, selectedSubcategory, selectedSubcategoryLanguage]);

  const selectedSegmentReviews = useMemo(() => {
    if (!selectedSegment) return [];
    const minutesFor = (review: ReviewRow) => {
      const val = review.author_playtime_forever;
      if (typeof val === "number") return val;
      if (typeof val === "string") return parseFloat(val) || 0;
      return 0;
    };
    const recentMinutesFor = (review: ReviewRow) => {
      const val = review.author_playtime_last_two_weeks;
      if (typeof val === "number") return val;
      if (typeof val === "string") return parseFloat(val) || 0;
      return 0;
    };
    const gamesOwned = (review: ReviewRow) => {
      const val = review.author_num_games_owned;
      if (typeof val === "number") return val;
      if (typeof val === "string") return parseInt(val, 10) || 0;
      return 0;
    };

    return filteredReviewSample
      .filter((review) => {
        switch (selectedSegment.type) {
          case 'experience': {
            const games = gamesOwned(review);
            switch (selectedSegment.key) {
              case 'newcomers': return games < 50;
              case 'casual': return games >= 50 && games < 200;
              case 'experienced': return games >= 200 && games < 500;
              case 'veterans': return games >= 500;
              default: return false;
            }
          }
          case 'purchase': return false;
          case 'activity': {
            const recent = recentMinutesFor(review);
            const total = minutesFor(review);
            switch (selectedSegment.key) {
              case 'currently_active': return recent > 0;
              case 'recently_stopped': return recent === 0 && total > 0;
              case 'inactive': return total === 0;
              default: return false;
            }
          }
          case 'engagement': {
            const minutes = minutesFor(review);
            switch (selectedSegment.key) {
              case 'highly_engaged': return minutes >= 1200; // 20h+
              case 'moderately_engaged': return minutes >= 120 && minutes < 1200; // 2-20h
              case 'low_engagement': return minutes < 120; // <2h
              default: return false;
            }
          }
          case 'language': {
            const reviewLang = (review.language || '').toLowerCase();
            return reviewLang === selectedSegment.key.toLowerCase();
          }
          default:
            return false;
        }
      })
      .sort((a, b) => Number(b.votes_up ?? 0) - Number(a.votes_up ?? 0));
  }, [filteredReviewSample, selectedSegment]);

  const highlightEvidence = (text: string, evidence: string[]): React.ReactNode => {
    if (!evidence || evidence.length === 0) return text;

    // Sort evidence by length (longest first) to handle overlapping matches
    const sortedEvidence = [...evidence].sort((a, b) => b.length - a.length);

    // Create a list of segments with their highlight status
    const segments: Array<{ text: string; highlight: boolean }> = [];
    let remainingText = text;
    let currentIndex = 0;

    // Find all evidence positions
    const matches: Array<{ start: number; end: number; text: string }> = [];
    sortedEvidence.forEach(snippet => {
      if (!snippet.trim()) return;
      const lowerText = text.toLowerCase();
      const lowerSnippet = snippet.toLowerCase();
      let index = lowerText.indexOf(lowerSnippet);
      while (index !== -1) {
        matches.push({ start: index, end: index + snippet.length, text: snippet });
        index = lowerText.indexOf(lowerSnippet, index + 1);
      }
    });

    // Sort matches by position and merge overlapping
    matches.sort((a, b) => a.start - b.start);
    const mergedMatches: typeof matches = [];
    matches.forEach(match => {
      if (mergedMatches.length === 0) {
        mergedMatches.push(match);
      } else {
        const last = mergedMatches[mergedMatches.length - 1];
        if (match.start <= last.end) {
          // Overlapping or adjacent - extend the last match
          last.end = Math.max(last.end, match.end);
        } else {
          mergedMatches.push(match);
        }
      }
    });

    // Build segments
    mergedMatches.forEach(match => {
      if (match.start > currentIndex) {
        segments.push({ text: text.slice(currentIndex, match.start), highlight: false });
      }
      segments.push({ text: text.slice(match.start, match.end), highlight: true });
      currentIndex = match.end;
    });

    if (currentIndex < text.length) {
      segments.push({ text: text.slice(currentIndex), highlight: false });
    }

    if (segments.length === 0) return text;

    return (
      <>
        {segments.map((segment, idx) =>
          segment.highlight ? (
            <mark
              key={idx}
              className="bg-yellow-400/30 text-yellow-100 rounded px-0.5"
            >
              {segment.text}
            </mark>
          ) : (
            <span key={idx}>{segment.text}</span>
          )
        )}
      </>
    );
  };

  const selectedSubcategoryLabel = selectedSubcategory ? toSubcategoryLabel(selectedSubcategory) : "";
  const selectedMainLabel = selectedSubcategory
    ? MAIN_CATEGORY_LABELS[selectedSubcategory.split("/", 1)[0]?.toLowerCase() ?? ""] ?? toTitleCase(selectedSubcategory)
    : "";
  const selectedSubcategoryLanguageLabel = selectedSubcategoryLanguage?.label ?? "";
  const summaryTotal = filteredReviewSample.length;
  const recommendationObservation = getMetricObservation(analysis.insights, "recommendation_rate");
  const issueObservation = getMetricObservation(analysis.insights, "technical_issue_rate");
  const requestObservation = getMetricObservation(analysis.insights, "feature_request_rate");
  const localRecommendationRate = summaryTotal > 0
    ? filteredReviewSample.reduce((sum, review) => sum + (isRecommended(review.voted_up) ? 1 : 0), 0) / summaryTotal
    : null;
  const localIssueRate = summaryTotal > 0
    ? filteredReviewSample.reduce((sum, review) => sum + (listifyStrings(review.llm_issue_subcategories).length ? 1 : 0), 0) / summaryTotal
    : null;
  const localRequestRate = summaryTotal > 0
    ? filteredReviewSample.reduce((sum, review) => sum + (listifyStrings(review.llm_request_subcategories).length ? 1 : 0), 0) / summaryTotal
    : null;
  const summaryRecommendationRate = filtersActive
    ? localRecommendationRate
    : metricValue(analysis.insights, "recommendation_rate", analysis.insights?.recommendation);
  const summaryIssueRate = filtersActive
    ? localIssueRate
    : metricValue(analysis.insights, "technical_issue_rate", analysis.insights?.llm?.issue_rate);
  const summaryRequestRate = filtersActive
    ? localRequestRate
    : metricValue(analysis.insights, "feature_request_rate", analysis.insights?.llm?.feature_request_rate);

  const trendLabels = trendSeries.map((point) => point.label);
  const recLineColor = theme.palette.secondary ?? theme.palette.accent;
  const recFillColor = hexToRgba(recLineColor, 0.18);
  const volumeBarColor = hexToRgba(theme.palette.accent, 0.55);
  const volumeBarHighlight = hexToRgba(theme.palette.accent, 0.9);
  const gridColor = "rgba(148,163,184,0.12)";
  const axisColor = "rgba(148,163,184,0.7)";
  const selectedTrendKey = selectedTrendWeek?.key ?? null;

  const recommendationTrendData = {
    labels: trendLabels,
    datasets: [
      {
        data: trendSeries.map((point) => Math.round(point.recommendation_rate * 100)),
        borderColor: recLineColor,
        backgroundColor: recFillColor,
        fill: true,
        tension: 0.35,
        pointRadius: 2,
        pointHoverRadius: 4,
        borderWidth: 2,
      },
    ],
  };

  const volumeTrendData = {
    labels: trendLabels,
    datasets: [
      {
        data: trendSeries.map((point) => point.reviews),
        backgroundColor: trendSeries.map((point) => {
          const key = point.date ? startOfWeek(point.date).toISOString().slice(0, 10) : point.label;
          return selectedTrendKey && key === selectedTrendKey ? volumeBarHighlight : volumeBarColor;
        }),
        borderRadius: 0,
        maxBarThickness: 28,
      },
    ],
  };

  const handleVolumeBarClick = useCallback(
    (index: number) => {
      const point = trendSeries[index];
      if (!point?.date) return;
      const start = startOfWeek(point.date);
      const end = new Date(start);
      end.setDate(end.getDate() + 7);
      const key = start.toISOString().slice(0, 10);
      const label = formatWeekRangeLabel(start);
      clearSelectedSubcategory();
      setSelectedTrendWeek((prev) => (prev?.key === key ? null : { key, start, end, label }));
    },
    [clearSelectedSubcategory, trendSeries],
  );

  const recommendationTrendOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (context: any) => `${context.parsed.y}% rec`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: gridColor },
        ticks: { color: axisColor, font: { size: 10 } },
      },
      y: {
        min: 0,
        max: 100,
        grid: { color: gridColor },
        ticks: {
          color: axisColor,
          font: { size: 10 },
          callback: (value: any) => `${value}%`,
        },
      },
    },
  };

  const volumeTrendOptions = {
    responsive: true,
    maintainAspectRatio: false,
    onClick: (_event: unknown, elements: Array<{ index: number }>) => {
      if (!elements || elements.length === 0) return;
      handleVolumeBarClick(elements[0].index);
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (context: any) => `${context.parsed.y.toLocaleString()} reviews`,
        },
      },
    },
    scales: {
      x: {
        grid: { color: gridColor },
        ticks: { color: axisColor, font: { size: 10 } },
      },
      y: {
        grid: { color: gridColor },
        ticks: {
          color: axisColor,
          font: { size: 10 },
          callback: (value: any) => value.toLocaleString(),
        },
      },
    },
  };


  const closeTopIssuesModal = useCallback(() => {
    setTopIssuesModalOpen(false);
    setTopIssuesSummary(null);
    setTopIssuesSummaryError(null);
    setTopIssuesSummaryLoading(false);
  }, []);

  const closeTopRequestsModal = useCallback(() => {
    setTopRequestsModalOpen(false);
    setTopRequestsSummary(null);
    setTopRequestsSummaryError(null);
    setTopRequestsSummaryLoading(false);
  }, []);

  const hasOverlay = Boolean(selectedSubcategory || selectedTrendWeek || selectedSegment || topIssuesModalOpen || topRequestsModalOpen);

  useEffect(() => {
    if (!hasOverlay) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (topIssuesModalOpen) {
          closeTopIssuesModal();
          return;
        }
        if (topRequestsModalOpen) {
          closeTopRequestsModal();
          return;
        }
        if (selectedSegment) {
          setSelectedSegment(null);
          return;
        }
        if (selectedTrendWeek) {
          setSelectedTrendWeek(null);
          return;
        }
        if (selectedSubcategory) {
          clearSelectedSubcategory();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, [
    hasOverlay,
    selectedTrendWeek,
    selectedSubcategory,
    selectedSegment,
    topIssuesModalOpen,
    topRequestsModalOpen,
    closeTopIssuesModal,
    closeTopRequestsModal,
    clearSelectedSubcategory,
  ]);

  useEffect(() => {
    setExpandedReviews(new Set());
    setSubcategorySummary(null);
    setSummaryError(null);
    setSummaryLoading(false);
  }, [selectedSubcategory]);

  useEffect(() => {
    if (!selectedTrendWeek) return;
    setExpandedReviews(new Set());
    setTrendWeekSummary(null);
    setTrendWeekSummaryError(null);
    setTrendWeekSummaryLoading(false);
  }, [selectedTrendWeek]);

  useEffect(() => {
    if (!selectedSegment) return;
    setExpandedReviews(new Set());
    setSegmentSummary(null);
    setSegmentSummaryError(null);
    setSegmentSummaryLoading(false);
  }, [selectedSegment]);

  useEffect(() => {
    setTopIssuesModalOpen(false);
    setTopIssuesSummary(null);
    setTopIssuesSummaryError(null);
    setTopIssuesSummaryLoading(false);
    setTopRequestsModalOpen(false);
    setTopRequestsSummary(null);
    setTopRequestsSummaryError(null);
    setTopRequestsSummaryLoading(false);
  }, [analysis]);

  // Lock body scroll when modal is open
  useEffect(() => {
    if (hasOverlay) {
      const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
      document.body.style.overflow = 'hidden';
      document.body.style.paddingRight = scrollbarWidth > 0 ? `${scrollbarWidth}px` : '';
    } else {
      document.body.style.overflow = '';
      document.body.style.paddingRight = '';
    }
    return () => {
      document.body.style.overflow = '';
      document.body.style.paddingRight = '';
    };
  }, [hasOverlay]);

  const filterScopeLabel = useMemo(() => {
    const parts: string[] = [];

    // Quick filters
    if (lastMonthOnly) parts.push("last 30 days");
    if (negativeOnly) parts.push("negative only");
    if (highPlaytime) parts.push("20h+ playtime");
    if (highHelpful) parts.push("10+ helpful");

    // Advanced filters
    if (filters.sentiment === "positive") parts.push("thumbs up only");
    if (filters.sentiment === "negative") parts.push("thumbs down only");

    if (filters.dateRange === "30d") parts.push("last 30d");
    if (filters.dateRange === "90d") parts.push("last 90d");
    if (filters.dateRange === "365d") parts.push("last 365d");
    if (filters.dateRange === "custom" && (filters.customStartDate || filters.customEndDate)) {
      const start = filters.customStartDate ? new Date(filters.customStartDate).toLocaleDateString() : "…";
      const end = filters.customEndDate ? new Date(filters.customEndDate).toLocaleDateString() : "…";
      parts.push(`custom range ${start} → ${end}`);
    }

    if (filters.minHelpful > 0) parts.push(`min helpful ≥${filters.minHelpful}`);

    if (filters.playtime === "lt2h") parts.push("playtime <2h");
    if (filters.playtime === "2to20h") parts.push("playtime 2–20h");
    if (filters.playtime === "20hplus") parts.push("playtime 20h+");

    if (filters.language && filters.language !== "all") {
      const match = LANGUAGE_OPTIONS.find((option) => option.value === filters.language.toLowerCase());
      parts.push(`language ${match?.label ?? filters.language}`);
    }

    const query = reviewQuery.trim();
    if (query) parts.push(`search "${query}"`);

    return parts.length ? parts.join(" · ") : null;
  }, [filters, reviewQuery, lastMonthOnly, negativeOnly, highPlaytime, highHelpful]);

  const handleSummarize = async () => {
    if (!selectedSubcategory || !selectedGame || selectedReviews.length === 0) return;

    setSummaryLoading(true);
    setSummaryError(null);

    try {
      const scopeParts: string[] = [];
      if (selectedSubcategoryLanguageLabel) scopeParts.push(`${selectedSubcategoryLanguageLabel} only`);
      if (filterScopeLabel) scopeParts.push(filterScopeLabel);
      const summary_context = scopeParts.length ? scopeParts.join(" · ") : "None";

      const result = await summarizeSubcategory({
        app_id: selectedGame.appid,
        subcategory: selectedSubcategory,
        summary_type: selectedSubcategoryType,
        // AI summaries in the reports workflow are intentionally fixed to
        // Simplified Chinese, independent of the surrounding UI language.
        output_language: "zh",
        summary_context,
        reviews: selectedReviews.slice(0, 50).map((r) => ({
          review_id: String(r.review_id ?? ""),
          review: r.review ?? "",
          voted_up: r.voted_up,
          votes_up: r.votes_up ?? 0,
          language: r.language ?? "",
          created_at: r.created_at,
          llm_subcategory_evidence: r.llm_subcategory_evidence ?? {},
          llm_subcategories: r.llm_subcategories ?? [],
          llm_issue_subcategories: r.llm_issue_subcategories ?? [],
          llm_request_subcategories: r.llm_request_subcategories ?? [],
        })),
      });
      setSubcategorySummary(result);
    } catch (err) {
      setSummaryError((err as Error).message || "AI 摘要生成失败，请检查系统设置中的 AI 服务配置后重试。");
    } finally {
      setSummaryLoading(false);
    }
  };

  const handleSummarizeTrendWeek = async () => {
    if (!selectedTrendWeek || !selectedGame || selectedWeekReviews.length === 0) return;

    setTrendWeekSummaryLoading(true);
    setTrendWeekSummaryError(null);

    const weekStart = selectedTrendWeek.start.toISOString().slice(0, 10);
    const weekEnd = selectedTrendWeek.end.toISOString().slice(0, 10);

    try {
      const result = await summarizeWidget({
        app_id: selectedGame.appid,
        widget_kind: "trend_week",
        widget_label: `Week of ${weekStart}`,
        context: {
          week_range: `${weekStart} → ${weekEnd}`,
          filters: filterScopeLabel ?? "None",
          baseline: {
            recommendation_rate: summaryRecommendationRate,
            issue_rate: summaryIssueRate,
            request_rate: summaryRequestRate,
          },
        },
        output_language: "zh",
        reviews: selectedWeekReviews.slice(0, 50).map((r) => ({
          review_id: String(r.review_id ?? ""),
          review: r.review ?? "",
          voted_up: r.voted_up,
          votes_up: r.votes_up ?? 0,
          votes_funny: r.votes_funny ?? 0,
          language: r.language ?? "",
          created_at: r.created_at,
          llm_subcategories: r.llm_subcategories ?? [],
          llm_issue_subcategories: r.llm_issue_subcategories ?? [],
          llm_request_subcategories: r.llm_request_subcategories ?? [],
          llm_subcategory_evidence: r.llm_subcategory_evidence ?? {},
        })),
      });

      setTrendWeekSummary(result);
    } catch (err) {
      setTrendWeekSummaryError((err as Error).message || "AI 摘要生成失败，请检查系统设置中的 AI 服务配置后重试。");
    } finally {
      setTrendWeekSummaryLoading(false);
    }
  };

  const handleSummarizeSegment = async () => {
    if (!selectedSegment || !selectedGame || selectedSegmentReviews.length === 0) return;

    setSegmentSummaryLoading(true);
    setSegmentSummaryError(null);

    const segmentCriteria = (() => {
      switch (selectedSegment.type) {
        case "experience":
          switch (selectedSegment.key) {
            case "newcomers":
              return "<50 games owned";
            case "casual":
              return "50–200 games owned";
            case "experienced":
              return "200–500 games owned";
            case "veterans":
              return "500+ games owned";
            default:
              return "unknown";
          }
        case "purchase":
          switch (selectedSegment.key) {
            case "steam_buyers":
              return "Steam purchase";
            case "key_users":
              return "Activated key (not Steam purchase, not free)";
            case "free_users":
              return "Received for free";
            default:
              return "unknown";
          }
        case "activity":
          switch (selectedSegment.key) {
            case "currently_active":
              return "Played in the last 2 weeks";
            case "recently_stopped":
              return "No playtime in the last 2 weeks, but has total playtime";
            case "inactive":
              return "No playtime recorded";
            default:
              return "unknown";
          }
        case "engagement":
          switch (selectedSegment.key) {
            case "highly_engaged":
              return "20h+ played";
            case "moderately_engaged":
              return "2–20h played";
            case "low_engagement":
              return "<2h played";
            default:
              return "unknown";
          }
        case "language":
          return `Reviews written in ${selectedSegment.label}`;
        default:
          return "unknown";
      }
    })();

    try {
      const result = await summarizeWidget({
        app_id: selectedGame.appid,
        widget_kind: "segment",
        widget_label: `${selectedSegment.label} (${segmentCriteria})`,
        context: {
          segment_type: selectedSegment.type,
          segment_key: selectedSegment.key,
          segment_criteria: segmentCriteria,
          filters: filterScopeLabel ?? "None",
          baseline: {
            recommendation_rate: summaryRecommendationRate,
            issue_rate: summaryIssueRate,
            request_rate: summaryRequestRate,
          },
        },
        output_language: "zh",
        reviews: selectedSegmentReviews.slice(0, 50).map((r) => ({
          review_id: String(r.review_id ?? ""),
          review: r.review ?? "",
          voted_up: r.voted_up,
          votes_up: r.votes_up ?? 0,
          votes_funny: r.votes_funny ?? 0,
          language: r.language ?? "",
          created_at: r.created_at,
          llm_subcategories: r.llm_subcategories ?? [],
          llm_issue_subcategories: r.llm_issue_subcategories ?? [],
          llm_request_subcategories: r.llm_request_subcategories ?? [],
          llm_subcategory_evidence: r.llm_subcategory_evidence ?? {},
        })),
      });

      setSegmentSummary(result);
    } catch (err) {
      setSegmentSummaryError((err as Error).message || "AI 摘要生成失败，请检查系统设置中的 AI 服务配置后重试。");
    } finally {
      setSegmentSummaryLoading(false);
    }
  };

  const handleSummarizeTopIssues = async () => {
    if (!selectedGame || issueItems.length === 0) return;

    setTopIssuesModalOpen(true);
    setTopIssuesSummaryLoading(true);
    setTopIssuesSummaryError(null);

    // Collect the top issue subcategory keys
    const topSubcatKeys = issueItems.map((e) => e.subcategory || e.sub_category || "other/general");

    // Filter reviews that have at least one matching issue subcategory
    const relevantReviews = reviewSample.filter((r) => {
      const issueSubs = listifyStrings(r.llm_issue_subcategories);
      return issueSubs.some((s) => topSubcatKeys.includes(s));
    });

    if (relevantReviews.length === 0) {
      setTopIssuesSummaryError("没有找到带有匹配问题标签的评论。");
      setTopIssuesSummaryLoading(false);
      return;
    }

    try {
      const result = await summarizeWidget({
        app_id: selectedGame.appid,
        widget_kind: "top_issues",
        widget_label: `Top ${issueItems.length} reported issues`,
        context: {
          top_subcategories: issueItems.map((e) => ({
            subcategory: e.subcategory || e.sub_category,
            issue_count: Number(e.issue_count ?? 0),
          })),
          filters: filterScopeLabel ?? "None",
        },
        reviews: relevantReviews.slice(0, 50).map((r) => ({
          review_id: String(r.review_id ?? ""),
          review: r.review ?? "",
          voted_up: r.voted_up,
          votes_up: r.votes_up ?? 0,
          votes_funny: r.votes_funny ?? 0,
          language: r.language ?? "",
          created_at: r.created_at,
          llm_subcategories: r.llm_subcategories ?? [],
          llm_issue_subcategories: r.llm_issue_subcategories ?? [],
          llm_request_subcategories: r.llm_request_subcategories ?? [],
          llm_subcategory_evidence: r.llm_subcategory_evidence ?? {},
        })),
        output_language: "zh",
        run_id: analysis?.run_id ?? null,
      });

      setTopIssuesSummary(result);
    } catch (err) {
      setTopIssuesSummaryError((err as Error).message || "AI 摘要生成失败，请检查系统设置中的 AI 服务配置后重试。");
    } finally {
      setTopIssuesSummaryLoading(false);
    }
  };

  const handleSummarizeTopRequests = async () => {
    if (!selectedGame || requestItems.length === 0) return;

    setTopRequestsModalOpen(true);
    setTopRequestsSummaryLoading(true);
    setTopRequestsSummaryError(null);

    // Collect the top request subcategory keys
    const topSubcatKeys = requestItems.map((e) => e.subcategory || e.sub_category || "other/general");

    // Filter reviews that have at least one matching request subcategory
    const relevantReviews = reviewSample.filter((r) => {
      const requestSubs = listifyStrings(r.llm_request_subcategories);
      return requestSubs.some((s) => topSubcatKeys.includes(s));
    });

    if (relevantReviews.length === 0) {
      setTopRequestsSummaryError("没有找到带有匹配需求标签的评论。");
      setTopRequestsSummaryLoading(false);
      return;
    }

    try {
      const result = await summarizeWidget({
        app_id: selectedGame.appid,
        widget_kind: "top_requests",
        widget_label: `Top ${requestItems.length} feature requests`,
        context: {
          top_subcategories: requestItems.map((e) => ({
            subcategory: e.subcategory || e.sub_category,
            request_count: Number(e.request_count ?? 0),
          })),
          filters: filterScopeLabel ?? "None",
        },
        reviews: relevantReviews.slice(0, 50).map((r) => ({
          review_id: String(r.review_id ?? ""),
          review: r.review ?? "",
          voted_up: r.voted_up,
          votes_up: r.votes_up ?? 0,
          votes_funny: r.votes_funny ?? 0,
          language: r.language ?? "",
          created_at: r.created_at,
          llm_subcategories: r.llm_subcategories ?? [],
          llm_issue_subcategories: r.llm_issue_subcategories ?? [],
          llm_request_subcategories: r.llm_request_subcategories ?? [],
          llm_subcategory_evidence: r.llm_subcategory_evidence ?? {},
        })),
        output_language: "zh",
        run_id: analysis?.run_id ?? null,
      });

      setTopRequestsSummary(result);
    } catch (err) {
      setTopRequestsSummaryError((err as Error).message || "AI 摘要生成失败，请检查系统设置中的 AI 服务配置后重试。");
    } finally {
      setTopRequestsSummaryLoading(false);
    }
  };

  // Health overview: prefer manual refresh override, fall back to auto-generated from insights
  const healthOverview = healthOverviewOverride ?? insights?.health_overview ?? null;

  const handleRefreshHealthOverview = useCallback(async () => {
    if (!selectedGame) return;

    const requestId = healthOverviewRequestIdRef.current + 1;
    healthOverviewRequestIdRef.current = requestId;

    setHealthOverviewRefreshing(true);

    try {
      const result = await summarizeRecentReviews({
        app_id: selectedGame.appid,
        count: 500,
        filter_context: filterScopeLabel ?? undefined,
        output_language: "zh",
      });
      if (healthOverviewRequestIdRef.current !== requestId) return;
      setHealthOverviewOverride({
        summary: result.summary,
        key_points: result.key_points,
        actions: result.actions,
        health_score: result.health_score ?? 5,
        sentiment_trend: result.sentiment_trend ?? "stable",
        top_strengths: result.top_strengths ?? [],
        review_count: result.review_count,
        start_date: result.start_date,
        end_date: result.end_date,
      });
    } catch {
      // Silently fail — the card still shows previous data or empty state
    } finally {
      if (healthOverviewRequestIdRef.current !== requestId) return;
      setHealthOverviewRefreshing(false);
    }
  }, [selectedGame, filterScopeLabel, userLanguage]);

  return (
    <div className="space-y-8">
      <Card variant="glass" className={`relative overflow-hidden border-white/15 p-4 sm:p-6 ${mounted ? 'animate-fade-slide-up' : 'opacity-0'}`}>
        <div className="flex flex-col gap-4 sm:gap-6 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-start gap-3 sm:gap-5">
            {selectedGame ? (
              <SteamImage
                appId={selectedGame.appid}
                variant="header"
                alt={selectedGame.name}
                className="h-16 w-28 sm:h-24 sm:w-44 rounded-lg sm:rounded-xl object-cover flex-shrink-0"
                imageUrl={analysis.metadata.header_image}
              />
            ) : null}
            <div className="space-y-1 sm:space-y-2 min-w-0">
              <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                <h2 className="text-2xl font-semibold tracking-tight text-white line-clamp-2 sm:text-3xl">
                  {selectedGame?.name ?? "Analysis"}
                </h2>
                {selectedGame && <CurrentPlayersWidget appId={selectedGame.appid} />}
              </div>
              <p className="text-xs sm:text-sm text-slate-400">
                最近运行：{analysis.metadata.fetched_at ? new Date(analysis.metadata.fetched_at).toLocaleDateString('zh-CN') : '时间未知'}
              </p>
              <p className="text-[11px] sm:text-xs text-slate-500">
                {(analysis.metadata.analysis_population_count ?? analysis.metadata.retrieved).toLocaleString()} 条评论 · {analysis.metadata.mode === 'codex_offline_fixture' ? '离线开发 Fixture' : '分析结果'}
              </p>
              <details className="text-[11px] text-slate-500">
                <summary className="cursor-pointer text-slate-400">查看 Run / 来源信息</summary>
                <div className="mt-2 grid gap-1 rounded border border-white/10 bg-slate-950/40 p-2 sm:grid-cols-2">
                  <span>Run ID：{analysis.run_id ?? analysis.metadata.run_id ?? '未知'}</span>
                  <span>来源：{analysis.metadata.source ?? '未知'}</span>
                  <span>模式：{analysis.metadata.mode ?? '未知'}</span>
                  <span>样本：{(analysis.metadata.analysis_population_count ?? analysis.metadata.retrieved).toLocaleString()} 条</span>
                  <span>时间范围：{analysis.metadata.window_start ?? '未知'} → {analysis.metadata.window_end ?? '未知'}</span>
                  <span>Provider 成本：{analysis.metadata.mode === 'codex_offline_fixture' ? '0（未调用 Provider）' : '见成本台账'}</span>
                  {provenance && <span>Taxonomy / Prompt：{provenance.taxonomy_version ?? '未知'} / {provenance.prompt_version ?? '未知'}</span>}
                  {provenance && <span>结果 Schema：{provenance.result_schema_version ?? '未知'} · 完成：{provenance.completed_at ?? '未知'}</span>}
                </div>
              </details>
              {/* Compact metadata row: Developer · Release Date · Price */}
              <div className="text-[11px] text-slate-500 flex flex-wrap items-center gap-x-1">
                {gameDetailsLoading ? (
                  <span className="animate-pulse">Loading details...</span>
                ) : gameDetailsUnavailable ? (
                  <span className="text-slate-500">游戏详情暂时不可用</span>
                ) : (
                  <>
                    {gameDetails?.developers && gameDetails.developers.length > 0 && (
                      <span>{gameDetails.developers.join(', ')}</span>
                    )}
                    {gameDetails?.developers && gameDetails.developers.length > 0 && gameDetails?.release_date && (
                      <span>·</span>
                    )}
                    {gameDetails?.coming_soon ? (
                      <span className="text-amber-400">Coming Soon</span>
                    ) : gameDetails?.release_date ? (
                      <span>{gameDetails.release_date}</span>
                    ) : null}
                    {(gameDetails?.release_date || gameDetails?.coming_soon) && (gameDetails?.is_free || gameDetails?.price_final) && (
                      <span>·</span>
                    )}
                    {gameDetails?.is_free ? (
                      <span className="text-emerald-400">Free</span>
                    ) : gameDetails?.price_final ? (
                      <span className="inline-flex items-center gap-1">
                        {gameDetails.price_discount > 0 && gameDetails.price_initial_formatted && (
                          <>
                            <span className="line-through">{gameDetails.price_initial_formatted}</span>
                            <span className="text-[10px] px-1 rounded bg-emerald-500/20 text-emerald-400">-{gameDetails.price_discount}%</span>
                          </>
                        )}
                        <span>{gameDetails.price_final_formatted ?? `$${gameDetails.price_final.toFixed(2)}`}</span>
                      </span>
                    ) : null}
                  </>
                )}
              </div>
            </div>
          </div>

        {updateSuccess && (
          <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-2 sm:p-3">
            <p className="text-xs sm:text-sm text-green-400">{updateSuccess}</p>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 sm:p-3">
            <p className="text-xs sm:text-sm text-rose-400">{error}</p>
          </div>
        )}

        {onUpdate && (
          <div className="flex flex-wrap items-center gap-2 sm:gap-3 sm:justify-end">
            <Button onClick={onUpdate} variant="ghost" size="sm" className="text-xs sm:text-sm flex-1 sm:flex-none">
              {t('dashboard.update')}
            </Button>
          </div>
        )}
      </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Quick filter toggles */}
          <button
            onClick={() => setLastMonthOnly((prev) => !prev)}
            className={`text-xs px-2.5 py-1.5 sm:px-2 sm:py-1 rounded border transition-colors ${
              lastMonthOnly
                ? "border-sky-500/50 bg-sky-500/20 text-sky-300"
                : "border-white/10 text-slate-400 hover:text-sky-400 hover:border-sky-500/30"
            }`}
          >
            {t('dashboard.lastMonthOnly')}
          </button>
          <button
            onClick={() => setNegativeOnly((prev) => !prev)}
            className={`text-xs px-2.5 py-1.5 sm:px-2 sm:py-1 rounded border transition-colors ${
              negativeOnly
                ? "border-rose-500/50 bg-rose-500/20 text-rose-300"
                : "border-white/10 text-slate-400 hover:text-rose-400 hover:border-rose-500/30"
            }`}
          >
            仅看负面
          </button>
          <button
            onClick={() => setHighPlaytime((prev) => !prev)}
            className={`text-xs px-2.5 py-1.5 sm:px-2 sm:py-1 rounded border transition-colors ${
              highPlaytime
                ? "border-amber-500/50 bg-amber-500/20 text-amber-300"
                : "border-white/10 text-slate-400 hover:text-amber-400 hover:border-amber-500/30"
            }`}
          >
            游玩 20 小时以上
          </button>
          <button
            onClick={() => setHighHelpful((prev) => !prev)}
            className={`text-xs px-2.5 py-1.5 sm:px-2 sm:py-1 rounded border transition-colors ${
              highHelpful
                ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-300"
                : "border-white/10 text-slate-400 hover:text-emerald-400 hover:border-emerald-500/30"
            }`}
          >
            10 个以上有用票
          </button>
          {filtersActive && (
            <button onClick={resetFilters} className="text-xs px-2.5 py-1.5 sm:px-0 sm:py-0 text-slate-500 hover:text-slate-300">
              {t('common.clearFilters')}
            </button>
          )}
          {filtersActive && <span className="text-xs text-emerald-400 hidden sm:inline">•</span>}
          <button
            onClick={() => setFiltersOpen((prev) => !prev)}
            className="text-xs px-2.5 py-1.5 sm:px-0 sm:py-0 text-slate-400 hover:text-sky-400 transition-colors"
          >
            {filtersOpen ? t('dashboard.hideFilters') : t('dashboard.showFilters')} {filtersOpen ? "↑" : "→"}
          </button>
        </div>

        {filtersOpen && (
          <Card variant="glass" className="mt-2 p-4">
            <DashboardFiltersBar filters={filters} onChange={updateFilters} />
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <input
                value={reviewQuery}
                onChange={(event) => setReviewQuery(event.target.value)}
                placeholder={t('database.searchPlaceholder')}
                className="flex-1 min-w-[200px] rounded border border-white/10 bg-slate-900/70 px-2 py-1 text-xs text-slate-100 placeholder:text-slate-500 focus:border-sky-400 focus:outline-none"
              />
              <span className="text-xs text-slate-500">
                {filteredReviewSample.length} / {reviewSample.length} reviews
              </span>
            </div>
          </Card>
        )}

        {/* Hero KPI cards */}
        <div className="mt-5 grid gap-2 sm:gap-3 grid-cols-3">
          {filtersActive && (
            <p className="col-span-3 text-[10px] text-amber-300/80">
              Filtered interactive view · legacy semantic rates are calculated for the selected review subset. Research Core metrics above remain fixed to the full analyzed population.
            </p>
          )}
          {/* Recommendation Rate */}
          <div className={`rounded-xl border border-white/10 bg-slate-900/30 px-3 py-2 flex items-center gap-2 ${mounted ? 'animate-fade-slide-up animation-delay-100' : 'opacity-0'}`}>
            <p className="text-[10px] sm:text-xs uppercase tracking-[0.2em] text-slate-400">{t('dashboard.recommendation')}</p>
            <p
              className="text-lg sm:text-xl font-semibold ml-auto"
              style={{ color: getRecommendationColor(summaryRecommendationRate ?? 0) }}
            >
              {formatPercentOrDash(summaryRecommendationRate)}
            </p>
            {!filtersActive && recommendationObservation && <span className="text-[9px] text-slate-500">{metricSecondaryLabel(recommendationObservation)}</span>}
          </div>
          {/* Issue Rate */}
          <div className={`rounded-xl border border-white/10 bg-slate-900/30 px-3 py-2 flex items-center gap-2 ${mounted ? 'animate-fade-slide-up animation-delay-150' : 'opacity-0'}`}>
            <p className="text-[10px] sm:text-xs uppercase tracking-[0.2em] text-slate-400">{t('dashboard.issueRate')}</p>
            <p className="text-lg sm:text-xl font-semibold text-white ml-auto">{formatPercentOrDash(summaryIssueRate)}</p>
            {!filtersActive && issueObservation && <span className="text-[9px] text-slate-500">{metricSecondaryLabel(issueObservation)}</span>}
            {issueItems.length > 0 && (
              <span className="text-[10px] text-slate-500">{issueItems.reduce((s, e) => s + Number(e.issue_count ?? 0), 0).toLocaleString()}</span>
            )}
          </div>
          {/* Request Rate */}
          <div className={`rounded-xl border border-white/10 bg-slate-900/30 px-3 py-2 flex items-center gap-2 ${mounted ? 'animate-fade-slide-up animation-delay-200' : 'opacity-0'}`}>
            <p className="text-[10px] sm:text-xs uppercase tracking-[0.2em] text-slate-400">{t('dashboard.requestRate')}</p>
            <p className="text-lg sm:text-xl font-semibold text-white ml-auto">{formatPercentOrDash(summaryRequestRate)}</p>
            {!filtersActive && requestObservation && <span className="text-[9px] text-slate-500">{metricSecondaryLabel(requestObservation)}</span>}
            {requestItems.length > 0 && (
              <span className="text-[10px] text-slate-500">{requestItems.reduce((s, e) => s + Number(e.request_count ?? 0), 0).toLocaleString()}</span>
            )}
          </div>
        </div>
      </Card>

      {/* Health Overview Card */}
      <div className={mounted ? 'animate-fade-slide-up animation-delay-75' : 'opacity-0'}>
        <div className="flex items-center justify-between mb-1">
          <button type="button" onClick={() => toggleWidget('healthOverview')} className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300 transition-colors">
            <svg className={`w-3 h-3 transition-transform ${collapsedWidgets.has('healthOverview') ? '-rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            {collapsedWidgets.has('healthOverview') ? 'Show' : 'Hide'} Overview
          </button>
        </div>
        {!collapsedWidgets.has('healthOverview') && (
          <HealthOverviewCard
            overview={healthOverview}
            onRefresh={handleRefreshHealthOverview}
            refreshing={healthOverviewRefreshing}
            gameName={selectedGame?.name}
            reviewCount={healthOverviewOverride?.review_count ?? analysis.metadata?.retrieved}
            startDate={healthOverviewOverride?.start_date}
            endDate={healthOverviewOverride?.end_date}
          />
        )}
      </div>

      <div className="space-y-6">

        <div>
          <button type="button" onClick={() => toggleWidget('topIssuesRequests')} className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300 transition-colors mb-2">
            <svg className={`w-3 h-3 transition-transform ${collapsedWidgets.has('topIssuesRequests') ? '-rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            {collapsedWidgets.has('topIssuesRequests') ? '显示' : '隐藏'} 问题与需求
          </button>
        {!collapsedWidgets.has('topIssuesRequests') && (
        <div className="grid gap-4 sm:gap-6 xl:grid-cols-2">
          <Card variant="glass" className={`p-4 sm:p-6 ${mounted ? 'animate-fade-slide-up animation-delay-250' : 'opacity-0'}`}>
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-base sm:text-lg font-semibold text-white">{t('dashboard.topIssues')}</h4>
                <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-slate-400">玩家最常提到的问题</p>
              </div>
              <div className="flex items-center gap-2">
                {issueItems.length > 0 && (
                  <button
                    onClick={handleSummarizeTopIssues}
                    disabled={topIssuesSummaryLoading}
                    className="text-[10px] sm:text-xs px-2 py-1 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    AI 摘要
                  </button>
                )}
              </div>
            </div>
            {issueItems.length === 0 ? (
              <p className="mt-3 text-xs sm:text-sm text-slate-500">暂未发现问题标签。</p>
            ) : (
              <div className="mt-3 sm:mt-4 space-y-2 sm:space-y-3">
                {issueItems.map((entry) => {
                  const subcategoryKey = entry.subcategory || entry.sub_category || "other/general";
                  const label = toSubcategoryLabel(subcategoryKey, entry.sub_category) || "其他";
                  const issueCount = Number(entry.issue_count ?? 0);
                  const issuePercentage = reviewSample.length > 0 ? Math.round((issueCount / reviewSample.length) * 100) : 0;
                  const snippet = entry.issue_snippets?.[0] ?? "";
                  return (
                    <button
                      key={subcategoryKey}
                      type="button"
                      onClick={() => {
                        openSubcategory(subcategoryKey, 'issue');
                      }}
                      className={`flex w-full items-start justify-between gap-2 rounded-lg sm:rounded-xl border px-2.5 sm:px-3 py-2 text-left active:scale-[0.99] ${
                        selectedSubcategory === subcategoryKey
                          ? "border-sky-400/50 bg-sky-500/10"
                          : "border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10"
                      }`}
                    >
                      <div className="min-w-0 space-y-0.5 sm:space-y-1 flex-1">
                        <p className="truncate text-xs sm:text-sm text-slate-200">{label}</p>
                        <p className="text-[10px] sm:text-xs text-slate-500">
                          {issueCount.toLocaleString()} / {reviewSample.length.toLocaleString()} 条评论（{issuePercentage}%） · 分类覆盖率 100%
                        </p>
                        {snippet ? (
                          <p className="text-[10px] sm:text-xs text-slate-400 line-clamp-2">{snippet}</p>
                        ) : null}
                      </div>
                      <p
                        className="text-xs sm:text-sm font-semibold flex-shrink-0"
                        style={{ color: getRecommendationColor(entry.recommendation_rate) }}
                      >
                        {formatPercentOrDash(entry.recommendation_rate)}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </Card>

          <Card variant="glass" className={`p-4 sm:p-6 ${mounted ? 'animate-fade-slide-up animation-delay-300' : 'opacity-0'}`}>
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-base sm:text-lg font-semibold text-white">{t('dashboard.topRequests')}</h4>
                <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-slate-400">玩家最常提出的需求</p>
              </div>
              <div className="flex items-center gap-2">
                {requestItems.length > 0 && (
                  <button
                    onClick={handleSummarizeTopRequests}
                    disabled={topRequestsSummaryLoading}
                    className="text-[10px] sm:text-xs px-2 py-1 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    AI 摘要
                  </button>
                )}
              </div>
            </div>
            {requestItems.length === 0 ? (
              <p className="mt-3 text-xs sm:text-sm text-slate-500">暂时没有带有需求标签的评论。</p>
            ) : (
              <div className="mt-3 sm:mt-4 space-y-2 sm:space-y-3">
                {requestItems.map((entry) => {
                  const subcategoryKey = entry.subcategory || entry.sub_category || "other/general";
                  const label = toSubcategoryLabel(subcategoryKey, entry.sub_category) || "其他";
                  const requestCount = Number(entry.request_count ?? 0);
                  const requestPercentage = reviewSample.length > 0 ? Math.round((requestCount / reviewSample.length) * 100) : 0;
                  const snippet = entry.request_snippets?.[0] ?? "";
                  return (
                    <button
                      key={subcategoryKey}
                      type="button"
                      onClick={() => {
                        openSubcategory(subcategoryKey, 'request');
                      }}
                      className={`flex w-full items-start justify-between gap-2 rounded-lg sm:rounded-xl border px-2.5 sm:px-3 py-2 text-left active:scale-[0.99] ${
                        selectedSubcategory === subcategoryKey
                          ? "border-sky-400/50 bg-sky-500/10"
                          : "border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10"
                      }`}
                    >
                      <div className="min-w-0 space-y-0.5 sm:space-y-1 flex-1">
                        <p className="truncate text-xs sm:text-sm text-slate-200">{label}</p>
                        <p className="text-[10px] sm:text-xs text-slate-500">
                          {requestCount.toLocaleString()} / {reviewSample.length.toLocaleString()} 条评论（{requestPercentage}%） · 分类覆盖率 100%
                        </p>
                        {snippet ? (
                          <p className="text-[10px] sm:text-xs text-slate-400 line-clamp-2">{snippet}</p>
                        ) : null}
                      </div>
                      <p
                        className="text-xs sm:text-sm font-semibold flex-shrink-0"
                        style={{ color: getRecommendationColor(entry.recommendation_rate) }}
                      >
                        {formatPercentOrDash(entry.recommendation_rate)}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
        )}
        </div>

        <section className={`workspace-section p-6 ${mounted ? 'animate-fade-slide-up animation-delay-400' : 'opacity-0'}`}>
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-base sm:text-lg font-semibold text-white">{t('dashboard.categoriesOverview')}</h4>
            <p className="mt-1 text-xs sm:text-sm text-slate-400">各分类推荐率（仅作描述性观察）</p>
            </div>
            <button type="button" onClick={() => toggleWidget('categoriesOverview')} className="text-slate-500 hover:text-slate-300 transition-colors p-1" title={collapsedWidgets.has('categoriesOverview') ? 'Expand' : 'Collapse'}>
              <svg className={`w-4 h-4 transition-transform ${collapsedWidgets.has('categoriesOverview') ? '-rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </button>
          </div>

          {!collapsedWidgets.has('categoriesOverview') && (
          <div className="mt-4 sm:mt-5 grid gap-3 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {categories.map((category) => {
              const rateText = formatPercentOrDash(category.rate);
              const rateColor = getRecommendationColor(category.rate);
              return (
                <div
                  key={category.key}
                  className="border-b border-white/10 py-3 sm:py-4 last:border-b-0"
                >
                  <div className="flex items-start justify-between gap-2 sm:gap-4">
                    <div className="min-w-0 flex-1">
                      <p className="text-[10px] sm:text-xs uppercase tracking-[0.2em] sm:tracking-[0.25em] text-slate-400 truncate">{category.label}</p>
                      <p className="mt-0.5 sm:mt-1 text-[10px] sm:text-xs text-slate-500">{category.count.toLocaleString()} reviews</p>
                    </div>
                    <p className="text-2xl sm:text-3xl font-semibold flex-shrink-0" style={{ color: rateColor }}>
                      {rateText}
                    </p>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 sm:mt-4 sm:grid-cols-3 sm:gap-2">
                    {category.subcategories.length === 0 ? (
                      <p className="text-xs sm:text-sm text-slate-500 col-span-2">当前没有已标注的子分类。</p>
                    ) : (
                      category.subcategories.map((sub) => (
                        <button
                          key={sub.subcategory}
                          type="button"
                          onClick={() => {
                            openSubcategory(sub.subcategory, 'general');
                          }}
                          className={`flex flex-col items-start rounded-lg sm:rounded-xl border px-2 sm:px-3 py-1.5 sm:py-2 text-left active:scale-[0.98] ${
                            selectedSubcategory === sub.subcategory
                              ? "border-sky-400/50 bg-sky-500/10"
                            : "border-transparent bg-white/[0.035] hover:border-white/10 hover:bg-white/[0.07]"
                          }`}
                        >
                          <div className="w-full min-w-0">
                            <p className="truncate text-[11px] sm:text-sm text-slate-200">
                              {toSubcategoryLabel(sub.subcategory, sub.sub_category)}
                            </p>
                            <div className="flex items-center justify-between gap-1 sm:gap-2 mt-0.5 sm:mt-1">
                              <p className="text-[10px] sm:text-xs text-slate-500">{Number(sub.count ?? 0).toLocaleString()}</p>
                              <p
                                className="text-[11px] sm:text-sm font-semibold"
                                style={{ color: getRecommendationColor(sub.recommendation_rate) }}
                              >
                                {formatPercentOrDash(sub.recommendation_rate)}
                              </p>
                            </div>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          )}
        </section>

        <Card variant="glass" className={`p-6 ${mounted ? 'animate-fade-slide-up animation-delay-500' : 'opacity-0'}`}>
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold text-white">每日确定性信号</h4>
              <p className="mt-1 text-xs text-slate-500">仅使用当前 Run 的完整原始评论；不以抽样数据补齐。</p>
            </div>
            {dailyProjection && <span className="text-[11px] text-emerald-300">exact run population</span>}
          </div>
          {dailyProjection ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {dailyProjection.recommendation.points.map((point) => (
                <div key={point.period} className="flex items-center justify-between rounded border border-white/10 bg-slate-950/30 px-3 py-2 text-xs">
                  <span className="text-slate-400">{point.period}</span>
                  <span className="text-slate-200">
                    {point.recommendation_rate == null ? "—" : `${Math.round(point.recommendation_rate * 100)}%`} · {point.review_count.toLocaleString()} reviews
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500">{dailyProjectionUnavailable ?? "每日 projection 暂不可用。"}</p>
          )}
        </Card>

        <Card variant="glass" className={`p-6 ${mounted ? 'animate-fade-slide-up animation-delay-500' : 'opacity-0'}`}>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h4 className="text-lg font-semibold text-white">趋势</h4>
              <p className="mt-1 text-sm text-slate-400">推荐率与评论量如何随时间变化</p>
            </div>
            <div className="flex items-center gap-3">
              {latestTrend && (
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  <span className="text-slate-400">
                    {userLanguage === 'zh' ? '最新推荐率 ' : 'Latest '}{formatPercentOrDash(latestTrend.recommendation_rate)}{userLanguage === 'zh' ? '' : ' rec'}
                  </span>
                  <span className={recDeltaClass}>{recDeltaLabel}</span>
                  <span className="text-slate-400">{latestTrend.reviews.toLocaleString()} {userLanguage === 'zh' ? '条评论' : 'reviews'}</span>
                  <span className={volumeDeltaClass}>{volumeDeltaLabel}</span>
                  {filtersActive && (
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-slate-300">
                      filtered view
                    </span>
                  )}
                </div>
              )}
              <button type="button" onClick={() => toggleWidget('sentimentTrend')} className="text-slate-500 hover:text-slate-300 transition-colors p-1" title={collapsedWidgets.has('sentimentTrend') ? 'Expand' : 'Collapse'}>
                <svg className={`w-4 h-4 transition-transform ${collapsedWidgets.has('sentimentTrend') ? '-rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
              </button>
            </div>
          </div>

          {!collapsedWidgets.has('sentimentTrend') && (trendSeries.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">
              {filtersActive && filteredReviewSample.length === 0
                ? "No reviews match the current filters."
                : reviewSample.length > 0
                ? "Trend data is missing for this analysis. Re-run analysis to include timestamps."
                : "Trend data is not available for this analysis."}
            </p>
          ) : (
            <div className="mt-4 sm:mt-5 grid gap-3 sm:gap-4 lg:grid-cols-2">
              <div className="rounded-xl sm:rounded-2xl border border-white/10 bg-slate-900/30 p-3 sm:p-4">
                <div className="flex items-center justify-between">
              <p className="text-xs sm:text-sm font-semibold text-white">{userLanguage === 'zh' ? '推荐率' : 'Recommendation rate'}</p>
                  {trendRangeLabel && (
                    <span className="text-[10px] sm:text-xs text-slate-500 hidden sm:inline">{trendRangeLabel}</span>
                  )}
                </div>
                <div className="mt-2 sm:mt-3 h-36 sm:h-40">
                  <Chart type="line" data={recommendationTrendData} options={recommendationTrendOptions as any} />
                </div>
              </div>

              <div className="rounded-xl sm:rounded-2xl border border-white/10 bg-slate-900/30 p-3 sm:p-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs sm:text-sm font-semibold text-white">Review volume</p>
                  <div className="flex items-center gap-2">
                    {trendRangeLabel && (
                      <span className="text-[10px] sm:text-xs text-slate-500 hidden sm:inline">{trendRangeLabel}</span>
                    )}
                    {selectedTrendWeek && (
                      <button
                        type="button"
                        onClick={() => setSelectedTrendWeek(null)}
                        className="text-xs text-sky-300 hover:text-sky-200 px-2 py-1 -mr-2"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                </div>
                <p className="mt-1 text-[10px] sm:text-xs text-slate-500">Tap a bar to view reviews from that week.</p>
                {selectedTrendWeek && (
                  <p className="mt-1 text-[10px] sm:text-xs text-sky-300">Selected {selectedTrendWeek.label}</p>
                )}
                <div className="mt-2 sm:mt-3 h-36 sm:h-40">
                  <Chart type="bar" data={volumeTrendData} options={volumeTrendOptions as any} />
                </div>
              </div>
            </div>
          ))}
        </Card>

        <FiveQuestionSummary insights={insights!} />

        <Card variant="glass" className={`p-6 ${mounted ? 'animate-fade-slide-up animation-delay-600' : 'opacity-0'}`}>
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-lg font-semibold text-white">观察到的评论群体</h4>
              <p className="mt-1 text-sm text-slate-400">Who is reviewing and what they care about</p>
            </div>
            <button type="button" onClick={() => toggleWidget('segmentation')} className="text-slate-500 hover:text-slate-300 transition-colors p-1" title={collapsedWidgets.has('segmentation') ? '展开' : '收起'}>
              <svg className={`w-4 h-4 transition-transform ${collapsedWidgets.has('segmentation') ? '-rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </button>
          </div>

          {!collapsedWidgets.has('segmentation') && (!playerSegments ? (
            <p className="mt-4 text-sm text-slate-500">Segmentation data is not available for this analysis.</p>
          ) : (
            <div className="mt-5 space-y-6">
              {/* Regional breakdown with top issues */}
              {playerSegments.language && playerSegments.language.languages?.length > 0 && (
                <div className="rounded-2xl border border-white/10 bg-slate-900/30 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wide">Regional Breakdown</h5>
                    <span className="text-xs text-slate-500">{playerSegments.language.total_languages} languages</span>
                  </div>
                  <div className="space-y-4">
                    {(() => {
                      const langs = playerSegments.language.languages.slice(0, 5);
                      // Calculate total reviews across all displayed languages for percentage
                      const totalReviews = langs.reduce((sum, l) => sum + l.count, 0);
                      return langs.map((lang) => {
                        // Bar width as percentage of total reviews (not relative to max)
                        const barWidth = totalReviews > 0 ? (lang.count / totalReviews) * 100 : 0;
                        const topIssues = lang.top_issues?.slice(0, 5) ?? [];
                        const langKey = lang.language.toLowerCase();
                        const langLabel = lang.language.charAt(0).toUpperCase() + lang.language.slice(1);
                        const isSelected = selectedSegment?.type === 'language' && selectedSegment?.key === langKey;
                        return (
                          <div key={lang.language} className="space-y-2">
                            <button
                              type="button"
                              onClick={() => setSelectedSegment(isSelected ? null : { type: 'language', key: langKey, label: langLabel, description: `${lang.count.toLocaleString()} reviews` })}
                              className={clsx(
                                "w-full flex items-center gap-3 py-1 px-1 -mx-1 rounded transition-colors",
                                isSelected ? "bg-indigo-500/20" : "hover:bg-white/5"
                              )}
                            >
                              <span className="w-20 text-xs text-slate-300 truncate text-left">
                                {langLabel}
                              </span>
                              <div className="flex-1 h-6 bg-slate-950/50 rounded relative overflow-hidden">
                                <div
                                  className="h-full rounded transition-all bg-indigo-500/40"
                                  style={{ width: `${barWidth}%` }}
                                />
                                <div className="absolute inset-0 flex items-center justify-between px-2">
                                  <span className="text-[10px] text-slate-400">
                                    {lang.count.toLocaleString()} ({Math.round(barWidth)}%)
                                  </span>
                                  <span
                                    className="text-xs font-medium"
                                    style={{ color: getRecommendationColor(lang.recommendation_rate) }}
                                  >
                                    {formatPercent(lang.recommendation_rate)}
                                  </span>
                                </div>
                              </div>
                            </button>
                            {topIssues.length > 0 && (
                              <div className="ml-[5.5rem] flex flex-wrap items-center gap-1.5">
                                <span className="text-[9px] text-slate-500 uppercase tracking-wide mr-1">重点问题：</span>
                                {topIssues.map((issue) => (
                                  <button
                                    key={issue.category}
                                    type="button"
                                    onClick={() => {
                                      openSubcategory(issue.category, 'issue', { key: langKey, label: langLabel });
                                    }}
                                    className={clsx(
                                      "inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border transition-colors",
                                      selectedSubcategory === issue.category && selectedSubcategoryLanguage?.key === langKey
                                        ? "bg-rose-500/20 border-rose-500/30"
                                        : "bg-slate-800/50 border-white/5 hover:bg-slate-700/50 hover:border-white/10"
                                    )}
                                  >
                                    <span className="text-rose-300">{toSubcategoryLabel(issue.category)}</span>
                                    <span className="text-slate-500">({issue.count})</span>
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>
              )}

              {/* Main segments grid - Compact cards */}
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {/* Experience Cohorts - Based on total games owned */}
                <div className="rounded-2xl border border-white/10 bg-slate-900/30 p-4">
                  <div className="flex items-center justify-between mb-1">
                    <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wide">Experience</h5>
                    <span className="text-[9px] text-slate-500 uppercase tracking-wide">Rec%</span>
                  </div>
                  <p className="text-[10px] text-slate-500 mb-3">Steam 库规模（可验证字段）</p>
                  <div className="space-y-2">
                    {!experienceDataAvailable ? <p className="text-xs text-slate-500">Unavailable — library size is not present in this review population.</p> : [
                      { label: "Library <10", subLabel: "games owned", key: "newcomers", data: playerSegments.experience_level?.newcomers },
                      { label: "Library 10–49", subLabel: "games owned", key: "casual", data: playerSegments.experience_level?.casual },
                      { label: "Library 50–149", subLabel: "games owned", key: "experienced", data: playerSegments.experience_level?.experienced },
                      { label: "Library 150+", subLabel: "games owned", key: "veterans", data: playerSegments.experience_level?.veterans },
                    ].map((row) => {
                      const count = row.data?.count ?? 0;
                      const rec = row.data?.recommendation_rate ?? 0;
                      const total = (playerSegments.experience_level?.newcomers?.count ?? 0) +
                                   (playerSegments.experience_level?.casual?.count ?? 0) +
                                   (playerSegments.experience_level?.experienced?.count ?? 0) +
                                   (playerSegments.experience_level?.veterans?.count ?? 0);
                      const share = total > 0 ? Math.round((count / total) * 100) : 0;
                      const isSelected = selectedSegment?.type === 'experience' && selectedSegment?.key === row.key;
                      return (
                        <button
                          key={row.label}
                          type="button"
                          onClick={() => setSelectedSegment(isSelected ? null : { type: 'experience', key: row.key, label: row.label, description: row.subLabel })}
                          className={clsx(
                            "w-full flex items-center justify-between py-1 px-1 -mx-1 rounded transition-colors",
                            isSelected ? "bg-indigo-500/20" : "hover:bg-white/5"
                          )}
                        >
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                              <div className="h-full bg-indigo-500/70 rounded-full" style={{ width: `${share}%` }} />
                            </div>
                            <span className="text-xs text-slate-300">{row.label}</span>
                            <span className="text-[10px] text-slate-500">{row.subLabel}</span>
                          </div>
                          <span
                            className="text-xs"
                            style={{ color: getRecommendationColor(rec) }}
                          >
                            {formatPercent(rec)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Purchase Type */}
                <div className="rounded-2xl border border-white/10 bg-slate-900/30 p-4">
                  <div className="flex items-center justify-between mb-1">
                    <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wide">Purchase</h5>
                    <span className="text-[9px] text-slate-500 uppercase tracking-wide">Rec%</span>
                  </div>
                  <p className="text-[10px] text-slate-500 mb-3">获取方式（当前评论未提供可验证字段）</p>
                  <div className="space-y-2">
                    {!purchaseDataAvailable ? <p className="text-xs text-slate-500">Unavailable — unknown is not treated as 0%.</p> : [
                      { label: "Steam", key: "steam_buyers", desc: "Steam purchase", data: playerSegments.purchase_type?.steam_buyers },
                      { label: "Key", key: "key_users", desc: "Activated key", data: playerSegments.purchase_type?.key_users },
                      { label: "Free", key: "free_users", desc: "Received free", data: playerSegments.purchase_type?.free_users },
                    ].map((row) => {
                      const count = row.data?.count ?? 0;
                      const rec = row.data?.recommendation_rate ?? 0;
                      const total = (playerSegments.purchase_type?.steam_buyers?.count ?? 0) +
                                   (playerSegments.purchase_type?.key_users?.count ?? 0) +
                                   (playerSegments.purchase_type?.free_users?.count ?? 0);
                      const share = total > 0 ? Math.round((count / total) * 100) : 0;
                      const isSelected = selectedSegment?.type === 'purchase' && selectedSegment?.key === row.key;
                      return (
                        <button
                          key={row.label}
                          type="button"
                          onClick={() => setSelectedSegment(isSelected ? null : { type: 'purchase', key: row.key, label: row.label, description: row.desc })}
                          className={clsx(
                            "w-full flex items-center justify-between py-1 px-1 -mx-1 rounded transition-colors",
                            isSelected ? "bg-sky-500/20" : "hover:bg-white/5"
                          )}
                        >
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                              <div className="h-full bg-sky-500/70 rounded-full" style={{ width: `${share}%` }} />
                            </div>
                            <span className="text-xs text-slate-300">{row.label}</span>
                            <span className="text-[10px] text-slate-500">{share}%</span>
                          </div>
                          <span
                            className="text-xs"
                            style={{ color: getRecommendationColor(rec) }}
                          >
                            {formatPercent(rec)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Activity Status - Based on recent play activity */}
                <div className="rounded-2xl border border-white/10 bg-slate-900/30 p-4">
                  <div className="flex items-center justify-between mb-1">
                    <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wide">Activity</h5>
                    <span className="text-[9px] text-slate-500 uppercase tracking-wide">Rec%</span>
                  </div>
                  <p className="text-[10px] text-slate-500 mb-3">Played in last 2 weeks（可验证字段）</p>
                  <div className="space-y-2">
                    {!activityDataAvailable ? <p className="text-xs text-slate-500">Unavailable — missing recent-playtime data; no active-rate fallback.</p> : [
                      { label: "Active", subLabel: "recent", key: "currently_active", desc: "Played recently", data: playerSegments.activity_status?.currently_active, color: "bg-emerald-500/70", selectedColor: "bg-emerald-500/20" },
                      { label: "Stopped", subLabel: "not recent", key: "recently_stopped", desc: "Stopped playing", data: playerSegments.activity_status?.recently_stopped, color: "bg-amber-500/70", selectedColor: "bg-amber-500/20" },
                      { label: "Inactive", subLabel: "never", key: "inactive", desc: "Never played", data: playerSegments.activity_status?.inactive, color: "bg-slate-500/70", selectedColor: "bg-slate-500/20" },
                    ].map((row) => {
                      const count = row.data?.count ?? 0;
                      const rec = row.data?.recommendation_rate ?? 0;
                      const total = (playerSegments.activity_status?.currently_active?.count ?? 0) +
                                   (playerSegments.activity_status?.recently_stopped?.count ?? 0) +
                                   (playerSegments.activity_status?.inactive?.count ?? 0);
                      const share = total > 0 ? Math.round((count / total) * 100) : 0;
                      const isSelected = selectedSegment?.type === 'activity' && selectedSegment?.key === row.key;
                      return (
                        <button
                          key={row.label}
                          type="button"
                          onClick={() => setSelectedSegment(isSelected ? null : { type: 'activity', key: row.key, label: row.label, description: row.desc })}
                          className={clsx(
                            "w-full flex items-center justify-between py-1 px-1 -mx-1 rounded transition-colors",
                            isSelected ? row.selectedColor : "hover:bg-white/5"
                          )}
                        >
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${row.color}`} style={{ width: `${share}%` }} />
                            </div>
                            <span className="text-xs text-slate-300">{row.label}</span>
                            <span className="text-[10px] text-slate-500">{share}%</span>
                          </div>
                          <span
                            className="text-xs"
                            style={{ color: getRecommendationColor(rec) }}
                          >
                            {formatPercent(rec)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Engagement - Based on playtime for this game */}
                <div className="rounded-2xl border border-white/10 bg-slate-900/30 p-4">
                  <div className="flex items-center justify-between mb-1">
                    <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wide">Engagement</h5>
                    <span className="text-[9px] text-slate-500 uppercase tracking-wide">Rec%</span>
                  </div>
                  <p className="text-[10px] text-slate-500 mb-3">Playtime in this game</p>
                  <div className="space-y-2">
                    {[
                      { label: "Low", subLabel: "<2h", key: "low_engagement", desc: "Under 2 hours played", data: playerSegments.engagement_topics?.low_engagement },
                      { label: "Medium", subLabel: "2-20h", key: "moderately_engaged", desc: "2-20 hours played", data: playerSegments.engagement_topics?.moderately_engaged },
                      { label: "High", subLabel: "20h+", key: "highly_engaged", desc: "20+ hours played", data: playerSegments.engagement_topics?.highly_engaged },
                    ].map((row) => {
                      const count = row.data?.count ?? 0;
                      const rec = row.data?.recommendation_rate ?? 0;
                      const total = (playerSegments.engagement_topics?.highly_engaged?.count ?? 0) +
                                   (playerSegments.engagement_topics?.moderately_engaged?.count ?? 0) +
                                   (playerSegments.engagement_topics?.low_engagement?.count ?? 0);
                      const share = total > 0 ? Math.round((count / total) * 100) : 0;
                      const isSelected = selectedSegment?.type === 'engagement' && selectedSegment?.key === row.key;
                      return (
                        <button
                          key={row.label}
                          type="button"
                          onClick={() => setSelectedSegment(isSelected ? null : { type: 'engagement', key: row.key, label: row.label, description: row.desc })}
                          className={clsx(
                            "w-full flex items-center justify-between py-1 px-1 -mx-1 rounded transition-colors",
                            isSelected ? "bg-teal-500/20" : "hover:bg-white/5"
                          )}
                        >
                          <div className="flex items-center gap-2">
                            <div className="w-8 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                              <div className="h-full bg-teal-500/70 rounded-full" style={{ width: `${share}%` }} />
                            </div>
                            <span className="text-xs text-slate-300">{row.label}</span>
                            <span className="text-[10px] text-slate-500">{row.subLabel}</span>
                          </div>
                          <span
                            className="text-xs"
                            style={{ color: getRecommendationColor(rec) }}
                          >
                            {formatPercent(rec)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </Card>

        {/* Recent Updates (News) */}
        {selectedGame && (
          <Card variant="glass" className={`p-4 sm:p-6 ${mounted ? 'animate-fade-slide-up animation-delay-700' : 'opacity-0'}`}>
            <div className="flex items-center justify-end mb-1">
              <button type="button" onClick={() => toggleWidget('recentUpdates')} className="text-slate-500 hover:text-slate-300 transition-colors p-1" title={collapsedWidgets.has('recentUpdates') ? 'Expand' : 'Collapse'}>
                <svg className={`w-4 h-4 transition-transform ${collapsedWidgets.has('recentUpdates') ? '-rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
              </button>
            </div>
            {!collapsedWidgets.has('recentUpdates') && (
              <NewsWithSummary appId={selectedGame.appid} count={5} />
            )}
          </Card>
        )}
      </div>

      {selectedSubcategory ? (
        <Portal>
          <div
            className="fixed inset-0 z-[9999] bg-black/60 backdrop-blur-md overflow-y-auto animate-modal-overlay"
            onClick={clearSelectedSubcategory}
            style={{ WebkitBackdropFilter: 'blur(12px)' }}
          >
            <div className="min-h-screen flex items-start sm:items-center justify-center p-2 sm:p-4">
              <div
                className="w-full max-w-4xl rounded-xl sm:rounded-2xl border border-white/20 bg-slate-900 p-4 sm:p-6 shadow-2xl my-2 sm:my-8 animate-modal-content"
                onClick={(event) => event.stopPropagation()}
              >
            <div className="flex flex-col sm:flex-row sm:flex-wrap items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="text-base sm:text-lg font-semibold text-white">{selectedSubcategoryLabel}</h3>
                <p className="mt-1 text-xs sm:text-sm text-slate-400">
                  {selectedMainLabel} · {selectedReviews.length.toLocaleString()} 条评论
                  {selectedSubcategoryLanguageLabel ? ` · ${selectedSubcategoryLanguageLabel} only` : ""}
                </p>
                {filterScopeLabel && (
                  <p className="mt-1 text-[11px] sm:text-xs text-sky-400 line-clamp-2">
                    筛选条件：{filterScopeLabel}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <button
                  onClick={handleSummarize}
                  disabled={summaryLoading || selectedReviews.length === 0}
                  className="flex-1 sm:flex-none text-xs sm:text-sm px-3 py-2.5 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
                >
                  {summaryLoading ? (
                    <>
                      <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      正在生成摘要…
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      {subcategorySummary ? "刷新" : "AI 摘要"}
                    </>
                  )}
                </button>
                <Button variant="secondary" onClick={clearSelectedSubcategory} className="flex-1 sm:flex-none text-xs sm:text-sm">
                  {t('common.close')}
                </Button>
              </div>
            </div>

            {/* Summary Section */}
            {summaryError && (
              <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4">
                <p className="text-sm text-rose-400">{summaryError}</p>
              </div>
            )}

            {subcategorySummary && (
              <div className="mt-4 space-y-4 rounded-xl border border-sky-500/30 bg-sky-500/5 p-4">
                <div>
                  <h4 className="text-xs uppercase tracking-wider text-sky-400 mb-2">摘要</h4>
                  <p className="text-sm text-slate-200 leading-relaxed">{subcategorySummary.summary}</p>
                </div>

                <div className={selectedSubcategoryType === 'general' ? "grid gap-4 sm:grid-cols-2" : "space-y-4"}>
                  {subcategorySummary.pros.length > 0 && (
                    <div>
                      <h4 className="text-xs uppercase tracking-wider text-emerald-400 mb-2 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        {selectedSubcategoryType === 'request' ? '功能需求' : '优点'}
                      </h4>
                      <ul className="space-y-1.5">
                        {subcategorySummary.pros.map((pro, idx) => (
                          <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                            <span className="text-emerald-400 mt-1">
                              {selectedSubcategoryType === 'request' ? '→' : '+'}
                            </span>
                            <span>{pro}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {subcategorySummary.cons.length > 0 && (
                    <div>
                      <h4 className="text-xs uppercase tracking-wider text-rose-400 mb-2 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                        {selectedSubcategoryType === 'issue' ? '问题' : '缺点'}
                      </h4>
                      <ul className="space-y-1.5">
                        {subcategorySummary.cons.map((con, idx) => (
                          <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                            <span className="text-rose-400 mt-1">
                              {selectedSubcategoryType === 'issue' ? '!' : '−'}
                            </span>
                            <span>{con}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                <p className="text-xs text-slate-500 pt-2 border-t border-white/10">
                  基于 {Math.min(selectedReviews.length, 50)} 条评论
                </p>
              </div>
            )}
            {selectedReviews.length === 0 ? (
              <p className="mt-4 text-sm text-slate-500">当前范围没有匹配评论；这不等同于证据查询失败。</p>
            ) : (
              <div className="mt-4 max-h-[32rem] space-y-3 overflow-auto pr-2">
                {selectedReviews.map((review, idx) => {
                  const reviewKey = String(review.review_id ?? idx);
                  const text = review.review ?? "";
                  const evidence = selectedSubcategory
                    ? (review.llm_subcategory_evidence?.[selectedSubcategory] ?? [])
                    : [];
                  const createdAt = review.created_at ? new Date(review.created_at) : null;
                  const createdLabel = createdAt && !Number.isNaN(createdAt.getTime())
                    ? createdAt.toLocaleDateString()
                    : "Date unknown";
                  const shouldClamp = text.length > 240 || text.split("\n").length > 3;
                  const isExpanded = expandedReviews.has(reviewKey);
                  // Translation check
                  const reviewLangCode = STEAM_TO_APP_LANGUAGE[review.language?.toLowerCase() || ''] || review.language?.toLowerCase();
                  const needsTranslation = reviewLangCode !== userLanguage && review.language;
                  const translationState = translations.get(reviewKey);
                  const isTranslating = translationState?.loading ?? false;
                  const translatedText = translationState?.text ?? null;
                  const showTranslation = translationState?.show ?? false;

                  const handleTranslate = async () => {
                    if (translatedText) {
                      // Toggle visibility if already translated
                      setTranslations((prev) => {
                        const next = new Map(prev);
                        const current = next.get(reviewKey);
                        if (current) {
                          next.set(reviewKey, { ...current, show: !current.show });
                        }
                        return next;
                      });
                      return;
                    }
                    // Start translation
                    setTranslations((prev) => {
                      const next = new Map(prev);
                      next.set(reviewKey, { text: null, loading: true, show: false });
                      return next;
                    });
                    try {
                      const result = await translateText({
                        text,
                        target_language: userLanguage,
                      });
                      setTranslations((prev) => {
                        const next = new Map(prev);
                        next.set(reviewKey, { text: result.translated_text, loading: false, show: true });
                        return next;
                      });
                    } catch (error) {
                      console.error('Translation failed:', error);
                      setTranslations((prev) => {
                        const next = new Map(prev);
                        next.set(reviewKey, { text: null, loading: false, show: false });
                        return next;
                      });
                    }
                  };

                  return (
                    <div
                      key={reviewKey}
                      className="rounded-xl border border-white/10 bg-white/5 p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                        <span>Review ID {review.review_id ?? "—"}</span>
                        <div className="flex flex-wrap items-center gap-3">
                          <span>{createdLabel}</span>
                          <span>{review.votes_up ?? 0} helpful</span>
                          {evidence.length > 0 && (
                            <span className="rounded-full bg-yellow-400/20 px-2 py-0.5 text-yellow-300">
                              {evidence.length} evidence
                            </span>
                          )}
                        </div>
                      </div>
                      {/* Translation controls */}
                      {needsTranslation && (
                        <div className="mt-2 flex items-center justify-between border-b border-white/10 pb-2">
                          <span className="text-[10px] text-slate-500">
                            Original: {review.language}
                          </span>
                          <button
                            type="button"
                            onClick={handleTranslate}
                            disabled={isTranslating}
                            className="flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-1 text-[10px] text-sky-300 transition hover:bg-sky-500/20 disabled:opacity-50"
                          >
                            {isTranslating ? (
                              <>
                                <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                </svg>
                                Translating...
                              </>
                            ) : translatedText ? (
                              <>
                                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                                </svg>
                                {showTranslation ? 'Original' : 'Translated'}
                              </>
                            ) : (
                              <>
                                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                                </svg>
                                Translate
                              </>
                            )}
                          </button>
                        </div>
                      )}
                      {/* Translated text */}
                      {showTranslation && translatedText && (
                        <div className="mt-2 rounded-lg border border-sky-500/20 bg-sky-500/5 p-2">
                          <p className="whitespace-pre-line text-sm text-slate-200">
                            {translatedText}
                          </p>
                        </div>
                      )}
                      <p
                        className="mt-2 whitespace-pre-line text-sm text-slate-100"
                        style={
                          !isExpanded && shouldClamp
                            ? {
                                display: "-webkit-box",
                                WebkitLineClamp: 3,
                                WebkitBoxOrient: "vertical",
                                overflow: "hidden",
                              }
                            : undefined
                        }
                      >
                        {highlightEvidence(text, evidence)}
                      </p>
                      <div className="mt-3 flex items-center justify-between gap-3 text-xs">
                        <span
                          className={`rounded-full px-2 py-1 ${
                            isRecommended(review.voted_up) ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
                          }`}
                        >
                          {isRecommended(review.voted_up) ? "Recommended" : "Not recommended"}
                        </span>
                        {shouldClamp ? (
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedReviews((prev) => {
                                const next = new Set(prev);
                                if (next.has(reviewKey)) {
                                  next.delete(reviewKey);
                                } else {
                                  next.add(reviewKey);
                                }
                                return next;
                              })
                            }
                            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-white/80 hover:border-white/20 hover:bg-white/10"
                            aria-label={isExpanded ? "Read less" : "Read more"}
                          >
                            {isExpanded ? "Read less" : "Read more"}
                          </button>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
              </div>
            </div>
          </div>
        </Portal>
      ) : null}

      {selectedTrendWeek ? (
        <Portal>
          <div
            className="fixed inset-0 z-[9998] bg-black/60 backdrop-blur-md overflow-y-auto animate-modal-overlay"
            onClick={() => setSelectedTrendWeek(null)}
            style={{ WebkitBackdropFilter: 'blur(12px)' }}
          >
            <div className="min-h-screen flex items-start sm:items-center justify-center p-2 sm:p-4">
              <div
                className="w-full max-w-4xl rounded-xl sm:rounded-2xl border border-white/20 bg-slate-900 p-4 sm:p-6 shadow-2xl my-2 sm:my-8 animate-modal-content"
                onClick={(event) => event.stopPropagation()}
              >
              <div className="flex flex-col sm:flex-row sm:flex-wrap items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h3 className="text-base sm:text-lg font-semibold text-white">{formatTrendLabel(selectedTrendWeek.start)} 周</h3>
                  <p className="mt-1 text-xs sm:text-sm text-slate-400">
                    {selectedTrendWeek.label} · {selectedWeekReviews.length.toLocaleString()} 条评论
                  </p>
                  {filterScopeLabel && (
                    <p className="mt-1 text-[11px] sm:text-xs text-sky-400 line-clamp-2">
                      筛选条件：{filterScopeLabel}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <button
                    onClick={handleSummarizeTrendWeek}
                    disabled={trendWeekSummaryLoading || selectedWeekReviews.length === 0}
                    className="flex-1 sm:flex-none text-xs sm:text-sm px-3 py-2.5 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
                  >
                    {trendWeekSummaryLoading ? (
                      <>
                        <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        正在生成摘要…
                      </>
                    ) : (
                      <>
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        {trendWeekSummary ? "刷新" : "AI 摘要"}
                      </>
                    )}
                  </button>
                  <Button variant="secondary" onClick={() => setSelectedTrendWeek(null)} className="flex-1 sm:flex-none text-xs sm:text-sm">
                    {t('common.close')}
                  </Button>
                </div>
              </div>

              {trendWeekSummaryError && (
                <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4">
                  <p className="text-sm text-rose-400">{trendWeekSummaryError}</p>
                </div>
              )}

              {trendWeekSummary && (
                <div className="mt-4 space-y-4 rounded-xl border border-sky-500/30 bg-sky-500/5 p-4">
                  <div>
                    <h4 className="text-xs uppercase tracking-wider text-sky-400 mb-2">摘要</h4>
                    <p className="text-sm text-slate-200 leading-relaxed">{trendWeekSummary.summary}</p>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    {trendWeekSummary.key_points.length > 0 && (
                      <div>
                        <h4 className="text-xs uppercase tracking-wider text-white/80 mb-2 flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 bg-white/70" />
                          关键发现
                        </h4>
                        <ul className="space-y-1.5">
                          {trendWeekSummary.key_points.map((item, idx) => (
                            <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                              <span className="text-sky-300 mt-1">•</span>
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {trendWeekSummary.actions.length > 0 && (
                      <div>
                        <h4 className="text-xs uppercase tracking-wider text-emerald-400 mb-2 flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 bg-emerald-400" />
                          建议行动
                        </h4>
                        <ul className="space-y-1.5">
                          {trendWeekSummary.actions.map((item, idx) => (
                            <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                              <span className="text-emerald-400 mt-1">→</span>
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  <p className="text-xs text-slate-500 pt-2 border-t border-white/10">
                    基于 {Math.min(selectedWeekReviews.length, 50)} 条评论
                  </p>
                </div>
              )}

              {selectedWeekReviews.length === 0 ? (
                    <p className="mt-4 text-sm text-slate-500">本周没有找到评论。</p>
              ) : (
                <div className="mt-4 max-h-[32rem] space-y-3 overflow-auto pr-2">
                  {selectedWeekReviews.map((review, idx) => {
                    const reviewKey = String(review.review_id ?? idx);
                    const text = review.review ?? "";
                    const createdAt = review.created_at ? new Date(review.created_at) : null;
                    const createdLabel = createdAt && !Number.isNaN(createdAt.getTime())
                      ? createdAt.toLocaleDateString()
                      : "Date unknown";
                    const shouldClamp = text.length > 240 || text.split("\n").length > 3;
                    const isExpanded = expandedReviews.has(reviewKey);
                    const reviewLangCode = STEAM_TO_APP_LANGUAGE[review.language?.toLowerCase() || ''] || review.language?.toLowerCase();
                    const needsTranslation = reviewLangCode !== userLanguage && review.language;
                    const translationState = translations.get(reviewKey);
                    const isTranslating = translationState?.loading ?? false;
                    const translatedText = translationState?.text ?? null;
                    const showTranslation = translationState?.show ?? false;

                    const handleTranslate = async () => {
                      if (translatedText) {
                        setTranslations((prev) => {
                          const next = new Map(prev);
                          const current = next.get(reviewKey);
                          if (current) {
                            next.set(reviewKey, { ...current, show: !current.show });
                          }
                          return next;
                        });
                        return;
                      }
                      setTranslations((prev) => {
                        const next = new Map(prev);
                        next.set(reviewKey, { text: null, loading: true, show: false });
                        return next;
                      });
                      try {
                        const result = await translateText({
                          text,
                          target_language: userLanguage,
                        });
                        setTranslations((prev) => {
                          const next = new Map(prev);
                          next.set(reviewKey, { text: result.translated_text, loading: false, show: true });
                          return next;
                        });
                      } catch (error) {
                        console.error("Translation error:", error);
                        setTranslations((prev) => {
                          const next = new Map(prev);
                          next.delete(reviewKey);
                          return next;
                        });
                      }
                    };

                    return (
                      <div
                        key={reviewKey}
                        className="rounded-xl border border-white/10 bg-white/5 p-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs text-slate-500">{createdLabel}</p>
                            <p className="mt-1 text-sm text-slate-200">{review.language}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            {needsTranslation && (
                              <button
                                type="button"
                                onClick={handleTranslate}
                                disabled={isTranslating}
                                className="flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-1 text-[10px] text-sky-300 transition hover:bg-sky-500/20 disabled:opacity-50"
                              >
                                {isTranslating ? (
                                  <>
                                    <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                    </svg>
                                    Translating...
                                  </>
                                ) : translatedText ? (
                                  <>
                                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                                    </svg>
                                    {showTranslation ? 'Original' : 'Translated'}
                                  </>
                                ) : (
                                  <>
                                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                                    </svg>
                                    Translate
                                  </>
                                )}
                              </button>
                            )}
                          </div>
                        </div>

                        {showTranslation && translatedText && (
                          <div className="mt-2 rounded-lg border border-sky-500/20 bg-sky-500/5 p-2">
                            <p className="whitespace-pre-line text-sm text-slate-200">
                              {translatedText}
                            </p>
                          </div>
                        )}

                        <p
                          className="mt-2 whitespace-pre-line text-sm text-slate-100"
                          style={
                            !isExpanded && shouldClamp
                              ? {
                                  display: "-webkit-box",
                                  WebkitLineClamp: 3,
                                  WebkitBoxOrient: "vertical",
                                  overflow: "hidden",
                                }
                              : undefined
                          }
                        >
                          {text}
                        </p>
                        <div className="mt-3 flex items-center justify-between gap-3 text-xs">
                          <span
                            className={`rounded-full px-2 py-1 ${
                              isRecommended(review.voted_up) ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
                            }`}
                          >
                            {isRecommended(review.voted_up) ? "Recommended" : "Not recommended"}
                          </span>
                          {shouldClamp ? (
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedReviews((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(reviewKey)) {
                                    next.delete(reviewKey);
                                  } else {
                                    next.add(reviewKey);
                                  }
                                  return next;
                                })
                              }
                              className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-white/80 hover:border-white/20 hover:bg-white/10"
                              aria-label={isExpanded ? "Read less" : "Read more"}
                            >
                              {isExpanded ? "Read less" : "Read more"}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              </div>
            </div>
          </div>
        </Portal>
      ) : null}

      {selectedSegment ? (
        <Portal>
          <div
            className="fixed inset-0 z-[9997] bg-black/60 backdrop-blur-md overflow-y-auto animate-modal-overlay"
            onClick={() => setSelectedSegment(null)}
            style={{ WebkitBackdropFilter: 'blur(12px)' }}
          >
            <div className="min-h-screen flex items-start sm:items-center justify-center p-2 sm:p-4">
              <div
                className="w-full max-w-4xl rounded-xl sm:rounded-2xl border border-white/20 bg-slate-900 p-4 sm:p-6 shadow-2xl my-2 sm:my-8 animate-modal-content"
                onClick={(event) => event.stopPropagation()}
              >
              <div className="flex flex-col sm:flex-row sm:flex-wrap items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h3 className="text-base sm:text-lg font-semibold text-white">
                    {selectedSegment.label} {selectedSegment.type === 'experience' ? 'Players' : selectedSegment.type === 'purchase' ? 'Users' : selectedSegment.type === 'activity' ? 'Players' : 'Players'}
                  </h3>
                  <p className="mt-1 text-xs sm:text-sm text-slate-400">
                    {selectedSegment.description} · {selectedSegmentReviews.length.toLocaleString()} 条评论
                  </p>
                  {filterScopeLabel && (
                    <p className="mt-1 text-[11px] sm:text-xs text-sky-400 line-clamp-2">
                      筛选条件：{filterScopeLabel}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <button
                    onClick={handleSummarizeSegment}
                    disabled={segmentSummaryLoading || selectedSegmentReviews.length === 0}
                    className="flex-1 sm:flex-none text-xs sm:text-sm px-3 py-2.5 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
                  >
                    {segmentSummaryLoading ? (
                      <>
                        <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        正在生成摘要…
                      </>
                    ) : (
                      <>
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        {segmentSummary ? "刷新" : "AI 摘要"}
                      </>
                    )}
                  </button>
                  <Button variant="secondary" onClick={() => setSelectedSegment(null)} className="flex-1 sm:flex-none text-xs sm:text-sm">
                    {t('common.close')}
                  </Button>
                </div>
              </div>

              {segmentSummaryError && (
                <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4">
                  <p className="text-sm text-rose-400">{segmentSummaryError}</p>
                </div>
              )}

              {segmentSummary && (
                <div className="mt-4 space-y-4 rounded-xl border border-sky-500/30 bg-sky-500/5 p-4">
                  <div>
                    <h4 className="text-xs uppercase tracking-wider text-sky-400 mb-2">摘要</h4>
                    <p className="text-sm text-slate-200 leading-relaxed">{segmentSummary.summary}</p>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    {segmentSummary.key_points.length > 0 && (
                      <div>
                        <h4 className="text-xs uppercase tracking-wider text-white/80 mb-2 flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 bg-white/70" />
                          关键发现
                        </h4>
                        <ul className="space-y-1.5">
                          {segmentSummary.key_points.map((item, idx) => (
                            <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                              <span className="text-sky-300 mt-1">•</span>
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {segmentSummary.actions.length > 0 && (
                      <div>
                        <h4 className="text-xs uppercase tracking-wider text-emerald-400 mb-2 flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 bg-emerald-400" />
                          建议行动
                        </h4>
                        <ul className="space-y-1.5">
                          {segmentSummary.actions.map((item, idx) => (
                            <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                              <span className="text-emerald-400 mt-1">→</span>
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  <p className="text-xs text-slate-500 pt-2 border-t border-white/10">
                    基于 {Math.min(selectedSegmentReviews.length, 50)} 条评论
                  </p>
                </div>
              )}

              {selectedSegmentReviews.length === 0 ? (
                <p className="mt-4 text-sm text-slate-500">No reviews found for this segment.</p>
              ) : (
                <div className="mt-4 max-h-[32rem] space-y-3 overflow-auto pr-2">
                  {selectedSegmentReviews.map((review, idx) => {
                    const reviewKey = `seg-${String(review.review_id ?? idx)}`;
                    const text = review.review ?? "";
                    const createdAt = review.created_at ? new Date(review.created_at) : null;
                    const createdLabel = createdAt && !Number.isNaN(createdAt.getTime())
                      ? createdAt.toLocaleDateString()
                      : "Date unknown";
                    const shouldClamp = text.length > 240 || text.split("\n").length > 3;
                    const isExpanded = expandedReviews.has(reviewKey);
                    const reviewLangCode = STEAM_TO_APP_LANGUAGE[review.language?.toLowerCase() || ''] || review.language?.toLowerCase();
                    const needsTranslation = reviewLangCode !== userLanguage && review.language;
                    const translationState = translations.get(reviewKey);
                    const isTranslating = translationState?.loading ?? false;
                    const translatedText = translationState?.text ?? null;
                    const showTranslation = translationState?.show ?? false;

                    const handleTranslate = async () => {
                      if (translatedText) {
                        setTranslations((prev) => {
                          const next = new Map(prev);
                          const current = next.get(reviewKey);
                          if (current) {
                            next.set(reviewKey, { ...current, show: !current.show });
                          }
                          return next;
                        });
                        return;
                      }
                      setTranslations((prev) => {
                        const next = new Map(prev);
                        next.set(reviewKey, { text: null, loading: true, show: false });
                        return next;
                      });
                      try {
                        const result = await translateText({
                          text,
                          target_language: userLanguage,
                        });
                        setTranslations((prev) => {
                          const next = new Map(prev);
                          next.set(reviewKey, { text: result.translated_text, loading: false, show: true });
                          return next;
                        });
                      } catch (error) {
                        console.error('Translation failed:', error);
                        setTranslations((prev) => {
                          const next = new Map(prev);
                          next.set(reviewKey, { text: null, loading: false, show: false });
                          return next;
                        });
                      }
                    };

                    return (
                      <div
                        key={reviewKey}
                        className="rounded-xl border border-white/10 bg-white/5 p-4"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                          <span>Review ID {review.review_id ?? "—"}</span>
                          <div className="flex flex-wrap items-center gap-3">
                            <span>{createdLabel}</span>
                            <span>{review.votes_up ?? 0} helpful</span>
                          </div>
                        </div>
                        {needsTranslation && (
                          <div className="mt-2 flex items-center justify-between border-b border-white/10 pb-2">
                            <span className="text-[10px] text-slate-500">
                              Original: {review.language}
                            </span>
                            <button
                              type="button"
                              onClick={handleTranslate}
                              disabled={isTranslating}
                              className="flex items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-1 text-[10px] text-sky-300 transition hover:bg-sky-500/20 disabled:opacity-50"
                            >
                              {isTranslating ? (
                                <>
                                  <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                  </svg>
                                  Translating...
                                </>
                              ) : translatedText ? (
                                <>
                                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                                  </svg>
                                  {showTranslation ? 'Original' : 'Translated'}
                                </>
                              ) : (
                                <>
                                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                                  </svg>
                                  Translate
                                </>
                              )}
                            </button>
                          </div>
                        )}
                        {showTranslation && translatedText && (
                          <div className="mt-2 rounded-lg border border-sky-500/20 bg-sky-500/5 p-2">
                            <p className="whitespace-pre-line text-sm text-slate-200">
                              {translatedText}
                            </p>
                          </div>
                        )}
                        <p
                          className="mt-2 whitespace-pre-line text-sm text-slate-100"
                          style={
                            !isExpanded && shouldClamp
                              ? {
                                  display: "-webkit-box",
                                  WebkitLineClamp: 3,
                                  WebkitBoxOrient: "vertical",
                                  overflow: "hidden",
                                }
                              : undefined
                          }
                        >
                          {text}
                        </p>
                        <div className="mt-3 flex items-center justify-between gap-3 text-xs">
                          <span
                            className={`rounded-full px-2 py-1 ${
                              isRecommended(review.voted_up) ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
                            }`}
                          >
                            {isRecommended(review.voted_up) ? "Recommended" : "Not recommended"}
                          </span>
                          {shouldClamp ? (
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedReviews((prev) => {
                                  const next = new Set(prev);
                                  if (next.has(reviewKey)) {
                                    next.delete(reviewKey);
                                  } else {
                                    next.add(reviewKey);
                                  }
                                  return next;
                                })
                              }
                              className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-white/80 hover:border-white/20 hover:bg-white/10"
                              aria-label={isExpanded ? "Read less" : "Read more"}
                            >
                              {isExpanded ? "Read less" : "Read more"}
                            </button>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              </div>
            </div>
          </div>
        </Portal>
      ) : null}

      {topIssuesModalOpen ? (
        <Portal>
          <div
            className="fixed inset-0 z-[9996] bg-black/60 backdrop-blur-md overflow-y-auto animate-modal-overlay"
            onClick={closeTopIssuesModal}
            style={{ WebkitBackdropFilter: "blur(12px)" }}
          >
            <div className="min-h-screen flex items-start sm:items-center justify-center p-2 sm:p-4">
              <div
                className="w-full max-w-4xl rounded-xl sm:rounded-2xl border border-white/20 bg-slate-900 p-4 sm:p-6 shadow-2xl my-2 sm:my-8 animate-modal-content"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="flex flex-col sm:flex-row sm:flex-wrap items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-base sm:text-lg font-semibold text-white">重点问题摘要</h3>
                    <p className="mt-1 text-xs sm:text-sm text-slate-400">
                      主要问题的跨分类综合分析
                    </p>
                    {filterScopeLabel && (
                      <p className="mt-1 text-[11px] sm:text-xs text-sky-400 line-clamp-2">
                        筛选条件：{filterScopeLabel}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    <button
                      onClick={handleSummarizeTopIssues}
                      disabled={topIssuesSummaryLoading}
                      className="flex-1 sm:flex-none text-xs sm:text-sm px-3 py-2.5 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
                    >
                      {topIssuesSummaryLoading ? (
                        <>
                          <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          正在生成摘要…
                        </>
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                          </svg>
                          {topIssuesSummary ? "刷新" : "AI 摘要"}
                        </>
                      )}
                    </button>
                    <Button variant="secondary" onClick={closeTopIssuesModal} className="flex-1 sm:flex-none text-xs sm:text-sm">
                      {t('common.close')}
                    </Button>
                  </div>
                </div>

                {topIssuesSummaryError && (
                  <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4">
                    <p className="text-sm text-rose-400">{topIssuesSummaryError}</p>
                  </div>
                )}

                {topIssuesSummary ? (
                  <div className="mt-4 space-y-4 rounded-xl border border-sky-500/30 bg-sky-500/5 p-4">
                    <div>
                      <h4 className="text-xs tracking-wider text-sky-400 mb-2">摘要</h4>
                      <p className="text-sm text-slate-200 leading-relaxed">{topIssuesSummary.summary}</p>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      {topIssuesSummary.key_points.length > 0 && (
                        <div>
                          <h4 className="text-xs uppercase tracking-wider text-white/80 mb-2 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 bg-white/70" />
                            关键发现
                          </h4>
                          <ul className="space-y-1.5">
                            {topIssuesSummary.key_points.map((item, idx) => (
                              <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                                <span className="text-sky-300 mt-1">•</span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {topIssuesSummary.actions.length > 0 && (
                        <div>
                          <h4 className="text-xs uppercase tracking-wider text-emerald-400 mb-2 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 bg-emerald-400" />
                            建议行动
                          </h4>
                          <ul className="space-y-1.5">
                            {topIssuesSummary.actions.map((item, idx) => (
                              <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                                <span className="text-emerald-400 mt-1">&rarr;</span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    <p className="text-xs text-slate-500 pt-2 border-t border-white/10">
                      基于 {Math.min(reviewSample.filter((r) => listifyStrings(r.llm_issue_subcategories).some((s) => issueItems.some((e) => (e.subcategory || e.sub_category) === s))).length, 50)} 条评论
                    </p>
                  </div>
                ) : topIssuesSummaryLoading ? (
                  <p className="mt-4 text-sm text-slate-500">正在生成摘要…</p>
                ) : null}
              </div>
            </div>
          </div>
        </Portal>
      ) : null}

      {topRequestsModalOpen ? (
        <Portal>
          <div
            className="fixed inset-0 z-[9996] bg-black/60 backdrop-blur-md overflow-y-auto animate-modal-overlay"
            onClick={closeTopRequestsModal}
            style={{ WebkitBackdropFilter: "blur(12px)" }}
          >
            <div className="min-h-screen flex items-start sm:items-center justify-center p-2 sm:p-4">
              <div
                className="w-full max-w-4xl rounded-xl sm:rounded-2xl border border-white/20 bg-slate-900 p-4 sm:p-6 shadow-2xl my-2 sm:my-8 animate-modal-content"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="flex flex-col sm:flex-row sm:flex-wrap items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-base sm:text-lg font-semibold text-white">重点需求摘要</h3>
                    <p className="mt-1 text-xs sm:text-sm text-slate-400">
                      主要需求的跨分类综合分析
                    </p>
                    {filterScopeLabel && (
                      <p className="mt-1 text-[11px] sm:text-xs text-sky-400 line-clamp-2">
                        筛选条件：{filterScopeLabel}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    <button
                      onClick={handleSummarizeTopRequests}
                      disabled={topRequestsSummaryLoading}
                      className="flex-1 sm:flex-none text-xs sm:text-sm px-3 py-2.5 rounded border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
                    >
                      {topRequestsSummaryLoading ? (
                        <>
                          <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          正在生成摘要…
                        </>
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                          </svg>
                          {topRequestsSummary ? "刷新" : "AI 摘要"}
                        </>
                      )}
                    </button>
                    <Button variant="secondary" onClick={closeTopRequestsModal} className="flex-1 sm:flex-none text-xs sm:text-sm">
                      关闭
                    </Button>
                  </div>
                </div>

                {topRequestsSummaryError && (
                  <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4">
                    <p className="text-sm text-rose-400">{topRequestsSummaryError}</p>
                  </div>
                )}

                {topRequestsSummary ? (
                  <div className="mt-4 space-y-4 rounded-xl border border-sky-500/30 bg-sky-500/5 p-4">
                    <div>
                      <h4 className="text-xs tracking-wider text-sky-400 mb-2">摘要</h4>
                      <p className="text-sm text-slate-200 leading-relaxed">{topRequestsSummary.summary}</p>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      {topRequestsSummary.key_points.length > 0 && (
                        <div>
                          <h4 className="text-xs uppercase tracking-wider text-white/80 mb-2 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 bg-white/70" />
                            关键发现
                          </h4>
                          <ul className="space-y-1.5">
                            {topRequestsSummary.key_points.map((item, idx) => (
                              <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                                <span className="text-sky-300 mt-1">•</span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {topRequestsSummary.actions.length > 0 && (
                        <div>
                          <h4 className="text-xs uppercase tracking-wider text-emerald-400 mb-2 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 bg-emerald-400" />
                            建议行动
                          </h4>
                          <ul className="space-y-1.5">
                            {topRequestsSummary.actions.map((item, idx) => (
                              <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                                <span className="text-emerald-400 mt-1">&rarr;</span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    <p className="text-xs text-slate-500 pt-2 border-t border-white/10">
                    基于 {Math.min(reviewSample.filter((r) => listifyStrings(r.llm_request_subcategories).some((s) => requestItems.some((e) => (e.subcategory || e.sub_category) === s))).length, 50)} 条评论
                    </p>
                  </div>
                ) : topRequestsSummaryLoading ? (
                  <p className="mt-4 text-sm text-slate-500">正在生成摘要…</p>
                ) : null}
              </div>
            </div>
          </div>
        </Portal>
      ) : null}

    </div>
  );
}

function listifyStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => item.length > 0);
}

function buildPlayerSegments(reviews: ReviewRow[]): PlayerSegments {
  const emptySegments: PlayerSegments = {
    experience_level: {
      newcomers: { count: 0, recommendation_rate: 0 },
      casual: { count: 0, recommendation_rate: 0 },
      experienced: { count: 0, recommendation_rate: 0 },
      veterans: { count: 0, recommendation_rate: 0 },
    },
    purchase_type: {
      steam_buyers: { count: 0, feature_request_rate: 0, recommendation_rate: 0 },
      key_users: { count: 0, feature_request_rate: 0, recommendation_rate: 0 },
      free_users: { count: 0, feature_request_rate: 0, recommendation_rate: 0 },
    },
    engagement_topics: {
      highly_engaged: { count: 0, recommendation_rate: 0 },
      moderately_engaged: { count: 0, recommendation_rate: 0 },
      low_engagement: { count: 0, recommendation_rate: 0 },
    },
    activity_status: {
      currently_active: { count: 0, recommendation_rate: 0, issue_count: 0 },
      recently_stopped: { count: 0, recommendation_rate: 0, issue_count: 0 },
      inactive: { count: 0, recommendation_rate: 0, issue_count: 0 },
    },
  };

  if (!reviews.length) return emptySegments;

  const hasIssueField = reviews.some((review) => review.llm_issue_subcategories !== undefined);
  const hasRequestField = reviews.some((review) => review.llm_request_subcategories !== undefined);

  const countRecommendationRate = (segment: ReviewRow[]) => {
    if (!segment.length) return 0;
    const recommended = segment.reduce((sum, review) => sum + (isRecommended(review.voted_up) ? 1 : 0), 0);
    return recommended / segment.length;
  };

  const countIssueReviews = (segment: ReviewRow[]) => {
    if (!hasIssueField) return 0;
    return segment.reduce((sum, review) => sum + (listifyStrings(review.llm_issue_subcategories).length > 0 ? 1 : 0), 0);
  };

  const topIssueCategories = (segment: ReviewRow[]) => {
    if (!segment.length) return [];
    const counts = new Map<string, number>();
    segment.forEach((review) => {
      const items = hasIssueField ? review.llm_issue_subcategories : review.llm_subcategories;
      listifyStrings(items).forEach((item) => {
        counts.set(item, (counts.get(item) ?? 0) + 1);
      });
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([category, count]) => ({ category, count }));
  };

  const featureRequestRate = (segment: ReviewRow[]) => {
    if (!segment.length || !hasRequestField) return 0;
    const withRequest = segment.reduce(
      (sum, review) => sum + (listifyStrings(review.llm_request_subcategories).length > 0 ? 1 : 0),
      0,
    );
    return withRequest / segment.length;
  };

  const minutesFor = (review: ReviewRow) => {
    const value = review.author_playtime_forever;
    if (typeof value === "number") return value;
    if (typeof value === "string") return parseFloat(value) || 0;
    return 0;
  };
  const recentMinutesFor = (review: ReviewRow) => Number(review.author_playtime_last_two_weeks ?? 0);
  const gamesOwnedFor = (review: ReviewRow) => Number(review.author_num_games_owned ?? 0);

  // Experience level based on Steam library size
  const newcomers = reviews.filter((review) => gamesOwnedFor(review) < 10);
  const casual = reviews.filter((review) => gamesOwnedFor(review) >= 10 && gamesOwnedFor(review) < 50);
  const experienced = reviews.filter((review) => gamesOwnedFor(review) >= 50 && gamesOwnedFor(review) < 150);
  const veterans = reviews.filter((review) => gamesOwnedFor(review) >= 150);

  const experience_level = {
    newcomers: {
      count: newcomers.length,
      recommendation_rate: countRecommendationRate(newcomers),
    },
    casual: {
      count: casual.length,
      recommendation_rate: countRecommendationRate(casual),
    },
    experienced: {
      count: experienced.length,
      recommendation_rate: countRecommendationRate(experienced),
    },
    veterans: {
      count: veterans.length,
      recommendation_rate: countRecommendationRate(veterans),
    },
  };

  const emptyContextSegment = { count: 0, feature_request_rate: 0, recommendation_rate: 0 };
  const purchase_type = {
    steam_buyers: { ...emptyContextSegment },
    key_users: { ...emptyContextSegment },
    free_users: { ...emptyContextSegment },
  };

  const mainCategoryForReview = (review: ReviewRow) => {
    if (typeof review.llm_main_category === "string" && review.llm_main_category.trim()) {
      return review.llm_main_category.trim().toLowerCase();
    }
    const subcats = listifyStrings(review.llm_subcategories);
    if (!subcats.length) return null;
    const main = subcats[0].includes("/") ? subcats[0].split("/", 1)[0] : subcats[0];
    return main ? main.toLowerCase() : null;
  };

  const topTopics = (segment: ReviewRow[]) => {
    if (!segment.length) return [];
    const counts = new Map<string, number>();
    segment.forEach((review) => {
      const main = mainCategoryForReview(review);
      if (!main) return;
      counts.set(main, (counts.get(main) ?? 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([topic, count]) => ({ topic, count }));
  };

  const highly_engaged = reviews.filter((review) => minutesFor(review) >= 6000);
  const moderately_engaged = reviews.filter((review) => minutesFor(review) >= 600 && minutesFor(review) < 6000);
  const low_engagement = reviews.filter((review) => minutesFor(review) < 600);

  const engagement_topics = {
    highly_engaged: {
      count: highly_engaged.length,
      recommendation_rate: countRecommendationRate(highly_engaged),
    },
    moderately_engaged: {
      count: moderately_engaged.length,
      recommendation_rate: countRecommendationRate(moderately_engaged),
    },
    low_engagement: {
      count: low_engagement.length,
      recommendation_rate: countRecommendationRate(low_engagement),
    },
  };

  const currently_active = reviews.filter((review) => recentMinutesFor(review) > 0);
  const recently_stopped = reviews.filter(
    (review) => recentMinutesFor(review) === 0 && minutesFor(review) > 0,
  );
  const inactive = reviews.filter((review) => minutesFor(review) === 0);

  const activity_status = {
    currently_active: {
      count: currently_active.length,
      recommendation_rate: countRecommendationRate(currently_active),
      issue_count: countIssueReviews(currently_active),
    },
    recently_stopped: {
      count: recently_stopped.length,
      recommendation_rate: countRecommendationRate(recently_stopped),
      issue_count: countIssueReviews(recently_stopped),
    },
    inactive: {
      count: inactive.length,
      recommendation_rate: countRecommendationRate(inactive),
      issue_count: countIssueReviews(inactive),
    },
  };

  const emptyPlatformSegment = { count: 0, recommendation_rate: 0, top_issues: [], issue_count: 0 };
  const platform: PlatformSegmentInsights = {
    steam_deck: { ...emptyPlatformSegment },
    desktop: { ...emptyPlatformSegment },
  };

  // Language segmentation
  const languageMap = new Map<string, ReviewRow[]>();
  reviews.forEach((review) => {
    const lang = review.language;
    if (lang) {
      const existing = languageMap.get(lang) || [];
      existing.push(review);
      languageMap.set(lang, existing);
    }
  });

  const languageStats = Array.from(languageMap.entries())
    .map(([lang, langReviews]) => ({
      language: lang,
      count: langReviews.length,
      recommendation_rate: countRecommendationRate(langReviews),
      top_issues: topIssueCategories(langReviews),
      issue_count: countIssueReviews(langReviews),
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 15);

  const language: LanguageSegmentInsights = {
    languages: languageStats,
    total_languages: languageMap.size,
  };

  return { experience_level, purchase_type, engagement_topics, activity_status, platform, language };
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatPercentOrDash(value: number | undefined | null): string {
  if (value === undefined || value === null) return "—";
  if (!Number.isFinite(value)) return "—";
  return formatPercent(value);
}

function formatMainCategoryLabel(value: string | undefined): string {
  const trimmed = (value || "").trim();
  if (!trimmed) return "";
  const normalized = trimmed.toLowerCase();
  return MAIN_CATEGORY_LABELS[normalized] ?? toTitleCase(trimmed);
}

function toSubcategoryLabel(value: string, subCategory?: string): string {
  const raw = (subCategory || value || "").trim();
  if (!raw) return "";
  return formatTaxonomyLabelZh(raw);
}

function toTitleCase(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";

  const normalized = trimmed.toLowerCase();
  const direct = MAIN_CATEGORY_LABELS[normalized];
  if (direct) return direct;

  if (trimmed.includes("/")) {
    const [mainRaw, subRaw] = trimmed.split("/", 2);
    const main = MAIN_CATEGORY_LABELS[mainRaw.toLowerCase()] ?? titleize(mainRaw);
    const sub = titleize(subRaw);
    return `${main} / ${sub}`;
  }

  return titleize(trimmed);
}

function titleize(value: string): string {
  return value
    .replace(/_/g, " ")
    .split(" ")
    .map((word) => {
      const lower = word.toLowerCase();
      if (lower === "ui") return "UI";
      if (lower === "ux") return "UX";
      if (lower === "ugc") return "UGC";
      if (lower === "ai") return "AI";
      if (lower === "dlc") return "DLC";
      if (lower === "fomo") return "FOMO";
      if (lower === "p2w") return "P2W";
      if (lower === "ctd") return "CTD";
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}
