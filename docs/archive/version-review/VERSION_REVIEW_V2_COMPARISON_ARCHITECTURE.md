# Version Review V2 Comparison Architecture

`resolve events → lifecycle windows → WindowCoverageGate → deterministic matched sample → cached labels → raw/topic deltas → paired evidence → window sensitivity → residual candidates`。

结果使用 `version-review-v2` immutable shape：A/B coverage、raw metrics、reviews/day、recommendation delta、semantic/classified counts、topic/request/positive comparisons、paired evidence、window sensitivity、emerging candidates。A 永远是较旧事件，B 是较新事件。

覆盖状态：`COMPLETE`、`PARTIAL`、`UNKNOWN`、`INSUFFICIENT_REAL_VOLUME`。最低语义支持为每侧 50 条；raw metrics 可在弱样本状态下展示，但不生成版本级语义结论。
