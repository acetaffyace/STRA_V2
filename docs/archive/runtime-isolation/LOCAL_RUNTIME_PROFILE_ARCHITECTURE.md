# Local Runtime Profile Architecture

| Profile | Frontend | Backend | Database |
|---|---:|---:|---|
| integration | 3000 | 8000 | `data/runtime/integration/sentinext.db` |
| agent-a | 3101 | 8101 | `data/runtime/agent-a/sentinext.db` |
| agent-b | 3102 | 8102 | `data/runtime/agent-b/sentinext.db` |

Each profile owns its environment variables, lock, logs, and writable SQLite database. `run_local.ps1 -Profile <name>` starts only the selected profile and validates health plus `/runtime-info` before starting the matching frontend.

The runtime handshake returns the profile, port, git identity, API contract, schema version, database instance ID, and required capabilities.
