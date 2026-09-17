# ADR-0020：在 CLI 封存后、桌面之前插入 Core-native Skills 阶段

**状态：** Accepted
**日期：** 2026-09-15
**接受：** 2026-09-17 用户确认阶段顺序与完整 Skills 设计

## 背景

Vera 当前没有 Skills 实现。本决策启动规划时，阶段七仍在收口 CLI 体验与个人 dogfood，原路线把阶段八定义为桌面集成，并把 Core-native Skills 暂列为桌面之后的候选能力；2026-09-17 阶段七随后按用户原文确认完成封存。

进一步设计确认了 Skills 不是桌面功能，也不是插件市场。发现、选择、冲突、信任、不可变 Snapshot、恢复、Context 装配和结构化事件都属于 UI 无关的 Core 控制面；CLI 可以独立完成完整验收，未来桌面只应消费同一契约。如果先实现桌面再增加 Skills，桌面会在 Core 契约再次扩展后返工，或者诱发 Renderer 临时复制发现与信任逻辑。

阶段七未封存前只能规划 Skills，不能实施。2026-09-17 的封存确认已满足该前置门禁，但不自动启动阶段八，也不替代后续实施授权。

## 候选方案

### A. CLI 封存后、桌面之前插入独立 Core Skills 阶段（采用）

阶段七完成后，以 CLI 作为首个完整客户端实现和验收 Core-native Skills；完成后再进入桌面集成。

优点是 Core 契约先稳定、CLI 可独立 dogfood，桌面无需承担第二套发现、选择或信任实现。代价是桌面与公开准备各顺延一个阶段编号。

### B. 桌面基础闭环后再增加 Skills

这是 ADR 最初 Proposed 版本的推荐方案。它能保持当时的阶段八桌面编号，但会让桌面先绑定一套不含 Skills 的 Core 表面，随后再补契约和展示，增加返工和旁路风险，因此不采用。

### C. 把 Skills 并入桌面阶段

阶段数量更少，但同时承担 Skill Core、CLI、桌面展示与安全验证，模糊 Core-first 边界，也无法证明 Skills 不依赖桌面，因此不采用。

## 决策

- 正式阶段顺序调整为：
  - 阶段七：CLI 体验收口与个人主力化；
  - 阶段八：Core-native Skills；
  - 阶段九：桌面集成；
  - 阶段十：私有预览与公开准备。
- 阶段八入口仍受阶段七封存门禁约束；封存前只允许架构与文档规划，不允许建立实施任务或修改产品代码。
- 阶段八只实现 UI 无关 Core 与 CLI 完整验收，不依赖 Electron、Tauri、Wails 或任何桌面代码。
- 阶段九桌面端只消费 `SkillSummary`、`SkillSelection`、`SkillSnapshot`、稳定错误和结构化 Event，不扫描目录、不解析 Skill 包、不判断信任。
- 采用“Core 控制面 + 外部 Skill 包”；Skill 包可外插分发，但不能扩大 Vera 权限。
- v1 只支持内置、用户本地和 workspace 本地来源、显式单 Skill、只读文本资源和不可变 Snapshot。
- workspace Skill 始终是不可信工程内容，只能显式选择。
- Skill 不能注册 Tool、扩大 Workspace、修改 Policy/Approval、读取 Provider Key、声明网络权限、绕过 Change Set 或执行包内脚本。
- 远程安装、市场、评分、支付、自动更新、多 Skill、Multi-Agent、Plugin、Hook 和可执行能力不随本决策进入 v1。

## 阶段边界

| 阶段 | 主要问题 | 退出证据 |
| --- | --- | --- |
| 阶段七 | CLI 是否达到个人主力标准 | 真实 Terminal.app 与持续 dogfood 通过，用户给出精确封存原文 |
| 阶段八 | 本地单 Skill 是否能由 Core 安全、确定、可恢复地控制 | CLI、离线安全矩阵、两个真实工程 dogfood 通过，无 Critical/High |
| 阶段九 | 桌面是否能复用 Core 完成工作台闭环 | Electron 客户端通过结构化契约完成桌面安全、性能和打包门禁 |
| 阶段十 | 产品是否适合可信用户预览与公开准备 | 发布、安全、内容政策与供应链检查清单完成 |

## 后果

- `ROADMAP.md`、`PRODUCT.md`、`STATUS.md`、`AGENTS.md`、现行规格、活动任务入口和索引需要同步新阶段顺序。
- ADR-0017 和 ADR-0013 接受时的“阶段八桌面、阶段九公开准备”保留为历史事实；本 ADR 作为后续决策调整当前编号，不重写其原始理由。
- 桌面规格当前仍是 Draft，只把所属阶段从八迁移为九；本决策不接受其工作台布局、前端框架或打包细节。
- Skills 规格转为 Accepted 只表示设计已接受，阶段八仍为 `Not started`。
- 阶段八完成前不得开始阶段九桌面实施；阶段七封存前不得实施阶段八。

## 验证与重审触发器

- `NoSkill` 回归证明未启用 Skills 时现有 Runtime、CLI、Plain、JSON、Event 与 Journal 行为保持兼容；
- Snapshot 恢复、来源信任、路径逃逸、并发修改和安全清理矩阵通过；
- 真实 Terminal.app 与至少两个真实工程副本完成单 Skill dogfood；
- 任一方案要求 Skill 执行脚本、注册权限、自动选择 workspace 内容、远程安装或在桌面 Renderer 实现控制面时，必须建立独立规格与 ADR 重新评审；
- 若未来阶段编号再次调整，继续通过新 ADR 记录，不回写本决策接受时的历史理由。

## 与现有决策的关系

- 后续调整 [ADR-0017](ADR-0017-insert-cli-experience-stage.md) 的当前阶段编号：其 CLI 体验阶段和封存门禁继续有效，桌面由阶段八顺延为阶段九，公开准备由阶段九顺延为阶段十。
- 后续调整 [ADR-0013](ADR-0013-electron-desktop-baseline.md) 的实施阶段编号：Electron 选择与 Python Core/结构化 Command/Event 边界不变，当前实施阶段为阶段九。
- 补充 [ADR-0015](ADR-0015-untrusted-content-trust-boundary.md)：workspace Skill 使用 `untrusted`，其他 Skill 也不具有安全策略权限。

## 关联

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [Core 原生 Skills 系统](../specs/2026-09-15-core-native-skills-system.md)
- [阶段九：桌面 Agent 工作台与 UI](../specs/2026-09-12-desktop-agent-workbench-ui.md)
