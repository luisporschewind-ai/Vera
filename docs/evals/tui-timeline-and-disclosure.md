# 验收：对话时间线与披露策略

**任务：** [0012](../tasks/0012-tui-timeline-and-disclosure.md)
**日期：** 2026-09-11
**结果：** Pass（非 live）

## 验证范围

| 项 | 证据 |
| --- | --- |
| DisclosurePolicy 初始矩阵与失败一次展开 | `tests/presentation/test_disclosure.py` |
| ANSI/OSC 清理 | `tests/presentation/test_sanitize.py` |
| Projector：Diff/审批展开、delta 去重、缺口 incomplete | `tests/presentation/test_projector.py` |
| 卡片折叠默认与手动切换 | `tests/terminal/test_blocks.py` |
| 滚动不被新输出抢走；巨大工具正文单 Widget | `tests/terminal/test_scrolling.py` |
| 50ms RenderScheduler 批处理 | `tests/terminal/test_render_scheduler.py` |
| 80×24 / 120×40 截图导出 | `tests/terminal/test_snapshots.py` |

## 命令

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```
