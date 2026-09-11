# 版本化 Codec 与兼容迁移验收记录

更新日期：2026-09-11

## 结论

任务 0007 离线实现、完整非 live 验收、静态检查和包构建通过。Vera 现在通过 `ContractCodec`、`JournalCodec`、`SnapshotCodec` 与 `RunManifest` 显式分派版本；legacy run 可查看不可续跑；未来版本与损坏项被隔离；`vera state inspect|migrate` 默认 dry-run，apply 前备份且不改写 Event Journal。

自动验收没有运行 live 测试，没有读取或使用用户真实 DeepSeek/GLM API Key。

## 规格验收对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | 当前 Command/Event schema v1 编解码往返 | 通过 |
| 2 | 未知未来 `schema_version` 返回 `unsupported_version` | 通过 |
| 3 | Journal / Snapshot 独立格式版本；缺失版本失败关闭 | 通过 |
| 4 | 新 run 在首事件前写入 `manifest.json` | 通过 |
| 5 | 阶段一 legacy fixture 可读，分类 `legacy_not_resumable` | 通过 |
| 6 | 损坏 JSONL 与未来 manifest 隔离，不影响其他 run 列表 | 通过 |
| 7 | 迁移 dry-run 生成 `migration_hash`；apply 备份后写派生 manifest | 通过 |
| 8 | apply 不改 Journal 字节；失败保留原状态与备份 | 通过 |
| 9 | 错误 `migration_hash` 不写盘 | 通过 |
| 10 | CLI `vera state inspect` / `migrate --json` | 通过 |

## 自动验证证据

- `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" --cov=vera --cov-report=term-missing`：235 passed，2 deselected（live）。
- 覆盖率：90%。
- Ruff check / format --check、Mypy、`uv build`、`git diff --check`：全部通过。

## 已知限制

- 本任务只写入派生 `manifest.json`，不升级公共 `schema_version`。
- PolicyEngine 与审批指纹属于任务 0008；ModelAdapter 韧性与阶段二总验收属于任务 0009。
