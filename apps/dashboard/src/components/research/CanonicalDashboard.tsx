'use client';

import { useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { formatTaxonomyLabelZh } from "@/lib/taxonomyLabels";
import { fetchAnalysisEvidence, DashboardMetricGroup, DashboardMetricRow, DashboardPresentation } from "@/lib/api";

function percent(value?: number | null): string {
  return value == null ? "Unavailable" : `${(value * 100).toFixed(value * 100 % 1 === 0 ? 0 : 2)}%`;
}

function MetricList({ title, group, onSelect, appId, runId, metricType }: { title: string; group: DashboardMetricGroup; onSelect: (row: DashboardMetricRow) => void; appId: number; runId?: string | null; metricType: string }) {
  return (
    <section className="rounded-lg border border-white/10 bg-slate-950/25 p-4" aria-labelledby={`metric-${title}`}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 id={`metric-${title}`} className="text-sm font-semibold text-white">{title}</h3>
        <span className="text-[11px] text-slate-500">{group.total_count} tracked</span>
      </div>
      {group.items.length === 0 ? <p className="text-sm text-slate-500">Unavailable for this run.</p> : (
        <div className="space-y-3">
          {group.items.map((row) => (
            <div key={row.taxonomy_key} className="group block w-full text-left">
              <button type="button" onClick={() => onSelect(row)} className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="min-w-0 truncate text-slate-200" title={formatTaxonomyLabelZh(row.taxonomy_key)}>{formatTaxonomyLabelZh(row.taxonomy_key)}</span>
                <span className="shrink-0 font-mono text-slate-300">{row.n} · {percent(row.share)}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-cyan-400/80 transition-all group-hover:bg-cyan-300" style={{ width: `${Math.min(100, Math.max(0, (row.share || 0) * 100))}%` }} /></div>
              <div className="mt-1 flex justify-between text-[10px] text-slate-500"><span>{row.n} / classified reviews · {percent(row.share)}</span><span>Preview source reviews</span></div>
              </button>
              <Link className="mt-1 inline-block text-[11px] text-sky-300 hover:text-sky-200" href={`/reviews?appId=${appId}${runId ? `&run=${encodeURIComponent(runId)}` : ""}&metric_type=${metricType}&taxonomy_key=${encodeURIComponent(row.taxonomy_key)}`}>查看全部 {row.n} 条原评论 →</Link>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function CanonicalDashboard({ presentation, appName, appId, showHeader = true, onConfigureSampling }: { presentation: DashboardPresentation; appName: string; appId: number; showHeader?: boolean; onConfigureSampling?: () => void }) {
  const [selected, setSelected] = useState<DashboardMetricRow | null>(null);
  const [evidence, setEvidence] = useState<Awaited<ReturnType<typeof fetchAnalysisEvidence>> | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const snapshot = presentation.research_snapshot;
  const semantic = presentation.semantic;
  const runId = presentation.run.run_id;

  async function openEvidence(row: DashboardMetricRow, metricType?: string) {
    setSelected(row); setEvidence(null); setEvidenceError(null);
    try { setEvidence(await fetchAnalysisEvidence(appId, row.taxonomy_key, runId, 5, 0, metricType)); }
    catch { setEvidenceError("Source reviews are temporarily unavailable."); }
  }

  return (
    <main className="mx-auto max-w-7xl space-y-5 px-4 pb-8" data-testid="canonical-dashboard">
      {!showHeader && <section className="rounded-lg border border-white/10 bg-slate-900/60 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-slate-500">Research snapshot</p><h1 className="mt-1 text-xl font-semibold text-white" title={appName}>{appName}</h1><p className="mt-1 text-xs text-slate-400">Run {presentation.run.run_id || "Unavailable"} · {presentation.run.status}</p></div><div className="flex flex-wrap items-end gap-5"><div><p className="text-xs text-slate-500">Observed recommendation rate</p><p className="text-2xl font-semibold text-white">{percent(snapshot.recommendation_rate)}</p></div><div><p className="text-xs text-slate-500">Population</p><p className="text-lg font-medium text-white">{snapshot.population_n} reviews</p><p className="text-xs text-amber-200">{snapshot.collection_status === "complete" ? "Collection complete" : snapshot.collection_status === "limited" ? "Limited / truncated" : "Collection status unknown"}</p></div>{onConfigureSampling && <button type="button" onClick={onConfigureSampling} className="rounded border border-sky-400/30 px-3 py-2 text-xs text-sky-200 hover:bg-sky-400/10">Analysis setup</button>}</div></div></section>}
      {showHeader && <section className="rounded-lg border border-white/10 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0"><p className="text-xs uppercase tracking-[0.22em] text-cyan-300/80">Research workspace</p><h1 className="mt-2 truncate text-2xl font-semibold tracking-tight text-white" title={appName}>{appName}</h1><p className="mt-1 text-sm text-slate-400">Run {presentation.run.run_id || "Unavailable"} · {presentation.run.status}</p></div>
          <div className="flex items-center gap-2"><span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-200">{snapshot.valid_n} valid observations</span>{semantic.claim_status && <span className="rounded-full border border-amber-300/50 bg-amber-300/15 px-3 py-1 text-xs font-bold tracking-wide text-amber-100">{semantic.claim_status}</span>}</div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3"><div><p className="text-xs text-slate-500">Recommendation rate</p><p className="mt-1 text-3xl font-semibold text-white">{percent(snapshot.recommendation_rate)}</p></div><div><p className="text-xs text-slate-500">Scope</p><p className="mt-1 text-lg font-medium text-white">{snapshot.population_n} recent English reviews</p><p className="text-xs text-amber-200/80">{snapshot.truncated_by_max_reviews ? "Limited to requested maximum" : "Collection complete"}</p></div><div><p className="text-xs text-slate-500">Recommendation split</p><p className="mt-1 text-lg font-medium text-white">{snapshot.recommended_n} recommended · {snapshot.not_recommended_n} not recommended</p><p className="text-xs text-slate-500">Observed sample, not all players</p></div></div>
      </section>}

      <section className="grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
        <Card className="border-white/10 bg-slate-900/60 p-5"><div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-slate-500">Semantic qualification</p><h2 className="mt-1 text-lg font-semibold text-white">Semantic analysis</h2></div><span className={`rounded-md border px-3 py-1 text-xs font-bold ${semantic.available ? "border-amber-300/50 bg-amber-300/15 text-amber-100" : "border-slate-500/40 bg-slate-500/10 text-slate-300"}`}>{semantic.claim_status || "UNAVAILABLE"}</span></div>{semantic.available ? <><p className="mt-3 text-sm text-amber-100">Production classification completed, but this semantic measurement has not yet passed formal classifier validation.</p><div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4"><div><span className="text-slate-500">Coverage</span><strong className="mt-1 block text-white">{semantic.classified_n} / {semantic.population_n}</strong></div><div><span className="text-slate-500">Coverage rate</span><strong className="mt-1 block text-white">{percent(semantic.classification_coverage)}</strong></div><div><span className="text-slate-500">Taxonomy</span><strong className="mt-1 block truncate text-white" title={semantic.taxonomy_version || ""}>{semantic.taxonomy_version || "Unavailable"}</strong></div><div><span className="text-slate-500">Provider</span><strong className="mt-1 block truncate text-white" title={`${semantic.provider || ""} ${semantic.model || ""}`}>{semantic.provider || "Unavailable"}</strong></div></div></> : <p className="mt-3 text-sm text-slate-400">Semantic analysis unavailable: {semantic.reason || "no persisted semantic result"}</p>}</Card>
        <Card className="border-white/10 bg-slate-900/60 p-5"><p className="text-xs uppercase tracking-widest text-slate-500">Methodology</p><h2 className="mt-1 text-lg font-semibold text-white">What the numbers mean</h2><p className="mt-3 text-sm leading-6 text-slate-400">Topic, issue, and request percentages use classified reviews as their denominator. The recommendation rate is owned by Research Core. Discovery support is never player prevalence.</p><div className="mt-4 flex flex-wrap gap-2"><span className="rounded-md bg-white/5 px-2 py-1 text-xs text-slate-300">{snapshot.population_n} population</span><span className="rounded-md bg-white/5 px-2 py-1 text-xs text-slate-300">{semantic.classified_n ?? 0} classified</span><span className="rounded-md bg-white/5 px-2 py-1 text-xs text-slate-300">{snapshot.acquisition_coverage || "scope unavailable"}</span></div></Card>
      </section>

      <section><div className="mb-3 flex items-end justify-between"><div><p className="text-xs uppercase tracking-widest text-sky-300/70">Player voice</p><h2 className="mt-1 text-xl font-semibold text-white">Actionable topics</h2></div><p className="text-xs text-slate-500">Observed classified review share</p></div><MetricList title="Actionable Topics" group={presentation.player_voice.actionable_topics} onSelect={(row) => openEvidence(row, "topic")} appId={appId} runId={runId} metricType="topic" /></section>
      <section className="grid gap-4 lg:grid-cols-2"><MetricList title="Issues" group={presentation.player_voice.issues} onSelect={(row) => openEvidence(row, "issue")} appId={appId} runId={runId} metricType="issue" /><MetricList title="Requests" group={presentation.player_voice.requests} onSelect={(row) => openEvidence(row, "request")} appId={appId} runId={runId} metricType="request" /></section>

      <section className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]"><Card className="border-white/10 bg-slate-900/60 p-5"><p className="text-xs uppercase tracking-widest text-slate-500">Context / Other</p><p className="mt-1 text-sm text-slate-400">Kept visible for coverage diagnosis, separated from actionable priorities.</p><div className="mt-4 space-y-3">{presentation.player_voice.context_topics.items.map((row) => <div key={row.taxonomy_key} className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.03] px-3 py-2"><span className="truncate text-sm text-slate-200" title={row.taxonomy_key}>{formatTaxonomyLabelZh(row.taxonomy_key)}</span><span className="shrink-0 font-mono text-xs text-slate-300">{row.n} / {semantic.classified_n ?? snapshot.population_n} · {percent(row.share)}</span></div>)}</div></Card><Card className="border-white/10 bg-slate-900/60 p-5"><div className="flex items-start justify-between"><div><p className="text-xs uppercase tracking-widest text-slate-500">Discovery signals</p><h2 className="mt-1 text-lg font-semibold text-white">Semantic geometry sidecar</h2></div><span className="rounded-full bg-white/5 px-2 py-1 text-xs text-slate-400">Secondary signal</span></div>{presentation.discovery.available ? <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 text-sm"><div><span className="text-slate-500">Dense</span><strong className="block text-white">{presentation.discovery.dense_region_n}</strong></div><div><span className="text-slate-500">Rare</span><strong className="block text-white">{presentation.discovery.rare_region_n}</strong></div><div><span className="text-slate-500">Outliers</span><strong className="block text-white">{presentation.discovery.outlier_review_n} reviews</strong></div><div className="min-w-0"><span className="text-slate-500">3C</span><strong className="block break-words text-xs leading-4 text-amber-100" title={String(presentation.discovery.interpretation?.real_status || presentation.discovery.interpretation?.status || "unavailable")}>{String(presentation.discovery.interpretation?.real_status || presentation.discovery.interpretation?.status || "unavailable")}</strong></div></div> : <p className="mt-4 text-sm text-slate-400">Discovery sidecar unavailable for this run.</p>}</Card></section>

      {selected && <section className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 p-5" aria-live="polite"><div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-cyan-200/70">Source reviews</p><h2 className="mt-1 text-lg font-semibold text-white">{formatTaxonomyLabelZh(selected.taxonomy_key)}</h2><p className="mt-1 text-sm text-slate-400">{selected.n} matched reviews · verified quotes are shown separately</p></div><button type="button" className="rounded border border-white/15 px-2 py-1 text-xs text-slate-300" onClick={() => setSelected(null)} aria-label="Close source reviews">Close</button></div>{evidenceError && <p className="mt-4 text-sm text-amber-200">{evidenceError}</p>}{evidence && <div className="mt-4">{evidence.verified_evidence_count === 0 && <p className="mb-3 text-sm text-slate-400">No verified quote available. Showing source reviews instead.</p>}<div className="space-y-2">{evidence.items.map((item) => <article key={item.review_id} className="rounded-lg border border-white/10 bg-slate-950/35 p-3"><div className="flex justify-between text-[11px] text-slate-500"><span>{item.review_id}</span><span>{item.evidence.length ? "Verified Evidence" : "Source Review"}</span></div><p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-300">{item.review}</p></article>)}</div></div>}</section>}

      <details className="rounded-xl border border-white/10 bg-slate-950/25 p-4"><summary className="cursor-pointer text-sm font-medium text-slate-200">Details & provenance</summary><div className="mt-4 grid gap-2 text-xs text-slate-400 sm:grid-cols-2 lg:grid-cols-3">{Object.entries(presentation.provenance).map(([key, value]) => <div key={key} className="min-w-0"><span className="text-slate-600">{key}</span><p className="truncate font-mono text-slate-300" title={String(value ?? "Unavailable")}>{String(value ?? "Unavailable")}</p></div>)}</div></details>
    </main>
  );
}
