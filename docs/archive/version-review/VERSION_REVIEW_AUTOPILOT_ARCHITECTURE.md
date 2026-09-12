# Version Review Autopilot Architecture

```text
Version Review page
  -> event catalog refresh/list
  -> deterministic /version-review/plan
       -> resolve event provenance
       -> choose previous comparable event
       -> lifecycle intervals
       -> cache coverage and missing intervals
       -> bounded semantic sample plan
  -> /version-review/start
       -> immutable existing analysis run
       -> cache-first Steam acquisition
       -> raw metrics from full target window
       -> deterministic semantic sample
       -> existing label cache / provider path
       -> existing Version Review + Adaptive Analysis output
```

The planner is provider-free and can be inspected before execution. Existing labels remain eligible for reuse through the existing cache contract. The semantic layer never receives the entire raw historical archive by default.

Event resolution is informational: ambiguous or conflicted anchors remain startable and are marked descriptive-only. The existing event catalog is preserved; no second review archive is introduced.
