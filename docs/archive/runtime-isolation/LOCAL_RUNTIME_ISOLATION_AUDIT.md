# Local Runtime Isolation Audit

## Root cause

The frontend was pointed at `localhost:8000` while the newer backend was running on `127.0.0.1:8001`. The old backend returned health but did not expose the unified workflow endpoints. Queue polling hid the incompatibility, and Version Review links used both `run` and `run_id`.

## Closure

- Canonical integration is fixed at frontend `3000`, backend `8000`, and the integration database path under `data/runtime/integration`.
- Agent profiles use separate ports, databases, logs, and runtime locks.
- Runtime identity and capabilities are exposed through `/runtime-info`.
- Frontend validates profile and capabilities before treating the backend as compatible.
- Queue failures are visible rather than silently ignored.
- New links use the canonical `run` parameter; `run_id` remains a read-only compatibility input.
- Invalid version runs are recovered on startup.
