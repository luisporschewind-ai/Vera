# 阶段六人工产品走查

**规格：** [CLI 产品化与体验完善](../specs/2026-09-12-cli-productization-and-polish.md)  
**任务：** [0029](../tasks/0029-phase-6-product-acceptance.md)  
**日期：** 2026-09-13  
**结果：** In progress（用户在真实 Terminal.app 与真实工程中走查；第 1 项部分完成，第 2–7 项 Not run）

自动测试、PTY、Textual Pilot、快照和 wheel smoke 不能填写本表的“实际”栏。Agent 不得把未观察的项写成通过。

每项记录环境、步骤、预期、实际、严重度和脱敏证据。初始值全部 `Not run`。

## 共用记录栏

| 字段 | 含义 |
|---|---|
| 环境 | 终端、尺寸、locale、颜色/动画、工程类型 |
| 步骤 | 实际操作顺序 |
| 预期 | 规格要求的可观察结果 |
| 实际 | 用户观察到的结果；未走查保持 `Not run` |
| 严重度 | Critical / High / Medium / Low / 无 |
| 证据 | 脱敏文本或截图路径；禁止 Key、请求正文、源码正文 |

## 1. 陌生工程首启

| 字段 | 内容 |
|---|---|
| 环境 | macOS Terminal.app；`~/Desktop/VeraTestDemo`（Swift/Xcode）与 `~/Desktop/python-demo`（Python，非 Git 仓库）；editable 安装的 `vera`（`/Users/admin/.local/bin/vera` → 仓库 `src/vera`） |
| 步骤 | 在工程目录执行 `vera`；查看首屏、`/help`、模型、workspace 与安全边界 |
| 预期 | 首屏可见版本、模型、规范化工作区、Git、审批模式、无 OS 沙箱边界；可用 `/help` 发现命令 |
| 实际 | 部分走查。首屏八行状态（版本、模型、规范化工作区、Git 状态、会话、上下文、审批模式、`current user · no OS sandbox`）正常呈现；`/help` 按六组显示且七个阶段六新增命令均可见。**但用户无法从首屏判断所运行的是否为最新构建**：版本行恒为 `Vera 0.1.0`，开发期不随改动变化，且 `vera --version` 选项不存在，执行后返回 Usage error。首屏信息可读性、安全边界措辞与 `/help` 可发现性的主观结论仍未给出。 |
| 严重度 | Medium（发现 1：缺版本自证手段） |
| 证据 | `/help` 输出含「开始/会话/代码与证据/恢复/安全/外观」六组与 `/diff` `/review` `/doctor` `/config` `/usage` `/shortcuts` `/theme`；`vera --version` 返回 `Usage: vera [OPTIONS] COMMAND [ARGS]...` 与 No such option 错误 |

## 2. 输入与引用

| 字段 | 内容 |
|---|---|
| 环境 | macOS Terminal.app；`~/Desktop/VeraTestDemo` |
| 步骤 | 普通对话、`@path`、多行、历史搜索、长粘贴、外部编辑器、单条队列 |
| 预期 | 输入不丢失、粘贴不误提交、审批中不能排队、`@path` 不逃逸 workspace、不暗示批准 |
| 实际 | 部分走查。输入 `/` 弹出命令提示，可用；普通对话（「你好」）收到模型回复，对话闭环可用。走查过程中发现时间线不自动跟随底部，需手动滚动（见发现 2）。`@path` 补全、多行、`Ctrl+R` 历史搜索、长粘贴、`Ctrl+G` 外部编辑器与单条队列仍未走查。 |
| 严重度 | 见发现 2（High） |
| 证据 | 用户在 Terminal.app 的直接观察 |

## 3. Diff 与审批

| 字段 | 内容 |
|---|---|
| 环境 | Not run |
| 步骤 | 单文件与多文件 Diff 导航、复制、拒绝、批准、过期审批 |
| 预期 | Diff 可导航可复制；默认焦点安全；过期审批不能继续使用 |
| 实际 | Not run |
| 严重度 | Not run |
| 证据 | Not run |

## 4. 验证、取消与恢复

| 字段 | 内容 |
|---|---|
| 环境 | Not run |
| 步骤 | 验证成功/失败、取消、恢复、回滚 |
| 预期 | 终态文字不混淆；取消不重复副作用；恢复/回滚有明确事实 |
| 实际 | Not run |
| 严重度 | Not run |
| 证据 | Not run |

## 5. 诊断与异常环境

| 字段 | 内容 |
|---|---|
| 环境 | Not run |
| 步骤 | `/doctor`、错误配置、无 Git、只读目录、Provider 不可用 |
| 预期 | 每项有 `pass`/`warning`/`fail`/`unavailable`；不泄漏秘密；错误可行动 |
| 实际 | Not run |
| 严重度 | Not run |
| 证据 | Not run |

## 6. 终端兼容

| 字段 | 内容 |
|---|---|
| 环境 | Not run |
| 步骤 | 小终端、无色、关闭动画、CJK、Resize、异常退出 |
| 预期 | 关键审批信息不截断；退出恢复终端；不依赖颜色传达状态 |
| 实际 | Not run |
| 严重度 | Not run |
| 证据 | Not run |

## 7. 四种入口语义对照

| 字段 | 内容 |
|---|---|
| 环境 | Not run |
| 步骤 | 同一场景分别走 TUI、`--plain`、`--json`、`vera run` |
| 预期 | 命令、审批、错误 code、终态和退出码语义一致；JSON 不混入 ANSI |
| 实际 | Not run |
| 严重度 | Not run |
| 证据 | Not run |

## 发现清单

按走查顺序累积。Critical/High 必须修复并重新走查；Medium/Low 可记录并由用户接受或转入后续修正任务。

| # | 走查项 | 发现 | 严重度 | 状态 |
|---|---|---|---|---|
| 1 | 1 首启 | 无法自证所运行的版本：版本行恒为 `Vera 0.1.0`，且 `vera --version` 选项不存在（返回 Usage error）。产品作者本人也需要检查 `vera.__file__` 才能确认跑的是最新代码。 | Medium | 已记录，用户选择先继续走查 |
| 2 | 2 输入与对话 | 时间线不自动跟随底部，新消息到达后需手动滚动才能看到。根因：`ConversationTimeline._append` 调用的 `mount()` 在 Textual 中是异步的，`apply()` 随即调用 `scroll_end()` 时新块尚未进入布局，`virtual_size` 仍是旧值，因此滚到的是上一条内容的底部。`apply`、`flush_scheduled`、`return_to_tail` 三处同源。自动测试只断言 `follow_tail` 标志与代码分支，未断言真实 `scroll_y` 是否达到 `max_scroll_y`，因此漏检。 | High | 待修复；修复后需重走第 2 项并补充滚动位置断言 |
| 3 | 2 输入与对话 | 执行任务时模型报错（用户确认 DeepSeek Key 有效、余额充足）。Vera 私有 run 日志中今日无任何新记录，最近记录均为 2026-09-11，说明失败发生在 run 落盘之前。同一工程 2026-09-11 的 run `run_98492fd8` 曾完成 `changeset.proposed` → `approval.required`（changeset + command）→ `run.completed` 完整闭环，证明该 Provider 的 tool calling 当时可用。 | 待定性（暂按 High 处理） | Blocked：需要错误原文或结构化错误事件才能定性为回归或环境故障 |

## 封存确认

用户确认原文必须是：「CLI 版本达到预期，可以封存」

当前记录：未确认。
