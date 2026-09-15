# STRA V2 Version Comparison V3

本文定义两个版本之间的四窗口比较契约。V3 的目标不是再创建一套爬虫或 Research Core，而是把现有 `SamplingContract`、Acquisition Service、确定性统计和 LLM label cache 串成一条可审计的版本分析链。

## 1. 核心问题

版本比较需要回答三层问题：

1. 两个版本各自上线前后，玩家反馈发生了什么变化；
2. 新版本相对于自己的上线前基线，是否比旧版本相对于自己的基线表现更好；
3. 主题、问题、需求的差异是否来自可比的语义样本，而不是两个时期语言/时间构成不同。

V3 不把 LLM 用于采集、窗口构造、推荐率、评论量、置信区间、可比性、标准化或窗口敏感性计算。LLM 只负责统一 taxonomy 下的语义标签。

## 2. 四个 population

A 始终为时间较早的版本，B 始终为时间较新的版本：

```text
A_PRE  ── A ── A_POST
B_PRE  ── B ── B_POST
```

主指标：

```text
ΔA  = A_POST - A_PRE
ΔB  = B_POST - B_PRE
Post gap = B_POST - A_POST
ΔΔ = ΔB - ΔA
```

`ΔΔ` 只作为描述性 difference-in-differences，不作为因果估计。

## 3. 时间边界

### 有精确 effective_at

```text
PRE  = [T-W, T)
POST = [T, T+W)
```

### 只有日期

版本当天不进入 primary estimator：

```text
PRE       = 前 W 个完整自然日
EVENT DAY = 排除
POST      = 后 W 个完整自然日
```

这样避免一个自然日同时混入更新前和更新后评论。

主窗口可选 `3 / 7 / 14` 天。执行时至少采集 14 天范围，因此同一次 run 可以同时计算 3/7/14 日 raw sensitivity。

## 4. Acquisition Contract

每个 cohort 都生成独立 `SamplingContract`：

```text
A_PRE  -> SamplingContract
A_POST -> SamplingContract
B_PRE  -> SamplingContract
B_POST -> SamplingContract
```

四个 contract 共用已有 Acquisition Service：

```text
local coverage / SQLite
        ↓
coverage compatible -> reuse
        ↓ otherwise
Steam targeted historical fetch / cursor fallback
        ↓
review_id upsert
```

V3 不新增独立版本爬虫。

原始评论上限是 **per cohort**，UI 明确标注。当前默认 2,000 / cohort，可选：

```text
500 / 1,000 / 2,000 / 5,000 / 10,000
```

达到上限时必须显示 PARTIAL coverage，不能把 bounded sample 伪装成完整 population。

## 5. Raw-only 模式

`analysis_mode=raw_only` 时：

- 不 import LLM provider；
- 不创建 semantic sample；
- 不调用 `ensure_review_labels`；
- 仍计算全部确定性指标。

包括：

- 四组评论量；
- 推荐率；
- Wilson 95% CI；
- ΔA / ΔB / Post gap / ΔΔ；
- population comparability；
- language standardization sensitivity；
- language + playtime sensitivity；
- 3/7/14 日窗口敏感性；
- 窗口内其他版本/事故/价格事件提示。

## 6. Semantic Sample：共同目标分布 + 分层确定性抽样

Semantic sampling 与 Acquisition sampling 是不同层。

V3 使用：

```text
pooled common support
× language
× relative lifecycle day
```

相对日 bucket：

```text
D1
D2
D3-4
D5-7
D8-14
D15+
```

### 共同支持

只有四组都存在的 `language × relative_day_bucket` strata 才进入主语义比较。

### 共同 target distribution

目标权重来自四组在 common support 上的 pooled composition。

### 相同 quota

同一 stratum 对四个 cohort 使用完全相同的 quota，因此最终四组样本数相同。

### 确定性选择

stratum 内按：

```text
SHA256(seed | stratum | review_id)
```

排序取前 N 条。

同一 input + seed 会得到同一 SemanticSampleManifest。

## 7. 明确不平衡 voted_up

`voted_up` 是版本表现的重要 outcome，不能强制成 50/50。

因此 V3 的 balancing dimensions 只有：

```text
language
relative_day_bucket
```

Manifest 明确记录：

```text
outcome_balanced = false
```

playtime、Steam purchase、free copy、early access、Steam Deck 等变量保留用于 composition diagnostics / sensitivity，而不是默认硬匹配。

## 8. SemanticSampleManifest

每次 semantic run 持久化：

- sampling method；
- deterministic seed；
- total budget；
- target_per_cohort；
- common support strata；
- target distribution；
- per-stratum quotas；
- 四组实际 selected review IDs；
- balancing dimensions；
- outcome_balanced=false。

后续主题比较只能使用 Manifest 中这些 review IDs，不能再次 `[:semantic_limit]` 另取一批评论。

## 9. Cohort-blind LLM

分类模型只接收评论内容和统一 game context/taxonomy，不收到 `A_PRE/A_POST/B_PRE/B_POST` 身份。

四组必须共享：

- taxonomy version；
- classifier prompt version；
- model/provider；
- preprocessing；
- JSON schema。

LLM 只生成 labels；所有 A/B 差异由确定性 Python 聚合。

## 10. Topic comparison

对于每个 topic：

```text
topic ΔA  = rate(A_POST) - rate(A_PRE)
topic ΔB  = rate(B_POST) - rate(B_PRE)
topic ΔΔ  = topic ΔB - topic ΔA
```

问题、需求、正向主题分别展示。

## 11. Confounder watch

在两个版本相关窗口内扫描已有 event catalog。

当前等级：

- `clean`
- `minor`
- `major`

major 示例：major patch、season、expansion、pricing、outage、controversy。

该提示不自动阻止分析，但报告必须显式显示。

## 12. API

### 计划，不调用 LLM

```http
POST /version-comparison/plan
```

### 启动

```http
POST /version-comparison/start
```

请求示例：

```json
{
  "app_id": 123,
  "event_a_id": "...",
  "event_b_id": "...",
  "window_days": 7,
  "languages": ["all"],
  "max_reviews_per_cohort": 2000,
  "analysis_mode": "semantic",
  "semantic_budget": 4000
}
```

### 查询 run

```http
GET /version-comparison/runs/{run_id}
GET /version-comparison/runs?app_id=123
```

## 13. UI

新 workspace：

```text
/version-comparison
```

界面遵循现有报告和 Game Compare 的视觉语言：

- 游戏 + A/B 版本选择；
- 四 cohort 方案预览；
- raw-only / semantic 显式选择；
- 四组推荐率卡；
- ΔA / ΔB / Post gap / ΔΔ 指标卡；
- 3/7/14 日 robustness；
- comparability；
- confounder watch；
- SemanticSampleManifest；
- 问题 / 需求 / 正向主题对比表。

旧 `/version-review` 与旧 `/runs` API 保留，用于已有历史 run 和兼容性，不在本轮删除。
