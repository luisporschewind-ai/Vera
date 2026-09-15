# 任务 0038：CLI 视觉原型与设计 Token 冻结

> 供主设计/实现 Agent 执行：先使用 `superpowers:brainstorming` 形成可见方案；本任务只产出评审资产和冻结决策，不修改产品 Widget/CSS。

**状态：** Planned
**执行就绪：** 否；等待任务 0043 完成
**分支：** `phase-7/0038-cli-visual-direction`
**依赖：** 任务 0043
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)

## 目标与边界

把完整字标、V 星点母形和组合标识做成可见终端原型，在 60×16、80×24、120×40 与无色环境中对照，记录用户选择并冻结语义 Token。未获用户明确选择前，本任务不得改 `src/vera/terminal/` 产品代码，也不得开始 0039。

## 原型共同事实

三套方案使用同一组假数据与状态，不靠内容差异影响判断：

- workspace：Git dirty 与非 Git 各一版；
- session：new 与 resumed 各一版；
- 状态：idle、running、approval、verification、completed、failed；
- 时间线：用户、助手、普通工具、Diff、审批和验证；
- 对话滚动：最近用户消息作为顶部上下文锚点，右侧显示原始本地时间；
- 输入区：左侧提示箭头、Composer、下方左侧上下文条/百分比与右侧模型/有效推理强度；
- 审批密度：同一内容分别放在普通时间线和 80×24 主流程中，检查卡片上下是否出现中断性空白；
- 宽度：60、80、120 列；高度：16、24、40 行；
- 回退：Unicode、ASCII、high-contrast、`NO_COLOR`。

## 实施步骤

### 1. 建立评审矩阵

- [ ] 新增 `docs/evals/phase-7-visual-review.md`，列出阶段七规格中的六个待确认视觉问题、共同内容、尺寸、字体/Terminal.app 环境和评分项。
- [ ] 评分项固定为：Vera 识别度、正文可读性、用户消息锚点可辨识、证据透明度、状态收敛、输入稳定性、审批连续性、小终端占用、无色可辨识、长期使用疲劳。
- [ ] 不把 Codex、Claude Code 或 Grok Build 的商标、Logo 字形或截图直接作为 Vera 资产。

### 2. 产出三套可见原型

- [ ] 新增 `docs/evals/artifacts/phase-7-cli-visual-a-wordmark.svg`：完整字标优先，紧凑时退化为文字 `VERA`。
- [ ] 新增 `docs/evals/artifacts/phase-7-cli-visual-b-v-star.svg`：V 星点母形优先，ASCII 使用 `[V]`。
- [ ] 新增 `docs/evals/artifacts/phase-7-cli-visual-c-combination.svg`：母形加字标，窄屏只保留母形/文本回退。
- [ ] 每套 SVG 同时展示 60×16、80×24、120×40，不以单张大尺寸效果掩盖窄屏问题。
- [ ] 每套原型都必须展示同一条 Composer 下方双侧状态带：左侧为会话上下文条与百分比，右侧为模型与有效推理强度；至少一版展示 Provider 无推理强度时的“模型默认/不可用”。
- [ ] 每套原型都必须展示用户消息从普通时间线进入顶部锚点、被下一条用户消息替换的两帧，以及带三个按钮且上下无中断性空白的审批卡。
- [ ] 另附纯文本 `.txt` 回退样例，证明不依赖 Nerd Font、Emoji 宽度或真彩色。

### 3. Terminal.app 对照与用户选择

- [ ] 在真实 Terminal.app 默认字体中展示三套原型，记录 CJK、宽字符、复制和缩放现象；自动截图不能代替该记录。
- [ ] 向用户展示 A/B/C，并明确说明每套在识别度、空间、实现复杂度和桌面延展上的取舍。
- [ ] 停止等待用户明确选择：标识方向、80×24 品牌高度、默认工具披露密度、时间线主轴，以及 60×16 状态带优先保留“上下文百分比”还是“模型名”。

### 4. 冻结 Token 与回退规则

- [ ] 用户选择后在 `docs/evals/phase-7-visual-review.md` 记录最终理由，而不是只写“已确认”。
- [ ] 新增 `docs/specs/2026-09-13-vera-cli-visual-tokens.md`，冻结语义 Token：`background`、`surface`、`surface_elevated`、`text_primary`、`text_muted`、`accent`、`success`、`warning`、`danger`、`focus`、`diff_add`、`diff_remove`。
- [ ] 每个 Token 记录默认深海、高对比和无色表示；状态文字/符号必须在移除颜色后仍可理解。
- [ ] 冻结 Logo 的 full/compact/ascii 三形态、选择阈值和可占用最大行数；桌面图标只记录延展原则，不产出桌面资产。
- [ ] 将规格状态保持为用户实际接受的状态；未确认时不得写 `Accepted`。

## 局部验证与提交

```bash
! rg -n "TBD|TODO|待定|稍后决定" docs/evals/phase-7-visual-review.md docs/specs/2026-09-13-vera-cli-visual-tokens.md
rg -n "#[0-9A-Fa-f]{6}" docs/specs/2026-09-13-vera-cli-visual-tokens.md
git diff --check
```

人工核对 SVG 与文本回退均可打开、没有第三方商标或隐藏外链。用户接受方向后更新证据并提交：

```bash
git commit -m "docs: freeze Vera CLI visual direction"
```

## 验收标准

- 用户看到并对照了三套同内容、多尺寸、含无色回退的原型。
- 最终 Token、Logo 形态、尺寸阈值、披露密度、用户消息锚点和底部状态带降级优先级已由用户明确选择。
- 产品 TUI 代码尚未因未确认的视觉偏好发生改变。
- 0039 只实现已冻结方向，不重新发明视觉规范。
