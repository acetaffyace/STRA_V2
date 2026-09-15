'use client';

import { Suspense, useEffect, useState, useCallback } from 'react';
import { AppLayout } from '@/components/AppLayout';
import { PageTransition } from '@/components/PageTransition';
import { ReviewsTab } from '@/components/database/tabs/ReviewsTab';
import { AcquisitionSetupDialog } from '@/components/analysis/AcquisitionSetupDialog';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/contexts/LanguageContext';
import { useStarredGames } from '@/contexts/StarredGamesContext';
import {
  fetchDatabaseStats,
  fetchDatabaseGames,
  deleteGame,
  clearEntireDatabase,
} from '@/lib/api';
import { collectReviews } from '@/lib/acquisitionApi';
import type { SamplingContract } from '@/types/acquisition';
import type { DatabaseGameOption } from '@/types';
import type { DatabaseStats } from '@/lib/api';

export default function DatabasePage() {
  const { t } = useLanguage();
  const { refresh: refreshStarred } = useStarredGames();

  const [stats, setStats] = useState<DatabaseStats | null>(null);
  const [games, setGames] = useState<DatabaseGameOption[]>([]);
  const [loadingStats, setLoadingStats] = useState(true);
  const [collectorOpen, setCollectorOpen] = useState(false);
  const [collectorBusy, setCollectorBusy] = useState(false);
  const [collectorAppId, setCollectorAppId] = useState<number | null>(null);
  const [collectorMessage, setCollectorMessage] = useState<string | null>(null);
  const [collectorError, setCollectorError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoadingStats(true);
    try {
      const [newStats, newGames] = await Promise.all([
        fetchDatabaseStats(),
        fetchDatabaseGames(),
      ]);
      setStats(newStats);
      setGames(newGames);
      if (collectorAppId == null && newGames.length > 0) {
        setCollectorAppId(newGames[0].app_id);
      }
    } catch (err) {
      console.error('Failed to load database data:', err);
    } finally {
      setLoadingStats(false);
    }
  }, [collectorAppId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function handleDeleteGame(appId: number) {
    await deleteGame(appId);
    await Promise.all([loadData(), refreshStarred()]);
  }

  async function handleClearDatabase() {
    await clearEntireDatabase();
    await Promise.all([loadData(), refreshStarred()]);
  }

  async function handleCollect(sampling: SamplingContract) {
    setCollectorBusy(true);
    setCollectorError(null);
    setCollectorMessage(null);
    try {
      const result = await collectReviews(sampling, { force: true });
      const fastPath = result.stats?.targeted_date_applied === true ? ' · 历史时间窗直达已验证' : '';
      setCollectorMessage(
        `已保存 ${result.matched_count.toLocaleString()} 条匹配评论；Steam 本次返回 ${result.fetched_count.toLocaleString()} 条${fastPath}`,
      );
      setCollectorOpen(false);
      await loadData();
    } catch (err) {
      setCollectorError(err instanceof Error ? err.message : '评论爬取失败');
    } finally {
      setCollectorBusy(false);
    }
  }

  const statItems = [
    { label: t('common.games'), value: stats?.games },
    { label: t('common.reviews'), value: stats?.reviews },
    { label: t('common.labels'), value: stats?.labels },
  ];
  const collectorGame = games.find((game) => game.app_id === collectorAppId);

  return (
    <AppLayout>
      <PageTransition>
        <div className="mx-auto max-w-[1440px] space-y-6 px-4 py-6 sm:px-6 sm:py-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-white">
                {t('database.title')}
              </h1>
              <p className="mt-1 text-sm text-slate-400">{t('database.subtitle')}</p>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-3">
              {statItems.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center gap-2 rounded-xl border border-white/10 bg-slate-900/50 px-3 py-1.5"
                >
                  <span className="text-[10px] uppercase tracking-wider text-slate-500">
                    {item.label}
                  </span>
                  <span className="text-sm font-medium text-white">
                    {loadingStats ? '...' : (item.value ?? 0).toLocaleString()}
                  </span>
                </div>
              ))}
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setCollectorError(null);
                  setCollectorMessage(null);
                  setCollectorOpen(true);
                }}
                disabled={games.length === 0}
              >
                爬取评论
              </Button>
            </div>
          </div>

          <Card variant="glass" className="p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-white">本地评论数据</p>
                <p className="mt-1 text-xs text-slate-500">手动爬取只写入 SQLite，不调用 LLM；之后主分析和版本分析都可以复用。</p>
              </div>
              <select
                value={collectorAppId ?? ''}
                onChange={(event) => setCollectorAppId(event.target.value ? Number(event.target.value) : null)}
                className="min-w-[220px] rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 outline-none focus:border-sky-400/60"
              >
                {games.length === 0 && <option value="">暂无本地游戏</option>}
                {games.map((game) => (
                  <option key={game.app_id} value={game.app_id}>{game.name} · {game.review_count.toLocaleString()} 条</option>
                ))}
              </select>
            </div>
            {collectorMessage && <div className="mt-3 rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{collectorMessage}</div>}
            {collectorError && <div className="mt-3 rounded-xl border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{collectorError}</div>}
          </Card>

          <Suspense
            fallback={
              <Card variant="glass" className="p-6 text-sm text-slate-400">
                Loading reviews explorer...
              </Card>
            }
          >
            <ReviewsTab games={games} onDeleteGame={handleDeleteGame} onClearDatabase={handleClearDatabase} t={t} />
          </Suspense>

          {collectorAppId != null && (
            <AcquisitionSetupDialog
              open={collectorOpen}
              appId={collectorAppId}
              gameName={collectorGame?.name}
              mode="collect"
              busy={collectorBusy}
              onClose={() => !collectorBusy && setCollectorOpen(false)}
              onSubmit={handleCollect}
            />
          )}
        </div>
      </PageTransition>
    </AppLayout>
  );
}
