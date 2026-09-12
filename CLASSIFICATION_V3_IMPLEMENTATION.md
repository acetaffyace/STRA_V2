# SentiNext Classification V3

## 1. 修改文件

- `apps/api/senti_next/llm.py`
- `tools/inspect_classifier_prompt_v3.py`
- `tests/fixtures/classifier_v3_reviews.json`
- `tests/unit/test_classifier_v3.py`

未修改 taxonomy keys、topic 策略、model/provider、lane、32k safety budget、retry、ReviewPreprocessor、duplicate reuse 或 Agent。

## 2. Prompt variant

环境变量：`SENTINEXT_CLASSIFIER_PROMPT_VARIANT`

- `legacy`：默认值，继续使用 `_BATCH_PROMPT_TEMPLATE_LEGACY`。
- `v3`：使用 `_BATCH_PROMPT_TEMPLATE_V3`，版本为 `steam_review_classifier_v3_compact`。

完整 V3 batch prompt 位于 `apps/api/senti_next/llm.py` 的 `_BATCH_PROMPT_TEMPLATE_V3`，包含：

- 仅基础 labels 的 JSON 输出 schema；
- 1–6 unique labels、primary first、sparsity；
- issue/request subset 与语义定义；
- technical boundary、controls、controller support、multiplayer/matchmaking、patch/update、pricing/DLC/value 边界；
- other/general 与 meme coexistence；
- 原 taxonomy 原样保留。

## 3. V3 输入字段

每条 review 仅发送：

```text
[review_id=<id>]
<<<BEGIN REVIEW>>>
<review_text>
<<<END REVIEW>>>
```

V3 不发送：`type`、`genres`、`categories`、`description`、`language`、`playtime`、`recommendation`。这些字段仍保留在原始 review 数据中。

V3 不发送 game name，因此 V3 identity 也不包含 game name。

## 4. Cache identity

V3 `classification_input_hash` 由实际 batch 分类输入组成：

```json
{
  "schema_version": "review-classification-schema-v1",
  "mode": "batch",
  "review_text": "...",
  "preprocessor_version": "...",
  "prompt_variant": "v3"
}
```

V3 不受 language、playtime、voted_up 或 game metadata 变化影响；review text 变化会产生新 hash。Legacy identity 保留原 metadata 组成，并与 V3 的 prompt version/hash 明确隔离。

## 5. Legacy vs V3 prompt chars

使用 `tools/inspect_classifier_prompt_v3.py`、12 条固定 fixture、同一 review text 测量，未调用 API：

| scope | legacy rendered | V3 rendered | reduction |
|---|---:|---:|---:|
| 12-review fixture | 6418 | 4992 | 22.71% |
| SHORT one-review sample | 3781 | 3554 | 6.00% |
| MEDIUM one-review sample | 3862 | 3635 | 5.88% |
| LONG one-review sample | 4160 | 3933 | 5.46% |
| VERY_LONG one-review sample | 5165 | 4938 | 4.39% |

这是字符与固定开销下降，不代表已实现 token 或 API 成本下降。

## 6. Enrichment

`SENTINEXT_ASPECT_ENRICH_LIMIT` 默认值已从 `50` 改为 `0`。因此默认流程是 first-pass classification → persist labels → end。`classify_review_single()` 与 enrichment 能力保留，未来仍可按需调用。

## 7. Tests

- V3 prompt snapshot：metadata omission、taxonomy/rules、中文/英文/葡萄牙语原样保留。
- V3 cache identity：metadata 不影响 hash，review text 变化影响 hash。
- Legacy prompt 默认兼容。
- 全量 pytest：通过。

## 8. 尚未验证

尚未通过真实 API A/B 验证 primary topic accuracy、多标签准确率、issue precision/recall、request precision/recall、input/output tokens、API cost、failure/retry rate、latency、32k 最优性或 strict lane 最优性。
