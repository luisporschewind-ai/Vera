# 任务 0079：清除 Apple Terminal 启动前的 `p`

**状态：** Done
**来源：** 2026-09-24 用户在原生 Terminal.app 启动 `vera` 时发现左上角短暂出现 `p`；已确认 `TERM_PROGRAM=Apple_Terminal`。
**规格：** [CLI 体验收口与个人主力化](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)

Vera 使用的 Textual 8.2.8 在 Apple Terminal 下仍发送 `ESC[?2048$p` 终端能力查询。Vera 只在该终端跳过这条查询，继续使用 Textual 的 `SIGWINCH` 窗口尺寸事件。其他终端维持原驱动。

按用户要求不运行全量回归；Ruff 检查、格式检查与改动差异检查通过。用户于 2026-09-24 确认原生 Terminal.app 启动时不再出现 `p`。修正随活动状态分支合并到 `main`。
