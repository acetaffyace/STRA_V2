# STRA V2 评论采集与分析流程重构 Spec

状态：Implementation Draft  
分支：`refactor/acquisition-analysis-flow-v1`  
基线：`main@f56dacfcf0ee6a25ac0128b9baa883cefd15d589`

## 1. 目标

STRA 对用户保持一个简单的主流程：

```text
搜索游戏
  ↓
点击「分析」
  ↓
设置时间 / 语言 / 评论类型 / 数量
  ↓
系统检查本地评论
  ↓
本地覆盖足够 → 直接复用
本地覆盖不足 → 自动从 Steam 获取并写入本地
  ↓
现有 Research Core + LLM 分类
  ↓
单一 Dashboard 报告
```

同时 Database 页面增加独立的「爬取评论」入口：

```text
Database
  ↓
选择游戏或输入 Steam App ID
  ↓
选择历史时间窗及采集条件
  ↓
Steam → SQLite
```

该入口只能采集和存储，**不得调用 LLM、不得生成报告**。

产品层可以把采集和分析耦合成“一次点击”；代码层必须保持 Acquisition 与 Analysis 分层。

---

## 2. 为什么采用稀疏时间窗缓存

STRA 是个人电脑上的本地应用，不建设大型 Steam 评论仓库。

版本 A 与版本 B 可以相隔数年，例如：

```text
2024-03-01 ～ 2024-03-30    1,842 reviews
2026-08-05 ～ 2026-09-05    2,216 reviews
```

本地只需要保存实际使用过的窗口。2024-04 到 2026-07 不需要因为版本间隔而被完整抓取。

因此缓存单位不是“每个游戏永远只保留最近 N 条”，而是：

> 原始 reviews 表 + 已完成 Collection Window 的覆盖记录。

禁止通过全局 latest-N 清理策略误删旧版本窗口。

---

## 3. 兼容性原则

本次重构必须遵守以下硬约束。

### 3.1 SamplingContract 继续作为公共底层契约

现有字段保持：

```text
app_id
start_time
end_time
languages
review_type
purchase_type
collection_order
include_offtopic_activity
max_reviews
```

未来的主分析、Database 手动采集、版本分析均复用同一契约，不另外制造互不兼容的日期 / 语言 / 购买来源字段。

### 3.2 `/analyze` 不破坏旧客户端

现有 legacy 字段继续兼容：

```text
review_count
language / languages
filter
day_range
persist
refresh
refresh_days
output_language
```

新前端应逐步优先提交明确的 `sampling`。旧调用不得因本次重构失效。

### 3.3 后续版本分析不得被切断

版本分析需要的核心能力为：

```text
版本发布日期
  ↓
形成 pre/post 时间窗
  ↓
SamplingContract
  ↓
共享 Acquisition Service
  ↓
Reviews / Collection Windows
```

禁止在 Database 页或 Dashboard 页内实现一套只能由 UI 使用的私有爬虫逻辑。

### 3.4 Research Core / LLM / 结果持久化继续工作

本次采集重构不删除：

- Research Core 后端统计能力
- `review_labels` LLM 缓存
- `analysis_results`
- general analysis run / progress
- version-analysis APIs
- existing report / evidence / export storage

它们继续消费同一个 Analysis Population。

---

## 4. 三层数据语义

### 4.1 Acquisition

回答：**Steam 上需要获取哪些评论？**

负责：

- Steam 请求
- cursor 分页
- 历史日期快速定位尝试
- timestamp 验证
- review-id 去重
- SQLite upsert
- Collection Window provenance

不负责：

- LLM
- Topic 分类
- 报告生成

### 4.2 Analysis Population

回答：**这次报告使用哪些评论？**

由 `SamplingContract` 固定。

分析运行必须继续保存 population provenance / snapshot hash，保证报告可复现。

### 4.3 Semantic Analysis

回答：**哪些评论还需要新的 LLM 分类？**

继续利用已有 `review_labels` / review hash / prompt version / model 信息进行复用。

Acquisition cache 与 LLM label cache 是两种不同缓存，不得混用。

---

## 5. 历史日期采集策略

### 5.1 Fast path

对于满足：

```text
start_time != null
end_time != null
collection_order == recent
```

的请求，可向 Steam storefront appreviews 尝试：

```text
start_date=<unix>
end_date=<unix>
date_range_type=include
```

该能力存在成熟社区客户端使用案例，但不作为 Steam 稳定官方协议依赖。

### 5.2 强制验证

Fast path 返回的每条评论必须满足：

```text
start_time <= timestamp_created <= end_time
```

只要出现越界评论，就判定 Steam 未正确应用该参数，**不得继续相信结果**。

### 5.3 Fallback

Fast path 不能证明有效时，自动退回现有 canonical cursor crawl：

```text
filter=recent
cursor pagination
local timestamp filtering
page-level lower-bound stop
```

因此：

> 日期快速定位是性能优化；cursor + timestamp filtering 才是正确性兜底。

用户 UI 不暴露 fast path / fallback 选择。

---

## 6. Collection Window Ledger

新增轻量覆盖表，不复制评论正文：

```text
review_collection_windows

app_id
start_time
end_time
languages_json
review_type
purchase_type
collection_order
include_offtopic_activity
requested_max_reviews
fetched_count
matched_count
collection_complete
truncated_by_max_reviews
stop_reason
targeted_date_attempted
targeted_date_applied
collected_at
```

作用只有一个：

> 告诉系统什么 population contract 曾被完整或截断地采集过。

不能只用 reviews 表的 `MIN(timestamp)` / `MAX(timestamp)` 推断“中间一定没有缺口”。

---

## 7. 缓存复用规则

分析请求到达后：

1. 根据 SamplingContract 查 compatible collection window。
2. 如果本地覆盖能够满足当前 population，直接加载 reviews。
3. 如果不能证明覆盖完整，重新采集或补齐。
4. Steam 返回数据通过 `review_id` upsert，因此重复获取不会生成重复行。

缓存命中必须保持当前 SamplingContract 的：

- languages
- review_type
- purchase_type
- collection_order
- include_offtopic_activity
- time bounds
- max_reviews semantics

不能因为“日期看起来一样”就复用不同 population definition 的数据。

### 后续增强：gap-only collection

V1 可以在没有完整 coverage row 时重新获取整个目标 window，并依赖 review-id upsert 去重。

后续优化可以计算：

```text
requested interval - known complete intervals = missing gaps
```

只抓缺口。

该优化不能改变 SamplingContract / API 语义。

---

## 8. 多语言规则

Steam 一次请求接受一个具体 language，因此多语言需要内部 fan-out。

用户看到的 `max_reviews` 必须是：

> 整个 population 的总上限。

不能解释为“每语言 N 条”，否则选择 5 个语言、max=2,000 时实际抓 10,000 条，个人电脑使用体验不可接受。

V1 采用平衡 first-pass quota 后做全局 cap。后续可以增加 quota redistribution，但最终输出始终：

```text
len(population) <= max_reviews   (max_reviews > 0)
```

`max_reviews=0` 仍沿用现有契约，表示不限数量。

---

## 9. API

### 9.1 手动采集

```http
POST /reviews/collect
```

Request：

```json
{
  "sampling": {
    "app_id": 553850,
    "start_time": 1709251200,
    "end_time": 1711843199,
    "languages": ["english", "schinese"],
    "review_type": "all",
    "purchase_type": "all",
    "collection_order": "recent",
    "include_offtopic_activity": false,
    "max_reviews": 2000
  },
  "force": true
}
```

Response 核心字段：

```text
source
fetched_count
stored_count
matched_count
cache_hit
collection_complete
truncated_by_max_reviews
stop_reason
sampling
stats
```

硬约束：该 endpoint 不能 import / call LLM classification pipeline。

### 9.2 覆盖记录

```http
GET /reviews/collection-windows?app_id=553850
```

用于 Database 数据管理、调试和未来版本分析的 acquisition planning。

### 9.3 主分析

继续使用：

```http
POST /analyze
```

外部分析协议不被替换。

正式分析的 fetch path 应优先复用 acquisition cache；不足时 Acquisition Service 自动获取，之后继续进入现有分析管线。

---

## 10. Dashboard UI

### 10.1 用户流程

```text
Search Result
  ↓
分析
  ↓
AcquisitionSetupDialog
  ↓
开始分析
  ↓
cache / Steam acquisition
  ↓
Research Core + LLM
  ↓
Dashboard 单一报告
```

### 10.2 默认主字段

- 时间范围：最近 7 / 30 / 90 天 / 自定义 / 不限时间
- 语言：真正 multi-select；All languages 与具体语言互斥
- 分析评论上限：500 / 1,000 / 2,000 / 5,000 / 10,000 / 不设上限

### 10.3 Advanced

- 推荐状态：all / positive / negative
- 购买来源：all / steam / non_steam_purchase
- collection order：recent / updated / helpful
- include off-topic activity

只要存在 start/end 时间窗口：

```text
collection_order = recent
```

UI 禁用 updated/helpful，并说明原因。

### 10.4 日期边界

前端统一将日期输入转换为 UTC：

```text
start date → 00:00:00 UTC
end date   → 23:59:59 UTC
```

后端 SamplingContract 的 start/end 为 inclusive Unix timestamp。

---

## 11. Database UI

Database 页面新增统一风格的「爬取评论」。

入口支持：

- 选择本地已有游戏
- 直接输入新的 Steam App ID

打开与主分析共用的 AcquisitionSetupDialog，但 `mode=collect`。

文案必须明确：

> 这里只保存评论，不运行 LLM 或报告生成。

完成后刷新：

- game list
- review stats
- reviews explorer

UI 使用现有 STRA dark slate / glass / sapphire accent 体系，不新增另一套视觉语言。

---

## 12. Dashboard 报告展示原则

Research Core 继续存在于后端，但不再作为一个与 Semantic Layer 并列的用户产品模块。

最终 Dashboard 应回归一份报告：

- 分析范围
- 评论量
- 推荐率及趋势
- Issues
- Requests
- Positive feedback
- 用户组成 / 主要 segment
- 代表评论
- 分析限制

允许在顶部展示轻量 scope：

```text
2026-08-01 ～ 2026-08-30 · 1,000 reviews · English / 简体中文
```

以及：

```text
采集完整
达到评论上限
```

禁止把以下工程状态作为大卡片占据主要界面：

```text
Research Core
Research READY
Semantic READY
Canonical Report
Legacy Insights
```

---

## 13. 失败与边界处理

### Steam targeted date 参数失效

自动 fallback，不向用户返回错误 population。

### Steam API 429 / 5xx

沿用现有 retry + circuit breaker。

### max_reviews 达到

```text
truncated_by_max_reviews = true
collection_complete = false
stop_reason = max_reviews_reached
```

不得伪装为完整时间窗。

### 缓存被清理

Collection Window 不能继续声称不存在的本地 rows 可复用。Database clear / per-game delete 必须同步清除对应 coverage，或 cache lookup 必须检测 coverage 与 raw rows 是否一致。

### 空时间窗

只有能够证明 Steam 正确执行目标时间窗、并抵达结果边界时，才能记录为 complete empty window。未经证明的 fast-path 空第一页必须 fallback。

---

## 14. 测试门槛

最低要求：

1. targeted historical window 返回窗口内评论 → fast path accepted。
2. targeted endpoint 返回窗口外评论 → fast path rejected。
3. fast path rejected → canonical cursor fallback。
4. compatible cache hit → 不再调用 Steam。
5. manual `/reviews/collect` → 不触发 LLM。
6. all languages 与 specific languages validation 保持。
7. bounded window 只能使用 recent。
8. multi-language final count 不超过 total max_reviews。
9. database clear / game delete 后旧 coverage 不可误命中。
10. existing `/analyze` legacy request tests 继续通过。
11. existing version-analysis tests 继续通过。
12. frontend TypeScript + Next build 通过。

---

## 15. Git / Review 流程

实施分支：

```text
refactor/acquisition-analysis-flow-v1
```

所有改动通过可审查 commit 保存，不 force-push main。

建议逻辑提交：

```text
feat: add reusable review acquisition service
feat: expose manual review collection api
feat: reuse acquisition cache in analysis fetch path
feat: add shared acquisition setup ui
feat: add manual review collection to database
feat: wire sampling setup into dashboard analysis
refactor: restore single-report dashboard presentation
test: cover sparse acquisition and cache reuse
docs: define acquisition analysis flow contract
```

最终通过 Draft PR 检查：

- changed files
- CI backend
- CI frontend
- compatibility diff
- no unintended version-analysis removal

确认后再进入正式 review / merge，不直接修改 `main`。

---

## 16. 本轮明确不做的事情

为了避免再次过度设计，本轮不建设：

- 全量 Steam 历史仓库
- 后台持续同步服务
- 定时爬虫
- 云数据库
- 分布式任务队列
- embedding taxonomy 分类替代 LLM
- 新的 Version Review 产品逻辑

本轮只建设以后这些能力可以复用的正确 Acquisition 边界。
