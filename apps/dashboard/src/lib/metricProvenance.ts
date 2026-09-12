import type { InsightsResponse, MetricObservation } from "@/types";

export function getMetricObservation(
  insights: InsightsResponse | null | undefined,
  metricId: string,
  expectedRunId?: string | null,
): MetricObservation | undefined {
  const observation = insights?.metric_provenance?.[metricId];
  if (!observation) return undefined;
  if (expectedRunId && observation.run_id && expectedRunId !== observation.run_id) return undefined;
  return observation;
}

/** Modern results never fall back to display-sample arithmetic. */
export function metricValue(
  insights: InsightsResponse | null | undefined,
  metricId: string,
  legacyValue: number | null | undefined,
  expectedRunId?: string | null,
): number | null {
  if (insights?.metric_provenance) {
    const observation = getMetricObservation(insights, metricId, expectedRunId);
    if (!observation || observation.status === "unavailable" || observation.value == null) return null;
    return Number.isFinite(Number(observation.value)) ? Number(observation.value) : null;
  }
  if (legacyValue == null || !Number.isFinite(Number(legacyValue))) return null;
  return Number(legacyValue);
}

export function compatibleMetricObservations(
  left: MetricObservation | undefined,
  right: MetricObservation | undefined,
): boolean {
  if (!left || !right) return false;
  return left.metric_id === right.metric_id
    && left.formula_version === right.formula_version
    && left.source_type === right.source_type
    && left.denominator_type === right.denominator_type
    && left.is_sampled === right.is_sampled
    && left.sampling_semantics === right.sampling_semantics;
}

export function metricSecondaryLabel(observation: MetricObservation | undefined): string | null {
  if (!observation) return null;
  if (observation.status === "unavailable" || observation.value == null) {
    return observation.unavailable_reason || "Unavailable";
  }
  const numerator = observation.numerator == null ? null : Number(observation.numerator);
  const denominator = observation.denominator == null ? null : Number(observation.denominator);
  const coverage = observation.coverage == null ? null : `${Math.round(Number(observation.coverage) * 100)}% coverage`;
  const parts = numerator != null && denominator != null ? [`${numerator}/${denominator}`] : [];
  if (coverage && observation.source_type === "llm_derived") parts.push(coverage);
  if (observation.is_sampled) parts.push("selected sample · non-representative");
  return parts.join(" · ") || observation.denominator_type;
}
