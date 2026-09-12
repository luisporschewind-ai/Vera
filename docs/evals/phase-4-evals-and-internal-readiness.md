# 验收：阶段四评测与内部就绪

**规格：** [2026-09-12-evals-and-internal-readiness](../specs/2026-09-12-evals-and-internal-readiness.md)
**任务：** [0019](../tasks/0019-eval-phase-4-acceptance.md)
**日期：** 2026-09-12
**结果：** Pass（非 live；未跑 `tests/live`；未读真实 DeepSeek/GLM Key；未修改 VeraTestDemo；未引入桌面框架）

## 质量门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests scripts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_eval_manifest.py --check src/vera/evals/corpus
git diff --check
```

- 完整非 live：535 passed / 2 deselected；覆盖率 91%
- Ruff、格式、Mypy、`uv build`、manifest `--check`、`git diff --check` 通过
- Worker 子进程是生命周期/超时隔离，不是 OS 沙箱
- 未运行 live，未读取供应商 Key，无 remote、未推送

## 冻结 corpus

manifest SHA-256：`8169f95abcb3bf1ccd30bfbadc1c2fee5464b7fdea3ce3909ea0fbc962a4d659`  
文件数：58；case 数：14

`create-file`、`update-file`、`multi-file-edit`、`plain-answer`、`verification-passes`、`reject-keeps-original`、`path-escape-denied`、`forbidden-command`、`usage-null-safe`、`rollback-after-apply`、`resume-after-approval`、`restore-partial-apply`、`in-flight-manual`、`idempotent-resume`

## 仓库外 wheel smoke

临时根 `/private/tmp/vera-phase4-smoke.mfZ9JR`（不保留 workspace 正文）：

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `vera eval validate --json` | 0 | 14 case；manifest 与仓库一致 |
| `vera eval list --json` | 0 | 14 case，按 `case_id` 排序 |
| `vera eval run plain-answer --json --output ./evidence` | 0 | `status=pass` |
| `vera eval run --suite offline --json --output ./suite-evidence` | 0 | 套件 `status=pass`，14/14 |

证据目录 `0700`，`report.json` / `files.json` / `events.jsonl` / `suite-report.json` 为 `0600`。

## 14 条退出条件

| # | 条件 | 证据 | 现场结果 |
| --- | --- | --- | --- |
| 1 | 评测只经 Core Command/Event；不解析人类 CLI/TUI | AST：`tests/e2e/test_phase_4_offline_evals.py::test_eval_package_has_no_human_presenter_dependency`；评分消费 Event/FileFact | Pass |
| 2 | 独立 Worker、临时工作区/`state_dir`；超时不阻塞套件 | `test_timeout_case_does_not_block_following_case`；`test_timeout_sends_term_then_kill` | Pass |
| 3 | corpus schema/manifest/路径/秘密校验；源 hash 不变 | `tests/evals/test_corpus.py`；`test_source_corpus_hash_is_stable_and_evidence_omits_workspace_body`；manifest `--check` | Pass |
| 4 | 固定 14 个离线任务，覆盖正确性/安全/恢复/对话 | `test_phase4_offline_suite_passes_all_frozen_cases` 断言四类 tag | Pass |
| 5 | 正确性按期望哈希、终态、必需 Event；失败有稳定 reason | `tests/evals/test_corpus_correctness_cases.py`、`test_scoring.py` | Pass |
| 6 | 安全抓住越界路径、禁止命令、拒绝审批、期望外变化 | `tests/evals/test_corpus_safety_cases.py`；`path-escape-denied` / `forbidden-command` / `reject-keeps-original` | Pass |
| 7 | 恢复覆盖续跑、部分写入恢复、in-flight 人工、幂等续跑 | `tests/evals/test_corpus_recovery_cases.py` 与 0017 场景测试 | Pass |
| 8 | 延迟与用量入报告；缺失 usage 为 `null` 而非 0 | `usage-null-safe`；wheel smoke 中 `metrics.usage` 为 `null` | Pass |
| 9 | `vera eval validate/list/run`；`--json` 仅一个 document | `tests/e2e/test_phase_4_eval_cli.py`、`tests/cli/test_eval_run.py` | Pass |
| 10 | 私有证据原子写入；权限、脱敏、排序、无正文 | 仓库外 smoke：目录 `0700`、文件 `0600`；`test_source_corpus_hash_is_stable_and_evidence_omits_workspace_body` | Pass |
| 11 | 重复跑同一离线套件 canonical projection 一致 | `tests/e2e/test_phase_4_repeatability.py` | Pass |
| 12 | wheel 安装后可发现并运行内置 corpus | `tests/e2e/test_phase_4_wheel_smoke.py`；仓库外 smoke 14/14 | Pass |
| 13 | 完整非 live、Ruff、格式、Mypy、构建、`git diff --check`；覆盖率 ≥ 90% | 535 passed / 2 deselected；覆盖率 91% | Pass |
| 14 | 不读真实 Key、不跑 live、不改 VeraTestDemo、不引入桌面框架 | 自动测试清除供应商环境；未跑 `tests/live`；无 Electron/Wails/Tauri 依赖 | Pass |

## 明确未做

- 未运行 live，未读取真实 DeepSeek/GLM Key
- 未修改 VeraTestDemo
- Worker 不是 OS 沙箱
- 无 remote，未推送
- 不把 Fake 离线套件表述为真实模型质量证明
- 阶段四完成后不自动开始桌面框架选型
