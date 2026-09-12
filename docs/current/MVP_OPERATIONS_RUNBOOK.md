# MVP Operations Runbook

Use the repository environment:

```powershell
.\.venv311\Scripts\python.exe -m pytest -q --basetemp .pytest-local
npm --prefix apps/dashboard run typecheck
npm --prefix apps/dashboard run lint
npm --prefix apps/dashboard run build
```

For no-provider development validation, run the offline fixture flow with a local JSONL review file. It records `mode=codex_offline_fixture`, never calls a provider, stores an immutable result, and exposes the exact `run_id` for AnalysisDesign/result inspection.

If no verified event/baseline exists, keep `analysis_type=current_snapshot`, `descriptive_only=true`, and render `What changed=unavailable`. Do not manufacture comparison claims.

For production-like local smoke, start the backend and dashboard, then check `/health`, `/openapi.json`, and `/dashboard`. The browser visual smoke should be repeated when the in-app browser bridge is available.
