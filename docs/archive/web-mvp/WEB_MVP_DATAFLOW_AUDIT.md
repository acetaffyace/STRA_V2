# Web MVP Dataflow Audit

Target: STEINS;GATE RE:BOOT, app_id `4012810`.

Observed path:

`dashboard/page.tsx` → `fetchAnalysisResult` / starred cache / in-memory task → `GET /analysis/{app_id}` → compatibility row `analysis_results`.

Analyze path:

`AnalysisContext.startAnalysis` → `POST /analyze` → Steam fetch + persistence → `analysis_runs` → background provider classification → immutable `analysis_run_results` and compatibility `analysis_results` → SSE/polling completion.

The prior page had no single readiness gate and could render a completed compatibility row when semantic coverage was zero. It also derived unsupported purchase, library and active segments from missing fields. The new `GET /analysis/{app_id}/dashboard` payload is keyed by the same `app_id` and `run_id` and exposes explicit readiness, coverage, design, evidence and semantic-engine fields.
