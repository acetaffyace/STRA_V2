# STRA Brand Identity Audit

Date: 2026-08-26  
Branch: `release/portfolio-v1.1`

## Public identity

The public/product brand is `STRA`. `SentiNext` remains the historical/internal codename and is not used as the visible product name in the current desktop UI or current portfolio-facing copy.

## Changes applied

| Area | Classification | Result |
|---|---|---|
| Dashboard logo, startup title, app error copy | PUBLIC_BRAND | Uses centralized `PRODUCT_NAME = STRA` or STRA copy |
| Tauri `productName` and window title | RELEASE_METADATA / PUBLIC_BRAND | `STRA`; identifier unchanged |
| Cargo description and capability description | RELEASE_METADATA | `STRA Desktop App` / `STRA desktop` |
| Marketing logo, footer, metadata, current docs copy | PUBLIC_BRAND | Visible product copy uses STRA |
| README current product copy | PUBLIC_BRAND | Uses STRA |

## Intentional remaining occurrences

| Pattern / example | Classification | Why retained |
|---|---|---|
| `com.sentinext.desktop` | RUNTIME_PATH_IDENTITY / INTERNAL_TECHNICAL_ID | Stable Tauri identity preserves existing AppData and installed-user data |
| `user_data_dir("SentiNext", "SentiNext")` | RUNTIME_PATH_IDENTITY | Existing migrated DB remains at `C:\Users\liuqi\AppData\Local\SentiNext\SentiNext\sentinext.db`; changing it would require an L3 migration |
| `sentinext.db` | INTERNAL_TECHNICAL_ID | Database filename is invisible and renaming adds migration risk without product value |
| `sentinext-backend` and `sentinext_desktop` | INTERNAL_TECHNICAL_ID | Sidecar/binary linkage and Rust package identity; not normal product chrome |
| `SENTINEXT_*` environment variables and `__SENTINEXT_*` bridge globals | INTERNAL_TECHNICAL_ID | Runtime/API compatibility identifiers |
| `sentinext-taxonomy-v1`, run IDs, historical reports, archive paths | HISTORICAL_ARTIFACT / TECHNICAL_DETAIL_ONLY | Immutable provenance and historical evidence |
| GitHub repository URLs containing `SentiNext` | HISTORICAL_ARTIFACT / TECHNICAL_DETAIL_ONLY | Repository address is an external technical link, not the visible product name |

## Compatibility decision

Option A was used: public `productName`/window title changed to STRA while the stable identifier and sidecar data path remain unchanged. No new AppData directory was created, no DB was copied or renamed, and no migration/rerun/provider call occurred.

## Acceptance boundary

Static source and release metadata checks pass. The newly branded package must still be opened for visual acceptance before the final release tag is created; source scan alone is not sufficient.
