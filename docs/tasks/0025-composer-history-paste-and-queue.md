# 任务 0025：Composer、历史、粘贴与单条队列

> 供 Cursor 执行：按 `superpowers:executing-plans` 实施；阶段五完成前不得开始本任务。

**状态：** Done
**执行就绪：** 阶段五自动门禁完成后（用户授权在 Ready for manual acceptance 时开始阶段六）
**分支：** `phase-6/0025-composer-history-queue`
**依赖：** 任务 0024 自动部分已合并
**规格：** [阶段六 CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 目标与边界

让多行、历史、反向搜索、可靠粘贴、Unicode 编辑、外部编辑器和运行中单条队列符合终端直觉，且不越过审批边界。历史和草稿只存在当前进程，退出后清空。

## 实施步骤

### 1. 会话内历史模型

**修改：**

- 新增 `src/vera/session/history.py`
- `src/vera/session/actions.py`
- `src/vera/session/controller.py`
- 新增 `tests/session/test_history.py`
- `tests/session/test_controller.py`

**测试先行：** 覆盖上一条/下一条、编辑后保留草稿、重复去重、上限、`Ctrl+R` 子串搜索、Unicode、空输入和退出清空。先确认缺少独立模型而失败，再实现 `PromptHistory`，不得写磁盘。

### 2. Composer 编辑与 bracketed paste

**修改：**

- `src/vera/terminal/widgets/composer.py`
- `src/vera/terminal/app.py`
- `tests/terminal/test_composer.py`
- `tests/terminal/test_app.py`

使用 Textual Pilot 测试 Home/End、按词移动、删除、撤销/重做、CJK 宽字符、多行快捷键、历史边界和 bracketed paste。多行粘贴必须成为一次编辑且不提交；ANSI/OSC/bidi 输入按普通文本保存并在展示层净化。

### 3. 运行中单条队列

**修改：**

- `src/vera/session/actions.py`
- `src/vera/session/controller.py`
- `src/vera/terminal/bridge.py`
- `src/vera/terminal/widgets/composer.py`
- `tests/session/test_controller.py`
- `tests/terminal/test_app.py`
- `tests/cli/test_plain_session.py`
- `tests/cli/test_json_session.py`

**测试先行：**

1. run 活动时仅允许一条 queued prompt，可查看、替换前必须显式撤销、终态后作为新 `StartRun` 提交。
2. 等待审批时拒绝排队；取消/失败/完成均不把队列拼进旧 run。
3. TUI、Plain、JSON 都有结构化 `QueuePrompt/ClearQueuedPrompt` 语义；JSON 不解析 UI 文本。

### 4. 安全外部编辑器

**修改：**

- 新增 `src/vera/session/external_editor.py`
- `src/vera/session/actions.py`
- `src/vera/session/controller.py`
- `src/vera/terminal/app.py`
- 新增 `tests/session/test_external_editor.py`
- `tests/terminal/test_app.py`

测试固定 argv、`shell=False`、`0600` 临时文件、首次命令预览确认、编辑成功/不变/失败/取消、只删除本次精确临时文件。仅接受 Vera 配置中的明确编辑器 argv；不隐式解析任意 shell 字符串。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_history.py tests/session/test_external_editor.py tests/session/test_controller.py tests/terminal/test_composer.py tests/terminal/test_app.py tests/cli/test_plain_session.py tests/cli/test_json_session.py -q
```

再运行[阶段六共同门禁](phase-6-execution-order.md)，更新任务证据并提交：

```bash
git commit -m "feat: polish composer history and prompt queue"
```

## 验收标准

- 输入、粘贴、历史和 CJK 编辑不误提交、不丢草稿。
- 队列严格一条且不跨未决审批或混入当前 run。
- 外部编辑器路径可复核、无 shell、临时文件私有且精确清理。
- 退出不保存自然语言历史。

## 验证证据

日期：2026-09-13

- 会话内 `PromptHistory` 只驻留进程，覆盖上下条、草稿恢复、去重、上限、子串搜索、CJK 与 `CloseSession` 清空。
- Composer 将 bracketed paste 视为一次编辑：净化 ANSI/OSC/bidi，不因换行提交。
- `QueuePrompt` 仅允许一条；审批中拒绝；替换需先 `ClearQueuedPrompt`；run 终态后作为新 `StartRun` 提交，关闭会话不冲刷队列。
- 外部编辑器使用固定 argv、`shell=False`、`0600` 草稿、首次预览确认，清理只删除本次文件。项目配置禁止 `editor_argv`。
- TUI、Plain、JSON 共享同一 SessionAction；排队事件不回传原文。
- 任务测试：`tests/session/test_history.py`、`test_external_editor.py`、`test_controller.py`、`tests/terminal/test_composer.py`、`test_app.py`、`tests/cli/test_plain_session.py`、`test_json_session.py` 通过。
- 完整非 live：sandbox 中 701 passed / 2 deselected；`git init` 与 PTY 三项在沙箱外复跑 5 passed。
- ruff、format、mypy、`uv build`、`git diff --check` 通过。
