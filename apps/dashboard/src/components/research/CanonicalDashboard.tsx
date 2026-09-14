'use client';

import { useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { formatTaxonomyLabelZh } from "@/lib/taxonomyLabels";
import { fetchAnalysisEvidence, DashboardMetricGroup, DashboardMetricRow, DashboardPresentation } from "@/lib/api";

function percent(value?: number | null): string {
  return value == null ? "Unavailable" : `${(value * 100).toFixed(value * 100 % 1 === 0 ? 0 : 2)}%`;
}

function semanticReason(reason?: string | null): string {
  if (reason === "no_provider") return "未配置 LLM Provider";
  return "语义分析暂不可用";
}

function MetricList({ title, group, onSelect, appId, runId, metricType }: { title: string; group?: DashboardMetricGroup | null; onSelect: (row: DashboardMetricRow) => void; appId: number; runId?: string | null; metricType: string }) {
  const items = group?.items ?? [];
  const totalCount = group?.total_count ?? 0;
  return (
    <section className="rounded-lg border border-white/10 bg-slate-950/25 p-4" aria-labelledby={`metric-${title}`}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 id={`metric-${title}`} className="text-sm font-semibold text-white">{title}</h3>
        <span className="text-[11px] text-slate-500">{totalCount} 项</span>
      </div>
      {items.length === 0 ? <p className="text-sm text-slate-500">暂无语义分析结果</p> : (
        <div className="space-y-3">
          {items.map((row) => (
            <div key={row.taxonomy_key} className="group block w-full text-left">
              <button type="button" onClick={() => onSelect(row)} className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="min-w-0 truncate text-slate-200" title={formatTaxonomyLabelZh(row.taxonomy_key)}>{formatTaxonomyLabelZh(row.taxonomy_key)}</span>
                <span className="shrink-0 font-mono text-slate-300">{row.n} 条 · {percent(row.share)}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-cyan-400/80 transition-all group-hover:bg-cyan-300" style={{ width: `${Math.min(100, Math.max(0, (row.share || 0) * 100))}%` }} /></div>
              <div className="mt-1 flex justify-between text-[10px] text-slate-500"><span>{row.n} 条已分析评论</span><span>查看评论 →</span></div>
              </button>
              <Link className="mt-1 inline-block text-[11px] text-sky-300 hover:text-sky-200" href={`/reviews?appId=${appId}${runId ? `&run=${encodeURIComponent(runId)}` : ""}&metric_type=${metricType}&taxonomy_key=${encodeURIComponent(row.taxonomy_key)}`}>查看全部 {row.n} 条评论 →</Link>
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
  const segmentDimensions = presentation.segments.dimensions as Record<string, {
    available?: boolean;
    groups?: Array<{ key: string; n?: number; recommended_n?: number; recommendation_rate?: number | null }>;
    missing_n?: number;
  }>;
  const scope = snapshot.collection_scope || {};
  const scopeLanguages = Array.isArray(scope.languages) && scope.languages.length ? scope.languages.join(" + ") : "全部语言";
  const scopeOrder = scope.collection_order === "updated" ? "最近更新" : scope.collection_order === "helpful" ? "最有帮助" : "最近评论";
  const meaningfulDiscovery = presentation.discovery.available && (
    (presentation.discovery.regions || []).some((region) => String(region.taxonomy_coverage_status || "").toLowerCase().includes("potential_gap"))
    || Boolean(presentation.discovery.interpretation?.candidate_count)
  );

  async function openEvidence(row: DashboardMetricRow, metricType?: string) {
    setSelected(row); setEvidence(null); setEvidenceError(null);
    try { setEvidence(await fetchAnalysisEvidence(appId, row.taxonomy_key, runId, 5, 0, metricType)); }
    catch { setEvidenceError("Source reviews are temporarily unavailable."); }
  }

  return (
    <main className="mx-auto max-w-7xl space-y-5 px-4 pb-8" data-testid="canonical-dashboard">
      {!showHeader && <section className="rounded-lg border border-white/10 bg-slate-900/60 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-slate-500">评论概览</p><h1 className="mt-1 text-xl font-semibold text-white" title={appName}>{appName}</h1><p className="mt-1 text-xs text-slate-400">{scopeOrder} · {scopeLanguages}</p><p className="mt-2 text-xs text-emerald-300">定量分析已完成 · 定量 Research Result 可用</p></div><div className="flex flex-wrap items-end gap-5"><div><p className="text-xs text-slate-500">好评率</p><p className="text-2xl font-semibold text-white">{percent(snapshot.recommendation_rate)}</p></div><div><p className="text-xs text-slate-500">评论</p><p className="text-lg font-medium text-white">{snapshot.population_n ?? "Unavailable"}</p><p className="text-xs text-slate-400">{snapshot.population_n != null ? `${snapshot.valid_n ?? "Unavailable"} 条有效评论` : "暂无评论"}</p></div><div><p className="text-xs text-slate-500">分析状态</p><p className="text-lg font-medium text-white">{semantic.available ? `${semantic.classified_n ?? 0} / ${semantic.population_n ?? snapshot.population_n}` : "语义分析暂不可用"}</p><p className="text-xs text-amber-200">{semantic.available ? "暂定结果 ⓘ" : semanticReason(semantic.reason)}</p></div>{onConfigureSampling && <button type="button" onClick={onConfigureSampling} className="rounded border border-sky-400/30 px-3 py-2 text-xs text-sky-200 hover:bg-sky-400/10">更新分析</button>}</div></div></section>}
      {showHeader && <section className="rounded-lg border border-white/10 bg-slate-900/60 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0"><p className="text-xs uppercase tracking-[0.22em] text-cyan-300/80">Research workspace</p><h1 className="mt-2 truncate text-2xl font-semibold tracking-tight text-white" title={appName}>{appName}</h1><p className="mt-1 text-sm text-slate-400">Run {presentation.run.run_id || "Unavailable"} · {presentation.run.status}</p></div>
          <div className="flex items-center gap-2"><span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-200">{snapshot.valid_n} valid observations</span>{semantic.claim_status && <span className="rounded-full border border-amber-300/50 bg-amber-300/15 px-3 py-1 text-xs font-bold tracking-wide text-amber-100">{semantic.claim_status}</span>}</div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3"><div><p className="text-xs text-slate-500">Recommendation rate</p><p className="mt-1 text-3xl font-semibold text-white">{percent(snapshot.recommendation_rate)}</p></div><div><p className="text-xs text-slate-500">Scope</p><p className="mt-1 text-lg font-medium text-white">{snapshot.population_n} recent English reviews</p><p className="text-xs text-amber-200/80">{snapshot.truncated_by_max_reviews ? "Limited to requested maximum" : "Collection complete"}</p></div><div><p className="text-xs text-slate-500">Recommendation split</p><p className="mt-1 text-lg font-medium text-white">{snapshot.recommended_n} recommended · {snapshot.not_recommended_n} not recommended</p><p className="text-xs text-slate-500">Observed sample, not all players</p></div></div>
      </section>}

      <section className="rounded-lg border border-white/10 bg-slate-900/60 p-5">
        <div className="flex items-start justify-between gap-3">
          <div><p className="text-xs uppercase tracking-widest text-slate-500">确定性分群</p><h2 className="mt-1 text-lg font-semibold text-white">谁在评论</h2></div>
          <span className="text-xs text-slate-500">exact run population · {presentation.segments.population_n.toLocaleString()} reviews</span>
        </div>
        {!presentation.segments.available ? <p className="mt-3 text-sm text-slate-400">该 Research Run 没有可用的确定性分群 projection。</p> : <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {Object.entries(segmentDimensions).map(([dimension, data]) => <div key={dimension} className="rounded border border-white/10 bg-slate-950/25 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{dimension === "playtime_at_review" ? "At-review playtime" : "Language"}</h3>
            {!data.available || !data.groups?.length ? <p className="mt-2 text-xs text-slate-500">Unavailable — missing observed fields.</p> : <div className="mt-2 space-y-2">{data.groups.map((group) => <div key={group.key} className="flex items-center justify-between gap-2 text-xs"><span className="truncate text-slate-300">{group.key}</span><span className="shrink-0 text-slate-400">{group.n ?? 0} · {percent(group.recommendation_rate)}</span></div>)}</div>}
            {data.missing_n ? <p className="mt-2 text-[10px] text-slate-600">Missing: {data.missing_n}</p> : null}
          </div>)}
        </div>}
      </section>

      <section className="rounded-lg border border-white/10 bg-slate-900/60 p-5"><div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-slate-500">分析状态</p><h2 className="mt-1 text-lg font-semibold text-white">语义分析</h2></div><span title="定量分析已经完成；语义分类可能因配置不可用。" className={`rounded-md border px-3 py-1 text-xs font-bold ${semantic.available ? "border-amber-300/50 bg-amber-300/15 text-amber-100" : "border-slate-500/40 bg-slate-500/10 text-slate-300"}`}>{semantic.available ? "暂定结果 ⓘ" : "暂不可用"}</span></div>{semantic.available ? <><p className="mt-3 text-sm text-slate-300">语义分析已完成，但当前结果仍处于验证阶段。</p><div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3"><div><span className="text-slate-500">已分析评论</span><strong className="mt-1 block text-white">{semantic.classified_n ?? 0} / {semantic.population_n ?? snapshot.population_n}</strong></div><div><span className="text-slate-500">分析覆盖率</span><strong className="mt-1 block text-white">{percent(semantic.classification_coverage)}</strong></div><div><span className="text-slate-500">结果资格</span><strong className="mt-1 block text-amber-100">暂定</strong></div></div></> : <div className="mt-3 space-y-1 text-sm text-slate-400"><p>语义分析暂不可用。</p><p>原因：{semanticReason(semantic.reason)}。</p><p>评论概览和定量结果仍可正常查看。</p></div>}</section>

      <section><div className="mb-3 flex items-end justify-between"><div><p className="text-xs uppercase tracking-widest text-sky-300/70">玩家声音</p><h2 className="mt-1 text-xl font-semibold text-white">玩家关注</h2></div><p className="text-xs text-slate-500">占已分析评论</p></div><MetricList title="主要讨论内容" group={presentation.player_voice.actionable_topics} onSelect={(row) => openEvidence(row, "topic")} appId={appId} runId={runId} metricType="topic" /></section>
      <section className="grid gap-4 lg:grid-cols-2"><MetricList title="主要问题" group={presentation.player_voice.issues} onSelect={(row) => openEvidence(row, "issue")} appId={appId} runId={runId} metricType="issue" /><MetricList title="玩家需求" group={presentation.player_voice.requests} onSelect={(row) => openEvidence(row, "request")} appId={appId} runId={runId} metricType="request" /></section>

      <section className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]"><Card className="border-white/10 bg-slate-900/60 p-5"><p className="text-xs uppercase tracking-widest text-slate-500">其他内容</p><p className="mt-1 text-sm text-slate-400">与主要问题和需求分开显示。</p><div className="mt-4 space-y-3">{presentation.player_voice.context_topics.items.map((row) => <Link key={row.taxonomy_key} href={`/reviews?appId=${appId}${runId ? `&run=${encodeURIComponent(runId)}` : ""}&metric_type=topic&taxonomy_key=${encodeURIComponent(row.taxonomy_key)}`} className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.03] px-3 py-2 hover:bg-white/[0.06]"><span className="min-w-0 truncate text-sm text-slate-200" title={formatTaxonomyLabelZh(row.taxonomy_key)}>{formatTaxonomyLabelZh(row.taxonomy_key)}</span><span className="shrink-0 font-mono text-xs text-slate-300">{row.n} 条 · {percent(row.share)}</span></Link>)}</div></Card>{meaningfulDiscovery && <Card className="border-white/10 bg-slate-900/60 p-5"><p className="text-xs uppercase tracking-widest text-slate-500">额外发现</p><h2 className="mt-1 text-lg font-semibold text-white">可能值得关注的新讨论</h2><div className="mt-4 space-y-2 text-sm text-slate-300">{(presentation.discovery.regions || []).filter((region) => String(region.taxonomy_coverage_status || "").toLowerCase().includes("potential_gap")).slice(0, 3).map((region, index) => <p key={String(region.region_id || index)}>发现一组稳定的额外讨论（{String(region.support_reviews ?? 0)} 条相关评论）。</p>)}</div></Card>}</section>

      {selected && <section className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 p-5" aria-live="polite"><div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-widest text-cyan-200/70">原评论</p><h2 className="mt-1 text-lg font-semibold text-white">{formatTaxonomyLabelZh(selected.taxonomy_key)}</h2><p className="mt-1 text-sm text-slate-400">{selected.n} 条匹配评论</p></div><button type="button" className="rounded border border-white/15 px-2 py-1 text-xs text-slate-300" onClick={() => setSelected(null)} aria-label="Close source reviews">关闭</button></div>{evidenceError && <p className="mt-4 text-sm text-amber-200">原评论暂时不可用。</p>}{evidence && <div className="mt-4">{evidence.verified_evidence_count > 0 && <p className="mb-3 text-sm text-slate-300">识别到的相关片段</p>}<div className="space-y-2">{evidence.items.map((item) => <article key={item.review_id} className="rounded-lg border border-white/10 bg-slate-950/35 p-3"><div className="flex justify-between text-[11px] text-slate-500"><span>原评论</span><span>{item.evidence.length ? "分析依据" : ""}</span></div><p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-300">{item.review}</p></article>)}</div></div>}</section>}
    </main>
  );
}
