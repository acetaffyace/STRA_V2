# Agent Governance Layout Execution Report

Date: 2026-08-26  
Branch: `chore/agent-governance-layout`  
Rollback point: `sentinext-mvp-v1` / frozen release commit

## What changed

- Moved API tests into `tests/unit/`, `tests/integration/`, and `tests/regression/`.
- Moved Gold, Dev, Holdout, prediction, draft, and evaluation-report assets into `tooling/evals/`.
- Moved active project documents into `docs/current/`; preserved `docs/archive/` history.
- Renamed `data/v1_pilot/` to `data/pilot/` and moved pilot logs to `logs/pilot/`.
- Added `data/imports/`, `artifacts/`, `logs/`, and isolated agent runtime directories.
- Updated `pytest.ini`, evaluation-tool defaults, and runtime logging paths.
- Added the governance document to `docs/current/SENTINEXT_AGENT_GOVERNANCE.md`.

## What was not changed

- No taxonomy, prompt identity, Five Questions, Evidence Grade, AnalysisDesign, Version Review methodology, or provider semantics changed.
- No canonical DB, historical DB, migration backup, Gold/Holdout contents, immutable result, or `llm_calls` ledger was deleted or rewritten.
- Integration ports remain 3000/8000 and the canonical DB path remains `data/runtime/integration/sentinext.db`.
- The frozen release branch and tag were not modified; this work is isolated on the governance-layout branch.

## Verification

- Pytest collection: PASS, 157 tests discovered under the new layout.
- Full pytest: PASS; existing Pydantic deprecation warnings remain.
- Python compileall and import smoke: PASS.
- Frontend typecheck: PASS.
- Frontend lint: PASS with 3 existing warnings and 0 errors.
- `git diff --check`: PASS.
- Canonical DB integrity: PASS (`PRAGMA integrity_check = ok`); schema migration version 12.
- Runtime path contract: PASS by static inspection; runtime startup/browser acceptance was not run in this layout-only task.

## Final gate

`PASS — layout separation implemented and code-level verification passed.`

This report does not claim integration/browser acceptance. That requires restarting the integration runtime and running the governed browser flow separately.
