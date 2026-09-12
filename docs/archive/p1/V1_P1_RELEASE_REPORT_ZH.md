# SentiNext V1/P1 离线发布成果报告

## 一、最终结论

**V1_P1_READY_OFFLINE（离线就绪）**

本轮完成的是本地优先、无需付费模型 API 的离线发布验收，不等同于已经完成真实 Provider 的生产验证。

## 二、本轮完成内容

- 补齐并诊断 SOCKS 代理依赖，启动前可检查运行环境。
- 对 DeepSeek 新请求的模型配置进行校验，与 V1 基线对齐。
- 为 Provider 空响应、代理依赖缺失等情况增加结构化错误信息。
- 未知价格不再导致成本台账崩溃，而是标记为“不可用”。
- 增加 Provider 操作级熔断，避免系统性失败时无限扩散请求。
- 保留运行中断后的恢复与取消机制。
- 增加明确的 `codex_offline_fixture` 离线执行模式，不产生 Provider 费用。
- 完成五问分析契约：发生了什么、为什么、影响谁、什么最重要、建议做什么。
- Dashboard 增加五问摘要。
- 增加可解释的 FIX / IMPROVE / BUILD / AMPLIFY 行动记录。
- 增加 Version Review 决策备忘录字段。
- 增加基于证据的离线 Chat 查询，引用原始评论片段，不生成无依据的因果结论。
- 增加缓存命中、分类、回退等运行计数器。
- 增加 3 个代表性离线语料库和 5 个离线场景。

## 三、实际跑出来的结果

| 检查项目 | 结果 |
|---|---|
| 后端 pytest | **110 passed** |
| Python compileall | **PASS** |
| 前端 TypeScript | **PASS** |
| 前端 ESLint | **PASS**，0 errors，3 warnings |
| 前端 production build | **PASS** |
| 离线 Fixture 测试 | **PASS** |
| 5 场景离线测试 | **PASS** |
| NINJA GAIDEN 4 离线语料 | **1000 条评论完成** |
| 离线模式 Provider 调用记录 | **0 条** |
| Gold v2 | **未修改** |
| P2 / P3 | **未启动** |

## 四、五问分析结果模型

每次分析结果现在包含：

1. **发生了什么**：对比观察；没有基线时明确显示不可用。
2. **为什么**：正向反馈、问题反馈、功能请求及对应覆盖率。
3. **影响谁**：语言、群体等支持的维度，并显示分母说明。
4. **什么最重要**：展示流行度、负面集中度、问题/请求支持度等透明评分组成。
5. **建议做什么**：行动类型、观察到的信号、证据、影响群体、不确定性和验证计划。

系统不会仅凭评论相关性推断因果关系。

## 五、NINJA GAIDEN 4 本轮离线成果的边界

NINJA GAIDEN 4 已经使用 1000 条本地评论跑通完整离线流程。该结果可以用于验证：

- 数据读取和分析流程是否能完整执行；
- 五问结果是否能生成；
- Dashboard 是否能展示；
- 证据引用是否能回到原始评论；
- 失败、回退、成本和运行状态是否可追踪。

但离线标签是确定性的开发 Fixture 标签，**不是人工 Gold，也不是 Provider 模型输出**，因此不能据此评价模型准确率。

## 六、已知限制

- 本轮没有重新调用真实外部 Provider，后续事项标记为 `EXTERNAL_PROVIDER_REVALIDATION`。
- 真实 Provider 仍需补做：单次 smoke request、5–10 条分类、50–100 条分阶段运行，以及重试、熔断、成本记录验证。
- 历史子分类精度约为 0.24，本轮没有重新设计分类体系。
- 首轮 LLM 情感结果仍不可用。
- Steam 评论存在自选择偏差和语言覆盖偏差。
- 小样本和稀有语言群体在分母不足时会被标记为不稳定或不可用。
- 当前后台任务仍是本地 FastAPI `BackgroundTasks`，不是分布式任务队列。
- SQLite 仍定位为单机、本地优先存储，不是多用户生产服务。
- 前端保留 3 个非阻塞 lint warning；后端保留 Pydantic 弃用警告。

## 七、发布建议

当前建议：**GO for V1/P1 offline dogfooding**。

可以继续使用离线模式进行产品流程和 Dashboard 试用；在宣称“真实模型生产可用”之前，应单独完成 `EXTERNAL_PROVIDER_REVALIDATION`。本轮不建议启动 P2/P3。

## 八、相关原始文件

- [英文原始发布报告](V1_P1_RELEASE_REPORT.md)
- [验收矩阵](V1_P1_ACCEPTANCE_MATRIX.md)
- [已知限制](V1_P1_KNOWN_LIMITATIONS.md)
- [运行手册](V1_P1_OPERATIONS_RUNBOOK.md)
- [自主执行进度](AUTONOMOUS_PROGRESS.md)
- [自主决策记录](AUTONOMOUS_DECISIONS.md)
- [失败记录](AUTONOMOUS_FAILURE_LOG.md)
