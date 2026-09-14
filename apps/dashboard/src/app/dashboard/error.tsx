'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();

  useEffect(() => {
    // Keep the stack available during development without exposing it in the
    // ordinary user-facing error state.
    console.error('Dashboard render error', error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
      <section className="w-full max-w-lg rounded-xl border border-rose-400/30 bg-slate-900/80 p-6 shadow-2xl">
        <p className="text-xs uppercase tracking-[0.24em] text-rose-300">Dashboard error</p>
        <h1 className="mt-3 text-2xl font-semibold">无法显示分析结果</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">页面渲染时发生错误。分析数据仍保存在本地，可以重新加载或返回分析首页。</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <button type="button" onClick={() => reset()} className="rounded border border-sky-400/40 bg-sky-400/10 px-4 py-2 text-sm text-sky-200 hover:bg-sky-400/20">重新加载</button>
          <button type="button" onClick={() => router.push('/dashboard')} className="rounded border border-white/15 px-4 py-2 text-sm text-slate-300 hover:bg-white/5">返回分析首页</button>
        </div>
      </section>
    </main>
  );
}
