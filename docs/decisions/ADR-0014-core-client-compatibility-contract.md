# ADR-0014：Core 客户端兼容契约

**状态：** Accepted
**日期：** 2026-09-13

## 背景

TUI、`--plain`、`--json`、`vera eval` 和未来桌面客户端必须依赖同一套结构化 Command/Event。若把 Widget、ANSI 或人类文案当成协议，展示变化就会破坏客户端，也会让审批与恢复无法独立验证。

## 决策

- 公共兼容面只包含：Command 名称与 `schema_version`、`EventEnvelope`、`RuntimeOutput`（持久 Event 与瞬时 Stream Frame）、稳定 error code、approval kind、recovery classification，以及 JSON Session 的 `SessionRecord` / `SessionAction`。
- 以只读 `CompatibilityManifest` 快照上述名称、版本、必需字段和兼容规则；序列化稳定，可供测试对照。
- 兼容规则三分：
  - `additive`：可在当前 `schema_version` 增加可选字段、事件类型或新命令名；旧客户端可忽略未知 additive 数据。
  - `deprecated`：字段在当前版本仍可读取，但不得重新变成必需；删除必须走 breaking。
  - `breaking`：重命名或删除必需字段、改变字段含义、撤销 decoder，必须提升 `schema_version` 并提供显式 decoder。
- TUI 文案、Widget 类、Rich 渲染和 CLI ANSI **不是**公共契约。
- 私有 snapshot、Journal 内部格式和评测夹具正文不属于本兼容面。

## 备选方案

### 以产品版本号代替契约版本

发布节奏与协议演进不同步，因此不采用。

### 把 CLI 文本列为稳定接口

会把展示改动变成协议破坏，并阻止桌面端直接消费 Core，因此不采用。

## 后果

- 四个当前客户端和未来桌面端可以机器检查同一份清单。
- 阶段六体验改动不得修改本清单中的必需字段含义。
- 未知未来版本继续返回 `unsupported_version`，不得静默改写。

## 验证与重审触发器

- `tests/contracts/test_compatibility_manifest.py` 对照当前模型。
- 四客户端对同一 Fake Model 场景的权威事实一致。
- 若需要删除某条旧 decoder，先定义支持周期和用户可执行的迁移路径。
