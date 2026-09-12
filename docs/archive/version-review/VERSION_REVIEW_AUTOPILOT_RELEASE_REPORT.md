# Version Review Autopilot Release Report

Date: 2026-08-25

## Release decision

`VERSION_REVIEW_AUTOPILOT_V1_READY`

The engineering gate is ready. Version Review now supports automatic event resolution, lifecycle-matched planning, cache-first historical acquisition planning, bounded semantic sampling, and one-click orchestration without mandatory manual event verification.

## User-visible result

The Version Review page now previews:

- automatic version-comparison mode;
- selected current and previous comparable events;
- Day 0–7 lifecycle window;
- event confidence/provenance;
- cached versus missing acquisition intervals;
- per-window semantic sample budget.

Completed runs distinguish raw window population, semantic sample, and classified count.

## Caveat

Manual visual browser smoke was not executed because the Codex in-app browser bridge was unavailable. This is recorded as an environment limitation, not represented as a visual pass.

No unrelated P2/P3 work was started.
