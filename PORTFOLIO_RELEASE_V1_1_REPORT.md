# Portfolio Release V1.1 Report

Branch: `release/portfolio-v1.1`  
Frozen baseline: `sentinext-portfolio-v1` (unchanged)

## Current gate

`STRA_PORTFOLIO_V1_1_BRAND_CANDIDATE`

## Completed

- Historical integration DB migrated into the packaged desktop user DB with verified backups, hashes, SQLite integrity, and content reconciliation.
- Packaged desktop runtime reopened historical games, analysis results, Reports, Version Review, and other pages; user acceptance confirmed this.
- No provider calls, reruns, schema changes, analytical-semantic changes, fake data, or presentation projections.
- Migration rollback point retained under `backups/portfolio-v1.1/`.

## Localization gate

`ZH_CN_LOCALIZATION = PARTIAL — NO_GO_FOR_FULL_CLOSURE`

The primary translation layer is active and the current packaged localization was user-accepted. The public brand closure changes product-facing names to STRA while preserving the stable sentinext runtime/data identity. See [STRA_BRAND_IDENTITY_AUDIT.md](STRA_BRAND_IDENTITY_AUDIT.md).

## Brand candidate

- Installer: `apps/desktop/src-tauri/target/release/bundle/nsis/STRA_0.8.2_x64-setup.exe`
- Size: 68,341,749 bytes
- SHA-256: `A86DC33C6F2528A644B1E7A5D729363ED005CFB0571F931F0855CA62EBBA0FA4`
- Tauri product name/window title: `STRA`
- Stable identifier: `com.sentinext.desktop` (preserved for data compatibility)
- Stable data path/file: `C:\Users\liuqi\AppData\Local\SentiNext\SentiNext\sentinext.db`

## Release decision

`SENTINEXT_PORTFOLIO_V1_1_NO_GO`

The migration itself is accepted and the public brand changes are built. The newly branded package still requires user/manual visual acceptance with migrated data. Do not create `stra-portfolio-v1.1` until that gate passes. The historical tags and database source remain untouched.

Required brand/data gates remain pending until the new STRA package is visually accepted: `PUBLIC_BRAND_STRA`, `WINDOW_TITLE_STRA`, `INSTALLER_BRAND_STRA`, `WINDOWS_APP_METADATA_STRA`, `PORTFOLIO_DOCS_STRA`, `DATA_PATH_COMPATIBILITY`, `HISTORICAL_DATA_REGRESSION`, `ZH_CN_LOCALIZATION`, and `PACKAGED_DESKTOP_SMOKE`.
