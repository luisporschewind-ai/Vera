# Vera 本地安装与升级

Vera 当前仅支持 **Python 3.12**（见 `pyproject.toml` 的 `requires-python`）。不要从本开发机的一次成功安装推断 Intel macOS 或其他 Python 版本可用。

## 从本地 wheel 全新安装

在仓库内构建：

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase5-dist
```

在仓库外隔离环境安装（不要把真实 Provider Key 写进命令行历史）：

```bash
uv venv --python 3.12 /private/tmp/vera-phase5-venv
uv pip install --python /private/tmp/vera-phase5-venv/bin/python --offline /private/tmp/vera-phase5-dist/*.whl
export PATH="/private/tmp/vera-phase5-venv/bin:$PATH"
cd /path/to/your/project
vera --help
vera --version
```

`--help`、`vera --version`、`vera eval validate` 与 `vera eval list` 不需要 Provider。交互会话（默认 TUI、`--plain`、`--json`）需要本地配置至少一个模型供应商。

重复对同一 venv 执行 `uv pip install --offline <wheel>` 是安全的，不会修改目标工程。

## 仓库外 smoke

脚本只接受显式路径，不删除宽泛目录；清理由调用方或 pytest 临时目录完成。

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/smoke_installed_wheel.py \
  --dist /private/tmp/vera-phase5-dist \
  --workspace /private/tmp/vera-phase5-smoke-workspace
```

## 配置与错误

| 情况 | 退出码 | 稳定 code |
|---|---|---|
| 工作区不是目录 | 2 | （人类提示） |
| 默认 TUI 但终端不支持 | 2 | `tui_unsupported` |
| 未配置模型供应商 | 5 | `missing_provider_config` |
| 私有 state 目录不可写 | 5 | `state_unwritable` |
| 未知/损坏 run schema | `vera state inspect` 报告 `format_status=unsupported` 或 `corrupt`，不改写原字节 | `unsupported_version` |

Provider Key 只从用户本地环境或 `VERA_PROVIDER_ENV_FILE` 读取，不会进入 Event、日志或证据。

## 升级与旧状态

从已封存的上一 Journal 格式升级时：

1. `vera state inspect --json` 查看 `legacy` / `current` / `unsupported` / `corrupt`。
2. `vera state migrate <run-id> --json` 默认 dry-run，生成 `migration_hash`。
3. 带 `--apply` 与匹配的 hash 才写入派生 `manifest.json`。
4. 失败时保留原始 `events.jsonl` 与 backup，给出「不要删除」建议。
5. 对已是 current 的 run 重复迁移结果为 `noop`。

未知新版本与损坏数据不会自动删除或改写。卸载 venv 或删除 Vera 私有 state 不得作为清理用户工程的手段。

## 人工验收

三类真实工程与 20 次 dogfood 不由自动测试代填，见：

- [代表性工程人工清单](evals/phase-5-representative-project-manual-checklist.md)
- 连续 dogfood 记录属于任务 0024，本文件不代填。
- 阶段六终端兼容只记录实测项，见 [阶段六终端兼容矩阵](evals/phase-6-terminal-compatibility-matrix.md)。`NO_COLOR`、`TERM=dumb` 与 `VERA_NO_ANIMATIONS=1` 走保守静态展示；默认 TUI 需要可用 TTY。
