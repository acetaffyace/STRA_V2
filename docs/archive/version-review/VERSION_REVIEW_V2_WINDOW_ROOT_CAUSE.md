# Version Review V2 Window Root Cause

HELLDIVERS 2 的 3113-vs-17 回归根因在旧历史采集路径：`_execute_version_run` 使用 Steam `filter=all`，该查询按 helpfulness 排序而非按创建时间排序，却配合 `stop_before_timestamp` 提前停止。因此“页面已达到历史边界”并不成立，17 条只能代表当前返回/缓存子集，不能代表 B 生命周期真实体量。

修复：历史 backfill 改用 chronological `filter=recent`，在进入 sampling/classifying 前持久化 A/B coverage contract；`PARTIAL`、`UNKNOWN`、`INSUFFICIENT_REAL_VOLUME` 均阻断正式比较。若实际完整后仍为 17 条，结果会诚实显示样本不足，不扩容伪造 parity。

注意：本地运行环境未提供可重复的线上 HELLDIVERS Steam crawl fixture，故没有把外部网络结果冒充为已复现数字；根因由实际执行代码路径和专门 regression contract 锁定。
