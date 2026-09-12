# Unified Analysis Workflows Acceptance Matrix

| Requirement | Status | Evidence |
|---|---|---|
| Recent cards bind app + exact run | PASS | Dashboard `run` query and recent registry |
| Explicit run never falls back to latest | PASS | Exact dashboard path and guards |
| General/version share run registry | PASS | `/analysis-runs/recent`, `/analysis-runs/active` |
| Version modes are visible | PASS | Version Review selector |
| Version comparison shows A/B | PASS | Comparison event selector and planner |
| Previous comparable event is default | PASS | Autopilot planner |
| Canonical review archive is reused | PASS | Existing `reviews` storage path |
| Version A/B semantic sampling is bounded | PASS | Deterministic per-event sampling |
| Global queue survives reload | PASS | Durable active-run API |
| Recent Version Review reopening | PASS | Exact `/version-review?run=...` links |
| Immutable/exact completed result contract | PASS | Existing result contract plus persisted version metrics |
| Browser visual smoke | NOT RUN | Native browser bridge unavailable |

## Gate

Engineering and automated acceptance criteria pass. The unavailable browser bridge is an environment limitation, not an application test failure.
