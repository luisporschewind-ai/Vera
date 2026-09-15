# 阶段六人工产品走查

> 后续关系：[ADR-0017](../decisions/ADR-0017-insert-cli-experience-stage.md) 保留本表作为阶段六缺陷复验和阶段七 dogfood 输入；最终 CLI 封存确认归入阶段七，不再作为阶段六完成条件。

**规格：** [CLI 产品化与体验完善](../specs/2026-09-12-cli-productization-and-polish.md)  
**任务：** [0029](../tasks/0029-phase-6-product-acceptance.md)  
**日期：** 2026-09-16
**结果：** 第 1–7 项主路径已过；发现 1–37 中 High 均已复验。阶段六基线走查完成；封存确认归阶段七。

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
| 实际 | 部分走查。首屏八行状态（版本、模型、规范化工作区、Git 状态、会话、上下文、审批模式、`current user · no OS sandbox`）正常呈现；`/help` 按六组显示且七个阶段六新增命令均可见。`vera --version` 复验通过：`vera 0.1.0+1412a33.dirty`，editable，路径指向仓库 `src/vera`。 |
| 严重度 | 发现 1 已复验通过 |
| 证据 | `/help` 输出含「开始/会话/代码与证据/恢复/安全/外观」六组与 `/diff` `/review` `/doctor` `/config` `/usage` `/shortcuts` `/theme`；`vera --version` 在 `~/Desktop/VeraTestDemo` 打出发行版本、短 commit、editable 路径 |

## 2. 输入与引用

| 字段 | 内容 |
|---|---|
| 环境 | macOS Terminal.app；`~/Desktop/VeraTestDemo` |
| 步骤 | 普通对话、`@path`、多行、历史搜索、长粘贴、外部编辑器、单条队列 |
| 预期 | 输入不丢失、粘贴不误提交、审批中不能排队、`@path` 不逃逸 workspace、不暗示批准 |
| 实际 | 主路径已走查。输入 `/` 弹出命令提示，可用；普通对话（「你好」）收到模型回复，对话闭环可用。`@` 选文件回车插入路径；补上任务后作为普通请求处理，不再误当成斜杠命令。上下滚动不再露出原终端；点击时间线后再打字可继续输入。粘贴多行不自动提交。Option+Enter（Alt+Enter）插入换行，输入框升高，裸 Enter 提交整段。运行中单条队列无问题。`Ctrl+R` / `Ctrl+G` 按用户决定不进主线。 |
| 严重度 | 发现 2、3、8–15、26 已复验通过 |
| 证据 | 用户在 Terminal.app 的直接观察 |

## 3. Diff 与审批

| 字段 | 内容 |
|---|---|
| 环境 | macOS Terminal.app；`~/Desktop/VeraTestDemo` |
| 步骤 | 单文件与多文件 Diff 导航、复制、拒绝、批准、过期审批 |
| 预期 | Diff 可导航可复制；默认焦点安全；过期审批不能继续使用 |
| 实际 | 主路径已走查。单文件写入、默认 Cancel、Reject 后再 Approve、事后 `/diff` 已过。多文件 Diff：`Diff · 2 files` 同时显示 `notes.md` 与 `walk-a.md` 的增减。审批中输入回车不会发出新任务。过期审批：工作区文件在等待期间被改后 Approve，提示过期且不按旧提案写入。Diff 可拖选复制。 |
| 严重度 | 发现 24、27 已复验通过 |
| 证据 | 用户在 Terminal.app 的直接观察；仓库内 `notes.md` 内容为 `hello` |

## 4. 验证、取消与恢复

| 字段 | 内容 |
|---|---|
| 环境 | macOS Terminal.app；`~/Desktop/VeraTestDemo` |
| 步骤 | 验证成功/失败、取消、恢复、回滚 |
| 预期 | 终态文字不混淆；取消不重复副作用；恢复/回滚有明确事实 |
| 实际 | 已走查。Ctrl+C 取消、回滚、审批 Tab、强制退出后的待恢复提示与 `/recover`/`/abandon` 已过。4A 验证成功已过（`test -f vera-walkthrough-verify.txt`）。4B 验证失败已过。2026-09-15 用户删除既有 `build/` 后，用 `vera 0.1.0+940bd29` 在 Terminal.app 对 `ViewController.swift` 按钮文案做小改并批准 `xcodebuild`：验证 `passed`/`exit_code=0`，最终 argv 含 `-derivedDataPath /private/tmp/vera-verification/.../000/DerivedData`，工程根未再生成 `build/`，精确产物根 `.../000` 已清理。TUI 命令审批卡当时只显示 `verification_0` / 「执行验证命令」，看不到最终 argv（发现 36）。2026-09-16 用已落地的 projector/Presenter 再走一张 command 卡（`run_54d549ca3e9d4e578f65443fb8f7302e`）：卡上出现 `命令 xcodebuild ... -derivedDataPath /private/tmp/vera-verification/f6f5956b5edf/run_54d549ca3e9d4e578f65443fb8f7302e/000/DerivedData`、`Profile xcode`、`产物根 .../000`、`工作目录 .`，默认焦点 Cancel；用户 Reject 后 `Verification · failed` / `rejected`，任务 `verification_failed`。工程根仍无 `build/`。Git 索引里仍有旧 `AD build/`，未取消暂存。 |
| 严重度 | 发现 28–30 已复验通过；4A、4B 通过；发现 35 隔离复验通过；发现 36 审批展示复验通过 |
| 证据 | 用户 Terminal.app 截图（changeset + command 批准、`Verification · passed`、任务完成；2026-09-16 command 卡含命令/Profile/产物根后 Reject）；Journal `run_187c2fe2abf94d7a91d35d790bb55568`、`run_54d549ca3e9d4e578f65443fb8f7302e`；磁盘无 `~/Desktop/VeraTestDemo/build` |

## 5. 诊断与异常环境

| 字段 | 内容 |
|---|---|
| 环境 | macOS Terminal.app；`~/Desktop/VeraTestDemo` |
| 步骤 | `/doctor`、错误配置、无 Git、只读目录、Provider 不可用 |
| 预期 | 每项有 `pass`/`warning`/`fail`/`unavailable`；不泄漏秘密；错误可行动 |
| 实际 | 已走查 5A–5E。5A 复验通过：`/doctor` 六项均有 `pass`/`warning`；`/config` 列出 sources 与脱敏值，仅环境变量名。5B：坏 TOML 与工程 forbidden key 均未进会话，`exit=5`。5C：无 Git 顶部路径正确，`/doctor` 显示 `not a repository`。5D：只读写入失败，提示 `任务失败：permission_denied`。5E：取消 Key 后未进会话，输出 `missing_provider_config: no model provider configured`，未见 Key。 |
| 严重度 | 发现 31、32 已复验通过；5A–5E 通过 |
| 证据 | 用户复验截图（5A）；用户粘贴的 5B/5E 终端输出；用户对 5C/5D 的直接观察 |

## 6. 终端兼容

| 字段 | 内容 |
|---|---|
| 环境 | macOS Terminal.app；`~/Desktop/VeraTestDemo` |
| 步骤 | 小终端、无色、关闭动画、CJK、Resize、异常退出 |
| 预期 | 关键审批信息不截断；退出恢复终端；不依赖颜色传达状态 |
| 实际 | 已走查。`/theme default` / `high-contrast` / `no-color` 立即换肤；高对比内容区为单线白框。6A 小终端已过。6B：`TERM=dumb vera` 未进 TUI，提示使用 `--plain` 或 `--json`，`exit=2`。5E 后平常 `vera` 仍可进入。6C：`VERA_NO_ANIMATIONS=1` 用户确认无问题。6D：中文输入与回答无乱码、提交未丢字。6E：拖窗口用户确认时间线/输入框不碎、不露出原终端，仍可输入。6F：`/exit` 后终端干净，再开 `vera` 正常。 |
| 严重度 | 发现 17、21 已复验通过；6A–6F 通过 |
| 证据 | 用户在 Terminal.app 的直接观察；用户粘贴的 6B 终端输出；用户 6D 截图 |

## 7. 四种入口语义对照

| 字段 | 内容 |
|---|---|
| 环境 | macOS Terminal.app；`~/Desktop/VeraTestDemo` |
| 步骤 | 同一场景分别走 TUI、`--plain`、`--json`、`vera run` |
| 预期 | 命令、审批、错误 code、终态和退出码语义一致；JSON 不混入 ANSI |
| 实际 | 已走查。7A：TUI「列出当前目录」有工具与中文终态。7B：`--plain` 为 `Vera >` 逐行模式，同一句可完成。7C：`vera --json` 为 NDJSON Session 记录，含 `model.requested`，`exit=0`。7D：`vera run` 人类输出有任务开始/工具/回答/任务完成，无 `model.requested`，`exit=0`；`vera run --json` 为裸 Event 行、含模型往返、无 ANSI、`exit=0`。复验后一次性 JSON 的 `model_profile` 为 `deepseek`。 |
| 严重度 | 发现 33、34 已复验通过；7A–7D 主路径通过 |
| 证据 | 用户 6D 截图；用户粘贴的 7B/7C/7D 终端输出 |

## 发现清单

按走查顺序累积。Critical/High 必须修复并重新走查；Medium/Low 可记录并由用户接受或转入后续修正任务。

| # | 走查项 | 发现 | 严重度 | 状态 |
|---|---|---|---|---|
| 1 | 1 首启 | 无法自证所运行的版本：版本行恒为 `Vera 0.1.0`，且 `vera --version` 选项不存在（返回 Usage error）。产品作者本人也需要检查 `vera.__file__` 才能确认跑的是最新代码。 | Medium | 复验通过：`vera --version` 显示发行版本、源码短 commit、editable 路径 |
| 2 | 2 输入与对话 | 时间线不自动跟随底部，新消息到达后需手动滚动。0032 的单次 `call_after_refresh` 仍可能测到旧高度；底部滚轮/布局事件会误标离开。`@` 选文件回车后再次复现需手动上划。 | High | 复验通过：Resize 与对话中用户确认仍跟到底部，不露出原终端 |
| 3 | 2 输入与对话 | 列文件已过；「分析项目结构」先是工具写回后 400（`reasoning_content` 未回传 / 压缩拆轮）。整轮回传后复验不再 400，但读完若干 Swift 文件后以 `repeated_tool_call` 失败。实现把整次运行的相同调用累加，规格只要求**连续**三次相同参数才停。 | High | 复验通过：分析项目能出最终回答，不再因重复工具整任务失败 |
| 8 | 2 输入与对话 | 提交「你好vera」后时间线看不到用户原文，助手回复正常。根因：`project_user_prompt()` 从未被调用，`run.started` 按契约不含 `goal`。 | High | 复验通过：时间线出现「用户」块 |
| 9 | 2 输入与对话 | `list_directory` 占很多行，展开正文为空。根因：公共 `tool.completed` 不含结果正文，投影读取 `result` 得到空串，且标题无目标/耗时。 | Medium | 复验通过：标题含目标与耗时，展开有摘要 |
| 10 | 2 输入与对话 | `/exit`（及补全后的 exit）只在时间线写「会话已关闭」，TUI 不退出，人仍留在 Vera 全屏。Ctrl+D 会 `app.exit(0)`，斜杠命令没有走同一条路径。 | High | 复验通过：`/exit` 回到原 shell |
| 11 | 2 输入与对话 | 「分析项目结构」过了 400 与误报 `repeated_tool_call` 后，读完全部文件以 `max_tool_calls` 硬失败（默认 50）。只读探索撞上限时应根据已有证据作答，而不是整任务失败。 | High | 复验通过：中间可有单次工具失败，最终有回答且不再整任务报错 |
| 13 | 2 输入与对话 | 助手结论文本按纯文本画出，Markdown 符号（`#`、`**`、列表标记等）原样显示。阶段三规格要求助手块渲染 Markdown。 | Medium | 复验通过：助手回答按标题/强调/列表/代码显示，符号不再原样露出 |
| 12 | 2 输入与对话 | TUI 里无法复制失败文案。Textual 默认走 OSC 52，macOS Terminal.app 不支持，鼠标又被应用捕获。 | Medium | 复验通过：拖选回答后写入系统剪贴板（发现 14） |
| 14 | 2 输入与对话 | 助手回答无法点选或拖选。根因：块包在 `Collapsible`（标题 `ALLOW_SELECT=False`），且 Markdown 走 `RichVisual`，`get_selection()` 提不出文本。 | Medium | 复验通过：回答可拖选，松手后进入剪贴板 |
| 15 | 2 输入与对话 | 分析项目时 `search_text` 打到单个 `.pbxproj` 文件，标题形如 `query @ path`，错误码 `not_a_directory`。工具只接受目录。 | Medium | 复验通过：对单个文件搜索不再报错 |
| 16 | 2 输入与对话 | 斜杠补全只列出命令，无选中高亮，回车不能直接执行匹配项。 | Medium | 复验通过：输入匹配、高亮选中、回车执行 |
| 17 | 6 终端兼容 | `/theme` 切换成功，但界面颜色不变。根因：只给 Screen 加 CSS 类，未走 Textual `App.theme`。高对比内容区 `tall` 白框外还有半块线。 | Low | 复验通过：三种主题立即换肤；高对比内容区为单线白框 |
| 18 | 5 诊断 | `~/Desktop/python-demo` 的 `/doctor` 显示 `git main`。该目录自有 `.git`，不是无 Git 环境。 | 无 | 复验通过：显示正确 |
| 19 | 2 输入与对话 | 多数状态默认收起，要点开才看得见；相邻工具/状态全部摊开，没有同类归并和层级。 | Medium | 复验通过：工具归入「工具 · N 次」；`/doctor` 默认可读 |
| 20 | 2 输入与对话 | 输入 `/` 弹出补全但列表不全；继续输入后提示看起来消失。先只渲染前 8 条；复验后滚到 `/doctor` 再打 `d``o` 仍会消失。选中无颜色；回车执行后弹层不收。 | Medium | 复验通过：全量匹配、选中可见、回车后收起 |
| 21 | 6 终端兼容 | 默认主题主色偏橙（输入框与补全选中为 `#ffa62b`），与已定深蓝方向不一致。输入框曾叠出 extra `tall` 细线。 | Low | 复验通过：输入框深蓝圆角，选中行深蓝，细线已去掉 |
| 22 | 2 输入与对话 | 输入 `@` 并选出 `ViewController` 后回车，只把裸 `@` 发给模型。根因：`accept()` 不处理 path 模式。同时出现无法输入、下划露出原终端。 | High | 复验通过：选文件回车插入路径；上下滚不再露出原终端；点击时间线后再打字可继续输入 |
| 23 | 2 输入与对话 | `@` 选中带子目录的文件后输入「分析此文件」回车，状态显示「未知命令：/ViewController.swift」。根因：斜杠补全把路径里的 `/` 当成命令，并把输入改写成 `/ViewController.swift`。 | High | 复验通过：补任务后作为普通请求处理 |
| 24 | 3 Diff 与审批 | 写入 `notes.md` 已成功且过程中 Diff 正常，但任务结束后 `/diff` 显示「文件数：无」。根因：无 run-id 时只看已结束的 `_active_run_id`（为 None），且 `session.diff` 被画成状态卡、隐藏「没有 Diff。」正文。 | High | 复验通过：事后 `/diff` 能看到权威 Diff |
| 25 | 2 输入与对话 | `/new` 与 `/clear` 无报错但 TUI 时间线不变。根因：只重置上下文；TUI 未处理 `clear_display`。清屏后确认被跟到底部。 | High | 复验通过：`/clear` 后启动状态在顶部；`/new` 保留历史并在状态栏确认 |
| 26 | 2 输入与对话 | Shift/Alt/Cmd+Enter 换行失败。Terminal.app 的 Option+Enter 是 `ESC+CR`，被 Textual 收成普通 Enter 并提交；输入框固定 1 行，换行后看不见。 | High | 复验通过：Option+Enter 插入换行且输入框升高；Shift/Cmd+Enter 在 Terminal.app 无法与回车区分，不作为换行 |
| 27 | 3 Diff 与审批 | 多文件 Diff 内容正确，但无法选中或复制。根因：Diff 包在 `Collapsible` 且 `Syntax` 走 `RichVisual`，与发现 14 相同。审批中回车不发新任务，符合预期。 | Medium | 复验通过：Diff 可拖选，复制为纯文本 |
| 28 | 4 验证取消恢复 | 审批卡 Tab 在整页控件间跳转，不在三个决定按钮间循环；Reject/Approve 没有 primary 选中态。 | Medium | 复验通过：Tab 只循环 Cancel/Reject/Approve，当前项为 primary |
| 29 | 4 验证取消恢复 | 强制退出后再进 `vera`，首屏无待恢复提示。`/recover` 投影为失败卡「恢复未完成：原因未记录」，两张相同、无 run-id；状态栏「正在恢复 · Esc/Ctrl-C 取消」。根因：TUI 不调用 `bootstrap_events()`；`recovery.detected` 被当成失败且 payload 用 `reason_code` 而非 `reason`。 | High | 复验通过：首屏提示待恢复；`/recover` 列出 run-id、分类与下一步 |
| 30 | 4 验证取消恢复 | 状态卡标题截断并重复正文。无参数 `/abandon` 只显示用法。`manual_required`（`notes.md` 哈希 unknown）下一步仍让人再敲 `/recover`，对其 `/abandon` 打出失败卡。规格不允许对人工分类自动放弃。 | Medium | 复验通过：单行状态不重复标题；`/abandon` 列出可放弃 run-id；人工分类写明不能自动放弃 |
| 31 | 5 诊断 | `/doctor` `/config` 走通用摘要：诊断卡无 `pass`/`warning`/`fail`/`unavailable`，配置卡只显示 `sources: 4` 一类计数。未见 Key。 | Medium | 复验通过：六项带 status；配置列出 sources 与脱敏值，仅环境变量名 |
| 32 | 5 诊断 | 只读目录任务失败文案为裸 `permission_denied`。对文件 `chmod a-w` 挡不住原子替换；规格 5D 是只读目录。 | Low | 复验通过：只读目录下 Approve 后失败，Diff 为「未写入」，失败卡未产生工作区变化，磁盘仍为 `keep` |
| 33 | 7 入口对照 | `--plain` 把 `model.requested` / `model.completed` 原样打出。TUI 已静默这些往返；HumanPresenter 未处理时回落到事件类型名。 | Low | 复验通过：`vera run` 人类输出无这两行；JSON 仍含事件名 |
| 34 | 7 入口对照 | `vera run --json` 的 `run.started.model_profile` 为 `default`，TUI/Session 为 `deepseek`。实际仍打到同一供应商，字段名不一致。 | Low | 复验通过：`model_profile= deepseek`，`exit=0` |
| 35 | 4 验证取消恢复 | `VeraTestDemo` 经用户批准的 `xcodebuild` 在工程根生成约 106 MB、354 个 `build/` 文件，其中 352 个进入 Git 暂存区。这是 Xcode 标准产物，不是 Vera 私有状态，但由未隔离的验证命令触发。 | High | 复验通过（2026-09-15，`vera 0.1.0+940bd29`）：用户先手动删除磁盘 `build/`；再批准隔离后的 `xcodebuild`，产物写入 `/private/tmp/vera-verification/.../000`，工程根未重建 `build/`，验证 passed。Git 索引仍有旧 `AD build/`，未取消暂存、未改 `.gitignore`。 |
| 36 | 4 验证取消恢复 | 命令审批卡只显示 `动作 command`、`目标 verification_0`、`效果 执行验证命令`，不展示最终 argv、`artifact_profile`、外部产物根。用户在看不见 `-derivedDataPath` 的情况下批准了验证。Plain 模式能打印 argv。规格要求批准的是实际执行语义。 | High | 复验通过（2026-09-16，`run_54d549ca3e9d4e578f65443fb8f7302e`）：TUI command 卡展示最终 `命令`、`Profile xcode`、`产物根`；默认焦点 Cancel。用户按约定 Reject，未再执行构建。 |
| 37 | 4 验证取消恢复 | 模型在 `propose_changeset.verification[]` 里自带 `artifact_plan.root='.'`，`ProposalInput` 校验失败，任务无法提出 Change Set。隔离根必须由 Planner 生成，不能接受模型字段。 | High | 复验通过：`ProposalInput` 丢弃模型提供的 `artifact_plan`。重启后同任务提出成功，Planner 挂上外部根（同上 run）。 |

## 阶段七最终封存确认（沿用本记录）

用户确认原文必须是：「CLI 版本达到预期，可以封存」

当前记录：未确认。
