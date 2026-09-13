# STRA V2 Runtime Foundation (Stage R0)

Stage R0 hardens the boundary between source-level tests and the packaged
desktop runtime. It does not change Research Core, Stage 2E, Semantic Index,
or Semantic Discovery methodology.

## Dependency topology

`apps/api/requirements-core.txt` is the shared runtime source for the API and
PyInstaller sidecar. `requirements-server.txt` contains server-only reporting
dependencies, `requirements-dev.txt` contains test tooling, and
`requirements.txt` is the complete API/development entry point. The desktop
requirements file includes the shared core file instead of copying a second
runtime list. This keeps `statsmodels`, `socksio`, and the Stage 3 runtime
packages (`onnxruntime`, `tokenizers`, `huggingface_hub`, `scikit-learn`, and
`hdbscan`) in the packaged environment.

## Startup state and health

The backend has an explicit `STARTING → READY` / `STARTING → FAILED` state
machine. Database migration failure records a bounded diagnostic and never
marks the process ready. `/health` is always reachable and returns HTTP 503
with `status=starting` or `status=startup_failed` until initialization
succeeds; a production-ready process returns HTTP 200 with `status=ready`.
Legacy test clients that set the old completion event directly retain their
`status=ok` compatibility response.

## Schema identity

`senti_next.migrations.MIGRATION_REGISTRY` is the single runtime identity for
known schema versions. `latest_known_schema_version()` reads that registry and
`applied_schema_version()` reads the SQLite `schema_migrations` ledger. Runtime
diagnostics report `latest_known`, `applied`, and one of `current`, `behind`,
`ahead`, `uninitialized`, or `error`. A fresh database reaches the same latest
known version through the existing ordered migration path (currently 16).

## Build identity

The current pre-release identity is `0.9.0-alpha.1`, shared by backend runtime
diagnostics and the Tauri/Cargo desktop metadata. `build.py` generates
ephemeral frozen-build metadata from `git rev-parse HEAD`; it is bundled into
the sidecar and ignored by Git. Runtime diagnostics expose only app version,
Git SHA, runtime profile, startup state, and schema status—never credentials or
full sensitive paths.

## Desktop runtime smoke

The `Desktop Runtime Smoke` workflow builds the Windows sidecar through the
canonical clean-venv `apps/desktop/pyinstaller/build.py`, runs the frozen
executable's `--self-test`, starts that same executable on a dynamic local
port, polls `/health`, reads `/runtime-info`, verifies schema/build identity,
and shuts the process down. The self-test imports the production API,
Research Core, and Stage 3 runtime modules, executes a deterministic snapshot
report, and initializes an isolated SQLite database. It never downloads E5,
calls Steam, or calls an LLM provider.

The explicit `SENTINEXT_DATA_DIR` override controls the SQLite file, logs, and
runtime temporary files for CI. When it is absent, the existing
`platformdirs("SentiNext", "SentiNext")` default remains unchanged.

## Deferred to Final Runtime Seal

The following are intentionally not accepted by R0: a real historical 0.8.2
database in-place upgrade, full NSIS installer acceptance, macOS DMG/notarized
release acceptance, real Steam or LLM smoke, real E5 model download/cache
acceptance, packaged HTML/PDF acceptance, identifier/data-directory renaming,
and a GitHub Release. Branch protection is a repository setting rather than a
code change; the stable required-check candidate names are `backend`,
`frontend`, and `desktop-runtime-smoke`.
