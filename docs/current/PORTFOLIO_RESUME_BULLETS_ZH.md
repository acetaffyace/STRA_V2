# SentiNext 简历素材

## 一行项目描述

构建面向游戏团队的玩家声音决策工具，将 Steam 评论转化为可追溯的五问分析、证据引用与 FIX/IMPROVE/BUILD/AMPLIFY 行动。

## 三条简历 bullet

- 设计 Run / provenance / immutable result / evidence verification 链路，让产品结论可回到 canonical player review，并支持无基线时的明确 unavailable 语义。
- 建立 150 条人工核验 Golden Set 与冻结 Dev/Holdout，历史 DeepSeek baseline 显示细粒度 taxonomy precision 约 0.24；据此将 taxonomy 限定为候选发现，并为决策增加证据门禁。
- 将首次真实 Pilot 的 Provider、重试、成本记录和中断恢复失败转化为 runtime diagnostics、typed failures、bounded retry、circuit breaker、unknown-cost semantics 和 offline mode；当前后端收集到 111 个自动化测试用例。

## 较长作品集描述

SentiNext 不是单纯的情感分析 Dashboard，而是一个把玩家声音连接到产品动作的分析系统。它用五问框架回答 What changed、Why、Who、What matters 和 What should we do，再通过 Evidence verification 将结论连接到真实评论。评测显示粗粒度 issue detection 相对可用，但细粒度 taxonomy precision 约 0.24，因此系统明确把标签定位为 candidate discovery，而不是自动事实。NINJA GAIDEN 4 的 1000 条离线样本用于端到端产品链路验证，不作为模型质量或真实玩家结论。项目同时处理了真实 Provider 失败、成本语义和恢复路径。
