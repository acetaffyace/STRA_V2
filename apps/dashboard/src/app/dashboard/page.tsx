'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import LegacyDashboardPage from '@/components/dashboard/LegacyDashboardPage';
import { NewDashboardHome } from '@/components/dashboard/NewDashboardHome';

function DashboardRouter() {
  const searchParams = useSearchParams();
  const hasSavedView = Boolean(
    searchParams.get('game') || searchParams.get('run') || searchParams.get('view'),
  );

  // Keep the proven report/detail implementation intact while replacing the
  // landing/search flow with the explicit SamplingContract launcher.
  return hasSavedView ? <LegacyDashboardPage /> : <NewDashboardHome />;
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-400">Loading dashboard…</div>}>
      <DashboardRouter />
    </Suspense>
  );
}
