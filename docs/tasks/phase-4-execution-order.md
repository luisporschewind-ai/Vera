# Vera 阶段四执行顺序

**状态：** Complete
**规格：** [阶段四：评测与内部就绪](../specs/2026-09-12-evals-and-internal-readiness.md)
**架构决策：** [ADR-0011：评测工具作为隔离的 Core 客户端](../decisions/ADR-0011-eval-harness-as-core-client.md)

## 目标

阶段四增加一个只消费 Core Command/Event 的离线评测客户端，用 14 个冻结 Fake Model case 重复验证正确性、安全、恢复、延迟和用量证据。它不调用真实 Provider，不解析 TUI/CLI 文本，也不提前桌面端。

## 执行前提

- 从最新干净 `main` 创建每个任务指定的 feature 分支。
- 每次只由一个主实现 Agent 修改当前工作树；不得并发执行两个阶段四任务。
- 每个生产行为遵循 Red → Green → Refactor，并在任务内形成小提交。
- 非 live 测试必须清除供应商变量并把 `VERA_PROVIDER_ENV_FILE` 指向不存在的临时路径。
- 不读取真实 DeepSeek/GLM Key，不运行 `tests/live`，不修改 `/Users/admin/Desktop/VeraTestDemo`。
- 不把 Worker 子进程描述为 OS 沙箱；本地执行仍继承当前系统用户权限。

## 顺序

1. [任务 0015：评测契约、Corpus 与夹具隔离](0015-eval-contracts-and-fixtures.md)
2. [任务 0016：Worker、Runner 与基础评分](0016-eval-runner-and-scoring.md)
3. [任务 0017：恢复场景、指标与确定性](0017-eval-recovery-and-metrics.md)
4. [任务 0018：评测 CLI 与 14 个冻结任务](0018-eval-cli-and-corpus.md)
5. [任务 0019：阶段四完整验收](0019-eval-phase-4-acceptance.md)

前一任务必须完成局部测试、完整非 live 门禁、验收记录、提交和本地合并，下一任务才可开始。

## 规格覆盖

| 能力 | 主任务 |
| --- | --- |
| 版本化契约、manifest、资源发现、临时隔离 | 0015 |
| 子进程硬超时、Runtime 驱动、文件评分、证据包 | 0016 |
| 恢复 failpoint、Runtime 重建、usage/latency、canonical projection | 0017 |
| `vera eval validate/list/run`、14 个 case、wheel 资源 | 0018 |
| 14 条退出条件、重复运行、安全负例与阶段收口 | 0019 |

## 完成定义

只有任务 0015–0019 全部合并，14 个离线 case 全部通过，阶段四规格的 14 条退出条件逐项有证据，才能把阶段四标记为 `Complete`。真实供应商效果和桌面端仍不在本阶段完成定义内。
