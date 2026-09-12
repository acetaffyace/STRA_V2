# SentiNext 一页介绍

**一句话**：SentiNext 将分散的玩家声音压缩成可追溯的决策信号，并让每个结论都能回到原始证据。

## 产品成果

- **1000-review offline end-to-end product/system validation**：使用 NINJA GAIDEN 4 本地评论验证完整产品链路。
- **Five Questions**：What changed? Why? Who? What matters? What should we do?
- **FIX / IMPROVE / BUILD / AMPLIFY**：把信号连接到可解释的产品动作。
- **Verified evidence path**：候选结论回到 canonical review，原话经过 source-slice verification。
- **Trust architecture**：Run、provenance、immutable result、evidence verification、cost ledger。
- **111 个自动化后端测试用例**：当前仓库 `pytest --collect-only` 的已核对数量。

## Model evaluation

150 条人工核验 Golden Set → 冻结 Dev/Holdout → 历史真实 DeepSeek baseline → 发现粗粒度 issue detection 相对可用，但细粒度 taxonomy precision 约 0.24、recall 约 0.67–0.70，overprediction 尚未解决。

因此：**labels 用于发现候选，decisions 必须回到 evidence 和人工解释。**

## NINJA GAIDEN 4 的边界

本案例是 `codex_offline_fixture` 下的系统链路验证，不是“模型已经验证了 1000 条评论”。

`codex_offline_fixture != human Gold != provider output != model-quality benchmark`

Fixture 派生的推荐率、问题率、需求率只可作为 Demo 页面中的明确标注数据，不作为作品集正文的模型质量或真实玩家结论。

## 可靠性故事

真实 Pilot 暴露 Windows/SOCKS 依赖、旧 model 配置、HTTP 200 empty content、retry fan-out、cost ledger secondary exception 和中断恢复问题；随后形成 runtime diagnostics、typed provider failures、bounded retry、circuit breaker、unknown-cost semantics、startup recovery 和 offline mode。

## 已知限制与下一步

评论是自选择样本；离线 Fixture 不验证模型准确率；taxonomy precision 仍需校准；external provider 尚未重新完成生产级复验。下一步只写三项：external provider staged revalidation、taxonomy precision calibration、multiple-game real-user dogfooding。
