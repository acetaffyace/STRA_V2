# Portfolio Release V1 Report

## Current gate

`SENTINEXT_PORTFOLIO_V1_READY`

The exact frozen candidate was installed into a new directory and started with new desktop app-data. The WebView reached Overview automatically, and all required release gates passed.

## Candidate

- Branch: `release/portfolio-v1`
- Frozen baseline/tag: `sentinext-mvp-v1` remains untouched
- Final install: `artifacts/portfolio-release-v1/clean-install-final`
- Installer SHA-256: `CFB902FACEBF3A628F8E54D27321D0925066F459A6F369DAD179134FC8A93309`
- Installer size: 68,339,056 bytes
- Installed files size: 79,127,884 bytes
- Sidecar size: 65,419,260 bytes
- Desktop executable size: 13,629,440 bytes

## Build checks

- Dashboard `npm run typecheck`: PASS
- Tauri `cargo check`: PASS
- PyInstaller sidecar build: PASS
- Tauri/NSIS package build: PASS
- Fresh isolated install: PASS
- Dynamic loopback sidecar health on port `61995`: PASS, approximately 10.26 seconds from launch
- v8 diagnostic: runtime detection, invoke, and dynamic URL handoff PASS; WebView health FAIL due to missing `http://tauri.localhost` allowed origin
- v9 post-fix sidecar health on port `58003`: PASS, approximately 8.8 seconds from launch
- AppLayout runtime-profile mismatch: identified and fixed; desktop now expects `desktop`

## Final gates

| Gate | Result | Evidence |
|---|---|---|
| INSTALLER_IDENTITY | PASS | Required SHA-256 matched exactly |
| DESKTOP_BOOTSTRAP | PASS | New app-data launch opened Overview without Retry |
| DYNAMIC_API_HANDOFF | PASS | Dynamic loopback sidecar and runtime identity confirmed |
| CORS | PASS | WebView reached application pages after `http://tauri.localhost` fix |
| RUNTIME_IDENTITY | PASS | `desktop`, actual dynamic port, migration 12 |
| THREE_COLD_STARTS | PASS | Launch 1/2/3 all opened Overview without startup error |
| RESTART_PERSISTENCE | PASS | Same DB instance `desktop-375fe5079ffb`, migration 12 |
| PACKAGED_DESKTOP_SMOKE | PASS | Overview, analysis entry, Reports, Version Review, Settings visually checked |
| OPTIONAL_CAPABILITY_FAILURE | PASS | No-key Steam capability is explicitly handled as unavailable in the packaged UI path |
| FAILURE_PATH | PASS | Missing sidecar showed explicit spawn failure and Retry remained available |

Final packaged screenshots were captured during the Computer Use acceptance trace for Overview, Reports, Version Review, and Settings.
- Runtime identity: sidecar is configured for `desktop` and reports its actual dynamic port

No fake data, analytical semantics, provider calls, database schema, taxonomy, or presentation projections were changed for this release-engineering closure.

## Tag gate

Candidate is ready for the explicit release-tag action: `sentinext-portfolio-v1`. The frozen tag `sentinext-mvp-v1` remains untouched.
