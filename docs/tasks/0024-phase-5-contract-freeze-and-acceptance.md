# 任务 0024：契约冻结与阶段五验收

> 供 Cursor 执行：按 `superpowers:executing-plans` 和 `superpowers:verification-before-completion` 实施；人工证据缺失时必须停在 `Ready for manual acceptance`。

**状态：** Planned
**执行就绪：** 任务 0020–0023 与任务 0030 合并后
**分支：** `phase-5/0024-contract-freeze-acceptance`
**依赖：** 任务 0020–0023 与 [任务 0030](0030-untrusted-content-and-prompt-injection.md) 已合并
**规格：** [阶段五 Core 加固](../specs/2026-09-12-core-security-and-reliability-hardening.md)、[不可信内容、提示词投毒与内容安全](../specs/2026-09-12-untrusted-content-and-prompt-injection-defense.md)

## 目标

在提示词投毒安全增量完成后，冻结阶段六和未来桌面客户端可依赖的结构化边界，运行完整安全与可靠性回归，形成不夸大的阶段五就绪报告。

## 实施步骤

### 1. 版本化公共契约清单

**修改：**

- 新增 `src/vera/contracts/compatibility.py`
- 新增 `tests/contracts/test_compatibility_manifest.py`
- 新增 `docs/decisions/ADR-0014-core-client-compatibility-contract.md`
- 新增 `docs/protocol.md`
- `docs/decisions/README.md`

**测试先行：** 快照当前 Command、EventEnvelope、RuntimeOutput、error code、approval kind、recovery classification 和 JSON session record 的名称、schema version、必需字段及兼容规则；确认当前没有单一 manifest 而失败。

**最小实现：** 提供只读 `CompatibilityManifest` 和稳定序列化；明确 additive、deprecated、breaking 规则。禁止把 TUI 文案、Widget 类或 CLI ANSI 输出列为公共契约。

### 2. 四客户端契约一致性

**修改：**

- 新增 `tests/e2e/test_core_client_contract_parity.py`
- `tests/cli/test_driver.py`
- `tests/terminal/test_app.py`
- `tests/evals/test_runner.py`

以同一 Fake Model 场景驱动 TUI controller、Plain、JSON 和 Eval，比较权威 run 状态、审批事实、Change Set hash、验证结果和错误 code；展示文字可以不同，语义事实必须相同。

### 3. 20 次连续 dogfood 记录机制

**修改：**

- 新增 `docs/evals/phase-5-dogfood-log.md`
- 新增 `src/vera/evals/dogfood.py`
- 新增 `tests/evals/test_dogfood.py`
- `src/vera/cli_eval.py`

提供脱敏记录 schema 和校验命令，字段仅含序号、时间、工程类型、工作流、结果、失败分类、恢复方式和聚合指标。校验器拒绝源码正文、请求正文、Key/Token 和伪造缺失字段。

自动测试可以验证格式和生成离线示例，但不能生成“用户已完成 20 次”的结论。真实记录由用户实际执行后填写。

### 4. 阶段五总验收与报告

**修改：**

- 新增 `docs/evals/phase-5-core-hardening.md`
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- 本任务文件

先执行全部自动门禁、wheel smoke、安全负例、三类夹具和 compatibility snapshot。报告按四栏记录：

1. 自动验证且通过；
2. 用户人工验证且通过；
3. 未运行/受阻；
4. 已接受限制与 Medium/Low 问题。

只有以下人工证据同时存在才能把阶段五、路线图和本任务改为 `Complete/Done`：

- 三类代表性真实工程副本的规定流程；
- 20 次连续 dogfood 记录通过校验；
- 没有未关闭 Critical/High，Medium 均有用户接受或修复记录。

否则 `docs/STATUS.md` 写 `Ready for manual acceptance`，阶段六保持未开始。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts/test_compatibility_manifest.py tests/e2e/test_core_client_contract_parity.py tests/evals/test_dogfood.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase5-acceptance-dist
git diff --check
```

审阅报告与实际命令输出一致后提交：

```bash
git commit -m "docs: freeze Core contracts and record phase five readiness"
```

## 验收标准

- 公共客户端契约可机器检查，有清晰兼容规则。
- 四客户端对相同 Core 事实一致，不依赖人类文本。
- 报告逐项对应阶段五 15 条退出条件。
- 缺少人工证据时不提前启动阶段六、不声称阶段五完成。
