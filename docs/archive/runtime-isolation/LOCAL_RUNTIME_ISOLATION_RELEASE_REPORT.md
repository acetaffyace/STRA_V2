# Local Runtime Isolation Release Report

## Release decision

`LOCAL_RUNTIME_ISOLATION_READY`

## Delivered

- Canonical integration runtime on 3000/8000.
- Isolated agent-a and agent-b profiles.
- Profile-specific environment files and startup entrypoint.
- Runtime ownership lock and profile-specific logs.
- `/runtime-info` metadata and capability handshake.
- Visible queue incompatibility errors.
- Canonical `run` URL helpers with legacy `run_id` reads.
- Runtime provenance embedded in new Run configurations.
- Deterministic startup recovery for invalid Version Review runs.

## Scope

No analytical methodology or unrelated product feature was changed.
