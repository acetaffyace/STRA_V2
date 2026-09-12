# Version Review V2 Data Audit

结论：旧实现把“本地已有评论数”当成窗口完整性，无法证明 A/B 人口可比。V2 增加 `event_effective_at`、半开生命周期窗口 `[effective_at, effective_at + N)`、抓取来源、缓存边界、抓取完成标记和 coverage status。

审计发现：旧执行器在语义分析前直接从 SQLite 取窗口；没有覆盖门，也没有对 `published_at`、`event_date`、`effective_at` 做明确优先级。V2 统一使用 `effective_at`，无有效锚点则 `UNKNOWN`。

实现位置：`apps/api/senti_next/comparative_intelligence.py`、`routes/runs.py`。不新增数据库，不改 canonical review storage。
