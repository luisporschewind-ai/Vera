# 验收：阶段三富交互 Terminal UI

**规格：** [2026-09-11-rich-terminal-ui](../specs/2026-09-11-rich-terminal-ui.md)
**日期：** 2026-09-11
**结果：** Pass（非 live；未跑 `tests/live`；未读真实 DeepSeek/GLM Key；未修改 VeraTestDemo）

## 质量门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

## 15 条验收标准证据

| # | 标准 | 证据 |
| --- | --- | --- |
| 1 | TTY 默认进入 Textual TUI，退出恢复终端 | `tests/cli/test_entrypoint.py`（TUI 路由）、`tests/pty/test_terminal_capabilities.py`（Plain 无 alternate screen）、Textual App lifecycle |
| 2 | 助手文本经 `assistant.delta` 流式显示，最终 `assistant.message` 一致 | `docs/evals/streaming-runtime-output.md`、`tests/presentation/test_projector.py` |
| 3 | Stream Frame 不进 Journal/Snapshot/会话上下文 | `docs/evals/streaming-runtime-output.md`、Runtime handle 过滤 |
| 4 | 时间线可滚动，离开底部不被抢回，显示新更新计数 | `tests/terminal/test_scrolling.py` |
| 5 | 工具/日志默认折叠；Diff/审批默认展开；失败首次展开 | `tests/presentation/test_disclosure.py`、`tests/terminal/test_blocks.py` |
| 6 | 审批经 Core Command，默认焦点不是 Approve | `tests/terminal/test_approval.py` |
| 7 | 状态词基于 Event；可禁用动画 | `tests/presentation/test_activity.py`、`tests/terminal/test_animation.py` |
| 8 | Composer 多行、Slash、取消、EOF、Resize | `tests/terminal/test_composer.py`、`tests/terminal/test_keybindings.py`、`tests/terminal/test_layout.py` |
| 9 | `vera --plain` 人类交互，无动态控制序列 | `tests/cli/test_mode_compatibility.py`、`tests/cli/test_session.py` |
| 10 | `vera --json` NDJSON Session；`vera run ... --json` 兼容 | `tests/cli/test_json_session.py`、`tests/cli/test_mode_compatibility.py`、`tests/cli/test_run.py` |
| 11 | 60×16 / 80×24 / 120×40 与动画关闭 | `tests/terminal/test_app.py`、`tests/terminal/test_snapshots.py`、`tests/terminal/test_animation.py` |
| 12 | 大量 block / 大工具正文不按行建 Widget | `tests/terminal/test_scrolling.py`（10,000 行单 Widget） |
| 13 | 控制字符与秘密脱敏；TUI 不新增执行权限 | `tests/presentation/test_sanitize.py`、`tests/cli/test_entrypoint.py` |
| 14 | 完整非 live 门禁、覆盖率 ≥90% | 本文件质量门禁；合并前 pytest/ruff/mypy/build |
| 15 | 不读真实 Key、不跑 live、不改 VeraTestDemo | 全程约束；仅 FakeModelAdapter / 临时目录 |

## 已知限制

- 真实 macOS Terminal.app 键盘/滚轮人工观察需用户本机复核；本仓库以 Pilot/PTY 轻量 harness 与确定性测试为主。
- OpenAI-compatible 真实流式仍需显式 `capabilities.streaming=True`；默认兼容 `complete()`。
- 无 Git remote，未推送。
