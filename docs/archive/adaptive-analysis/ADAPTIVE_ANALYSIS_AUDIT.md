# Adaptive Analysis Phase 0 Audit

日期：2026-08-25

## 审计范围

复用目标：现有 `analysis_runs` / `version_events`、Version Review、Five Questions、metric provenance、Evidence、offline runner、Apex 7—8 月 corpus、NINJA GAIDEN 4 corpus、Dashboard/Reports。

## 现有能力

| 能力 | 现状 | 结论 |
|---|---|---|
| Run | `analysis_runs` 已有 generalized schema、lifecycle、immutable result | 复用，不建平行 run truth |
| Event | `version_events` 只有单点 `event_date`，支持 event_type/source/source_url/manual_verified | 需要兼容扩展 range/effective/published/provenance |
| Version Review | `version_analysis.py` 已有 pre/event_day/post、daily volume、topic/evidence/recommendations | 复用 executor，外包 adaptive design 与更严格合同 |
| Five Questions | 已有 metric provenance、无基线 unavailable、行动卡 | 只消费 valid AnalysisDesign 结果 |
| Evidence | `evidence.py` 有 source-slice verification、run/app/review scope | 复用并挂接 EvidenceGrade |
| Metrics | `metric_provenance.py` 有 numerator/denominator/coverage/run_id | 扩展 effect/support/CI，不覆盖旧字段 |
| Offline | `run_offline_fixture.py` 可零 Provider 跑 ingest→label→insights→immutable result | 作为 deterministic regression harness |
| Apex corpus | `data/v1_pilot/apex_legends_1172470_2026-07-01_2026-08-31/reviews.jsonl`，`filter=recent` 全量抓取 12,600 条原始、窗口 12,435 条 | 可作为回归数据；事件锚点不得预设 |
| NINJA corpus | 1000 条离线 Fixture | 用于 profile/scenario 回归，不当模型质量证据 |
| UI | Dashboard/Reports/Version Review 已存在，但没有 Analysis Design/robustness/grade 卡 | 后续增量接入 |

## 已确认的缺口

1. `version_events.event_date` 将事件压成单日，无法表达 published/effective/range/precision/conflict。
2. `analysis_runs.config` 可保存配置，但缺少 canonical immutable `AnalysisDesign` schema/version identity。
3. Version Review 默认固定窗口，未根据 archetype、velocity、样本量、同期事件自适应。
4. 已有 pre/post 指标，但没有统一 Population Comparability、CI/effect size、window/cohort robustness、Evidence Grade。
5. emerging topics 是候选队列，不是完整 Public Opinion Event Detector。
6. Five Questions 当前能识别无基线，但还不能消费 design validity、robustness、competing mechanisms。

## 不创建平行事实源

- 事件事实继续以 `version_events` 为 canonical store。
- Run 继续以 `analysis_runs` / immutable result 为 canonical store。
- AnalysisDesign 作为 run 关联的 methodology snapshot，不复制 reviews 或另建 event catalog。
- 既有 Gold v2、cost ledger、FTS、review_id 语义不变。

## 实施边界

本轮只实现确定性、可解释、无付费 Provider 的分析设计层；不引入 PostgreSQL、Redis、Celery、vector database，也不把离线 Fixture 伪装成模型质量验证。
