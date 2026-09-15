# Core 原生 Skills 系统

**状态：** Draft
**日期：** 2026-09-15
**所属阶段：** 阶段八后候选能力；具体编号与公开准备的先后关系由 ADR-0020 决定

## 目的

让 Vera 能以可发现、可审阅、可复现的方式加载针对某类任务的工作方法、约束、模板与只读资源，使 Coding Agent 在不同工程和任务中复用成熟流程，而不把长篇说明永久塞进 System Prompt，也不把 Skills 变成绕过 Core 权限的执行后门。

Skills 是 Core 能力，不等同于插件市场：Skill 描述“如何完成一类工作”，Tool 提供“能够执行什么动作”，Policy/Approval 决定“当前是否允许执行”。安装来源、远程分发、第三方市场与商业生态在本阶段之外。

## 用户价值

- 用户能知道当前有哪些 Skills、它们来自哪里、为何被选中、实际加载了哪个版本。
- 常见 Coding 工作流可以复用稳定步骤、检查清单、模板和参考资料，而不是每次重新提示。
- Skill 只在相关任务中按需进入 Context，减少无关上下文占用。
- 同一次任务使用不可变 Skill 快照；磁盘上的 Skill 中途变化不会静默改变正在执行的行为。
- 工程内不可信 Skill 不能授予工具、网络、文件、命令或审批权限。

## 核心概念

### SkillPackage

一个 Skill 目录至少包含 `SKILL.md`，可选包含 `references/`、`templates/` 和只读资产。第一版不自动执行 Skill 自带脚本；未来若允许脚本，也必须转换为显式 Tool Action，经过 Workspace、PolicyEngine 与 ApprovalGate。

### SkillManifest

Core 从 `SKILL.md` 的受限元数据读取稳定身份和选择信息：

- `name`：同一作用域内唯一的规范名；
- `version`：可比较的版本；
- `description`：供用户审阅与候选选择；
- `triggers`：任务类型或显式调用条件；
- `entrypoint`：固定为包内 `SKILL.md`；
- `resources`：允许加载的相对路径清单；
- `compatibility`：Skill 格式版本与最低 Vera Core 版本。

Manifest 不能声明额外权限、可信级别、免审批动作、任意环境变量或启动命令。

### SkillSource 与优先级

第一版只发现三类本地来源：

1. Vera 内置 Skills；
2. 当前用户显式安装的 Skills；
3. 当前 workspace 内的 Skills。

同名覆盖顺序为“用户显式选择 > 当前用户安装 > Vera 内置 > workspace 建议”。workspace Skill 始终属于不可信工程内容，只能成为候选建议，不能覆盖内置安全规则或用户已固定的 Skill。冲突、版本不兼容和路径异常必须可见，不静默任选一个。

### SkillSelection 与 SkillSnapshot

- 用户可通过明确命令选择 Skill；自动选择只能依据 Manifest 中的受限元数据和当前任务分类，结果必须可见且可关闭。
- Core 在 Run 开始前解析 Skill，生成包含规范名、版本、来源、内容哈希和资源哈希的不可变 `SkillSnapshot`。
- Run 只消费 Snapshot，不在模型循环中反复读取可变磁盘文件。
- Journal/Event 记录 Skill 身份、版本、来源和哈希，不复制完整 Skill 正文、工程私有内容或模板输出。

## Core 边界

新增 UI 无关模块建议按职责拆分：

- `vera.skills.manifest`：受限元数据模型与格式校验；
- `vera.skills.discovery`：在允许根目录内发现候选，不跟随越界符号链接；
- `vera.skills.registry`：名称、版本、来源冲突与兼容性解析；
- `vera.skills.selection`：显式选择与可解释的候选匹配；
- `vera.skills.snapshot`：有界读取、哈希与 Run 固定快照；
- `vera.skills.context`：把已选 Skill 的必要片段装配为带 provenance 的不可信/受限 Context，而不是高于用户与安全策略的指令层。

CLI 与未来桌面端只消费结构化 `SkillSummary`、`SkillSelection`、`SkillSnapshot` 和错误码，不扫描目录、不解析 `SKILL.md`、不复制选择算法。

## CLI 用户流程

第一版提供以下只读或显式会话入口：

- `/skills`：列出可用、冲突、损坏和不兼容的 Skills，并显示来源与版本；
- `/skills show <name>`：显示 Manifest、来源、资源清单、哈希和当前可用性，不默认展开完整正文；
- `/skills use <name>`：为下一次 Run 显式选择一个 Skill；
- `/skills clear`：清除当前显式选择；
- `/status`：显示当前会话选择和活动 Run 的固定 Skill Snapshot 身份。

第一版自动选择最多一个主 Skill；组合多个 Skills、依赖解析和工作流编排等到真实单 Skill dogfood 稳定后再评估。显式 Skill 名不存在、冲突或不兼容时拒绝开始对应 Run，并保留用户输入供修正。

## 安全与信任边界

- 内置安全策略、用户当前目标与具体审批、用户配置、工程约定、不可信内容的既有权威顺序保持不变；Skill 不能把自己声明为更高权威。
- Skill 文本、references、templates 和未来外部来源都通过 `ContentEnvelope` 标记 provenance；检测结果只能保持或收紧 Policy。
- Skill 不能新增 Tool、放宽 WorkspacePaths、修改命令允许前缀、读取 Provider Key、声明网络权限或替代 ApprovalGate。
- 发现与加载使用允许根、普通文件、符号链接逃逸检查、单文件/整包字节上限、文件数上限和解析超时。
- 公共 Event 与 Journal 只记录身份和哈希，不写入完整 Skill 正文、用户私有模板内容、模型请求或秘密。
- Skill 损坏、过大、编码非法、Manifest 未知字段、版本不兼容或加载竞态时失败关闭该 Skill；未显式要求该 Skill 的普通对话可在清楚告警后不加载它继续。

## 非目标

- 第三方 Skill 市场、搜索、评分、支付、远程更新或自动安装；
- 把 Skills 当作任意 Python/Shell/Node 脚本执行器；
- 允许 Skill 注册新权限、永久授权或绕过 Change Set 审批；
- 多 Skill 依赖图、递归调用、Skill 自主创建 Skill 或 Multi-Agent 编排；
- 把整个 Skill 库长期注入每次模型请求；
- 让 CLI/桌面 Renderer 成为 Skill 解析与信任判断的权威。

## 计划增量

本候选阶段在本规格与 ADR-0020 转为 Accepted 后再建立连续编号任务，按以下顺序实施：

1. 冻结 `SkillManifest`、`SkillSummary`、`SkillSelection`、`SkillSnapshot`、错误码和兼容性夹具；
2. 实现安全本地发现、来源优先级、冲突诊断和资源边界；
3. 实现显式选择、单 Skill 自动候选、Run 快照和 Context 装配；
4. 接入 SessionController、`/skills`、Plain/JSON 对照与状态展示；
5. 以内置只读“工程理解”Skill 完成离线评测、真实工程 dogfood、故障与安全矩阵；
6. 桌面端仅通过 Core 契约展示与选择 Skill，不复制加载器。

每个增量只允许一个主实现 Agent，遵循规格接受、TDD、独立验证、文档同步和单独提交。阶段八的桌面基础闭环不依赖 Skills，不得以本规格为由提前扩展阶段八范围。

## 验收标准

1. 同一 Skill 包在相同 Core/配置下得到确定的 Manifest、资源集合和内容哈希。
2. 内置、用户和 workspace 来源的覆盖、冲突、不兼容与显式选择行为可解释且有负例测试。
3. 路径逃逸、符号链接、过大文件、未知字段、损坏编码和加载竞态不会读取越界内容或扩大权限。
4. Run 使用固定 `SkillSnapshot`；执行中修改磁盘 Skill 不影响该 Run，下一 Run 才能看到新版本。
5. Skill 只改变提供给模型的工作方法上下文，不改变 ToolRegistry、PolicyEngine、ApprovalGate、Workspace、Recovery 或验证权威。
6. TUI、Plain、JSON 与未来桌面端对同一 Skill 事实语义一致；客户端不解析 Skill 文件。
7. `/skills`、显式选择、清除、缺失、冲突、损坏和不兼容流程均可在无网络、无 Provider Key 的测试中验证。
8. 真实 Terminal.app 和至少两个真实工程完成单 Skill dogfood，没有未关闭的 Critical/High 安全或正确性问题。

## 转为 Accepted 前的决策

1. 用户安装目录是否固定为 Vera 私有配置目录，workspace 目录名采用 `.vera/skills/` 还是 `skills/`。
2. 第一版是否允许 workspace Skill 自动成为候选，还是只能显式 `/skills use`。
3. `SKILL.md` 元数据采用 YAML frontmatter 还是独立 `skill.toml`；两者不能同时成为权威。
4. 自动选择的可解释证据显示到何种粒度，既能审阅又不泄漏完整用户目标。
5. 首个 Skills 阶段是否只交付内置/本地 Skills，远程安装继续留到公开发布后的独立阶段。

## 关联

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [阶段七：CLI 体验收口与个人主力化](2026-09-13-cli-experience-and-personal-dogfood.md)
- [阶段八：桌面 Agent 工作台与 UI](2026-09-12-desktop-agent-workbench-ui.md)
- [不可信内容与提示词投毒防御](2026-09-12-untrusted-content-and-prompt-injection-defense.md)
- [ADR-0015：不可信内容信任边界](../decisions/ADR-0015-untrusted-content-trust-boundary.md)
- [ADR-0020：在桌面基线后规划 Core 原生 Skills 阶段](../decisions/ADR-0020-stage-core-native-skills.md)
