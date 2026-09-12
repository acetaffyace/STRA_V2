# Adaptive Analysis V1 Release Report

## 实现内容

本版本新增确定性 Adaptive Analysis Design Engine：Profile、Event Anchor、Adaptive Window、Event Impact、Lifecycle Compare、Longitudinal、Public Opinion Candidate、Population Comparability、Robustness Matrix、Competing Mechanisms、Evidence Grade，并将 immutable `AnalysisDesign` 与 Run 关联；Version Review 增加 Analysis Design Card。

## 迁移

迁移版本：`10`。在现有 backup/restore framework 上新增 `analysis_designs`，并为 `version_events` 增加 provenance 字段。旧 `event_date` 保留；迁移重复执行安全。失败路径恢复备份，未改变 review_id 或 Gold v2。

## 验证状态

- Adaptive unit tests：5 passed（另有 lifecycle/longitudinal 场景覆盖）。
- 既有 SQLite/version-run targeted tests：30 passed。
- Apex corpus：12,435 条窗口评论，0 Provider calls。
- Apex：通过 adaptive pipeline；官方来源已记录 published/effective range，正式结果为 descriptive-only、Evidence Grade C（范围锚点仍不允许因果表述）。
- 前端：已接入 Analysis Design Card；最终 full typecheck/lint/build 结果以本次 release gate 命令输出为准。

## 兼容性与风险

新增字段均为 additive；既有事件创建和版本分析继续使用 `event_date`。没有为旧数据静默补写真实生效日。缺乏 event provenance 时系统宁可降级为 descriptive-only。

## 最终 Gate

`ADAPTIVE_ANALYSIS_V1_READY`

READY 的含义是引擎、迁移、UI、回归和 Apex provenance guard 已闭环，不是宣称 Apex 存在因果识别。Apex 仍明确显示 range/confounded、descriptive-only 和 Evidence Grade C。停止，不启动无关 P2/P3 工作。
