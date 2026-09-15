# 任务 0040：时间线、Composer 与导航收口

> 供主实现 Agent 执行：按 `superpowers:test-driven-development` 实施；视觉层不得重新推断运行结果或审批风险。

**状态：** Planned
**执行就绪：** 否；等待任务 0039 完成
**分支：** `phase-7/0040-terminal-workflow-polish`
**依赖：** 任务 0039
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)

## 目标与边界

以“用户/助手对话为主轴、工具/日志为次级证据、Diff/审批/验证/失败为高优先级事实”收口时间线，并完成用户消息滚动锚点、原始时间、输入箭头、审批紧凑布局以及 Composer/焦点/复制/滚动/折叠和小终端体验。本任务不增加新 Core 权限，不修改审批边界。

阶段六任务 0033 已在当前实现中建立独立 `ComposerBar`/`>` 提示符和审批卡零 margin、单行按钮基线。阶段七必须保留并回归这些行为，只按任务 0038 接受的视觉 Token 做样式收口，不新建第二套 Composer 容器或审批交互。

## 实施步骤

### 1. 固定信息层级

- [ ] 扩展 `tests/presentation/test_projector.py`，固定各类 Event 已有的结构化类别、标题、状态、披露信息与原始时间；在 `TimelineBlock` 增加可选 `occurred_at`，只从 `EventEnvelope.timestamp` 或持久化 Turn 时间写入，不使用 Widget 重绘时间。
- [ ] 扩展 `tests/terminal/test_blocks.py`，先覆盖用户、助手、普通工具、失败工具、Diff、审批、验证、恢复和空内容块的相对层级，并断言用户消息的本地 `HH:mm` 右对齐、未知时间省略。
- [ ] 修改 `src/vera/terminal/widgets/blocks.py` 与 `theme.tcss`：用户/助手正文获得连续阅读主轴；工具默认紧凑；Diff/审批/验证/失败可辨识但不使用大面积警示色。
- [ ] 新增 `src/vera/presentation/timeline_time.py` 与 `tests/presentation/test_timeline_time.py`；用户消息标题使用水平布局承载左侧角色与右侧时间，时区取本机当前时区，恢复历史保持原始 instant，并覆盖 UTC 跨日、夏令时和未知时间。
- [ ] 空块、重复状态和只含装饰符号的块不得进入时间线。

### 2. 用户消息滚动锚点

- [ ] 新增 `tests/terminal/test_user_prompt_anchor.py`，覆盖原消息仍可见时不重复、原消息越过视口顶部后出现锚点、下一条用户消息到达顶部后替换、滚回原位置后隐藏、`/clear` 清空和历史恢复沿用原时间。
- [ ] 新增 `src/vera/terminal/widgets/user_prompt_anchor.py`，只接收当前可见区之前最近一个 `BlockKind.USER` 的 `TimelineBlock`；锚点是时间线的展示镜像，不创建 Event、不进入复制全文、不改变 projector 顺序。
- [ ] 修改 `ConversationTimeline`，在布局/滚动稳定后依据已挂载用户块的位置选择锚点；锚点不得改变 `scroll_y`、`follow_tail`、未读计数或自动滚动判定。
- [ ] 修改 `app.py` 与 `theme.tcss`，把锚点放在滚动区顶部、Header 下方；未决审批的决定区域和底部 Composer 始终优先可见，小终端空间不足时锚点先退化为单行再隐藏。

### 3. 工具披露与长内容

- [ ] 扩展 `tests/terminal/test_disclosure.py`、`test_timeline_extra.py`，覆盖工具动作、目标、状态、耗时、展开正文、截断提示和 run 证据入口。
- [ ] 普通工具默认展示“动作 + 目标 + 状态 + 耗时”；失败工具保留可行动错误；完整输出通过显式展开或 `/show` 获取。
- [ ] Diff 默认显示文件摘要与关键片段，完整权威 Diff 仍来自结构化 Event/RunStore，不从渲染文本反解析。
- [ ] 长对话、长工具输出和恢复历史采用窗口化/有界 Widget；不可见旧项保留可重新投影的数据引用。

### 4. Composer 稳定状态

- [ ] 扩展 `tests/terminal/test_composer.py` 与 `test_keyboard_flows.py`，覆盖 idle/running/queued/approval 四态的稳定位置、提示、禁用/启用和焦点恢复。
- [ ] 扩展阶段六已有 `test_composer_shows_prompt_glyph_left_of_input`，加入 Unicode 选择与 ASCII `>` 回退，继续断言箭头不进入 `PromptComposer.text`、`PromptSubmitted.text`、历史记录、复制内容或上下文计量，多行草稿只有一个箭头。
- [ ] 复用 `src/vera/terminal/widgets/composer.py` 中既有 `ComposerBar` 组合提示符与 `PromptComposer`；只在同一组件内增加能力回退和视觉 Token，不把装饰字符注入 `TextArea` 内容，也不新建平行容器。
- [ ] 修改既有 `ComposerBar`/`PromptComposer` 与 `app.py`，时间线刷新、状态动画、Resize 和历史增量加载都不得移动输入焦点或丢草稿；Composer 下方保持任务 0039 已实现的单一状态带。
- [ ] 运行中只允许既有单条队列；审批等待时明确拒绝排队；视觉提示不得暗示可绕过 Controller。

### 5. 审批密度、滚动、复制、折叠与返回底部

- [ ] 扩展阶段六已有审批间距回归，在 60×16、80×24、120×40 断言审批标题、正文和三个决策按钮连续可见，卡片上下空白不超过一行，Tab 顺序与默认 Cancel 不变。
- [ ] 保留 `ApprovalBlockWidget` 已有零 margin、`.approval-actions`/Button 单行高度基线；仅按冻结 Token 校准 padding/颜色/焦点，并证明没有重新引入默认 `Horizontal` 伸展或通过隐藏风险/目标/效果换取紧凑。
- [ ] 扩展 `tests/terminal/test_scrolling.py`、`test_keybindings.py`，覆盖用户向上阅读时不抢滚动、消息锚点、未读计数、返回底部、选择文本、复制、折叠和鼠标可选。
- [ ] 自动滚动只在用户仍位于底部时发生；新内容到达而用户在上方时保留位置并显示可访问的未读提示。
- [ ] 所有主流程均有键盘路径；鼠标只是增强，不能成为审批、展开或返回底部的唯一入口。

### 6. CJK、Resize 与性能预算

- [ ] 扩展 `tests/terminal/test_layout_matrix.py`，覆盖 CJK、英文、Emoji、组合字符、60×16/80×24/120×40 和连续 Resize。
- [ ] 扩展 `tests/performance/test_terminal_timeline.py`，使用冻结的大历史/长工具夹具测量启动、追加和滚动；预算沿用阶段六已接受基线，任何放宽必须先写明原因并获确认。
- [ ] 扩展 `tests/pty/test_terminal_lifecycle.py`，覆盖退出后终端属性、光标、备用屏和 Ctrl-C 恢复。

### 7. Plain/JSON 语义对照

- [ ] 扩展 `tests/e2e/test_phase_6_product_matrix.py` 或新建 `tests/e2e/test_phase_7_cli_semantics.py`，对同一离线场景比较 TUI Controller、Plain 和 JSON 的 Event 类型、审批事实、终态与退出码。
- [ ] 断言 TUI 新视觉没有修改 JSON 字段、Plain 文案中的关键风险事实或一次性 `vera run` 行为。

## 局部验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation/test_projector.py tests/presentation/test_timeline_time.py tests/terminal/test_blocks.py tests/terminal/test_user_prompt_anchor.py tests/terminal/test_disclosure.py tests/terminal/test_timeline_extra.py tests/terminal/test_composer.py tests/terminal/test_keyboard_flows.py tests/terminal/test_approval.py tests/terminal/test_scrolling.py tests/terminal/test_keybindings.py tests/terminal/test_layout_matrix.py tests/performance/test_terminal_timeline.py tests/pty/test_terminal_lifecycle.py tests/e2e/test_phase_7_cli_semantics.py -q
git diff --check
```

若实现选择扩展既有 e2e 文件而非新建文件，上述最后一个路径替换为实际文件并在本任务记录。再运行共同门禁，更新证据后提交：

```bash
git commit -m "feat: polish terminal conversation workflow"
```

## 验收标准

- 对话正文、普通工具和关键证据形成稳定、克制的信息层级。
- 用户向上/向下浏览时，最近一条已越过顶部的用户消息作为上下文锚点；下一条到达时替换，右侧时间保持原始事实。
- 输入箭头只是视觉提示，不污染草稿、提交、历史、复制或上下文；Composer 下方状态带不跳动。
- 审批卡上下没有中断性空白，紧凑布局不牺牲风险事实、默认 Cancel 或键盘路径。
- Composer 不因刷新、恢复、Resize 或长输出跳动、丢焦点或丢草稿。
- 复制、滚动、折叠和返回底部均可用键盘完成，鼠标不是必需。
- 小终端、CJK、长历史和 PTY 生命周期满足阶段基线，Plain/JSON 语义不变。
