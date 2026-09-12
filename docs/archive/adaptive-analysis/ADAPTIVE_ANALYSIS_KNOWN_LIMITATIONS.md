# Adaptive Analysis 已知限制

1. Steam Review API 的分页、排序和自选择样本不能证明历史评论全集覆盖；Apex crawl metadata 已明确记录这一点。
2. 目前若没有结构化 Steam App metadata，Profile 会保守返回 `hybrid_unknown`，不会猜测游戏类型。
3. 事件日期范围或来源冲突时，系统不会选 8 月 3 日或 8 月 5 日中的一个；因此没有合法单日 event impact。
4. 评论聚合只能显示观察性变化，不能证明版本导致变化，也不能识别真实机制。
5. 语言 drift、playtime 缺失、分类缺失会降低可比性；系统不做静默重加权。
6. topic/label 质量受既有 taxonomy 限制，历史精细 taxonomy precision 约 0.24，必须结合 Evidence verification。
7. 当前 Longitudinal 提供日序列，尚未将趋势模型作为决策结论；支持不足时只显示 descriptive-only。
8. Public Opinion detector 输出 candidate，不是已确认舆情事件；恢复与原因需要更多时间序列和官方来源。

