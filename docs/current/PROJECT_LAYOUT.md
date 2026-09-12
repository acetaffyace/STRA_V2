# SentiNext Governed Project Layout

This layout is governed by `SENTINEXT_AGENT_GOVERNANCE.md` and applies to the frozen MVP plus the two permitted active tracks.

| Root | Ownership | Contents | Git policy |
|---|---|---|---|
| `apps/` | Product source | API, dashboard, desktop, marketing | Source is versioned |
| `tests/` | Verification | `unit/`, `integration/`, `regression/` | Versioned test code |
| `tooling/` | R&D/evaluation | Gold, Dev, Holdout, predictions, prompts, benchmarks, fixtures | Versioned evaluation assets; generated benchmark caches ignored |
| `data/` | Business/provenance state | `runtime/`, `pilot/`, `imports/` | Runtime data is not disposable cache |
| `artifacts/` | Generated outputs | reports, screenshots, exports, benchmarks | Regenerable; ignored by Git |
| `backups/` | Rollback snapshots | MVP database backups | Managed separately from source commits |
| `docs/` | Human-facing documentation | `current/`, `archive/`, assets | Current docs separated from historical process docs |
| `logs/` | Runtime logs | integration, agent-ui, agent-cost, pilot | Ignored by Git |
| `dist/` | Release packages | final packaging output | Regenerable; ignored by Git |

## Runtime boundary

- Integration frontend/backend remain on ports 3000/8000.
- Integration DB remains `data/runtime/integration/sentinext.db`.
- UI and cost agent DB directories are reserved at `data/runtime/agent-ui/` and `data/runtime/agent-cost/`.
- `run_local.ps1` writes backend/frontend logs to `logs/<profile>/`; it does not move or recreate the integration database.

## Non-negotiable separation

- Source, evaluation assets, runtime data, and generated artifacts use separate root directories.
- Generated runtime artifacts must not be written into source directories unless explicitly versioned as a fixture or release asset.
- Tests use copied/synthetic fixtures and must not mutate the canonical integration database.
