# ADR-0021：桌面前插入 Core 工具集与 Git 能力阶段

**状态：** Proposed
**日期：** 2026-09-17

## 背景

阶段七已经完成并由用户确认 CLI 可以封存。后续讨论发现，当前 Vera 虽然具备安全编辑、验证、Checkpoint、恢复和成熟 CLI 表面，但默认模型工具仍是早期垂直切片：只读工具加单个 `propose_changeset`，缺少成熟 Coding Agent 的 `read/write/edit/bash` 工具循环，也没有原生 Git Commit 能力。

用户明确希望先扩展工具集、在工具能力上对齐 Pi，并加入 Git 状态、Diff、历史、提交和后续分支能力。同时，当前“一律审批 Change Set、未知命令默认审批或拒绝”的早期策略会在日常使用中产生过多卡点，需要升级为按用户目标、工作区信任和实际副作用分级的 Policy v2。

若按现有路线直接启动阶段八桌面，Renderer 和桌面交互将被迫围绕一个尚未成熟的工具、权限和 Git Core 建立，之后再升级会同时改动 CLI、桌面和协议，增加返工与安全分叉风险。

## 候选方案

### A. 桌面前插入独立 Core 工具集与 Git 能力阶段（推荐）

先以 CLI 和 Core 契约完成 ToolExecutor、Policy v2、Pi 对齐工具和原生 Git 本地能力，再启动桌面。桌面直接消费稳定的 ToolAction、PolicyDecision、Git 事实与审批契约。

优点是 Core-first 边界清楚，能以现有 CLI 做真实 dogfood，也避免桌面复制临时逻辑。代价是桌面开始时间顺延，现行阶段编号需要在决策接受后统一校准。

### B. 把工具与 Git 能力纳入桌面阶段

编号变化较小，但桌面阶段会同时承担 Tool Core、Policy、Git、Renderer、进程桥和打包，失败面过大；CLI 也无法先独立验证新能力。

### C. 只开放通用 `bash`，让模型直接运行 Git

实现最快，但不能为文件写入、Commit、index 保全、Hook、恢复和远程副作用提供稳定结构化契约；客户端只能解析人类输出或依赖不透明 ToolResult，违背 Vera 的 Core 权威边界。

### D. 桌面先行，工具和 Git 延后到桌面完成之后

保留现有路线，但桌面会固化早期工具模型，且不能满足用户当前“先扩展工具集”的优先级。

## 建议决策

接受方案 A，并固定以下方向：

1. 在当前阶段七与桌面阶段之间插入独立的 Core 工具集与 Git 能力阶段；正式阶段编号和后续顺延只在本 ADR 转为 Accepted 后更新。
2. 默认模型工具在名称与能力上对齐 Pi 的 `read/write/edit/bash`，但所有副作用仍经过 Vera Core 的 Workspace、PolicyEngine、ApprovalGate、Checkpoint、Recovery 与 Event/Journal。
3. `bash` 第一版是结构化 argv 命令能力，不解释原生 Shell 字符串；原生 Shell 语言等待 OS 沙箱与独立规格。
4. Policy v2 以 `balanced` 为推荐默认：可信工作区内明确目标授权的普通编辑、只读 Git 和已知验证自动执行，敏感、外部或高影响动作审批，越权和不可接受动作拒绝。
5. Git 作为一等 Core 能力包实现，不允许通用命令工具绕过。底层使用系统 Git CLI 与稳定机器格式，不引入 GitPython/libgit2。
6. 第一版 Git 范围为 `status/diff/log/show/branch-list/commit`；branch create/switch 在本地 Commit 稳定后进入同阶段增量；远程 fetch/pull/push 另立规格。
7. Skills 继续只描述工作方法和资源，不能注册 Tool、授予权限或执行任意包脚本。
8. 阶段七封存事实保持有效；新阶段是新增能力，不重写已完成验收历史。

## 阶段退出条件

- `read/write/edit/bash` 默认工具与辅助只读工具通过统一 ToolExecutor；
- Policy v2 的 trust、档位、风险、授权作用域和兼容迁移通过离线矩阵；
- Vera 能在不夹带用户既有 index 内容的情况下完成精确本地 Commit；
- 多动作 Run、Receipt 与恢复不会重复副作用；
- TUI、Plain、JSON 与 CompatibilityManifest 对同一事实一致；
- 三类真实工程完成 Terminal.app dogfood，无未关闭 Critical/High 正确性或安全问题；
- 本阶段不引入 Electron 或其他桌面代码。

## 后果

- 桌面阶段与现行阶段九、Skills 候选阶段的编号需要在本 ADR 接受后统一顺延和校准；
- ADR-0017 中“桌面为阶段八”的编号将由本 ADR 的新顺序取代，但其 CLI-first、显式封存门禁和桌面复用 Core 原则继续有效；
- ADR-0013 的 Electron 技术选择不变，只调整实施阶段编号；
- ADR-0020 必须按新的桌面阶段编号重新校准，Skills 仍位于桌面基础闭环之后；
- ToolDefinition、Policy、Approval、Run 恢复和 CompatibilityManifest 会产生受控演进，需要明确 additive/deprecated/breaking 分类；
- Git Commit 不取代 Vera Checkpoint；Git 远程能力不会随本决策自动获批。

## 接受前必须确认

1. 用户接受桌面再次顺延，先完成 Core 工具集与 Git 能力；
2. 用户接受 `bash` 首版只提供结构化 argv，不支持原生 Shell 语法；
3. 用户接受 `balanced` 为推荐默认、`review` 与 `autonomous` 为可选档位；
4. 用户接受第一版 Git 不包含 fetch/pull/push、force、reset --hard、clean 和自动历史改写；
5. 两份关联规格中的开放决策已经收束，不含影响实施路线的 TBD。

## 重新评审触发器

- 真实 dogfood 证明结构化 argv 无法满足常见 Coding 流程；
- Policy v2 无法在不增加频繁审批的情况下控制工作区或命令副作用；
- 系统 Git CLI 无法可靠保全 index、worktree 或特殊仓库状态；
- 工具契约演进必须破坏已冻结客户端协议且无法提供迁移 decoder；
- 新阶段范围过大，无法拆成独立可验证增量。

## 关联

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [Core 工具集与风险分级 Policy v2](../specs/2026-09-17-core-tooling-and-risk-tiered-policy.md)
- [Vera 原生 Git 能力](../specs/2026-09-17-native-git-capability.md)
- [ADR-0007：统一 PolicyEngine 与策略指纹](ADR-0007-unified-policy-engine.md)
- [ADR-0013：阶段八首个桌面底版采用 Electron](ADR-0013-electron-desktop-baseline.md)
- [ADR-0014：Core 客户端兼容契约](ADR-0014-core-client-compatibility-contract.md)
- [ADR-0017：插入 CLI 体验阶段并顺延桌面路线](ADR-0017-insert-cli-experience-stage.md)
- [ADR-0020：在桌面基线后规划 Core 原生 Skills 阶段](ADR-0020-stage-core-native-skills.md)
