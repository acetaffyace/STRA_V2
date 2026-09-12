# Desktop Data Migration Report — Portfolio Release V1.1

Date: 2026-08-26  
Branch: `release/portfolio-v1.1`  
Baseline: `sentinext-portfolio-v1` (unchanged)

## Result

`DESKTOP_DATA_MIGRATION = PASS`

The existing historical integration database was migrated into the packaged desktop user database by verified SQLite backup replacement. The user confirmed that historical games, analysis results, and the other desktop pages open successfully after migration.

No provider call, analysis rerun, label regeneration, schema migration, result rewrite, or analytical-semantic change was performed.

## Source and destination

| Role | Exact path | Before size | Migration | Integrity |
|---|---|---:|---:|---|
| Historical source | `D:\reviews\SentiNext\SentiNext-refactor\data\runtime\integration\sentinext.db` | 67,198,976 bytes | 12 | `ok` |
| Packaged desktop destination | `C:\Users\liuqi\AppData\Local\SentiNext\SentiNext\sentinext.db` | 266,240 bytes | 12 | `ok` |

The prior generated desktop app-data was moved recoverably to `artifacts/portfolio-release-v1/app-data-previous-acceptance` before replacement. It was not deleted.

## Backup and hash evidence

Backups were created with the SQLite backup API before replacement:

| Backup | Path | SHA-256 | Integrity |
|---|---|---|---|
| Desktop before migration | `backups/portfolio-v1.1/desktop-before-migration.db` | `E70747E9E7E131F096527C073B880761E5CE07D5036DE0F5B4C58BAF8B438127` | `ok` |
| Integration source | `backups/portfolio-v1.1/integration-source-before-migration.db` | `FB3404296C86E401C04EC432B7FAAAA2738EF5B531AD6C7C390E93B61CC1B9CB` | `ok` |

The destination hash after replacement equals the verified integration-source backup hash exactly:

`FB3404296C86E401C04EC432B7FAAAA2738EF5B531AD6C7C390E93B61CC1B9CB`

No `sentinext.db-wal` or `sentinext.db-shm` file was present at replacement time.

## Content reconciliation

| Measure | Historical source | Desktop after migration |
|---|---:|---:|
| Reviews | 20,806 | 20,806 |
| Review labels | 4,325 | 4,325 |
| Analysis runs | 13 | 13 |
| Analysis run results | 6 | 6 |
| Analysis results | 2 | 2 |
| Analysis designs | 7 | 7 |
| Version events | 25 | 25 |
| LLM calls ledger | 1,142 | 1,142 |
| Starred games | 2 | 2 |
| Completed general analyses | 6 | 6 |
| Completed Version Reviews | 2 | 2 |

Failed and running historical Version Review rows were preserved as-is; no stale-run policy was invented.

## Packaged runtime verification

- Executable: `artifacts/portfolio-release-v1/clean-install-final/sentinext-desktop.exe`
- Runtime profile: `desktop`
- Dynamic backend port: `54458`
- Schema migration version: `12`
- Database instance ID: `desktop-375fe5079ffb`
- `/database/games`: 3 games returned
- Launch-to-health timing: approximately 10.646 seconds
- User acceptance: historical games, analysis results, Reports, Version Review, and other pages opened successfully
- Provider calls during migration: 0

## Rollback

To restore the pre-migration empty desktop database, stop the packaged app and replace the destination only with `backups/portfolio-v1.1/desktop-before-migration.db`, after verifying its hash and SQLite integrity. The historical source database was not modified.

## Scope boundary

The migrated database is local user data and is not bundled into the installer. The frozen V1 tag remains unchanged. This report does not authorize new analyses, provider calls, schema changes, or presentation projections.
