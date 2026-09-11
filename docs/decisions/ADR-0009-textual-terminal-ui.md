# ADR-0009：Textual Terminal UI 与三种呈现模式

**状态：** Accepted
**日期：** 2026-09-11

## 背景

Vera 需要可滚动对话、可折叠工具和日志、展开的 Diff/审批、失败自动展开、固定 Composer 和任务动画。现有 Typer + 逐行输出不能稳定表达这些交互。

## 决策

- `vera` 在 TTY 中默认启动 Textual 全屏 TUI，并使用 alternate screen。
- Typer 继续作为模式与子命令路由；Rich 继续承担 Markdown 和 Diff renderable。
- `vera --plain` 保留逐行人类模式和终端原生 scrollback。
- `vera --json` 提供 NDJSON Session 协议；`vera run ... --json` 保持旧 Event 输出兼容。
- TUI、Plain、JSON 通过同一个 `SessionController` 发送 `SessionAction` 并消费结构化 Core 输出。
- 不引入 `prompt_toolkit`，不允许两个框架共同接管 stdin 或事件循环。
- TUI 只渲染和提交结构化意图，不直接读写项目、执行命令或调用模型。
- 第一版固定一套 16/256 色安全主题，不实现主题市场。

## 后果

- 终端 UI 可以独立替换，不影响 Runtime、恢复与未来桌面客户端。
- Textual 成为富交互模式的新增运行依赖，并需要异步 Worker、焦点和 PTY 生命周期测试。
- 用户需要原生 scrollback 或终端能力不足时必须显式使用 `--plain`。
- Mode router、SessionController 与 View Model 必须保持无 Textual 类型的公共边界。

## 验证与重审触发器

- 通过 Textual Pilot/SVG 和真实 PTY 测试验证滚动、折叠、审批、Resize 与退出恢复。
- 如果 Textual 无法在 macOS Terminal.app 保持输入可靠或长时间线性能，重新评估 prompt_toolkit 或 Rust TUI，但不能在同一进程混用两个终端框架。
- 若未来桌面客户端需要解析 TUI 字符串，说明边界已被破坏，必须先修复结构化契约。
