# Desktop Bootstrap Handoff Diagnostic

Status: `SENTINEXT_PORTFOLIO_RELEASE_V1_NO_GO` pending uninterrupted v9 WebView verification.

## Evidence from packaged debug candidate v8

The visible diagnostic panel proved:

| Stage | Result |
|---|---|
| Runtime detection | `runtime=tauri` — PASS |
| Tauri global API | `invoke_available=true` — PASS |
| Command call | `get_backend_url=success` — PASS |
| Returned value | `http://127.0.0.1:56963` — valid dynamic URL |
| WebView request construction | `health_request=start http://127.0.0.1:56963/health` — PASS |
| WebView health request | repeated network failure — FAIL |
| Runtime-info request | not reached because health never succeeded |

The sidecar on the same candidate was independently healthy on the dynamic port (`/health` HTTP 200 in approximately 7.6 seconds) under normal Windows process permissions. This separates the failure from PyInstaller, SQLite, migrations, analysis logic, providers, and API route availability.

## Root cause classification

Root cause: `H — WebView origin/CORS policy mismatch`.

The packaged WebView is served from the Tauri 2 production origin `http://tauri.localhost`. The desktop sidecar configured `SENTINEXT_ALLOWED_ORIGINS` with `tauri://localhost` and `https://tauri.localhost`, but omitted `http://tauri.localhost`. Consequently, the WebView could resolve the correct loopback URL and issue a request, while the browser fetch was rejected and surfaced through the generic `TypeError` wrapper as “无法连接 SentiNext 后端”.

The Tauri CSP already contains the narrow loopback allowance `http://127.0.0.1:*`; no wildcard CSP change was made.

## Smallest fix applied

- Added only `http://tauri.localhost` to the desktop sidecar's allowed origins.
- Moved the desktop `/api` guard ahead of the static environment fallback so a packaged WebView can never silently use `/api` before URL handoff.
- No sleep, retry policy, UI design, schema, analysis semantics, provider, taxonomy, prompt, or presentation projection changes were made.

## Fix candidate

Candidate: `clean-install-v9` (new install directory; not `clean-install-v7` or v8).

The v9 build completed with fresh sidecar, Tauri, and NSIS artifacts. The sidecar health probe succeeded on dynamic port `58003` in approximately 8.8 seconds. Subsequent user-visible testing reached the application layout and exposed a second, independent release defect: `AppLayout` compared the desktop sidecar's valid `runtime_profile=desktop` against the build-time integration value `NEXT_PUBLIC_RUNTIME_PROFILE=integration`.

The smallest fix is to derive the expected profile from the actual runtime: Tauri WebView expects `desktop`; ordinary local Web expects the configured `integration` profile. This is a frontend environment-selection fix, not a backend or data change. A new package must be built and verified after this fix.

The desktop-control session was stopped with the physical Escape key before the post-fix candidate could be captured, so `OVERVIEW_READY`, three cold starts, and the failure path remain open.

## Gate

Do not create `sentinext-portfolio-v1`. Resume with one uninterrupted Computer Use pass against `clean-install-v9`; all stages above must pass and no manual Retry may be required.
