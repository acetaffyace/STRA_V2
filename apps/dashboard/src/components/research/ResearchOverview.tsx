'use client';

import Link from 'next/link';
import { Card } from '@/components/ui/card';
import type { DashboardReadiness } from '@/lib/api';
import type { ResearchReport, SemanticStatus } from '@/types';
import { useLanguage } from '@/contexts/LanguageContext';

function percent(value: number | null | undefined, digits = 1): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${(value * 100).toFixed(digits)}%`
    : '—';
}

function count(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—';
}

function dateOrDash(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return new Date(value * 1000).toLocaleDateString();
}

function statusLabel(status: string | undefined, zh: boolean): string {
  if (status === 'available') return zh ? '就绪' : 'READY';
  if (status === 'unavailable') return zh ? '不可用' : 'UNAVAILABLE';
  if (status === 'failed') return zh ? '未完成' : 'FAILED';
  if (status === 'pending') return zh ? '处理中' : 'PENDING';
  return status ? status.toUpperCase() : (zh ? '未知' : 'UNKNOWN');
}

function semanticReason(reason: string | null | undefined, zh: boolean): string {
  if (!zh) {
    if (reason === 'no_provider') return 'No semantic provider is configured. Quantitative research completed normally.';
    if (reason === 'no_api_key') return 'The semantic provider has no API key. Quantitative research is unaffected.';
    if (reason === 'invalid_configuration') return 'The semantic runtime configuration is unavailable. Quantitative research completed normally.';
    if (reason === 'no_reviews') return 'The requested research scope contained no reviews for semantic analysis.';
    if (reason === 'no_classifiable_reviews') return 'No review text was available for semantic classification.';
    if (reason === 'runtime_error') return 'Semantic analysis did not complete, but the quantitative Research Core result remains valid.';
    return 'Semantic analysis is unavailable for this result.';
  }
  if (reason === 'no_provider') return '未配置语义分析模型。定量研究结果已正常完成。';
  if (reason === 'no_api_key') return '当前语义模型缺少 API Key。定量研究结果不受影响。';
  if (reason === 'invalid_configuration') return '当前语义模型配置不可用。定量研究结果已正常完成。';
  if (reason === 'no_reviews') return '当前研究范围没有可用于语义分析的评论。';
  if (reason === 'no_classifiable_reviews') return '当前评论没有可进行语义分类的文本。';
  if (reason === 'runtime_error') return '语义分析本次未完成，但定量 Research Core 结果仍然有效。';
  return '语义分析当前不可用，定量研究结果仍然有效。';
}

export function ResearchOverview({
  report,
  semanticStatus,
  readiness,
  stale = false,
  staleReason,
}: {
  report: ResearchReport;
  semanticStatus?: SemanticStatus | null;
  readiness?: DashboardReadiness | null;
  stale?: boolean;
  staleReason?: string | null;
}) {
  const { language } = useLanguage();
  const zh = language === 'zh';
  const knownSnapshot = report.schema_version === 'research-report-v1' && report.mode === 'snapshot';
  const researchReady = readiness?.research_ready ?? knownSnapshot;
  const semanticReady = readiness?.semantic_ready ?? semanticStatus?.status === 'available';
  const semanticDisplayStatus = semanticStatus?.status ?? (semanticReady ? 'available' : undefined);
  const population = report.population;
  const recommendation = report.recommendation;
  const recommendationPopulation = recommendation?.population;
  const interval = recommendation?.model_based_interval;
  const validity = recommendation?.inference_validity;
  const activity = report.activity;
  const activityPopulation = activity?.population;
  const repetition = activity?.text_repetition;
  const activitySummary = activity?.summary;
  const spikes = activity?.spikes;
  const candidateComplete = activity?.methodology?.candidate_diagnostics?.candidate_generation_complete;
  const contract = population?.sampling_contract;
  const semanticUnavailable = !semanticReady && semanticStatus?.status !== 'pending';

  if (!knownSnapshot) {
    return (
      <section className="mx-auto max-w-6xl px-4 pb-6" aria-label="Research Core">
        <Card className="border-amber-400/30 bg-amber-500/5 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-amber-100">Research Core</p>
              <p className="mt-1 text-sm text-amber-200/80">
                {zh ? '此 Research Report 使用尚未支持的 schema 或分析模式。' : 'This Research Report uses an unsupported schema or analysis mode.'}
              </p>
            </div>
            <span className="rounded-full border border-amber-300/30 px-3 py-1 text-xs text-amber-200">
              {report.schema_version} · {report.mode}
            </span>
          </div>
        </Card>
      </section>
    );
  }

  const collectionLabel = population?.collection_complete === true
    ? (zh ? '完整' : 'Complete')
    : population?.collection_complete === false
      ? (population.truncated_by_max_reviews ? (zh ? '受上限截断' : 'Limited — truncated') : (zh ? '采集不完整' : 'Limited — incomplete'))
      : (zh ? '未知' : 'Unknown');
  const eligibilityLabel = validity?.inference_eligibility === 'model_based_only'
    ? (zh ? '完整请求总体' : 'Complete requested population')
    : validity?.inference_eligibility === 'limited'
      ? (zh ? '有限 — 采集受限' : 'Limited — incomplete acquisition')
      : (zh ? '未知来源' : 'Unknown provenance');

  return (
    <section className="mx-auto max-w-6xl space-y-4 px-4 pb-6" aria-label="Research Core overview">
      <Card className="border-cyan-400/20 bg-slate-950/50 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-cyan-300">Research Core</p>
            <h2 className="mt-1 text-xl font-semibold text-white">{zh ? '定量研究概览' : 'Quantitative Research Overview'}</h2>
          </div>
          <div className="flex flex-wrap gap-2 text-xs font-medium">
            <span className={`rounded-full border px-3 py-1 ${researchReady ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200' : 'border-slate-500/40 text-slate-300'}`}>
              Research Core · {researchReady ? (zh ? '就绪' : 'READY') : (zh ? '不可用' : 'UNAVAILABLE')}
            </span>
            <span className={`rounded-full border px-3 py-1 ${semanticReady ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200' : 'border-amber-400/40 bg-amber-500/10 text-amber-200'}`}>
              {zh ? '语义分析' : 'Semantic Analysis'} · {statusLabel(semanticDisplayStatus, zh)}
            </span>
          </div>
        </div>

        {stale && (
          <div role="status" className="mt-4 rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            {zh ? '已保存的分析与当前评论池不一致。请重新运行 Analyze 以创建新的可复现 Research Report。' : (staleReason || 'The stored analysis no longer matches the current review pool. Run Analyze again to create a new reproducible Research Report.')}
          </div>
        )}

        {semanticUnavailable && (
          <div role="status" className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-400/30 bg-sky-500/10 px-3 py-3 text-sm text-sky-100">
            <span>{semanticReason(semanticStatus?.reason, zh)}</span>
            {['no_provider', 'no_api_key', 'invalid_configuration'].includes(semanticStatus?.reason ?? '') && (
              <Link href="/settings" className="rounded-md border border-sky-300/40 px-3 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-400/10">
                {zh ? '配置语义分析' : 'Configure semantic analysis'}
              </Link>
            )}
          </div>
        )}

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard title={zh ? '观测评论数' : 'Observed Reviews'} value={count(population?.review_count)} />
          <MetricCard title={zh ? 'Steam 推荐率' : 'Recommendation Rate'} value={percent(recommendationPopulation?.recommendation_rate)} />
          <MetricCard title={`${zh ? '模型假设下的' : 'Model-based'} ${percent(interval?.confidence_level, 0)} ${zh ? '区间' : 'Interval'}`} value={`${percent(interval?.lower)} – ${percent(interval?.upper)}`} />
          <MetricCard title={zh ? '采集状态' : 'Collection Status'} value={collectionLabel} detail={eligibilityLabel} />
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="border-white/10 bg-slate-950/30 p-4 sm:p-5">
          <SectionTitle>{zh ? '总体 / 采样' : 'Population / Sampling'}</SectionTitle>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <Fact label={zh ? '语言' : 'Languages'} value={contract?.languages?.join(', ') || population?.sampling_contract?.languages?.join(', ') || '—'} />
            <Fact label={zh ? '评论类型' : 'Review type'} value={contract?.review_type || '—'} />
            <Fact label={zh ? '购买类型' : 'Purchase type'} value={contract?.purchase_type || '—'} />
            <Fact label={zh ? '采集顺序' : 'Collection order'} value={contract?.collection_order || '—'} />
            <Fact label={zh ? '请求上限' : 'Requested max'} value={contract?.max_reviews == null ? '—' : count(contract.max_reviews)} />
            <Fact label={zh ? '覆盖范围' : 'Coverage'} value={`${dateOrDash(population?.coverage_start_time)} – ${dateOrDash(population?.coverage_end_time)}`} />
            <Fact label={zh ? '覆盖状态' : 'Coverage status'} value={population?.coverage_status || '—'} />
            <Fact label={zh ? '完整采集' : 'Collection complete'} value={collectionLabel} />
            <Fact label={zh ? '停止原因' : 'Stop reason'} value={population?.stop_reason || '—'} />
          </div>
        </Card>

        <Card className="border-white/10 bg-slate-950/30 p-4 sm:p-5">
          <SectionTitle>{zh ? '推荐详情' : 'Recommendation Detail'}</SectionTitle>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <Fact label="valid_n" value={count(recommendationPopulation?.valid_n)} />
            <Fact label={zh ? '推荐' : 'Recommended'} value={count(recommendationPopulation?.recommended_n)} />
            <Fact label={zh ? '不推荐' : 'Not Recommended'} value={count(recommendationPopulation?.not_recommended_n)} />
            <Fact label={zh ? '缺失结果' : 'Missing'} value={count(recommendationPopulation?.missing_n)} />
          </div>
          <p className="mt-4 text-xs leading-5 text-slate-400">
            {interval?.method ? `${interval.method} · ${(interval.confidence_level == null ? 0.95 : interval.confidence_level * 100).toFixed(0)}%` : '—'}
            {' · '}{validity?.observed_metric_status || (zh ? '观测指标' : 'Observed metric')}
          </p>
          {validity?.reason && <p className="mt-2 text-xs text-slate-500">{validity.reason}</p>}
        </Card>
      </div>

      <Card className="border-white/10 bg-slate-950/30 p-4 sm:p-5">
        <SectionTitle>{zh ? '评论活动与表达完整性' : 'Review Activity & Expression Integrity'}</SectionTitle>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <MetricCard title={zh ? '唯一文本占比' : 'Unique Text Share'} value={percent(repetition?.unique_text_share)} />
          <MetricCard title={zh ? '完全重复占比' : 'Exact Duplicate Share'} value={percent(repetition?.exact_duplicate_share)} detail={`${count(repetition?.exact_duplicate_review_count)} ${zh ? '条属于重复文本组' : 'group members'}`} />
          <MetricCard title={zh ? '近似复制新增占比' : 'Near-Copy Additional Share'} value={percent(repetition?.near_copy_additional_share)} />
          <MetricCard title={zh ? '集中表达信号' : 'Coordinated Expression Share'} value={percent(repetition?.coordinated_expression_share)} detail={activitySummary?.coordinated_expression_level || '—'} />
          <MetricCard title={zh ? '活动峰值数量' : 'Activity Spike Count'} value={count(spikes?.spike_bin_count)} detail={activitySummary?.activity_spike_detected ? (zh ? '检测到评论量峰值' : 'Review-volume spike(s) detected') : undefined} />
        </div>
        <p className="mt-4 text-xs leading-5 text-slate-500">
          {count(activityPopulation?.raw_review_count)} {zh ? '条原始评论；' : 'raw reviews; '}
          {zh ? '完全重复评论属于重复文本组，未从 Research Core 总体中删除。文本相似与时间集中是描述性信号，不等同于垃圾评论、机器人或恶意刷评。' : 'exact duplicate members remain in the Research Core population. Text similarity and temporal concentration are descriptive signals, not spam, bot, or review-bombing claims.'}
        </p>
        {candidateComplete === false && (
          <p role="note" className="mt-3 rounded-md border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            {zh ? '近似复制检测的候选生成未完整完成；超大 LSH 桶被跳过，因此近似复制可能被低估。' : 'Near-copy candidate generation was incomplete; oversized LSH buckets were skipped, so near-copy detection may be underestimated.'}
          </p>
        )}
      </Card>

      <Card className="border-white/10 bg-slate-950/30 p-4 sm:p-5">
        <SectionTitle>{zh ? '方法与限制' : 'Methodology & Limitations'}</SectionTitle>
        <ul className="mt-3 grid gap-2 text-sm leading-6 text-slate-300 sm:grid-cols-2">
          <li>• {zh ? 'Steam 评论者是自选样本。' : 'Steam reviewers are self-selected.'}</li>
          <li>• {zh ? 'Steam 评论者不代表全部玩家。' : 'Steam reviewers are not all players.'}</li>
          <li>• {zh ? '推荐率不是文本情感。' : 'Recommendation is not text sentiment.'}</li>
          <li>• {zh ? '这是描述性、观察性分析，不是因果结论。' : 'This is observational and descriptive, not causal.'}</li>
          <li>• {zh ? '单个快照不能证明版本影响。' : 'A snapshot cannot establish version impact.'}</li>
        </ul>
      </Card>
    </section>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-slate-200">{children}</h3>;
}

function MetricCard({ title, value, detail }: { title: string; value: string; detail?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
      <p className="text-xs text-slate-400">{title}</p>
      <p className="mt-2 text-lg font-semibold text-white">{value}</p>
      {detail && <p className="mt-1 text-[11px] text-slate-500">{detail}</p>}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-white/[0.03] p-2.5">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="mt-1 break-words text-sm text-slate-200">{value}</p>
    </div>
  );
}
