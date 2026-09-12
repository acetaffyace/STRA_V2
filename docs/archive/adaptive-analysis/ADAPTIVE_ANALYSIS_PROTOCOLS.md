# Adaptive Analysis Protocols

## Profile

使用 genres/categories、是否多人/免费/抢先体验、评论速度和可用元数据进行确定性 first-pass。缺少元数据时输出 `hybrid_unknown` 与 `insufficient_profile_metadata`，不伪造游戏画像。

## Anchor 与窗口

事件必须记录 published/effective/range/precision/source quality/status。单日锚点才可做 event-centered；range、unresolved、confounded 只做 descriptive-only。默认候选窗口为 ±1/3/7/14/28 日，先按 archetype/event type 选择，再按每侧最小支持数扩窗，并保留 sensitivity windows。

## Executors

- `event_impact`：pre、post、pp delta、Wilson 95% CI、support。
- `lifecycle_compare`：按 Day 1–7、8–14 对齐，不把 A 版本末期和 B 版本初期混比。
- `longitudinal_series`：日序列；支持不足时标记 descriptive-only。
- `current_snapshot`：无有效 baseline 时 `What changed = unavailable`。

## 比较、稳健性与机制

比较显示原始 n、推荐率、语言分布和 drift，不静默 reweight。稳健性至少保留窗口方向；方向冲突为 `unstable`。每个 aggregate change 输出 direct version effect、composition shift、concurrent event、operational incident、controversy/review bombing、seasonality、platform/collection change，并列出 support、falsification 和 data still needed。任何观察都不自动升级为因果结论。

## Evidence Grade

A/B/C/D 由 sample adequacy、temporal robustness、cohort robustness、evidence verification、label reliability、confounder risk 组成。当前历史细粒度 taxonomy precision 约 0.24，因此没有人工/验证证据时不得给 A；Grade 不是概率 confidence。

## 舆情异常

只有至少两个独立信号（volume burst、negative-rate shift、topic burst 等）才生成 candidate event；没有官方解释时 `cause=unknown`，并保留 onset/peak/recovery 的已知程度。

