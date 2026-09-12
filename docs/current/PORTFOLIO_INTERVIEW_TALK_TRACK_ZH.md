# SentiNext 面试话术

## 30 秒介绍

SentiNext 是一个面向游戏团队的玩家声音决策工具。它不只做情感分类，而是把 Steam 评论组织成五个产品问题，再把信号连接到 FIX、IMPROVE、BUILD、AMPLIFY 行动。核心差异是 Run、provenance、immutable result 和 Evidence verification：每个重要判断都能回到真实玩家原话。

## 90 秒解释

我先用 150 条人工核验 Golden Set 冻结 Dev/Holdout，并历史性执行真实 DeepSeek baseline。评测发现粗粒度 issue detection 相对可用，但细粒度 taxonomy precision 约 0.24、recall 约 0.67–0.70，存在 overprediction。所以我没有把 taxonomy 直接当成事实，而是把它定位为 candidate discovery；进入产品决策前必须有 verified evidence 和不确定性说明。

NINJA GAIDEN 4 的 1000 条数据是 offline end-to-end product/system validation，验证的是从评论、Run、五问、Evidence、Dashboard、Chat 到 Reports 的系统链路，不是模型质量 benchmark。

## 3 分钟深挖

真实 Pilot 还暴露了 Windows/SOCKS 依赖、旧 DeepSeek model 配置、HTTP 200 empty content、batch retry fan-out、cost ledger secondary exception 和中断恢复问题。之后补上 runtime diagnostics、typed provider failures、bounded retry、operation circuit breaker、unknown-cost semantics、startup recovery 和 explicit offline mode。这个项目的重点不是“调用了 LLM”，而是把数据、分析、产品展示、证据和失败恢复接成一条可诊断链路。

## 常见问题

### Why is this more than sentiment analysis?

因为输出不是正负面比例，而是五问决策结构、证据、分母、行动类型和验证计划；用户可以从结论回到原始评论。

### How do you know the model is accurate?

我不会说它整体准确。我们有 150 条人工核验 Gold、冻结 Dev/Holdout 和历史 DeepSeek baseline；结果是 issue detection 相对可用，但细粒度 taxonomy precision 只有约 0.24，所以产品要求 evidence verification。

### Why is taxonomy precision only ~0.24?

细粒度标签边界重叠、评论一条多主题、模型有 overprediction 倾向。这个数字揭示了分类器的质量边界，而不是靠 prompt 叙事掩盖它。

### Why did you still keep the model?

因为模型仍然适合从大量评论中发现候选信号；但候选发现和最终决策被拆开，后者必须有原话和不确定性。

### How do you prevent hallucinated evidence?

引用必须在对应 Run 的 canonical review 中通过 source-slice verification；不能核验就标记 unavailable，不生成替代原话。

### Why SQLite instead of PostgreSQL?

这是桌面、本地优先产品，SQLite 降低部署和数据移动成本，并且已经通过 FTS、迁移、备份和兼容性测试。若未来进入多用户服务，再用实际并发和运维需求评估数据库迁移。

### Why no vector database?

当前问题是可追溯的评论证据和结构化聚合，不是大规模语义检索。引入向量库会增加同步、版本和证据回溯复杂度，暂时没有足够收益。

### What failed in the first real pilot?

Windows/SOCKS runtime、旧模型配置、HTTP 200 空内容、重试扇出、cost ledger 二次异常和中断恢复都曾失败；之后转化为 typed errors、bounded retry、circuit breaker、unknown-cost 和 recovery 语义。

### What would you do next?

只做三件事：external provider staged revalidation、taxonomy precision calibration、multiple-game real-user dogfooding。

### Which parts are AI-generated versus deterministic?

标签候选可以来自 LLM；Run、schema、分母、指标 provenance、证据核验、状态机、成本记录、错误分类和离线 Chat 路径是确定性的。模型输出不能绕过证据门禁。
