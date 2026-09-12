# Local Runtime Isolation Test Report

## Results

- Python compileall: **PASS**.
- Frontend typecheck: **PASS**.
- Version/Web regression subset: **PASS** — 15 tests passed.
- Isolated agent-a startup: **PASS** — backend 8101 and frontend 3101 responded successfully.
- Agent runtime handshake: **PASS** — profile, port, contract, and capabilities matched.
- Canonical integration startup: **PASS** — backend 8000 and frontend 3000 responded successfully.
- Canonical `/analysis-runs/active`: **PASS** — endpoint returned 200.

The initial agent startup exposed and fixed two PowerShell argument-expansion defects and a stale Next development lock. The final clean startup passed.

Browser-native visual smoke was not automated because the Codex browser bridge is unavailable in this environment; HTTP and runtime smoke were completed.
