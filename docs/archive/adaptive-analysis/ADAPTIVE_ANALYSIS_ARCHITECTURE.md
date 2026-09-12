# Adaptive Analysis Engine 架构

## 目标与边界

本层在现有 Run、Version Event、Five Questions、Evidence 和离线执行链之上增加“先设计、后分析”的方法论快照。它不调用 LLM，不修改 Gold v2，不改变 `review_id`、Dashboard/API 既有语义，也不创建第二套事件真相源。

## 单一真相源

- 事件：`version_events`；新增发布日期、生效日/范围、锚点精度、来源质量、状态和并发组字段。
- Run：`analysis_runs`；配置和执行状态仍由现有 Run schema 管理。
- 方法：`analysis_designs`；每个 Run 一条 immutable JSON snapshot。
- 证据：现有 Evidence scope/verification；不能验证的原话不提升 Evidence Grade。

## 组件

`GameAnalysisProfile → GameEvent/Anchor → WindowSpec → Executor → PopulationComparability → Robustness → CompetingMechanisms → EvidenceGrade → Five Questions/UI`

所有输出带 `adaptive-analysis-v1` 与 `adaptive-analysis-engine-v1` identity。单日锚点、日期范围、未解析锚点分别进入不同执行分支；范围或未解析事件只允许 descriptive-only。

## 迁移与失败语义

使用既有 migration/backup/restore 框架，版本为 10。迁移失败恢复数据库；普通启动不自动重建分析结果。方法快照写入失败不会被当作成功的完整 Adaptive Run。

