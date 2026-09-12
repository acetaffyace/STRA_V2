# Autonomous Failure Log

## Missing SOCKS dependency

- Symptom: `Using SOCKS proxy, but the 'socksio' package is not installed.`
- Reproduction: run the provider path in the project environment with a SOCKS proxy configured.
- Root cause: proxy support was not declared in `apps/api/requirements.txt` or local setup docs.
- Fix: declare `socksio==1.0.0`, add runtime diagnostics, and add `run_backend_local.ps1`.
- Regression test: `test_runtime_diagnostics.py` and provider failure contracts.
- User-facing change: startup now has a clear dependency path.

## Empty provider content

- Symptom: HTTP 200 followed by `Empty response from deepseek.`
- Reproduction: provider response with zero content.
- Root cause: adapter accepted transport success without typed content diagnostics; model/thinking/JSON compatibility was not visible.
- Fix: typed `EMPTY_RESPONSE` metadata and safe diagnostics; no raw prompt/review/key logging.
- Regression test: provider circuit and offline failure tests.
- User-facing change: systemic failures are bounded and fall back explicitly.

## Unknown pricing secondary exception

- Symptom: `TypeError: float() argument must be a string or a real number, not 'NoneType'`.
- Reproduction: `deepseek-chat` or another unpriced model completes/fails with usage metadata.
- Root cause: cost estimation checked for missing keys but not `None` values.
- Fix: unknown/partial prices return unavailable and preserve the primary provider error.
- Regression test: `test_unknown_pricing_never_raises_on_none_snapshot`.
- User-facing change: cost is unavailable rather than falsely zero or masking the real error.

## Batch retry fan-out

- Symptom: a failed batch triggered individual requests for every review.
- Root cause: generic batch fallback did not distinguish systemic provider failures from item-specific mapping failures.
- Fix: systemic typed failures create fallback labels without per-review provider calls; operation circuit blocks pending work.
- Regression test: `test_provider_circuit.py` and offline flow tests.
- User-facing change: failure is bounded and recoverable.

## Interrupted run state

- Symptom: force-stopping a local process left an active run until the next startup/cancel path.
- Fix: startup recovery remains authoritative; cancellation path is tested and documented; stale-running cleanup remains as a secondary guard.
- Regression test: existing P0 lifecycle/recovery tests.
- User-facing change: failed runs converge to a terminal state on restart and can be safely rerun.

