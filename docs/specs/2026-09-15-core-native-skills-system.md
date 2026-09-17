# Core 原生 Skills 系统

**状态：** Accepted
**日期：** 2026-09-15
**接受：** 2026-09-17 用户确认总体架构、公共契约、Snapshot、CLI 与验收设计
**所属阶段：** 阶段九——Core-native Skills（尚未开始；由 ADR-0021 从阶段八顺延）

## 目的

让 Vera 通过可发现、可审阅、可复现的本地 Skill 包复用一类任务的工作方法、检查清单、模板和参考资料，同时保持 Vera Core 对发现、选择、信任、运行快照、恢复、Context 与结构化事实的唯一控制权。

Skill 只描述“如何工作”。Tool 描述“能够执行什么动作”；`Workspace`、`PolicyEngine`、`ApprovalGate`、`Verification`、`Checkpoint` 与 `Recovery` 决定动作是否允许、如何执行以及如何恢复。Skill 不能把文本说明转换为权限，也不能成为绕过旧 `ChangeSet` 或新版 `FileMutationPlan` 的执行后门。

阶段九只交付 UI 无关的 Core 能力与完整 CLI 验收。未来阶段十桌面端只消费相同结构化契约，不自行发现、解析或信任 Skill 包。

## 已确认决策

- 采用“Core 控制面 + 外部 Skill 包”。Skill 包可以独立维护和分发，运行语义由 Core 统一控制。
- v1 只支持 Vera 内置、用户本地和 workspace 本地三种来源。
- 用户目录固定为 `platformdirs.user_config_path("Vera") / "skills"`；workspace 目录固定为 `<workspace>/.vera/skills/`。
- `skill.toml` 是唯一权威 Manifest；`SKILL.md` 不使用 YAML frontmatter 表达权威元数据。
- v1 只允许显式选择一个主 Skill，不做自动候选、多 Skill 组合或依赖解析。
- workspace Skill 始终是不可信工程内容，只能由用户显式选择。
- v1 只读取 UTF-8 文本形式的 `SKILL.md`、`references/` 与 `templates/`；不执行 Skill 自带脚本。
- Run 开始前把实际使用内容冻结到 Core 私有 `SkillSnapshotStore`；运行与恢复不重新读取原始包。
- 插件、Hook、可执行扩展、远程安装、市场、评分、支付和自动更新不属于 Skills v1。

## Skill 包边界

### 目录结构

一个 v1 Skill 包具有以下结构：

```text
<skill-package>/
├── skill.toml
├── SKILL.md
├── references/       # 可选
└── templates/        # 可选
```

除 `skill.toml`、`SKILL.md` 和 Manifest 明确声明的资源外，Core 不读取包内其他文件。`scripts/`、可执行文件、设备文件、套接字、符号链接和越界路径一律不进入 v1 Snapshot。

### 来源

| `source_kind` | 根目录 | 信任分类 | v1 选择方式 |
| --- | --- | --- | --- |
| `builtin` | Vera 安装包内的只读 Skills 根 | `advisory` | 显式 |
| `user` | `platformdirs.user_config_path("Vera") / "skills"` | `advisory` | 显式 |
| `workspace` | `<workspace>/.vera/skills/` | `untrusted` | 只能显式 |

内置与用户 Skill 也不是 `builtin_policy`。来源分类只影响 provenance、冲突诊断与安全展示，不能授予 Tool、网络、Workspace、秘密或免审批能力。

## `SkillManifest`

`skill.toml` 使用严格、封闭且版本化的 TOML Schema。v1 形状如下：

```toml
format_version = 1
name = "python-project-review"
version = "1.0.0"
description = "以固定检查清单审阅 Python 工程"

[compatibility]
min_vera_core = "0.1.0"
max_vera_core_exclusive = "1.0.0"

[resources]
references = ["references/checklist.md"]
templates = ["templates/report.md"]
```

约束如下：

- `name` 使用规范化小写 kebab-case，在单个来源根内唯一；
- `version`、`min_vera_core` 和可选的 `max_vera_core_exclusive` 使用严格 SemVer；
- `description` 是供用户审阅的短文本，不参与授权；
- `SKILL.md` 是固定入口，不允许通过 Manifest 改为其他文件；
- `references` 与 `templates` 只能声明包内规范化相对路径；
- 未知字段、重复规范路径、绝对路径、空段、`.`、`..`、NUL 和规范化后冲突均拒绝；
- v1 不定义 `triggers`、权限、命令、环境变量、网络、Hook 或脚本字段；未来自动候选必须通过新 `format_version` 与独立规格引入。

## 公共 Core 契约

### `SkillSummary`

供 CLI 与未来桌面端发现和审阅候选。Manifest 有效时至少包含：

- `schema_version`；
- `skill_id`：`builtin:<name>`、`user:<name>` 或 `workspace:<name>`；
- `name`、`version`、`description`；
- `source_kind` 与 `trust_level`；
- `availability`：`available`、`conflict`、`invalid` 或 `incompatible`；
- `manifest_hash` 与聚合 `resource_hash`；
- `reason_codes`，不包含完整正文或秘密路径。

Manifest 无法建立规范身份时，Summary 以来源内安全候选引用和 `availability=invalid` 返回诊断；`skill_id`、规范名称、版本和 hash 保持缺失，不能用目录名伪造有效身份。

### `SkillSelection`

表示会话希望下一次 Run 使用什么，而不是活动 Run 已经使用什么，至少包含：

- `schema_version`；
- `mode`：v1 只允许 `none` 或 `explicit`；
- 用户输入的 `selector`；
- 成功解析后的 `skill_id`、来源、版本与 `manifest_hash`；`mode=none` 或解析失败时这些字段为空；
- 选择状态和稳定 `reason_codes`。

`/skills use <name>` 只在规范名唯一时成功。同名候选不按来源静默覆盖，返回 `skill_name_conflict`；用户可以使用完整 `skill_id` 显式消歧。显式选择在未来 v2 中继续高于自动候选。

### `SkillSnapshot`

公共 `SkillSnapshot` 是冻结内容的安全描述符，不包含正文，至少包含：

- `schema_version`；
- `snapshot_id`；
- `skill_id`、`name`、`version` 与 `source_kind`；
- `manifest_hash`、`package_hash` 与聚合 `resource_hash`。

私有 Snapshot 记录另外保存规范化 Manifest、冻结文件表、相对路径、长度、逐文件 hash 与文件原始字节。客户端不得获得私有 Store 路径。

## Core 控制面

Core 按单一职责提供以下 UI 无关边界；模块名是规划边界，不授权当前实现：

- `manifest`：严格解析 `skill.toml` 与兼容性；
- `discovery`：只在允许来源根发现包，不跟随符号链接；
- `registry`：生成 `SkillSummary`，处理名称、版本、来源与冲突；
- `selection`：保存和恢复会话级显式选择；
- `snapshot`：有界读取、内容寻址、原子冻结、校验与安全清理；
- `context`：把已绑定 Snapshot 装配为带 provenance 的受限 Context；
- `projection`：向 TUI、Plain、JSON 与未来桌面端提供同一结构化事实。

数据流固定为：

```text
外部 Skill 包
  → Discovery / Manifest Validation
  → Registry / Explicit Selection
  → SkillSnapshotStore 原子冻结
  → Run 绑定 snapshot_id
  → Context Assembly 读取冻结副本
  → VeraRuntime / Agent loop
```

Skill 只在 Run 启动和 Context 装配边界接入。它不能修改 `ToolRegistry`，不能扩大 `Workspace`，不能覆盖 `PolicyEngine` 或 `ApprovalGate`，不能改变 `Verification`、`Checkpoint`、`Recovery` 或既有 Event/Journal 的事实权威。

## `SkillSnapshotStore`

### 私有布局与身份

Store 位于：

```text
<state_dir>/skills/snapshots/sha256/<digest>/
```

`snapshot_id` 对以下规范化输入进行带格式版本、带域分隔的 SHA-256：

1. Snapshot 格式版本；
2. `skill_id` 与 `source_kind`；
3. 规范化 Manifest；
4. 按相对路径排序的冻结文件表；
5. 每个文件的路径、长度和原始字节。

来源进入身份，避免内容相同的 workspace Skill 与内置 Skill 共享同一信任身份。绝对源路径不进入公共身份，也不写入公共 Event。

### 原子冻结

Run 开始前执行以下步骤：

1. 在允许来源根内解析并验证包；
2. 只读取 Manifest 声明的普通 UTF-8 文件；
3. 拒绝符号链接、特殊文件、路径逃逸和规范化冲突；
4. 在私有临时目录复制实际字节并计算 hash；
5. 再次确认源文件身份、长度和内容事实没有变化；
6. 以目录 `0700`、文件 `0600` 写入，完成 flush/fsync 后原子发布；
7. 发布成功后才创建或启动绑定该 `snapshot_id` 的 Run。

冻结期间源文件变化返回 `skill_source_changed`。写入失败不留下可引用的半成品 Snapshot，也不建立半初始化 Run。

### 恢复

- Run 与恢复流程只读取 `snapshot_id` 指向的冻结副本，并重新校验格式与 hash；
- 原始 Skill 被修改、移动或删除后，恢复行为不变；
- Snapshot 缺失、损坏或版本未知时停止恢复，不回退到当前磁盘包；
- Checkpoint 不复制 Skill 正文，只保留 Run 对 Snapshot 的权威引用；
- 公共 Event/Journal 只记录身份、来源、版本、聚合 hash 与 `snapshot_id`。

### 保留与安全清理

- Store 通过 Run/Session 权威记录做 mark-and-sweep 引用扫描，不信任可漂移的单独引用计数；
- 被活动、可恢复或仍保留的 Run/Session 引用时持续保留；
- 最后一个引用消失后进入至少 30 天孤儿宽限期；
- 不允许按年龄删除仍被引用的 Snapshot；
- 清理只针对通过路径、格式、权限、非符号链接和内容地址校验的精确 Snapshot 根；
- 元数据损坏、版本未知或引用状态不确定时返回 `skill_snapshot_cleanup_refused` 并保留内容；
- 清理不进入普通启动关键路径，结果以结构化扫描、保留、删除和失败计数呈现。

## Context 装配与限制

v1 只支持小型、完全可冻结的文本包：

- `skill.toml`、`SKILL.md` 与声明资源合计最多 32 个文件；
- `SKILL.md` 和任一资源最多 64 KiB；
- 整包冻结与装配内容最多 128 KiB；
- 所有内容必须是有效 UTF-8；
- 超限或非法编码直接拒绝，不静默截断。

Core 从冻结 Snapshot 按规范路径顺序装配 `SKILL.md`、`references` 和 `templates`。每段内容携带 `skill_id`、`source_kind`、相对路径与内容 hash。内置和用户 Skill 使用 `advisory`；workspace Skill 使用 `untrusted`。任何 Skill Context 都低于 Vera 内置安全策略、用户当前目标和针对具体动作的有效审批。

## `NoSkill` 路径

未启用 Skills 能力时必须保持现有行为：

- 不扫描任何 Skill 目录；
- 不创建 `SkillSelection` 或 Snapshot；
- 不向 Context 注入 Skill 内容；
- 不增加 Run Event 或 Journal 字段；
- 现有 `VeraRuntime`、Agent loop、CLI、Plain、JSON、Recovery 与 Checkpoint 投影保持兼容。

Skills 能力已启用但选择为 `none` 时，普通 Run 同样不扫描 workspace、不创建 Snapshot、不注入 Context，也不产生 `skill.snapshot.bound`。只有启用该能力的客户端状态投影可以显示 `selected_skill=none`。

## CLI 用户流程

v1 提供：

- `/skills`：按名称与来源稳定排序，列出可用、冲突、损坏和不兼容的 Skill；
- `/skills show <name|skill_id>`：显示 Manifest、来源、信任、资源清单、hash 与诊断，不默认展开完整正文；
- `/skills use <name|skill_id>`：为下一次 Run 设置显式选择；
- `/skills clear`：清除后续 Run 的选择，不改变活动 Run；
- `/status`：分别显示会话待用 `SkillSelection` 和活动 Run 的 `SkillSnapshot`。

选择随持久化会话恢复。每个新 Run 重新解析所选来源并生成或复用相同内容地址的 Snapshot；磁盘内容变化只影响下一 Run。TUI、Plain 与 JSON 消费同一 Core 结构化结果，JSON 不包含 ANSI，也不要求解析人类文案。

至少提供以下结构化事实：

- `skill.selection.changed`：会话选择被设置或清除；
- `skill.snapshot.bound`：Run 已绑定不可变 Snapshot。

预 Run 冻结失败返回稳定错误并保留用户输入供修正，不创建伪造的 Run。Event/Journal 不记录 Skill 正文、模板内容、完整用户目标或私有绝对路径。

## 稳定错误码

| 边界 | 错误码 |
| --- | --- |
| 发现与 Manifest | `skill_not_found`、`skill_manifest_missing`、`skill_manifest_invalid`、`skill_manifest_version_unsupported`、`skill_version_incompatible`、`skill_name_conflict` |
| 资源与安全 | `skill_path_escape`、`skill_symlink_refused`、`skill_resource_missing`、`skill_resource_invalid`、`skill_package_limit_exceeded`、`skill_source_changed` |
| Snapshot 与恢复 | `skill_snapshot_write_failed`、`skill_snapshot_missing`、`skill_snapshot_corrupt`、`skill_snapshot_version_unsupported`、`skill_snapshot_cleanup_refused` |

公共错误只携带 `code`、处理阶段、可选 `skill_id`、安全详情和可重试事实。不得包含完整 Skill 正文、模板内容、用户目标、秘密或私有绝对路径。

## 安全与失败行为

- Skill 声称可以注册 Tool、网络、命令前缀、Workspace、Provider Key、免审批动作或永久授权时，该文本只作为待分析内容，不产生对应能力；
- workspace Skill 永远不能把自己提升为 `advisory`、`user_intent` 或 `builtin_policy`；
- 显式选择 workspace Skill 不等于批准其建议的任何动作；
- 路径逃逸、符号链接、特殊文件、加载竞态、格式损坏与兼容性失败均关闭当前 Skill；
- 选择失败或冻结失败不丢弃用户消息，不回退选择同名其他来源；
- 活动 Snapshot 损坏时阻止继续和恢复，不使用原始包“修复”历史事实；
- Skill 内容经过现有 `ContentEnvelope` provenance 与投毒防御；风险信号只能保持或收紧策略；
- Skill 不能绕过 Core 文件变更计划、参数绑定审批或验证产物隔离。

## 离线验证与安全矩阵

自动验证不访问网络、不读取真实 Provider Key，并使用临时 `state_dir` 与临时 workspace。至少覆盖：

1. 内置、用户、workspace 三来源的发现、选择、冲突与兼容性；
2. 未知字段、非法版本、编码错误、大小/文件数超限和规范化路径冲突；
3. 绝对路径、`..`、符号链接、特殊文件、权限失败、inode/内容竞态；
4. workspace Skill 诱导注册工具、读取 Key、扩大 Workspace、声明网络、跳过审批或绕过 Core 文件变更计划；
5. 原始包在 Run 后修改、移动和删除，恢复仍使用冻结副本；
6. Snapshot 缺失、损坏、未知版本以及安全清理的引用、宽限和拒绝路径；
7. TUI、Plain、JSON 对相同 `SkillSummary`、`SkillSelection`、`SkillSnapshot` 与错误的语义一致性；
8. 完整 `NoSkill` 回归，证明未启用时现有行为、Event 与 Journal 不变。

真实验收必须在 Terminal.app 完成 `/skills`、查看、选择、清除、状态、失败与恢复，并在一个 Python 工程和一个 Swift/Xcode 工程的安全副本中完成 dogfood。不得把自动测试、Textual Pilot、快照或桌面原型当作真实 Terminal.app 证据。

未关闭的权限扩大、Snapshot 身份混淆、恢复读取可变源、正文泄漏或审批绕过属于 `Critical/High`，阻止阶段九完成。

## 演进分层

### v1：本地单 Skill

- 三种本地来源；
- 显式选择；
- 单个主 Skill；
- 只读文本资源；
- 不可变 Snapshot、恢复和完整 CLI 验收。

### v2：自动候选与多 Skill

通过新 Manifest 版本和独立规格增加自动候选、多 Skill 组合与依赖。自动候选的解释只公开名称、版本、来源、`selection_mode`、稳定 `reason_codes`、命中的声明式 trigger 标识、任务类别和简短取舍；不公开完整用户目标、Context 原文、模型思维过程或内部详细评分。

### v3：签名远程分发

通过独立供应链规格增加签名来源、远程分发、版本锁定、更新、回滚和撤销。市场、评分、支付与商业生态仍单独决策。

Plugin、Observer Hook、Action Hook 与任何可执行能力始终是独立体系。未来 Action Hook 必须把结构化动作重新送入 `Workspace -> PolicyEngine -> ApprovalGate -> execute -> Event/Journal`，不能借 Skill 身份获得执行权限。

## 非目标

- 远程安装、市场、评分、支付、自动更新或远程执行；
- 自动候选、多 Skill 依赖、递归调用或 Multi-Agent 编排；
- 执行包内 Python、Shell、Node 或其他脚本；
- 让 Skill 注册权限、网络、环境变量、Tool 或审批豁免；
- 把整个 Skill 库永久注入每次模型请求；
- 让 CLI 或桌面 Renderer 成为文件解析、信任或选择权威；
- 在阶段八工具/Policy/Git 完成前建立阶段九实施任务或产品代码。

## 验收标准

1. 相同包、来源与 Core 格式得到确定的 Manifest、文件集合、hash 和 `snapshot_id`；
2. 三种来源、显式选择、同名冲突和完整 `skill_id` 消歧行为可解释；
3. 路径、文件类型、大小、编码、兼容性和加载竞态失败关闭且不读取越界内容；
4. Run 与恢复只使用冻结 Snapshot，原始包后续变化不影响已开始 Run；
5. 公共 Event/Journal 不包含完整正文、模板内容、用户目标或私有路径；
6. Skill 只改变受限工作方法 Context，不改变任何执行与恢复权威；
7. `NoSkill` 路径与阶段七封存的现有 Runtime、CLI、Plain、JSON 行为兼容；
8. Snapshot 引用、30 天宽限和安全清理矩阵通过；
9. 离线矩阵、真实 Terminal.app 和两个真实工程副本 dogfood 没有未关闭的 Critical/High；
10. 阶段十桌面端能够只通过公共契约消费同一事实，不需要复制 Skills 控制面。

## 阶段门禁

本规格被接受只完成 Skills 架构规划，不表示阶段九已经开始。2026-09-17 用户已原文确认「CLI 版本达到预期，可以封存」；ADR-0021 随后把工具集、Policy v2 与原生 Git 插入为阶段八。Skills 实施还必须等待阶段八 Complete 与独立实施授权。本次仍然：

- 不建立阶段九实施任务；
- 不修改 `src/` 或 `tests/` 实现 Skills；
- 不引入桌面代码或依赖；
- 保持阶段九 `Not started`，等待阶段八完成与独立实施授权。

阶段八完成后才能进入阶段九 Skills；阶段九完成后才能进入阶段十桌面集成。桌面不是 Skills 的实现前置条件。

## 关联

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [阶段七：CLI 体验收口与个人主力化](2026-09-13-cli-experience-and-personal-dogfood.md)
- [阶段十：桌面 Agent 工作台与 UI](2026-09-12-desktop-agent-workbench-ui.md)
- [不可信内容与提示词投毒防御](2026-09-12-untrusted-content-and-prompt-injection-defense.md)
- [ADR-0015：不可信内容信任边界](../decisions/ADR-0015-untrusted-content-trust-boundary.md)
- [ADR-0020：在 CLI 封存后、桌面之前插入 Core-native Skills 阶段](../decisions/ADR-0020-stage-core-native-skills.md)
- [ADR-0021：桌面前插入 Core 工具集与 Git 能力阶段](../decisions/ADR-0021-core-tools-before-desktop.md)
