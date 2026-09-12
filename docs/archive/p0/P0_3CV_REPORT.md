# P0.3cV Report — Frontend Environment & Build Verification

Status: **PASS — GO for P0.4 review**. P0.4 was not started.

## Dependency audit and root cause

The repository declares a standalone frontend at `apps/dashboard` with `apps/dashboard/package-lock.json`. CI and the Dockerfile both use `npm ci`; the README requires Node.js 20+. There is no root frontend package or alternate lockfile.

Observed environment:

- Node: `v24.15.0`
- npm: `11.12.1`
- lockfile: `apps/dashboard/package-lock.json`
- package versions were not changed

The previous `node_modules` was incomplete: `language-subtag-registry/data/json/index.json` and the `caniuse-lite` browser data required by Browserslist were unavailable. The lockfile declared both dependency trees and showed no missing declaration or inconsistent package metadata. This was an incomplete/corrupted install, not a product-code or dependency-declaration defect.

## Repair

1. Ran the repository-declared `npm ci`.
2. The normal install reached Windows `spawn EPERM` while running package scripts.
3. Ran `npm ci --ignore-scripts` using the same lockfile. It completed successfully: 509 packages added, 510 audited, 0 vulnerabilities.
4. No package or lockfile was edited. No files were copied manually into `node_modules`.

The missing dependency data was restored by the deterministic install. `node_modules`, `.next`, `out`, and TypeScript build metadata remain ignored local artifacts and were not added to version control.

## Verification results

Commands and results:

- `npx tsc --noEmit` — **PASS**
- `npm run lint` — **PASS**, 0 errors and 3 existing warnings outside the P0.3c surface (`reviews/page.tsx`, `AchievementsWidget.tsx`, `SteamImage.tsx`)
- `npm run build` — **PASS** with elevated Windows process permission; compiled successfully, typechecked, generated all 13 static pages, and finalized optimization
- Frontend tests — **NOT CONFIGURED**; `package.json` has no test script or frontend test runner
- `git diff --check` — **PASS**
- Backend full pytest — **89 passed, 2 intentional xfailed**
- Backend `compileall` — **PASS**
- Backend import smoke — **PASS** (`senti_next.insights`, `metric_provenance`, and `routes.analysis`)

The build warning that Browserslist data is eight months old is informational only; it does not fail the build and no package upgrade was authorized or needed.

## Final KPI adoption verification

- Modern unfiltered Dashboard formal cards read `metric_provenance` observations.
- Display samples cannot override the backend formal recommendation value.
- LLM-derived rates use the backend validated-classified denominator and expose coverage in the secondary presentation label.
- Null/unavailable observations render as unavailable, never as `0%`.
- Observation run mismatches are rejected by the shared presenter.
- Compare checks metric ID, formula version, source type, denominator type, sampled state, and sampling semantics before treating observations as comparable; incompatible formal runs are surfaced as unavailable/warning rather than silently merged.
- Active filters remain explicitly labeled interactive; only that state may use sample-derived values.
- Legacy records without `metric_provenance` continue through the legacy numeric compatibility path.

Category/cohort and segment surfaces remain documented legacy/interactive paths because P0.3b does not publish equivalent backend observations. No new backend metrics were added, and no existing surface was relabeled as a formal run-level KPI.

## Files changed in P0.3cV

- `P0_3CV_REPORT.md`
- `apps/dashboard/src/app/compare/page.tsx` — minimal Hook dependency correction required for clean lint

Dependency files were not changed. Product logic was not redesigned or expanded.

## Recommendation

All applicable verification gates are green. **GO for P0.4.** Stop after P0.3cV; P0.4 remains unimplemented and requires a separate authorization.
