# Unified Analysis Workflows Audit

## Scope

This audit covers the general analysis and Version Review flows defined by `UNIFIED_ANALYSIS_WORKFLOWS_ENGINEERING_SPEC.md`.

## Findings before integration

- Recent Analysis cards were not consistently bound to an exact persisted `run_id`.
- Dashboard loading could fall back to a latest/starred result after an exact-run lookup failed.
- Version Review exposed an event-oriented flow, but not a real analysis-mode selector or two-event comparison.
- Version Review had durable records in `analysis_runs`, but its queue visibility and history reopening were separate from the general flow.
- Pasted Run ID was the primary recovery path on the Version Review page.

## Implemented closure

- Added a shared recent/active run registry over the existing `analysis_runs` table.
- Added exact run loading with app/run identity checks and no fallback when `run` is explicit.
- Added Version Review modes and current/comparison event selection.
- Added lifecycle-matched A/B execution, deterministic bounded semantic sampling, and persisted comparison metrics.
- Added a single global queue projection for general and version runs.

## Boundary

No new review database, run table, analysis methodology, or parallel result store was introduced.
