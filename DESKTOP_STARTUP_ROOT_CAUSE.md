# Desktop Startup Root Cause — Portfolio Release V1

Status: `SENTINEXT_MVP_FROZEN` / `SENTINEXT_UI_REDESIGN_V1_1_READY` / `SENTINEXT_PRESENTATION_PROJECTIONS_V1_READY`

## Root cause

The original packaged failure was a startup handoff race. Tauri started the sidecar and attempted to publish the dynamic URL from a page-load callback, while the static Next.js entry page initialized first. The frontend then used the static `/api` fallback or waited without an authoritative URL. This produced the visible “无法连接后端服务” / permanent startup state even when the sidecar could become healthy.

A separate diagnostic run showed that sandboxed shell launches can make PyInstaller report `Failed to create parent directory structure`; this was not reproducible with normal Windows process permissions. The release sidecar is therefore built without UPX compression for extraction reliability.

## Canonical bootstrap contract

1. Tauri chooses one free loopback port.
2. Tauri stores that port in managed state and launches the bundled sidecar with `--port`.
3. The frontend, when running under Tauri, obtains `http://127.0.0.1:<actual-port>` through the registered `get_backend_url` command. It never guesses `/api`.
4. The frontend polls `/health` only after resolving that URL.
5. Tauri and the frontend both use a bounded 60-second startup window and show a truthful timeout/error state.

## Latest candidate evidence

Candidate: `clean-install-v7`

| Event | Timestamp / result |
|---|---|
| T0 process launch | 2026-08-26 18:36:51.7935399 +08:00 |
| T1 desktop process observed | 2026-08-26 18:36:51.9337784 +08:00 |
| T2/T3 sidecar health probe | 2026-08-26 18:36:59.3894658 +08:00 |
| T4 first successful `/health` | 2026-08-26 18:36:59.3894658 +08:00 |
| Dynamic port | `64495` |
| T0→T4 | approximately 7.6 seconds |
| T5 URL handoff / T6 dashboard ready / T7 smoke | not captured: desktop-control tool was stopped with physical Escape |

The sidecar health response was successful under normal Windows process permissions. Frontend typecheck and `cargo check` also passed. The visual desktop acceptance, key-page smoke, restart persistence, and controlled failure-path screenshot remain unverified in this turn because Computer Use was stopped before the final candidate window could be inspected.

## Release disposition

Final packaged acceptance passed against `clean-install-final`: dynamic WebView handoff, Overview readiness, three cold starts, restart persistence, page smoke, and controlled sidecar failure were captured. The candidate is `SENTINEXT_PORTFOLIO_V1_READY`; the frozen `sentinext-mvp-v1` tag remains untouched.
