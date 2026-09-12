# STRA Portfolio Case Study

## 一句话

STRA 把 Steam 玩家反馈从“很多评论”转成可追溯的产品判断：变化、原因、影响群体、优先级、行动和验证方式。

## 问题与方法

单独的正负面比例无法回答产品团队真正关心的问题。STRA 将语义分类与确定性指标分开，把重要结论连接回原始评论，并为版本变化提供生命周期匹配的比较窗口。

```text
Steam reviews → local SQLite/FTS5 → bounded LLM labels
→ deterministic metrics → evidence / actions / Version Review
→ Next.js dashboard → STRA desktop
```

## 真实规模与 provenance

- 20,806 条历史 Steam 评论
- 4,325 条 review labels
- 13 次分析运行；其中 6 次完成的 general analysis
- 2 次完成的 Version Review
- 1,142 条记录在 cost ledger 中的 LLM calls
- provenance acceptance：100 条精确 population、3 个 UTC 日 bucket、评论量 reconciled 到 100、推荐 numerator 为 91、127,047 tokens、约 $0.0217、0 retry / 0 failed provider calls

## Version Review V2 案例

HELLDIVERS 2 的生命周期匹配比较显示：上一窗口 831 条、推荐率 55%；当前窗口 1,573 条、推荐率 75%，变化为 +19.2 个百分点。语义比较样本为 831 / 1,000，成功分类为 831 / 768。

这不是因果结论。STRA 同时展示 coverage gate、topic delta、paired evidence 和 3/7/14 日稳健性窗口，用于区分“可观察变化”和“需要进一步验证的可能机制”。

## 方法边界

评论是观察性、自选择数据；推荐率不是 sentiment。LLM confidence 不等于模型准确率，Evidence Grade 只描述观察性证据质量。没有精确 population provenance 时，STRA 不伪造 daily projection；外部数据能力不可用时显示 unavailable。

## 作品集价值

这个项目展示的是一个完整 data product：本地数据生命周期、受约束的 AI 语义层、确定性分析、证据链、版本研究工作流、成本 ledger、运行故障处理和可安装桌面交付。
