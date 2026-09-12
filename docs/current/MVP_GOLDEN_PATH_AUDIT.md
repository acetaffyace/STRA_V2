# SentiNext MVP Golden Path — Audit

The repository already had the lifecycle, adaptive-analysis, evidence, offline chat, report payload, and immutable-result components. The closure audit found the offline fixture path was the closest no-provider product path, but it did not persist an inspectable AnalysisDesign or crawl/data-quality record and had no single end-to-end acceptance test.

The path is now closed through `run_offline_fixture()`:

`offline review fixture → deduplicated canonical storage → enrichment columns → queued/running/completed run → profile → current_snapshot AnalysisDesign → deterministic labels/metrics → Five Questions → verified evidence → action → offline Chat → immutable result`.

No valid event is required. The fixture path explicitly selects `current_snapshot`, marks the design descriptive-only, and reports `What changed` as unavailable. Enrichment fields remain context-only.

Primary product corpus: the existing NINJA GAIDEN 4 local corpus/database is retained; the automated closure test uses a small deterministic NINJA GAIDEN 4-shaped fixture to keep the test offline and reproducible.
