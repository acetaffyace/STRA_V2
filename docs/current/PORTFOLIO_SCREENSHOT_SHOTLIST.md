# 作品集视觉清单

## 产品截图（7 张）

1. Dashboard 顶部：游戏名、1000 条评论、离线来源。
2. Run / 来源信息：Run ID、mode、source、样本、窗口。
3. 五问决策摘要：无基线提示、当前快照、行动卡。
4. What Matters：FIX/IMPROVE/BUILD/AMPLIFY、理由、不确定性、验证计划。
5. Evidence：匹配数、分页、已验证玩家原话。
6. Chat：中文问题“当前评论中玩家最常提到哪些问题？请给我原始证据。”、verified citations、tool calls = 0。
7. Reports：当前分析摘要与 PDF 窗口配置并列，但语义分开。

## 两张非 UI 视觉

### A. Trust architecture diagram

```text
Steam Reviews
      ↓
Analysis Run
      ↓
LLM / Offline Classification
      ↓
Label Provenance
      ↓
Metric Provenance
      ↓
Five Questions
      ↓
Priority / Action

Evidence ─────────→ Verified source quote
Run ──────────────→ Immutable result
Provider call ────→ Cost ledger
```

### B. Model evaluation / quality boundary

```text
150 human-verified Golden Set
            ↓
     Frozen Dev / Holdout
            ↓
   Historical DeepSeek baseline
            ↓
Issue detection: relatively strong
Fine-grained taxonomy: precision ≈ 0.24
                         recall ≈ 0.67–0.70
            ↓
Product rule:
Use labels for discovery;
require evidence for decisions.
```

截图和图示都要标注：`codex_offline_fixture` 不等于 human Gold、provider output 或 model-quality benchmark。避免展示 API key、Provider 配置和 debug 日志。
