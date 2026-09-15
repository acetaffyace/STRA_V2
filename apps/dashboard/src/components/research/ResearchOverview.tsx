'use client';

import { Card } from '@/components/ui/card';
import type { DashboardReadiness } from '@/lib/api';
import type { ResearchReport, SemanticStatus } from '@/types';
import { useLanguage } from '@/contexts/LanguageContext';

function safeStaleReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  const sanitized = reason.replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 160);
  if (!sanitized || /traceback|stack trace|exception|\berror\b| at \w+[./]/i.test(sanitized)) return null;
  return sanitized;
}

export function staleReasonLabel(reason: string | null | undefined, zh: boolean): string {
  const normalized = reason?.trim().toLowerCase() || '';
  const action = zh ? '重新运行分析可以生成基于当前评论的数据。' : 'Run the analysis again to use the current review pool.';
  if (normalized.includes('review pool changed')) {
    return zh ? `当前评论池与该报告生成时相比已经变化。${action}` : `The review pool changed since this report was generated. ${action}`;
  }
  if (normalized.includes('freshness') || normalized.includes('older') || normalized.includes('expired') || normalized.includes('age') || normalized.includes('threshold')) {
    return zh ? `该报告已超过当前的新鲜度阈值。${action}` : `This report is older than the current freshness threshold. ${action}`;
  }
  const detail = safeStaleReason(reason);
  return zh
    ? `该报告可能与当前数据不完全一致。${detail ? `原因：${detail}。` : ''}${action}`
    : `This report may no longer match the current data.${detail ? ` Reason: ${detail}.` : ''} ${action}`;
}

function formatDate(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return new Date(value * 1000).toLocaleDateString();
}

function formatCount(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—';
}

export function ResearchOverview({
  report,
  semanticStatus: _semanticStatus,
  readiness: _readiness,
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
  const population = report.population;
  const contract = population?.sampling_contract;
  const languages = contract?.languages?.length ? contract.languages.join(', ') : (zh ? '全部语言' : 'All languages');
  const start = population?.coverage_start_time ?? contract?.start_time;
  const end = population?.coverage_end_time ?? contract?.end_time;
  const complete = population?.collection_complete;
  const truncated = population?.truncated_by_max_reviews;

  let collectionLabel = zh ? '覆盖状态未知' : 'Coverage unknown';
  let collectionClass = 'border-slate-500/30 bg-slate-500/10 text-slate-300';
  if (complete === true) {
    collectionLabel = zh ? '采集完整' : 'Collection complete';
    collectionClass = 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200';
  } else if (truncated) {
    collectionLabel = zh ? '达到评论上限' : 'Review limit reached';
    collectionClass = 'border-amber-400/30 bg-amber-500/10 text-amber-200';
  } else if (complete === false) {
    collectionLabel = zh ? '采集未完整' : 'Collection incomplete';
    collectionClass = 'border-amber-400/30 bg-amber-500/10 text-amber-200';
  }

  return (
    <section className="mx-auto max-w-6xl px-4 pb-4" aria-label={zh ? '分析范围' : 'Analysis scope'}>
      <Card className="border-white/10 bg-slate-950/35 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-500">{zh ? '分析范围' : 'Analysis scope'}</p>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-200">
              <span>{formatDate(start)} – {formatDate(end)}</span>
              <span className="text-slate-700">·</span>
              <span>{formatCount(population?.review_count)} {zh ? '条评论' : 'reviews'}</span>
              <span className="text-slate-700">·</span>
              <span className="text-slate-400">{languages}</span>
            </div>
          </div>
          <span className={`w-fit rounded-full border px-3 py-1 text-xs ${collectionClass}`}>{collectionLabel}</span>
        </div>
        {stale && (
          <div className="mt-3 rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2 text-xs leading-5 text-amber-100">
            {staleReasonLabel(staleReason, zh)}
          </div>
        )}
      </Card>
    </section>
  );
}
