# 评审：阶段七 CLI 视觉原型

**任务：** [0038](../tasks/0038-cli-visual-prototypes-and-tokens.md)  
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)  
**日期：** 2026-09-16  
**状态：** 用户已选择方向。Token 规格 Accepted。产品 TUI 在本任务中未改。

## 六个问题的结论

2026-09-16 用户对照三套 SVG 与 A 方案 txt 后明确选择。理由写在选择记录，不单写「已确认」。

1. 主 Logo：完整字标 A。
2. 80×24 品牌区：两行。
3. 深海色值：接受拟议深海 / 高对比 / 无色表，见 Token 规格。
4. 时间线主轴：连续对话（用户消息钉顶）。「时间线主轴确定」按评审主提案理解，不是任务卡片备选。
5. 默认工具披露：一行摘要。
6. 60×16 状态带：优先保留上下文百分比。

## 共同假数据

三套方案、所有尺寸使用同一组事实，不靠文案差异影响判断。

| 字段 | 值 |
|---|---|
| workspace | `/Users/admin/VeraTestDemo`（宽屏）/ `VeraTestDemo`（窄屏） |
| Git dirty | `main*` |
| 非 Git | `/tmp/plain-project` · 非 Git · 新会话（120×40 对照行） |
| session | 60×16 为新会话；80×24 / 120×40 为已恢复 |
| 用户 | `把背景改成深海绿` · 本地时间 `10:24` |
| 下一条用户 | `再把标题字号加大` · `10:31`（锚点帧 2） |
| 模型 | `deepseek-chat` |
| 推理 | `模型默认`（Provider 无推理强度） |
| 上下文 | 主流程 24%；120×40 恢复中段 12% |
| Diff | `ViewController.swift` update；蓝 → 绿 |
| 审批 | Change Set · 风险 medium · 取消 / 拒绝 / 批准 |
| 验证 | 未排队（无验证命令） |
| 失败对照 | `EACCES  Permission denied`（仅 120×40 状态条） |

## 已冻结 Token

权威表在 [视觉 Token 规格](../specs/2026-09-13-vera-cli-visual-tokens.md)。评审期使用的拟议值即最终值：

| Token | 深海默认 | 高对比 | 无色 |
|---|---|---|---|
| `background` | `#0B1C28` | `#000000` | `#1A1A1A` |
| `surface` | `#122433` | `#000000` | `#2A2A2A` |
| `surface_elevated` | `#1A3144` | `#000000` | `#222222` |
| `text_primary` | `#D7E4EE` | `#FFFFFF` | `#E0E0E0` |
| `text_muted` | `#7E96A8` | `#FFFFFF` | `#B0B0B0` |
| `accent` | `#3D7A8C` | `#FFFF00` | `#B0B0B0` |
| `success` | `#4A8B6F` | `#00FF00` | `#C8C8C8` |
| `warning` | `#B08A4A` | `#FFFF00` | `#D0D0D0` |
| `danger` | `#A85A5A` | `#FF4444` | `#E0E0E0` |
| `focus` | `#5B9BB0` | `#FFFF00` | `#F0F0F0` |
| `diff_add` | `#3D6B55` 底 / `#7EB89A` 字 | `#00FF00` | `#E0E0E0` |
| `diff_remove` | `#8B4A4A` 底 / `#D98989` 字 | `#FF4444` | `#E0E0E0` |

无色与 ASCII 下，批准/拒绝/取消仍靠括号标签区分；成功/失败靠「完成」「失败」等文字，不靠色相。

## 原型资产

| 方案 | SVG | 文本回退 | 结果 |
|---|---|---|---|
| A 完整字标 | [phase-7-cli-visual-a-wordmark.svg](artifacts/phase-7-cli-visual-a-wordmark.svg) | [phase-7-cli-visual-a-wordmark.txt](artifacts/phase-7-cli-visual-a-wordmark.txt) | 采用 |
| B V 星点母形 | [phase-7-cli-visual-b-v-star.svg](artifacts/phase-7-cli-visual-b-v-star.svg) | [phase-7-cli-visual-b-v-star.txt](artifacts/phase-7-cli-visual-b-v-star.txt) | 不采用 |
| C 组合标识 | [phase-7-cli-visual-c-combination.svg](artifacts/phase-7-cli-visual-c-combination.svg) | [phase-7-cli-visual-c-combination.txt](artifacts/phase-7-cli-visual-c-combination.txt) | 不采用 |

生成脚本：`docs/evals/artifacts/_gen_phase7_visuals.py`。不含 Codex、Claude Code、Grok 的商标或截图。B/C 仅作对照证据保留，0039 不得实现母形。

## 尺寸与环境

| 尺寸 | 角色 | 已冻结行为 |
|---|---|---|
| 60×16 | 安全降级 | `compact` 一字标一行；状态带留上下文百分比 |
| 80×24 | 完整主流程 | `full` 两行品牌；工具一行；审批卡内连续 |
| 120×40 | 证据更密 | 仍两行品牌、一行工具默认；可增加证据密度、不改语义 |

字体/终端：Terminal.app 默认 Menlo。对照 CJK 是否占两列、`█░` 进度条、复制是否夹带盒线、缩小到 60 列后字标是否裁切。

## 评分项

用户未逐项打 1–5，以书面选择代替评分表。选择 A 是因为字标冷启动即可读出产品名，且实现不必维护母形阈值。

## 选择记录

| 问题 | 选择 | 理由 |
|---|---|---|
| 1 标识 | A 完整字标 `VERA` | 用户指定「标识A」。四字即产品名，60×16 仍是 `VERA`，不必学图形。否决母形与组合，避免双套资产。 |
| 2 80×24 品牌高度 | 两行 | 用户指定「两行」。第一行独占字标，第二行放 workspace/git/会话，接受少一行对话换更清楚的产品首屏。60×16 仍压成一行，避免再吃高度。 |
| 3 深海色值 | 接受拟议表 | 用户指定「深海色值确定」。低饱和蓝绿底、克制强调色与危险色，与既有深海方向一致，不再改单点色值。 |
| 4 时间线主轴 | 连续对话，用户消息钉顶 | 用户指定「时间线主轴确定」，对应评审主提案而非任务卡片备选。Vera 是长期对话式 Coding Agent；Diff/审批提高权重，但不改主轴。 |
| 5 工具披露密度 | 一行摘要 | 用户指定「默认工具披露，一行摘要」。80×24 先保住 Diff 与审批；详情按需展开。 |
| 6 60×16 状态带 | 上下文百分比 | 用户指定「上下文百分比」。窄屏先回答还能聊多久；模型名退到 `/status` 或 ≥80 列。 |

## Terminal.app 对照

自动 SVG 不能代替本项。用户打开 A 方案 `.txt` 并对照修复后的三套 SVG 后作出选择。

| 现象 | 记录 |
|---|---|
| CJK 是否按两列对齐 | 初版 SVG 曾因整行 `textLength` 把中文拉爆；已改为格子排版。用户在修复后选择，未再报重叠。 |
| 宽字符 / 进度条是否错位 | 用户未报进度条错位；txt 内框按显示宽度对齐。 |
| 复制是否夹带盒线或多余空格 | 用户未报复制问题。ASCII 回退使用 `+`/`-`/`>`，不依赖 Nerd Font。 |
| 缩放到 60×16 后标识是否可认 | 用户选择 A，60×16 仍为 `VERA`。 |

## 后续

- 0039 只实现已冻结方向：字标、两行品牌（宽屏）、深海三主题、双侧状态带与 60×16 百分比优先。
- 0040 实现对话主轴、用户消息锚点与一行工具披露。
- 阶段七不得因本评审被标 Complete；封存仍需用户书面确认 `CLI 版本达到预期，可以封存`。
