# 任务 0033：用户消息、工具块与 tool_call_id

> 供 Cursor 执行：阶段六真实 Terminal.app 走查新发现的三项缺陷。规格条款早已接受，是实现未达成，因此不需要新规格。

**状态：** Done（用户 2026-09-15 指示走查视觉到此为止。七项主路径已过；发现 1–3、8–17、19–34 已复验。TUI 视觉修正留在当前工作树，未提交。不封存阶段六）
**执行就绪：** 否；后续阶段六工作转到任务 0042
**分支：** `phase-6/0033-cli-dogfood-bugs`
**依赖：** 任务 0032 代码已合入当前工作树；不改 0032 的待复验结论
**规格：** [阶段六 CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 背景

用户在真实 Terminal.app 继续走查，报告三条可复现问题：

1. 提交「你好vera」后时间线看不到自己发出的内容，助手回复正常。
2. `list_directory` 占很多行，展开后正文为空。
3. 简单「列出文件」失败：`provider_request_invalid · HTTP 400 · messages[1]: missing field tool_call_id`。

第 3 条同时定性了 [走查发现 3](../evals/phase-6-manual-walkthrough.md)：失败发生在工具结果写回后的下一轮模型请求，属于 Core 请求构造错误，不是 Key/余额问题。

## 目标与边界

让提交后的用户原文出现在时间线；让只读工具块显示动作、目标、状态和耗时，展开有摘要而不是空白；让压缩掉旧工具结果时不再发出缺少 `tool_call_id` 的 `role=tool` 消息。

不新增 Core 权限，不把用户目标写进公共 `run.started`（仍只发 `goal_hash`），不引入桌面端，不读取 Provider Key，不放宽审批边界，不把阶段六标为 Complete。

## 实施步骤

### 1. 压缩占位不得破坏 tool 协议

**修改：**

- `src/vera/runtime/context.py`
- `src/vera/models/openai_compatible.py`
- `tests/runtime/test_message_compaction.py`
- `tests/models/test_openai_errors.py`

**缺陷：** `compact_run_messages` 丢掉旧工具结果后，在 `system` 后插入一条 `role="tool"` 且没有 `tool_call_id` 的占位。DeepSeek 将 `messages[1]` 判为非法。同时，被丢掉的 tool 结果若仍挂在先前 `assistant.tool_calls` 上，请求也不成对。

**要求：** 占位不得使用无 id 的 `tool`；被丢掉的 `tool_call_id` 必须从对应 assistant 的 `tool_calls` 中剥离。适配器发送 `role=tool` 时必须带 `tool_call_id`，缺 id 的 tool 消息不得发出。

### 2. 提交后保留用户消息副本

**修改：**

- `src/vera/session/controller.py`
- `src/vera/presentation/projector.py`
- `src/vera/cli_session.py`
- `tests/session/test_controller.py`
- `tests/presentation/test_projector.py`

**缺陷：** `project_user_prompt()` 从未被调用；`run.started` 按契约不含 `goal` 原文。时间线因此只有助手块。

**要求：** `SubmitPrompt` 实际开跑前发出 `session.user_prompt`；TUI 投影为 `BlockKind.USER`；Plain 写出「你：…」。失败、取消或审批等待不得丢掉这条已提交原文。

### 3. 工具摘要含目标、耗时与可展开正文

**修改：**

- `src/vera/runtime/engine.py`
- `src/vera/presentation/event_copy.py`
- `src/vera/presentation/projector.py`
- `src/vera/cli_presenter.py`
- `tests/presentation/test_projector.py`

**缺陷：** 工具标题仍是 `list_directory · completed`；`tool.completed` 公共 payload 不含结果正文，投影去读 `result` 得到空串。

**要求：** `tool.started` / `tool.completed` 增加可选 `target`（路径或查询），不改已有字段语义。标题为动作、目标、状态和耗时；展开正文为同样摘要，不铺目录或文件正文。同类只读工具保持各 Event 一块，不得合并到看不到单次调用。

### 4. 走查与状态记录

**修改：**

- `docs/evals/phase-6-manual-walkthrough.md`
- `docs/STATUS.md`
- `docs/tasks/phase-6-execution-order.md`
- 本任务文件

发现 3 标为代码已修、待 Terminal.app 复验列文件。新增发现 8（用户消息缺失）、发现 9（工具块为空）同样待复验。不把任务 0029 或阶段六标为 Complete。

### 5. 分析项目结构：整轮回传思考与工具

**修改：**

- `src/vera/runtime/context.py`
- `src/vera/runtime/engine.py`
- `src/vera/models/openai_compatible.py`
- `tests/runtime/test_message_compaction.py`
- `tests/models/test_openai_errors.py`
- `tests/models/test_openai_stream.py`

**缺陷：** 「列出文件」复验通过，但「分析项目结构」在大量并行工具后仍 400。压缩按最后 8 条 tool 裁剪，并在每条工具结果后立刻压缩；同一轮 `assistant.tool_calls` 被拆成残缺思考消息，DeepSeek 思考模式拒绝。流式块有时把 `reasoning_content` 放在 extras / `choice.message`。

**要求：** 压缩按完整工具轮次丢弃旧轮，最新一轮的 `reasoning_content` 与全部 `tool_calls` 必须原样保留；只在一轮工具跑完后压缩。适配器从 extras 和 `choice.message` 读取思考字段。不关闭 thinking。

### 6. 重复工具守卫只计连续调用

**修改：**

- `src/vera/runtime/engine.py`
- `src/vera/runtime/context.py`
- `tests/runtime/test_limits.py`

**缺陷：** 「分析项目结构」过了 400 后，读完若干文件以 `repeated_tool_call` 失败。规格要求参数完全相同的**连续**三次才停；实现按整次运行累加，隔了别的工具再 `list_directory` / `read_file` 同一路径也会误杀。

**要求：** 仅当相邻两次工具的 name+arguments 完全相同才累加；中间插入不同调用则重置。三次连续相同仍失败。不放宽 `max_tool_calls` / `max_model_turns`。

### 7. `/exit` 必须离开 TUI

**修改：**

- `src/vera/terminal/app.py`
- `tests/terminal/test_app.py`

**缺陷：** 输入 `/` 补全后提交 `/exit`，只投影「会话已关闭」，全屏 TUI 不拆除。规格要求退出会话；Plain 因循环检查 `exit_requested` 会回到 shell，TUI 漏了 `app.exit`。

**要求：** 收到 `session.closed` 后以退出码 0 结束 Textual 应用，回到原终端。`/quit` 与有未决审批时先取消再退出的现有 Core 语义不变。

### 8. 工具次数用尽后先作答；TUI 可复制

**修改：**

- `src/vera/runtime/engine.py`
- `src/vera/terminal/app.py`
- `src/vera/session/diagnostics.py`
- `tests/runtime/test_limits.py`
- `tests/terminal/test_app.py`

**缺陷：** 分析项目在约 50 次只读工具后 `max_tool_calls` 硬失败。TUI 无法把失败文案复制到系统剪贴板（Terminal.app 不支持 OSC 52）。

**要求：** 未写入工作区时，次数用尽后给模型一轮无工具请求，根据已有证据作答；已有写入或作答仍要工具则仍失败。复制走 macOS `pbcopy`，并提供 Cmd+C / Ctrl+Shift+C。不提高默认 50 的安全上限。

### 9. 助手回答渲染 Markdown

**修改：**

- `src/vera/terminal/widgets/blocks.py`
- `tests/terminal/test_blocks.py`

**缺陷：** 助手结论按 `Text(body)` 原样画出，`#`、`**`、列表和代码围栏都看得见。阶段三规格要求 `AssistantMessageBlock` 渲染 Markdown。

**要求：** TUI 助手块用 Rich Markdown 显示标题、强调、列表和代码；不把模型正文当 Rich markup 解析。工具、日志、错误、用户块仍为转义纯文本。Plain 模式保持原文。

### 10. 助手回答可鼠标拖选

**修改：**

- `src/vera/terminal/widgets/blocks.py`
- `tests/terminal/test_blocks.py`

**缺陷：** 助手块包在 `Collapsible` 里，标题组件 `ALLOW_SELECT=False`。正文又用 `Static.update(Markdown)`，Textual 把它变成 `RichVisual`；`get_selection()` 只提取 `Text`/`Content`，所以点选、拖选都没有选区。

**要求：** 用户/助手/错误块不再包 `Collapsible`。助手 Markdown 先渲成 Rich `Text`（进而变成可选取的 `Content`）。拖选结束写入 macOS 剪贴板，不依赖 Terminal.app 的 Cmd+C。折叠工具块保持原样。不新增斜杠复制命令。

### 11. `search_text` 可搜单个文件

**修改：**

- `src/vera/tools/filesystem.py`
- `src/vera/tools/builtin.py`
- `tests/tools/test_filesystem.py`

**缺陷：** 分析 Xcode 工程时模型对 `.pbxproj` 调用 `search_text`，实现只接受目录，返回 `not_a_directory`。中间工具失败但不阻断最终作答。

**要求：** `path` 是文件时只搜索该文件；是目录时保持递归搜索。不存在则 `not_found`。不放宽 workspace 边界。

### 12. 斜杠补全高亮并回车执行

**修改：**

- `src/vera/terminal/widgets/completions.py`
- `src/vera/terminal/widgets/composer.py`
- `src/vera/terminal/theme.tcss`
- `tests/terminal/test_completions.py`
- `tests/terminal/test_composer.py`

**缺陷：** 输入 `/` 只列出命令，没有选中态；回车提交的是当前残缺输入，不能直接执行匹配项。

**要求：** 前缀过滤时自动高亮第一项；上下键改选；回车执行选中命令。已输入完整命令名（可带参数）时仍提交原文。补全仍只来自 Catalog。

### 13. 状态默认可读，同类归并出层级

**修改：**

- `src/vera/presentation/disclosure.py`
- `src/vera/presentation/event_copy.py`
- `src/vera/presentation/projector.py`
- `src/vera/terminal/widgets/blocks.py`
- `src/vera/terminal/widgets/timeline.py`
- `tests/presentation/test_disclosure.py`
- `tests/presentation/test_projector_extra.py`
- `tests/terminal/test_disclosure.py`
- `tests/terminal/test_blocks.py`

**缺陷：** 走查里多数状态卡默认折叠，要点开才看得到正文；相邻工具/状态又全部摊成同级卡片，没有组标题，信息层次看不清。

**要求：** `STATUS` 默认展开且不包 `Collapsible`。相邻 `TOOL` / `LOG` / `STATUS` 收入带标题的视觉组；工具/日志组默认折叠，失败自动展开组；状态组默认展开。每个权威 Event 仍是独立子块，不得合并丢掉。

### 14. 斜杠补全列出全部匹配且输入过程保持可见

**修改：**

- `src/vera/terminal/widgets/completions.py`
- `src/vera/session/command_catalog.py`
- `src/vera/terminal/theme.tcss`
- `tests/terminal/test_completions.py`
- `tests/terminal/test_composer.py`

**缺陷：** 输入 `/` 只渲染 Catalog 前 8 条，`/doctor` `/theme` `/exit` 被裁掉；滤到 1 条时整行 `reverse` 高亮，在 Terminal.app 里看起来像提示消失。

**要求：** 补全保留全部前缀匹配，窗口滚动而不是丢弃；标题行始终可见；选中行用强调色底（不是只加粗）。无匹配时显示「没有匹配的命令」，不要整层收起。弹层已打开时，即使输入法或光标吃掉 `/`，只要还能匹配到命令就补回 `/` 并保持可见。回车执行命令后必须收起弹层。

### 15. 默认主题改深蓝主色

**修改：**

- `src/vera/terminal/theme.py`
- `src/vera/terminal/widgets/completions.py`
- `tests/terminal/test_theme.py`

**要求：** 用户批准后，默认主题改为 `primary #1B4F8A`、`secondary #0F2C4C`、`accent #2A5F9E`、`warning #C4A35A`。补全选中行改为浅蓝字深蓝底。启动时实际套用 Vera `default` 主题，输入框用圆角边框，不用 Textual `tall` 边框和滚动条槽。高对比、无色、Diff、成功/失败色不动。不启动阶段七、不画 Logo。

### 16. `@` 选文件后回车必须插入路径；提交后跟底、可输入、滚轮不漏到终端

**修改：**

- `src/vera/terminal/widgets/completions.py`
- `src/vera/terminal/widgets/composer.py`
- `src/vera/terminal/widgets/timeline.py`
- `src/vera/terminal/app.py`
- `src/vera/terminal/theme.tcss`
- `tests/terminal/test_completions.py`
- `tests/terminal/test_composer.py`
- `tests/terminal/test_app.py`
- `tests/terminal/test_scrolling.py`

**缺陷：** 路径补全弹层已列出文件，回车却提交光秃 `@`。`accept()` 只处理 slash/theme。提交后时间线不跟底；焦点被时间线或审批块抢走后无法继续输入；滚轮在边缘未消费，Terminal.app 滚出 TUI 露出原 shell。

**要求：** 路径模式下回车用选中项的 `display` 替换最后一个 `@fragment`，并加尾空格，不提交。第二次回车才发送完整 `@path`。完成后的 mention（含空格）不再弹层。提交与 run 结束（无未决审批）把焦点还回输入框并 `return_to_tail`。时间线与 App 消费滚轮，Screen `overflow: hidden`。不把裸 `@` 发给模型。路径中的 `/` 不得触发斜杠补全，也不得把输入改写成 `/文件名` 当未知命令提交。

### 17. 任务结束后 `/diff` 必须展示最近一次权威 Diff

**修改：**

- `src/vera/session/queries.py`
- `src/vera/session/controller.py`
- `src/vera/presentation/projector.py`
- `src/vera/presentation/event_copy.py`
- `tests/session/test_queries.py`
- `tests/session/test_controller.py`
- `tests/presentation/test_projector.py`

**缺陷：** `/diff` 无 run-id 时只回落到 `_active_run_id`。任务一结束该值为 None，且 `None == None` 会误读已清空的内存事件。`session.diff` 又被画成「状态更新」，`files: []` 显示「文件数：无」，「没有 Diff。」被隐藏。

**要求：** 无参数时依次使用待审批 run、否则最近一次已记录 run。有 Change Set 则投影为 Diff 块（含路径与 unified diff）；没有则明确写「没有 Diff。」。不扫描工作区 Git，不绕过审批。

### 18. `/clear` 必须清掉 TUI 时间线；`/new` 确认可见

**修改：**

- `src/vera/session/controller.py`
- `src/vera/presentation/projector.py`
- `src/vera/presentation/status_panel.py`
- `src/vera/cli_session_presenter.py`
- `src/vera/presentation/activity.py`
- `src/vera/terminal/widgets/timeline.py`
- `src/vera/terminal/app.py`
- `tests/terminal/test_app.py`
- `tests/presentation/test_projector.py`
- `tests/cli/test_session.py`

**缺陷：** `/new` 与 `/clear` 只重置会话上下文并追加 `session.message`。Plain 模式 `/clear` 会 `io.clear()`，TUI 从不拆时间线，看起来像没执行。

**要求：** `/clear` 清空投影与时间线后，把启动状态面板放在时间线顶部（版本/Model/Workspace/Git/Session/Context/Approval/Execution），确认文案可在其下或状态栏；不要跟到底部。`/new` 按规格保留时间线，但状态栏必须出现「已开始新会话」。两者都清空排队输入。不改 `Ctrl+R` / `Ctrl+G`。

### 19. `/theme` 必须真正换肤

**修改：**

- `src/vera/terminal/theme.py`
- `src/vera/terminal/theme.tcss`
- `src/vera/terminal/app.py`
- `src/vera/session/controller.py`
- `tests/terminal/test_theme.py`
- `tests/session/test_controller.py`

**缺陷：** `/theme` 报告成功，但只给 Screen 加 CSS 类，不设置 Textual `App.theme`。输入框等硬编码深蓝边框，`$accent`/`$background` 仍是启动主题，界面看起来没换。

**要求：** 切换时设置 `App.theme` 并立刻 `refresh_css`。`theme.tcss` 的 Screen/输入框走 `$background`/`$accent`，高对比/无色同时匹配 `.theme-*` 与 Textual 的 `.-theme-*`。高对比内容区用单线 `solid` 白框，不用 `tall`（`tall` 会在白框外混出半块线）。确认写在时间线与状态栏，不写配置、不加载外部主题代码。

### 20. Alt+Enter 插入换行，输入框进入多行

**修改：**

- `src/vera/terminal/alt_enter.py`
- `src/vera/terminal/widgets/composer.py`
- `src/vera/terminal/app.py`
- `src/vera/session/diagnostics.py`
- `tests/terminal/test_composer.py`
- `tests/terminal/test_alt_enter.py`
- `tests/terminal/test_app.py`

**缺陷：** 规格要求可识别的修饰键回车插入换行。真实 Terminal.app 的 Option+Enter 发送 `ESC`+`CR`，Textual 把它收成普通 `enter`，因此 Alt+Enter 会提交。Shift/Cmd+Enter 在 Terminal.app 里与回车无法区分。输入框固定 1 行且 `overflow-y: hidden`，插入换行后也看不见多行。误提交后队列回填光标在开头，看起来像积压错乱。

**要求：** 只把 `Alt+Enter`（Terminal.app 为 Option+Enter）和兼容路径 `Ctrl+J` 当作换行。裸 `Enter` 始终提交整段多行。输入框随行数升高（最多 5 行正文）。被拒绝的草稿回填时光标在末尾。不改 `Ctrl+R` / `Ctrl+G`。队列仍只允许一条。不把 Shift/Cmd+Enter 宣传为换行。

### 21. Diff 可拖选并复制纯文本

**修改：**

- `src/vera/terminal/widgets/blocks.py`
- `src/vera/terminal/app.py`
- `tests/terminal/test_blocks.py`
- `tests/terminal/test_app.py`

**缺陷：** Diff 包在 `Collapsible` 里（标题 `ALLOW_SELECT=False`），正文 `Static.update(Syntax)` 变成 `RichVisual`，`get_selection()` 提不出文本。Cmd+C 回退也不包含 Diff 块。

**要求：** Diff 与助手块一样用可选取的 `Text`/`Content` 渲染，保留增删着色。拖选松手写入剪贴板；无选区时 Cmd+C / Ctrl+Shift+C 复制最近一块可复制文本（含 Diff）。复制内容为纯文本，不含控制序列。不改审批默认 Cancel、不改审批中禁止新任务。

### 22. 审批 Tab 只在 Cancel/Reject/Approve 间循环

**修改：**

- `src/vera/terminal/widgets/approval.py`
- `src/vera/terminal/app.py`
- `src/vera/terminal/widgets/timeline.py`
- `tests/terminal/test_approval.py`

**缺陷：** 审批出现后 Tab 在时间线、输入框和整页控件间跳转，不在三个决定按钮间循环。只有 Cancel 是 `primary`，焦点到 Reject/Approve 时外观不变。

**要求：** 有未决审批时 Tab / Shift+Tab 只在 Cancel → Reject → Approve 间循环。当前焦点按钮为 `primary`，其余为 `default`。默认仍落在 Cancel。Enter 激活当前按钮。不给 Approve 绑定单字母。

### 23. `/recover` 列出分类，启动提示待恢复

**修改：**

- `src/vera/presentation/event_copy.py`
- `src/vera/presentation/errors.py`
- `src/vera/presentation/projector.py`
- `src/vera/presentation/activity.py`
- `src/vera/session/controller.py`
- `src/vera/terminal/app.py`
- `tests/presentation/test_projector.py`
- `tests/presentation/test_activity.py`
- `tests/presentation/test_errors.py`
- `tests/presentation/test_event_copy.py`
- `tests/terminal/test_app.py`
- `tests/cli/test_recovery_inspection.py`

**缺陷：** TUI `on_mount` 不消费 `bootstrap_events()`，强制退出后再进看不到待恢复。`/recover` 的 `recovery.detected` 被投影成失败卡，只读 `reason`/`message`，忽略 `reason_code`，因此「原因未记录」；活动状态把检查当成「正在恢复」。

**要求：** 启动时间线包含待恢复提示并指向 `/recover`。`/recover` 每条待恢复任务显示 run-id、分类、原因和下一步 `/resume` 或 `/abandon`，不得写成空失败卡。只读检查不得把状态栏打成进行中的恢复。不自动 `/resume`。

### 24. `/doctor` `/config` 投影完整诊断，不折叠成计数

**修改：**

- `src/vera/presentation/diagnostics_copy.py`
- `src/vera/presentation/projector.py`
- `src/vera/presentation/errors.py`
- `src/vera/cli_session.py`
- `tests/presentation/test_diagnostics_copy.py`
- `tests/presentation/test_projector_extra.py`
- `tests/presentation/test_errors.py`
- `tests/terminal/test_app.py`
- `tests/cli/test_plain_session.py`

**缺陷：** 走查 5A 中 TUI 把 `session.doctor` / `session.config` 走通用 `event_summary`。诊断卡丢掉每项 `pass`/`warning`/`fail`/`unavailable`，只拼 `detail`；配置卡把字典收成 `sources: 4` / `limits: 8` / `providers: 1`，看不到脱敏值。只读失败文案留下裸 `permission_denied`。Core payload 本身已有状态和脱敏值，JSON 未泄漏 Key。

**要求：** `/doctor` 人类输出每项 `name status detail`。`/config` 列出 sources、providers（模型 / base_url / `api_key_env` 名）、limits、editor、ui 的脱敏值，不得显示计数摘要或 Key。`permission_denied` 译为「没有写入权限」并保留 code。不改 Core `doctor_report` / `redacted_config_view` 字段。

### 25. Plain 不打印静默模型往返事件名

**修改：**

- `src/vera/cli_presenter.py`
- `tests/cli/test_presenter.py`

**缺陷：** 走查 7B 中 `--plain` 把 `model.requested` / `model.completed` 原样打出。TUI 已把这些类型标为静默；HumanPresenter 未处理时回落到 `event.type`。

**要求：** Plain / `vera run` 人类输出跳过 `SILENT_EVENT_TYPES`。未知事件用人类标题，不得打印事件类型标识。JSON 协议仍输出完整事件。

### 26. 未写入时 Diff 不得看成已更改

**修改：**

- `src/vera/presentation/projector.py`
- `src/vera/session/controller.py`
- `tests/presentation/test_projector.py`
- `tests/session/test_controller.py`

**缺陷：** 只读失败时磁盘 `notes.md` 未改，TUI 仍留下提案 Diff，看起来像已经改过。失败卡本身应写「未产生工作区变化」，但 Diff 标题仍是普通 `Diff · N files`。

**要求：** 未观察到 `changeset.applied` 时，失败/取消把该 run 的 Diff 标为「未写入」；`/diff` 正文前缀「这是提案 Diff，未写入工作区。」已写入的 Diff 保持原样。不把提案绿行当成工作区事实。

### 27. `vera run` 的 model_profile 与交互式一致

**修改：**

- `src/vera/cli.py`
- `tests/cli/test_run.py`

**缺陷：** 走查 7D 中 `vera run --json` 的 `run.started.model_profile` 为 `default`，TUI/Session 为 `deepseek`。`execute_run` 在未传 `--model` 时写死 `"default"`，交互式用第一个已配置供应商名。

**要求：** 一次性调用与交互式相同：未指定时用 `next(iter(config.providers), "default")`。实际供应商选择仍走 `build_runtime`。

### 28. 输入框左侧提示符；审批卡上下空白

**修改：**

- `src/vera/terminal/widgets/composer.py`
- `src/vera/terminal/app.py`
- `src/vera/terminal/theme.tcss`
- `src/vera/terminal/widgets/approval.py`
- `src/vera/terminal/widgets/blocks.py`
- `tests/terminal/test_composer.py`
- `tests/terminal/test_theme.py`
- `tests/terminal/test_approval.py`

**缺陷：** 输入框没有终端式提示符，光标贴在左边框上。审批卡夹在状态组与后续块之间时，Collapsible 底边距、组 margin 和默认 3 行高按钮会上下各空出打断阅读的空白。

**要求：** 输入框左侧固定 ASCII `>`，不属于提交正文。圆角边框包住提示符和编辑区。审批卡上下 margin 为 0；组内 Collapsible 去掉顶部分隔线和底 padding；审批按钮单行无 tall 边框。不改审批默认 Cancel、不改 Tab 循环。用户消息悬浮与底栏上下文占用仍不动，等规划。

### 29. 审批卡完整显示；刚滚走的用户消息悬浮

**修改：**

- `src/vera/presentation/timeline.py`
- `src/vera/presentation/projector.py`
- `src/vera/terminal/widgets/approval.py`
- `src/vera/terminal/widgets/blocks.py`
- `src/vera/terminal/widgets/user_sticky.py`
- `src/vera/terminal/widgets/timeline.py`
- `src/vera/terminal/app.py`
- `src/vera/terminal/theme.tcss`
- `tests/presentation/test_timeline.py`
- `tests/presentation/test_projector.py`
- `tests/terminal/test_approval.py`
- `tests/terminal/test_scrolling.py`

**缺陷：** 审批按钮仍带 Textual 默认 `min-width: 16`、`line-pad: 1` 和 tall 边框，压成 1 行后标题/正文/Cancel·Reject·Approve 被裁切。用户消息上滑后消失，右侧也没有时间。

**要求：** 审批卡完整露出正文每一行和三个按钮，按钮单行且无 tall 边框，仍默认 Cancel。用户块右侧显示本地 12 小时制时间（如 `9:21 PM`），字色为偏暗灰色。时间线里每一条用户消息都是深蓝填充条：左侧 `>`、正文、右侧时间；无蓝色描边；上下内边距各 1 格（约 10px），单行高度至少 3；卡片外上下各留 1 行、左右各留 2 列；宽度撑满时间线同一列，不随正文长短收缩。填充用实色 `$secondary`。刚滚走出视口的用户正文以同样填充条叠在时间线上方，不移动顶栏。再滚到下一条则替换；滚回可见则收起。Textual 滚动条是占位槽而不是 overlay：时间线 `overflow-y: auto` 且 `scrollbar-size-vertical: 0`，不侵占内容列；滚轮与键盘仍可滚动。时间线块、用户卡片与输入框左右各留 2 列，互相对齐，不得贴齐窗口左缘。助手标题 `▼ 助手` 与正文同一左缘。用户卡片正文为更亮的白字，助手正文略暗，形成 Grok 式层次。输入框圆角边框内的编辑区与提示符无独立底色。自动折行与 Alt+Enter 换行都会升高输入框（最多 5 行正文），不得只显示当前行。不实现底栏上下文占用、状态收敛或 Skills。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest tests/runtime/test_message_compaction.py tests/models/test_openai_errors.py tests/presentation/test_projector.py tests/session/test_controller.py tests/presentation/test_event_copy.py tests/terminal/test_theme.py tests/terminal/test_composer.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git diff --check
```

## 验收标准

- 压缩后的消息里，任何 `role=tool` 都有非空 `tool_call_id`；assistant 的 `tool_calls` 只引用仍存在的 tool 消息。
- 适配器发出的 JSON 中，`role=tool` 必含 `tool_call_id`。
- 提交自然语言后时间线出现用户块，正文为提交原文。
- 成功的 `list_directory` 展开后含目标与状态，不是空串；标题不含内部事件类型名。
- 状态卡默认可读；相邻同类工具/状态归入组标题下，单次 Event 仍可单独查看。
- 输入 `/` 能列出全部 Slash Command；继续输入时补全层保持可见，可用 ↑↓ 滚到窗口外的匹配项。选中行有强调色；回车执行后弹层消失。
- 默认主题主色为深蓝：`#1B4F8A` / `#0F2C4C` / `#2A5F9E`，警告为 `#C4A35A`。
- 输入 `@` 并选中文件后回车，输入框变为 `@相对路径 `，不提交；再回车才发送完整 mention。
- `@dir/file 分析此文件` 作为普通任务提交，不得变成「未知命令：/file」。
- 任务结束后无参数 `/diff` 展示最近一次 run 的权威 Diff；没有 Change Set 时写「没有 Diff。」，不得显示「文件数：无」。
- `/clear` 清空 TUI 时间线后，顶部为启动状态面板；`/new` 保留时间线并在状态栏确认新会话。
- `/theme default|high-contrast|no-color` 立即改变输入框边框和画布颜色；高对比内容区为单线白框，框外无多余线条；未知名拒绝且不写配置。
- `Alt+Enter` 插入换行且不提交；自动折行与硬换行都会升高输入框；裸 Enter 提交多行正文；被拒绝的草稿回填后光标在末尾。
- Diff 可拖选；无选区 Cmd+C 复制最近一块（含 Diff）纯文本。
- 未决审批时 Tab 只在 Cancel/Reject/Approve 间循环，当前项外观为 primary。
- 强制退出后再进，首屏可见待恢复提示；`/recover` 列出 run-id、分类与 `/resume` 或 `/abandon`，不是「原因未记录」。
- `/doctor` 人类输出含每项 `pass`/`warning`/`fail`/`unavailable`；`/config` 显示来源和脱敏值，不是字典计数。
- Plain / `vera run` 人类输出不打印 `model.requested` 等静默事件类型名。
- 未写入的提案 Diff 标题含「未写入」；`/diff` 写明未写入工作区。
- `vera run --json` 未指定 `--model` 时 `model_profile` 为已配置供应商名，不是字面 `default`。
- 输入框左侧可见 `>`，提交正文不含该符号。
- 审批卡完整显示正文与 Cancel / Reject / Approve，间隙不超过 1 行；按钮高度为 1。
- 用户消息右侧有本地 12 小时制时间（AM/PM），字色偏暗灰；时间线与悬浮条均为 `$secondary` 填充条，无蓝色描边，上下内边距各 1 格，与输入框左右各留 2 列并对齐；用户正文比助手更亮，助手标题与正文左缘对齐，不移动顶栏。
- 时间线滚动条不占内容列（`scrollbar-size-vertical: 0`）；输入框编辑区无独立底色。
- 完整非 live、Ruff、格式、Mypy 与 `git diff --check` 通过；阶段六仍为 Ready for manual acceptance。

## 收口记录

用户 2026-09-15 指示「走查视觉先停，进行 0042，0033 到此为止」。本任务停止新的视觉走查与视觉改动。正确性项（用户消息、工具块、`tool_call_id`、Slash/路径、诊断命令、主题、审批 Tab、恢复文案）已复验。TUI 视觉修正保留在未提交工作树，不单独封存阶段六。后续阶段六工作转到任务 0042。
