# 阶段六终端兼容矩阵

**日期：** 2026-09-13
**机器：** 开发机自动记录；不得把单机结果写成全平台承诺。

| 终端 | 尺寸 | locale | 颜色 | 动画 | 结果 |
|---|---|---|---|---|---|
| Textual Pilot | 60×16 / 80×24 / 120×40 | 默认 | 由能力探测 | 关闭 | 自动通过 |
| PTY harness | 默认 | 默认 | xterm / dumb | 不适用 | 自动通过（正常退出、超时取消、无 alternate screen） |
| Terminal.app | 未测 | 未测 | 未测 | 未测 | Not run |
| iTerm2 | 未测 | 未测 | 未测 | 未测 | Not run |
| Warp | 未测 | 未测 | 未测 | 未测 | Not run |
| 常见 Linux 终端 | 未测 | 未测 | 未测 | 未测 | Not run |
| Windows Terminal | 未测 | 未测 | 未测 | 未测 | Not run |

未实测项保持 `Not run`，不推断支持。
