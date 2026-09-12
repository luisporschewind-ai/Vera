# 验收：阶段五 Core 安全、权限与可靠性加固

**规格：** [2026-09-12-core-security-and-reliability-hardening](../specs/2026-09-12-core-security-and-reliability-hardening.md)  
**任务：** [0024](../tasks/0024-phase-5-contract-freeze-and-acceptance.md)  
**日期：** 2026-09-13  
**结果：** Ready for manual acceptance（自动门禁通过；20 次真实 dogfood 与三类真实工程人工走查未完成）

## 质量门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts/test_compatibility_manifest.py tests/e2e/test_core_client_contract_parity.py tests/evals/test_dogfood.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase5-acceptance-dist
git diff --check
```

自动证据（2026-09-13）：

- 完整非 live：`683 passed, 2 deselected, 1 warning in 437.78s`
- 聚焦：`tests/contracts/test_compatibility_manifest.py`、`tests/e2e/test_core_client_contract_parity.py`、`tests/evals/test_dogfood.py` 通过
- `ruff check` / `ruff format --check` / `mypy src` 通过
- `uv build --out-dir /private/tmp/vera-phase5-acceptance-dist` 产出 `vera_agent-0.1.0` sdist 与 wheel
- `git diff --check` 无空白错误
- warning 来自既有 `tests/pty/test_terminal_capabilities.py` 的 `forkpty` DeprecationWarning

## 15 条退出条件

| # | 条件 | 栏 | 说明 |
|---|---|---|---|
| 1 | 阶段四独立审查无阻断项 | 自动验证且通过 | 阶段四审查 64/64；0030 对抗门禁已合并 |
| 2 | workspace 逃逸与特殊文件负例 | 自动验证且通过 | 任务 0020 及冻结 eval 安全 case |
| 3 | 命令策略、环境、超时、取消、子进程 | 自动验证且通过 | 任务 0021 |
| 4 | 审批绑定、过期、跨 run、拒绝零副作用 | 自动验证且通过 | 任务 0020/0024 四客户端事实 |
| 5 | Key/Token/请求正文/用户正文不进公共证据 | 自动验证且通过 | 0021/0030；dogfood 校验拒绝秘密 |
| 6 | 恢复中断与幂等 | 自动验证且通过 | 任务 0022 与冻结恢复 case |
| 7 | 损坏状态失败关闭 | 自动验证且通过 | 任务 0022 |
| 8 | 三类代表性工程规定流程 | 未运行/受阻 | 0023 为夹具自动验收；真实工程副本需用户走查 |
| 9 | 20 次连续 dogfood | 未运行/受阻 | schema 与 `dogfood-check` 已就绪；无用户 20 条记录 |
| 10 | wheel 新装/升级/仓库外启动 | 自动验证且通过 | 任务 0023；本次再跑 wheel 构建 |
| 11 | 四客户端共享 Core 契约 | 自动验证且通过 | `test_core_client_contract_parity` |
| 12 | 版本化公共协议 | 自动验证且通过 | `CompatibilityManifest`、`docs/protocol.md`、ADR-0014 |
| 13 | 无未关闭 Critical/High | 自动验证且通过 | 已知限制为 Medium/Low，见下 |
| 14 | 完整非 live 与静态门禁 | 自动验证且通过 | 见自动证据 |
| 15 | 未读真实 Key、未改未授权工程、无桌面框架代码 | 自动验证且通过 | 测试清除供应商环境；无 Electron 依赖 |

## 已接受限制与 Medium/Low

- 基线投毒检测器是启发式，漏报依赖 Workspace/PolicyEngine/ApprovalGate（Medium，已接受）。
- `ContentSafetyPolicy` 未强制执行公开审核（Low，阶段五非目标）。
- 私有 snapshot 仍保留 `StartRun.goal` 供恢复（Low；公共 Event 仅 `goal_hash`）。
- 阶段七桌面规格仅为 Draft 预校准，未实施。

## 明确未做

- 未把阶段五标为 Complete
- 未开始阶段六实现（本报告截止时）
- 未读取真实 Provider Key，未跑 live
- 未引入 Electron/Wails/Tauri 代码
