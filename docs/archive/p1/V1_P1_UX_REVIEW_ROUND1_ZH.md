# SentiNext V1/P1 第一轮真实产品体验审查

## 审查范围

本轮使用本地真实页面和 NINJA GAIDEN 4 Run 进行结构性 UX Review，实际检查了：

- 首页 / 游戏选择
- Dashboard 第一屏
- Five Questions 区域
- 问题卡到证据的点击路径
- 分析报告入口
- 智能问答 Chat
- 后端数据读取和页面错误日志

本轮没有修改产品逻辑，只记录真实体验问题。

## 总体判断

产品的视觉骨架已经有了：游戏上下文、Five Questions、指标、问题/需求、分群、版本更新都能看到，中文导航也基本完整。

但当前还不能称为“决策闭环产品”，因为关键链路存在断裂：

1. 首页能显示指标，但不能快速告诉用户当前最重要的玩家信号。
2. 问题卡可以点击，但点击后没有对应评论证据。
3. Chat 可以发起问题，但真实请求最后显示通用错误。
4. Dashboard 和报告页显示的样本量不一致。
5. `/analysis/2627260` 的 metadata 校验错误会阻断新鲜结果读取。

建议当前 UX 状态：**NO-GO for portfolio/demo polish；先修 P0 UX 闭环。**

## P0 UX 问题

### P0-1：Dashboard 第一屏没有回答“现在发生了什么”

**现象**

打开 NINJA GAIDEN 4 Dashboard 后，第一屏显示：

- “暂无可比较基线”
- “问题 / 请求带覆盖说明”
- “按可用 cohort 查看”
- “重点：content_design/general”
- “行动：AMPLIFY: content_design/general”

页面诚实地说明了没有基线，但用户看不到当前 Run 最重要的实际信号，例如战斗系统、锁定系统、内容量或低游玩时长人群风险。

**为什么重要**

用户在 5 秒内无法知道这款游戏的核心反馈是什么；页面把“分析状态”放在了“分析结论”前面。

**建议改动**

当没有比较窗口时，保留“无法判断近期变化”的提示，但同时展示单窗口观察：

- 当前总体推荐率
- 最强正向信号：战斗 / 武器 / 高难度挑战
- 主要问题信号：锁定、目标选择、攻击磁吸
- 观察到的高风险群体：低游玩时长评论者
- 每条结论的评论数和证据入口

**优先级：P0 UX**

### P0-2：问题卡点击后无法进入证据

**现象**

Dashboard 显示“缺陷与错误 33 个问题（100%）”。点击后，页面打开“技术与稳定性 / 缺陷与错误”，但显示：

> No reviews found for this subcategory.

这与卡片上已经显示 33 个问题直接矛盾。

**为什么重要**

这是产品最核心的 Signal → Evidence 链路断裂。用户会认为 33 个问题可能是假的，或者系统无法证明自己的判断。

**建议改动**

- 卡片使用后端真实的 canonical subcategory key；
- 统一 `technical/bugs` 与 UI taxonomy key 的映射；
- 点击后必须显示评论数量、原文摘录、review_id、验证状态；
- 如果证据查询失败，不显示空结果，而是显示明确的“证据加载失败”和可重试入口；
- 为所有可点击分析卡增加集成测试：卡片数量必须等于证据列表数量。

**优先级：P0 UX / P0 数据契约**

### P0-3：Chat 问题最终显示通用错误

**现象**

在 Chat 中选择 NINJA GAIDEN 4，点击 “What are the top issues players complain about?”，页面经历：

- Searching reviews...
- Processing results...
- I encountered an error processing your request. Please try again.

用户没有得到任何部分结果、证据或可解释失败原因。

**实际后端错误**

- `get_reviews_by_subcategory` 的 SQLite 查询出现缺失 bind parameter `_jx`；
- 后续 Provider tool-calling 请求出现重复 `tool_call_id`；
- 最终 Chat 以通用错误结束。

**为什么重要**

Chat 是用户验证“为什么”的入口。当前失败时没有告诉用户是数据查询失败、模型失败还是 Provider 失败，无法建立信任，也无法恢复。

**建议改动**

- 先修复 SQL `json_each` alias / bind 参数问题；
- 对同一 tool call 保证唯一 ID；
- 将错误分为“数据查询失败 / Provider 失败 / 证据不足”；
- 允许 Chat 返回已经成功取得的结构化观察，即使后续总结失败；
- 页面显示：Observed / Evidence / Possible mechanisms / Not established；
- 不要只显示“请重试”。

**优先级：P0 UX / P0 Reliability**

### P0-4：分析结果 API metadata 校验错误

**现象**

请求 `/analysis/2627260` 时后端报错：

> AnalyzeMetadata.fetched_at — Field required

Dashboard 仍能显示部分缓存结果，但新鲜结果读取路径已经不可靠。

**为什么重要**

用户无法知道页面显示的是最新 Run、缓存结果还是降级结果。对于一个强调 Run、provenance 和 immutable result 的产品，这是严重的信任问题。

**建议改动**

- 给历史 metadata 提供兼容迁移或后端默认值；
- 页面明确显示“当前结果来源：最新 Run / 缓存 / 降级”；
- 新旧结果读取统一走同一 schema adapter；
- 增加真实数据库 fixture 的 `/analysis/{app_id}` contract test。

**优先级：P0 数据契约**

### P0-5：Dashboard 与报告页样本量不一致

**现象**

- Dashboard：1,000 reviews
- Reports：August 2026，137 reviews

报告页标题是 “Generate a monthly executive PDF from existing analysis data”，但没有清楚解释为什么同一款游戏出现两个样本范围。

**为什么重要**

用户会误以为系统数据不一致，或者不知道哪个数字可以用于决策。

**建议改动**

每个页面顶部固定显示：

- Run ID
- 数据截止时间
- 样本范围
- 过滤条件
- 结果模式

如果报告是月度窗口，明确写成“月度窗口：137 条；全量 Run：1000 条”。

**优先级：P0 UX / P0 Metric Provenance**

## P1 UX 问题

### P1-1：What matters 仍然像分类器输出

当前显示：

> content_design/general

这不是业务语言，也没有解释为什么排在第一位。用户无法知道这是正向信号、问题还是需求，更无法看到 prevalence、negative concentration、evidence count 和 confidence。

建议改为：

> AMPLIFY — 战斗系统与高难度挑战
>
> 907 条评论涉及内容/体验；该排序为离线启发式辅助，需通过真实模型或人工抽样确认。
>
> 查看证据 →

### P1-2：FIX / IMPROVE / BUILD / AMPLIFY 没有成为页面主叙事

当前“五问”只显示一个“AMPLIFY: content_design/general”，没有把行动卡展开成：

- Observed signal
- Why prioritized
- Evidence
- Uncertainty
- Next action
- Validation

建议至少在首屏显示一张完整行动卡，把行动类型和证据绑定起来。

### P1-3：Who 的文案仍然容易过度包装

页面使用 “Experience”“New / Casual / Regular / Veteran”，但这些实际来自 Steam library size，不是真实玩家画像，也不等同于游戏内的新手或老玩家。

建议改成：

- “Observed concentration”
- “High-library owners”
- “Low-playtime reviewers”
- “Based on available review metadata”

中文界面应明确写“观察到的评论群体”，不要写“最受影响玩家群体”。

### P1-4：覆盖率文案容易误导

问题卡显示“33 个问题（100%）”，底部指标又显示“33/1000 · 100% coverage”。这两个 100% 的分母语义不同，但界面没有解释。

建议显示：

> 33 条评论 / 1000 条样本（3.3%）
>
> 分类覆盖率：100%

不要在同一张卡上并列两个未解释的百分比。

### P1-5：中文产品仍有明显英文残留

真实页面中出现：

- Last run
- Last 30 days
- Negative only
- 20h+ playtime
- Top issues
- Top feature requests
- Categories overview
- Trends
- Userbase segmentation
- AI Summary
- Feature Requests

这会降低中文用户的产品完成度感，也让作品集截图显得像开发中界面。

### P1-6：Reports 页面不是“分析报告”而是 PDF 生成器

导航叫“分析报告”，页面却只提供月度 PDF 生成，并且正文信息非常少。用户想看游戏分析成果时，会进入一个不能直接阅读 Five Questions 的页面。

建议把页面分成：

1. 在线可读的游戏分析报告；
2. 月度窗口报告；
3. 下载 PDF。

不要让 PDF 导出成为“分析报告”页面的默认内容。

### P1-7：运行和成本信息不可见

首屏只有“离线开发 Fixture”小标签，没有显示：

- 运行模式
- Provider / model
- Provider cost
- fallback count
- classified count
- evidence verification status

建议加入一个可展开的“本次 Run 信息”区，而不是把这些信息藏在 Debug 或日志中。

## Keep：值得保留的部分

### Keep-1：游戏上下文清晰

游戏封面、名称、当前在线人数、最近 Run 时间和评论数集中在顶部，用户知道自己正在看哪款游戏。

### Keep-2：Five Questions 已经进入首屏

这比把 Review Count、Positive%、Technical% 直接放在最上面更接近产品目标。结构方向是对的，内容优先级还需要重排。

### Keep-3：离线模式有明确标识

“离线开发 Fixture”以及“没有基线窗口，不能声称近期发生了变化”的提示是诚实的，应保留。但应同时提供当前快照的可读观察。

### Keep-4：筛选器方向正确

Last 30 days、Negative only、20h+ playtime、10+ helpful 等筛选器能支持进一步追查。下一步需要让筛选后的结果和证据卡真正联动。

### Keep-5：版本更新入口与 Version Review 已连接

Dashboard 能看到版本事件入口，Reports 也能跳转 Version Review，这是从玩家信号连接到版本决策的正确方向。

## 推荐修复顺序

### 第一组：先修“可信度闭环”

1. 修复问题卡 → 证据列表的 taxonomy key 映射。
2. 修复 `/analysis/{app_id}` metadata 兼容问题。
3. 修复 Chat 的 SQL bind 参数和 tool call ID 问题。
4. 统一 Dashboard、Reports、Chat 的 Run ID、样本范围和时间窗口。

### 第二组：再修“首页决策价值”

1. 首屏增加单窗口 Observed signals。
2. 将 What matters 改为业务可读的 FIX / IMPROVE / BUILD / AMPLIFY 卡。
3. 每张卡显示证据数、覆盖率分母、置信度和验证入口。

### 第三组：最后做“展示完成度”

1. 清理英文残留。
2. 重新命名 Who 分群，避免过度包装。
3. 重构 Reports 页面为可读报告 + PDF 导出。
4. 增加 Run / Cost / Provenance 抽屉。

## 第一轮结论

当前产品已经从“能显示分析指标”进入“尝试显示决策摘要”的阶段，但还没有完成最重要的产品闭环：

> Signal → Why → Evidence → Priority → Action → Validation

目前断点最严重的是：

- Signal 有了，但首页不够可读；
- Evidence 入口有了，但点进去为空；
- Chat 入口有了，但真实问答失败；
- Action 类型有了，但没有业务化行动内容。

因此第一轮不建议继续做作品集包装，建议先做 **P0 UX / Data Contract 修复**，再重新审查同一条路径。
