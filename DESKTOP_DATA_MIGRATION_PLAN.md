# Desktop Data Migration Plan — Portfolio Release V1.1

Status: `EXECUTED — accepted`

Branch: `release/portfolio-v1.1`

Rollback/release baseline: `sentinext-portfolio-v1` (unchanged)

## Database locations found

| Role | Exact path | Size | Migration | Integrity |
|---|---|---:|---:|---|
| Authoritative historical/integration DB | `D:\reviews\SentiNext\SentiNext-refactor\data\runtime\integration\sentinext.db` | 67,198,976 bytes | 12 | `ok` |
| Packaged desktop user DB | `C:\Users\liuqi\AppData\Local\SentiNext\SentiNext\sentinext.db` | 266,240 bytes | 12 | `ok` |

The desktop DB is a clean user database: all inspected analytical tables contain zero rows. The historical DB contains the existing review and analysis provenance. The two databases are not being conflated.

## Historical source read-only inventory

| Table / condition | Observed |
|---|---:|
| reviews | 20,806 |
| review_labels | 4,325 |
| analysis_runs | 13 |
| analysis_run_results | 6 |
| analysis_results | 2 |
| analysis_designs | 7 |
| version_events | 25 |
| llm_calls | 1,142 |
| starred_games | 2 |
| completed general analyses | 6 |
| completed Version Reviews | 2 |
| failed Version Reviews | 3 |
| running Version Reviews | 2 |

The two running Version Review rows are preserved as historical state unless a later, explicit decision defines a safe stale-run policy. No temporary/test-only rows were deleted or excluded by this plan.

## Executed strategy

Because both databases were at migration 12 and the desktop DB was empty, the approved SQLite-safe full replacement was executed after backups:

1. Stop the packaged desktop app and confirm no sidecar is running.
2. Create a SQLite-consistent backup of the current desktop DB.
3. Create a SQLite-consistent backup of the historical source DB.
4. Verify both backup hashes and run `PRAGMA integrity_check` on both backups.
5. Replace only the desktop `sentinext.db` with the verified historical backup. Do not copy WAL/SHM files inconsistently.
6. Start the packaged desktop app and verify migration 12, runtime profile `desktop`, and unchanged run IDs/provenance.

Execution evidence is recorded in `DESKTOP_DATA_MIGRATION_REPORT.md`.

This is an L3 data operation. The steps above are the rollback point and execution boundary; no write will occur until the plan is accepted for execution.

## Identity rules

- Runtime identity remains process-owned: `runtime_profile=desktop`, actual dynamic port, and desktop app-data path.
- Historical `run_id`, `app_id`, result hashes, taxonomy/prompt/provider provenance, evidence, `llm_calls`, and Version Review state remain unchanged.
- No provider call, label regeneration, analysis rerun, schema change, or result rewrite is permitted.
- The source integration DB will not be bundled into the installer or used as a default for future installations.

## Acceptance after approved execution

- source and backup integrity: PASS;
- desktop DB migration 12 and integrity: PASS;
- existing games, completed general runs, Version Review history, exact `app_id + run_id` links, evidence, and Reports visible;
- historical projection-unavailable behavior remains truthful;
- no provider call occurs;
- then and only then begin the separate zh-CN packaged UI audit. This audit is recorded separately and does not alter the migrated database.
