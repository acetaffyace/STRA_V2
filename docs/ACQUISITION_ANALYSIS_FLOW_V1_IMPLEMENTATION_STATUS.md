# STRA V2 Acquisition / Analysis Flow V1 — Implementation Status

本文是 `ACQUISITION_ANALYSIS_FLOW_V1.md` 的实现状态补充。若两份文档在 V1 UI 细节上存在差异，以本文和当前分支代码为准；底层兼容契约仍以主 Spec 为准。

分支：`refactor/acquisition-analysis-flow-v1`  
基线：`main@f56dacfcf0ee6a25ac0128b9baa883cefd15d589`  
PR：`#2`（Draft，未合并 main）

## 已完成

### 主分析入口

Dashboard 无 report query 时使用新的统一分析首页：

```text
搜索游戏
  ↓
分析
  ↓
设置时间 / 语言 / 推荐状态 / 购买来源 / 数量
  ↓
优先复用本地评论
  ↓
覆盖不足则自动 Steam 采集并写入 SQLite
  ↓
沿用现有 Research Core + LLM pipeline
  ↓
进入原有报告详情页
```

已有 `/dashboard?game=...`、run/detail/report 视图继续使用原成熟 Dashboard 实现，不重写已有报告核心逻辑。

### Database 手动采集

Database 页面新增「爬取评论」：

- 可选已有本地游戏；
- 可直接输入 Steam App ID；
- 与主分析共用同一个 AcquisitionSetupDialog；
- 仅执行 Steam → SQLite；
- 不运行 LLM；
- 不创建报告。

### 稀疏历史时间窗

对于版本相隔很久的情况，不要求把中间年份完整下载。

系统可以只保存实际使用过的窗口，例如：

```text
2024-03-01 ～ 2024-03-30
2026-08-05 ～ 2026-09-05
```

新增 `review_collection_windows` 只记录采集覆盖和 provenance；评论正文仍只保存在既有 `reviews` 表。

### 历史日期定位

有完整 start/end 且 order=recent 时：

1. 尝试 `start_date/end_date/date_range_type=include` fast path；
2. 对每条返回评论校验 `timestamp_created`；
3. 任意越界或无法证明参数有效，立即放弃 fast path；
4. 自动 fallback 到既有 recent + cursor + timestamp filtering。

因此 fast path 只负责提速，不承担正确性。

### 缓存复用

主分析通过 package-level fetch compatibility wrapper 接入 Acquisition Service：

- compatible window 命中 → 不重新请求 Steam；
- 未命中 → 自动采集；
- review_id upsert 避免重复行；
- 删除游戏导致本地评论为 0 时，自动分析强制重新采集，旧 coverage 不可误命中；
- collection-windows API 不暴露已经没有 raw rows 的 app coverage。

### 多语言总预算

V1 的 `max_reviews` 对用户始终表示整个 population 的总上限。

Targeted fast path 和 canonical fallback 都使用平衡 first-pass quota，避免旧实现的“每语言各自抓 N 条、最后再裁 N 条”造成请求放大。

例如：

```text
max_reviews = 10,000
languages = 3
```

内部 first-pass 约为：

```text
3,334 / language
```

而不是：

```text
10,000 / language
```

最终 population 仍不超过 10,000。

## V1 UI 最终限制

STRA 是个人电脑本地应用，因此新 UI 不提供 Unlimited。

可选数量：

```text
500
1,000
2,000
5,000
10,000
```

默认：

- 主分析：1,000
- Database 手动爬取：2,000

底层 `SamplingContract.max_reviews=0` 仍保留为 legacy / internal compatibility 语义，不删除旧接口能力；只是新 UI 不提供这个危险入口。

## 仍然保持兼容的接口

- `/analyze` legacy fields 保留；
- `/analyze` explicit `sampling` 可用；
- `SamplingContract` 继续作为 acquisition / analysis / future version analysis 的共享 population contract；
- Research Core backend 不删除；
- `review_labels` LLM cache 不删除；
- analysis runs / progress / immutable result persistence 不删除；
- version-analysis 现有接口和测试不删除。

新增：

```text
POST /reviews/collect
GET  /reviews/collection-windows
```

## Dashboard 展示

Research Core 仍是后端统计能力，但前台 `ResearchOverview` 已收缩成轻量 Analysis Scope：

- 日期范围
- 评论数量
- 语言
- 采集完整 / 达到上限 / 未完整
- stale warning（如适用）

不再把 Research Core READY / Semantic READY 当成两个并列产品模块展示。

## 明确未做

V1 不做：

- 全量 Steam 历史仓库；
- 后台持续同步；
- 云数据库；
- 分布式任务；
- embedding taxonomy 替代 LLM；
- 版本分析产品本身的重新设计；
- collection-window gap 差集规划。

最后一点意味着：如果没有一个已有 coverage 可以完整证明目标窗口，本轮允许重新抓该目标窗口，再依靠 review_id upsert 去重。后续可以优化为只补缺口，但不能改变现有 SamplingContract/API 语义。

## 自动化验证

新增单元测试覆盖：

- historical fast path 仅接受窗口内 timestamp；
- Steam 忽略日期参数时拒绝 fast path；
- fast path 失败自动 cursor fallback；
- compatible cache hit 不再采集；
- 本地 raw reviews 被清空后不允许旧 coverage 误命中；
- targeted 多语言使用总上限；
- fallback 多语言实际请求预算也受总上限约束。

GitHub Actions CI 要求：

- backend syntax check；
- backend test suite；
- frontend TypeScript check；
- frontend Next build。

合并前必须以 PR 最新 head 的 CI 双绿为准。
