# Cleanup Candidate Manifest

Status: audited before Phase A cleanup; candidates below are scoped explicitly.

Audit basis: current working tree on 2026-08-26, branch `codex/p0-player-voice-hardening`, HEAD `7ec4adcb7cb17e69ae997310e108d7ec6688d291`. The working tree contains user changes; no broad `git clean` is authorized.

## KEEP

| Path | Reason | Decision |
|---|---|---|
| `apps/` | Current source/runtime | KEEP |
| `apps/api/senti_next/migrations.py` and migration/schema modules | Reproducible schema history | KEEP |
| `tests/`, `pytest.ini` | Regression and release tests | KEEP |
| `tooling/evals/` | Gold/Dev/Holdout evaluation evidence | KEEP |
| `tooling/benchmarks/prompts/`, taxonomy/schema modules | Prompt and analytical contracts | KEEP |
| `data/pilot/` and all canonical/historical DBs and DB backups | Source evidence, runs, and provenance | KEEP |
| `MVP_ACCEPTANCE_MATRIX.md`, `MVP_GOLDEN_PATH_*`, `MVP_OPERATIONS_RUNBOOK.md`, `MVP_RELEASE_REPORT.md` | Current release evidence | KEEP |
| `PORTFOLIO_*` | Final portfolio evidence | KEEP |
| `README.md`, `LOCAL_DEVELOPMENT.md`, `.env.example`, startup/runtime scripts | Product/runbook/config templates | KEEP |

## ARCHIVE

The following exact root-level document families are superseded process artifacts. They will be moved, not deleted, with an index recording the reason and destination:

| Candidate path/family | Destination | Reason | Decision |
|---|---|---|---|
| `P0_0A_REPORT.md`, `P0_0B_REPORT.md`, `P0_1*.md`, `P0_2*.md`, `P0_3*.md`, `P0_4*.md`, `P0_5A*.md`, `P0_5B_annotation*.md`, `P0_5B_*REPORT.md`, `P0_5C*.md`, `P0_6*.md`, `ADR_P0_*.md`, `P0_IMPLEMENTATION_PLAN.md` | `docs/archive/p0/` | Superseded P0 execution/audit artifacts; evaluation data itself remains KEEP | ARCHIVE |
| `V1_P1_*.md`, `V1_PILOT_*.md`, `V1_REAL_USE_PILOT.md` | `docs/archive/p1/` | Superseded P1/pilot process material | ARCHIVE |
| `ADAPTIVE_ANALYSIS_*.md`, `APEX_ADAPTIVE_ANALYSIS_REPORT_ZH.md`, `UNIFIED_ANALYSIS_*.md`, `SEMANTIC_RUNTIME_*.md` | `docs/archive/adaptive-analysis/` | Superseded architecture/audit milestones | ARCHIVE |
| `STEAM_REVIEW_ENRICHMENT_*.md`, `STEINS_500_WEB_ANALYSIS_REPORT.md` | `docs/archive/web-mvp/` | Superseded web/enrichment milestone material | ARCHIVE |
| `WEB_MVP_*.md` | `docs/archive/web-mvp/` | Superseded web-MVP audits, acceptance, and browser reports | ARCHIVE |
| `VERSION_REVIEW_AUTOPILOT_*.md`, `VERSION_REVIEW_V2_*.md`, `UNIFIED_VERSION_REVIEW_UX_REPORT.md` | `docs/archive/version-review/` | Superseded Version Review milestone/UX reports | ARCHIVE |
| `LOCAL_RUNTIME_*.md` | `docs/archive/runtime-isolation/` | Superseded runtime-isolation reports; current runbook remains at root | ARCHIVE |
| `AUTONOMOUS_*.md` | `docs/archive/` | Process execution logs, not product contract | ARCHIVE |
| `APEX_LEGENDS_ANALYSIS_REPORT_ZH.md`, `NINJA_GAIDEN_4_ANALYSIS_REPORT_ZH.md` | `docs/archive/` | Historical generated analysis reports; raw data remains KEEP | ARCHIVE |

## DELETE

Deletion is limited to the following disposable paths after this manifest exists. No database, migration backup, Gold/Holdout file, source evidence, or release report is in this list.

| Path | Reason | Decision |
|---|---|---|
| `.pytest_cache/`, `.pytest-local/`, `.pytest-runtime-isolation/`, `.pytest-unified/`, `.pytest-v2-release-temp/` | Disposable pytest caches/runtime fixtures | DELETE |
| `.pytest-tmp/` | Temporary pytest base directory created for isolated regression | DELETE |
| `.benchmark-test-tmp/`, `.p0_1-failure-fixture/`, `.p0_2a-failure-fixture/`, `.p0_2a-parity-fixture/`, `.p0-test-tmp/` | Disposable test/benchmark scratch directories | DELETE |
| `__pycache__/`, `tooling/**/__pycache__/`, `apps/api/**/__pycache__/` | Python bytecode caches | DELETE |
| `apps/dashboard/.next/`, `apps/dashboard/out/` | Regenerable frontend build output | DELETE |
| `data/runtime/*/*.log`, `data/runtime/*/runtime.lock` | Runtime logs and stale lock metadata | DELETE |

## Explicit non-actions

- Do not run `git clean -xdf`.
- Do not delete `data/runtime/*/*.db`, `*.bak`, `data/pilot/**`, `tooling/evals/**`, or evaluation JSONL/JSON files.
- Do not archive current `MVP_*` release/acceptance/runbook materials or portfolio materials.
- `.venv311/` and `node_modules/` are retained in this pass so regression tests can run without reinstalling dependencies.
