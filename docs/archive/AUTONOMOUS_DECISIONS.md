# Autonomous Decisions

## Use an explicit offline fixture source

**Decision**: add `apps/api/senti_next/offline.py` and `tooling/offline_pilot/` rather than bypassing the production normalization and insight builders.

**Evidence**: the real pilot was blocked by provider behavior; the plan freezes paid APIs. Existing review and taxonomy pipelines were reusable.

**Alternatives considered**: skip analysis; create a fake production provider; alter Gold data.

**Smallest correct choice**: a development-only source with explicit provenance, isolated databases, and zero `llm_calls` rows.

**Reversibility**: delete/disable the offline runner without changing production provider selection.

## Treat unsupported live model IDs as configuration errors

**Decision**: new DeepSeek calls accept the pinned V1 identities only; historical IDs remain readable in cached provenance.

**Evidence**: the pilot used `deepseek-chat` while the accepted V1 baseline is `deepseek-v4-flash`; the cost registry did not price the former.

**Reversibility**: provider configuration validation is isolated in `providers/config.py`.

## Open a local provider operation circuit after systemic failure

**Decision**: repeated/empty systemic failures must not fan one batch into per-review provider calls.

**Evidence**: the previous run converted one empty batch into hundreds of individual requests.

**Smallest correct choice**: in-process cooldown circuit; no Redis/Celery/queue infrastructure.

**Reversibility**: remove the circuit wrapper without changing label schemas.

## Use heuristic priority transparently

**Decision**: expose prevalence, negative concentration, issue/request support and a heuristic marker.

**Evidence**: P1 requires explainable prioritization and prohibits an opaque magic score or causal claim.

**Reversibility**: the contract version and score components are explicit.

