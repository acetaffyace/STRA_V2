# Player Voice Review Runs

This is the first vertical slice for the Game Player Voice & Community Growth
Intelligence workflow. It adds a reproducible version-event analysis contract
without changing SentiNext's existing app-level analysis endpoints.

## Workflow

1. Register a human-verified version/update event.
2. Create an analysis run with an immutable configuration snapshot.
3. Run the normal SentiNext ingestion/classification flow for the target game.
4. Request deterministic pre/event/post metrics for the run.

## API example

```bash
# Register the event anchor
curl -X POST http://localhost:8000/version-events \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": 123456,
    "event_name": "Version 1.1 Patch",
    "event_date": "2026-08-01",
    "event_type": "patch",
    "manual_verified": true
  }'

# Create a run using the returned event_id
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "target_app_id": 123456,
    "event_id": "<event_id>",
    "pre_window_days": 28,
    "post_window_days": 28,
    "languages": ["english", "schinese"],
    "competitor_app_ids": [],
    "taxonomy_version": "sentinext-taxonomy-v1"
  }'

# Compute metrics from reviews and cached labels already in SentiNext
curl -X POST http://localhost:8000/runs/<run_id>/metrics

# Read ranked issue cards and selected verbatim evidence
curl http://localhost:8000/runs/<run_id>/issues
curl "http://localhost:8000/runs/<run_id>/evidence?subcategory=technical/performance&limit=10"
curl http://localhost:8000/runs/<run_id>/recommendations
curl http://localhost:8000/runs/<run_id>/comparison
curl http://localhost:8000/runs/<run_id>/emerging-topics
```

## Current metric contract

The first implementation reports:

- pre, event-day, and post review counts;
- recommendation rate for each period;
- subcategory mention rate before and after the event;
- issue rate and request count by subcategory;
- aspect negative/positive rate, negative burden, and pre/post deltas when
  aspect labels are available;
- observable proxy segments for playtime, reviewer experience, purchase type,
  Steam Deck usage, and language;
- daily review volume and a post-vs-pre volume index;
- percentage-point changes;
- low-sample warnings;
- a deterministic issue-priority score with reach, severity, deterioration,
  actionability, and confidence components;
- ranked issue cards linked to up to five evidence cards per subcategory;
- deterministic recommendation drafts classified as product, community, or
  content actions, each with validation metrics and limitations;
- emerging-topic candidates from negative `other/*` reviews, explicitly marked
  `pending_review` and never silently added to the fixed taxonomy;
- explicit warnings about observational data and proxy metrics.

The label schema now accepts aspect entries with `sentiment` in `-2..+2`, a
verbatim `evidence_span`, and model `confidence`. Older cached labels remain
valid: when aspect entries are absent, `issue_rate` is intentionally used as a
proxy and is not named `negative_rate`. The priority score is versioned as
`ips-v1-proxy`; it is a triage aid, not a causal score. Evidence cards retain
the source review ID and period so a reviewer can inspect the original text.

## Persistence

The new tables are:

- `version_events`: manually verified event anchors;
- `analysis_runs`: immutable run configuration plus derived metrics.

The existing `analysis_results` table remains app-level and backward compatible.
`app_id` identifies a game; `run_id` identifies one reproducible event review.

Run creation is gated on a manually verified event and supported Steam language
codes. The persisted config contains a manifest with taxonomy, prompt, model,
and pipeline version fields so later results can be reproduced and audited.
