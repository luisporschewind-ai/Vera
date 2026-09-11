# 验收：评测契约、Corpus 与夹具隔离

**规格：** [2026-09-12-evals-and-internal-readiness](../specs/2026-09-12-evals-and-internal-readiness.md)
**任务：** [0015](../tasks/0015-eval-contracts-and-fixtures.md)
**日期：** 2026-09-12
**结果：** Pass（非 live；未跑 `tests/live`；未读真实 DeepSeek/GLM Key；未修改 VeraTestDemo；未启动 Runtime）

## 质量门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- 新增评测测试 44 项全部通过（contracts 19、codec 8、corpus 11、isolation 6）
- 完整非 live：407 passed / 2 deselected；覆盖率 90%
- 沙箱内 3 个既有测试失败：`tests/e2e/test_git_fixture.py`、`tests/e2e/test_rejection.py`（`git init`）、`tests/pty/test_terminal_capabilities.py`（PTY）。与阶段三相同，不是本任务回归
- Ruff、格式、Mypy、`uv build`、`git diff --check` 通过
- 未运行 live，未读取供应商 Key

## 契约与隔离证据

| 项 | 证据 |
| --- | --- |
| `schema_version=1`、冻结 extra=forbid、`model=fake` | `tests/evals/test_contracts.py` |
| 未知 schema 拒绝且不含原始 JSON | `tests/evals/test_codec.py` |
| canonical 排除 evaluation_id / run_ids / 耗时 | `tests/evals/test_codec.py` |
| manifest hash、路径、秘密、symlink/FIFO | `tests/evals/test_corpus.py` |
| `../outside.txt` 只作为脚本字面量 | `test_loader_keeps_escape_literal_in_script_not_as_filesystem_path` |
| 临时 workspace/state/staging，权限 0700，源不变 | `tests/evals/test_isolation.py` |

## 已知限制

- 内置 14 个冻结 case 尚未写入包内 corpus；默认资源根指向 `vera.evals` 的 `corpus` 路径，由任务 0018 填充
- Worker 子进程、评分与 CLI 属于任务 0016–0018
