'use client';

import { useEffect, useMemo, useState } from 'react';
import { Portal } from '@/components/Portal';
import { Button } from '@/components/ui/button';
import { LANGUAGE_OPTIONS } from '@/lib/languageOptions';
import type { CollectionOrder, PurchaseType, ReviewType, SamplingContract } from '@/types/acquisition';

type RangePreset = '7d' | '30d' | '90d' | 'custom' | 'all';

export interface AcquisitionSetupDialogProps {
  open: boolean;
  appId: number;
  gameName?: string;
  mode: 'analysis' | 'collect';
  busy?: boolean;
  onClose: () => void;
  onSubmit: (sampling: SamplingContract) => void | Promise<void>;
}

function startOfUtcDay(date: string): number | null {
  if (!date) return null;
  const value = Date.parse(`${date}T00:00:00.000Z`);
  return Number.isFinite(value) ? Math.floor(value / 1000) : null;
}

function endOfUtcDay(date: string): number | null {
  if (!date) return null;
  const value = Date.parse(`${date}T23:59:59.999Z`);
  return Number.isFinite(value) ? Math.floor(value / 1000) : null;
}

function dateInputValue(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function presetRange(preset: RangePreset): { start: string; end: string } {
  if (preset === 'all' || preset === 'custom') return { start: '', end: '' };
  const end = new Date();
  const start = new Date(end);
  const days = preset === '7d' ? 7 : preset === '30d' ? 30 : 90;
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return { start: dateInputValue(start), end: dateInputValue(end) };
}

export function AcquisitionSetupDialog({
  open,
  appId,
  gameName,
  mode,
  busy = false,
  onClose,
  onSubmit,
}: AcquisitionSetupDialogProps) {
  const [rangePreset, setRangePreset] = useState<RangePreset>('30d');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [languages, setLanguages] = useState<string[]>(['all']);
  const [reviewType, setReviewType] = useState<ReviewType>('all');
  const [purchaseType, setPurchaseType] = useState<PurchaseType>('all');
  const [collectionOrder, setCollectionOrder] = useState<CollectionOrder>('recent');
  const [includeOfftopic, setIncludeOfftopic] = useState(false);
  const [maxReviews, setMaxReviews] = useState(mode === 'analysis' ? 1000 : 2000);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const range = presetRange('30d');
    setRangePreset('30d');
    setStartDate(range.start);
    setEndDate(range.end);
    setLanguages(['all']);
    setReviewType('all');
    setPurchaseType('all');
    setCollectionOrder('recent');
    setIncludeOfftopic(false);
    setMaxReviews(mode === 'analysis' ? 1000 : 2000);
    setShowAdvanced(false);
    setError(null);
  }, [open, mode, appId]);

  useEffect(() => {
    if (rangePreset === 'custom') return;
    const range = presetRange(rangePreset);
    setStartDate(range.start);
    setEndDate(range.end);
  }, [rangePreset]);

  const hasTimeWindow = rangePreset !== 'all';
  const effectiveOrder: CollectionOrder = hasTimeWindow ? 'recent' : collectionOrder;

  const selectedLanguageLabels = useMemo(() => {
    return languages.map((value) => LANGUAGE_OPTIONS.find((item) => item.value === value)?.label ?? value);
  }, [languages]);

  if (!open) return null;

  const toggleLanguage = (value: string) => {
    setLanguages((current) => {
      if (value === 'all') return ['all'];
      const withoutAll = current.filter((item) => item !== 'all');
      if (withoutAll.includes(value)) {
        const next = withoutAll.filter((item) => item !== value);
        return next.length ? next : ['all'];
      }
      return [...withoutAll, value];
    });
  };

  const submit = async () => {
    setError(null);
    const startTime = hasTimeWindow ? startOfUtcDay(startDate) : null;
    const endTime = hasTimeWindow ? endOfUtcDay(endDate) : null;
    if (hasTimeWindow && (startTime == null || endTime == null)) {
      setError('请选择完整的开始和结束日期。');
      return;
    }
    if (startTime != null && endTime != null && startTime > endTime) {
      setError('开始日期不能晚于结束日期。');
      return;
    }
    if (!Number.isInteger(maxReviews) || maxReviews < 1 || maxReviews > 10000) {
      setError('评论数量需要在 1–10,000 之间。');
      return;
    }

    const sampling: SamplingContract = {
      app_id: appId,
      start_time: startTime,
      end_time: endTime,
      languages,
      review_type: reviewType,
      purchase_type: purchaseType,
      collection_order: effectiveOrder,
      include_offtopic_activity: includeOfftopic,
      max_reviews: maxReviews,
    };
    await onSubmit(sampling);
  };

  return (
    <Portal>
      <div className="fixed inset-0 z-[10020] overflow-y-auto bg-black/65 backdrop-blur-md" onClick={busy ? undefined : onClose}>
        <div className="flex min-h-full items-center justify-center p-3 sm:p-6">
          <div
            className="w-full max-w-2xl rounded-2xl border border-white/15 bg-slate-950/95 p-5 shadow-2xl sm:p-6"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[11px] uppercase tracking-[0.25em] text-sky-400/80">
                  {mode === 'analysis' ? 'Analysis setup' : 'Review collection'}
                </p>
                <h2 className="mt-1 text-xl font-semibold text-white">
                  {mode === 'analysis' ? '设置分析范围' : '爬取 Steam 评论'}
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                  {gameName ?? `Steam App ${appId}`}
                </p>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={onClose}
                className="rounded-lg border border-white/10 px-2.5 py-1.5 text-sm text-slate-400 transition hover:border-white/20 hover:text-white disabled:opacity-40"
              >
                关闭
              </button>
            </div>

            <div className="mt-6 space-y-5">
              <section>
                <label className="text-xs font-medium uppercase tracking-wider text-slate-400">时间范围</label>
                <div className="mt-2 flex flex-wrap gap-2">
                  {([
                    ['7d', '最近 7 天'],
                    ['30d', '最近 30 天'],
                    ['90d', '最近 90 天'],
                    ['custom', '自定义'],
                    ['all', '不限时间'],
                  ] as const).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setRangePreset(value)}
                      className={`rounded-lg border px-3 py-2 text-xs transition ${
                        rangePreset === value
                          ? 'border-sky-400/50 bg-sky-500/15 text-sky-200'
                          : 'border-white/10 bg-white/[0.03] text-slate-400 hover:border-white/20 hover:text-slate-200'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {hasTimeWindow && (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <label className="text-xs text-slate-500">
                      开始日期
                      <input
                        type="date"
                        value={startDate}
                        onChange={(event) => { setStartDate(event.target.value); setRangePreset('custom'); }}
                        className="mt-1 w-full rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-sky-400/60"
                      />
                    </label>
                    <label className="text-xs text-slate-500">
                      结束日期
                      <input
                        type="date"
                        value={endDate}
                        onChange={(event) => { setEndDate(event.target.value); setRangePreset('custom'); }}
                        className="mt-1 w-full rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-sky-400/60"
                      />
                    </label>
                  </div>
                )}
              </section>

              <section>
                <div className="flex items-center justify-between gap-3">
                  <label className="text-xs font-medium uppercase tracking-wider text-slate-400">语言</label>
                  <span className="text-[11px] text-slate-500">{selectedLanguageLabels.join('、')}</span>
                </div>
                <div className="mt-2 flex max-h-36 flex-wrap gap-2 overflow-y-auto rounded-xl border border-white/10 bg-slate-900/40 p-3">
                  {LANGUAGE_OPTIONS.map((option) => {
                    const active = languages.includes(option.value);
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => toggleLanguage(option.value)}
                        className={`rounded-full border px-2.5 py-1.5 text-[11px] transition ${
                          active
                            ? 'border-sky-400/50 bg-sky-500/15 text-sky-200'
                            : 'border-white/10 text-slate-400 hover:border-white/20 hover:text-slate-200'
                        }`}
                      >
                        {option.label}
                      </button>
                    );
                  })}
                </div>
              </section>

              <section className="grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-slate-500">
                  {mode === 'analysis' ? '分析评论上限' : '本次最多采集'}
                  <select
                    value={maxReviews}
                    onChange={(event) => setMaxReviews(Number(event.target.value))}
                    className="mt-1 w-full rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-sky-400/60"
                  >
                    {[500, 1000, 2000, 5000, 10000].map((value) => (
                      <option key={value} value={value}>{`${value.toLocaleString()} 条`}</option>
                    ))}
                  </select>
                </label>
                <div className="rounded-xl border border-white/10 bg-slate-900/40 p-3 text-xs leading-5 text-slate-400">
                  {mode === 'analysis'
                    ? '点击开始后会先复用本地数据；覆盖不足时自动补抓，再进入现有统计和 LLM 分析。'
                    : '这里只保存评论，不运行 Research Core、LLM 分类或报告生成。'}
                </div>
              </section>

              <button
                type="button"
                onClick={() => setShowAdvanced((value) => !value)}
                className="text-xs text-slate-400 transition hover:text-sky-300"
              >
                {showAdvanced ? '收起高级选项 ↑' : '高级选项 →'}
              </button>

              {showAdvanced && (
                <section className="grid gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-4 sm:grid-cols-2">
                  <label className="text-xs text-slate-500">
                    推荐状态
                    <select value={reviewType} onChange={(e) => setReviewType(e.target.value as ReviewType)} className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-200">
                      <option value="all">全部</option>
                      <option value="positive">仅推荐</option>
                      <option value="negative">仅不推荐</option>
                    </select>
                  </label>
                  <label className="text-xs text-slate-500">
                    购买来源
                    <select value={purchaseType} onChange={(e) => setPurchaseType(e.target.value as PurchaseType)} className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-200">
                      <option value="all">全部</option>
                      <option value="steam">Steam 购买</option>
                      <option value="non_steam_purchase">非 Steam 购买</option>
                    </select>
                  </label>
                  <label className="text-xs text-slate-500">
                    排序方式
                    <select
                      value={effectiveOrder}
                      disabled={hasTimeWindow}
                      onChange={(e) => setCollectionOrder(e.target.value as CollectionOrder)}
                      className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-2 text-sm text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <option value="recent">发布时间</option>
                      <option value="updated">最近更新</option>
                      <option value="helpful">有用度</option>
                    </select>
                    {hasTimeWindow && <span className="mt-1 block text-[10px] text-slate-600">指定时间范围时固定为发布时间，以保证历史窗口边界可验证。</span>}
                  </label>
                  <label className="flex items-center gap-3 rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2.5 text-xs text-slate-400">
                    <input type="checkbox" checked={includeOfftopic} onChange={(e) => setIncludeOfftopic(e.target.checked)} />
                    包含 Steam 标记的异常 / off-topic activity
                  </label>
                </section>
              )}

              {error && <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{error}</div>}
            </div>

            <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button variant="secondary" onClick={onClose} disabled={busy}>取消</Button>
              <Button variant="primary" onClick={submit} disabled={busy}>
                {busy ? '处理中…' : mode === 'analysis' ? '开始分析' : '开始爬取'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Portal>
  );
}
