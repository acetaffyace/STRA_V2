# Unified Analysis Storage Architecture

## Canonical model

```text
Game
├── reviews
├── version_events
└── analysis_runs
    ├── analysis_designs
    ├── review_labels
    ├── llm_calls
    ├── evidence
    └── analysis_run_results
```

`analysis_runs.run_type` distinguishes `general_analysis` from `version_review`; `analysis_mode` describes the selected workflow (`current_snapshot`, `event_impact`, `version_comparison`, `version_longitudinal`, or `public_opinion`).

## Run identity

Every history and queue item carries `app_id`, `run_id`, `run_type`, status, phase, timestamps, counts, and result availability. Dashboard and Version Review links pass the exact `run_id` and never silently select another run.

## Review reuse

Version windows read and extend the canonical `reviews` archive. Missing historical ranges are fetched into the same table; semantic analysis uses the run population/design and does not copy reviews into a version-specific database.

## Lifecycle

The persisted run is the source of truth for queue state. Version phases include historical acquisition, window construction, A/B classification, comparison, and finalization. The active registry is a projection of durable rows and survives page reload/navigation.
