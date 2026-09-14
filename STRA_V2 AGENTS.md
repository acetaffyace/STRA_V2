# STRA_V2 Agent Execution Contract

## 1. Authoritative specification

The authoritative rebuild specification is:

`docs/master-spec/STRA_V2_MASTER_PRODUCT_REBUILD_SPEC_1.1.md`

Treat it as the product, research, architecture, migration, compatibility, semantic measurement, and release authority for the STRA_V2 rebuild.

Do not silently replace its contracts with assumptions inferred from the existing implementation.

When current code conflicts with the Master Spec:

1. identify the conflict;
2. preserve existing user data where required;
3. implement the migration path required by the Master Spec;
4. record material architectural decisions in `docs/execution/DECISION_LOG.md`.

Do not reinterpret explicit invariants merely to minimize implementation effort.

---

## 2. Persistent execution state

Before performing substantial implementation work, always read:

- `docs/execution/EXECUTION_STATE.md`
- `docs/execution/DECISION_LOG.md`
- `docs/execution/BLOCKERS.md`

These files are the persistent handoff state between Codex sessions.

Never rely solely on previous chat context.

Do not redo work already recorded as completed unless validation demonstrates that it is incorrect or incomplete.

---

## 3. Execution model

Execute the rebuild milestone by milestone in the order defined by the Master Spec:

M0 → M1 → M2 → M3 → M4 → M5.

Within the active milestone:

- identify the next unblocked acceptance item;
- inspect the relevant existing implementation and tests;
- implement the smallest coherent vertical change;
- run relevant tests;
- fix failures caused by the change;
- update persistent execution state;
- commit the verified change;
- immediately continue to the next unblocked item.

Do not stop merely because one subtask, file, endpoint, migration, component, or commit has been completed.

Continue autonomously until one of the following is true:

1. the current milestone satisfies its Definition of Done;
2. a genuine blocker requires information or authorization that cannot be derived from the Master Spec, repository, tests, or existing project decisions;
3. continuing would require violating a RELEASE_BLOCKER or an explicit Master Spec invariant;
4. the execution environment prevents further work.

A difficult implementation problem is not by itself a reason to stop. Investigate, test, and attempt a reasonable solution first.

---

## 4. Planning is not completion

Do not finish a task after only:

- analyzing the repository;
- producing a plan;
- listing TODOs;
- creating interfaces without implementation;
- adding backend code without the required consumer path;
- adding frontend placeholders without canonical backend contracts;
- adding tests that do not exercise the actual implementation.

Plans are intermediate artifacts.

When implementation is requested, proceed from planning into implementation in the same execution unless genuinely blocked.

---

## 5. Exact source-of-truth hierarchy

Preserve the canonical identity hierarchy defined by the Master Spec.

In particular:

`Game != ResearchRun != SemanticRun != Job != Export`

Do not store canonical analytical truth in StarredGame/FavoriteGame objects.

Do not substitute `app_id` for an exact analytical run identity where the Master Spec requires `research_run_id`, `semantic_run_id`, comparison run identity, version-review run identity, or another canonical source resource.

Do not make "latest" data masquerade as immutable historical data.

---

## 6. Analytical integrity

Frontend code may render canonical metrics and compute explicitly exploratory local views only where permitted.

Frontend pages must not recreate canonical formal metrics from raw review arrays.

Do not create a second analytical truth in:

- Reports / Exports;
- Compare;
- Version Review;
- Ask STRA;
- frontend helper functions;
- legacy compatibility code.

Exports must consume exact canonical source resources.

Ask STRA must consume canonical analytical and evidence resources rather than independently recreating formal metrics.

---

## 7. Semantic Engine rules

Semantic Engine implementation must follow the Master Spec's canonical SemanticUnit, SemanticMention, review-level rollup, prevalence denominator, unresolved semantics, compatibility, and semantic_config_hash contracts.

Do not use mention count as topic prevalence.

Do not force unresolved reviews into `overall_experience/general` merely to obtain complete classification coverage.

Do not perform formal cross-run semantic comparison unless compatibility rules allow it.

Game-specific topics from different games are not formally equivalent merely because labels or embeddings appear similar.

---

## 8. Historical reproducibility

Formal results must remain reproducible after:

- Steam review edits;
- taxonomy changes;
- embedding model changes;
- prototype changes;
- calibration changes;
- frontend changes;
- system clock changes.

Respect ReviewSnapshot, PopulationSnapshot, exact run identity, source-content hash, offset, anchor-time, and time-window contracts.

---

## 9. Long-running jobs

Long-running acquisition, semantic, export, migration, or analytical operations must follow the persistent job contract defined in the Master Spec.

Do not implement long-running work purely as fragile browser state.

Respect:

- idempotency;
- duplicate prevention;
- persistent progress;
- cancellation;
- retry policy;
- restart recovery;
- terminal failure state;
- immutable final resource identity.

---

## 10. Database migration safety

Database/schema changes must be additive or explicitly migrated according to the Master Spec.

Never destroy or silently reinterpret existing user data.

Migration work must include the required migration tests and legacy database fixture coverage.

If a migration can be interrupted, ensure restart behavior is safe.

---

## 11. Testing requirements

For each coherent change, run the narrowest relevant tests first.

Before declaring a milestone complete, run the complete validation required by that milestone and the repository CI-equivalent checks.

Do not suppress failing tests merely to obtain green CI.

Do not weaken an existing assertion unless the Master Spec intentionally changes the underlying contract and the new assertion correctly expresses that contract.

Deterministic offline fixtures must be usable without requiring live Steam access or paid LLM calls where the Master Spec requires deterministic testing.

---

## 12. Benchmark and release rules

A benchmark being executed does not mean that it passed.

Respect the Master Spec's benchmark acceptance thresholds and release classification:

- RELEASE_BLOCKER
- REQUIRED
- POST_RELEASE

Never declare the rebuild or a milestone complete while an applicable RELEASE_BLOCKER remains failed.

A REQUIRED item may be waived only if the Master Spec explicitly permits the waiver and the reason is recorded.

---

## 13. Git discipline

Keep changes reviewable.

Prefer coherent commits corresponding to verified architectural or product increments rather than one enormous rebuild commit.

Before every commit:

- inspect the diff;
- run applicable tests;
- confirm no unrelated generated or temporary files are included.

After every commit:

- confirm repository status;
- record the commit SHA and completed acceptance items in `docs/execution/EXECUTION_STATE.md`.

Do not rewrite previously accepted commits merely to hide execution history.

---

## 14. Execution state updates

`docs/execution/EXECUTION_STATE.md` must always contain at least:

- Master Spec version;
- baseline/ref;
- active milestone;
- milestone status;
- completed acceptance items;
- current work item;
- next unblocked work items;
- tests run and outcomes;
- relevant commit SHAs;
- open release blockers;
- open required items;
- last verified timestamp.

Update it after every verified coherent work unit.

This file must be sufficient for a fresh Codex session with no previous chat context to continue correctly.

---

## 15. Decision logging

Record a decision in `DECISION_LOG.md` when implementation requires choosing between materially different designs not explicitly fixed by the Master Spec.

Each entry should contain:

- decision;
- context;
- alternatives considered;
- reason;
- affected contracts/files;
- migration impact;
- date/commit.

Do not create decision-log entries for trivial implementation details.

---

## 16. Blocker policy

Before declaring a blocker:

1. inspect the Master Spec;
2. inspect existing implementation;
3. inspect relevant tests;
4. inspect execution and decision logs;
5. attempt a reasonable implementation or diagnostic path.

If still blocked, write the blocker into `BLOCKERS.md` with:

- exact problem;
- evidence;
- attempted approaches;
- affected milestone/item;
- consequence of guessing;
- precise human decision or missing input required.

Continue working on other unblocked items when doing so is safe.

---

## 17. Completion reporting

When ending an execution turn, report:

- what was completed;
- commits produced;
- tests run;
- active milestone status;
- remaining release blockers;
- exact next work item.

Do not use vague statements such as "mostly complete", "should work", or "implementation finished" when acceptance evidence is incomplete.