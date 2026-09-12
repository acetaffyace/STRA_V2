# Version Review Autopilot Audit

Date: 2026-08-25

The former hard blocker was `POST /runs` rejecting events where `manual_verified` was false. The Version Review page also required manual event selection and executed a broad event-centered fetch without a separate semantic budget.

This round adds an additive planning layer over the existing `version_events`, `analysis_runs`, review archive, label cache, Adaptive Analysis, and Evidence pipeline:

- automatic event resolution with `AUTO_CONFIRMED`, `SOURCE_CONFIRMED`, `INFERRED`, `AMBIGUOUS`, and `CONFLICTED` states;
- previous comparable major event selection that skips hotfixes and small patches;
- deterministic lifecycle-matched Day 0–7 windows;
- cache-first acquisition plans with explicit required, cached, and missing intervals;
- deterministic bounded semantic sampling with a stable SHA-256 seed;
- raw-window versus semantic-sample population provenance in the result;
- `/version-review/plan` and `/version-review/start` orchestration contracts;
- Version Review UI auto-plan preview and optional, non-blocking manual correction.

Adaptive Analysis methodology, taxonomy semantics, Evidence verification, and Five Questions were reused rather than redesigned.
