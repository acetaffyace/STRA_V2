# zh-CN Remaining Surface Checklist — Portfolio V1.1

This checklist is the implementation work queue for the final closure pass. Canonical values, stored content, evidence quotes, and technical identifiers are excluded from translation.

| Surface | Visible English | Classification | Source file/component | Replacement | Status |
|---|---|---|---|---|---|
| Overview | Back to Home; games found; Reviews; Favorite Games; Loading analysis results; Recommendation rate | SHOULD_TRANSLATE | `apps/dashboard/src/app/dashboard/page.tsx` | Existing zh display branches | IMPLEMENTED; typecheck passed |
| Game Analysis | Trend fallback; unavailable population helper text; chart labels | SHOULD_TRANSLATE | `apps/dashboard/src/app/dashboard/page.tsx` | Existing language layer / truthful Chinese states | PARTIAL; remaining source scan items require packaged visual confirmation |
| Version Review | READY/BLOCKED/coverage/version state values; mixed section chrome | SHOULD_TRANSLATE | `apps/dashboard/src/app/version-review/page.tsx`, `apps/dashboard/src/lib/displayLabels.ts` | Centralized display maps and Chinese section labels | IMPLEMENTED; typecheck passed |
| Reports | Loading, empty state, PDF actions, month selection, achievement context | SHOULD_TRANSLATE | `apps/dashboard/src/app/reports/page.tsx`, `apps/dashboard/src/components/reports/MonthSelector.tsx`, `apps/dashboard/src/components/AchievementsWidget.tsx` | Existing zh display branches | IMPLEMENTED in prior pass |
| Settings/System | API key, provider, model, performance, save/test, system log chrome | SHOULD_TRANSLATE | `apps/dashboard/src/app/settings/page.tsx` | Existing language state branches | IMPLEMENTED; typecheck passed |
| Onboarding | English introduction copy | SHOULD_TRANSLATE if reachable; otherwise dead UI | `apps/dashboard/src/components/Onboarding.tsx` | Do not expand unless reachable in release | NOT VERIFIED in this environment |
| All surfaces | Steam, game names, provider/model names, run IDs, hashes, taxonomy IDs, original evidence | KEEP_CANONICAL / PROPER_NOUN / TECHNICAL_DETAIL_ONLY | Various | Preserve exactly | PRESERVED |

## Final candidate build

- Installer: `apps/desktop/src-tauri/target/release/bundle/nsis/SentiNext_0.8.2_x64-setup.exe`
- SHA-256: `9706DDAEBA368E8EE41ED46384D8A005C29AE68964AE98C254133AC32168E8C1`
- Size: 68,340,128 bytes
- Frontend typecheck/lint/production build: PASS
- Tauri cargo check/bundle: PASS

## Packaged acceptance status

The required new-package visual inspection was not completed because the in-app browser connection was unavailable. Therefore the affected surface rows remain conditional and no final visual PASS is claimed.
