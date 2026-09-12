# Portfolio Release V1 Content Manifest

Status: `RELEASE_CONTENT_AUDIT_IN_PROGRESS`
Target branch: `release/portfolio-v1`
Candidate tag: `sentinext-portfolio-v1`

This manifest is the packaging boundary. The installer must be assembled from the desktop bundle output and runtime necessities only; the repository remains the development/evidence workspace.

## KEEP_IN_PACKAGE

- Tauri desktop shell and its generated production frontend assets from `apps/dashboard/out/`.
- Tauri runtime resources and icons from `apps/desktop/src-tauri/` required by the configured Windows installer target.
- The packaged Python sidecar generated from `apps/desktop/pyinstaller/sentinext-backend.spec`.
- Python runtime dependencies frozen into the sidecar by `apps/desktop/pyinstaller/requirements-desktop.txt`.
- Application migrations and schema initialization code embedded in the sidecar; no pre-populated developer database.
- Required report templates and application assets explicitly collected by the PyInstaller spec.
- Runtime configuration behavior that resolves the user database and logs under the OS application-data directory.
- Installer metadata and the normal Tauri NSIS bundle output.

## EXCLUDE_FROM_PACKAGE

- `.venv311`, `apps/desktop/pyinstaller/.venv`, and all host virtual environments.
- `node_modules`, npm caches, `.next`, TypeScript caches, pytest caches, `__pycache__`, and build scratch directories.
- `tests/`, `tooling/evals/`, Gold/Dev/Holdout, predictions, benchmark source/output, and fixtures.
- `data/runtime/integration/`, agent databases, pilot/import data, historical development databases, and `backups/`.
- `logs/`, screenshots, exports, reports, governance/process documents, and `docs/archive/`.
- `.git/`, source-control metadata, local `.env` files, API keys, Steam credentials, and provider secrets.
- Any source-worktree path such as `D:\reviews\SentiNext\SentiNext-refactor`.

## OPTIONAL_RUNTIME_DATA

- A clean per-user SQLite database created on first launch under the OS application-data directory.
- Per-user runtime logs under the same application-data directory.
- Optional provider configuration entered by the user through supported settings/environment mechanisms; no credentials are preloaded.
- Optional Steam Web API capability configuration; missing credentials must remain an explicit unavailable state.
- An explicitly supplied external demo dataset, only if separately approved later. No demo dataset is included in this release.

## Audit rules

- The canonical integration SQLite is verification input only and is never the packaged default database.
- The installer must be tested from a clean application-data directory, not from the repository or localhost development runtime.
- Measured package sizes and final paths are recorded in `PORTFOLIO_RELEASE_V1_REPORT.md` after the build.
