# Adaptive Analysis V1 验收矩阵

| 能力 | 验收标准 | 状态 |
|---|---|---|
| Profile | 确定性 archetype、reason、ambiguity、protocol | PASS |
| Anchor | 单日/范围/未解析不混淆，保存 provenance | PASS |
| Window | 3/7/14/28 自适应、支持不足扩窗、敏感性窗口 | PASS |
| Event impact | rate、CI、pp delta、support | PASS |
| Version vs Version | lifecycle matched 且低支持标记 invalid | PASS |
| Longitudinal | daily series 与 descriptive-only guard | PASS |
| Public opinion | 至少双信号、未知原因 | PASS |
| Population | n、语言、推荐率、drift、pass/warn/fail | PASS |
| Robustness | 窗口矩阵与 unstable | PASS |
| Mechanisms | 7 个替代机制、反证和待补数据 | PASS |
| Evidence Grade | 六个组件、A/B/C/D、无伪 confidence | PASS |
| Five Questions/UI | 仅消费有效比较，显示设计/证据/边界 | PASS |
| Apex regression | 完整 corpus；冲突 anchor 不静默选日 | PASS（descriptive-only） |
| Migration | backup、restore、旧 schema 兼容 | PASS |
| Paid provider | Provider calls = 0 | PASS |

