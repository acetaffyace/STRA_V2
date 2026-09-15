'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AppLayout } from '@/components/AppLayout';
import { PageTransition } from '@/components/PageTransition';
import { AcquisitionSetupDialog } from '@/components/analysis/AcquisitionSetupDialog';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useAnalysis } from '@/contexts/AnalysisContext';
import { searchGames } from '@/lib/api';
import type { SearchResult } from '@/types';
import type { SamplingContract } from '@/types/acquisition';

function phaseLabel(phase?: string | null): string {
  switch (phase) {
    case 'fetching': return '正在补充 Steam 评论';
    case 'ingesting': return '正在写入本地数据';
    case 'research_core': return '正在计算统计指标';
    case 'classifying': return '正在进行 LLM 评论分类';
    case 'building_insights':
    case 'aggregating': return '正在整理分析结果';
    case 'finalizing': return '正在生成报告';
    default: return '正在准备分析';
  }
}

export function NewDashboardHome() {
  const router = useRouter();
  const { startAnalysis, getTask, tasks } = useAnalysis();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [setupGame, setSetupGame] = useState<SearchResult | null>(null);
  const [activeGame, setActiveGame] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeTask = activeGame ? getTask(activeGame.appid) : undefined;
  const activeProgress = activeTask?.progress;
  const progressPercent = useMemo(() => {
    if (!activeProgress?.total || activeProgress.total <= 0) return null;
    return Math.max(0, Math.min(100, Math.round((activeProgress.processed / activeProgress.total) * 100)));
  }, [activeProgress]);

  useEffect(() => {
    if (!activeGame || !activeTask) return;
    if (activeTask.status === 'completed') {
      router.push(`/dashboard?game=${encodeURIComponent(activeGame.appid)}`);
    }
  }, [activeGame, activeTask, router]);

  async function runSearch() {
    const value = query.trim();
    if (!value) return;
    setSearching(true);
    setError(null);
    try {
      const items = await searchGames(value);
      setResults(items);
      if (!items.length) setError('没有找到匹配的 Steam 游戏。');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Steam 游戏搜索失败。');
    } finally {
      setSearching(false);
    }
  }

  async function startConfiguredAnalysis(sampling: SamplingContract) {
    if (!setupGame) return;
    const game = setupGame;
    setSetupGame(null);
    setActiveGame(game);
    setError(null);
    try {
      await startAnalysis(game, {
        refresh: true,
        persist: true,
        review_count: sampling.max_reviews,
        language: sampling.languages[0] ?? 'all',
        languages: sampling.languages,
        filter: sampling.collection_order,
        sampling,
        output_language: 'zh',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动分析。');
    }
  }

  const runningTasks = Array.from(tasks.values()).filter((task) => task.status === 'analyzing' || task.status === 'queued');

  return (
    <AppLayout>
      <PageTransition>
        <main className="mx-auto min-h-[calc(100vh-5rem)] max-w-6xl px-4 py-8 sm:px-6 lg:py-12">
          <section className="relative overflow-hidden rounded-[28px] border border-white/10 bg-slate-950/75 px-5 py-8 shadow-2xl backdrop-blur-xl sm:px-8 sm:py-10">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(56,189,248,0.10),transparent_32%),radial-gradient(circle_at_80%_0%,rgba(99,102,241,0.10),transparent_28%)]" />
            <div className="relative mx-auto max-w-3xl text-center">
              <p className="text-[11px] font-medium uppercase tracking-[0.3em] text-sky-400/80">Steam Review Intelligence</p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">从一个时间窗口开始分析</h1>
              <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-400">
                选择游戏后直接设置时间、语言和评论范围。STRA 会优先复用本地数据，缺失时自动补抓，再进入统计和 LLM 分析。
              </p>

              <div className="mx-auto mt-7 flex max-w-2xl gap-2 rounded-2xl border border-white/10 bg-slate-900/70 p-2 shadow-inner">
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => { if (event.key === 'Enter') void runSearch(); }}
                  placeholder="输入游戏名、Steam App ID 或商店链接"
                  className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm text-white outline-none placeholder:text-slate-600"
                />
                <Button variant="primary" onClick={() => void runSearch()} disabled={searching}>
                  {searching ? '搜索中…' : '搜索'}
                </Button>
              </div>
            </div>
          </section>

          {error && (
            <div className="mt-5 rounded-2xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}</div>
          )}

          {activeGame && activeTask && (activeTask.status === 'analyzing' || activeTask.status === 'queued' || activeTask.status === 'error') && (
            <Card variant="glass" className="mt-6 overflow-hidden p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex min-w-0 items-center gap-3">
                  {activeGame.image_url ? (
                    <img src={activeGame.image_url} alt="" className="h-12 w-20 rounded-lg object-cover ring-1 ring-white/10" />
                  ) : (
                    <div className="h-12 w-20 rounded-lg bg-slate-800" />
                  )}
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-white">{activeGame.name}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {activeTask.status === 'queued'
                        ? `等待 ${activeTask.waitingFor ?? '当前任务'} 完成`
                        : activeTask.status === 'error'
                          ? activeTask.error
                          : phaseLabel(activeProgress?.phase)}
                    </p>
                  </div>
                </div>
                {activeTask.status !== 'error' && (
                  <div className="text-right">
                    <p className="text-xs text-slate-500">目标范围</p>
                    <p className="text-sm font-medium text-slate-200">{activeTask.requestedLimit === 0 ? '不限数量' : `${activeTask.requestedLimit.toLocaleString()} 条`}</p>
                  </div>
                )}
              </div>
              {activeTask.status === 'analyzing' && (
                <div className="mt-4">
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-400 transition-all duration-500"
                      style={{ width: `${progressPercent ?? 12}%` }}
                    />
                  </div>
                  <div className="mt-2 flex justify-between text-[11px] text-slate-600">
                    <span>{activeProgress?.fetched_count ? `已获取 ${activeProgress.fetched_count.toLocaleString()} 条` : '本地缓存与 Steam 自动协调'}</span>
                    <span>{progressPercent != null ? `${progressPercent}%` : '处理中'}</span>
                  </div>
                </div>
              )}
            </Card>
          )}

          {results.length > 0 && (
            <section className="mt-7">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-medium text-slate-300">搜索结果</h2>
                <span className="text-xs text-slate-600">选择游戏后设置分析范围</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {results.map((game) => {
                  const task = getTask(game.appid);
                  const busy = task?.status === 'analyzing' || task?.status === 'queued';
                  return (
                    <Card key={game.appid} variant="glass" className="group overflow-hidden p-0 transition hover:border-sky-400/25">
                      <div className="flex min-h-28 gap-4 p-4">
                        {game.image_url ? (
                          <img src={game.image_url} alt="" className="h-24 w-36 flex-none rounded-xl object-cover ring-1 ring-white/10" />
                        ) : (
                          <div className="h-24 w-36 flex-none rounded-xl bg-slate-800" />
                        )}
                        <div className="flex min-w-0 flex-1 flex-col">
                          <div>
                            <h3 className="line-clamp-2 text-sm font-medium text-white">{game.name}</h3>
                            <p className="mt-1 text-[11px] text-slate-600">Steam App {game.appid}</p>
                          </div>
                          <div className="mt-auto flex items-center justify-between gap-3 pt-3">
                            <span className="truncate text-xs text-slate-500">{game.price ?? 'Steam'}</span>
                            <Button variant="primary" size="sm" disabled={busy} onClick={() => setSetupGame(game)}>
                              {busy ? '分析中' : '分析'}
                            </Button>
                          </div>
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            </section>
          )}

          {!results.length && !searching && (
            <section className="mt-7 grid gap-3 md:grid-cols-3">
              {[
                ['按时间定位', '可以直接选择旧版本附近的历史窗口，不要求先把中间年份全部抓下来。'],
                ['本地自动复用', '已经采集过的评论会优先从 SQLite 使用，重复分析不必重复下载。'],
                ['成本留给分析', '评论采集本身不调用 LLM，只有真正的语义分类和报告阶段才使用模型。'],
              ].map(([title, body]) => (
                <Card key={title} variant="glass" className="p-4">
                  <p className="text-sm font-medium text-slate-200">{title}</p>
                  <p className="mt-2 text-xs leading-5 text-slate-500">{body}</p>
                </Card>
              ))}
            </section>
          )}

          {runningTasks.length > 1 && (
            <p className="mt-4 text-center text-[11px] text-slate-600">当前共有 {runningTasks.length} 个分析任务（按队列顺序执行）。</p>
          )}

          {setupGame && (
            <AcquisitionSetupDialog
              open
              appId={setupGame.appid}
              gameName={setupGame.name}
              mode="analysis"
              onClose={() => setSetupGame(null)}
              onSubmit={startConfiguredAnalysis}
            />
          )}
        </main>
      </PageTransition>
    </AppLayout>
  );
}
