# Vera 阶段六：CLI 功能与可靠性收口

**状态：** Accepted
**日期：** 2026-09-12

> 后续关系：[ADR-0017](../decisions/ADR-0017-insert-cli-experience-stage.md) 将阶段六收口为 CLI 功能与可靠性基线，并把持久化会话、具体品牌视觉、长期个人 dogfood 和最终用户封存门禁移至阶段七；[ADR-0020](../decisions/ADR-0020-stage-core-native-skills.md) 与 [ADR-0021](../decisions/ADR-0021-core-tools-before-desktop.md) 又依次把工具/Policy/Git 和 Skills 放在桌面之前。当前桌面为阶段十。本规格的功能、终端兼容、安全和结构化客户端要求继续有效。

## 背景

阶段三已经完成默认 Textual TUI、可滚动时间线、折叠策略、流式输出、Composer、审批交互以及 `--plain` / `--json` 兼容模式。阶段五将进一步加固 Core 的安全、权限与可靠性。

机制可用仍不等于产品成熟。一个长期使用的 Coding Agent CLI 还需要稳定、易发现、符合终端直觉的输入和导航；清晰、一致、可行动的状态与错误；完整的 Diff、审批、诊断和配置入口；以及对粘贴、Unicode、Resize、低速终端和异常退出等日常细节的处理。

阶段六专门处理这些产品化问题。它参考 Claude Code、Codex CLI 和 Gemini CLI 的共同交互模式，但不照搬品牌视觉或引入 Vera 当前阶段之外的云端、Multi-Agent、插件等能力。

## 目标

- 让用户在工程目录执行 `vera` 后，无需阅读外部教程也能理解工作区、模型、安全边界和主要操作。
- 让输入、历史、补全、路径引用、滚动、折叠、复制和取消符合主流终端使用习惯。
- 建立完整且单一来源的 Slash Command、快捷键和帮助系统。
- 让工具、日志、Diff、审批、验证、恢复和失败具有稳定的信息层次与可操作入口。
- 让验证命令的构建与缓存产物默认隔离在 workspace 外，不因一次验证静默污染用户工程或 Git 暂存区。
- 统一 TUI、Plain、JSON 和一次性调用的命令语义、错误分类、退出码与文档。
- 消除会造成误操作、状态误判、输入丢失或终端损坏的高频低级问题。
- 形成可由自动测试、终端矩阵和人工走查共同复核的 CLI 产品验收报告。

## 非目标

- 不增加新的 Agent 核心能力；需要新工具、新权限或新恢复语义时退回阶段五或另立规格。
- 不实现桌面应用、Web UI 或桌面框架 Spike。
- 不增加 Multi-Agent、MCP 市场、插件市场、长期记忆、复杂 RAG 或向量数据库。
- 不恢复退出后的自然语言对话；会话内记忆仍在进程退出后清空。
- 不提供 `!shell`、全局自动批准或其他绕过 PolicyEngine 的快捷方式。
- 不追求与 Claude Code、Codex CLI 或 Gemini CLI 像素级一致。

## 阶段入口条件

1. 阶段五完整通过，没有未关闭的 `Critical` 或 `High` 安全问题；
2. Core Command/Event、审批、恢复和错误契约已经版本化；
3. 默认 TUI、Plain、JSON 与 Eval 仍消费同一 Core；
4. CLI 体验改动不需要放宽已接受的安全和权限边界。

## 主流交互基线

阶段六只采纳多个成熟 Coding Agent CLI 中反复出现、且符合 Vera 目标的共同模式：

- 无参数命令进入交互模式，同时保留一次性和机器可读模式；
- 输入历史、反向搜索、多行编辑、补全、可靠粘贴和明确取消；
- Slash Command 管理帮助、状态、模型、上下文、Diff、诊断和会话；
- 当前工作区、Git、模型、上下文和权限状态始终可见或一键可查；
- 工具过程紧凑，Diff、审批和失败突出，详细日志按需展开；
- 高风险动作采用显式、可复核、默认不批准的交互；
- 终端尺寸、色彩能力、动画偏好和非交互管道有确定行为。

Vera 保持自身边界：不因竞品支持会话恢复、直接 Shell、自定义 Agent 或插件就自动增加对应能力。

## 启动与首次使用

启动画面必须在首屏清楚展示：

- Vera 版本、当前模型 Profile 和模型名；
- 规范化工作区、Git 分支和 clean/dirty 状态；
- 会话状态、上下文使用量和审批模式；
- “当前系统用户执行、没有 OS 沙箱”的真实边界；
- 一个主要提示：输入自然语言，或使用 `/help` 查看命令。

要求：

- 首次可交互帧之前不得等待 Provider 网络请求；
- 非 Git 目录、缺失可选配置和单项状态读取失败必须局部降级；
- 在用户 Home、文件系统根或过大目录启动时给出醒目但不阻塞的风险提示；
- 退出时恢复 alternate screen、光标、回显和终端模式，不留下乱码或残余控制序列。
- 发行包装版本保持 `vera-agent` 的 packaging version；源码或 editable 安装的首屏版本行必须附加 Vera 源码树的短 commit（有未提交变更时再标 `dirty`），wheel 安装只显示发行版本。
- `vera --version` 与 `vera -V` 不启动会话、不要求工作区，退出码 0；人类输出包含发行版本、安装类型和正在执行的包装目录。`--json` 与 `--version` 同时出现时输出单行 JSON 对象，不是 NDJSON Session 协议。Vera 源码 git 探测只用固定 argv、无 Shell、短超时，失败时省略 git 字段，不得探测用户工作区 git。

## Composer 与输入体验

- 单行 `Enter` 提交；`Ctrl+J` 和终端可识别的 `Ctrl/Shift/Alt+Enter` 插入换行。
- 支持 Home/End、按词移动、选择、Backspace/Delete、撤销/重做和 UTF-8/宽字符光标位置。
- 上下键只在适当光标位置浏览当前进程内的输入历史；`Ctrl+R` 提供历史反向搜索。
- Bracketed Paste 将多行粘贴视为一次编辑，不因换行自动提交，不解释其中的终端控制序列。
- 超长输入显示大小与上下文影响，拒绝时保留原输入供用户编辑。
- `Ctrl+G` 把当前草稿写入权限为 `0600` 的临时文件，并以固定 argv、`shell=False` 调用用户明确配置的编辑器；首次使用展示确切命令并确认，读取完成后只清理本次创建的精确文件。
- 发送后保留明确的用户消息副本；失败、取消或审批等待不会悄悄丢失原始输入。

运行中输入采用一个明确的单条队列：模型或工具活动期间可排队一条后续消息，界面显示、允许撤销；存在未决审批时禁止排队，避免把新指令误当成批准。队列只在当前 run 到达持久终态后作为新的 `StartRun` 提交，不能改变正在执行的 run。

## 路径引用与补全

- 输入 `@` 后按当前 workspace 提供文件和目录补全；补全结果尊重忽略规则与 Workspace 边界。
- 路径引用解析为空格、Unicode 和大小写差异保留可逆表示；展示值与传给 Core 的规范化路径必须可核对。
- 不展开 workspace 外路径、符号链接逃逸、设备文件或隐藏的私有状态目录。
- `@path` 只表示“把该路径作为候选上下文”，不代表批准读取、写入或执行。
- Slash Command 与路径补全来自共享 Catalog，不在 Widget 中维护第二份命令或权限逻辑。

## Slash Command 产品方案

### 保留并打磨

- `/help`、`/status`、`/context`、`/permissions`
- `/new`、`/clear`、`/compact [focus]`
- `/model [profile]`
- `/runs`、`/show <run-id>`、`/resume <run-id>`、`/abandon <run-id>`、`/rollback <run-id>`
- `/exit`、`/quit`

### 阶段六新增

| 命令 | 行为 |
|---|---|
| `/diff [run-id]` | 展示当前待审批或指定 run 的权威 Diff；没有 Diff 时明确说明 |
| `/review [run-id]` | 由确定性 Projector 基于已有 Diff、Event 和验证事实生成只读风险摘要；不调用 Provider、不自动修改文件 |
| `/doctor` | 检查版本（含安装类型与包装位置）、Python、终端能力、配置存在性、状态目录权限和 Git 可用性；不显示秘密 |
| `/config` | 只读显示当前有效配置、来源和脱敏值；修改配置仍通过文件与文档完成 |
| `/usage` | 显示当前会话可得的调用次数、token 和用量；缺失值显示 unavailable，不填零 |
| `/shortcuts` | 显示当前终端可用快捷键和替代按键 |
| `/theme [name]` | 查看或切换当前会话的内置高对比/无色主题，不隐式写配置、不加载可执行主题代码 |

`/help` 按“开始、会话、代码与证据、恢复、安全、外观”分组，并根据当前状态显示可用性。未知命令提供最接近的候选，但绝不自动执行纠正后的命令。

## 时间线与信息层次

- 用户消息和助手最终回答默认展开；工具和普通日志默认折叠；Diff、审批和失败默认展开。
- 工具摘要显示动作、目标、状态和耗时，不把大量 stdout 或完整文件正文铺满时间线。
- 相邻同类只读工具、日志和状态事件可以视觉归组；组保留层级标题，每个权威 Event 仍可单独查看。工具/日志组默认折叠，状态组默认展开。
- Diff 支持文件级导航、行号、增加/删除语义、水平滚动或安全换行，并保留可复制纯文本。
- 验证卡展示命令、cwd、风险、退出码、耗时以及截断状态；失败自动展开 stderr 摘要。
- 失败卡必须同时给出“发生了什么、是否产生副作用、现在能做什么”，不能只显示异常类名。
- 用户离开底部后不抢滚动位置；新更新计数、End 回到底部和 Resize 锚点保持可靠。
- 不可信文本中的 ANSI、OSC、Rich markup 和双向控制字符必须转义或显式标记。

## 审批与任务控制

- 审批卡第一视觉层展示动作、目标、风险、Diff/argv、工作区和批准后的实际效果。
- 默认焦点仍为 Cancel；Approve 不绑定单字母或容易误触的快捷键。
- 审批期间可以展开证据、复制 Diff、滚动历史和执行只读 `/permissions`，不能提交新任务。
- 若批准对象、工作区事实或策略 hash 已变化，界面必须显示“审批已过期”并要求重新生成。
- `Esc` 和 `Ctrl+C` 在运行中只发送一次取消；重复输入显示当前取消状态，不重复副作用。
- 取消、拒绝、失败、恢复和完成使用不同的文字与语义颜色，不能都显示为“结束”。

## 模式一致性

| 入口 | 产品要求 |
|---|---|
| `vera` | 默认 TUI，完整交互、滚动、折叠和审批 |
| `vera --plain` | 原生 scrollback、无动态重绘，拥有同一命令和审批语义 |
| `vera --json` | 稳定 NDJSON Session，无 ANSI、提示符或人类日志 |
| `vera --version` / `vera -V` | 打印安装身份后退出；不启动会话、不要求工作区 |
| `vera --version --json` | 单行 JSON 身份对象；不是 Session 协议，不含 ANSI |
| `vera run <goal>` | 一次性执行，错误和退出码与交互模式一致 |
| `vera run <goal> --json` | 保持既有 EventEnvelope 协议兼容 |
| 非 TTY/管道 | 不猜测模式；根据调用显式进入受支持模式或给出可行动提示 |

任何新 Slash Command 先定义 `SessionAction`/结构化结果，再由不同 Presenter 映射；不得让 JSON 客户端解析 TUI 文本。

## 诊断、错误与退出码

- 错误使用稳定 code、简短中文说明、影响范围和下一步建议；调试细节只在显式展开或诊断文件中出现。
- `/doctor` 对每一项输出 `pass`、`warning`、`fail`、`unavailable`，并提供脱敏 JSON 形式供报告问题。
- 配置错误、工作区错误、Provider 错误、策略拒绝、用户取消、验证失败和内部错误不能共享模糊退出码。
- JSON 模式的错误必须仍是合法协议记录；stdout 不能混入 traceback、日志或进度动画。
- 崩溃报告默认不包含环境、用户源文件、模型请求或 Event payload；用户必须能先预览再决定是否分享。

## 验证产物与工作区无污染

- 验证命令只读取 workspace 源码；Xcode、SwiftPM、pytest、Mypy 等派生产物必须写入 workspace 外、与 Run 精确绑定的 Vera 私有临时根。
- 最终 argv、cwd、隔离 Profile 和产物根必须在 Change Set hash、PolicyEngine 分类和命令审批前形成，审批后不得静默改写。
- 无法证明只读且没有隔离 Profile 的命令失败关闭，不进入系统进程表。
- `.gitignore` 不能代替隔离；被忽略的 `build/`、`.build/`、缓存与覆盖率输出仍视为工作区污染。
- 发现意外工作区写入时验证失败并保留证据；Vera 不自动删除目录、恢复文件、取消暂存或修改 `.gitignore`。
- 详细契约、首版 Profile、恢复和清理要求见[验证产物隔离与工作区无污染](2026-09-14-verification-artifact-isolation.md)。

## 视觉、可访问性与终端兼容

- 提供默认、高对比和无色三种内置主题；状态不能只依赖颜色。
- 动画可关闭并尊重 `NO_COLOR`、`TERM=dumb`、`VERA_NO_ANIMATIONS` 和 reduced-motion 配置。
- 60×16 显示安全降级界面，80×24 完成主流程，120×40 展示完整信息层次。
- macOS Terminal.app 为必过环境；iTerm2、Warp、常见 Linux 终端和 Windows Terminal 建立兼容矩阵。
- 鼠标不是必需条件；所有主要流程可以只用键盘完成。
- 文案、边框、宽字符和 emoji 在 CJK/英文 locale 下不重叠、不截断关键审批信息。

## 性能门槛

在项目参考 Intel Mac 和固定离线夹具上：

- 不含 Provider 请求的 TUI 首个可交互帧不超过 1.5 秒；
- 500 个时间线 block 下普通按键到界面响应的 p95 不超过 100 ms；
- 10,000 行折叠工具输出不为每行创建 Widget，展开/折叠不阻塞输入超过 250 ms；
- 流式 Markdown 合并刷新不超过 20 FPS，动画不超过 10 FPS；
- Resize、滚动和持续 stream 同时发生时不丢输入、不重复 block、不改变审批选择。

性能测试必须记录机器与终端环境；其他平台使用相同功能门禁，数值作为比较证据而非无条件硬件承诺。

## 产品验收走查

人工走查至少覆盖：

1. 从陌生工程启动并在不查文档的情况下找到 `/help`、状态和安全边界；
2. 普通对话、`@path`、多行输入、历史搜索和长文本粘贴；
3. 单文件与多文件 Change Set 的 Diff 导航、复制、拒绝和批准；
4. 验证命令审批、成功、失败、取消和恢复；
5. `/doctor`、错误配置、无 Git、只读目录和 Provider 不可用；
6. 小终端、无色、关闭动画、CJK 输入、Resize 和异常退出；
7. TUI、Plain、JSON 和一次性调用对同一场景的语义对照。

走查记录问题严重度、复现步骤、截图或脱敏文本、修复版本和回归证据。不能以“测试通过”替代真实终端观察。

## 阶段六收口门禁

阶段六不能仅凭原任务 0029 的自动测试、PTY、Textual Pilot、快照或 wheel smoke 通过就直接标记 `Complete`；真实使用已经发现的正确性与可靠性问题必须通过任务 0031–0033、任务 0042 和必要复验收口。

任务 0025–0028 合并后，任务 0029 的自动矩阵形成阶段六基线。输入缺失、工具事实错误、审批误导、终端状态损坏、错误失真等问题继续留在阶段六处理；Logo、品牌视觉、信息密度、会话连续性和长期个人使用质感由阶段七承接。

阶段六完成只表示 CLI 功能与可靠性基线成立。它允许进入阶段七 CLI 体验收口，但不表示 CLI 已最终封存，也不授权任何桌面实施。

未经用户在阶段七明确确认「CLI 版本达到预期，可以封存」，不得：

1. 将阶段七标记为 `Complete`；
2. 实施阶段八工具/Policy/Git、阶段九 Core-native Skills，或开始阶段十桌面规划、测量或实现；
3. 引入 Wails、Tauri、Electron 或任何桌面端代码、依赖与 Spike；
4. 用 Textual Pilot、快照或自动测试代替人工体验结论。

确认语句必须由用户在当前对话或书面记录中原文给出；Agent 不得自行改写、推断或用近似措辞代替。

## 阶段退出条件

阶段六关闭前，以下功能与可靠性条件必须成立：

1. 首次启动无需外部教程即可发现输入、帮助、模型、工作区和权限边界；
2. 多行、历史、反向搜索、粘贴、Unicode、外部编辑器和单条排队行为通过测试；
3. `@path` 补全不逃逸 workspace、不跟随不可信链接、不暗示批准；
4. 保留命令全部兼容，新增 7 个命令具有统一 Catalog、帮助和参数校验；
5. 工具/日志、Diff/审批、验证、恢复和失败的信息层次符合规格；
6. Diff 可导航和复制，审批默认安全，过期审批不能继续使用；
7. 取消和退出不会重复副作用，所有退出路径恢复终端状态；
8. TUI、Plain、JSON 和一次性模式的语义、错误和退出码对齐；
9. `/doctor` 能生成可分享的脱敏诊断，配置和异常不泄漏秘密；
10. 三种主题、禁用动画、小终端、CJK 和键盘-only 流程通过；
11. macOS Terminal.app 必过，其他声明支持的终端有清晰兼容结果；
12. 性能门槛通过或有用户明确接受的环境差异记录；
13. 必要的真实终端复验没有未关闭的 Critical/High 正确性或可靠性缺陷；
14. 完整非 live 测试、PTY、Textual Pilot、快照、Ruff、格式、Mypy、构建和 wheel smoke 通过；
15. 自动验收不读取真实 Key、不修改未授权工程、不引入桌面框架或新的 Core 权限；
16. 任务 0031–0033 等阶段六修正已经记录验证结果，且仓库未引入桌面框架代码；
17. 任务 0042 的隔离 Profile、审批绑定、清理和真实 Xcode 回归通过，验证不再在用户 workspace 生成未声明产物。

任务 0029 的既有自动证据保留为基线；任务 0031–0033、任务 0042 与必要复验负责关闭后续发现的正确性和可靠性缺口。

完成后只能进入阶段七 CLI 体验收口。阶段七未获用户封存确认前，阶段八及之后实施都保持 `Not started`，仓库不得出现后续 Core 产品实现或桌面框架代码。

## 参考与关联

- [阶段三：富交互 Terminal UI](2026-09-11-rich-terminal-ui.md)
- [阶段五：Core 安全、权限与可靠性加固](2026-09-12-core-security-and-reliability-hardening.md)
- [验证产物隔离与工作区无污染](2026-09-14-verification-artifact-isolation.md)
- [ADR-0018：验证产物必须在审批前规划并隔离](../decisions/ADR-0018-isolate-verification-artifacts.md)
- [ADR-0009：Textual Terminal UI](../decisions/ADR-0009-textual-terminal-ui.md)
- [ADR-0012：桌面集成延后至 Core 加固与 CLI 产品化之后](../decisions/ADR-0012-delay-desktop-until-cli-hardening.md)
- [ADR-0017：插入 CLI 体验阶段并顺延桌面路线](../decisions/ADR-0017-insert-cli-experience-stage.md)
- [阶段七：CLI 体验收口与个人主力化](2026-09-13-cli-experience-and-personal-dogfood.md)
- [阶段六执行顺序](../tasks/phase-6-execution-order.md)
- [Claude Code CLI 与交互模式](https://docs.anthropic.com/en/docs/claude-code/interactive-mode)
- [Codex CLI Developer Commands](https://developers.openai.com/codex/cli/slash-commands)
- [Gemini CLI Commands](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/commands.md)
- [Gemini CLI Keyboard Shortcuts](https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/keyboard-shortcuts.md)
