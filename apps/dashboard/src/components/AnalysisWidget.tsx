'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAnalysis } from '@/contexts/AnalysisContext';
import { buildDashboardRunUrl, buildVersionReviewRunUrl, fetchActiveAnalysisRuns, type AnalysisHistoryItem } from '@/lib/api';
import { SteamImage } from './SteamImage';
import clsx from 'clsx';
import { useLanguage } from '@/contexts/LanguageContext';

function formatRemainingTime(seconds: number | null | undefined, language: string) {
  if (seconds === undefined || seconds === null) {
    return null;
  }
  if (seconds <= 0) {
    return language === 'zh' ? '预计不到 1 分钟' : language === 'ja' ? '1分未満の見込み' : 'Less than 1 minute';
  }
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (language === 'zh') return `预计约 ${minutes} 分钟`;
  if (language === 'ja') return `約 ${minutes} 分の見込み`;
  return `About ${minutes} minute${minutes === 1 ? '' : 's'}`;
}

export function AnalysisWidget() {
  const { tasks, clearTask } = useAnalysis();
  const { language } = useLanguage();
  const ui = language === 'zh'
    ? { queue: '分析队列', expand: '展开', minimize: '最小化', cancel: '取消分析', remove: '移出队列', dismiss: '关闭', waiting: '排队中', another: '其他分析', fetching: '正在获取评论', fetched: '条评论', connecting: '正在连接 Steam API…', researchCore: '正在进行定量研究分析', classifying: '正在进行语义分类', analyzed: '条评论', preparingClassify: '正在准备分析…', building: '正在生成指标', aggregating: '正在整理语义洞察', finalizing: '正在保存分析结果', saving: '正在保存分析结果…', starting: '正在准备分析', preparing: '准备中…', remaining: '剩余时间', fetch: '获取', research: '定量研究', classify: '语义分类', insights: '洞察', save: '保存', complete: '分析完成', view: '查看结果' }
    : language === 'ja'
      ? { queue: '分析キュー', expand: '展開', minimize: '最小化', cancel: '分析をキャンセル', remove: 'キューから削除', dismiss: '閉じる', waiting: 'キューで待機中', another: '別の分析', fetching: 'Steamからレビューを取得中', fetched: '件取得済み', connecting: 'Steam APIに接続中…', researchCore: '定量研究を実行中', classifying: 'セマンティック分類中', analyzed: '件を分析済み', preparingClassify: '分類を準備中…', building: 'インサイトを作成中', aggregating: 'セマンティック洞察を整理中', finalizing: '分析結果を保存中', saving: '結果を保存中…', starting: '分析を開始中', preparing: '準備中…', remaining: '残り時間', fetch: '取得', research: '定量研究', classify: '分類', insights: '洞察', save: '保存', complete: '分析完了', view: '表示' }
      : { queue: 'Analysis Queue', expand: 'Expand', minimize: 'Minimize', cancel: 'Cancel analysis', remove: 'Remove from queue', dismiss: 'Dismiss', waiting: 'Waiting in queue', another: 'another analysis', fetching: 'Fetching reviews from Steam', fetched: 'reviews fetched', connecting: 'Connecting to Steam API...', researchCore: 'Running quantitative research', classifying: 'Classifying reviews semantically', analyzed: 'reviews analyzed', preparingClassify: 'Preparing classification...', building: 'Building insights', aggregating: 'Organizing semantic insights...', finalizing: 'Saving analysis result', saving: 'Saving results...', starting: 'Starting analysis', preparing: 'Preparing...', remaining: 'Est. remaining', fetch: 'Fetch', research: 'Research', classify: 'Classify', insights: 'Insights', save: 'Save', complete: 'Analysis complete', view: 'View' };
  const [isMinimized, setIsMinimized] = useState(false);
  const [remoteRuns, setRemoteRuns] = useState<AnalysisHistoryItem[]>([]);
  const [queueError, setQueueError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = () => fetchActiveAnalysisRuns()
      .then((items) => { if (!cancelled) { setRemoteRuns(items); setQueueError(null); } })
      .catch((error: unknown) => { if (!cancelled) setQueueError(error instanceof Error ? error.message : '分析队列无法连接到当前后端。'); });
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const activeTasks = Array.from(tasks.entries());
  const hasActiveTasks = activeTasks.length > 0 || remoteRuns.length > 0;

  if (!hasActiveTasks && !queueError) {
    return null;
  }

  return (
    <div className="fixed bottom-24 right-4 z-50 w-[calc(100vw-2rem)] max-w-[calc(100vw-2rem)] sm:bottom-6 sm:right-6 sm:w-96 sm:max-w-[calc(100vw-3rem)]">
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-900/95 shadow-2xl backdrop-blur">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 bg-slate-800/50 px-4 py-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white">
              {ui.queue} ({activeTasks.length + remoteRuns.length})
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsMinimized(!isMinimized)}
              className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-white"
              aria-label={isMinimized ? ui.expand : ui.minimize}
            >
              {isMinimized ? '↑' : '↓'}
            </button>
          </div>
        </div>

        {/* Task List */}
        {!isMinimized && (
          <div className="max-h-96 space-y-2 overflow-y-auto p-4">
            {queueError && (
              <div role="alert" className="rounded-xl border border-amber-400/30 bg-amber-950/40 p-3 text-xs text-amber-100">
                分析队列无法连接到当前后端：{queueError}
              </div>
            )}
            {activeTasks.map(([appId, task]) => {
              const remainingLabel = task.progress
                ? formatRemainingTime(task.progress.remainingSeconds, language)
                : null;
              return (
                <div
                key={appId}
                className="flex items-start gap-3 rounded-xl border border-white/10 bg-slate-800/30 p-3"
              >
                <SteamImage
                  appId={task.game.appid}
                  variant="capsule"
                  alt={task.game.name}
                  className="h-12 w-20 flex-shrink-0 rounded object-cover"
                  imageUrl={task.game.image_url}
                />

                <div className="flex-1 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-white line-clamp-1">
                      {task.game.name}
                    </p>
                    {(task.status === 'completed' || task.status === 'analyzing' || task.status === 'queued') && (
                      <button
                        onClick={() => clearTask(appId)}
                        className="flex-shrink-0 rounded p-0.5 text-slate-400 hover:bg-rose-500/20 hover:text-rose-400"
                        title={task.status === 'analyzing' ? ui.cancel : task.status === 'queued' ? ui.remove : ui.dismiss}
                      >
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    )}
                  </div>

                  {/* Status */}
                  {task.status === 'queued' && (
                    <div className="space-y-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-amber-300">
                          {ui.waiting}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400">
                        {language === 'zh' ? `等待${task.waitingFor ?? ui.another}完成… · 目标最多 ${task.requestedLimit} 条` : language === 'ja' ? `${task.waitingFor ?? ui.another}の完了を待機中… · 最大 ${task.requestedLimit} 件` : `Waiting for ${task.waitingFor ?? ui.another} to finish... · up to ${task.requestedLimit}`}
                      </p>
                      <div className="h-1.5 overflow-hidden rounded-full bg-slate-700">
                        <div
                          className="h-full w-full bg-gradient-to-r from-amber-500/40 to-amber-500/20 animate-pulse"
                        />
                      </div>
                    </div>
                  )}

                  {task.status === 'analyzing' && (
                    <div className="space-y-1.5">
                      {/* Phase indicator with step number */}
                      {(() => {
                        const phase = task.progress?.run_phase || task.progress?.phase;
                        const total = task.progress?.total ?? 0;
                        const processed = task.progress?.processed ?? 0;
                        const fetchedCount = task.progress?.fetched_count ?? 0;
                        // Determine current step and label
                        let stepNumber = 1;
                        let stepLabel = '';
                        let stepDetail = '';
                        let showProgress = false;

                        let pipelineLabels = [ui.fetch, ui.classify, ui.insights, ui.save];
                        if (phase === 'ingesting' || phase === 'fetching' || (!phase && total === 0 && !task.progress)) {
                          stepNumber = 1;
                          stepLabel = ui.fetching;
                          stepDetail = fetchedCount > 0 ? (language === 'zh' ? `已获取 ${fetchedCount} 条 / 目标最多 ${task.requestedLimit} 条` : `${fetchedCount} ${ui.fetched}`) : (language === 'zh' ? `目标最多 ${task.requestedLimit} 条` : ui.connecting);
                        } else if (phase === 'research_core') {
                          stepNumber = 2;
                          stepLabel = ui.researchCore;
                          stepDetail = language === 'zh' ? 'Research Core 正在整理观测总体、推荐率与评论活动' : 'Assembling population, recommendation, and activity evidence';
                          pipelineLabels = [ui.fetch, ui.research, ui.save];
                        } else if (phase === 'classifying' || (!phase && processed < total)) {
                          stepNumber = 2;
                          stepLabel = ui.classifying;
                          stepDetail = total > 0 ? `${language === 'zh' ? '正在分析评论 · ' : ''}${processed} / ${total} ${ui.analyzed}` : ui.preparingClassify;
                          showProgress = total > 0;
                        } else if (phase === 'aggregating' || phase === 'building_insights') {
                          stepNumber = 3;
                          stepLabel = ui.building;
                          stepDetail = ui.aggregating;
                        } else if (phase === 'finalizing' || phase === 'summarizing' || phase === 'idle' && total > 0) {
                          // Only show "Finalizing" when total > 0, meaning
                          // classification actually happened and is wrapping up.
                          stepNumber = 4;
                          stepLabel = ui.finalizing;
                          stepDetail = ui.saving;
                        } else {
                          // Fallback - either initial state or unknown phase
                          stepNumber = 1;
                          stepLabel = ui.starting;
                          stepDetail = ui.preparing;
                        }

                        return (
                          <>
                            {/* Step indicator */}
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-medium text-slate-200">
                                {stepLabel}
                              </span>
                            </div>

                            {/* Detail text */}
                            <p className="text-[11px] text-slate-400">
                              {stepDetail}
                            </p>
                            {/* Progress bar for classification phase */}
                            {showProgress && (
                              <div className="h-1.5 overflow-hidden rounded-full bg-slate-700">
                                <div
                                  className="h-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-300"
                                  style={{
                                    width: `${(processed / total) * 100}%`,
                                  }}
                                />
                              </div>
                            )}

                            {/* Time estimate */}
                            {remainingLabel && showProgress && (task.progress?.processed ?? 0) >= 30 && (
                              <p className="text-[11px] tracking-wide text-slate-400">
                                {ui.remaining}:{' '}
                                <span className="font-mono text-slate-200">{remainingLabel}</span>
                              </p>
                            )}

                            {/* Pipeline steps overview */}
                            <div className="flex items-center gap-1 pt-1">
                              {pipelineLabels.map((_, index) => index + 1).map((step) => (
                                <div
                                  key={step}
                                  className={clsx(
                                    'h-1 flex-1 rounded-full transition-colors',
                                    step < stepNumber && 'bg-sky-500',
                                    step === stepNumber && 'bg-sky-500 animate-pulse',
                                    step > stepNumber && 'bg-slate-700'
                                  )}
                                />
                              ))}
                            </div>
                            <div className="flex justify-between text-[9px] text-slate-500">
                              {pipelineLabels.map((label) => <span key={label}>{label}</span>)}
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  )}

                  {task.status === 'completed' && (
                    <div className="flex items-center gap-2 text-xs text-emerald-400">
                      <span>{ui.complete} · {task.result?.metadata.analysis_population_count ?? task.result?.metadata.retrieved ?? task.progress?.analysis_population_count ?? task.requestedLimit} {language === 'zh' ? '条评论' : 'reviews'}</span>
                      <Link
                        href={`/dashboard?game=${appId}`}
                        className="ml-auto text-sky-400 hover:text-sky-300 hover:underline"
                      >
                        {ui.view}
                      </Link>
                    </div>
                  )}

                        {task.status === 'error' && (
                          <div className="mt-1 rounded-md border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5 text-xs text-rose-400">
                            {task.error}
                          </div>
                        )}
                      </div>
                    </div>
              );
            })}
            {remoteRuns.filter((run) => !activeTasks.some(([, task]) => task.progress?.run_id === run.run_id || task.result?.run_id === run.run_id)).map((run) => {
              const phase = run.phase || 'resolving_events';
              const isVersionReview = run.run_type === 'version_review';
              const phaseLabel = isVersionReview
                ? phase === 'fetching_historical_reviews' ? '正在补抓历史评论' : phase === 'building_windows' ? '正在构造版本窗口' : phase === 'classifying_version_a' ? '正在分析版本 A' : phase === 'classifying_version_b' ? '正在分析版本 B' : phase === 'comparing' ? '正在生成版本对比' : phase === 'finalizing' ? '正在保存版本复盘' : '正在准备版本复盘'
                : phase === 'fetching' || phase === 'ingesting' ? '正在获取评论' : phase === 'classifying' ? '正在分析评论' : phase === 'summarizing' ? '正在生成分析结果' : '正在准备常规分析';
              const contract = (run.metrics?.population_contract || {}) as Record<string, unknown>;
              const current = Number(contract.classified_count ?? 0);
              const total = Number(run.requested_review_count ?? run.analysis_population_count ?? 0);
              return (
                <div key={run.run_id} className="flex items-start gap-3 rounded-xl border border-cyan-400/20 bg-slate-800/30 p-3">
                  <SteamImage appId={run.app_id} variant="capsule" alt={run.app_name} className="h-12 w-20 flex-shrink-0 rounded object-cover" />
                  <div className="flex-1 space-y-1.5"><div className="flex items-start justify-between gap-2"><p className="text-sm font-medium text-white line-clamp-1">{run.app_name}</p><span className="text-[10px] text-cyan-300">{isVersionReview ? '版本复盘' : '常规分析'}</span></div><p className="text-xs text-cyan-200">{phaseLabel}</p><p className="text-[11px] text-slate-400">{total > 0 ? `${current} / ${total}` : '正在准备分析方案…'}</p><div className="h-1.5 overflow-hidden rounded-full bg-slate-700"><div className="h-full bg-gradient-to-r from-cyan-500 to-indigo-500 transition-all" style={{ width: `${total > 0 ? Math.min(100, current / total * 100) : 25}%` }} /></div><Link href={isVersionReview ? buildVersionReviewRunUrl(run.run_id) : buildDashboardRunUrl(run.app_id, run.run_id)} className="text-[11px] text-sky-400 hover:underline">查看运行</Link></div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
