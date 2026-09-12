# SentiNext Agent Governance Rules

Status: Project Governance Contract  
Applies to: Codex / coding agents / integration work / UI redesign / API cost optimization / maintenance  
Project stage: `SENTINEXT_MVP_FROZEN`

---

# 0. Core principle

SentiNext is now a frozen MVP with two permitted active engineering tracks:

```text
1. UI redesign
2. API cost optimization
```

The purpose of Agent governance is to prevent:

- fake completion;
- runtime/environment mixups;
- two agents editing the same implementation state;
- accidental modification of frozen analytical methodology;
- database/run-state corruption;
- optimization that reduces cost by silently reducing analytical work;
- visual redesign that changes product semantics;
- "tests passed" being confused with "product works".

All agents must follow this document before executing project work.

---

# 1. Task classification: L1 / L2 / L3

Every task must be classified before execution.

## L1 — local, low-risk, reversible

Examples:

- copy/text changes;
- spacing;
- CSS;
- icon replacement;
- isolated React rendering bug;
- non-authoritative UI label;
- dead code removal with clear references;
- deterministic refactor with no contract change.

Execution:

```text
inspect
→ implement
→ targeted verification
→ report
```

Agent may execute autonomously.

Minimum verification:

- relevant typecheck/lint/test;
- no unrelated files changed.

---

## L2 — multi-file or behavior-affecting

Examples:

- page redesign;
- component-system refactor;
- queue UI;
- API cost instrumentation;
- cache behavior;
- incremental classification;
- prompt compression;
- batching changes;
- report synthesis optimization;
- navigation/routing changes;
- provider adapter changes that preserve contract.

Execution:

```text
inspect current behavior
→ define acceptance
→ identify rollback point
→ implement
→ targeted tests
→ regression
→ integration verification
→ report
```

Agent may execute autonomously only within the explicitly assigned scope.

---

## L3 — destructive, methodological, data or release risk

Examples:

- database migration;
- deleting canonical data;
- deleting Gold/Dev/Holdout;
- changing taxonomy;
- changing Evidence Grade;
- changing Five Questions;
- changing AnalysisDesign methodology;
- changing Version Review analytical semantics;
- changing canonical run lifecycle;
- changing integration DB;
- release/tag operations;
- changing secrets;
- modifying runtime isolation architecture;
- deleting archived provenance;
- changing model routing in a way that affects quality.

L3 requires explicit approval before destructive execution.

Required sequence:

```text
inspect
→ impact analysis
→ rollback point
→ exact proposed actions
→ user approval
→ execute
→ full verification
```

Never perform an L3 destructive action based only on inferred intent.

---

# 2. Frozen MVP contract

Authoritative frozen state:

```text
SENTINEXT_MVP_FROZEN
tag: sentinext-mvp-v1
```

The frozen analytical contract includes:

- taxonomy;
- classification schema;
- prompt identity/version history;
- Five Questions;
- FIX / IMPROVE / BUILD / AMPLIFY semantics;
- Evidence verification;
- Evidence Grade;
- AnalysisDesign;
- adaptive windows;
- Version Review comparative methodology;
- metric provenance;
- run provenance.

UI and cost work must not silently modify these contracts.

If an optimization or redesign requires changing them:

```text
STOP
→ classify as product/methodology change
→ request approval
```

Do not hide methodology changes inside "refactoring".

---

# 3. One agent = one worktree

Two agents must never actively edit the same physical working tree.

Required:

```text
integration/
agent-ui/
agent-cost/
```

Example ownership:

```text
Agent UI:
ui/redesign-v1

Agent Cost:
perf/api-cost-v1
```

No shared uncommitted files.

No agent may modify another agent's worktree.

Before editing a file, verify that the current worktree owns the task.

---

# 4. One runtime = one port set + one database

Canonical integration runtime:

```text
Frontend: 3000
Backend: 8000
DB: integration
```

Example isolated runtimes:

```text
UI agent:
Frontend 3101
Backend 8101
DB ui-agent

Cost agent:
Frontend 3102
Backend 8102
DB cost-agent
```

Rules:

- agent runtimes may not use integration ports;
- concurrent writable runtimes may not share SQLite DB;
- agent runtimes may not claim integration acceptance;
- `.env` must be profile-specific;
- do not automatically switch to "next available port".

If the declared port is occupied:

```text
FAIL STARTUP
```

Do not silently move to a different backend.

---

# 5. Runtime truth beats report truth

When there is disagreement between:

```text
old report
README
comment
assumption
```

and:

```text
current code
current database
current HTTP behavior
current runtime
```

inspect current runtime truth first.

Examples:

- `/health = 200` is not enough;
- required endpoint must actually exist;
- frontend backend URL must match runtime;
- exact run must exist in the active DB;
- UI must load the expected run.

Never infer product readiness from old release documents alone.

---

# 6. No fake completion

An agent MUST NOT say:

```text
READY
PASS
fixed
completed
working
```

unless the required acceptance evidence exists.

Forbidden examples:

```text
compile passed
→ therefore feature READY
```

```text
unit tests passed
→ therefore browser flow works
```

```text
agent-a runtime works
→ therefore integration works
```

```text
fixture output works
→ therefore real provider works
```

```text
HTTP 200
→ therefore result is semantically correct
```

Use exact language:

```text
implemented
code-level verification passed
integration not yet verified
browser not tested
real-provider not tested
```

when appropriate.

---

# 7. Exit artifact rule

Every L2/L3 phase must define what proves completion.

Examples:

## UI redesign

Completion evidence:

- implemented page;
- typecheck;
- build;
- browser screenshots;
- no console exceptions;
- exact user flow manually verified.

## API cost baseline

Completion evidence:

- `API_COST_BASELINE_RAW.json`;
- `API_COST_BASELINE.md`;
- ledger-backed measurements;
- workload identities;
- provider/model/prompt versions.

## Cost optimization

Completion evidence:

```text
before
after
cost delta
token delta
latency delta
quality delta
retry delta
cache delta
```

No exit artifact → no READY claim.

---

# 8. Acceptance must be defined before implementation

For every L2/L3 task, write acceptance first.

Example:

```text
Task:
reduce repeat-run classification cost

Acceptance:
- identical eligible run reuses >=95% cached labels;
- no change to raw population;
- no change to taxonomy;
- no material Gold regression;
- ledger confirms provider calls reduced;
- exact cache provenance remains valid.
```

Do not implement first and invent success criteria afterward.

---

# 9. Rollback point before risky work

Before:

- database migration;
- prompt change;
- provider routing;
- large UI rewrite;
- runtime configuration changes;
- cleanup/deletion;
- cost optimization that changes batching or semantic execution;

create a rollback point.

Possible rollback points:

```text
git commit
branch
tag
DB backup
config snapshot
prompt version
benchmark baseline
```

A rollback point must be named and identifiable.

---

# 10. Integration acceptance is separate from agent acceptance

Required lifecycle:

```text
agent worktree
↓
agent tests
↓
commit
↓
merge/rebase into integration
↓
restart integration runtime
↓
integration verification
↓
accept
```

Do not skip:

```text
merge
restart
integration check
```

An agent runtime PASS is not an integration PASS.

---

# 11. Global queue/run truth must be durable

For long-running analysis:

- `analysis_runs` is authoritative;
- queue is a projection of durable state;
- no in-memory-only success state;
- page refresh/navigation must not lose run state;
- invalid orphan runs must recover deterministically.

UI cannot invent completion.

Backend cannot report completion before immutable result persistence succeeds.

---

# 12. Exact-run identity rule

Every saved/recent result must resolve by:

```text
app_id + run_id
```

Never reopen by:

- title text;
- latest guess;
- in-memory selection;
- approximate game identity.

Canonical URL parameter:

```text
run
```

Old `run_id` may be read for compatibility, but new links must generate `run`.

---

# 13. UI redesign boundary

The UI redesign track may change:

- layout;
- spacing;
- typography;
- visual hierarchy;
- colors;
- icons;
- component architecture;
- chart presentation;
- responsive behavior;
- navigation presentation;
- animations/micro-interactions.

It may NOT silently change:

- metrics;
- taxonomy;
- model outputs;
- recommendation logic;
- Five Questions;
- Evidence Grade;
- sample definitions;
- analytical denominators;
- Version Review comparison semantics;
- API/provider behavior.

If UI cannot render existing semantics cleanly:

```text
adapt presentation
not methodology
```

---

# 14. Cost optimization boundary

The cost track may optimize:

- cache reuse;
- incremental classification;
- prompt size;
- output size;
- batching;
- provider caching;
- unnecessary synthesis calls;
- deterministic/LLM boundary;
- model routing only with evaluation.

It may NOT reduce cost by silently:

- analyzing fewer reviews without recording it;
- excluding difficult languages;
- skipping negative reviews;
- changing denominator;
- disabling taxonomy categories;
- dropping Evidence verification;
- reducing Version Review windows;
- replacing missing cost with zero;
- marking fallback classifications as valid.

Cost reduction must be attributable to an explicit mechanism.

---

# 15. Cost and quality must be measured together

Every cost optimization report must include:

```text
cost
tokens
calls
latency
retry
fallback
cache hit
classification coverage
schema validity
quality metrics
```

A change is not successful merely because:

```text
cost ↓
```

if:

```text
quality ↓ materially
coverage ↓
fallback ↑
```

Unknown quality impact must be reported as unknown.

---

# 16. No invented performance numbers

All claims such as:

```text
40% cheaper
2x faster
95% cache hit
accuracy improved
```

must come from measured data.

Required provenance:

```text
workload
run_id
provider/model
prompt version
sample size
ledger source
timestamp
```

Do not estimate and present as measured.

---

# 17. Provider/model changes require stronger gate

Switching:

```text
DeepSeek model
→ cheaper model
```

is not a simple cost refactor.

Minimum requirements:

- new provider/model identity;
- Dev/Gold evaluation;
- language slice checks;
- schema-valid rate;
- fallback rate;
- cost benchmark;
- latency benchmark.

Do not route "easy reviews" to a cheaper model before proving the routing criterion is reliable.

---

# 18. Prompt changes are versioned artifacts

Never overwrite the meaning of an existing prompt version.

Prompt modification:

```text
v16
→ v17
```

must create:

- new prompt identity;
- benchmark;
- eval comparison;
- rollback route.

Do not update prompt text while keeping the same version identifier.

---

# 19. Historical data is evidence, not disposable cache

Do not delete:

- canonical Steam review archive;
- version event provenance;
- immutable results;
- LLM cost ledger;
- Gold/Dev/Holdout;
- evidence source slices;
- migration history;

under "cleanup" without explicit L3 approval.

Build caches are disposable.

Analytical provenance is not.

---

# 20. Product dissatisfaction escalation

If the user says twice that the result is still wrong, stop patch-by-patch development.

Reclassify the problem first:

```text
A. correctness bug
B. data pipeline
C. methodology
D. information architecture
E. interaction flow
F. visual design
G. runtime/environment
```

Then identify the real layer before changing code.

Do not keep fixing symptoms if the user is rejecting the product concept.

---

# 21. Data-validity before interpretation

For any comparative/temporal analysis:

```text
coverage
population
window
event identity
sampling
```

must be valid before semantic interpretation.

Example:

```text
A = 3113
B = 17
```

must trigger coverage/support investigation before generating version conclusions.

No analysis layer may compensate for invalid upstream data by producing more prose.

---

# 22. Observed vs inferred vs needed evidence

All major product conclusions should preserve:

```text
Observed signal
Inferred mechanism
Evidence still needed
```

Do not convert observational review movement into causal claims.

This remains true even if the UI becomes more polished.

---

# 23. Evidence truth

Verified evidence means:

```text
quote/source slice exists
```

It does NOT automatically mean:

```text
semantic classification is correct
topic interpretation is correct
causal mechanism is correct
```

Do not collapse evidence existence and semantic accuracy.

---

# 24. LLM confidence is not accuracy

Model confidence cannot substitute for:

- Gold evaluation;
- human verification;
- precision/recall;
- slice analysis.

Do not expose confidence as "accuracy".

---

# 25. Coverage is not accuracy

Example:

```text
413 / 500 classified
= 82.6% coverage
```

This does not mean:

```text
82.6% correct
```

UI, reports, and release documents must keep these concepts separate.

---

# 26. No silent fallback contamination

Fallback/default labels must not enter normal KPI calculations as if they were validated semantic labels.

Track origin:

```text
live_provider
cache
fallback
fixture
```

Analytical metrics must honor provenance rules.

---

# 27. Review population truthfulness

Always distinguish:

```text
requested
retrieved
deduplicated
analysis population
semantic sample
classified
verified evidence
```

Do not use one number as shorthand for all stages.

Example:

```text
raw window = 8432
semantic sample = 1000
classified = 921
```

Never say:

```text
8432 AI-analyzed
```

---

# 28. Test pyramid for SentiNext

Use the smallest sufficient test first, then broaden.

Recommended order:

```text
unit
→ targeted regression
→ backend/frontend contract
→ full suite
→ integration runtime
→ browser flow
→ real provider only when necessary
```

Do not call paid provider to test CSS/layout.

Do not run a browser smoke as proof of model quality.

Use the right evidence for the claim.

---

# 29. Browser/manual acceptance rule

For user-facing flows, browser acceptance matters.

Examples:

- analysis start;
- global queue;
- recent-run reopening;
- Version Review;
- 3/7/14 filter;
- UI redesign.

If browser automation is unavailable:

```text
report BLOCKED
or
use manual browser evidence
```

Do not replace browser acceptance with `npm build`.

---

# 30. Error visibility

Authoritative APIs must not silently swallow errors.

Forbidden:

```ts
.catch(() => undefined)
```

for:

- queue;
- run start;
- run result;
- runtime compatibility;
- critical saved-analysis retrieval.

Errors must become explicit states.

---

# 31. Runtime compatibility handshake

Frontend must verify:

```text
runtime_profile
api_contract_version
capabilities
database_instance
```

A frontend connected to the wrong backend must fail visibly.

Do not continue silently if integration frontend is connected to an agent backend.

---

# 32. Cleanup rule

Cleanup is manifest-driven.

Before deletion:

```text
path
reason
KEEP / ARCHIVE / DELETE
```

must exist.

Never use broad destructive commands on project root.

Do not run:

```text
git clean -xdf
```

against the canonical repository without explicit L3 approval.

---

# 33. Archive, don't erase project history

Superseded:

- P0/P1 reports;
- old architecture;
- old NO_GO reports;
- UX iteration docs;
- execution plans;

may move to:

```text
docs/archive/
```

Do not keep every process document at root.

But preserve enough history to reconstruct major design decisions.

---

# 34. Release report vocabulary

Use only evidence-supported states.

Recommended:

```text
PASS
FAIL
BLOCKED
NOT RUN
PARTIAL
READY
NO_GO
```

Avoid vague states such as:

```text
basically done
should work
probably fixed
```

---

# 35. Agent final response format

For L2/L3 implementation tasks, final response should contain:

```text
What changed
What was not changed
Verification performed
Known limitations
Final gate
```

If NO_GO:

```text
exact blocker
next required action
```

Do not generate long self-congratulatory summaries.

---

# 36. Stop conditions

An agent must STOP and ask before proceeding when:

- task crosses frozen-methodology boundary;
- destructive cleanup becomes necessary;
- canonical DB must be changed destructively;
- secrets/credentials must be modified;
- release/tag must be rewritten;
- another agent owns the target worktree/files;
- integration environment cannot be identified;
- cost optimization appears to reduce analytical scope;
- user intent conflicts with existing freeze contract.

---

# 37. Recommended active branch structure

```text
sentinext-mvp-v1
│
├── release/mvp-v1          frozen
│
├── ui/redesign-v1          visual redesign
│
└── perf/api-cost-v1        cost optimization
```

Do not mix UI and cost changes in one branch unless a shared change is explicitly approved.

---

# 38. Current project priority

Current default priority:

```text
1. keep frozen MVP reproducible
2. improve UI without changing semantics
3. reduce API cost without reducing quality
4. dogfood real games
5. avoid infrastructure expansion
```

Not current priorities:

```text
PostgreSQL
Redis/Celery
vector DB
full auth
microservices
local bundled LLM
new analysis modes
```

unless future evidence creates a clear need.

---

# 39. Ten non-negotiable rules

If only ten rules are loaded into an agent context, use these:

1. Classify every task as L1/L2/L3 before execution.
2. Runtime/code/database truth beats old reports.
3. Never claim READY without the required acceptance evidence.
4. Agent-runtime PASS is not Integration PASS.
5. One agent = one worktree = one runtime profile = one writable DB.
6. L3 work requires a rollback point and explicit approval.
7. Define acceptance before implementation.
8. Two user rejections trigger problem re-diagnosis, not more patching.
9. UI/cost tasks must not silently modify frozen analytical contracts.
10. All cost/performance/quality numbers must come from measured evidence.

---

# 40. Governance mode for current two-agent development

## UI Agent

Allowed:

```text
layout
design system
components
charts
navigation
visual hierarchy
responsive behavior
```

Forbidden:

```text
taxonomy
analysis methodology
provider
DB schema
semantic sampling
Five Questions
Evidence Grade
```

Runtime:

```text
isolated UI worktree/runtime/DB
```

---

## Cost Agent

Allowed:

```text
ledger analysis
cache
incremental classification
prompt compression
batch benchmark
provider cache
synthesis call reduction
```

Forbidden without separate approval:

```text
taxonomy change
sample reduction hidden from user
language exclusion
model-routing quality tradeoff
database destructive change
```

Runtime:

```text
isolated cost worktree/runtime/DB
```

---

## Integration

Only merged, reviewed work enters:

```text
integration
```

After merge:

```text
restart
→ regression
→ browser
→ acceptance
```

Only then may the project state be updated.
