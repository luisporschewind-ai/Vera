# 任务 0067：Skill Manifest、Discovery、Registry 与公共契约

**状态：** Done（代码与局部门禁通过）；阶段九已获用户授权，可与阶段八人工验收并行推进

**Goal：** 为 builtin、user、workspace 三种本地来源建立严格、可审阅且不泄漏私有路径的 Skill Manifest 解析、发现、Registry、显式选择和公共契约基础。

**范围：** 本任务只交付 Manifest、Discovery、Registry 与错误/兼容性契约，不接入 Runtime、Snapshot、Context 或 CLI。workspace Skill 仍标记为 `untrusted`，任何 Skill 都不能注册 Tool、扩大 Workspace、改变 Policy/Approval、声明网络或执行脚本。

**规格：** `docs/specs/2026-09-15-core-native-skills-system.md`、`docs/decisions/ADR-0020-stage-core-native-skills.md`、`docs/decisions/ADR-0021-core-tools-before-desktop.md`

## 实现内容

- 新增 `SkillSummary`、`SkillSelection`、`SkillSnapshot` 及选择/绑定 payload 公共契约，使用封闭 Pydantic schema。
- 新增严格 `skill.toml` 解析：封闭字段、严格 SemVer、lower kebab-case 名称、UTF-8、资源根限制、重复规范路径拒绝、符号链接/特殊文件拒绝和 32 文件/64 KiB/128 KiB 上限。
- 新增三来源非递归 Discovery，仅在允许根的直接子目录中检查包，不跟随符号链接。
- 新增 Registry：稳定排序、available/conflict/invalid/incompatible 摘要、裸名称冲突拒绝和完整 `skill_id` 显式消歧。
- 新增阶段九稳定错误码，并在 CompatibilityManifest 中声明 Core-native Skill 事实为 additive；NoSkill 仍为默认行为。

## 验收证据

已通过：

```text
16 passed
ruff check（0067 新增源码与测试）通过
mypy src/vera/contracts/skills.py src/vera/skills 通过
git diff --check 通过
```

本任务提交：`feat: add core skill discovery contracts`

覆盖范围包括：

- 有效 Manifest、未知字段、非法版本/名称、格式版本、路径逃逸、规范化冲突、缺失资源、符号链接、超限和非法 UTF-8；
- builtin/user/workspace 三来源、根目录缺失、只扫描直接子目录和符号链接包诊断；
- 同名冲突、完整 `skill_id` 消歧、不兼容包、非法包和公共摘要不泄漏绝对路径或正文；
- 公共契约拒绝未知字段且不携带 Skill 正文。

## 未完成与边界

- Snapshot 原子冻结、源竞态复核、恢复和安全清理属于任务 0068；
- Session 选择持久化、Run 绑定、Context 装配和 NoSkill Runtime 回归属于任务 0069；
- CLI/TUI/Plain/JSON 投影属于任务 0070；
- 本任务不修改阶段八状态，不合并或删除任何已有分支/工作树，也不代表阶段九完成。

## 复核重点

- Manifest 无法建立规范身份时，公共摘要不使用目录名伪造 `name` 或 `skill_id`；
- 同名候选不按来源静默覆盖，只有完整来源前缀 ID 可以显式消歧；
- 所有新契约和错误保持 additive，旧客户端与 NoSkill 路径不被强制要求理解 Skill 内容。
