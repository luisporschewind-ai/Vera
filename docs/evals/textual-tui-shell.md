# 验收：Textual TUI 外壳与模式路由

**任务：** [0011](../tasks/0011-textual-tui-shell.md)
**日期：** 2026-09-11
**结果：** Pass（非 live）

## 验证范围

| 项 | 证据 |
| --- | --- |
| PresentationMode 与 TTY/`TERM=dumb`/`--plain` 路由 | `tests/terminal/test_mode.py`、`tests/cli/test_entrypoint.py` |
| SessionController / SessionAction | `tests/session/test_controller.py`、`tests/session/test_actions.py` |
| Plain InteractiveSession 回归 | `tests/cli/test_session.py` |
| Textual 布局与 Resize | `tests/terminal/test_app.py`、`tests/terminal/test_layout.py` |
| TerminalBridge Worker 不阻塞 Composer | `tests/terminal/test_bridge.py` |
| 子命令不启动 TUI；TUI 失败提示 `--plain` | `tests/cli/test_entrypoint.py` |
| 未引入 prompt_toolkit | `pyproject.toml` 依赖仅 Typer + Textual + Rich |

## 命令

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

## 已知限制（留待 0012–0014）

- 时间线仅为外壳，卡片/折叠/流式渲染在 0012。
- Composer 多行、审批焦点与取消语义在 0013。
- Root `--json` Session 协议在 0014 公开；本任务仅接入 `--plain` 与默认 TUI。
