# Web MVP Acceptance Matrix

| Gate | Result | Evidence |
|---|---|---|
| Raw reviews visible separately from analysis | PASS | Dashboard payload reports `review_count=500` |
| Exact app/run linkage | PASS | Payload reports app `4012810`, run `0c689e1c24354d41aba0ed16917c9371` |
| Zero classifications cannot be READY | PASS | Contract returns `ANALYSIS_INCOMPATIBLE` |
| Unknown is not 0% for unsupported segments | PASS | Purchase/library/activity show unavailable states |
| Contract regression tests | PASS | `test_web_mvp_contract.py` 2 passed |
| Frontend typecheck | PASS | `npm --prefix apps/dashboard run typecheck` |
| Real browser visual smoke | BLOCKED | In-app browser native pipe bridge unavailable |
| Validated semantic result for STEINS | FAIL | Classified count is 0; no design/evidence |
