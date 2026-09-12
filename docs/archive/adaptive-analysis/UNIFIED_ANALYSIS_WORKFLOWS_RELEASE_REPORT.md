# Unified Analysis Workflows Release Report

## Release decision

`UNIFIED_ANALYSIS_WORKFLOWS_V1_READY`

## Delivered

- Exact-run recent-analysis navigation.
- Unified recent and active run registry.
- Unified global queue for general analysis and Version Review.
- Version Review mode selection, automatic comparable-event planning, and A/B lifecycle-matched execution.
- Recent Version Review history with Debug-only Run ID recovery.
- Canonical review storage reuse and bounded per-window semantic sampling.
- Persisted phase/progress metadata and explicit error states.

## Verification

Backend tests, targeted regressions, compileall, frontend typecheck, lint, production build, and live HTTP smoke all passed. Lint has only existing warnings. Browser visual smoke remains pending because the local native browser bridge was unavailable.

## Scope guard

No unrelated feature work was started. Analytical methodology outside the required Version Review comparison contract was not redesigned.
