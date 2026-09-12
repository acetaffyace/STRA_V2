# MVP Freeze Release Report

Date: 2026-08-26  
State: `SENTINEXT_MVP_FROZEN`  
Phase: A — cleanup and freeze

Freeze commit: the commit resolved by `git rev-parse sentinext-mvp-v1^{}`  
Tag: `sentinext-mvp-v1`

## Completed

- Cleanup candidate manifest created before destructive cleanup.
- Superseded process artifacts moved to `docs/archive/` with an archive index.
- Disposable pytest scratch, Python caches, frontend build output, runtime logs, and stale locks removed from the explicit manifest only.
- Canonical integration SQLite database checked with `PRAGMA integrity_check`: `ok`.
- Canonical DB copied and verified at `backups/mvp-v1/sentinext-mvp-v1.db`; schema version `12`; SHA-256 recorded in `backups/mvp-v1/SHA256SUMS.txt`.
- No paid provider calls were made for the freeze checks.

Gold/Holdout SHA-256 identities:

- `tooling/evals/gold/P0_5B_gold_verified.jsonl`: `24F34E35936C2D8944908EDECC0A5D42EB98A2B4E5EFCE384195B055131061C3`
- `tooling/evals/gold/P0_5B_gold_verified_v2.jsonl`: `5B7AA442B9F70EC27F3DDEE76A11CA0AAB6C5CC110022DA7E9C3DA0F29EAB50D`
- `tooling/evals/dev/P0_5C_dev.jsonl`: `3384AB1D0599C9EA992F3B9201ABEC3F89497D302B8697207152253F2BBD0000`
- `tooling/evals/holdout/P0_5C_holdout.jsonl`: `5A4D28B43CB4A82AC50A2612395372C19FF8DDC57000D84CA4ADCC1FC77D167B`
- `tooling/evals/dev/P0_5CW_dev.jsonl`: `25CDDFDF3190AB78AC24FFE935082D3A3425D53F4F1059D0E53EF2C6002DF9FF`
- `tooling/evals/holdout/P0_5CW_holdout.jsonl`: `08C68493076FC91D298586B0B61529222150EBC9189CA89EEE25DCC7E1886EE2`

## Regression evidence

| Check | Result | Notes |
|---|---|---|
| Full backend pytest | PASS | Full suite passed in `.venv311`; warnings are existing Pydantic deprecations |
| Migration tests | PASS | Included in full pytest suite |
| Python compileall | PASS | `apps/api/senti_next`, API tests, evals, and benchmarks |
| Import smoke | PASS | Core DB/LLM/storage/version-analysis modules imported |
| Frontend typecheck | PASS | `npm run typecheck` |
| Frontend lint | PASS | `npm run lint`; 3 existing warnings, 0 errors |
| Frontend production build | PASS | `npm run build` completed with static routes generated |
| `git diff --check` | PASS | No whitespace errors |
| Runtime health/handshake | PASS | `run_local.ps1 -Profile integration` validated backend health and runtime profile/port handshake |
| General-analysis browser smoke | BLOCKED | In-app browser bridge unavailable in this desktop environment; no alternate browser control used |
| Version Review browser smoke | BLOCKED | Same environment limitation |

## Known limitations

- Browser UI smoke remains to be rerun when the in-app browser bridge is available.
- Lint reports three non-blocking existing warnings: one React hook dependency warning and two `img` optimization warnings.
- Pytest reports existing Pydantic V2 deprecation warnings; no test failures.
- Provider/model values remain runtime configuration and are not copied into release documents or logs.

## Cost track boundary

API cost measurement and optimization were not started. The next permitted work is to branch from this frozen baseline, measure the existing `llm_calls` ledger, and proceed in COST-1 through COST-5 order without changing analytical semantics.
