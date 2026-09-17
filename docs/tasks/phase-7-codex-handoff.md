# 阶段七交接：交给 Codex 继续

> 2026-09-17 Cursor 主实现会话结束。下一任主实现 Agent 为 Codex。只读本文件后先读 `docs/STATUS.md`、活动任务与视觉 Token，再改代码。

**分支：** `phase-7/0041-product-acceptance`  
**产品代码：** 原交接基线为 `ce2d9f2`；Codex 后续完成收口修正、真实验证与封存提交。
**工作区：** 仅 `/Users/admin/Vera`。`/Users/admin/Coding-harness` 只读。  
**阶段：** 7 Complete。用户 2026-09-17 原文确认「CLI 版本达到预期，可以封存」；阶段八 Core-native Skills 与阶段九桌面均 Not started，该确认不自动授权下一阶段实施。

## 硬约束

- 用户封存原文必须一字不差：`CLI 版本达到预期，可以封存`。没有该句不得标阶段七 Complete、不得开始阶段八、不得引入 Electron/Tauri/Wails。
- 不读真实 Provider Key；不改用户真实工程内容；不自动处理 `VeraTestDemo` 索引里残留的 `AD build/`，不改 `.gitignore`。
- 同一时间一个主实现 Agent。文档默认中文；标识符与协议字段保持规范英文。
- 未经用户批准不得 push、不得改 git remotes、不得破坏性 Git 操作。

## 当前进度

阶段七主链 0034–0041、0043–0058 已 Done。0041 自动栏、真实 Provider、原生 Terminal.app 代测与用户封存确认已完成。

走查修正 **0044–0058 Done**。2026-09-17 Codex 按用户授权用独立原生 Terminal.app 窗口、真实 Provider 和脱敏临时工程代测，发现 38–54 中已记录项全部关闭。

原交接时待 Terminal.app 的项目现状：

| 任务 | 内容 | 用户口头 |
|---|---|---|
| 0051 | 发现 42：路径/CJK 折行；回答署名 Vera | Codex 原生 Terminal.app 代测通过 |
| 0052 | 发现 50 High：工具后空响应催促一次 | 真实 Provider 工具后完整回答，关闭 |
| 0053 | 占用 K、审批卡 margin | Codex 原生 Terminal.app 代测通过 |
| 0055 | 工作轨在 Composer 上；状态组默认收起 | Codex 原生 Terminal.app 代测通过 |
| 0056 | 三行点阵欢迎卡；任务后 `VERA  ~/path`；底栏分支/审批/占用 \| 模型+推理 | Codex 原生 Terminal.app 代测通过 |
| 0057 | Markdown 表格按列；Diff 词界折行；进场单条亮带 | 用户确认波动；Codex 原生 Terminal.app 表格/Diff 代测通过 |
| 0058 | 缩放重绘；底栏按内宽，模型名不被裁 | Codex 复现残影、补修并在原生 Terminal.app 复验关闭 |

真实 Run 记 **16/20**（VeraTestDemo + Python 示例/脱敏临时工程、2 个自然日、3 次跨进程）。用户明确接受把剩余量化样本转入后续 Bug 收敛阶段规划。

## 打开的发现

当前无未关闭 Critical/High/Medium/Low 走查发现。白块已关；进场波动方向、单条、2.5 秒一巡已按用户最后一次口头确认落地（`AnimationClock.wave_phase` 系数为 `0.4`）。

## 建议下一刀

1. 阶段七已封存；后续 Bug 收敛、阶段八 Skills 与阶段九桌面均另行规划。
2. 本交接记录不授权自动实施阶段八 Skills、开始阶段九桌面或引入桌面框架。

视觉与进场的现行规格以 [视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md) 和任务 0056–0058 为准，不要倒回 0039 的两行品牌或 0053 把运行状态放回底栏。

## 近期提交（新在上）

- `ce2d9f2` 波动一巡 2.5 秒
- `0e40b85` 缩放重绘与底栏模型不被裁
- `d8b5785` / `a7deea2` 单条慢亮带
- `06ae151` 表格按列、Diff 词界折行、波动重新可见
- `927784a` 波动左下→右上；底栏按 padding 排
- `f5d58c3` 密集点阵欢迎卡与缩行路径
- `9664a92` 工作轨钉在 Composer 上
