# Apex Legends Adaptive Analysis 报告

## 结论先行

本次使用 Apex Legends（App ID `1172470`）2026-07-01—2026-08-31 的离线 corpus：原始抓取 12,600 条，窗口内 12,435 条；7 月 1 日—8 月 2 日 6,473 条，8 月 3 日—8 月 31 日 5,962 条。Provider 调用为 0。

公开来源已核验到：EA 官方 Patch Notes 页面发布日期为 8 月 3 日，但正文写明上线为 8 月 4 日；Steam 官方公告也记录 8/4 patch。因此 canonical anchor 保存为 published=8/3、effective range=8/3—8/4，而不是静默择一。正式 Adaptive 结论仍是 `descriptive_only`，不是“版本导致了变化”。

## Anchor 处理

| 项目 | 结果 |
|---|---|
| published/effective provenance | EA Patch Notes：published 8/3；正文上线 8/4；Steam 公告：8/4 |
| 候选冲突 | 8/3 是公告/页面日期，8/4 是上线/Steam patch 日期；8/5 未被接受 |
| anchor precision | `range` |
| event status | `confounded`（时区/发布与生效语义仍需人工确认） |
| event impact | 不输出合法因果/单日事件效应 |
| 可运行内容 | 日序列、候选窗口描述、语言分布、稳健性/待补证据 |

## Observed（观察到）

- 窗口内推荐 8,395 条、不推荐 4,040 条；前段推荐率约 67.1%，后段约 67.9%。
- 语言分布主要为英语 5,083、简体中文 3,824、俄语 987、繁体中文 433；这些是 Steam 评论样本的语言分布，不是玩家总体画像。
- 评论中可见的候选主题包括匹配/平衡、反作弊/性能、资源与武器、社区行为以及角色/皮肤审美。它们是待复核信号，不是已验证驱动。
- 7/1—8/31 日序列和 ±3/±7/±14 的探索窗口可以生成，但因 anchor 未解析，窗口结果只用于描述和后续核验。

## Inferred（只能谨慎推断）

- 前后窗口的推荐率差异很小，不能据此判断版本没有影响。
- 语言组成和评论选择机制可能造成变化；这属于 composition shift 的替代机制，不是版本效应。
- 资源/落地装备/武器相关表达值得优先核验，因为它们比泛化的“游戏不好玩”更接近具体改动假设。
- 当前证据等级应为 `C`（探索性），而不是 A/B：anchor、官方解释和已验证 evidence 不足，且细粒度标签质量受历史 taxonomy 限制。

## Evidence still needed（仍需证据）

1. 人工确认 EA 的 8/3 页面日期与 8/4 上线日期在 Steam 评论 UTC 时间轴上的映射。
2. 解释 8/3 与 8/5 候选冲突，确认 8/5 是否只是评论/地区延迟，而非独立事件。
3. 对匹配、反作弊、性能、资源/武器主题做跨语言人工 evidence verification。
4. 检查并发事件、Review Bombing、Steam 收集/排序变化和季节性。
5. 在 anchor 清晰后重跑 event impact、窗口敏感性、语言/游玩时长分层和机制反证。

## 运行记录

- 数据：[reviews.jsonl](D:\reviews\SentiNext\SentiNext-refactor\data\v1_pilot\apex_legends_1172470_2026-07-01_2026-08-31\reviews.jsonl)
- 元数据：[crawl_metadata.json](D:\reviews\SentiNext\SentiNext-refactor\data\v1_pilot\apex_legends_1172470_2026-07-01_2026-08-31\crawl_metadata.json)
- 旧版离线 Run：`offline-b8c68caf457149f28f3aa6d291c8c48d`
- 本报告不把旧版固定日期切分升级为 canonical event。

官方来源：
- https://www.ea.com/games/apex-legends/apex-legends/news/marked-patch-notes
- https://steamcommunity.com/app/1172470/announcements/
