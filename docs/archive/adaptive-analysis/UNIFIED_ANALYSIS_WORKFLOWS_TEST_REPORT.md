# Unified Analysis Workflows Test Report

## Results

- Backend full pytest: **PASS** — all tests passed.
- Version/autopilot/web contract regression subset: **PASS** — 18 tests passed.
- Python compileall: **PASS**.
- Frontend typecheck: **PASS**.
- Frontend lint: **PASS** with 3 pre-existing warnings (hook dependency and raw `img` warnings; no errors).
- Frontend production build: **PASS** after allowing the required Windows process spawn permission.
- Runtime health smoke: **PASS** — backend health returned 200, recent and active run endpoints returned 200.

## Covered contracts

- exact recent-run navigation;
- no latest-result fallback for explicit run IDs;
- general/version coexistence in `analysis_runs`;
- Version Review mode and comparison-event planning;
- persisted queue phase projection;
- lifecycle-matched A/B metrics;
- existing web and version regression suites.

## Environment note

The in-app browser native bridge was unavailable in this execution environment, so visual click-through was not claimed. HTTP, compile, type, lint, build, and automated regression checks were completed.
