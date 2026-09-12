# V1/P1 UX 第二轮复核（中文）

复核对象：NINJA GAIDEN 4，离线开发 Fixture，1000 条评论，Run `offline-db4b5a9593e6421ca1ddff2318c6aa4d`。

## 结论

核心 BLOCKER/HIGH 已关闭，建议 `V1_P1_PORTFOLIO_DEMO_READY = GO`。本轮没有启动 P2/P3，也没有调用 Provider。

## 复核证据

| 路径 | 结果 |
|---|---|
| Dashboard 首屏 | PASS：显示游戏、1000 条样本、离线来源、Run/来源入口、五问摘要与当前快照 |
| 最近变化 | PASS：无基线时明确显示“不可用：没有可比较基线”，不伪造变化 |
| Why / What matters | PASS：展示“内容与设计 / 一般反馈”等中文 taxonomy、行动类别、理由、不确定性和验证计划 |
| Evidence | PASS：`technical/bugs` 返回 33 条匹配评论、分页 7 页、首屏 5 条已验证原话；修复 `_json_elem` bind 名称冲突 |
| Chat | PASS：离线 Fixture 返回确定性答案、原始评论引用、`verification_status=verified`、`tool_calls_made=0` |
| Reports | PASS：先展示当前分析摘要，再提供月度窗口 PDF 导出，不再只有导出配置 |
| legacy `/analysis/{app_id}` | PASS：旧 metadata 缺少 `fetched_at` 时保持 null，不制造时间 |

## 本轮修复

1. 兼容历史 metadata：`fetched_at` 可为空，`mode/source/run_id` 显式补齐。
2. 修复 SQLite JSON 数组查询中把 `:subcategory_pattern` 误替换为 `_json_elem` 的问题。
3. Evidence endpoint 从 canonical review label payload 读取原话，并在返回前做 source-slice verification。
4. Offline Chat 在 `codex_offline_fixture` 下绕过 Provider，保留 deterministic evidence-first 语义。
5. Dashboard 统一显示中文 taxonomy、样本分母、分类覆盖率与 Run 来源。
6. 当前快照与无基线状态分开呈现，避免把单窗口观察包装为趋势结论。

## 遗留低优先级项

- 少量第三方/历史组件仍有英文辅助标签（例如部分趋势图轴标签和 Steam 上下文卡片）。不影响核心决策路径，但可作为后续中文化清扫项。
- ESLint 仅有既存 warning：图片优化和一个 Hook 依赖提示；无 error。
- Steam 评论是自选择样本，cohort 仅能称为“观察到的评论群体”，不能解释为完整玩家画像。

## 复核判定

核心决策路径无 BLOCKER/HIGH。允许进入作品集发布；明确停止在 V1/P1，不启动 P2/P3。
