# V1 Real-Use Pilot / Dogfooding

## 状态

- 产品状态：**V1 Agent — usable**
- P0：**CLOSED**
- 当前阶段：真实使用试点 / 产品验证
- 本阶段：只记录真实使用，不实现 P1 功能

## 目标

使用当前版本完整分析 3–5 款真实游戏，记录：

1. 它是否真的帮助用户回答业务问题；
2. 哪些结论足够可信、哪些仍需人工核验；
3. 哪些工作流摩擦最影响真实决策；
4. P1 应由实际摩擦排序，而不是由旧路线图预设。

建议覆盖：Live-service/competitive、single-player/narrative、systems-heavy/roguelike/strategy；可选增加近期大版本更新游戏和多语言评论游戏。

## 每款游戏的基本记录

- app_id：
- 游戏名称：
- 游戏类型：
- 选择原因：
- 分析日期：
- review window：
- review count：
- languages：
- run_id：
- 是否使用已有本地数据：
- 是否产生真实 provider 调用：
- 成本查询结果：

## 五个真实业务问题

每款游戏都必须回答：

### A. 最近发生了什么变化？

记录时间窗口、Run 对比、版本/事件上下文，以及哪些变化只是观察关联。

### B. 玩家为什么满意或不满意？

记录推荐率、正式 issue/request/topic 指标、denominator、coverage 和证据。

### C. 谁受到的影响更大？

记录语言、时间段、评论群体或其他可观察 cohort；没有后端 formal observation 时，不得把样本差异写成总体结论。

### D. 什么重要到值得行动？

记录信号强度、覆盖范围、重复出现程度、证据质量与不确定性。

### E. 后续应采取什么行动？

把观察到的信号映射到产品、社区或营销动作，并明确哪些仍只是 hypothesis。

## 证据纪律

每个主要发现使用以下结构：

```text
observed signal
  -> inferred mechanism
  -> evidence still needed
```

必须记录：

- observed signal；
- metric；
- denominator / coverage；
- taxonomy/topic；
- verified player evidence；
- inference/mechanism hypothesis；
- alternative explanation；
- additional evidence needed。

Steam 评论是观察性资料。不得把评论模式写成因果结论，也不得把 LLM confidence 当作事实准确率。

## 工作流摩擦记录

将分析质量问题与使用摩擦分开记录。可记录：

- navigation 不清晰；
- repetitive clicks；
- waiting/latency；
- repeated classification；
- run comparison 困难；
- issue prioritization 困难；
- evidence discoverability 差；
- task restart pain；
- cost visibility；
- Version Review confusion；
- Chat usefulness/failure；
- 决策所需上下文缺失。

每条摩擦填写：

- severity：blocking / high / medium / low；
- frequency：every run / frequent / occasional / one-off；
- workaround：none / easy / annoying；
- 具体场景和影响；
- 是否影响最终决策。

不要把每条摩擦直接变成 feature request。完成至少 3 款游戏后，再归并为 decision prioritization、information architecture、incremental processing、task durability、version interpretation、cost visibility、taxonomy precision、evidence workflow 等主题。

## 分析质量问题

不改模型、不改 taxonomy，单独记录：

- obvious taxonomy false positives；
- missing important labels；
- issue/topic confusion；
- request detection errors；
- multilingual failures；
- long-review failures；
- weak Challenge-like cases。

## 固定基线

试点不能替代 Golden Set 基线。始终保留：

- Gold：`p0.5c-gold-verified-v2`；
- Provider/model：`deepseek / deepseek-v4-flash`；
- subcategory precision approximately 0.24；
- taxonomy overprediction unresolved；
- first-pass sentiment unavailable；
- Challenge small-N limitation。

## 执行顺序

1. 选择并记录游戏，不先改代码；
2. 用当前 V1 完整走完 ingest → analysis → evidence → result → cost → Chat/Version Review（适用时）；
3. 填写一份 `V1_PILOT_GAME_TEMPLATE.md`；
4. 至少完成 3 款后，再填写 `V1_PILOT_SYNTHESIS.md`；
5. 只根据真实摩擦排序 P1；
6. 试点完成前不开始 P1 实现。

## 成功标准

试点不是“所有指标都好”，而是能够明确回答：

- 我是否愿意用这份分析做一次真实决策；
- 哪些地方仍需手工补充；
- 最常见、最严重、最难绕过的摩擦是什么；
- 哪个 P1 候选最值得先做，以及证据是什么。
