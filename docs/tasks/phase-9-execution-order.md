# 阶段九执行顺序：Core-native Skills

**状态：** 自动实现完成，等待人工验收

**入口说明：** 阶段九规格与 ADR 已 Accepted。按用户 2026-09-21 明确授权，阶段九在阶段八仍为 `In progress` 时使用独立工作树并行实施；后续用户于 2026-09-22 明确要求将当前代码和文档更新同步到 GitHub，因此本次允许合并与推送，但不覆盖阶段八状态切换或阶段十桌面代码。

## 任务顺序

| 顺序 | 任务 | 状态 | 本地提交 |
| --- | --- | --- | --- |
| 1 | [0067：Skill Manifest、Discovery、Registry 与公共契约](0067-skill-discovery-contracts.md) | Done | `8a436e7` |
| 2 | [0068：SkillSnapshotStore、原子冻结与安全清理](0068-skill-snapshots.md) | Done | `7cd2f19` |
| 3 | [0069：Session Selection、Run 绑定与 Context 装配](0069-skill-runtime-context.md) | Done | `965abe9` |
| 4 | [0070：CLI 命令与三客户端结构化投影](0070-skill-cli-projection.md) | Done | `ec1e7da` |
| 5 | [0071：NoSkill、兼容迁移与安装态整合](0071-skill-compatibility.md) | Done（安装态缓存阻断） | `33ae850` |
| 6 | [0072：阶段九自动验收与人工验收准备](0072-phase-9-skills-acceptance.md) | Ready for manual acceptance | 待用户确认 |

## 证据入口

- 自动矩阵：[阶段九 Core-native Skills 评测记录](../evals/phase-9-core-native-skills.md)
- 规格：[Core 原生 Skills 系统](../specs/2026-09-15-core-native-skills-system.md)
- 决策：[ADR-0020](../decisions/ADR-0020-stage-core-native-skills.md)

阶段九在用户确认前不得标记为 Complete；阶段十仍不得开始。
