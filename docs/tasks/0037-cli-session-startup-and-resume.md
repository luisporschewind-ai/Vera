# 任务 0037：CLI 新建、继续、选择与会话维护

> 供主实现 Agent 执行：按 `superpowers:test-driven-development` 实施；入口语法必须先用 CliRunner 与 PTY 固定，再接 TUI。

**状态：** Planned
**执行就绪：** 否；等待任务 0036 完成
**分支：** `phase-7/0037-cli-session-resume`
**依赖：** 任务 0036
**规格：** [持久化对话会话](../specs/2026-09-13-persistent-conversation-sessions.md)

## 目标与边界

完整实现 `vera` 新建、`vera -c` 最近继续、`vera -r` 交互选择、`vera -r <session-id>` 明确恢复，以及 `/sessions`、状态和维护入口。恢复只装载自然语言上下文；既有 `/resume <run-id>` 继续表示恢复中断 Run。

## 启动请求契约

新增 `src/vera/session/startup.py`：

```python
SessionOpenMode = Literal["new", "continue", "resume_picker", "resume_id"]

class SessionOpenRequest(BaseModel):
    mode: SessionOpenMode
    session_id: str | None = None

class SessionStartupService:
    def resolve(self, request: SessionOpenRequest, workspace: Path, *, interactive_tty: bool) -> LoadedConversationSession: ...
```

在 `src/vera/cli_options.py` 隔离 `-r/--resume` 的可选值解析边界；公开函数只返回 `SessionOpenRequest`，不得把解析器私有对象传入 Core。`-c` 与 `-r` 互斥；`-r` 后的值只解释为 session id，不解释为路径、命令或 stdin。

## 实施步骤

### 1. 固定根命令语法

- [ ] 扩展 `tests/cli/test_session.py`，先覆盖 `vera`、`-c`、`--continue`、`-r`、`--resume`、`-r ID`、`--resume ID`、与 `--plain/--json/--workspace` 的顺序组合。
- [ ] 增加冲突负例：`-c -r`、重复 `-r`、`-r` 后多余位置参数、`run/eval/runs` 子命令不得误吃会话参数。
- [ ] 新增 `src/vera/cli_options.py`，用一个被单元测试包围的根命令解析适配器表达“可选 session id”；不在 `cli.py` 散布 `sys.argv` 猜测。
- [ ] 帮助中明确显示 `-r [SESSION_ID]`，并把 `/resume <run-id>` 描述为“继续可恢复 Run”。

### 2. 新建、最近继续与明确 ID 恢复

- [ ] 新增 `tests/session/test_startup.py`，覆盖 new 总是新建、continue 无匹配明确失败、continue 选择当前 workspace 最新可恢复项、resume id 不存在/损坏/workspace 不匹配失败关闭。
- [ ] 新增 `src/vera/session/startup.py`，只通过 `ConversationSessionStore` 解析请求；不读取 TUI 文本或直接遍历 JSONL。
- [ ] 修改 `src/vera/cli.py`，在模式选择后创建一次启动结果，并将同一 `loaded_session` 传给 TUI/Plain/JSON。
- [ ] `vera` 即使发现历史也必须新建，不显示诱导式隐式恢复。

### 3. TTY 选择器与非 TTY 退化

- [ ] 新增 `src/vera/terminal/widgets/session_picker.py` 与 `tests/terminal/test_session_picker.py`，覆盖键盘选择、取消、长标题、短 ID、损坏项禁用、60×16 降级。
- [ ] `vera -r` 在交互式 TTY 启动选择器；选择前不得创建或写入新会话。
- [ ] Plain 交互 TTY 使用简洁编号列表；JSON 或非 TTY 不打开选择器，只发出/打印可用会话摘要并要求明确 ID。
- [ ] 增加 `tests/pty/test_session_resume.py`，证明无参数 `-r` 不从 stdin 猜测、不输出 ANSI 到 JSON。

### 4. 恢复展示与输入历史

- [ ] 修改 `src/vera/terminal/app.py` 和 `src/vera/terminal/widgets/timeline.py`，只恢复用户消息、助手最终回复与短 run 结果；默认有界装载最近 40 个展示条目。
- [ ] 提供结构化 `session.loaded`、`session.load_failed`、`session.listed` Event；Plain 只打印恢复确认和最近上下文，JSON 只写 NDJSON。
- [ ] 使用恢复会话中的用户消息重建 Controller 的 `PromptHistory`，再由 Composer 接收；不得另读磁盘。
- [ ] 历史增量加载只读取 Store 投影，不创建无限 Widget，不阻塞 Composer。

### 5. `/sessions`、状态与显式修复入口

- [ ] 在 `src/vera/session/command_catalog.py` 注册 `/sessions`，只读列出当前 workspace 会话；活动 Run/审批中不得切换会话。
- [ ] 扩展 `/status`、`/context`、`/new`、`/clear`、`/compact` 测试，验证新建/恢复来源、消息数、压缩数和 `saved|unsaved` 一致。
- [ ] 在 `src/vera/cli.py` 增加 `sessions inspect <id>` 与 `sessions repair <id>` 维护组；默认 repair 只输出计划，只有 `--apply` 才调用 `create_repaired_copy`。
- [ ] 维修命令重新校验源摘要、创建新 session id、输出原文件未改的结果；支持 `--json`，不得要求 TUI。

### 6. 安装包入口回归

- [ ] 扩展 `scripts/smoke_installed_wheel.py`，在仓库外临时 state/workspace 覆盖 new、continue、resume id、非 TTY picker 拒绝和 session list。
- [ ] 测试进程退出再启动时第二轮模型输入含必要前文，且 Run/工具副作用未重放。

## 局部验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_startup.py tests/cli/test_session.py tests/cli/test_plain_session.py tests/cli/test_json_session.py tests/terminal/test_session_picker.py tests/terminal/test_app.py tests/pty/test_session_resume.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase7-session-dist
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/smoke_installed_wheel.py --dist /private/tmp/vera-phase7-session-dist --workspace /private/tmp/vera-phase7-session-smoke
git diff --check
```

再运行共同门禁，更新证据后提交：

```bash
git commit -m "feat: add conversation session resume flows"
```

## 验收标准

- 六种已接受启动形式行为明确，`-c/-r` 不会静默新建或跨 workspace 恢复。
- TUI、Plain、JSON 和非 TTY 共享 `SessionOpenRequest` 与 Store 结果。
- 长历史恢复有界，输入历史可用，旧工具/Diff 不铺满首屏。
- 尾部修复必须显式 `--apply` 创建副本，原 Journal 不变。
