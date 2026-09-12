# SentiNext：把 Steam 评论压缩成可追溯的决策信号

## 01 Problem

Steam 评论很多，但团队真正需要的不是摘要，而是：发生了什么、为什么、谁在表达、什么值得行动，以及每个判断能否回到真实评论。普通情感分析只能告诉团队“正面或负面”，不能直接回答产品决策问题。

## 02 Product / Five-question workflow

SentiNext 把评论组织成五个问题：

`What changed? → Why? → Who? → What matters? → What should we do?`

用户从 Dashboard 进入五问摘要，再从 signal 进入 Evidence，最后进入行动卡。系统明确区分当前单窗口观察和窗口间变化：没有可比较基线时，显示 unavailable，不把单窗口结果写成“最近变化”。

## 03 FIX / IMPROVE / BUILD / AMPLIFY

What Matters 不是标签墙，而是可解释的行动框架：

- **FIX**：已有问题，需要修复或复现。
- **IMPROVE**：功能存在，但体验需要优化。
- **BUILD**：存在明确需求，值得做需求验证。
- **AMPLIFY**：稳定的正向信号，可用于传播或社区内容。

每张卡同时显示观察信号、证据、排序理由、不确定性和下一步验证计划。启发式 priority 是辅助排序，不是因果结论或自动产品优先级。

## 04 Trust architecture

核心链路是：

`Run → Provenance → Immutable Result → Evidence Verification → Decision`

每次分析保留 Run、来源、样本、窗口、分类/证据人口和结果快照。引用必须能在对应 canonical review 中找到 source slice；无法核验时显示 unavailable，而不是让模型补写“看起来合理”的原话。Offline Chat 只做 deterministic evidence-first lookup。

## 05 Model evaluation / what can be trusted

项目建立了 **150 条人工核验 Golden Set**，冻结 Dev/Holdout，并在历史阶段执行过真实 DeepSeek baseline。结果显示：粗粒度 issue detection 相对可用，但细粒度 taxonomy 仍存在明显 overprediction，precision 约 **0.24**，recall 约 **0.67–0.70**。这不是一个可以被隐藏的缺点，而是产品设计输入：

> taxonomy 用于 candidate discovery；真正的决策必须回到 Evidence 和人工解释。

因此，离线 Fixture 不被当作模型质量提升证据；Gold 与 baseline 也不被包装成“模型已经准确理解玩家”。系统选择把 taxonomy、coverage、verification status 和 uncertainty 一起展示。

## 06 Real pilot failure → operational hardening

第一次真实运行暴露出一条完整的可靠性故事：Windows runtime 与 SOCKS 依赖、旧 DeepSeek model 配置、HTTP 200 但 empty content、batch retry fan-out、cost ledger secondary exception，以及进程中断后的恢复问题。

结果不是继续堆 prompt，而是把 AI demo 改成可诊断的分析系统：runtime diagnostics、typed provider failures、bounded retry、operation circuit breaker、unknown-cost semantics、startup recovery 和 explicit offline execution mode。

离线测试可以验证合同和恢复逻辑，但不能替代真实 Provider 的重新运行验证。

## 07 Final V1/P1 product

NINJA GAIDEN 4 的 **1000-review offline end-to-end product/system validation** 验证了完整产品链路：原始评论、Run、Five Questions、Evidence、Dashboard、Chat、Reports 和决策框架能够连通。当前离线 Fixture 结果明确是：

`codex_offline_fixture != human Gold != provider output != model-quality benchmark`

可直接观察的工程/产品成果是：1000 条 E2E 样本、Evidence 查询、已验证 source quotes、0 provider calls in offline mode，以及当前全量后端 **111 个自动化测试用例**。

## 08 Honest limitations

- Steam 评论是自选择样本，不能代表全部玩家。
- 1000 条离线 Fixture 验证产品系统链路，不验证模型准确率，也不构成真实玩家结论。
- taxonomy overprediction 尚未解决，precision 约 0.24 仍需校准。
- 当前没有重新完成 external provider 的生产级复验。
- 单窗口观察不能证明趋势，更不能证明因果。

## 09 Next validation steps

1. External provider staged revalidation。
2. Taxonomy precision calibration。
3. Across multiple games 的真实用户 dogfooding。

这些是下一步验证，不属于本轮已完成成果；本轮停止在 V1/P1。
