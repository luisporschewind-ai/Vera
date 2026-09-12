# Vera 公共协议

**状态：** Frozen for Phase 5 clients  
**日期：** 2026-09-13  
**决策：** [ADR-0014](decisions/ADR-0014-core-client-compatibility-contract.md)、[ADR-0002](decisions/ADR-0002-command-event-contract.md)、[ADR-0006](decisions/ADR-0006-versioned-state-codecs.md)

机器可读清单由 `vera.contracts.compatibility.current_compatibility_manifest()` 生成。本文只解释规则，不复制 TUI 文案。

## 调用链

```text
Command -> VeraRuntime.handle -> EventEnvelope | StreamFrame
```

四个当前客户端（默认 TUI、`--plain`、`--json`、`vera eval`）必须消费上述结构。桌面客户端不得解析人类 CLI 输出。

## 当前版本

- 公共 `schema_version`：`1`
- 协议清单 `protocol_version`：`1`
- Command：`start_run`、`resolve_approval`、`cancel_run`、`rollback_run`、`inspect_recovery`、`resume_run`、`abandon_run`、`inspect_state`、`plan_state_migration`、`apply_state_migration`
- RuntimeOutput：持久 `event` 与瞬时 `stream`
- JSON Session record：`event` / `stream`
- JSON Session action：`prompt.submit`、`session.command`、`approval.resolve`、`run.cancel`、`session.close`

## 兼容规则

| 类别 | 允许 | 禁止 |
|---|---|---|
| additive | 新的可选字段、新事件 type、新命令名 | 把新字段标成旧客户端的必需项 |
| deprecated | 保留可读、停止推荐 | 在同一 `schema_version` 删除或改义 |
| breaking | 提升 `schema_version` 并注册 decoder | 静默改必需字段、改枚举含义、丢弃旧 decoder |

## 明确排除

- TUI Widget、区域 id、焦点文案、主题
- CLI ANSI、表格排版、帮助段落措辞
- 私有 recovery snapshot 字段（除非已提升为公共 Event）
- 用户目标原文、源码、Key/Token

## 错误、审批与恢复

- 稳定 `CoreErrorCode` 见 `vera.contracts.errors`
- 审批 kind：`changeset`、`command`、`recovery`
- 恢复分类：`resumable_approval`、`resumable_verification`、`safe_to_abandon`、`recoverable_partial_apply`、`manual_required`、`legacy_not_resumable`

新增公共事件或命令时，先更新清单测试，再改客户端。
