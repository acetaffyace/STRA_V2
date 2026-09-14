# STRA V2 Master Product Rebuild Specification

**Document status:** Master execution specification — hardened implementation candidate 1.1  
**Repository:** `acetaffyace/STRA_V2`  
**Baseline:** `main@f56dacfcf0ee6a25ac0128b9baa883cefd15d589` (`Merge Research Core V2 into main`)  
**Target:** End-to-end product rebuild from repository baseline through canonical run identity, durable population snapshots, backend/data migration, Semantic Engine V2, frontend information architecture, desktop usability, and final E2E acceptance.  
**Primary executor:** Codex autonomous engineering agent  
**Language:** Product semantics in Chinese; code identifiers and API contracts in English where appropriate.  
**Revision note:** 1.1 hardens execution invariants, population/time semantics, semantic measurement, durable jobs, migration/recovery, compatibility, benchmark gates, export identity, and milestone-level Definition of Done.

---

# 0. Purpose of this document

This document is the single execution source of truth for the next major rebuild of STRA.

It is intentionally broader than a normal PRD. It combines:

- product definition;
- research methodology contract;
- data and domain contracts;
- backend target architecture;
- Semantic Engine V2 contract;
- Core Taxonomy V2 contract;
- Game Topic / Emerging Topic lifecycle;
- Snapshot / Trend analysis contract;
- Version / Event Review contract;
- Cross-Game Compare contract;
- Evidence Explorer contract;
- Ask STRA contract;
- Exports contract;
- frontend information architecture;
- UI / UX hierarchy;
- migration and legacy compatibility;
- implementation milestones;
- automated testing and E2E scenarios;
- Codex autonomous execution protocol;
- final acceptance criteria.

This specification supersedes ad-hoc feature-by-feature development for this rebuild. Existing historical documents remain useful as evidence of previous decisions, but when they conflict with this document, this document wins unless a section explicitly marks a legacy behavior as immutable.


## 0.1 Normative precedence and hidden-dependency rule

This document is self-contained for product and research semantics. No unseen chat, prior review, prompt, or historical design note is normative unless this document names an exact repository path and version/commit.

When two sources disagree, apply this precedence:

1. this Master Spec 1.1;
2. versioned machine-readable contracts explicitly created by this spec (for example the canonical taxonomy source and persisted schema versions);
3. protected deterministic Research Core tests/contracts already present at the sealed baseline;
4. legacy documentation and historical implementation behavior.

A legacy implementation detail does not override this specification merely because it already exists in code.

The canonical Core Taxonomy V2 machine-readable source must be created at:

`docs/taxonomy/core_taxonomy_v2.yaml`

Its topic IDs and business meaning must be derived only from §8.2–§8.4 and Appendix A unless a later explicit product decision changes this document. The previous sentence in candidate 1.0 that referred to an unspecified "approved taxonomy review" is superseded; **no external unseen wording is required to implement this rebuild**.

## 0.2 Non-negotiable execution invariants

The following invariants apply across all modules and take precedence over convenience/legacy behavior:

1. `Game` identifies a game; it is never the analytical source of truth.
2. Formal deterministic results are identified by exact immutable `ResearchRun.run_id`.
3. Formal semantic results are identified by exact immutable `SemanticRun.semantic_run_id`.
4. A formal workspace must pin exact source IDs; "latest for app" is navigation convenience only.
5. Every formal run freezes exact population membership and review revision/content identity.
6. Formal time windows are persisted absolute windows; relative date phrases are resolved once at run creation.
7. Formal metrics are backend-owned canonical observations with explicit numerator/denominator/provenance; React pages must not recreate them from loaded rows.
8. Every Semantic Mention represents one topic assertion and at most one signal type; multiple valid topics/signals create multiple mentions rather than overloaded arrays.
9. Topic prevalence is review-level de-duplicated prevalence unless a metric explicitly says otherwise.
10. `PARTIAL` semantic output may be browsed but may not silently masquerade as full-population formal semantic output.
11. Version/Compare semantic deltas require compatible or explicitly harmonized semantic configurations.
12. Exports render exact canonical source resources and may not create a new analytical population.
13. Long-running work is a durable persisted Job with idempotency, progress, recovery and cancellation semantics.
14. User review text is untrusted data, including when passed to an LLM; review content never becomes executable instructions.
15. Migration, restart and duplicate-submit behavior are testable product requirements, not implementation details.

## 0.3 Canonical terminology

Use these terms consistently:

- **ReviewSnapshot** — one captured revision/content state of a Steam review.
- **PopulationSnapshot** — immutable ordered/set membership of ReviewSnapshots used by a formal run.
- **ResearchRun** — immutable deterministic analytical result over one PopulationSnapshot.
- **SemanticRun** — immutable semantic interpretation over one exact ResearchRun population under one semantic configuration.
- **Job** — mutable execution state that produces or materializes immutable resources; a Job is not itself the analytical result.
- **Formal metric** — canonical backend metric tied to exact source IDs and a versioned calculation contract.
- **Exploratory metric/view** — explicitly labeled slice or transformation that is not allowed to replace a formal metric.

---

# 1. Autonomous Execution Protocol for Codex

## 1.1 Mission

You are the primary execution engineer for the complete STRA product rebuild described by this specification.

Start from the actual repository state. Read this document completely before making architectural changes. Then inspect the repository and reconcile actual code, database schemas, tests, migrations, runtime profiles, and existing behavior against the target contracts defined here.

Your job is **not** to complete one isolated work package and wait for approval. Your job is to execute the entire rebuild through all milestones and final E2E acceptance.

## 1.2 Autonomy

Do not wait for user approval between normal implementation work packages or milestones.

For every work package:

1. inspect relevant existing code and tests;
2. implement the required target behavior;
3. migrate or adapt existing data/contracts safely;
4. run applicable tests, lint, type checks and integration checks;
5. review the diff against this specification;
6. fix failures and semantic regressions;
7. create a focused Git commit;
8. update the execution ledger;
9. continue automatically to the next work package/milestone.

You may return to an earlier work package when a later integration reveals an architectural defect. When doing so, rerun all affected contract and regression tests.

## 1.3 Decisions Codex may make independently

Codex may independently choose:

- internal file organization;
- class and function names;
- implementation patterns;
- library wrappers;
- SQL query structure;
- state-management implementation;
- internal component decomposition;
- non-breaking migration mechanics;
- test organization;
- caching implementation;
- batching strategy;
- exact local embedding implementation after benchmarking;
- exact clustering implementation after benchmarking;
- UI component composition as long as the UX contract is satisfied.

## 1.4 Decisions Codex must not silently change

Codex must not independently redefine:

- Research Run semantics;
- Sampling Contract semantics;
- deterministic Research Core metrics;
- historical data interpretation;
- Core Taxonomy V2 meaning;
- Game Topic / Emerging Topic lifecycle;
- Semantic Run immutability;
- formal Version Review comparability rules;
- formal vs exploratory metric distinction;
- Report/Export source-of-truth;
- the boundary between deterministic research computation and LLM reasoning;
- the rule that raw embedding similarity is not calibrated probability;
- the rule that LLM cannot silently mutate a production taxonomy;
- the rule that historical V1 labels are never silently reinterpreted as V2 labels;
- PopulationSnapshot and ReviewSnapshot immutability;
- canonical UTC/time-window semantics;
- formal metric denominators and review-level topic prevalence;
- SemanticMention cardinality/invariants;
- Semantic configuration compatibility semantics;
- durable Job/idempotency/recovery semantics;
- release-blocking quality gates defined in §12 and §35.

## 1.5 Conditions that justify stopping for user input

Only stop and request a product decision when at least one of the following is true:

1. two requirements in this specification are genuinely contradictory and code/tests cannot resolve them;
2. a required migration would irreversibly delete user data;
3. a required external paid service or secret is unavailable and no local/fallback path is permitted;
4. two implementation choices would produce materially different user-visible research conclusions and the specification provides no decision rule;
5. legal or external-provider constraints make the requested behavior impossible.

Normal code design, refactoring, test repair, compatibility layers, schema migrations and UI decomposition are **not** reasons to stop.

## 1.6 Prohibited completion shortcuts

Do not:

- delete or weaken failing tests merely to obtain green CI;
- replace real core-path validation with mocks when the real integration can be tested;
- reinterpret old labels as new taxonomy labels;
- recompute an old immutable result and present it as the historical result;
- let Export/Report establish a second analytical truth;
- use LLM output to replace deterministic Research Core metrics;
- label cosine similarity or distance as probability/confidence without calibration;
- hide invalid historical runs with hard-coded frontend IDs instead of a persisted validity/status contract;
- retain duplicate page-level business logic merely to avoid refactoring;
- call a sampled local slice “all reviews”;
- allow frontend ad-hoc recomputation to overwrite formal canonical metrics.

## 1.7 Execution ledger

Maintain:

`docs/STRA_V2_REBUILD_EXECUTION_LOG.md`

Each milestone/work-package entry must contain:

- milestone/work-package identifier and title;
- status: NOT_STARTED / IN_PROGRESS / BLOCKED / COMPLETE;
- scope implemented;
- contracts affected;
- database migration(s);
- API changes;
- frontend changes;
- tests executed and results;
- known limitations;
- commit SHA(s);
- any deviation from this specification and justification.

---

# 2. Current repository baseline and diagnosis

## 2.1 What is already strong and must be protected

At baseline `main@f56dacfc`, STRA already contains a valuable deterministic research foundation.

The following are not to be casually rewritten:

- configurable Steam review acquisition;
- Sampling Contract semantics;
- acquisition provenance;
- local persistence in SQLite;
- deterministic Research Core;
- population validity diagnostics;
- recommendation-rate computation;
- uncertainty assumptions and Wilson interval presentation;
- missingness handling;
- standardization/comparison methodology already accepted in Stage 2 workflows;
- 3/7/14-day window robustness infrastructure;
- activity / duplication / coordination diagnostics;
- immutable-ish Research Report persistence introduced in recent work;
- presentation projection endpoints;
- LLM cost ledger;
- desktop/Tauri packaging and runtime profile checks;
- Version Review V2 foundations.

The rebuild must consume and regularize these capabilities rather than restarting them.

## 2.2 Current product architecture problems

The product layer has accumulated functionality without one canonical user workflow.

Current primary navigation is approximately:

- Dashboard/Home;
- Chat;
- Compare;
- Reports;
- Version Review;
- Database;
- Settings.

`/reviews` exists separately as a drill-down surface.

This structure exposes historical implementation modules rather than the research workflow.

## 2.3 Current source-of-truth ambiguity

Current frontend state mixes several representations:

- exact analysis run/result;
- latest result for an `app_id`;
- in-memory analysis task;
- `StarredGameDTO` cached metadata;
- duplicated `insights`;
- duplicated `sample` reviews.

`AnalysisContext` currently fetches a completed latest analysis and persists its `metadata`, `insights`, and `sample` into StarredGame state/storage. This creates ambiguity between:

- favorite/bookmarked game identity;
- current task state;
- exact immutable run;
- latest app-level run;
- sample snapshot.

This must be removed.

## 2.4 Current page-level business logic concentration

Current frontend contains very large pages and duplicated domain logic. Baseline examples include approximately:

- `apps/dashboard/src/app/dashboard/page.tsx`: 224 KB;
- `apps/dashboard/src/app/compare/page.tsx`: 59 KB;
- `apps/dashboard/src/app/chat/page.tsx`: 51 KB;
- `apps/dashboard/src/app/version-review/page.tsx`: 43 KB;
- `apps/dashboard/src/lib/api.ts`: about 55 KB.

The backend has similar concentration in modules such as:

- `routes/analysis.py`;
- `chat_tools.py`;
- `routes/runs.py`;
- `chat.py`;
- `llm.py`.

The rebuild must move product semantics out of page components and create clear domain/services/features boundaries.

## 2.5 Current Reports problem

The existing Reports page mixes:

- latest app-level analysis result;
- monthly windows;
- separately generated executive PDF;
- additional Steam/live/risk widgets.

The backend report path can load stored reviews and labels and recalculate monthly insights, which risks creating a second analytical pipeline distinct from canonical Research Runs.

Target behavior: **Exports render canonical analysis results; they do not recreate them.**

## 2.6 Current Compare problem

Current Compare contains duplicated date/recommendation/trend logic and uses StarredGame/sample-derived data for exploratory filters. Formal metrics and locally filtered sample views can become visually indistinguishable.

Target behavior:

- formal cross-game metrics are generated by a canonical comparison contract;
- exploratory slices are explicitly labeled exploratory;
- client-side filtering may change display slices but must not silently replace formal metrics.

## 2.7 Current Evidence problem

Review exploration is split between `/reviews`, `/database`, dashboard samples, version evidence and chat citations.

These do not share one clear backend-driven filtering contract.

Target behavior: **one Evidence Explorer** for review/evidence drill-down.

## 2.8 Current Version Review strengths and debt

Version Review is the strongest current end-to-end research workflow. It already includes:

- version events;
- plans;
- exact run IDs;
- 3/7/14-day windows;
- population diagnostics;
- comparison structures;
- evidence/action presentation.

However it still contains historical implementation debt, including hard-coded invalid run IDs in the frontend and semantic taxonomy assumptions that must be aligned with Semantic Engine V2.

Target behavior: preserve the research design, replace ad-hoc validity and semantic coupling with persisted formal contracts.

## 2.9 Current semantic layer status

The README correctly defines Semantic Layer as optional and provider-dependent and marks future semantic sampling as deferred.

Current dependencies do not yet establish the intended local embedding/clustering pipeline. Existing semantic classification is primarily LLM/fixed-taxonomy oriented.

The rebuild must therefore introduce Semantic Engine V2 as a new versioned subsystem rather than silently morphing the old classifier.


## 2.10 Required migration bridge from the current baseline

The rebuild must account for current implementation reality instead of assuming target contracts already exist.

At baseline, Codex should expect and explicitly migrate these patterns:

- `apps/dashboard/src/contexts/AnalysisContext.tsx` uses app-centric task/result behavior. Move durable execution identity toward `job_id`/`run_id`; do not keep `app_id` as the unique identity for concurrent/historical analysis.
- `apps/dashboard/src/contexts/StarredGamesContext.tsx` and StarredGame DTO/storage contain analytical snapshots/samples. Stop new writes first, add compatibility reads/migration, then remove analytical fields after replacement verification.
- `apps/dashboard/src/app/reports/page.tsx` mixes latest app analysis with app/month report generation. Preserve old artifact access if needed, but route all new generation through exact source-resource Export contracts.
- `apps/dashboard/src/app/compare/page.tsx` performs page-local date filtering, weekly bucketing and recommendation calculations. Keep such logic only for explicitly exploratory UI while formal metrics migrate to backend canonical comparison projections.
- `apps/dashboard/src/app/version-review/page.tsx` contains frontend validity hacks and a frontend-supplied semantic limit. Replace hard-coded invalid-run IDs with persisted validity and ensure formal semantic coverage/configuration is backend-owned rather than defined by an arbitrary page constant.

Migration order principle:

`introduce canonical resource -> dual-read/compatibility bridge -> switch new writes/UI -> verify historical access -> remove deprecated analytical source`

Do not delete the old path before the new exact-run path can reopen representative historical and current data.

---

# 3. Product definition

## 3.1 Product statement

STRA is an **evidence-driven Steam Review Research Workbench** for game product, user research, publishing, live-ops and community teams.

STRA converts a defined Steam review population into reproducible quantitative and semantic research outputs, preserving provenance and allowing every material conclusion to be traced back to review evidence.

## 3.2 STRA must answer six product questions

For a selected game and research population:

1. **What is happening?**  
   Review volume, recommendation rate, trends, population structure.

2. **What are players talking about?**  
   Stable Core Topics, game-specific topics, issues, requests and praises.

3. **Who is affected?**  
   Language, playtime and other supported segments.

4. **What changed?**  
   Time trends and formal version/event comparisons.

5. **What evidence supports this?**  
   Original review text, provenance and semantic mention evidence.

6. **What should a researcher inspect next?**  
   Prioritized signals and structured interpretation, without pretending observational Steam data proves causation.

## 3.3 Non-goals for this rebuild

STRA is not being rebuilt as:

- a generic social listening platform;
- a real-time alerting system;
- a generic sentiment dashboard;
- a chatbot product;
- an autonomous decision-maker;
- a causal inference engine;
- a multi-platform ingestion framework before Steam is stable;
- an LLM that reads every review individually;
- a taxonomy that grows without governance.

## 3.4 Product design principle

The interface must move from **feature-first** to **research-workflow-first**.

Current mental model:

`Dashboard / Chat / Compare / Report / Database / Version Review`

Target mental model:

`Game → Research Population → Research Run → Quantitative + Semantic Analysis → Evidence → Compare/Version Review → Export/Interpret`

---

# 4. Canonical end-to-end workflows

## 4.1 Workflow A — Snapshot / Trend Analysis

1. Search/select a Steam game.
2. Configure the Sampling Contract.
3. Reuse stored reviews where provenance proves compatibility.
4. Acquire missing reviews when required.
5. Create an immutable Research Run.
6. Produce deterministic Research Core results.
7. Optionally create a Semantic Run using Semantic Engine V2.
8. Display Overview.
9. Inspect Signals.
10. Inspect Segments.
11. Inspect Trends.
12. Drill into Evidence.
13. Export the canonical result.
14. Ask STRA to explain existing results if desired.

## 4.2 Workflow B — Version / Event Review

1. Select a game.
2. Select or create a Version/Event anchor.
3. Define lifecycle/window policy.
4. Construct pre/post or matched version populations.
5. Validate comparability and coverage.
6. Produce quantitative delta.
7. Apply compatible semantic configuration to both populations.
8. Produce Topic delta and Emerging/Resolved Topic signals.
9. Identify affected segments.
10. Inspect 3/7/14-day robustness where applicable.
11. Inspect evidence.
12. Export Version Review.

## 4.3 Workflow C — Cross-Game Compare

1. Select exactly two games for V2 rebuild scope.
2. Select exact canonical runs or create compatible runs.
3. Check population compatibility.
4. Compare formal metrics.
5. Compare stable Core Topics.
6. Compare compatible Game/Archetype topics only where semantically valid.
7. Optionally apply clearly-labeled exploratory filters.
8. Inspect evidence separately for each game.
9. Export comparison.

## 4.4 Workflow D — Ask STRA

Ask STRA may:

- parse intent;
- interpret a user request into analysis setup parameters;
- prefill a Snapshot/Version/Compare workflow;
- navigate to the correct workspace;
- explain already-computed metrics/topics;
- retrieve and cite evidence.

Ask STRA must not, in this rebuild, automatically launch high-cost acquisition or LLM-heavy work without an explicit user action on the prepared analysis screen.

---

# 5. Canonical domain model

## 5.1 Game

Game contains identity and relatively stable metadata only.

Required principle:

`Game != Analysis Result`

Favorite/starred state may be attached to Game, but analytical results and review samples must not be embedded into the favorite record as canonical truth.

Suggested fields:

```text
app_id
name
header_image
basic Steam metadata
favorite flag
created_at
updated_at
```

## 5.2 SamplingContract

SamplingContract defines the requested Steam review population.

Canonical fields include:

```text
app_id
start_time
end_time
languages[]
review_type
purchase_type
collection_order
include_offtopic
max_reviews
```

Any existing legacy field names may be retained at the API edge for compatibility, but canonical internal semantics must map to this model.

## 5.3 AcquisitionResult

Must distinguish requested population from observed acquisition.

Required fields/semantics:

```text
requested_contract
observed_count
collection_complete
truncated_by_max_reviews
stop_reason
language_stats
provider/source metadata
acquired_at
review_snapshot_ids[] or immutable population snapshot reference
```

AcquisitionResult is provenance about collection. It is not itself a formal analytical result and must not be used as a mutable substitute for PopulationSnapshot.

## 5.4 ResearchRun

ResearchRun is the canonical formal unit for Snapshot Research Core output.

A formal analysis result must be addressable by exact `run_id` and must bind one immutable PopulationSnapshot.

Required fields/semantics:

```text
run_id
run_type = snapshot
app_id
sampling_contract
sampling_contract_version
acquisition_provenance
population_snapshot_id
population_hash
anchor_time
research_core_version
metric_schema_version
time_semantics_version
config
status
created_by_job_id
created_at
completed_at
validity_status
immutable_result_ref
```

Rules:

- `run_id` is the formal deterministic result identity.
- `population_snapshot_id` and `population_hash` cannot change after the run reaches READY/PARTIAL/FAILED terminal state.
- `anchor_time` freezes any relative-window interpretation such as "last 30 days".
- a successful ResearchRun remains valid even if a later SemanticRun fails.
- app-level latest endpoints may resolve/navigate to a run ID but must never substitute silently after exact context has been selected.
- a ResearchRun must never read current mutable Review rows at display time to reconstruct its original population.

## 5.5 ResearchContext

Frontend and cross-module navigation must use one explicit exact context:

```json
{
  "app_id": 123,
  "run_id": "run_...",
  "semantic_run_id": "sem_...",
  "analysis_mode": "snapshot",
  "population_snapshot_id": "pop_...",
  "population_contract_version": "...",
  "taxonomy_version": "stra-core-taxonomy-v2"
}
```

Fields may be nullable where the layer is not available, but once an exact formal resource is selected its ID must remain pinned until the user deliberately changes it.

The URL must expose enough context to restore the exact formal workspace after refresh/restart. If more than one SemanticRun exists for a ResearchRun, a formal Signals/semantic view must not silently choose "latest" while claiming to show an historical exact result. It must either:

- include `semantic_run_id` in URL/context; or
- require an explicit semantic-run selection that is then persisted in URL/context.

## 5.6 SemanticRun

SemanticRun is a versioned, immutable semantic interpretation of one exact ResearchRun population.

Required fields/semantics:

```text
semantic_run_id
research_run_id
population_snapshot_id
population_hash
semantic_engine_version
core_taxonomy_version
game_topic_catalog_version
archetype_topic_pack_versions[]
embedding_model_version
embedding_artifact_hash
prototype_versions
calibration_version
segmentation_version
normalization_version
assignment_policy_version
llm_adjudication_policy_version
semantic_config_json
semantic_config_hash
status
eligible_review_count
processed_review_count
semantic_coverage
unresolved_review_count
created_by_job_id
created_at
completed_at
cost_summary
result_ref
```

`semantic_config_hash` must cover every parameter/artifact that can materially change final SemanticMentions, including model artifact identity, taxonomy/catalog versions, normalization/segmentation, prototypes, thresholds/calibration, assignment policy and LLM adjudication policy.

Old Semantic Runs must never be silently rewritten when taxonomy/model/prototype/configuration changes. A changed semantic configuration creates a new SemanticRun.

## 5.7 SemanticUnit

A SemanticUnit is the minimum semantic classification unit.

Rules:

- short reviews may map to one unit;
- long reviews may map to multiple units;
- a unit should represent one locally coherent semantic statement;
- one unit may yield multiple SemanticMentions when more than one valid topic assertion exists;
- evidence boundaries must be reproducible across Python and JavaScript runtimes.

Required fields/semantics:

```text
semantic_unit_id
semantic_run_id
review_snapshot_id
source_content_hash
start_byte_offset
end_byte_offset
text_snapshot
segmentation_version
```

Offsets are **UTF-8 byte offsets into the exact ReviewSnapshot content bytes**. Do not persist ambiguous runtime-native string indices (for example JavaScript UTF-16 indices) as the canonical cross-runtime evidence coordinate.

`text_snapshot` is allowed as a convenience/cache, but `source_content_hash + byte offsets + review_snapshot_id` define traceability.

## 5.8 SemanticMention

SemanticMention represents one topic assertion from one SemanticUnit.

Required fields/semantics:

```text
mention_id
semantic_run_id
semantic_unit_id
core_topic_id
secondary_topic_id (nullable; archetype/game topic only)
signal_type (nullable: issue | request | praise)
assignment_source
similarity_score
calibrated_confidence (nullable)
decision_band
prototype_version
adjudication_ref (nullable)
```

Hard invariants:

1. one SemanticMention has exactly one `core_topic_id`;
2. one SemanticMention has zero or one secondary Archetype/Game Topic;
3. one SemanticMention has zero or one primary `signal_type`;
4. a SemanticUnit may have multiple SemanticMentions;
5. a ReviewSnapshot may have multiple units and mentions;
6. legitimate co-occurrence such as `service_operations/update_quality` plus `technical/performance` is represented as two mentions, not one array-valued mention;
7. praise + issue + request in one review must remain distinct mentions where they refer to distinct assertions;
8. duplicate mentions of the same topic within one review do not give that review multiple votes in formal topic prevalence.

## 5.9 TopicDefinition

TopicDefinition is the business definition of a topic.

Do not store model-specific embedding vectors directly as the topic definition.

Suggested fields:

```text
topic_id
name
scope = core | archetype | game
definition
include_rules
exclude_rules
boundary_rules
aliases[]
primary_parent
related_topics[]
status
catalog_version
created_at
updated_at
```

## 5.10 TopicPrototypeSet

TopicPrototypeSet is the model-specific representation used for local matching.

Suggested fields:

```text
topic_id
embedding_model_version
prototype_version
centroid/vector refs
exemplar_semantic_unit_ids[]
positive examples
hard negative examples
calibration_version
```

Changing embedding model must not force a business taxonomy version change.

## 5.11 EmergingTopicCandidate

Suggested fields:

```text
candidate_id
semantic_run_id
cluster_id
provisional_name
provisional_definition
cluster_size
nearest_known_topics
representative_unit_ids
segment_distribution
time_distribution
recommendation_distribution
llm_recommendation
promotion_target = game | archetype | refine_existing | none
status = detected | reviewed | pending | accepted | merged | rejected | deferred
reviewed_at
accepted_topic_id
```

No candidate may automatically become a production taxonomy topic.

## 5.12 VersionEvent

Represents a release/version/patch/season/DLC or other explicitly anchored product event.

VersionEvent is research context, not a Core Topic.

## 5.13 VersionReviewRun

Must persist:

- anchor event(s);
- window policy;
- population membership/provenance;
- comparability diagnostics;
- quantitative comparison;
- semantic configuration compatibility;
- topic deltas;
- evidence links;
- robustness outputs.

## 5.14 ComparisonRun

A formal cross-game comparison must have its own persisted contract and exact source runs.

## 5.15 ExportManifest

Every export must persist enough metadata to prove its source.

Suggested fields:

```text
export_id
export_type
source_run_ids[]
source_semantic_run_ids[]
template_version
generated_at
language
format
population_contract_refs[]
```


## 5.16 ReviewSnapshot

A ReviewSnapshot freezes one observed revision/content state of a Steam review so historical runs remain reproducible if the upstream review is edited later.

Required fields/semantics:

```text
review_snapshot_id
steam_review_id
app_id
content_text
content_hash
voted_up
language
timestamp_created
timestamp_updated (nullable)
author/review metadata required by accepted Research Core
provider/source metadata
fetched_at
snapshot_schema_version
```

A later refetch of an edited review creates a new ReviewSnapshot or new revision record. Historical PopulationSnapshots retain the original revision reference.

## 5.17 PopulationSnapshot

PopulationSnapshot freezes exact membership used by a formal run.

Required fields/semantics:

```text
population_snapshot_id
app_id
sampling_contract_canonical_json
sampling_contract_hash
ordered_review_snapshot_ids[] or normalized membership table
membership_count
population_hash
anchor_time
created_at
```

The persisted representation may use a normalized membership table rather than one JSON array, but membership and order semantics must be immutable and hashable.

## 5.18 Review-level semantic rollups

Canonical rollups must support de-duplicated formal prevalence without depending on segmentation granularity.

At minimum expose or materialize equivalent unique keys:

```text
ReviewTopicRollup:  unique(semantic_run_id, review_snapshot_id, core_topic_id)
ReviewSignalRollup: unique(semantic_run_id, review_snapshot_id, core_topic_id, signal_type)
```

Secondary Game/Archetype topic rollups may be modeled similarly.

## 5.19 Job

Long-running acquisition, semantic analysis, harmonized reprocessing, comparison materialization and export generation must use a durable Job contract.

Required fields/semantics:

```text
job_id
job_type
target_resource_type
target_resource_id (nullable until allocated)
idempotency_key
status = QUEUED | RUNNING | SUCCEEDED | PARTIAL | FAILED | CANCELLED
stage
progress_current
progress_total
progress_unit
attempt_count
heartbeat_at
retryable
cancel_requested_at
error_code
error_detail
created_at
started_at
finished_at
```

A Job is mutable execution state. It does not replace the immutable ResearchRun/SemanticRun/Export resource it creates.

## 5.20 MetricObservation

Every formal metric returned to the frontend must be representable with enough provenance to avoid hidden denominator drift.

Canonical shape:

```text
metric_id
metric_version
source_resource_id
population_snapshot_id
value
unit
numerator (nullable)
denominator (nullable)
missing_count (nullable)
method/model note (nullable)
availability = AVAILABLE | PARTIAL | UNAVAILABLE
```

Equivalent typed projections are acceptable; the invariant is that formal metrics expose their calculation identity and source rather than appearing as context-free numbers.


## 5.21 TopicEquivalence

Formal cross-game comparison of secondary topics requires an explicit versioned equivalence object when two topic IDs are not already the same accepted Archetype Topic.

Suggested fields:

```text
equivalence_id
left_topic_id
right_topic_id
scope = formal_compare | display_only
rationale
evidence_ref
status = proposed | accepted | rejected | deprecated
version
created_at
reviewed_at
```

Only `status=accepted` and `scope=formal_compare` may authorize a formal secondary-topic comparison. Embedding/text similarity alone never creates this object automatically.

---

# 6. Review acquisition contract

## 6.1 Preserve existing configurable acquisition

Existing user value must remain:

- date/time filtering;
- language filtering;
- recommendation/review type filtering where Steam supports it;
- purchase type filtering;
- collection order;
- optional off-topic inclusion;
- review count/max cap;
- provenance.

## 6.2 Required semantics

The UI must always distinguish:

- requested population;
- observed reviews;
- complete collection;
- truncated collection;
- unavailable provider state;
- partial/error state.

A count shown in the UI must never imply “all reviews” unless acquisition proves collection completeness for the requested contract.

## 6.3 Reuse policy

Stored reviews may be reused only when their provenance satisfies the requested contract. Reuse must not hide gaps.

## 6.4 Acquisition UX

Analysis Setup must preview:

- game;
- date range;
- languages;
- review type;
- purchase type;
- collection order;
- max reviews;
- whether stored data can be reused;
- whether additional acquisition is required.


## 6.5 Population reuse compatibility

Stored data may be reused only through an explicit compatibility decision. Implement a backend compatibility service that returns one of:

- `EXACT` — existing PopulationSnapshot exactly satisfies the requested canonical contract;
- `SAFE_SUBSET` — a deterministic subset can be derived without inventing missing members and the resulting membership is materialized as a new PopulationSnapshot;
- `INCOMPATIBLE` — additional acquisition/rebuild is required.

The decision must include machine-readable reasons. At minimum evaluate:

- app ID;
- absolute start/end window;
- language set;
- review type;
- purchase type;
- collection order when order affects capped membership;
- off-topic inclusion;
- max/cap and truncation state;
- provider/source semantics;
- completeness/coverage.

A capped or truncated collection must never be treated as a complete superset merely because its observed rows overlap the new request.

## 6.6 Canonical time semantics

All formal persisted timestamps use UTC instants.

Rules:

1. formal time windows use half-open intervals `[start_at, end_at)`;
2. user-entered local dates/times are converted once at setup time and the resulting UTC instants are persisted;
3. relative windows such as "last 30 days" are resolved against persisted `anchor_time`, never against display-time `now()`;
4. daily buckets use UTC calendar-day boundaries unless a future explicitly versioned timezone policy says otherwise;
5. weekly buckets use ISO week semantics starting Monday 00:00 UTC;
6. VersionEvent stores source timestamp precision. If the provider supplies date-only precision, the system must persist that precision and apply one versioned date-only anchoring rule rather than pretending an exact release second is known;
7. frontend and backend must consume the same versioned time semantics; React page-local `new Date()` must not change historical formal population membership.

## 6.7 Content revision and historical evidence

Reopening a historical run must display the ReviewSnapshot revision that belonged to its PopulationSnapshot. The Evidence Explorer may optionally indicate that a newer upstream review revision exists, but it must not replace historical evidence silently.

---

# 7. Deterministic Research Core contract

## 7.1 Freeze principle

The Stage 1–2P deterministic foundation is treated as protected infrastructure.

Refactor interfaces and code organization where necessary, but do not change accepted metric meaning without an explicit version bump and compatibility plan.

## 7.2 Core outputs

At minimum, canonical Snapshot Research Core should expose:

- observed review count;
- recommendation numerator/denominator/rate;
- interval under documented model assumptions;
- daily/weekly review volume;
- daily/weekly recommendation rate;
- language distribution;
- playtime distribution/cohorts;
- Steam purchase status;
- received-for-free status;
- Early Access status where supported;
- Steam Deck/platform metadata where available;
- missingness;
- acquisition validity;
- activity/duplicate/coordination diagnostics;
- provenance;
- limitations.

## 7.3 Recommendation semantics

`voted_up` is Recommended / Not Recommended.

It is not:

- text sentiment;
- overall satisfaction;
- representative opinion of all owners/players.

UI copy must preserve this distinction.

## 7.4 Deterministic ownership

LLM must never calculate or override canonical quantitative metrics.

Narrative summaries may describe canonical metrics but must cite them rather than recompute them.


## 7.5 Formal metric denominator contract

Every formal rate/count must define its eligible population and denominator in backend code/tests.

Required examples:

- recommendation rate = Recommended reviews / reviews with valid `voted_up` in the PopulationSnapshot;
- language share = reviews in language / reviews with non-missing language under the declared missingness policy;
- segment rate = eligible recommended/not-recommended reviews in segment / eligible reviews in segment;
- topic prevalence = defined in §11.15 and must not use raw SemanticMention count as its denominator.

The frontend may format canonical values but must not reconstruct formal numerator/denominator logic from loaded Review rows.

## 7.6 Calculation versioning

A material change to accepted deterministic metric meaning requires a version bump (`research_core_version` and/or metric-specific version), regression documentation, and compatibility behavior for historical runs. Refactoring that preserves results does not require a semantic version change.

---

# 8. Core Taxonomy V2 contract

## 8.1 Global principles

Core Taxonomy V2 describes stable, cross-game product dimensions.

It must not encode:

- specific heroes/weapons/maps;
- specific versions/patches;
- sentiment;
- issue/request/praise intent;
- memes;
- off-topic status;
- unclear/ambiguous state;
- mixed state;
- game-specific business objects.

Semantic flags and signals are separate dimensions.

## 8.2 Frozen top-level domains

Core Taxonomy V2 freezes these 9 domains:

1. `overall_experience`
2. `gameplay`
3. `technical`
4. `content`
5. `ux_accessibility`
6. `presentation`
7. `online_community`
8. `service_operations`
9. `commercial_model`

## 8.3 Frozen 50 subtopics

### overall_experience

1. `overall_experience/general`

### gameplay

2. `gameplay/mechanics`  
3. `gameplay/controls`  
4. `gameplay/balance`  
5. `gameplay/difficulty`  
6. `gameplay/progression`  
7. `gameplay/ai_behavior`

### technical

8. `technical/performance`  
9. `technical/bugs`  
10. `technical/stability_crashes`  
11. `technical/compatibility`  
12. `technical/networking`  
13. `technical/installation_launch`  
14. `technical/save_data`

### content

15. `content/scope_variety`  
16. `content/world_level_design`  
17. `content/activities_modes`  
18. `content/narrative_characters`  
19. `content/replayability`  
20. `content/content_pacing`  
21. `content/customization`

### ux_accessibility

22. `ux_accessibility/interface_hud`  
23. `ux_accessibility/readability_clarity`  
24. `ux_accessibility/quality_of_life`  
25. `ux_accessibility/input_device_support`  
26. `ux_accessibility/accessibility`  
27. `ux_accessibility/onboarding_learnability`

### presentation

28. `presentation/visuals_art`  
29. `presentation/animation`  
30. `presentation/audio_music`  
31. `presentation/voice_acting`  
32. `presentation/localization`

### online_community

33. `online_community/multiplayer_experience`  
34. `online_community/matchmaking`  
35. `online_community/social_features`  
36. `online_community/competitive_integrity`  
37. `online_community/moderation_safety`  
38. `online_community/mods_ugc_ecosystem`

### service_operations

39. `service_operations/update_quality`  
40. `service_operations/update_cadence`  
41. `service_operations/roadmap_delivery`  
42. `service_operations/developer_communication`  
43. `service_operations/customer_support`

### commercial_model

44. `commercial_model/pricing`  
45. `commercial_model/regional_pricing`  
46. `commercial_model/paid_content`  
47. `commercial_model/microtransactions`  
48. `commercial_model/monetization_fairness`  
49. `commercial_model/monetization_pressure`  
50. `commercial_model/value_for_money`

## 8.4 Mandatory high-risk boundary rules

The production taxonomy contract must preserve at least the following distinctions:

- `mechanics` = how the system works; `controls` = how player input operates it.
- `balance` = relative strength/fairness of legitimate options; `difficulty` = absolute challenge faced by the player.
- `progression` = player advancement; `content_pacing` = narrative/activity pacing.
- `performance` = slow/stutter/resource performance while running; `stability_crashes` = termination/freeze/hang.
- `networking` = connection quality; `matchmaking` = who the system pairs together.
- `scope_variety` = amount/variety of first-order content; `replayability` = reason to continue/replay after completion.
- `world_level_design` = spatial structure; `visuals_art` = visual presentation.
- `interface_hud` = interface organization/interaction; `readability_clarity` = visibility/comprehension of presented information.
- `readability_clarity` = information is present but unclear; `onboarding_learnability` = game fails to teach the player.
- `controls` = input feel; `input_device_support` = device/configuration capability.
- `technical/bugs` = fallback technical functional defect; more specific technical categories take precedence.
- `voice_acting` = performance/delivery; `narrative_characters` = writing/content.
- `update_quality` = evaluation of patch/update outcome; `technical/*` = current product defect. They may co-occur.
- `update_cadence` = real-world update frequency; `content_pacing` = in-game pacing.
- `developer_communication` = one-to-many public communication; `customer_support` = one-to-one support handling.
- `microtransactions` = purchase mechanism exists; `monetization_fairness` = mechanism creates unfair advantage/restriction; `monetization_pressure` = mechanism pressures spending.
- `pricing` = price itself; `value_for_money` = experience relative to price.
- `pricing` = general price; `regional_pricing` = regional/currency/purchasing-power differential.

## 8.5 Full definition contract requirement

Implementation must place the full Definition / Include / Exclude / Boundary / Typical Examples / Counterexamples contract in the versioned machine-readable source:

`docs/taxonomy/core_taxonomy_v2.yaml`

For Master Spec 1.1, the normative business meaning is the frozen topic IDs in §8.3, mandatory boundaries in §8.4, and concise meanings in Appendix A. No unspecified prior chat/review is a required dependency.

The structured source may add examples, aliases and hard negatives to operationalize those meanings, but it must not broaden/narrow/re-parent a topic in a way that changes the distinctions in §8.4 without an explicit taxonomy version change.

A schema validator must fail CI if any of the 50 topics lacks required fields or if IDs are duplicated/renamed unexpectedly.

## 8.6 Legacy taxonomy

Existing taxonomy V1/V3 labels remain historical data.

Do not rename them in place.

Create a new version identifier, e.g.:

`stra-core-taxonomy-v2`

Old labels that are safely identical may have an explicit mapping for display/migration tooling. Ambiguous composites such as old `pay_to_win_grind`, `battle_pass_fomo`, `other/mixed`, `other/unclear`, `presentation/atmosphere`, etc. must not be silently mapped to V2.

They require either:

- legacy rendering; or
- explicit reclassification under a new Semantic Run.

---

# 9. Signal and semantic-flag contract

## 9.1 Signal types

Signals are separate from topic classification.

Freeze the primary signal set for this rebuild as:

- `issue`
- `request`
- `praise`

No `mixed` signal.

If no explicit signal applies, `signals=[]` is valid.

A review with praise and complaint should produce distinct mentions rather than a single mixed label.

## 9.2 Semantic flags

Keep data/utterance-state flags outside taxonomy, e.g.:

- `off_topic`
- `meme`
- `ambiguous`
- `insufficient_content`
- `meta_discussion`

Exact set may be refined in implementation, but none may become a Core Topic.

---

# 10. Game Topic / Archetype Topic contract

## 10.1 Purpose

Core Taxonomy is intentionally stable and broad. Game Topics capture specific, actionable semantic objects.

Examples:

Competitive shooter archetype:

- weapon balance;
- map balance;
- ranked system;
- anti-cheat implementation;
- queue quality;
- netcode implementation.

Specific game:

- CS2 Premier Rating;
- CS2 subtick;
- Elden Ring Scadutree Fragment progression;
- a named boss;
- a named DLC mechanic;
- a specific mode/map/character.

## 10.2 Scope hierarchy

Externally the product exposes:

- Core Topics;
- Game Topics;
- Emerging Topics.

Internally Game Topics may have:

- `scope=archetype`;
- `scope=game`.

This avoids unnecessary product-level hierarchy while enabling reusable topic packs.

## 10.3 Stability

Accepted Game/Archetype topics are persistent and versioned.

They are not regenerated from scratch every run.

## 10.4 Governance

New topics follow:

`Detected → LLM Reviewed → Pending → Accept / Merge / Reject / Defer`

Only an explicit accepted action changes the production topic catalog.

LLM output is a recommendation, never direct taxonomy mutation.

---

# 11. Semantic Engine V2 contract

## 11.1 Objective

Process large Steam review populations efficiently while retaining:

- per-review final labels;
- stable cross-game Core Topics;
- stable game-specific topics;
- discovery of new topics;
- evidence traceability;
- bounded LLM cost;
- immutable reproducibility.

## 11.2 Architecture

```text
Research Run Population
        ↓
Semantic Unit Segmentation
        ↓
Local Multilingual Embedding
        ↓
Known Topic Prototype Matching
(Core + Archetype + Game)
        ↓
HIGH / MEDIUM / LOW decision bands
        ↓
Discovery Pool
        ↓
Clustering / substructure discovery
        ↓
Representative Sampling
        ↓
Selective LLM Adjudication
        ↓
Semantic Mentions
        ↓
Review-level Rollup
        ↓
Immutable Semantic Run
```

## 11.3 Semantic Unit segmentation

Do not use full review text as the only semantic unit.

Requirements:

- preserve short reviews as one unit when appropriate;
- split long multi-topic reviews into coherent statements/short passages;
- preserve offsets/evidence spans;
- avoid overfragmentation that destroys context;
- version segmentation policy.

## 11.4 Local embedding

The embedding layer must be:

- multilingual;
- local-first;
- batchable;
- replaceable;
- deterministic enough for reproducible runs under the same version/config;
- usable on the target desktop environment;
- benchmarked for representative English/Chinese/Japanese and other common Steam languages before freeze.

The Master Spec intentionally does not hard-code a model name.

## 11.5 Prototype matching

Each Semantic Unit should be compared against:

- Core Topic prototype sets;
- applicable Archetype Topic prototype sets;
- Game Topic prototype sets.

Prototype data may include:

- definitions;
- aliases;
- validated exemplars;
- hard negatives;
- centroids.

## 11.6 Decision bands

Use semantic decision bands:

- `HIGH`
- `MEDIUM`
- `LOW`

Do not expose raw similarity as calibrated confidence.

Store at minimum:

```text
similarity_score
decision_band
calibration_version
```

Only expose `calibrated_confidence` if an actual calibration procedure exists.

Thresholds must be configurable and benchmark-derived. They may vary by model/language/topic family if evidence supports it.

## 11.7 Local acceptance

High-confidence known-topic matches may be accepted locally without LLM.

Medium-confidence assignments may be provisional and sampled for QA/discovery according to the versioned assignment policy.

Low-confidence assignments may remain `unresolved`. **Do not force a semantically uncertain review into `overall_experience/general` or another Core Topic solely to achieve 100% coverage.**

A review may still be semantically eligible while having no resolved Core Topic after all permitted adjudication. Such unresolved state must be counted explicitly in SemanticRun coverage/quality statistics. Unresolved semantic-eligible reviews remain in the formal topic-prevalence denominator and contribute to no resolved topic numerator; this prevents prevalence from being inflated merely because the classifier became more uncertain.

## 11.8 Discovery Pool

Discovery Pool must not be limited to LOW-confidence units.

It should include configurable sources such as:

- LOW-confidence units;
- selected MEDIUM-confidence units;
- statistically meaningful samples of HIGH-confidence high-volume topics;
- recent temporal bursts;
- dense substructure within broad known topics;
- novelty/outlier candidates.

Reason: an emerging specific issue may be highly similar to a broad Core Topic and would otherwise be swallowed by the broad topic.

## 11.9 Clustering

Clustering is a discovery/refinement tool, not the final production label authority.

Its responsibilities are:

- discover candidate new topics;
- expose meaningful substructure inside broad known topics;
- support merge/split suggestions;
- select coherent evidence sets.

The clustering algorithm is implementation-specific and must be benchmarked. Do not hard-code one algorithm in the product contract.

## 11.10 Representative sampling

For each candidate cluster, sample multiple evidence types:

- high-centrality/representative units;
- diverse units;
- boundary units;
- optionally high-helpfulness/high-engagement review evidence if methodologically justified.

Do not send arbitrary first-N cluster reviews to LLM.

## 11.11 Selective LLM adjudication

LLM receives structured cluster context rather than raw review dumps.

Include where available:

- cluster size;
- recommendation distribution;
- language distribution;
- playtime/segment distribution;
- time trend;
- nearest known topics and similarity summaries;
- representative units;
- boundary examples.

LLM may recommend:

- existing topic;
- existing topic refinement;
- merge;
- split;
- new candidate topic;
- noise/no useful topic.

LLM may also propose:

- provisional topic name;
- definition;
- parent Core Topic;
- likely signal interpretation.

LLM must not mutate production taxonomy directly.

## 11.12 Per-review final assignment

Semantic assignment is mention-based and then rolled up to review-level formal observations.

Example:

```text
"Combat is great, performance is terrible, please add crossplay."

mention 1:
  gameplay/mechanics + praise

mention 2:
  technical/performance + issue

mention 3:
  online_community/social_features + game_topic/crossplay + request
```

Do not flatten this into one mixed label.

For a unit such as "The last update ruined performance", two Core Topic assertions may legitimately co-occur:

```text
mention A: service_operations/update_quality + issue
mention B: technical/performance + issue
```

The same unit therefore may own multiple SemanticMentions, each obeying §5.8 cardinality.

A semantically eligible review is not required to receive a resolved Core Topic when assignment remains genuinely ambiguous after the configured path. Unresolved output is preferable to fabricated certainty.

## 11.13 Semantic immutability

When taxonomy/model/prototype changes, create a new Semantic Run.

Never modify historical semantic results in place.


## 11.14 Semantic configuration identity

Persist canonical `semantic_config_json` and a stable `semantic_config_hash`.

The hash must change when any material assignment input changes, including at minimum:

- Core Taxonomy version;
- Game/Archetype catalogs;
- embedding model identifier **and artifact checksum**;
- normalization/segmentation policy;
- prototype artifacts;
- decision thresholds/calibration;
- assignment policy;
- LLM adjudication prompt/schema/model policy where adjudication can affect final labels.

Do not rely only on human-readable model names such as `model-v1` when the underlying artifact can differ.

## 11.15 Formal semantic measurement

Formal Core Topic prevalence is **review-level de-duplicated prevalence**:

```text
resolved_topic_reviews(topic)
---------------------------------
semantic_prevalence_denominator
```

Where:

- `resolved_topic_reviews(topic)` = unique eligible ReviewSnapshots with at least one resolved ReviewTopicRollup for the topic;
- `semantic_prevalence_denominator` = unique semantic-eligible ReviewSnapshots successfully processed to the minimum state required by the SemanticRun policy, **including unresolved-only reviews**, while excluding explicitly semantic-ineligible states such as off-topic/insufficient-content according to the versioned eligibility policy.

The API must also expose the denominator count and unresolved/excluded counts.

A review mentioning the same topic three times still contributes one review to formal prevalence.

Raw `SemanticMention` count may be exposed as a separate descriptive metric such as `mention_count` or `mention_intensity`, but must never be labeled Topic prevalence.

Formal signal prevalence follows the same de-duplicated review-level principle for `(topic, signal_type)` unless another metric is explicitly named/versioned.

## 11.16 PARTIAL semantic result rule

A SemanticRun with `status=PARTIAL` must expose:

```text
eligible_review_count
processed_review_count
semantic_coverage
unresolved_review_count
failure/remainder reason
```

PARTIAL results may support evidence inspection and diagnostic previews. They may only expose formal population-level Topic prevalence/delta when the backend can prove that the metric's required denominator is complete under the versioned method. Otherwise the metric availability must be `PARTIAL` or `UNAVAILABLE`, not a deceptively precise percentage.

Version Review and formal Cross-Game Compare must reject semantic delta when either side lacks required semantic coverage under the compatibility contract.

## 11.17 LLM input security and structured adjudication

Steam review text, usernames, linked text and retrieved evidence are untrusted data.

When sent to an LLM:

- wrap/encode review text as data fields, never system/developer instructions;
- instruct the model that quoted review content cannot change task rules;
- require structured schema-validated output;
- give adjudication no tool/capability that can mutate production taxonomy directly;
- reject malformed/out-of-schema output rather than executing embedded instructions;
- log prompt/policy version and adjudication provenance;
- escape rendered review content in HTML/Markdown/UI to prevent script/markup injection.

Add adversarial tests containing prompt-injection-like review text.

---

# 12. Semantic Engine evaluation and benchmark contract

Semantic V2 cannot be labeled `PRODUCT_READY` merely because the pipeline runs. Quality gates are release-blocking.

## 12.1 Two evaluation assets

Maintain two different assets:

### A. Boundary Regression Suite

A curated 200–500 example suite focused on known confusions and previous regressions, including:

- balance vs difficulty;
- mechanics vs controls;
- progression vs content pacing;
- networking vs matchmaking;
- bugs vs stability;
- technical defect vs update quality;
- microtransactions vs monetization fairness vs monetization pressure;
- pricing vs value for money;
- narrative writing vs voice acting;
- UI structure vs readability vs onboarding;
- multilingual paraphrases and short/long multi-topic examples.

This suite is for deterministic regression and boundary discipline. It is not sufficient by itself for unbiased performance estimates.

### B. Evaluation Holdout

Maintain a separate labeled holdout, target 300–600 examples initially, sampled/stratified across realistic Steam review language/topic conditions. English, Chinese and Japanese should each have meaningful representation; aim for at least 50 examples per primary language when available.

Do not report per-topic F1 for topics with insufficient support. Use `N >= 10` as the default minimum for a per-topic metric; otherwise report family/aggregate metrics and sample count.

## 12.2 Required reports

Report at minimum:

- macro/micro precision/recall/F1 where support allows;
- confusion matrix/top confusions;
- decision-band coverage;
- HIGH-band precision/error rate;
- unresolved rate;
- semantic coverage;
- seeded novel-topic discovery recall;
- LLM escalation rate;
- multilingual slice results;
- processing cost/time per 1k/10k/50k reviews on declared hardware profiles.

## 12.3 Initial product-ready gates

Unless this Master Spec is explicitly revised, Semantic V2 is blocked from `PRODUCT_READY` if any release-blocking gate below fails on the holdout/reference corpus:

- HIGH decision-band precision < **0.93** overall;
- HIGH decision-band error rate > **0.07** overall;
- macro F1 across supported Core Topics (`N >= 10`) < **0.75**;
- any specifically designated high-risk boundary pair has precision < **0.80** on its supported slice;
- unresolved rate > **0.30** for semantic-eligible holdout reviews after permitted adjudication;
- seeded novel-topic discovery recall < **0.70**;
- representative 10k-review LLM escalation rate > **0.35** without documented evidence that the local path cannot meet quality otherwise;
- a primary language slice (EN/ZH/JA with `N >= 50`) has HIGH-band precision < **0.88**.

These are initial product gates, not claims of statistical optimality. Codex may tune models/prototypes/thresholds to meet them but must not silently lower them. If a release-blocking gate appears infeasible for a defensible methodological reason, M2 remains `BLOCKED`: Codex must surface the evidence and request an explicit product decision to revise this specification. A RELEASE_BLOCKER is not satisfied by a completion-time waiver.

## 12.4 Reproducibility

Benchmark artifacts must record:

- dataset version/hash;
- labeling schema/taxonomy version;
- semantic_config_hash;
- random seeds where applicable;
- hardware/runtime profile;
- evaluation code version/commit.

The objective is a high-precision local path with principled escalation, not maximum automatic coverage.

---

# 13. Snapshot / Trend Analysis contract

## 13.1 Purpose

Snapshot answers:

> What does this defined review population look like over the selected period?

It must not imply version impact unless a Version Review is explicitly performed.

## 13.2 Required sections

Snapshot should expose:

### Population

- requested Sampling Contract;
- observed reviews;
- completeness/truncation;
- language and playtime composition;
- provenance and limitations.

### Quantitative overview

- recommendation rate;
- interval/model note;
- review volume;
- trend;
- segment recommendation rates.

### Semantic overview

When Semantic Run exists:

- Core Topic prevalence;
- Game Topic prevalence;
- Top Issues;
- Top Requests;
- Top Praises;
- Emerging Topic candidates;
- topic-by-time trend;
- topic-by-language;
- topic-by-playtime;
- topic-by-recommendation.

### Evidence

Every topic/signal card must allow evidence drill-down.

## 13.3 No hidden version semantics

Snapshot must not display:

- causal version impact;
- pre/post claims;
- lifecycle matching claims;
- version robustness;

unless the displayed object is explicitly a Version Review result.

---

# 14. Version / Event Review contract

## 14.1 Purpose

Version Review answers:

> Under a defined event/version and comparable review populations, what changed after/between versions?

## 14.2 Research unit

Formal Version Review is:

`Version/Event + matched population windows`

not arbitrary free-form date comparison.

Arbitrary date comparison may exist as exploratory analysis but must not be labeled formal Version Review.

## 14.3 Required diagnostics

At minimum:

- pre/post or version window sizes;
- coverage;
- language composition drift;
- playtime composition drift;
- purchase/free/Early Access composition where supported;
- review-volume difference;
- missingness;
- acquisition provenance;
- window robustness;
- semantic comparability.

## 14.4 Semantic comparability rule

Formal Topic Delta requires exact semantic compatibility or explicit harmonization across compared populations.

Primary compatibility key:

`semantic_config_hash`

The backend must return one of:

- `COMPATIBLE` — configuration hashes and required metric semantics match;
- `HARMONIZABLE` — both source populations can be reprocessed under one shared semantic configuration without changing their ResearchRun populations;
- `INCOMPATIBLE` — a valid formal semantic delta cannot be produced.

The compatibility explanation must still identify material components, including taxonomy/catalog, embedding artifact, prototypes, segmentation/normalization, calibration/thresholds, assignment policy and LLM adjudication policy.

If harmonization is chosen, create new immutable SemanticRuns for the exact original populations and persist those exact source semantic IDs on VersionReviewRun. Do not rewrite old SemanticRuns.

Formal semantic delta additionally requires sufficient semantic coverage under §11.16 on both sides.

Do not compare topic percentages across incompatible semantic systems and present the delta as real user change.

Formal Version Review must not define its semantic population through a frontend-only constant such as `semantic_limit=1000`. Any cap/sampling used for a formal semantic comparison must be part of the persisted semantic configuration/population contract and must satisfy §11.16. A capped sample may be used for exploratory diagnostics but not silently labeled full-population Topic Delta.

## 14.5 Required output

- recommendation-rate delta;
- review-volume delta;
- population composition diagnostics;
- Core Topic deltas;
- compatible Game Topic deltas;
- newly emerging topic candidates;
- declining/resolved topic signals;
- affected segments;
- 3/7/14-day robustness where applicable;
- evidence before/after;
- limitations.

## 14.6 Causality language

Version Review may identify temporal association around an event. It must not automatically claim the event caused the change.

---

# 15. Cross-Game Compare contract

## 15.1 Purpose

Compare answers:

> How do two games differ under explicitly defined, comparable research populations?

## 15.2 Formal vs exploratory

The UI must visually and semantically distinguish:

### Formal Comparable Metrics

Computed from exact canonical run contracts and compatibility rules.

### Exploratory Filtered View

A user slice used for inspection. It may use backend-driven filters but must not overwrite formal metrics.

## 15.3 No StarredGame sample as analytical truth

Compare must not derive formal conclusions from `StarredGame.sample`.

## 15.4 Topic comparability

Core Topics may be compared only when the same canonical Core Topic ID and compatible Semantic configuration are used.

Game-scoped topics are **not** cross-game comparable by name similarity alone. A Game/Archetype Topic may appear in a formal cross-game metric only when one of these is true:

1. both sides reference the same accepted `scope=archetype` canonical topic ID; or
2. an explicit versioned TopicEquivalence mapping exists and is marked valid for formal comparison.

No LLM/text-similarity guess may create a formal cross-game equivalence on the fly.

Otherwise show those topics separately as game-specific evidence, not as a percentage delta.

Exploratory filters must be evaluated relative to the exact source populations and persisted/frozen filter anchors. They must not use display-time `now()` to change historical membership.

## 15.5 Required output

- exact source run IDs;
- population/comparability strip;
- recommendation rate comparison;
- review volume;
- stable segment comparisons;
- Core Topic comparison;
- compatible Game/Archetype topic comparison where meaningful;
- evidence links;
- limitations.

---

# 16. Evidence system and Evidence Explorer

## 16.1 Single evidence surface

Replace fragmented review/database/sample browsing with one canonical Evidence Explorer.

Target user concept:

**Evidence** = original review-level source material and semantic mentions used to support analysis.

## 16.2 Required filters

Backend-driven filters should support as applicable:

- Game;
- Research Run;
- Semantic Run;
- date/time;
- language;
- Recommended / Not Recommended;
- playtime cohort;
- purchase status;
- received for free;
- Core Topic;
- Game Topic;
- signal type;
- Emerging Candidate;
- keyword/full-text search;
- helpfulness;
- evidence status;
- version window/pre-post side when invoked from Version Review.

## 16.3 Pagination

All filters that affect result set membership must be applied server-side before pagination.

Do not derive available taxonomy options only from the currently loaded page.

## 16.4 Deep links

Dashboard/Workspace topic cards, Compare, Version Review, Ask STRA citations and Export references should deep-link into Evidence Explorer with context encoded in query params or route state.

## 16.5 Sample labeling

Any limited/sampled evidence view must explicitly display the sample mechanism/count.

---

# 17. Ask STRA contract

## 17.1 Product role

Ask STRA is the natural-language control and interpretation layer.

It is not a second analytical engine.

## 17.2 Supported roles

### Planner

Convert requests such as:

> Analyze CS2 Chinese and English reviews from June to August.

into a structured Analysis Setup draft.

### Navigator

Route users to:

- Snapshot Setup;
- Version Review;
- Compare;
- Evidence;
- Exports.

### Interpreter

Explain existing canonical results.

### Evidence Q&A

Retrieve supporting evidence under a known Research Context.

## 17.3 Context binding

Chat sessions should store/restore a context snapshot including as applicable:

```text
app_id
run_id
semantic_run_id
version_review_run_id
comparison_run_id
active topic
active filters
selected evidence ids
```

## 17.4 Cost rule

For this rebuild, Chat must not automatically execute expensive acquisition or semantic jobs solely from a conversational utterance.

It may prepare a valid configuration and provide an explicit “Open Analysis Setup / Run Analysis” action.

## 17.5 Aggregate metric rule

Chat must use canonical aggregate tools/results rather than calculating formal metrics from its top-N retrieved evidence reviews.

Evidence retrieval can remain limited, but the response must distinguish aggregate data from retrieved examples.

---

# 18. Reports → Exports contract

## 18.1 Rename concept

Product terminology should move from a generic `Reports` module to `Exports` or `Briefs`.

## 18.2 Export source types

At minimum:

- Snapshot Research Brief;
- Version Review Brief;
- Comparison Brief.

## 18.3 No independent analysis

Exports may:

- format;
- render charts;
- render canonical narrative summaries;
- include evidence appendix;
- generate PDF/HTML.

Exports must not:

- accept `app_id + arbitrary date range/month` as the analytical source for a new formal export;
- query arbitrary review populations and calculate new formal metrics;
- silently use latest app analysis instead of selected source run;
- rerun semantic classification;
- establish a parallel monthly analysis pipeline.

`POST /exports` must reference exact canonical source resources, for example:

```text
Snapshot Brief   -> research_run_id + optional exact semantic_run_id
Version Brief    -> version_review_run_id
Comparison Brief -> comparison_run_id
```

Legacy app/month report APIs may remain read-only compatibility paths for old artifacts during migration, but new UI and new exports must not call them to generate canonical output.

## 18.4 Exact consistency

If the workspace shows a formal recommendation rate of X for a source run, the export must show X, not a recalculated value.

## 18.5 Manifest

Every export must reference exact source IDs and persist:

```text
export_id
export_type
source resource IDs
source schema/version IDs
template_version
narrative_template_version
narrative_model/prompt policy version when LLM narrative is used
generated_at
language
format
artifact_hash/status
```

If narrative text is generated, it may interpret canonical metrics but must not invent/recalculate them. Re-generating narrative under a different template/model produces a distinct Export artifact/manifest rather than mutating a historical export.

---

# 19. Target frontend information architecture

## 19.1 Primary navigation

Target primary navigation:

1. **Home**
2. **Games**
3. **Compare**
4. **Version Review**
5. **Exports**
6. **Settings**

Ask STRA should be accessible globally/contextually but does not need to remain a disconnected primary destination.

Database should no longer be a primary product module. Data-management functions belong under Settings/Data Library or Run/Evidence management.

## 19.2 Home

Home is a work-entry surface, not a duplicate dashboard.

Recommended sections:

- recent games;
- recent Research Runs;
- recent Version Reviews;
- recent Exports;
- unfinished/failed jobs;
- shortcuts to Analyze Game / Compare / Version Review;
- optional data/runtime status.

Do not invent generic “alerts” without a persisted alert lifecycle.

## 19.3 Games

Games page provides:

- search Steam games;
- favorite/recent games;
- game status;
- latest valid run summary;
- direct Analyze action.

## 19.4 Game Workspace

Target route may follow a structure such as:

```text
/games/{app_id}/runs/{run_id}/overview
/games/{app_id}/runs/{run_id}/signals
/games/{app_id}/runs/{run_id}/segments
/games/{app_id}/runs/{run_id}/trends
/games/{app_id}/runs/{run_id}/evidence
/games/{app_id}/runs
```

Exact routing implementation may differ, but exact run context must be recoverable from URL/navigation.

Workspace tabs:

- Overview
- Signals
- Segments
- Trends
- Evidence
- Runs

## 19.5 Overview page

Primary user order:

1. Game header;
2. Research Context Strip;
3. primary quantitative metrics;
4. What Changed / Trend summary;
5. Who Is Affected;
6. Priority Signals;
7. evidence entry;
8. Research Details (collapsed by default).

Research Context Strip must show:

- run ID or short readable reference;
- date range;
- languages;
- observed reviews;
- collection completeness/truncation;
- Research readiness;
- Semantic status.

## 19.6 Signals page

When Semantic Run is available:

- Core Topics;
- Game Topics;
- Top Issues;
- Top Requests;
- Top Praises;
- Emerging Topic candidates;
- topic prevalence;
- topic trend;
- evidence count;
- semantic provenance/details.

When unavailable:

- Research Core remains usable;
- semantic section displays explicit unavailable/failed/not-run state;
- offer action to configure/run semantic analysis when supported.

## 19.7 Segments page

Expose cross-tabs such as:

- recommendation × language;
- recommendation × playtime;
- topic × language;
- topic × playtime;
- signal × segment;
- other Research Core-supported stable segments.

Do not imply unobserved demographics.

## 19.8 Trends page

Expose:

- daily/weekly volume;
- daily/weekly recommendation rate;
- topic prevalence over time;
- signal prevalence over time;
- selectable topics;
- exact coverage limitations.

Trend is descriptive time analysis, not Version Review.

## 19.9 Evidence page

This is Evidence Explorer scoped to the current run by default.

## 19.10 Runs page

Show:

- Research Run history;
- semantic run(s) associated with each research run;
- status;
- taxonomy/model versions;
- exact date/population summary;
- validity;
- re-run semantic action;
- open exact historical result.

Historical immutable outputs must remain inspectable.

## 19.11 Compare page

Rebuild around formal run selection, population compatibility and backend projections.

Avoid recomputing formal trend/recommendation metrics inside the page component.

## 19.12 Version Review page

Keep event-driven workflow but simplify around:

1. Game;
2. Event/version;
3. Window policy;
4. Comparability;
5. Quantitative Delta;
6. Semantic Delta;
7. Affected Segments;
8. Evidence;
9. Robustness;
10. Export.

Remove hard-coded invalid run IDs. Invalid/deprecated status belongs to persisted backend metadata.

## 19.13 Exports page

Select existing canonical object:

- Research Run;
- Version Review Run;
- Comparison Run.

Preview export metadata and generate/download without recomputation.

## 19.14 Settings

Settings may contain:

- runtime/provider configuration;
- LLM provider/API settings;
- local semantic model settings;
- semantic cost policy;
- default acquisition values;
- language/UI preferences;
- Data Library / storage management;
- taxonomy/catalog management for accepted Game Topics if appropriate;
- diagnostic/runtime information.

---

# 20. Analysis Setup frontend

Create a clear setup flow instead of hiding research configuration inside general dashboard logic.

Required inputs:

- Game;
- mode = Snapshot by default;
- date range;
- languages;
- review type;
- purchase type;
- collection order;
- include off-topic;
- max reviews;
- reuse existing reviews toggle where safe;
- semantic analysis mode/status;
- output language if narrative generation is enabled.

Display a plain-language population summary before execution.

Example:

```text
Counter-Strike 2
2026-06-01 → 2026-08-31
English + Simplified Chinese
All recommendation types
Steam purchase: all
Up to 20,000 observed reviews
Research Core: enabled
Semantic Engine: local-first + selective LLM adjudication
```

High-cost LLM work must not be silently triggered from Chat. From Analysis Setup the user may explicitly start the configured job.

---

# 21. Frontend visual hierarchy and design system

## 21.1 Problem to solve

Current UI has too many equal-weight cards, labels and badges. Research methodology often competes visually with decision-level information.

## 21.2 Hierarchy

Use four levels:

### Level 1 — Decision / primary answer

Examples:

- Recommendation Rate;
- major change;
- #1 issue;
- strongest affected segment.

### Level 2 — Signal

Examples:

- topic prevalence;
- trend;
- issue/request/praise cards;
- segment differences.

### Level 3 — Evidence

Examples:

- original reviews;
- evidence counts;
- matched examples;
- before/after quotes.

### Level 4 — Methodology / provenance

Examples:

- Sampling Contract;
- Wilson assumptions;
- taxonomy/model versions;
- validity diagnostics;
- limitations.

Methodology must remain accessible and trustworthy but should not dominate the first screen.

## 21.3 Card usage

Do not wrap every piece of text in a Card.

Use:

- page sections;
- metric strips;
- tables where comparison is the natural form;
- cards only for bounded objects/signals.

## 21.4 Consistency

Normalize:

- radius system;
- typography scale;
- spacing;
- labels;
- data-status colors;
- empty/loading/error states;
- chart tooltips;
- filter controls;
- provenance presentation.

Remove obsolete cyber/neon styling hooks that conflict with the final research-workbench visual language, unless retained intentionally as subtle brand accents.

## 21.5 Accessibility

Maintain keyboard navigation, focus states, semantic labels and reasonable contrast.

---

# 22. Frontend state architecture

## 22.1 Starred/Favorite Game

Refactor StarredGame/Favorite state so it stores identity/bookmark metadata only.

Do not persist canonical `insights` or review `sample` inside Favorite Game as the source of analytical truth.

## 22.2 Analysis task state

AnalysisContext or its replacement owns:

- queued/running/completed/failed state;
- progress;
- job/run identifiers;
- cancellation;
- queue management.

It should not become the permanent result store.

## 22.3 Canonical result fetching

Formal result surfaces fetch exact run resources by `run_id`.

App-level “latest valid run” endpoints may exist only for navigation convenience and must resolve to a concrete run ID before formal display.

## 22.4 URL state

Formal workspace URLs must preserve exact `run_id` and, when a semantic view is active, exact `semantic_run_id`. Routes must not resolve an historical semantic workspace by `app_id` alone.

Formal pages must be reloadable/bookmarkable without relying on hidden in-memory selected game state.

---

# 23. Frontend/backend service decomposition

The current giant `lib/api.ts` should be split by domain, for example:

```text
services/
  gamesApi.ts
  acquisitionApi.ts
  researchRunsApi.ts
  semanticApi.ts
  evidenceApi.ts
  comparisonApi.ts
  versionReviewApi.ts
  exportsApi.ts
  assistantApi.ts
  settingsApi.ts
```

Frontend feature boundaries may follow:

```text
features/
  analysis-setup/
  research-overview/
  signals/
  segments/
  trends/
  evidence/
  compare/
  version-review/
  exports/
  assistant/
  runs/
```

Domain-only utilities should not live in page components.

Examples to extract from current pages:

- review date parsing;
- recommendation normalization;
- playtime cohort logic;
- weekly bucketing;
- formal metric provenance display;
- taxonomy labels;
- URL/context builders.

Prefer backend canonical projections when a computation is part of formal research output.

---

# 24. Backend target architecture

Exact package names may differ, but responsibilities should become explicit.

Suggested conceptual boundaries:

```text
domain/
  acquisition/
  research/
  taxonomy/
  semantic/
  evidence/
  comparison/
  version_review/
  exports/

services/
  steam/
  embeddings/
  clustering/
  llm/
  persistence/

api/routes/
  games
  acquisition
  research_runs
  semantic_runs
  evidence
  comparisons
  version_reviews
  exports
  assistant
  settings
```

Do not retain an oversized miscellaneous route module as a permanent home for unrelated endpoints.

`chat_tools.py`, `llm.py`, `analysis.py` and other giant modules should be decomposed when responsibilities can be separated safely.

---

# 25. API contract direction

Exact URLs may be adapted for compatibility, but the API must expose resource-oriented contracts.

Representative target resources:

```text
POST /research-runs
GET  /research-runs/{run_id}
GET  /games/{app_id}/research-runs

POST /research-runs/{run_id}/semantic-runs
GET  /semantic-runs/{semantic_run_id}
GET  /research-runs/{run_id}/semantic-runs

GET  /research-runs/{run_id}/overview
GET  /research-runs/{run_id}/segments
GET  /research-runs/{run_id}/trends

GET  /evidence

POST /version-reviews
GET  /version-reviews/{run_id}

POST /comparisons
GET  /comparisons/{comparison_id}

POST /exports
GET  /exports/{export_id}

POST /assistant/plan
POST /assistant/query

GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel

POST /population-compatibility/check
POST /semantic-compatibility/check
```

Use typed response contracts and explicit schema versions where long-lived persistence is involved.

High-cost POST operations must accept/derive an `idempotency_key`. Repeated equivalent submissions within the active/retry window must resolve to the same active target resource/job or return an explicit duplicate/conflict response; they must not silently create duplicate formal runs.

---

# 26. Database migration requirements

## 26.1 Preserve user data

All migrations must be additive/non-destructive unless a backup and explicit irreversible migration is justified.

## 26.2 Legacy run preservation

Historical runs remain addressable.

## 26.3 Taxonomy coexistence

Legacy taxonomy and Core V2 coexist.

Never rewrite V1 label strings in historical records to “look like” V2.

## 26.4 Semantic V2 tables

Add normalized persistence for at least:

- semantic runs;
- semantic units;
- semantic mentions;
- topic definitions;
- topic catalog versions;
- topic prototype sets;
- emerging candidates;
- adjudication records;
- semantic configuration/version references.

## 26.5 Validity/status

Persist validity/deprecated/invalid status for runs instead of hard-coded UI exclusion.


## 26.6 Transactional migration and recovery

SQLite/desktop migrations must use explicit schema versions and be restart-safe.

Requirements:

- preflight database integrity check;
- automatic timestamped backup before any migration classified as material;
- transactional migration where SQLite permits;
- migration journal/version marker so interrupted upgrades are detected;
- idempotent retry or documented recovery path after process termination;
- representative legacy DB fixtures in CI/integration tests;
- post-migration integrity assertions for run counts, historical IDs and key foreign references.

The application must not partially open a newer binary against a half-migrated database and continue as if healthy.

## 26.7 Backfill policy

New provenance fields may be backfilled only when derivable from existing persisted evidence without guessing. Unknown historical values must remain explicit `UNKNOWN/LEGACY_UNAVAILABLE` rather than fabricated defaults that imply provenance the old run never recorded.

---

# 27. Legacy compatibility classification

Before deletion, classify relevant old paths as:

- `ACTIVE`
- `DEPRECATED`
- `LEGACY_COMPAT`
- `DEV_ONLY`
- `UNUSED`

Do not blindly delete code based only on static analysis.

Likely migration targets include:

- `/home` redirect route;
- `/reviews` and `/database` duplication;
- old Reports monthly independent analysis path;
- legacy PDF generator;
- old taxonomy prompt path;
- app-level latest-result compatibility reads;
- StarredGame analytical snapshots;
- hard-coded invalid version run IDs;
- old Chat endpoints superseded by contextual assistant APIs;
- duplicated frontend derived-metric utilities.

Every removed path must have a confirmed replacement or documented deprecation.

---

# 28. Runtime and dependency requirements

## 28.1 Local semantic runtime

Introduce local embedding/clustering dependencies only after:

- compatibility with the target Python/runtime environment is tested;
- desktop packaging impact is measured;
- memory/CPU/GPU behavior is measured on representative hardware;
- model download/storage strategy is explicit;
- offline behavior is understood.

## 28.2 Model management

The app must expose model state clearly:

- available;
- downloading/setup required;
- unavailable;
- incompatible;
- ready.

Do not silently fall back from local semantic processing to expensive full-review LLM processing.

## 28.3 Provider independence

Research Core remains valid without LLM provider configuration.


## 28.4 Reference hardware profiles

Performance reports must name hardware instead of presenting context-free timings.

Use at least:

- **Minimum Desktop Profile:** CPU-only or integrated/entry GPU path representative of a normal laptop, 16 GB RAM;
- **Reference Accelerated Profile:** the primary development/test machine when available, recording CPU, RAM, GPU/VRAM, OS, Python/runtime versions.

Exact brands are not product requirements, but the final execution report must record them.

A semantic feature is not considered desktop-ready if it works only on an undeclared high-end GPU environment.

## 28.5 Model artifact integrity and storage

Persist model identifier, source/license metadata where required, local artifact checksum and size. Detect missing/corrupt model files explicitly.

Embedding/model caches are evictable performance artifacts; ReviewSnapshots, PopulationSnapshots, ResearchRuns, SemanticMentions needed for historical evidence, and accepted taxonomy/catalog definitions are not disposable caches.

Provide a storage accounting/cleanup path that never deletes immutable analytical truth without explicit user action and dependency checks.

---

# 29. Performance and cost budget

Semantic Engine V2 must be measured at representative scales:

- 1,000 reviews;
- 10,000 reviews;
- 50,000 reviews.

Record:

- segmentation time;
- embedding time;
- peak memory;
- clustering time;
- number/percentage escalated to LLM;
- token usage;
- estimated cost;
- cache hit rate;
- total wall-clock processing time;
- disk growth for embeddings/cache and persisted semantic outputs.

The key product constraint is that LLM cost should scale primarily with ambiguous/discovery clusters, not linearly with every review.

No fixed numerical SLA is mandated until benchmarking, but the execution report must present results and practical limits.

---

# 30. Error, unavailable, partial and durable-job states

## 30.1 Layer state models

Each layer must have an explicit persisted state model.

Research Core:

- QUEUED
- RUNNING
- READY
- PARTIAL
- FAILED
- UNAVAILABLE
- CANCELLED

Semantic:

- NOT_RUN
- QUEUED
- RUNNING
- READY
- PARTIAL
- FAILED
- UNAVAILABLE
- CANCELLED

Exports:

- QUEUED
- GENERATING
- READY
- FAILED
- CANCELLED

The frontend must never render unavailable data as zero.

Partial semantic failure must not invalidate a successful Research Core result.

## 30.2 Durable execution and restart

Long-running jobs must persist stage/progress frequently enough to survive backend/Tauri restart without losing identity.

On restart the system must deterministically classify interrupted jobs as one of:

- resumable and resumed;
- retryable and re-queued;
- failed with explicit recovery action;
- cancelled.

It must not create a second formal result merely because the client retried after a timeout.

## 30.3 Idempotency and concurrency

At minimum protect:

- ResearchRun creation;
- SemanticRun creation for a `(research_run_id, semantic_config_hash)` request;
- harmonized Version semantic processing;
- ComparisonRun creation where the same source/config request is retried;
- Export creation/retry.

Define database uniqueness/locking semantics so two tabs/double-click/network retries cannot silently produce competing duplicate "same request" resources.

## 30.4 Cancellation

Cancellation stops future expensive work but does not delete already-valid immutable source resources. A cancelled Job must leave a coherent status and may leave a clearly labeled PARTIAL target only when that target's contract permits it.

## 30.5 Error codes

User-facing APIs should return stable machine-readable error codes for at least:

- incompatible population;
- incomplete acquisition;
- semantic configuration incompatibility;
- missing model/provider;
- migration required/failed;
- invalid historical run;
- job conflict/duplicate;
- cancelled job;
- unavailable formal metric due to partial coverage.

---

# 31. Testing strategy

## 31.1 Unit tests

Cover:

- deterministic metrics;
- taxonomy parsing/validation;
- semantic segmentation;
- prototype matching;
- decision-band logic;
- candidate lifecycle;
- run compatibility checks;
- evidence filters;
- export manifest rules;
- state transitions;
- PopulationCompatibilityResult logic;
- UTF-8 byte-offset evidence reconstruction;
- review-level topic prevalence de-duplication;
- semantic_config_hash determinism.

## 31.2 Contract tests

High priority contracts:

- exact run source-of-truth;
- Research Core immutability;
- old taxonomy preservation;
- Semantic Run immutability;
- TopicDefinition vs PrototypeSet separation;
- Version Review semantic compatibility;
- Report/Export no-recompute rule;
- formal vs exploratory Compare separation;
- Evidence server-side filter-before-pagination;
- raw similarity not exposed as probability;
- relative-time anchoring does not drift after reopening;
- exact ReviewSnapshot evidence survives upstream edit;
- PARTIAL semantic metrics obey availability rules;
- high-cost resource creation is idempotent.

## 31.3 Integration tests

Cover real database and API flows:

- create Snapshot run;
- persist result;
- create Semantic Run;
- retrieve topics/evidence;
- create Version Review;
- create Comparison;
- create Export;
- restore exact run after restart;
- resume/recover interrupted long-running Job;
- duplicate-submit/idempotency behavior;
- export exact source identity and narrative version.

## 31.4 Frontend tests

At minimum:

- exact-run restoration from URL;
- Analysis Setup validation;
- Research/Semantic readiness states;
- evidence filter deep-linking;
- formal/exploratory Compare labels;
- Version Review window switching;
- Export source display;
- Chat context restoration.

## 31.5 E2E tests

Use Playwright or equivalent existing framework where feasible.

Final E2E scenarios are mandatory and defined below.

## 31.6 Deterministic offline acceptance fixtures

CI/E2E must not depend on live Steam availability, paid LLM credentials or wall-clock time to prove core product correctness. Maintain deterministic fixtures that provide:

- frozen ReviewSnapshots/PopulationSnapshots;
- frozen clock/anchor time;
- deterministic acquisition/provider fixture;
- deterministic LLM adjudication fixture or fake provider with schema-valid outputs;
- representative legacy database fixture;
- seeded semantic benchmark subset.

Live Steam/provider smoke tests may run separately and must not be the only proof of acceptance.

## 31.7 Security/adversarial tests

Include review text containing prompt-injection instructions, HTML/Markdown/script-like payloads, Unicode edge cases and maliciously long content. Verify that these remain inert data and cannot mutate taxonomy, alter system instructions or execute UI markup.

---

# 32. Mandatory E2E acceptance scenarios

## Scenario A — Snapshot analysis from start to evidence

1. Search/select game.
2. Open Analysis Setup.
3. Choose time range and at least two languages.
4. Configure max reviews and purchase/review type.
5. Acquire/reuse reviews.
6. Produce Research Run.
7. Open exact Overview.
8. Confirm population strip and recommendation rate.
9. Run/attach Semantic Run.
10. Open Signals.
11. Open a Core Topic.
12. Drill into matching Evidence.
13. Apply language/playtime filter.
14. Return to Overview without losing run context.
15. Generate Snapshot Export.
16. Verify export source IDs match displayed run.

PASS requires no manual database repair and no hidden fallback to StarredGame sample.

## Scenario B — Large-review semantic workflow

Use a sufficiently large stored/fixture population to exercise batching.

1. Embed locally.
2. Match known topics.
3. Produce HIGH/MEDIUM/LOW statistics.
4. Build Discovery Pool.
5. Cluster candidates.
6. Produce representative samples.
7. Exercise LLM adjudication using test provider/fixture if external provider unavailable.
8. Persist candidate lifecycle.
9. Ensure per-review rollups exist.
10. Ensure cost ledger distinguishes local processing and LLM calls.

PASS requires that the system does not send all reviews to LLM.

## Scenario C — Version Review

1. Select a game with version events.
2. Choose event/version.
3. Create matched windows.
4. Inspect comparability.
5. Open 3/7/14-day views.
6. Confirm quantitative delta.
7. Confirm semantic configurations are compatible.
8. Inspect Topic delta.
9. Inspect affected segment.
10. Open before/after evidence.
11. Export Version Review.

PASS requires no hard-coded run hiding and exact source provenance.

## Scenario D — Cross-game Compare

1. Choose two games.
2. Choose exact source runs.
3. Inspect compatibility strip.
4. Compare formal recommendation metrics.
5. Compare Core Topics.
6. Apply exploratory filter.
7. Verify formal metrics remain clearly distinct from exploratory values.
8. Open evidence for each game.
9. Export comparison.

## Scenario E — Ask STRA planning

1. Ask: “Analyze this game’s English and Chinese reviews from the last three months.”
2. Verify correct game/date/language intent extraction.
3. Verify Chat prepares Analysis Setup rather than silently running expensive analysis.
4. Open prepared setup.
5. Ask a question about an existing topic increase.
6. Verify answer uses current exact run metrics plus cited evidence.

## Scenario F — Historical compatibility

1. Open a historical legacy run.
2. Verify historical result remains unchanged.
3. Verify legacy taxonomy displays as legacy.
4. Verify no silent Core V2 reinterpretation.
5. Optionally trigger explicit Semantic V2 re-analysis.
6. Verify it creates a new Semantic Run and preserves the old result.

## Scenario G — Restart/recovery

1. Complete a Research Run and Semantic Run.
2. Restart backend/desktop.
3. Reload exact URL.
4. Confirm exact result restoration from persistence.
5. Confirm no dependence on transient React context.
6. Interrupt a long-running semantic Job, restart, and verify documented resume/retry state without duplicate SemanticRun creation.
7. Submit the same semantic request twice and verify idempotent resolution.

## Scenario H — Historical review revision and time anchoring

1. Create a Research Run using a fixture review revision and a relative window resolved at anchor time T0.
2. Modify the upstream/current fixture review text and advance the system clock.
3. Reopen the exact historical run.
4. Verify population membership is unchanged.
5. Verify historical Evidence displays the original ReviewSnapshot revision/content hash.
6. Verify formal date/window metrics remain anchored to T0 and do not shift with current time.

---

# 33. Implementation milestones

The candidate 1.0 list of 27 backend/frontend-separated phases is replaced by six **vertical milestones**. Internal work packages and commits may still be small, but a milestone is not COMPLETE until its user-visible vertical slice and required tests pass.

Codex must continue automatically between normal work packages; milestones are execution/acceptance structure, not approval gates.

## Milestone M0 — Foundation Seal: identity, population, time, jobs and migration

Scope:

- reconcile actual repository against the sealed baseline;
- run existing CI/tests and record known failures;
- inventory DB/routes/UI/legacy paths;
- implement/lock canonical domain contracts for ReviewSnapshot, PopulationSnapshot, ResearchRun, ResearchContext, Job and MetricObservation;
- exact `run_id` formal identity;
- Sampling/Population compatibility service;
- UTC/half-open/anchor-time semantics;
- durable Job/idempotency/restart contract;
- migration versioning, backup and representative legacy fixture;
- decouple StarredGame/AnalysisContext from canonical analytical storage;
- frontend exact-run URL restoration.

M0 exit gate:

- a deterministic ResearchRun can be created, persisted, reopened after restart and traced to the same PopulationSnapshot;
- relative-time reopening does not drift;
- duplicate submit does not silently create duplicate formal resources;
- legacy DB migration fixture passes.

## Milestone M1 — Canonical Research Workbench

Scope:

- preserve/reconcile Stage 1–2P deterministic Research Core;
- backend canonical Overview/Segments/Trends projections and MetricObservation provenance;
- Analysis Setup and run-aware Game Workspace shell;
- Home/Games/Workspace IA foundation;
- unified Evidence backend/frontend for deterministic evidence fields;
- run history and validity status;
- remove formal page-local recomputation where canonical projections exist.

M1 exit gate:

- Scenario A works through deterministic Overview/Segments/Trends/Evidence without semantic dependency;
- formal metrics match backend canonical projections and exact source IDs;
- no StarredGame sample is needed to restore a formal result.

## Milestone M2 — Semantic Engine V2 vertical slice

Scope:

- Core Taxonomy V2 structured source and validation;
- Game/Archetype Topic catalog persistence/governance;
- SemanticUnit/SemanticMention/rollup schema;
- local multilingual embedding/prototypes/decision bands;
- semantic_config_hash and immutable SemanticRun;
- Discovery Pool, clustering and representative sampling;
- selective LLM adjudication with prompt-injection defenses;
- EmergingTopicCandidate lifecycle;
- semantic coverage/PARTIAL rules;
- Signals semantic projections and Evidence links;
- semantic status/progress UI and exact semantic_run restoration;
- benchmark assets and §12 release gates.

M2 exit gate:

- a user can attach/run Semantic V2 on an exact ResearchRun, observe durable progress, reopen it after restart, inspect topics/signals/evidence and distinguish failure/partial states;
- Scenario B passes;
- §12 product-ready gates PASS. If they cannot pass after defensible tuning, M2 remains BLOCKED pending an explicit product/specification decision.

## Milestone M3 — Comparative Research

Scope:

- preserve Version Review's accepted research design while replacing ad-hoc semantic coupling;
- semantic compatibility service using semantic_config_hash;
- harmonized reprocessing under exact original populations;
- remove hard-coded invalid run IDs;
- exact VersionReviewRun sources and Topic deltas;
- formal Cross-Game ComparisonRun;
- Core/Game/Archetype topic comparability/equivalence rules;
- strict formal vs exploratory UI distinction;
- backend-driven exploratory filters with frozen anchors;
- evidence linking for both Version Review and Compare.

M3 exit gate:

- Scenarios C and D pass;
- no Version/Compare formal result is computed from StarredGame sample or page-local current-time logic;
- incompatible semantic configurations cannot produce a formal Topic delta.

## Milestone M4 — Presentation and Interaction Layer

Scope:

- Reports → Exports migration with exact source-resource APIs;
- Snapshot/Version/Comparison Briefs;
- Export narrative/template/model version provenance;
- Ask STRA planner/navigator/interpreter/evidence Q&A bound to exact context;
- no hidden expensive execution from chat;
- finish primary IA Home/Games/Compare/Version Review/Exports/Settings;
- design hierarchy, responsive/accessibility cleanup;
- decompose giant pages/modules and split API client/domain utilities where safe.

M4 exit gate:

- Scenario E passes;
- exports reproduce workspace canonical values and exact IDs;
- Ask STRA uses canonical aggregate tools and cited evidence instead of top-N evidence recomputation.

## Milestone M5 — Legacy, packaging and final release seal

Scope:

- legacy path classification/deprecation cleanup;
- explicit readers for historical artifacts where needed;
- model setup/storage/cleanup UX;
- repository-wide unit/contract/integration/frontend/build tests;
- desktop packaging smoke test and runtime profile checks;
- performance/cost/storage benchmarks on declared hardware;
- Scenarios A–H;
- documentation reconciliation/archive;
- final migration and architecture report.

M5 exit gate:

- all RELEASE_BLOCKER gates in §35 PASS;
- all REQUIRED gates PASS or have explicit user/product-owner WAIVER with rationale;
- final completion report is generated in Appendix C format.

---

# 34. Milestone Definition of Done rule

A backend implementation or commit may be complete as a work package, but a **milestone** is COMPLETE only when the vertical user capability exists across required layers.

Every milestone must evaluate, where applicable:

1. **Domain/Persistence** — data semantics are correct, versioned and durable.
2. **API** — typed resource can be created/read/queried with explicit availability/errors.
3. **Frontend** — user can access, understand and operate the capability.
4. **Integration** — exact canonical context flows end-to-end.
5. **Recovery** — restart/retry/duplicate submission preserves identity and truth.
6. **Tests** — unit/contract/integration/frontend/E2E gates relevant to the milestone pass.
7. **Migration/Compatibility** — existing user data/historical runs remain coherent.
8. **Documentation** — execution ledger and changed contracts are current.

A backend-only Semantic API may be marked as a completed **work package**, not as completed Milestone M2.

---

# 35. Final product acceptance and release gates

Use three statuses:

- `RELEASE_BLOCKER` — every item must PASS. It cannot be waived inside the completion report; changing one requires an explicit revision of this specification/product decision before completion.
- `REQUIRED` — must PASS unless the user/product owner explicitly records `WAIVED` with rationale.
- `POST_RELEASE` — useful follow-up, not required for rebuild completion.

This classification supersedes the ambiguous candidate-1.0 P0/P1 completion wording.

## RELEASE_BLOCKER — Research identity and correctness

- [ ] Formal deterministic metrics trace to exact immutable ResearchRun IDs and PopulationSnapshots.
- [ ] Exact historical run reopening never silently switches to latest app result.
- [ ] ReviewSnapshot revisions/content hashes preserve historical evidence after upstream edit.
- [ ] Canonical time windows use persisted anchor time and do not drift with current time.
- [ ] Research Core accepted metric semantics remain intact or receive an explicit version bump/migration contract.
- [ ] Formal metrics expose correct eligible denominator/provenance and are not recreated in React pages.
- [ ] Historical runs are not silently mutated.
- [ ] V1 taxonomy is preserved as legacy.
- [ ] Core Taxonomy V2 is versioned/structured and passes completeness validation.
- [ ] SemanticRun is immutable and pins exact semantic_config_hash/population hash.
- [ ] SemanticMention cardinality obeys §5.8; no overloaded topic/signal arrays as canonical truth.
- [ ] Formal Topic prevalence is review-level de-duplicated and exposes denominator/unresolved counts.
- [ ] Raw similarity is not presented as probability/confidence without calibration.
- [ ] Game Topic promotion is explicit, not automatic.
- [ ] Version/Compare semantic delta requires compatible or harmonized semantic configuration and sufficient coverage.
- [ ] Cross-game Game Topic formal comparison requires same canonical archetype ID or explicit TopicEquivalence mapping.
- [ ] Export never establishes an independent analytical truth and accepts exact source resources.
- [ ] Compare clearly separates formal and exploratory results.
- [ ] PARTIAL/UNAVAILABLE data is never displayed as a complete zero/full-population metric.

## RELEASE_BLOCKER — Durability, migration and security

- [ ] High-cost operations have persisted Job state and idempotency behavior.
- [ ] Restart/recovery does not silently duplicate ResearchRun/SemanticRun/Export resources.
- [ ] Migration is versioned, backup-aware and passes representative legacy DB fixture tests.
- [ ] Unknown legacy provenance remains explicit rather than guessed.
- [ ] Review/LLM prompt-injection fixtures remain inert data and structured adjudication rejects malformed output.
- [ ] No hard-coded invalid run IDs remain in product code.

## RELEASE_BLOCKER — Product usability

- [ ] A user can complete Snapshot workflow without database/manual code intervention.
- [ ] A user can run/attach Semantic V2, see progress/status, inspect signals/evidence and reopen exact semantic result after restart.
- [ ] A user can complete Version Review workflow.
- [ ] A user can complete two-game Compare workflow.
- [ ] A user can drill every major semantic signal into exact evidence.
- [ ] Semantic failure does not destroy a valid Research Core result.
- [ ] Mandatory E2E Scenarios A–H pass with deterministic offline fixtures.

## RELEASE_BLOCKER — Semantic product readiness

- [ ] Boundary Regression Suite and Evaluation Holdout are versioned and reproducible.
- [ ] All §12.3 measured product-ready gates pass under the declared benchmark/hardware configuration.
- [ ] Large populations use local embedding/batching rather than full-review LLM calls.
- [ ] LLM escalation remains selective and measured.

## REQUIRED — Frontend architecture and engineering

- [ ] Primary navigation matches target IA.
- [ ] Game Workspace exists with exact-run URL restoration.
- [ ] `/reviews` + Database review browsing are unified into Evidence or explicitly redirected/deprecated.
- [ ] StarredGame no longer stores canonical analytical snapshots.
- [ ] Giant page-local formal research computations are extracted/replaced.
- [ ] methodology/provenance remains accessible but visually secondary.
- [ ] frontend lint/type/tests pass.
- [ ] backend unit/contract/integration suite passes.
- [ ] production frontend build passes.
- [ ] desktop packaging/runtime smoke test passes where the declared build environment supports it.
- [ ] legacy compatibility paths are explicitly documented.
- [ ] model artifacts expose integrity/state/storage behavior.
- [ ] performance/cost/storage measurements exist for representative 1k/10k/50k scales where fixtures/resources permit.

## POST_RELEASE — Optional follow-up

Examples:

- broader taxonomy benchmark labeling beyond initial holdout;
- additional archetype topic packs;
- richer export themes/templates;
- multi-platform ingestion;
- real-time monitoring/alerts;
- advanced topic equivalence governance UI;
- background scheduling beyond this rebuild.

---

# 36. Final expected user experience

A new user should understand STRA in this order:

1. **Choose a game.**
2. **Define which Steam reviews you want to study.**
3. **Run a reproducible analysis over an immutable PopulationSnapshot.**
4. **See what is happening quantitatively.**
5. **Optionally run a versioned SemanticRun and see what players are talking about semantically.**
6. **See which player segments are most affected.**
7. **Open the original reviews behind every important signal.**
8. **When a release/patch matters, run a formal Version Review instead of pretending a trend is causal.**
9. **Compare another game only under an explicit comparison contract.**
10. **Export the existing canonical result.**
11. **Use Ask STRA to plan, navigate and interpret—not to create a hidden second analysis engine.**

The final product should feel like one coherent research workbench, not a collection of independent demo pages.

---

# Appendix A — Core Taxonomy V2 concise boundary reference

This appendix is a compact implementation reference. The structured taxonomy source created in Milestone M2 at `docs/taxonomy/core_taxonomy_v2.yaml` must contain Definition / Include / Exclude / Boundary / Typical Examples / Counterexamples for every topic and must preserve the normative IDs/meanings/boundaries in §8 and this appendix.

| Topic | Core meaning | Key exclusion/boundary |
|---|---|---|
| overall_experience/general | Overall game evaluation without specific product aspect | use specific topic whenever identifiable |
| gameplay/mechanics | Core interaction rules/systems | not input feel, balance or difficulty |
| gameplay/controls | Input/camera/control feel | not device support |
| gameplay/balance | Relative strength/fairness of legitimate options | not absolute difficulty or paid advantage |
| gameplay/difficulty | Absolute challenge level | not option balance or progression speed |
| gameplay/progression | Advancement/unlocks/XP/gear/grind | not narrative pacing |
| gameplay/ai_behavior | NPC/enemy/ally decision behavior | not character writing |
| technical/performance | FPS/stutter/loading/resource performance | not crash/network |
| technical/bugs | General functional defects | use more specific technical topic when available |
| technical/stability_crashes | crash/freeze/hang/fatal stability | not ordinary FPS degradation |
| technical/compatibility | OS/hardware/platform environment compatibility | not supported-but-slow performance |
| technical/networking | latency/disconnect/desync/netcode | not matchmaking |
| technical/installation_launch | install/update/launcher/startup pipeline | not in-session crash |
| technical/save_data | save/load/cloud/progress persistence | not progression design |
| content/scope_variety | amount/variety/repetition of content | not replayability after completion |
| content/world_level_design | spatial/map/level structure | not visual art |
| content/activities_modes | quests/missions/modes/activities | not mechanics inside them |
| content/narrative_characters | story/writing/dialogue/characters/lore | not pacing/voice performance |
| content/replayability | reason/value to replay/continue | not first-play content amount |
| content/content_pacing | pacing of story/levels/activities | not progression speed/update cadence |
| content/customization | appearance/personal-expression customization | not skill progression |
| ux_accessibility/interface_hud | UI/HUD/navigation organization | not readability |
| ux_accessibility/readability_clarity | visibility/understandability of presented information | not teaching/onboarding |
| ux_accessibility/quality_of_life | friction-reduction conveniences | not core-rule changes |
| ux_accessibility/input_device_support | controller/KBM/wheel/rebinding/device support | not control feel |
| ux_accessibility/accessibility | dedicated ability/disability support | not generic QOL |
| ux_accessibility/onboarding_learnability | tutorial/tooltips/learning support | not difficulty itself |
| presentation/visuals_art | art/graphics/lighting/visual quality | not performance or spatial design |
| presentation/animation | movement/facial/combat animation quality | not input latency |
| presentation/audio_music | music/SFX/ambient audio | not voice acting |
| presentation/voice_acting | spoken performance/delivery | not writing/localization text |
| presentation/localization | translation/localization quality | not subtitle readability/regional price |
| online_community/multiplayer_experience | experience of playing with/against humans | not network or matchmaking |
| online_community/matchmaking | pairing/queue/skill matching | not network connection quality |
| online_community/social_features | party/guild/friends/chat/social tools | not moderation behavior |
| online_community/competitive_integrity | cheating/smurfing/botting/manipulation | not legal game balance |
| online_community/moderation_safety | toxicity/harassment/reporting/moderation | not cheating |
| online_community/mods_ugc_ecosystem | mods/workshop/custom content ecosystem | not official DLC |
| service_operations/update_quality | quality/effect/regressions of patches | may co-occur with technical defect |
| service_operations/update_cadence | real-world update/fix frequency | not in-game content pacing |
| service_operations/roadmap_delivery | promised plan/milestone delivery | not communication quality |
| service_operations/developer_communication | public one-to-many dev communication | not individual support ticket |
| service_operations/customer_support | one-to-one support handling | not public dev communication |
| commercial_model/pricing | base/edition/general price | not regional difference/value judgment |
| commercial_model/regional_pricing | country/currency/purchasing-power pricing | not ordinary price complaint |
| commercial_model/paid_content | DLC/expansion/paid content packs | not small recurring purchases |
| commercial_model/microtransactions | in-game store/currency/loot-box purchase mechanism | not fairness/pressure by itself |
| commercial_model/monetization_fairness | paid advantage/unfair restriction | not pure FOMO pressure |
| commercial_model/monetization_pressure | FOMO/time pressure/aggressive prompts/friction-to-sell | not mere existence of MTX |
| commercial_model/value_for_money | experience/content relative to price | not price number alone |

---

# Appendix B — Required documentation after rebuild

Codex must leave the repository with current, non-conflicting documentation for:

1. product architecture;
2. Research Run contract;
3. Core Taxonomy V2;
4. Game/Archetype Topic governance;
5. Semantic Engine V2;
6. Version Review methodology;
7. Evidence contract;
8. API routes/resources;
9. data migration;
10. local semantic model setup;
11. testing/E2E instructions;
12. desktop build/run instructions;
13. final known limitations;
14. Population/Time compatibility contract;
15. durable Job/recovery/idempotency contract;
16. semantic benchmark datasets and release-gate results;
17. model artifact/storage/cleanup behavior.

Historical documents may be moved under an archive/history location or clearly marked historical when they would otherwise mislead future agents.

---

# Appendix C — Final Codex completion report format

At the end of the rebuild, produce a final report containing:

```text
1. Baseline commit
2. Final commit
3. Milestone completion table
4. Major architecture changes
5. Database migrations
6. Research contracts preserved/changed
7. Semantic benchmark results
8. Performance/cost results
9. Frontend IA summary
10. E2E Scenario A–H results
11. CI/build results
12. Legacy compatibility retained
13. Known limitations
14. Remaining optional future work
15. Acceptance table: RELEASE_BLOCKER=PASS/FAIL/N/A; REQUIRED=PASS/FAIL/WAIVED/N/A; POST_RELEASE=OPEN/DONE/N/A
```

A rebuild with any unresolved RELEASE_BLOCKER failure is not complete. REQUIRED failures also block completion unless the user/product owner explicitly records a WAIVER with rationale. Codex may not self-waive these gates.



---

# Appendix D — Canonical implementation invariants and formulas

This appendix is intentionally compact and test-oriented. When prose is ambiguous, tests should encode these invariants.

## D.1 Identity graph

```text
Game
 └─ ResearchRun (exact run_id)
     ├─ PopulationSnapshot (immutable membership)
     │   └─ ReviewSnapshot[] (immutable revision/content identity)
     └─ SemanticRun[] (exact semantic_run_id + semantic_config_hash)

VersionReviewRun
 └─ exact ResearchRun/PopulationSnapshot/SemanticRun source references

ComparisonRun
 └─ exact source ResearchRun/SemanticRun references

Export
 └─ exact source ResearchRun | VersionReviewRun | ComparisonRun references

Job
 └─ execution state that materializes the immutable resources above
```

## D.2 Time formula

```text
formal_window = [start_at_utc, end_at_utc)
relative_request -> resolve once using anchor_time -> persist absolute window
```

Display-time clock changes must not alter formal membership.

## D.3 Topic prevalence formula

```text
topic_prevalence(topic) =
  count(unique review_snapshot_id with ReviewTopicRollup(topic))
  / semantic_prevalence_denominator
```

Never:

```text
SemanticMention count / all mentions
```

unless the metric is explicitly named `mention_share` or equivalent and is not shown as Topic prevalence.

## D.4 Semantic comparison gate

```text
if semantic_config_hash_A == semantic_config_hash_B
   and coverage_A satisfies metric
   and coverage_B satisfies metric:
       COMPATIBLE
elif both exact populations can be reprocessed under one shared config:
       HARMONIZABLE
else:
       INCOMPATIBLE
```

## D.5 Export gate

```text
Export(source IDs) -> render canonical observations/evidence
Export(app_id + arbitrary date/month) -> NOT a valid new canonical export contract
```

## D.6 Frontend gate

A React component may:

- format;
- sort/display;
- request backend exploratory slices;
- derive purely visual state.

It may not silently recreate a formal research denominator/population/statistical result from the currently loaded page/sample and label it canonical.

## D.7 Historical evidence gate

```text
Historical Run -> historical PopulationSnapshot -> historical ReviewSnapshot revision
```

not:

```text
Historical Run -> current mutable review row
```

## D.8 No forced semantic certainty

If configured local + adjudication paths cannot defensibly resolve a Core Topic, preserve `unresolved` and count it. Do not use `overall_experience/general` as a catch-all for uncertainty.
