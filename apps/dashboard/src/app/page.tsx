'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { SentiNextLogo } from '@/components/SentiNextLogo';
import { apiUrl, fetchHealth, fetchRuntimeInfo } from '@/lib/api';
import { PRODUCT_NAME } from '@/lib/productIdentity';

const COSMETIC_MESSAGES = [
  '> INITIALIZING SYSTEM...',
  '> LOADING NEURAL CORE...',
];

const POLL_MS = 1_000;
const BOOT_TIMEOUT_MS = 60_000;
const BOOT_DIAGNOSTICS = process.env.NEXT_PUBLIC_BOOT_DIAGNOSTICS === '1';

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function isDesktopRuntime(): boolean {
  if (typeof window === 'undefined') return false;
  return window.location.protocol === 'tauri:' || window.location.hostname === 'tauri.localhost';
}

/** True once the desktop runtime has handed off the actual sidecar URL. */
function hasResolvedApiBase(): boolean {
  if (typeof window === 'undefined') return false;
  if (isDesktopRuntime()) return Boolean(window.__SENTINEXT_API_BASE__);
  if (window.__SENTINEXT_API_BASE__) return true;
  if (process.env.NEXT_PUBLIC_API_BASE_URL) return true;
  if (
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
    window.location.port !== '8000'
  ) return true; // Next.js dev server on any available local port
  return false;
}

function isLocalWebDevelopment(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
    window.location.port !== '8000'
  );
}

async function resolveDesktopApiBase(): Promise<{ resolved: boolean; invokeAvailable: boolean; result: string }> {
  if (!isDesktopRuntime()) return { resolved: hasResolvedApiBase(), invokeAvailable: false, result: 'web-runtime' };
  if (window.__SENTINEXT_API_BASE__) return { resolved: true, invokeAvailable: true, result: 'existing-global' };

  const internals = (window as Window & {
    __TAURI_INTERNALS__?: { invoke: (cmd: string) => Promise<unknown> };
  }).__TAURI_INTERNALS__;
  const globalTauri = (window as Window & {
    __TAURI__?: { core?: { invoke: (cmd: string) => Promise<unknown> } };
  }).__TAURI__;
  const invoke = globalTauri?.core?.invoke ?? internals?.invoke;
  if (!invoke) return { resolved: false, invokeAvailable: false, result: 'invoke-unavailable' };

  try {
    const base = await invoke('get_backend_url');
    if (typeof base === 'string' && base) {
      window.__SENTINEXT_API_BASE__ = base;
      return { resolved: true, invokeAvailable: true, result: 'success' };
    }
    return { resolved: false, invokeAvailable: true, result: 'invalid-result' };
  } catch {
    // Tauri is still initializing; the bounded boot loop will retry.
    return { resolved: false, invokeAvailable: true, result: 'invoke-rejected' };
  }
}

export default function RootPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<string[]>([]);
  const [showLogo, setShowLogo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [bootDiagnostics, setBootDiagnostics] = useState<string[]>([]);

  useEffect(() => {
    let active = true;

    const push = (msg: string) => {
      if (active) setMessages(prev => [...prev, msg]);
    };
    const diag = (msg: string) => {
      if (BOOT_DIAGNOSTICS && active) setBootDiagnostics(prev => [...prev, msg]);
    };

    async function boot() {
      // Phase 1: cosmetic boot messages
      for (const msg of COSMETIC_MESSAGES) {
        if (!active) return;
        push(msg);
        await sleep(200);
      }

      if (!active) return;
      diag(`runtime=${isDesktopRuntime() ? 'tauri' : 'web'}`);
      diag(`invoke_available=${Boolean((window as Window & { __TAURI__?: unknown }).__TAURI__)}`);

      // In local web development, entering the workspace must not be blocked
      // by a splash health loop. The dashboard has its own reconnect banner
      // and can still be used to inspect diagnostics when the API is down.
      if (isLocalWebDevelopment()) {
        setShowLogo(true);
        router.replace('/dashboard?view=home');
        return;
      }

      push('> CONNECTING TO BACKEND...');

      // Phase 2: wait for the authoritative Tauri URL handoff, then poll the
      // actual sidecar. Desktop never guesses /api.
      const startedAt = Date.now();
      while (active) {
        if (Date.now() - startedAt >= BOOT_TIMEOUT_MS) {
          setError('无法连接后端服务，请确认 API 正在运行后重试。');
          return;
        }

        // Check for Tauri sidecar boot error (fatal — process couldn't spawn)
        if (typeof window !== 'undefined' && window.__SENTINEXT_BACKEND_BOOT_ERROR__) {
          if (active) setError(window.__SENTINEXT_BACKEND_BOOT_ERROR__);
          return;
        }

        // Wait for a real API base URL (avoids tauri://localhost/api fetch failures)
        const handoff = await resolveDesktopApiBase();
        diag(`get_backend_url=${handoff.result}`);
        diag(`backend_url=${window.__SENTINEXT_API_BASE__ || 'unresolved'}`);
        if (!handoff.resolved) {
          await sleep(POLL_MS);
          continue;
        }

        try {
          diag(`health_request=start ${apiUrl('/health')}`);
          await fetchHealth();
          diag('health_request=success');
          try {
            const runtime = await fetchRuntimeInfo();
            diag(`runtime_info=success profile=${runtime.runtime_profile} port=${runtime.backend_port}`);
          } catch (runtimeError) {
            diag(`runtime_info=error ${runtimeError instanceof Error ? runtimeError.message : 'unknown'}`);
          }
          if (!active) return;
          push('> REVIEW ANALYSIS MODULE: ONLINE');
          await sleep(200);
          if (!active) return;
          push('> SYSTEM READY');
          setShowLogo(true);
          await sleep(500);
          if (active) router.replace('/dashboard?view=home');
          return;
        } catch (healthError) {
          diag(`health_request=error ${healthError instanceof Error ? healthError.message : 'unknown'}`);
          await sleep(POLL_MS);
        }
      }
    }

    boot();
    return () => { active = false; };
  }, [router, retryKey]);

  const handleRetry = () => {
    setError(null);
    setMessages([]);
    setShowLogo(false);
    setBootDiagnostics([]);
    setRetryKey(k => k + 1);
  };

  return (
    <div className="flex min-h-screen items-center justify-center relative overflow-hidden">
      {/* Grid background */}
      <div
        className="absolute inset-0 opacity-20"
        style={{
          backgroundImage: `
            linear-gradient(rgba(0, 255, 255, 0.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 255, 255, 0.1) 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
        }}
      />

      {/* Scan line effect */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'repeating-linear-gradient(0deg, rgba(0,0,0,0.1), rgba(0,0,0,0.1) 1px, transparent 1px, transparent 2px)',
        }}
      />

      {/* Content */}
      <div className="text-center space-y-8 z-10 p-8">
        {/* Boot sequence terminal */}
        <div className="text-left font-mono text-xs space-y-1 mb-12 min-h-[180px]">
          {messages.map((message, index) => (
            <div
              key={index}
              className={
                message.includes('ONLINE') || message.includes('ACTIVE') || message.includes('READY')
                  ? 'text-[rgb(0,255,136)]'
                  : 'text-[rgb(0,255,255)]/70'
              }
            >
              {message}
              {index === messages.length - 1 && !error && (
                <span className="inline-block w-2 h-4 bg-[rgb(0,255,255)] ml-1 animate-pulse" />
              )}
            </div>
          ))}
          {!error && !showLogo && (
            <p className="mt-3 text-xs text-[rgb(0,255,255)]/60 font-mono tracking-wider">
              正在启动本地分析服务…
            </p>
          )}
          {error && (
            <div className="mt-4 space-y-3">
              <div className="text-red-400">
                {'>'} ERROR: {error}
              </div>
              <button
                onClick={handleRetry}
                className="text-[rgb(0,255,255)] hover:text-white border border-[rgb(0,255,255)]/40 hover:border-[rgb(0,255,255)] px-3 py-1 text-xs font-mono transition-colors"
              >
                [ RETRY ]
              </button>
            </div>
          )}
          {BOOT_DIAGNOSTICS && bootDiagnostics.length > 0 && (
            <pre className="mt-4 max-w-[760px] whitespace-pre-wrap text-left text-[10px] text-amber-300/80">
              {bootDiagnostics.join('\n')}
            </pre>
          )}
        </div>

        {/* Logo */}
        <div
          className={`transition-all duration-700 ${
            showLogo ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
          }`}
        >
          {/* Icon */}
          <div className="mb-6">
            <SentiNextLogo size="lg" className="mx-auto" />
          </div>

          {/* Title */}
          <h1 className="text-5xl font-bold tracking-[0.3em] mb-4">
            <span className="text-white">
              {PRODUCT_NAME}
            </span>
          </h1>

          {/* Subtitle */}
          <p className="text-sm uppercase tracking-[0.4em] text-[rgb(0,255,255)]/50">
            Steam Reviews Analysis
          </p>

          {/* Loading bar */}
          <div className="mt-8 mx-auto w-64">
            <div className="h-[2px] bg-[rgb(0,255,255)]/20 overflow-hidden">
              <div className="h-full w-[30%] bg-gradient-to-r from-[rgb(0,255,255)] to-[rgb(255,0,128)] animate-loading-slide" />
            </div>
            <p className="mt-3 text-[10px] uppercase tracking-[0.3em] text-[rgb(0,255,255)]/40 font-mono">
              Entering System...
            </p>
          </div>
        </div>
      </div>

      {/* Corner decorations */}
      <div className="absolute top-8 left-8 w-16 h-16 border-t border-l border-[rgb(0,255,255)]/30" />
      <div className="absolute top-8 right-8 w-16 h-16 border-t border-r border-[rgb(0,255,255)]/30" />
      <div className="absolute bottom-8 left-8 w-16 h-16 border-b border-l border-[rgb(255,0,128)]/30" />
      <div className="absolute bottom-8 right-8 w-16 h-16 border-b border-r border-[rgb(255,0,128)]/30" />
    </div>
  );
}
