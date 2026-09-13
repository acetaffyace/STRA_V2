# Stage 1–2P Final Seal — Deterministic Research Core

## 1. Accepted baseline

The accepted deterministic baseline is:

`ca66e70a3a808a3cf4d136ddea2cff5380651cc0`

It represents the accepted Stage 1–2P snapshot path: Sampling Contract, Steam
acquisition, provenance, Research Core, persistence, immutable runs, API, and
Dashboard integration. The Final Seal commit adds documentation and browser
acceptance evidence only; it does not reopen the accepted methods.

Important accepted checkpoints are:

| Checkpoint | Commit |
|---|---|
| Stage 1 Sampling Contract | `26eb963` |
| Stage 2P.2 Research Core orchestrator | `cf84e83` |
| Stage 2P.3 `/analyze` integration | `ef04207` |
| Stage 2P.4 persistence/API | `fa13c47` |
| Stage 2P.5 Research Dashboard | `4a29282` |
| Stage 2P.6 product acceptance | `ca66e70` |

## 2. Product architecture

STRA is an Evidence-Driven Player Insights & Version Research Workbench. The
authoritative snapshot path is:

```text
Sampling Contract
  → Steam Acquisition
  → Raw Review Population + provenance
  → Deterministic Research Core
  → immutable Research Report
  → Analysis API
  → Dashboard Research Overview
```

The Semantic Layer is an optional parallel extension. It may classify text and
produce topics, issues, requests, labels, evidence, and summaries after Research
Core succeeds. Research Core does not depend on an LLM provider.

Production `/analyze` currently emits `research-report-v1` with `mode=snapshot`.
Snapshot Research Core includes population/Sampling Contract, Recommendation Rate,
model-based Wilson uncertainty, acquisition validity, activity and expression
diagnostics, limitations, and provenance. Comparability, standardization,
lifecycle-window robustness, and version-impact claims require two explicit
populations and are not fabricated by snapshot analysis.

## 3. Authoritative metric ownership

Research Core owns the research population and denominator, Sampling Contract,
acquisition provenance, Recommendation Rate and uncertainty, and activity /
expression diagnostics. When an explicit comparison workflow is used, it also
owns comparison validity, standardization, and matched-window robustness.

The Semantic Layer owns topics, issues, requests, semantic labels, semantic
evidence, and semantic summaries. Legacy fields remain compatibility output, not
an alternate source for canonical Research Core metrics.

Steam `voted_up` means Recommended / Not Recommended. It is not general sentiment,
player satisfaction, or a claim about all players.

## 4. Accepted product invariants

- Valid Steam acquisition plus successful Research Core is a valid quantitative
  product, independent of provider, API-key, request, or classifier availability.
- The persisted Research Report equals a direct Research Core call on the exact raw
  run population and metadata; no client/server statistical recalculation is added.
- The Research population denominator is not changed by duplicate-text diagnostics,
  near-copy detection, coordinated-expression signals, or local Dashboard filters.
- Research READY + Semantic READY shows both layers.
- Research READY + Semantic UNAVAILABLE shows a valid quantitative product and a
  non-blocking notice.
- Research READY + Semantic FAILED preserves the quantitative product and shows a
  semantic failure notice.
- A run with no Research Report is not Research-ready; historical semantic-only
  results remain readable without a fabricated report.

## 5. Research limitations

Steam reviewers are self-selected and are not all players. Recommendation Rate is
not general satisfaction. A Wilson interval describes a binomial/Bernoulli model
for observed recommendations and does not solve reviewer self-selection. Duplicate
text is not automatically spam; coordinated expression is not proof of manipulation;
activity spikes are not automatically review bombing. Snapshot analysis is
observational and does not establish version effect or causality.

## 6. Deferred scope

The following are intentionally not accepted by this seal:

- Stage 2F external event timeline;
- Stage 3A semantic sampling and its sampling provenance;
- classifier validation and classifier-error uncertainty;
- multiple-testing correction for semantic topic discovery;
- full comparison/version Research Core frontend migration where not yet available;
- causal identification and all-player representativeness correction.

## 7. Verification evidence

The sealing change is documentation/browser acceptance only; production analytical
modules are unchanged. Evidence recorded with the sealing delivery includes:

- full backend pytest with an isolated temporary directory;
- targeted Stage 2P.6 acceptance pytest (12 scenarios at the accepted baseline);
- dashboard typecheck, lint, and production build;
- a rendered-browser Research Core smoke using a deterministic local quantitative-only
  fixture (`research_ready=true`, `semantic_ready=false`, `insights=null`, reason
  `no_provider`), with no Steam network or paid LLM call; the visible Dashboard
  showed Research Core READY, 定量研究概览, Steam 推荐率, 观测评论数, model-based
  interval, 采集状态, duplicate diagnostics, and 语义分析 · 不可用;
- GitHub Actions backend and frontend checks for the Final Seal commit.

The exact Final Seal commit SHA and GitHub Actions run ID are recorded in the final
delivery report for the commit containing this document. No credentials, raw Steam
downloads, local databases, or generated build artifacts are part of the seal.

## 8. Browser smoke evidence

The required rendered-browser scenario opens a completed quantitative-only Dashboard
from the local fixture and verifies visible Research Core READY, Quantitative Research
Overview, Recommendation Rate, model-based interval, Observed Reviews, Collection
Status, activity/duplicate diagnostics, and Semantic Analysis UNAVAILABLE. It also
verifies that the page does not show an “analysis not ready” blocker or fabricated
semantic zero widgets. This manual rendered-browser smoke passed on the local
Next.js + FastAPI stack; the repeatable Playwright scenario is
`tooling/stage2p_research_browser.spec.ts`. The historical Web MVP smoke remains
separate.

## 9. Release Candidate status

After the documentation and browser smoke commit receives green backend and frontend
CI, the deterministic foundation is:

**STRA V2 Deterministic Core — RC1**

This is an internal Release Candidate checkpoint, not a GitHub Release. A recommended
future tag is `v2-research-core-rc1`; no tag is created by this task.

## 10. Stage 3 entry conditions

Stage 3 must consume the frozen raw Research population and immutable Research Report.
Population `N` is not semantic sample `N`. A future semantic sampler may deduplicate,
downsample, stratify, or balance for thematic breadth, but it must preserve separate,
reproducible sampling provenance and must never silently redefine the Research
population. The denominator, Recommendation Rate source, Sampling Contract semantics,
acquisition provenance, Research Report v1 snapshot meaning, and Stage 2E denominator
behavior are frozen during Stage 3 unless a new explicit stage accepts a change.

No merge to `main` or tag creation is performed by this checkpoint.
