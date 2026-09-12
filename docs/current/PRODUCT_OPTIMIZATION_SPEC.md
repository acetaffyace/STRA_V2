# SentiNext / Game Player Voice Intelligence
## 产品优化目标与实施规范

版本：v1.0  
用途：供 Codex 进行产品、数据、LLM、后端、前端与工程可靠性改造  
执行原则：先保证分析可信，再提升业务价值，再优化性能和成本，最后考虑规模化架构。

---

# 0. 文档目的

本项目不是一个通用 Steam 评论 Dashboard，也不是一个“把 Steam 评论交给 LLM 总结”的聊天应用。

产品目标应统一为：

> 将非结构化 Steam 玩家声音转换为可验证、可追溯、可比较、可用于产品与社区决策的结构化分析。

系统必须围绕五个业务问题设计：

1. 最近玩家体验发生了什么变化？
2. 玩家为什么满意或不满？
3. 哪些玩家群体受到的影响最大？
4. 哪些问题与机会最值得优先处理？
5. 应采取什么行动，以及后续如何验证行动是否有效？

所有页面、API、指标、LLM 调用和分析结果必须能够映射到以上五个问题之一。

不能回答上述问题、不能提高分析可信度、不能明显改善性能/成本/可靠性的功能，不进入当前优化范围。

---

# 1. 产品北极星

产品不追求“功能最多”。

产品追求：

> Evidence-backed Player Voice Decision System

即：

```text
Player Signal
    ↓
Reliable Data
    ↓
Structured Classification
    ↓
Deterministic Metrics
    ↓
Cohort / Trend Diagnosis
    ↓
Verified Evidence
    ↓
Priority
    ↓
Recommended Action
    ↓
Post-action Validation
```

最终用户看到的任何重要结论，都应该能够反向追踪到：

```text
结论
→ 指标
→ 分母/样本范围
→ 分类来源
→ 对应评论
→ 分析 Run
→ 数据采集时间
→ 模型 / Prompt / Taxonomy 版本
```

这是系统可信度的基本约束。

---

# 2. 当前阶段明确不做什么

Codex 不得因为“更生产级”而主动引入不必要的复杂架构。

当前禁止把以下事项作为优先优化：

- 不因“以后可能多人使用”立即迁移 PostgreSQL。
- 不因存在后台任务立即引入 Redis + Celery。
- 不重写 FastAPI。
- 不重写 Next.js。
- 不替换 Tauri。
- 不建立复杂账户系统。
- 不为了技术先进而引入向量数据库。
- 不把所有分析迁移到 Embedding / RAG。
- 不增加普通通用聊天能力。
- 不为了“AI 感”让更多指标由 LLM 计算。
- 不把所有评论送高价大模型重新分析。
- 不一次性接入 Reddit、Discord、YouTube 等多个来源。
- 不对现有 provider abstraction 进行大规模重构，除非有明确测试证明收益。

当前定位仍然是：

> Local-first / single-user / Steam-first analytical application.

只有当规模指标实际触发阈值以后，才升级基础设施。

---

# 3. 外部参考项目与借鉴原则

## 3.1 Steam Review Intelligence

参考：

`arda-basarici/steam-reviews`

重点借鉴：

### A. Data pipeline separation

将：

```text
fetch
clean
validate
analyse
report
```

明确分离。

不要让 `/analyze` 同时隐式承担：

抓数据、清洗、更新数据库、LLM 分类、聚合、报告等所有职责。

### B. Reproducibility

每一次分析都应能明确回答：

- 数据从哪里来；
- 截止什么时间；
- 用了什么查询参数；
- 总共取得多少条；
- 排除了多少条；
- 最终分析多少条；
- 使用什么版本算法；
- 使用什么模型。

### C. Methodological restraint

该项目特别值得借鉴的一点是：

> 对无法由数据支持的结论明确不做判断。

其分析采用 within-game 验证，而不是简单将不同游戏的数据混在一起得出结论，并且明确指出 observational data 的边界。

SentiNext 也必须采用同样的产品原则：

**系统必须允许“不知道”成为合法答案。**

---

## 3.2 Steamworks User Reviews API

以 Steamworks 官方文档为数据接口唯一事实来源。

分页采集应遵循：

- `recent`
- `updated`
- cursor pagination
- language
- purchase_type
- review_type

对于连续分页，Steam 官方明确建议使用 `recent` 或 `updated`，而不是默认基于 helpfulness 的 `all`。

需要特别优化：

### Initial ingestion

第一次分析：

```text
filter = recent
→ cursor pagination
→ target window / target review count
```

### Incremental ingestion

已有数据：

```text
filter = updated
→ overlap window
→ upsert by recommendation_id
→ timestamp_updated comparison
→ stop at high-water mark
```

禁止每一次 Analyze 都无条件重新抓完整窗口。

---

## 3.3 SQLite FTS5

当前项目已有明确 FTS 重复风险。

目标架构：

```text
reviews
   ↓ triggers
reviews_fts
```

使用：

- external-content FTS5；
- `content_rowid`；
- INSERT trigger；
- UPDATE trigger；
- DELETE trigger；
- rebuild repair command。

SQLite 官方明确建议 external-content FTS 使用触发器维护内容表和 FTS 索引的一致性，并提供 `rebuild` 用于重新建立已经不一致的索引。

不要继续在业务代码不同路径里手动维护两份数据。

---

## 3.4 Argilla：Golden Set / Human Evaluation

不要直接把 Argilla 作为产品依赖。

借鉴其 workflow：

```text
LLM prediction
→ human validation
→ disagreement
→ guideline refinement
→ gold dataset
→ regression evaluation
```

Argilla 支持 model suggestions、人工 annotation、多标签任务和人工 feedback，非常适合作为本项目 Golden Set 工作流的设计参考。

SentiNext 内部只需要实现轻量版。

---

## 3.5 Phoenix / Langfuse：LLM Evaluation 与 Trace

不要默认将 Phoenix/Langfuse 打包进桌面客户端。

借鉴以下数据模型：

```text
run
trace
llm_call
prompt_version
model
latency
input_tokens
output_tokens
cost
error
evaluation
```

Phoenix 支持 tracing、dataset、experiment、prompt/model comparison 和 evaluation，适合作为开发期评测工具。

Langfuse 同样提供 tracing、prompt version、datasets、experiments 和多种 evaluation 机制。

本项目第一阶段只需要自建轻量 `llm_calls` + benchmark。

---

## 3.6 LiteLLM：成本治理参考

不要立即将所有 provider 调用替换为 LiteLLM。

借鉴：

- token tracking；
- model price map；
- spend tracking；
- per-feature cost；
- budget cap；
- model routing。

LiteLLM 已实现基于模型 token 价格的 spend tracking，并支持 provider/model/tag budget。

SentiNext 应实现自己的最小成本治理层。

---

## 3.7 Instructor：结构化 LLM 输出

当前分类阶段应尽可能：

```text
Pydantic Schema
→ Provider structured output
→ deterministic validation
→ limited retry
→ failure state
```

而不是：

```text
free text
→ regex/json repair
→ repeated retry
→ fallback pretending to be valid result
```

Instructor 的核心模式就是 Schema-first structured extraction + validation + retry，并支持多个当前项目已经使用的 provider。

可以借鉴其设计，但不强制引入依赖。

---

## 3.8 Huey：本地持久任务参考

FastAPI 官方明确提示：重型后台计算如果需要脱离 Web 进程，应考虑独立任务系统。

但本项目 local-first，不应立刻引入 Redis/Celery。

如第二阶段确实需要持久任务队列，优先评估：

`SqliteHuey`

Huey 支持 SQLite、任务重试、锁、超时、优先级和多种 worker 模式。

优先级：

```text
analysis_runs 状态机
↓
restart reconciliation
↓
必要时 SqliteHuey
↓
真实多人规模以后才 Redis
```

---

# 4. 目标系统架构

目标逻辑架构：

```text
Steam Reviews API
        │
        ▼
Incremental Ingestion
        │
        ├── ingestion_state
        │
        ▼
Canonical Review Store
        │
        ├── reviews
        └── FTS5
        │
        ▼
Analysis Run Builder
        │
        ├── immutable run metadata
        ├── review fingerprint
        └── run scope
        │
        ▼
Classification Layer
        │
        ├── cached labels
        ├── new/changed reviews only
        ├── schema validation
        └── classification provenance
        │
        ▼
Evidence Enrichment
        │
        ├── priority evidence sample
        └── verified quotes
        │
        ▼
Deterministic Metrics Engine
        │
        ├── trend
        ├── cohort
        ├── issue
        ├── request
        └── opportunity
        │
        ▼
Decision Layer
        │
        ├── What changed?
        ├── Why?
        ├── Who?
        ├── Priority?
        └── What next?
        │
        ├──────── Dashboard
        ├──────── Chat
        ├──────── Version Review
        └──────── Report
```

横向能力：

```text
Data Quality
LLM Evaluation
Cost Tracking
Performance Tracking
Versioning
Auditability
```

---

# 5. Analysis Run 必须成为系统核心对象

当前“一个游戏只有最新 analysis result”的模式需要调整。

新增/完善：

`analysis_runs`

至少包含：

```text
run_id
app_id

created_at
started_at
completed_at

status
phase

data_cutoff
window_start
window_end

requested_languages
requested_review_count

retrieved_count
valid_review_count
classified_count
fallback_count
enriched_count

review_fingerprint

taxonomy_version
prompt_version
analysis_version

provider
model_id

input_tokens
output_tokens
estimated_cost

classification_coverage
evidence_coverage

parent_run_id
error_code
error_message
```

Run 完成后必须 immutable。

允许状态：

```text
queued
ingesting
classifying
enriching
aggregating
summarizing

completed
failed
cancelled
```

禁止：

完成之后 phase 仍然是 `classifying`。

---

# 6. 数据范围与 Provenance

每一个指标必须知道自己的数据范围。

前端不得只显示：

> Technical Issues 17%

至少能够获取：

```text
value: 0.17
numerator: 143
denominator: 842

population_count: 842
classified_count: 817

source_type: "llm_label"
is_sampled: false

run_id: xxx
window_start: ...
window_end: ...
```

对数据源必须区分：

```text
raw_steam
deterministic_derived
llm_derived
heuristic
```

这是一个强制 contract。

---

# 7. 全量、样本、Evidence 三种数据必须彻底区分

定义三个术语。

## Population

当前 Run 中所有满足 scope 的有效评论。

用于：

- review count；
- recommendation；
- language；
- playtime；
- Steam 原始字段。

## Classified Population

Population 中获得有效模型分类的评论。

用于：

- issue rate；
- feature request rate；
- taxonomy distribution；
- aspect metrics。

分母只能是：

> valid classified reviews

失败/fallback 不允许静默混入。

## Priority Evidence Sample

用于：

- quote；
- evidence card；
- LLM 深度 enrich；
- case examples。

这不是 representative sample。

前端不得把它叫：

> 玩家代表样本

应叫：

> Priority Evidence / Selected Evidence

如果未来需要 representative evidence，则单独实现 stratified sample。

---

# 8. Label Provenance

每条分类增加：

```text
label_source:
    llm
    cache
    rule_fallback
    failed

model_id
provider
prompt_version
taxonomy_version
review_hash

validated
retry_count
latency_ms
input_tokens
output_tokens
```

核心统计默认只接受：

```text
label_source IN ("llm", "cache")
AND validated = true
```

`rule_fallback`：

只允许保证程序可继续运行。

不得自动进入正式分析 KPI。

---

# 9. Golden Set 与模型评测体系

这是 P0，不是“以后再做”。

创建：

```text
tooling/evals/player_voice/
```

包含：

```text
golden_set.jsonl
annotation_guidelines.md
evaluate.py
baseline.json
README.md
```

Golden Set 初始目标：

300–500 条。

必须覆盖：

- positive；
- negative；
- mixed；
- short review；
- long review；
- sarcasm；
- technical；
- gameplay；
- content；
- UI；
- onboarding；
- monetization；
- feature request；
- no-issue review；
- multi-label review。

语言按当前实际主要数据分布做 stratified selection。

优先语言每种尽量至少 50 条。

至少部分样本需要二次人工复查。

---

# 10. Evaluation Metrics

不要使用“LLM confidence”代替准确率。

输出：

### Category

- precision
- recall
- F1
- macro F1

### Multi-label

- micro F1
- macro F1
- per-label precision / recall

### Issue detection

- precision
- recall

### Feature request

- precision
- recall

### Sentiment

- accuracy
- confusion matrix

### Evidence

- quote exactness
- quote support rate

### Operational

- invalid JSON rate
- schema retry rate
- fallback rate
- latency
- tokens / review
- cost / 1,000 reviews

所有 Prompt / Model 修改必须跑 benchmark。

---

# 11. 模型升级门禁

Codex 不允许因为：

> “这个模型更便宜”

直接替换模型。

模型 A → 模型 B 必须满足：

```text
Golden Set quality
+
latency
+
cost
```

三维比较。

推荐输出：

```text
Model Candidate
Macro F1
Critical Issue Precision
Feature Request F1
Invalid Output Rate
Latency p50 / p95
Tokens / 1k reviews
Cost / 1k reviews
```

只有质量下降在允许范围内且成本/延迟显著改善时才能替换。

---

# 12. 分类成本优化

优化顺序必须是：

## 第一层：不调用

最佳 LLM 成本优化：

> 不调用 LLM。

以下情况必须 0 次 classification API call：

- review_hash 未变化；
- taxonomy_version 未变化；
- prompt_version 未变化；
- model_id 未变化；
- 已存在 validated label。

---

## 第二层：只分析增量

假设：

历史已有 10,000 条评论。

新抓：

320 条新评论；
15 条被编辑。

本次最多重新分类：

335 条。

不能重新分类 10,000 条。

---

## 第三层：控制输入

分类 Prompt：

只包含完成 taxonomy 分类所需信息。

不得包含：

- 完整游戏历史；
- Dashboard 汇总；
- 无关 metadata；
- 多余长说明。

长评论采用 token-aware policy。

例如：

```text
normal → full text
oversized → controlled truncation/chunk policy
```

所有截断必须记录：

```text
was_truncated
original_chars
processed_chars
```

---

## 第四层：控制输出

分类必须使用严格 schema。

禁止让分类模型输出长篇解释。

应该输出：

```json
{
  "categories": [],
  "issues": [],
  "requests": [],
  "sentiment": "",
  "confidence": null
}
```

而不是生成自然语言分析报告。

---

## 第五层：分模型路由

分类与高级总结不要默认使用相同模型。

概念：

```text
Bulk Classification
→ cheapest model that passes Golden Set

Complex Evidence / Health Summary
→ stronger model when required
```

但便宜模型必须先通过 benchmark。

---

# 13. 中长期分类降本：SetFit

如果出现以下任一情况，再做 SetFit 实验：

```text
新增评论 > 50,000 / 月
OR
classification 占 LLM 总成本 > 70%
OR
离线/隐私分类成为核心需求
```

SetFit 是 few-shot、prompt-free 的轻量分类框架，并支持 multilingual sentence transformer；官方示例强调它可以用较少标注数据训练高效分类器。

未来目标：

```text
local classifier
        ↓
high confidence ──→ accept
        │
low confidence
        ▼
LLM classification
```

但不得现在直接实施。

必须先：

Golden Set → benchmark → cost analysis。

---

# 14. Emerging Topic Discovery

固定 taxonomy 会漏掉新问题。

增加实验能力：

> Emerging Topics

但不要给每条评论调用 LLM。

候选路线：

```text
text embedding / TF-IDF
→ clustering
→ cluster keywords
→ LLM only names clusters
```

BERTopic 可以作为设计参考，其核心是 embeddings + clustering + c-TF-IDF topic representation。

本功能 P2。

不允许替代固定 taxonomy。

正确结构：

```text
Known taxonomy
+
Unknown / Emerging topic detector
```

---

# 15. FTS 数据一致性整改

P0。

目标 invariant：

```text
1 canonical review
→ exactly 1 FTS document
```

要求：

### 数据库约束

`reviews` 中 Steam review ID 必须唯一。

建议：

```text
UNIQUE(app_id, recommendation_id)
```

### FTS

使用 external-content FTS。

### Trigger

INSERT：

更新 FTS。

UPDATE：

删除旧 index + 写新 index。

DELETE：

同步删除。

### Repair

新增：

```text
rebuild_fts()
verify_fts_integrity()
```

### 自动测试

必须覆盖：

```text
insert once → 1 FTS row

same upsert × 100
→ still 1 FTS row

update text
→ only new text searchable

delete review
→ no longer searchable

rebuild
→ FTS count consistent
```

验收：

```text
duplicate FTS review IDs = 0
```

---

# 16. Steam 增量抓取

新增：

`review_ingestion_state`

字段建议：

```text
app_id
language

last_success_at
last_seen_created_at
last_seen_updated_at

last_review_id

last_cursor
last_fetch_count
```

不要把 Steam cursor 当永久 checkpoint。

使用：

```text
time watermark
+
review ID dedup
+
small overlap
```

保证 at-least-once ingestion + idempotent upsert。

---

# 17. 分析数据指纹

Review fingerprint 不应该只是模糊 hash。

建议：

```text
scope_fingerprint =
hash(
  app_id
  sorted review ids
  review updated timestamp
  review text hash
  query window
)
```

Label fingerprint：

```text
hash(
  review_hash
  taxonomy_version
  prompt_version
  model_id
)
```

Analysis fingerprint：

```text
hash(
  scope_fingerprint
  taxonomy_version
  analysis_version
)
```

---

# 18. 五大业务问题：Dashboard 重构

Dashboard 不再以“我有什么图”为核心。

重构成五段。

---

# 18.1 What Changed?

页面第一屏回答：

> 最近发生了什么？

必须出现：

- analysis window；
- compared window；
- review count；
- recommendation rate；
- negative review volume；
- Top Rising Issues；
- Top Falling Issues；
- Top Positive Themes；
- 数据覆盖率。

变化必须同时有：

```text
current
previous
absolute delta
percentage / pp delta
```

对于率：

使用 percentage points。

---

# 18.2 Why?

第二段：

> 哪些玩家体验最可能解释当前变化？

展示 Driver Cards。

每张卡：

```text
Issue / Topic
Current mention rate
Previous mention rate
Delta

Negative association
Affected reviews

Evidence count
Evidence quality

Top subthemes

Verified quotes
```

不得出现：

> “X 导致推荐率下降”

除非有实验数据。

使用：

> “X 与当前下降同时显著增加，是优先调查机制之一。”

---

# 18.3 Who?

第三段：

> 哪些玩家群体受影响？

至少支持：

```text
playtime
language
recommendation
recent/new player proxy
high-playtime
Steam purchase
platform if reliable
```

展示差异，而不是单独展示人群总量。

例如：

```text
Technical Issue Rate

<10h     8.3%
10–50h  13.5%
50h+    27.1%
```

---

# 18.4 What Matters?

第四段：

> 应优先处理什么？

拆成四类：

### FIX

阻断性问题：

- crash
- launch
- severe bug
- save loss

### IMPROVE

体验摩擦：

- UI
- balance
- onboarding
- performance

### BUILD

玩家显式需求：

- feature request
- content request
- QoL request

### AMPLIFY

玩家已经喜欢、值得放大的：

- character
- mechanic
- boss
- soundtrack
- art
- narrative moment

这是 Community Growth 与产品改进真正连接的位置。

---

# 19. Priority Score 不允许成为黑箱

不要只输出：

```text
Priority = 82
```

至少显示组成因素。

建议：

```text
Prevalence
Severity
Trend
Affected Cohort Breadth
Evidence Confidence
```

第一版不用复杂机器学习。

建议展示 component score。

例如：

```text
Crash after patch

Prevalence      High
Severity        Critical
Trend           Rising
Breadth         Broad
Evidence        Strong

Priority        P0
```

如必须使用数值 score：

公式、权重必须进入 metric registry。

---

# 20. Metric Registry

新增：

```text
metric_registry
```

可以先作为 Python 定义或 JSON，而不必数据库表。

每个指标定义：

```text
metric_id
name
description

numerator
denominator

source_type

requires_llm
is_sampled

valid_for
invalid_when

formula_version
```

例如：

```text
technical_issue_rate

numerator:
validated classified reviews
with technical issue

denominator:
all validated classified reviews

source:
llm_derived

invalid_when:
classification coverage < threshold
```

---

# 21. Health Score 重构

如现有整体健康度无法解释：

必须弱化。

优先显示：

```text
Recommendation
Issue trend
High-severity issue trend
Player cohort deterioration
Classification coverage
```

如保留 Health Score：

必须显示：

```text
Experimental / Heuristic
```

并提供：

> How this score is calculated

禁止给用户产生“63 是客观游戏质量”的错觉。

---

# 22. Chat Agent 产品重构

Chat 的定位：

> Natural-language interface to verified player evidence.

不是：

> General AI assistant.

无游戏上下文时：

不要自动进入普通 LLM 聊天。

建议显示：

> Select a game or analysis run to ask questions about player feedback.

---

# 23. Chat 数据路径

首选：

```text
Question
↓
Intent
↓
Deterministic tool / SQL / FTS
↓
Structured evidence
↓
LLM synthesis
↓
Citation validation
↓
Answer
```

LLM 不负责：

- 算推荐率；
- 数评论；
- 猜分母；
- 自己回忆证据。

---

# 24. Quote Verification

这是 P0。

每一个引用必须包含：

```text
review_id
quote
start_offset / matching method
verified
```

验证方式：

第一优先：

exact normalized substring match。

如果找不到：

```text
verified = false
```

最终回答禁止继续保留引号。

可以改为：

> 玩家评论中存在关于 X 的描述。

但不能伪造成直接 quote。

---

# 25. Chat 输出格式

对于分析问题，标准答案：

```text
Finding
Evidence
Scope
Caveat
```

例如：

```text
Finding:
Performance complaints increased after the latest patch.

Evidence:
Technical/performance mention rate:
11.2% → 19.4%.

Main themes:
stutter, FPS drop, crash.

Scope:
817 valid classified reviews,
Aug 1–Aug 21.

Caveat:
The timing is consistent with the patch,
but review data alone cannot prove the patch caused the increase.
```

---

# 26. Chat 性能与成本

普通分析问题目标：

```text
0 LLM calls
```

如果纯 SQL 可以回答。

需要解释时目标：

```text
1 final synthesis call
```

复杂问题：

```text
≤ 3 logical tool rounds
```

现有最大 5 次可以保留作为 hard ceiling，但不应该成为正常路径。

必须监控：

```text
tool_calls_per_chat
llm_calls_per_chat
tokens_per_chat
cost_per_chat
chat_latency
```

---

# 27. Version Review 重构

Version Review 不允许：

```text
Before worse
After better
→ Version success
```

必须拆成：

```text
Observed Change
Possible Mechanisms
Evidence
Alternative Explanations
Additional Data Needed
```

---

# 28. 版本分析必须生成竞争假设

至少考虑五类机制：

### H1 Version effect

版本真正改变了体验。

需要验证：

对应 issue 是否在 post window 上升/下降；
玩家原文是否明确提及 update/patch。

### H2 Player-mix shift

折扣、新曝光导致新玩家进入。

需要：

playtime distribution；
new-player proxy；
purchase cohort。

### H3 Review-bomb / external controversy

需要：

评论量异常；
文本集中度；
off-topic flag；
外部事件。

### H4 Language/region mix shift

需要：

language distribution；
各语言内部变化。

### H5 Operational incident

服务器、平台、驱动或服务故障。

需要：

时间精度；
issue burst；
外部故障记录。

可继续加入：

- competitor launch；
- marketing campaign；
- seasonal sale；
- DLC release；
- influencer event。

最终不得把 aggregate movement 自动解释成 causal effect。

---

# 29. Action Layer

Insights 不应停在：

> 玩家不满 Performance。

每个重要发现生成 action candidates。

格式：

```text
Finding
Affected Users
Evidence Strength

Product Action
Community Action
Content/Marketing Action

Validation Metric
Validation Window
```

例如：

```text
Finding:
Players strongly praise Boss X's phase transition.

Product:
Preserve related encounter design pattern.

Community:
UGC campaign around first Phase 2 reactions.

Content:
Short-form highlight content.

Validate:
Topic mention volume,
engagement,
positive sentiment,
UGC participation.
```

Action 必须标记：

```text
Suggested
```

不能冒充确定性结论。

---

# 30. Evidence Confidence

不要简单等同于 LLM confidence。

Evidence Confidence 可由确定性因素构成：

```text
sample size
classification coverage
number of distinct reviews
number of distinct players
cross-cohort consistency
quote verification
trend persistence
```

输出：

```text
Strong
Moderate
Weak
```

并可查看为什么。

---

# 31. Helpfulness 的使用限制

Steam helpful vote 不应默认作为：

> 代表性权重。

可以作为：

> Evidence discoverability / readability signal.

即：

高 helpful 评论可以优先用于选“容易展示的证据”，但不能让 helpfulness 直接放大问题 prevalence。

---

# 32. 性能预算

建立 reference benchmark。

Reference machine：

```text
4+ CPU cores
16 GB RAM
SSD
local SQLite
```

数据规模：

```text
20k reviews/game — normal
100k reviews/game — stress
500k cross-game rows — future scale
```

目标：

### Cached dashboard

后端核心聚合接口：

```text
p95 < 500 ms
```

### FTS search

100k reviews：

```text
p95 < 250 ms
```

### Cached analysis

数据未变化：

```text
0 classification calls
0 enrichment calls
```

目标：

几秒级完成 freshness check，而不是重新分析。

### Incremental analysis

只处理新增/更新评论。

### Memory

正常单游戏分析应避免复制多个全量 DataFrame。

---

# 33. Pandas 优化原则

目前不要为了性能主动迁移 Polars。

先 profiling。

必须先找到：

```text
SQL
network
LLM
Pandas
serialization
frontend
```

哪个是真正瓶颈。

如果数据分析 CPU/内存确实成为瓶颈，再实验 Polars Lazy API。

Polars 的 lazy execution 支持 predicate/projection pushdown，并可通过 streaming 降低内存压力。

迁移条件：

```text
Pandas processing > 20% run time
OR
peak RAM unacceptable
OR
cross-game analysis > ~500k rows
```

否则不换。

---

# 34. DuckDB 使用条件

SQLite 继续负责：

- transactional state；
- reviews；
- labels；
- FTS；
- settings；
- runs。

如果未来出现：

```text
百万级历史分析
大量 cross-game aggregation
Parquet archive
```

再评估 DuckDB。

DuckDB 特别适合较大的 OLAP、Parquet filtering 和 aggregation，但并不是为了大量小型并发事务查询设计。

不要现在替换 SQLite。

---

# 35. Materialized Analysis Snapshot

Dashboard 不应该每次打开重新对所有 reviews 做完整 Pandas pipeline。

每一个 completed run 生成：

```text
metric_snapshot
cohort_snapshot
topic_snapshot
trend_snapshot
priority_snapshot
```

Dashboard 默认读取 snapshot。

只有：

- 新 Run；
- filter drill-down；
- ad-hoc Chat query

才做实时计算。

---

# 36. API Payload 控制

禁止 `/analysis/{app_id}` 默认返回大量 review sample。

拆分：

```text
GET /runs/{run_id}/summary
GET /runs/{run_id}/metrics
GET /runs/{run_id}/cohorts
GET /runs/{run_id}/priorities

GET /reviews?...pagination
GET /evidence?...pagination
```

避免：

```text
一个巨大 JSON
→ Next.js
→ 前端再计算
```

---

# 37. Frontend 原则

前端：

> render results

而不是：

> redefine analytics.

所有正式指标必须后端计算。

前端只能：

- filter UI；
- sort；
- presentation；
- visualization；
- local interaction。

禁止前端从 1000 review sample 再算一个看起来像正式 KPI 的指标。

---

# 38. 数据库迁移

引入 Alembic。

Alembic 是 SQLAlchemy 官方生态中的轻量数据库 migration 工具。

必须能够：

```text
upgrade
downgrade
```

数据库初始化不再仅依赖：

```text
CREATE TABLE IF NOT EXISTS
```

首次 migration 包含：

- run schema；
- provenance；
- FTS migration；
- indexes。

迁移前自动 backup local DB。

---

# 39. 建议索引

根据实际 SQL profiling 决定最终方案。

至少检查：

```text
reviews(app_id, timestamp_created)

reviews(app_id, language, timestamp_created)

review_labels(app_id, recommendation_id)

analysis_runs(app_id, created_at)

chat_messages(session_id, created_at)
```

不允许盲目建大量 index。

每个 index 必须对应真实 query。

---

# 40. 后台任务可靠性

Phase 1：

保留当前执行方式，但引入 durable run state。

服务器启动：

```text
scan runs
status in running states
↓
mark interrupted
OR
resume supported stage
```

任何任务必须有：

```text
run_id
```

不能只靠：

```text
app_id
```

作为任务身份。

---

# 41. Cancellation

取消：

```text
running
→ cancelling
→ cancelled
```

分类 batch 之间检查 cancellation flag。

禁止：

用户点击 cancel 后后台继续大量消耗 token。

---

# 42. Retry

区分：

### Network retry

可以指数退避。

### Provider 429

尊重 retry-after。

### JSON/schema failure

少量 retry。

### Permanent invalid request

不 retry。

### Auth error

立即失败。

### Budget exceeded

立即暂停/失败。

每种错误必须有 error_code。

---

# 43. LLM Cost Ledger

新增：

`llm_calls`

字段：

```text
call_id
run_id

feature
provider
model

prompt_version

input_tokens
output_tokens
cached_tokens

estimated_cost

latency_ms

status
retry_count
error_type

created_at
```

Feature：

```text
classification
enrichment
health_summary
chat
comparison
report
translation
```

---

# 44. 成本 Dashboard

Settings / Diagnostics 增加：

```text
Today's Spend
Last 7 Days
Last 30 Days

Spend by Feature
Spend by Model
Tokens by Feature

Cache Hit Rate

Cost / Analysis Run
Cost / 1k Reviews
Cost / Chat Answer
```

不要求账单级绝对精确。

但必须能比较优化前后。

---

# 45. 成本 Guardrail

支持：

```text
soft_daily_budget
hard_daily_budget

max_run_budget
```

启动分析前估算：

```text
uncached reviews
× estimated tokens
× model price
```

显示：

> Estimated cost range

用户可继续或切换模型。

本地 Ollama：

cost 可显示：

```text
API cost = 0
```

但仍跟踪：

latency / token volume。

---

# 46. Analysis Cost SLO

至少记录以下趋势：

```text
classification cache hit > 95%
```

针对重复分析。

未改变数据重复运行：

```text
classification cost = 0
```

健康总结：

只有：

```text
analysis fingerprint changed
```

才重新生成。

Evidence enrichment：

使用动态上限。

例如：

```text
min(
  configured limit,
  number required for coverage
)
```

而不是无条件固定跑满。

---

# 47. Performance Instrumentation

每个 Run 记录阶段耗时：

```text
ingestion_ms
db_write_ms
classification_ms
enrichment_ms
aggregation_ms
summary_ms
persistence_ms
```

前端可以在 Diagnostics 查看。

优化只允许基于 profiling。

禁止：

> “看起来 Pandas 比较慢，所以换 Polars。”

---

# 48. Data Quality Checks

每次正式 analysis 前后运行轻量检查。

Pre-analysis：

```text
review IDs unique
timestamps valid
required fields present
```

Post-analysis：

```text
classified <= valid reviews
enriched <= classified
fallback tracked
FTS integrity
snapshot run_id match
```

任何 hard invariant 失败：

不允许把 Run 标记 completed。

---

# 49. CI 必须新增

现有测试全部通过并不足够。

CI：

```text
python compileall
backend tests
frontend typecheck
frontend eslint
benchmark smoke test
migration test
FTS integrity test
mock E2E
desktop build smoke test
```

`evaluate_labeling.py` 一类语法错误必须在 compile stage 被发现。

---

# 50. LLM Benchmark CI

普通 PR：

跑小 benchmark：

```text
30–50 samples
```

涉及：

```text
prompt
taxonomy
provider
parser
classification
```

时：

跑完整 Golden Set。

输出 comparison artifact：

```text
baseline
candidate
delta
```

---

# 51. Desktop Build

Tauri 官方支持将 PyInstaller 等 Python 可执行程序作为 sidecar 打包。

CI 至少验证：

```text
build frontend
build Python sidecar
start sidecar
GET /health
shutdown
process exits
```

删除 stale hidden imports。

sidecar 权限和 binary path 必须与 Tauri v2 configuration 一致。

---

# 52. 安全边界

Local desktop：

默认：

```text
127.0.0.1
```

不能：

```text
0.0.0.0
```

除非显式配置。

API Key：

日志中绝不输出。

设置接口：

只返回：

```text
configured: true/false
masked key
```

不返回完整 key。

Docker：

默认文档明确：

> Do not expose directly to public internet.

认证系统不是当前 P0。

---

# 53. 页面信息架构建议

主导航可保持现有页面，避免高成本重写。

但 Dashboard 内部统一五问。

建议：

```text
Overview
  ├─ What Changed
  ├─ Why
  ├─ Who
  ├─ Priority
  └─ Actions

Reviews
Evidence

Version Review

Ask Data

Reports

Settings
```

Chat 可更名：

> Ask Data

强化其分析属性。

---

# 54. 报告结构

正式报告默认：

```text
1 Executive Summary
2 Data Scope
3 What Changed
4 Key Drivers
5 Affected Player Cohorts
6 Priority Issues
7 Growth Opportunities
8 Recommended Actions
9 Version / Trend Context
10 Evidence Appendix
11 Methodology & Limitations
```

报告必须显示：

```text
run_id
date
scope
review count
classification coverage
model
taxonomy
prompt version
```

---

# 55. 产品用语规范

禁止：

> 玩家认为……

当只有部分 Steam reviewer 数据时。

优先：

> 在本次 Steam 评论样本中……

禁止：

> 版本导致……

优先：

> 版本后观察到……

禁止：

> 玩家最重要的问题……

如果只是 mention count。

优先：

> 当前最高频反馈之一……

禁止：

> Representative Reviews

除非真的做 representative sampling。

优先：

> Selected Evidence

---

# 56. 分析局限必须成为产品功能

Analysis Scope 面板至少显示：

```text
Source:
Steam Reviews

Window:
...

Languages:
...

Reviews collected:
...

Valid classified:
...

Evidence enriched:
...

Known limitations:
Steam reviewers are self-selected.
Review data does not represent all players.
Aggregate changes do not establish causality.
```

这不是免责声明装饰。

这是产品可信度的一部分。

---

# 57. P0 执行阶段：可信度修复

Codex 第一阶段只完成以下任务。

## P0.1 FTS

- 修复重复；
- external-content；
- triggers；
- rebuild；
- tests。

Definition of Done：

```text
duplicate review IDs = 0
```

---

## P0.2 Analysis Run

实现 immutable `analysis_runs`。

Definition of Done：

任意结果可以知道：

```text
when
what data
what model
what prompt
what taxonomy
```

---

## P0.3 Provenance

区分：

```text
population
classified population
priority evidence
fallback
```

Definition of Done：

前端任一 LLM KPI 都知道 denominator 和 classification coverage。

---

## P0.4 Evidence Verification

所有 Chat / Evidence quote 必须验证。

Definition of Done：

系统不能显示数据库中不存在的直接引语。

---

## P0.5 Golden Set

至少完成：

```text
annotation guideline
initial dataset
evaluation script
baseline report
```

---

## P0.6 Cost Ledger

记录所有 LLM call token / cost / latency。

---

# 58. P1：产品价值升级

完成：

### Five-question Dashboard

What / Why / Who / Priority / Action。

### Priority framework

FIX / IMPROVE / BUILD / AMPLIFY。

### Version Review

竞争假设 + falsification requirements。

### Incremental ingestion

避免重复抓取。

### Incremental classification

只分类新增/变更。

### Cost dashboard

展示 cost per run / 1k reviews。

### Durable task state

支持 interrupted run reconciliation。

---

# 59. P2：性能与分析增强

只有 P0/P1 稳定后：

- emerging topics；
- Polars benchmark；
- materialized cross-game metrics；
- representative stratified evidence；
- model routing；
- automated model comparison；
- Huey persistent queue。

---

# 60. P3：规模触发后才做

达到实际需求后：

- PostgreSQL；
- Redis；
- worker cluster；
- multi-user；
- authentication；
- multi-source ingestion；
- vector retrieval；
- SetFit production classifier；
- DuckDB/Parquet analytical archive。

---

# 61. Codex 执行规则

Codex 必须：

## Rule 1

修改之前读取相关代码与测试。

不要仅根据本文件假设当前实现。

---

## Rule 2

发现本文件与源码不一致：

以源码为 observed fact。

在：

```text
IMPLEMENTATION_NOTES.md
```

记录偏差。

---

## Rule 3

先写 failing test，再修关键数据一致性问题。

特别：

```text
FTS
run state
fallback
citation
incremental cache
```

---

## Rule 4

不进行 unrelated refactor。

一个任务只解决一个明确问题。

---

## Rule 5

不一次性替换核心技术。

例如：

禁止：

```text
Pandas → Polars
BackgroundTasks → Celery
SQLite → PostgreSQL
custom provider → LiteLLM
```

除非先有 benchmark 和 ADR。

---

## Rule 6

所有 schema 修改必须 migration。

---

## Rule 7

所有新的业务指标必须进入 metric registry。

---

## Rule 8

所有新的 LLM 调用必须：

```text
feature-tagged
token-tracked
cost-tracked
versioned
```

---

## Rule 9

所有新的 AI 输出必须回答：

> 如果模型错了，用户怎么知道？

---

## Rule 10

所有性能优化必须回答：

> profiling 证明瓶颈在哪里？

---

# 62. 每阶段 Codex 输出格式

每个 Phase 完成以后生成：

```text
CHANGELOG_PHASE_X.md
```

包含：

```text
Implemented

Files Changed

Schema Changes

API Changes

Tests Added

Performance Before / After

LLM Cost Before / After

Known Risks

Remaining Work
```

---

# 63. Benchmark Fixtures

增加固定 fixture：

### Dataset Small

100 reviews。

CI 快速测试。

### Dataset Medium

10,000 reviews。

性能测试。

### Dataset Large

100,000 reviews。

stress benchmark，不必每个 PR 运行。

---

# 64. 关键验收场景

## Scenario A：重复分析

第一次：

10,000 reviews。

第二次：

数据无变化。

预期：

```text
Steam minimal freshness fetch
classification calls = 0
enrichment calls = 0
cached metrics reused
```

---

## Scenario B：增量

10,000 历史。

新增：

100 reviews。

预期：

只分类约 100 条。

---

## Scenario C：评论编辑

已有 review 文本发生改变。

预期：

```text
review_hash changes
label cache invalidated
FTS updated
only that review reclassified
```

---

## Scenario D：Prompt 修改

Prompt version：

v1 → v2。

预期：

旧 labels 不可作为 v2 的 validated cache。

旧 Run 保留。

---

## Scenario E：LLM Provider 失败

20% batch failure。

预期：

```text
valid classification coverage visible
fallback tracked
formal KPI denominator excludes invalid fallback
```

---

## Scenario F：伪引用

模型生成数据库不存在的 quote。

预期：

quote verifier 拦截。

---

## Scenario G：版本后推荐率下降

预期：

系统报告：

```text
Observed change
+
candidate mechanisms
+
supporting evidence
+
alternative explanations
+
additional data needed
```

不能自动输出：

> 更新失败。

---

# 65. 最终产品质量标准

优化完成后的 SentiNext 不应被描述为：

> AI Steam Review Analyzer

而应该被描述为：

> A local-first player voice intelligence system that converts Steam review data into reproducible, evidence-backed product and community insights.

它最核心的差异化不是：

-用了多少模型；
- 有多少图；
- 有 Agent；
- 有桌面应用。

而是：

> 每一个重要业务判断都有明确的数据范围、指标口径、模型来源、原始玩家证据与不确定性边界。

---

# 66. 最终系统必须证明的能力

最终作品集应能展示：

### Data Engineering

增量采集、去重、缓存、FTS、migration、data contract。

### Analytics

趋势、cohort、rate、change、priority、版本分析。

### User Research

从非结构化反馈形成 taxonomy、issue、request 和 evidence。

### AI Engineering

structured extraction、eval、golden set、prompt version、citation verification。

### Product Thinking

从：

```text
feedback
```

走到：

```text
decision
```

### Community / Growth

识别：

```text
AMPLIFY opportunities
```

并转化为：

内容、社区、传播动作。

### Engineering Judgment

证明：

> 知道什么时候应该引入复杂系统，也知道什么时候不应该。

---

# 67. 第一轮 Codex 指令

Codex 首轮不要立即改完整项目。

第一轮任务：

```text
1. Audit the repository against PRODUCT_OPTIMIZATION_SPEC.md.

2. For every P0 requirement, classify:
   - already implemented
   - partially implemented
   - missing
   - implemented differently

3. Verify all claims directly against source code.

4. Identify existing tests covering each requirement.

5. Produce:
   P0_IMPLEMENTATION_PLAN.md

6. The plan must include:
   - exact files to modify
   - database migration changes
   - API compatibility impact
   - test cases
   - performance risks
   - LLM cost impact
   - migration/rollback strategy

7. Do not modify application code during this audit pass.

8. After the audit, rank implementation work in dependency order.

9. Prefer minimal compatible changes over rewrites.

10. Flag any recommendation in PRODUCT_OPTIMIZATION_SPEC.md
    that would create unnecessary complexity given the real codebase.
```

首轮完成后，再让 Codex 开始 P0.1。

不要一次要求它：

> “按照文档全部优化。”

---

# 68. 推荐实施顺序

```text
Audit
↓
FTS Integrity
↓
Analysis Run / Provenance
↓
Label Provenance
↓
Evidence Verification
↓
Golden Set
↓
LLM Cost Ledger
↓
Incremental Ingestion
↓
Incremental Classification
↓
Five-question Dashboard
↓
Priority Framework
↓
Version Review Methodology
↓
Performance Profiling
↓
Optional Architecture Upgrades
```

该顺序不得因为“某项开发简单”而随意调换。

核心依赖关系是：

```text
Data trustworthy
↓
AI trustworthy
↓
Metrics trustworthy
↓
Decision layer
↓
Performance optimization
↓
Scale
```

---

# 69. 最终 Definition of Done

项目达到本轮优化目标，至少满足：

```text
FTS duplicates = 0

Every completed analysis has immutable run_id

Every LLM-derived metric exposes valid denominator

Fallback results are identifiable

Every evidence quote is verified

Golden Set benchmark exists

Prompt/model changes are evaluable

Repeated unchanged analysis makes zero classification calls

Incremental analysis only processes changed reviews

LLM cost per run is measurable

Dashboard answers all five business questions

Version Review does not automatically claim causality

Formal metrics are backend-derived

Core reports expose data scope and limitations

Desktop build has automated smoke test
```

只有以上事项完成，才进入“增加 Reddit / Discord / 多源社区信号”等下一阶段。