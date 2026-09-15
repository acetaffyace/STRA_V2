'use client';

import { useEffect, useMemo, useState } from 'react';
import { AppLayout } from '@/components/AppLayout';
import { PageTransition } from '@/components/PageTransition';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { fetchVersionEvents, searchGames, syncNewsVersionEvents, type VersionEventResponse } from '@/lib/api';
import type { SearchResult } from '@/types';
import {
  createVersionComparisonPlan,
  fetchVersionComparisonRun,
  startVersionComparison,
  type VersionComparisonAnalysisMode,
  type VersionComparisonMetrics,
  type VersionComparisonPlan,
  type VersionComparisonRequest,
  type VersionComparisonRun,
  type VersionComparisonTopic,
} from '@/lib/versionComparisonApi';

const COHORT_LABELS = {
  A_PRE: '版本 A · 更新前',
  A_POST: '版本 A · 更新后',
  B_PRE: '版本 B · 更新前',
  B_POST: '版本 B · 更新后',
} as const;

function pct(value: number | null | undefined): string {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

function pp(value: number | null | undefined): string {
  if (value == null) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(1)} pp`;
}

function dateTime(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

function levelLabel(value?: string): string {
  if (value === 'high') return '高';
  if (value === 'moderate') return '中';
  if (value === 'low') return '低';
  if (value === 'unknown') return '未知';
  return value || '未知';
}

function MetricTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-4">
      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-white">{value}</p>
      {note && <p className="mt-1 text-xs leading-5 text-slate-500">{note}</p>}
    </div>
  );
}

function DeltaTile({ label, value, emphasis = false }: { label: string; value: number | null | undefined; emphasis?: boolean }) {
  const positive = (value ?? 0) > 0;
  const negative = (value ?? 0) < 0;
  return (
    <div className={`rounded-xl border p-4 ${emphasis ? 'border-cyan-400/30 bg-cyan-400/[0.06]' : 'border-white/10 bg-black/20'}`}>
      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${positive ? 'text-emerald-300' : negative ? 'text-rose-300' : 'text-white'}`}>{pp(value)}</p>
    </div>
  );
}

function TopicTable({ title, rows }: { title: string; rows: VersionComparisonTopic[] }) {
  if (!rows.length) return null;
  return (
    <Card variant="glass">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Semantic comparison</p>
          <h3 className="mt-1 text-lg font-semibold text-white">{title}</h3>
        </div>
        <Badge variant="default">共同支持样本</Badge>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-white/10 text-xs uppercase tracking-wider text-slate-500">
            <tr><th className="py-3 pr-4">主题</th><th className="px-3">A 前→后</th><th className="px-3">B 前→后</th><th className="px-3">相对变化 ΔΔ</th><th className="pl-3">四组支持数</th></tr>
          </thead>
          <tbody>
            {rows.slice(0, 12).map((row) => (
              <tr key={row.topic_id} className="border-b border-white/[0.06] last:border-0">
                <td className="py-3 pr-4 font-medium text-slate-200">{row.display_name}</td>
                <td className="px-3 text-slate-300">{pp(row.a_change_pp)}</td>
                <td className="px-3 text-slate-300">{pp(row.b_change_pp)}</td>
                <td className="px-3 font-medium text-cyan-200">{pp(row.difference_in_differences_pp)}</td>
                <td className="pl-3 text-xs text-slate-500">{Object.values(row.support).join(' / ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function VersionComparisonPage() {
  const [gameQuery, setGameQuery] = useState('');
  const [games, setGames] = useState<SearchResult[]>([]);
  const [appId, setAppId] = useState<number | null>(null);
  const [gameName, setGameName] = useState('');
  const [events, setEvents] = useState<VersionEventResponse[]>([]);
  const [eventA, setEventA] = useState('');
  const [eventB, setEventB] = useState('');
  const [windowDays, setWindowDays] = useState<3 | 7 | 14>(7);
  const [mode, setMode] = useState<VersionComparisonAnalysisMode>('semantic');
  const [maxPerCohort, setMaxPerCohort] = useState<500 | 1000 | 2000 | 5000 | 10000>(2000);
  const [semanticBudget, setSemanticBudget] = useState(4000);
  const [plan, setPlan] = useState<VersionComparisonPlan | null>(null);
  const [run, setRun] = useState<VersionComparisonRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useMemo<VersionComparisonRequest | null>(() => {
    if (!appId || !eventA || !eventB || eventA === eventB) return null;
    return {
      app_id: appId,
      event_a_id: eventA,
      event_b_id: eventB,
      window_days: windowDays,
      languages: ['all'],
      max_reviews_per_cohort: maxPerCohort,
      analysis_mode: mode,
      semantic_budget: mode === 'semantic' ? semanticBudget : 0,
    };
  }, [appId, eventA, eventB, windowDays, maxPerCohort, mode, semanticBudget]);

  const metrics = run?.metrics?.schema_version === 'version-comparison-v3' ? run.metrics as VersionComparisonMetrics : null;

  useEffect(() => {
    if (!request) { setPlan(null); return; }
    let cancelled = false;
    createVersionComparisonPlan(request)
      .then((value) => { if (!cancelled) setPlan(value); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : '无法生成版本对比方案。'); });
    return () => { cancelled = true; };
  }, [request]);

  useEffect(() => {
    if (!run || run.status !== 'running') return;
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchVersionComparisonRun(run.run_id);
        setRun(next);
        if (next.status === 'failed') setError(next.error || '版本对比执行失败。');
      } catch (err) {
        setError(err instanceof Error ? err.message : '无法读取分析进度。');
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [run]);

  const findGame = async () => {
    const query = gameQuery.trim();
    if (!query) return;
    setLoading(true); setError(null);
    try { setGames(await searchGames(query)); }
    catch (err) { setError(err instanceof Error ? err.message : '无法搜索游戏。'); }
    finally { setLoading(false); }
  };

  const selectGame = async (game: SearchResult) => {
    setAppId(game.appid); setGameName(game.name); setGameQuery(game.name); setGames([]); setPlan(null); setRun(null); setError(null);
    setLoading(true);
    try {
      let nextEvents = await fetchVersionEvents(game.appid);
      if (nextEvents.length < 2) {
        await syncNewsVersionEvents(game.appid, { news_count: 60 });
        nextEvents = await fetchVersionEvents(game.appid);
      }
      nextEvents = [...nextEvents].sort((a, b) => String(a.event_date).localeCompare(String(b.event_date)));
      setEvents(nextEvents);
      if (nextEvents.length >= 2) {
        setEventA(nextEvents[nextEvents.length - 2].event_id);
        setEventB(nextEvents[nextEvents.length - 1].event_id);
      }
    } catch (err) { setError(err instanceof Error ? err.message : '无法读取版本事件。'); }
    finally { setLoading(false); }
  };

  const refreshEvents = async () => {
    if (!appId) return;
    setLoading(true); setError(null);
    try {
      await syncNewsVersionEvents(appId, { news_count: 80 });
      const next = [...await fetchVersionEvents(appId)].sort((a, b) => String(a.event_date).localeCompare(String(b.event_date)));
      setEvents(next);
    } catch (err) { setError(err instanceof Error ? err.message : '同步版本事件失败。'); }
    finally { setLoading(false); }
  };

  const start = async () => {
    if (!request) return;
    setLoading(true); setError(null);
    try {
      const result = await startVersionComparison(request);
      setPlan(result.plan);
      setRun(result.run);
    } catch (err) { setError(err instanceof Error ? err.message : '无法启动版本对比。'); }
    finally { setLoading(false); }
  };

  const raw = metrics?.raw;
  const cohortEntries = raw ? Object.entries(raw.cohorts) as Array<[keyof typeof COHORT_LABELS, typeof raw.cohorts.A_PRE]> : [];
  const phaseText: Record<string, string> = {
    planning: '正在生成四窗口方案',
    acquiring_a_pre: '正在准备版本 A 更新前评论',
    acquiring_a_post: '正在准备版本 A 更新后评论',
    acquiring_b_pre: '正在准备版本 B 更新前评论',
    acquiring_b_post: '正在准备版本 B 更新后评论',
    building_semantic_sample: '正在构造可比语义样本',
    classifying_semantic_sample: '正在进行统一口径语义分类',
    finalizing: '正在生成对比报告',
  };

  return (
    <AppLayout>
      <PageTransition>
        <div className="min-h-screen bg-[rgb(5,5,15)] px-4 py-8 text-slate-100 sm:px-8 lg:px-12">
          <div className="mx-auto max-w-7xl space-y-6">
            <div>
              <p className="text-xs uppercase tracking-[0.25em] text-cyan-400/70">Version comparison · four cohorts</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">版本对比</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">比较两个版本各自的更新前后反馈。原始统计不依赖 LLM；需要主题、问题与需求时，再对四组共同支持样本进行统一语义分类。</p>
            </div>

            <Card variant="gradient">
              <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr_1fr_auto] lg:items-end">
                <div>
                  <label className="text-xs uppercase tracking-wider text-slate-500">游戏</label>
                  <div className="mt-2 flex gap-2">
                    <input value={gameQuery} onChange={(e) => setGameQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void findGame(); }} placeholder="输入游戏名" className="min-h-11 flex-1 rounded-md border border-cyan-400/20 bg-black/30 px-3 text-sm outline-none focus:border-cyan-400/70" />
                    <Button type="button" onClick={() => void findGame()} disabled={loading}>搜索</Button>
                  </div>
                  {games.length > 0 && <div className="mt-2 space-y-1">{games.map((game) => <button key={game.appid} type="button" onClick={() => void selectGame(game)} className="block w-full rounded-md border border-white/10 bg-black/30 px-3 py-2 text-left text-sm hover:border-cyan-400/40">{game.name} <span className="text-slate-500">({game.appid})</span></button>)}</div>}
                </div>
                <div>
                  <label className="text-xs uppercase tracking-wider text-slate-500">版本 A（较早）</label>
                  <select value={eventA} onChange={(e) => setEventA(e.target.value)} className="mt-2 min-h-11 w-full rounded-md border border-cyan-400/20 bg-slate-950 px-3 text-sm" disabled={!events.length}>
                    <option value="">选择较早版本</option>{events.map((event) => <option key={event.event_id} value={event.event_id}>{event.event_date} · {event.event_name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs uppercase tracking-wider text-slate-500">版本 B（较新）</label>
                  <select value={eventB} onChange={(e) => setEventB(e.target.value)} className="mt-2 min-h-11 w-full rounded-md border border-cyan-400/20 bg-slate-950 px-3 text-sm" disabled={!events.length}>
                    <option value="">选择较新版本</option>{events.map((event) => <option key={event.event_id} value={event.event_id}>{event.event_date} · {event.event_name}</option>)}
                  </select>
                </div>
                <Button type="button" variant="secondary" onClick={() => void refreshEvents()} disabled={!appId || loading}>同步版本</Button>
              </div>

              {appId && <div className="mt-5 grid gap-4 border-t border-white/10 pt-5 md:grid-cols-4">
                <div><label className="text-xs uppercase tracking-wider text-slate-500">主窗口</label><select value={windowDays} onChange={(e) => setWindowDays(Number(e.target.value) as 3 | 7 | 14)} className="mt-2 min-h-11 w-full rounded-md border border-white/10 bg-slate-950 px-3 text-sm"><option value={3}>前后 3 天</option><option value={7}>前后 7 天</option><option value={14}>前后 14 天</option></select></div>
                <div><label className="text-xs uppercase tracking-wider text-slate-500">每组原始评论上限</label><select value={maxPerCohort} onChange={(e) => setMaxPerCohort(Number(e.target.value) as typeof maxPerCohort)} className="mt-2 min-h-11 w-full rounded-md border border-white/10 bg-slate-950 px-3 text-sm">{[500,1000,2000,5000,10000].map((n) => <option key={n} value={n}>{n.toLocaleString()} / cohort</option>)}</select></div>
                <div><label className="text-xs uppercase tracking-wider text-slate-500">分析层</label><select value={mode} onChange={(e) => setMode(e.target.value as VersionComparisonAnalysisMode)} className="mt-2 min-h-11 w-full rounded-md border border-white/10 bg-slate-950 px-3 text-sm"><option value="raw_only">仅数据对比 · 不调用 LLM</option><option value="semantic">数据 + 语义对比</option></select></div>
                <div><label className="text-xs uppercase tracking-wider text-slate-500">语义总预算</label><select value={semanticBudget} onChange={(e) => setSemanticBudget(Number(e.target.value))} disabled={mode === 'raw_only'} className="mt-2 min-h-11 w-full rounded-md border border-white/10 bg-slate-950 px-3 text-sm disabled:opacity-40">{[1000,2000,4000,8000].map((n) => <option key={n} value={n}>{n.toLocaleString()} total</option>)}</select></div>
              </div>}
            </Card>

            {error && <div className="rounded-xl border border-rose-400/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-200">{error}</div>}

            {plan && <Card variant="glass">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div><p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Comparison contract</p><h2 className="mt-1 text-xl font-semibold text-white">{gameName || `App ${plan.app_id}`} · 四窗口方案</h2><p className="mt-1 text-sm text-slate-400">A = 较早版本，B = 较新版本；日期级事件自动排除更新当天。</p></div>
                <div className="flex gap-2"><Badge variant="default">{plan.window_days} 天主窗口</Badge><Badge variant={plan.confounder_risk === 'clean' ? 'success' : 'warning'}>{plan.confounder_risk === 'clean' ? '未发现窗口内事件干扰' : `${plan.confounders.length} 个窗口内事件`}</Badge></div>
              </div>
              <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{Object.entries(plan.cohorts).map(([key, value]) => <div key={key} className="rounded-xl border border-white/10 bg-black/20 p-4"><p className="text-xs font-medium text-cyan-200">{COHORT_LABELS[key as keyof typeof COHORT_LABELS]}</p><p className="mt-2 text-sm text-slate-300">{dateTime(value.start_time)} → {dateTime(value.end_time_exclusive)}</p><p className="mt-1 text-xs text-slate-500">{value.boundary_mode === 'event_day_excluded' ? '排除版本当天' : '按精确发布时间切分'}</p></div>)}</div>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4"><p className="text-xs leading-5 text-slate-500">语义样本：四组统一 language × relative day 配额；不平衡好评/差评。3/7/14 天原始敏感性会一并计算。</p><Button type="button" onClick={() => void start()} disabled={loading || !request}>{loading ? '正在准备…' : mode === 'raw_only' ? '开始数据对比' : '开始数据 + 语义对比'}</Button></div>
            </Card>}

            {run?.status === 'running' && <Card variant="glass"><div className="flex items-center gap-3"><span className="h-2.5 w-2.5 animate-pulse rounded-full bg-cyan-300"/><div><p className="font-medium text-white">{phaseText[run.phase || ''] || '正在执行版本对比'}</p><p className="mt-1 text-xs text-slate-500">Run {run.run_id.slice(0, 8)} · 本地缓存优先，缺口才访问 Steam</p></div></div></Card>}

            {metrics && raw && <>
              <Card variant="gradient">
                <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Version comparison report</p><h2 className="mt-1 text-2xl font-semibold text-white">{metrics.event_a.event_name} <span className="text-slate-600">vs</span> {metrics.event_b.event_name}</h2><p className="mt-2 text-sm text-slate-400">{metrics.event_a.event_date} → {metrics.event_b.event_date} · {metrics.window_days} 天主窗口</p></div><div className="flex gap-2"><Badge variant={metrics.coverage_status === 'COMPLETE' ? 'success' : 'warning'}>{metrics.coverage_status === 'COMPLETE' ? '完整 coverage' : '部分 coverage'}</Badge><Badge variant="default">{metrics.analysis_mode === 'raw_only' ? '无 LLM' : '语义可比样本'}</Badge></div></div>
                <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{cohortEntries.map(([key, value]) => <div key={key} className="rounded-xl border border-white/10 bg-black/20 p-4"><p className="text-xs font-medium text-slate-400">{COHORT_LABELS[key]}</p><div className="mt-4 flex items-end justify-between"><div><p className="text-3xl font-semibold text-white">{pct(value.recommendation_rate)}</p><p className="mt-1 text-xs text-slate-500">推荐率</p></div><div className="text-right text-xs text-slate-400"><p>{value.reviews.toLocaleString()} 评论</p><p className="mt-1">95% CI {pct(value.recommendation_ci95?.[0])}–{pct(value.recommendation_ci95?.[1])}</p></div></div></div>)}</div>
              </Card>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><DeltaTile label="版本 A 前→后" value={raw.deltas.a_pre_to_post_pp}/><DeltaTile label="版本 B 前→后" value={raw.deltas.b_pre_to_post_pp}/><DeltaTile label="B 后 − A 后" value={raw.deltas.b_post_minus_a_post_pp}/><DeltaTile label="相对变化 ΔΔ" value={raw.deltas.difference_in_differences_pp} emphasis/></div>

              <div className="grid gap-6 lg:grid-cols-2">
                <Card variant="glass"><p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Robustness</p><h3 className="mt-1 text-lg font-semibold text-white">3 / 7 / 14 天窗口敏感性</h3><div className="mt-4 space-y-3">{metrics.window_sensitivity.map((row) => <div key={row.window_days} className="grid grid-cols-[64px_1fr_1fr_1fr] items-center gap-2 rounded-lg border border-white/[0.07] bg-black/20 px-3 py-3 text-sm"><span className="font-medium text-white">{row.window_days} 天</span><span className="text-slate-400">ΔA {pp(row.a_pre_to_post_pp)}</span><span className="text-slate-400">ΔB {pp(row.b_pre_to_post_pp)}</span><span className="text-cyan-200">ΔΔ {pp(row.difference_in_differences_pp)}</span></div>)}</div></Card>
                <Card variant="glass"><p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Comparability</p><h3 className="mt-1 text-lg font-semibold text-white">样本构成可比性</h3><div className="mt-4 space-y-3">{Object.entries(metrics.comparability).map(([name, result]) => { const level = result.composition_comparability?.level || result.comparability?.level; return <div key={name} className="flex items-center justify-between rounded-lg border border-white/[0.07] bg-black/20 px-3 py-3"><span className="text-sm text-slate-300">{name.replaceAll('_', ' ')}</span><Badge variant={level === 'high' ? 'success' : level === 'low' ? 'warning' : 'default'}>{levelLabel(level)}</Badge></div>; })}</div><p className="mt-4 text-xs leading-5 text-slate-500">主语义样本只平衡语言与相对版本日；playtime 仅进入敏感性分析，不硬匹配。</p></Card>
              </div>

              {metrics.confounders.length > 0 && <Card variant="glass"><p className="text-xs uppercase tracking-[0.2em] text-amber-300">Confounder watch</p><h3 className="mt-1 text-lg font-semibold text-white">窗口内还有其他事件</h3><div className="mt-3 grid gap-2 md:grid-cols-2">{metrics.confounders.map((item, index) => <div key={`${item.event_id}-${index}`} className="rounded-lg border border-amber-400/20 bg-amber-950/20 p-3"><div className="flex justify-between gap-3"><p className="text-sm font-medium text-amber-100">{item.event_name || item.event_type}</p><Badge variant="warning">{item.severity}</Badge></div><p className="mt-1 text-xs text-amber-200/60">{item.event_date} · {item.event_type}</p></div>)}</div></Card>}

              {metrics.semantic_sample_manifest && <Card variant="glass"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-[0.2em] text-cyan-300">Semantic sample manifest</p><h3 className="mt-1 text-lg font-semibold text-white">统一可比语义样本</h3></div><Badge variant={metrics.semantic_sample_manifest.status === 'ready' ? 'success' : 'warning'}>{metrics.semantic_sample_manifest.status}</Badge></div><div className="mt-4 grid gap-3 md:grid-cols-4"><MetricTile label="总预算" value={metrics.semantic_sample_manifest.total_budget.toLocaleString()}/><MetricTile label="每组实际目标" value={metrics.semantic_sample_manifest.target_per_cohort.toLocaleString()}/><MetricTile label="共同 strata" value={metrics.semantic_sample_manifest.common_support_strata.length.toLocaleString()}/><MetricTile label="Outcome balance" value={metrics.semantic_sample_manifest.outcome_balanced ? '是' : '否'} note="推荐状态不会被强制配平"/></div></Card>}

              {metrics.semantic && <><TopicTable title="问题变化" rows={metrics.semantic.problems}/><TopicTable title="需求变化" rows={metrics.semantic.requests}/><TopicTable title="正向主题变化" rows={metrics.semantic.positives}/></>}

              <Card variant="glass"><p className="text-xs uppercase tracking-[0.2em] text-slate-500">Interpretation guardrail</p><p className="mt-2 text-sm leading-6 text-slate-400">ΔΔ 用于描述两个版本相对各自基线的变化差异，不是因果估计。Steam 评论来自自选择评论者；coverage 不完整、窗口内其他事件和玩家构成变化都会影响解释。</p>{metrics.warnings?.length > 0 && <div className="mt-3 space-y-1 text-xs text-slate-500">{metrics.warnings.map((warning) => <p key={warning}>• {warning}</p>)}</div>}</Card>
            </>}
          </div>
        </div>
      </PageTransition>
    </AppLayout>
  );
}
