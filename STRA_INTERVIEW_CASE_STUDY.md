# STRA Interview Case Study

## Problem

游戏团队有大量 Steam 评论，却很难快速回答“最近发生了什么、为什么发生、谁受影响、先做什么”。简单 sentiment 分析缺少话题、证据、优先级和版本上下文。

## Data

STRA 本地保存 20,806 条历史评论、4,325 条 labels、13 次 analysis runs、2 次完成的 Version Review 和 1,142 条 LLM calls ledger。每次分析保留 run、population、模型、prompt、taxonomy 和 evidence provenance。

## Method

LLM 做受约束的多标签语义分类；确定性代码计算推荐率、评论量、趋势、覆盖和版本 delta；Evidence 将结论连接回评论；Version Review 使用生命周期匹配窗口与 3/7/14 天稳健性检查。

## Finding 1：常规分析

在精确 100 条评论的 provenance acceptance 中，3 个 UTC 日 bucket 的每日评论量 reconciled 到 100，推荐 numerator reconciled 到 91。该运行使用 127,047 tokens，记录成本约 $0.0217，retry 和失败 provider call 均为 0。这个案例证明的是 population / projection provenance 与运行链路，不是模型准确率。

## Finding 2：版本变化

HELLDIVERS 2 Version Review V2 中，生命周期匹配的上一窗口为 831 条、推荐率 55%，当前窗口为 1,573 条、推荐率 75%，变化 +19.2 个百分点；语义比较样本 831 / 1,000，成功分类 831 / 768。系统进一步给出 topic delta、paired evidence 和窗口稳健性。

## Decision → Validation → Limitation

团队可以把变化拆成可复核的问题、需求或正向信号，先按证据强度和影响范围形成候选行动，再回到新的评论窗口、重复提及率、support/bug-ticket volume 或 telemetry 验证。Steam 评论是自选择观察性数据；推荐率不是 sentiment；LLM confidence 不是 accuracy；缺少精确 population provenance 时不生成 daily projection。
