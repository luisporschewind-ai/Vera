# 验收：评测 CLI 与 14 个冻结任务

**规格：** [2026-09-12-evals-and-internal-readiness](../specs/2026-09-12-evals-and-internal-readiness.md)
**任务：** [0018](../tasks/0018-eval-cli-and-corpus.md)
**日期：** 2026-09-12
**结果：** Pass（非 live；未跑 `tests/live`；未读真实 DeepSeek/GLM Key；未修改 VeraTestDemo）

## 质量门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- 完整非 live：513 passed / 2 deselected；覆盖率 90%
- `vera eval` 不调用 `build_runtime()` / `load_provider_environment()` / `load_config()`
- JSON stdout 恰好一个 document，无 ANSI、无 `Vera >`
- Worker 子进程仍是生命周期/超时隔离，不是 OS 沙箱
- 未运行 live，未读取供应商 Key
- Ruff、格式、Mypy、`uv build`、`git diff --check` 通过

## 冻结 corpus

manifest SHA-256：`8169f95abcb3bf1ccd30bfbadc1c2fee5464b7fdea3ce3909ea0fbc962a4d659`  
文件数：58（不含 `manifest.json` 自身）

| case_id | 标签焦点 |
| --- | --- |
| `create-file` | correctness |
| `update-file` | correctness |
| `multi-file-edit` | correctness |
| `plain-answer` | conversation |
| `verification-passes` | correctness（`$VERA_EVAL_PYTHON -c`） |
| `reject-keeps-original` | safety |
| `path-escape-denied` | safety |
| `forbidden-command` | safety |
| `usage-null-safe` | safety / cost null |
| `rollback-after-apply` | recovery |
| `resume-after-approval` | recovery |
| `restore-partial-apply` | recovery |
| `in-flight-manual` | recovery |
| `idempotent-resume` | recovery |

## CLI 退出码矩阵

| 调用 | 退出码 | 测试 |
| --- | --- | --- |
| `vera eval run plain-answer --json` 且评分 PASS | 0 | `test_eval_run_plain_answer_json_exits_0` |
| `vera eval run --suite offline --json` 且 14 case 全 PASS | 0 | `test_eval_suite_json_is_one_document_without_ansi` |
| 脚本内预期 `cancel` 且评分 PASS | 0 | 规格：不等同 Ctrl+C |
| 用户 Ctrl+C | 2 | `test_eval_run_ctrl_c_exits_2` |
| case 断言失败 | 4 | `test_eval_run_fail_exits_4` |
| case 超时 | 4 | `test_eval_run_timeout_exits_4` |
| 同时给出 case 与 `--suite`、缺参、未知 suite、未知 case、语料/证据错误、Runtime ERROR | 5 | `tests/cli/test_eval_run.py` |
| `--live` | 非 0 | `test_eval_run_rejects_live_option` |

默认证据父目录为 `user_state_path("Vera") / "evals"`，显式 `--output` 只作父目录；已有 `evaluation_id` 目录拒绝覆盖。

## Wheel

- Hatchling `packages = ["src/vera"]` 将 `vera/evals/corpus/**` 打入 wheel；sdist 含同一冻结语料
- `tests/evals/test_packaged_corpus.py`：wheel/sdist 含 14 个 `case.json` 与 `manifest.json`；解压 wheel 后 `CorpusLoader().list_cases()` 长度为 14

## 已知限制

- 任务 0019 才做仓库外 venv 安装 smoke、14 条退出条件总表和阶段四收口
- Worker 不是 OS 沙箱；本地执行仍继承当前用户权限
