# 验收：Composer、审批与任务控制

**任务：** [0013](../tasks/0013-tui-composer-and-approvals.md)
**日期：** 2026-09-11
**结果：** Pass（非 live）

## 验证范围

| 项 | 证据 |
| --- | --- |
| Composer 提交 / 多行 / 空白不提交 | `tests/terminal/test_composer.py` |
| 共享 Slash Command 目录与补全 | `tests/session/test_command_catalog.py`、`tests/terminal/test_completions.py` |
| 审批默认 Cancel，经 ResolveSessionApproval | `tests/terminal/test_approval.py` |
| ActivityPresenter 状态词 | `tests/presentation/test_activity.py` |
| AnimationClock 可禁用、≤10 FPS | `tests/terminal/test_animation.py` |
| Ctrl+C 取消/清空；Ctrl+D 空闲退出 | `tests/terminal/test_keybindings.py` |
| 未跑 live、未读真实 Key | 本验收仅 `pytest -m "not live"` |

## 命令

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```
