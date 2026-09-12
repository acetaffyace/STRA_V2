# Dynamic Batch Planner V2 Hardening

本阶段按 Hardening 范围完成，未修改 prompt、taxonomy、topic 策略、model routing、cache 或 lane 参数。

## Infrastructure complete

- Dynamic batch 返回统一经过 `validate_batch_results()`；有效结果立即保存，只有 `retry_ids` 进入后续 retry，unexpected ID 不落库并记录 warning。
- retry 语义固定为 `attempt_number=0` 初始请求，`max_retry_attempts=2` 时最多再执行 retry 1、retry 2。
- lexical 短评论不再因少于两个词被强制标成 `other/general`；`short_text`、字符数和词数仍保留用于统计与 planning。
- high-confidence `punctuation_or_symbol`、`emoji_only`、`drawing_only` 默认本地 skip，保护 `10/10`、`GG`、`W`、`L` 等 lexical 例外；fallback 明确标记为 `nonlexical_skip` / `rule_fallback` / `validated=false`。
- `32000` 是动态 batch 的当前工程安全上限，约束 `review_text_for_model` 的总字符数；不是完整 prompt 长度，也不是 token/context 硬限制。oversized 单条 review 保持独立 batch 并进入 telemetry。
- Dynamic batch 默认仍关闭；provider failure 不触发 structural split，structural failure 仍只允许受 retry ceiling 与 min split size 约束的二分。
- 每次 dynamic API 调用 telemetry 包含 batch、lane、字符量、attempt、split、valid/invalid/missing、success、error type、latency，并增加 `max_total_chars`、`char_fill_ratio`、`oversized_input`。

## Real database read-only dry-run

数据库：`D:\reviews\SentiNext\source\data\sentinext.db`。本次只读，没有调用 LLM，也没有修改生产数据库。

| app_id | total | empty | pure skip | short lexical preserved | representatives | planned batches | avg reviews/batch | avg chars/batch | max chars | avg fill ratio | SHORT/MEDIUM/LONG/VERY_LONG batches |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1172470 | 7669 | 28 | 175 | 4858 | 6015 | 73 | 82.40 | 7162.25 | 31400 | 0.2238 | 48 / 13 / 7 / 5 |
| 2584270 | 1000 | 6 | 11 | 249 | 969 | 24 | 40.38 | 18161.50 | 31442 | 0.5675 | 5 / 4 / 6 / 9 |
| 2868840 | 2000 | 7 | 22 | 1047 | 1802 | 24 | 75.08 | 8444.00 | 25181 | 0.2639 | 13 / 5 / 4 / 2 |
| 4162040 | 1000 | 4 | 21 | 432 | 938 | 15 | 62.53 | 9767.33 | 31531 | 0.3052 | 7 / 3 / 3 / 2 |

`planned_batch_count` 是理论 planning 指标。它不等于已验证的 API 成本下降；本 dry-run 也没有声称成本已下降。

## Optimization not yet proven

仍需第三阶段真实 API A/B 实验确认：

- 32k 是否为最优安全预算；
- strict lane 参数是否优于旧 batch；
- 实际 input/output token、失败率、retry 率、latency 和成本是否改善。

## Verification

全量测试：`.venv311\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp`

结果：全部通过；仅保留项目既有 Pydantic deprecation warnings。
