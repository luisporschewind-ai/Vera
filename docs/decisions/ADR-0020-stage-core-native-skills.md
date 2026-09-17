# ADR-0020：在桌面基线后规划 Core 原生 Skills 阶段

**状态：** Proposed
**日期：** 2026-09-15

## 背景

Vera 当前没有 Skills 模块实现，现行阶段七与阶段八规格还明确排除了插件市场。用户希望确认 Skills 是否已有规划；若没有，需要纳入路线。Skills 与插件市场不是同一能力：前者让 Agent 复用可审阅的工作方法和资源，后者还涉及远程分发、安装、更新、第三方信任与商业生态。

把 Skills 直接塞进正在收口的阶段六或阶段七会扩大当前 CLI 门禁；放进阶段八又会让首个桌面闭环依赖一个尚未验证的新 Core 子系统。当前路线中的阶段九用于私有预览与公开准备，因此是否在阶段八后插入独立 Skills 阶段会改变后续编号，需要单独决策。

## 候选方案

### A. 阶段八后插入独立 Core Skills 阶段（推荐）

先完成阶段七 CLI 体验和阶段八桌面基础闭环，再以独立阶段实现本地 Core-native Skills；原“私有预览与公开准备”顺延一位。

优点是边界清楚，CLI 与桌面都能消费稳定的 Core 契约，Skills 的来源、快照、上下文与安全矩阵有独立退出条件。代价是后续阶段编号再次调整。

### B. 把 Skills 纳入阶段八桌面集成

编号不变，但桌面基础闭环会同时承担 Skill Core、CLI、桌面展示和安全验证，增加阶段八范围与失败面，不推荐。

### C. 保持阶段九公开准备，Skills 延后到公开发布后

现有路线改动最小，但 Vera 会在私有预览前缺少可复用工作方法模块，也推迟了用户要求的 Coding Agent 丰满化能力。

## 建议决策

接受方案 A，但只在 [Core 原生 Skills 系统](../specs/2026-09-15-core-native-skills-system.md)经过用户审阅并转为 Accepted 后生效：

- 阶段七与阶段八的边界、顺序和门禁不变；
- 阶段八后新增独立 Core 原生 Skills 阶段；
- 原“私有预览与公开准备”顺延一位；
- 首个 Skills 阶段只覆盖内置/本地发现、单 Skill 选择、不可变 Snapshot、Context 装配、CLI/桌面共同契约和安全 dogfood；
- 插件市场、远程安装、支付、评分、自动更新与可执行第三方代码不随本决策进入范围。

## 后果

- 在本 ADR 仍为 Proposed 时，路线图只把 Skills 标为“阶段八后候选”，现行阶段九公开准备编号保持不变。
- 接受后需要同步更新 `ROADMAP.md`、`PRODUCT.md`、`STATUS.md`、ADR-0017 中仍生效的阶段表，以及内容安全规格对公开准备阶段的引用。
- Skills 将遵循 Core-first：客户端只消费结构化事实，不能自行发现文件、判断信任或授予权限。
- 第一版不允许 Skill 直接执行包内脚本，避免在能力尚未成熟时引入新的代码执行供应链。

## 接受或重新评审条件

接受前必须确认：

1. Skills 规格中的来源目录、Manifest 形式、workspace 自动候选策略和远程安装边界；
2. 阶段八基础闭环不依赖 Skills；
3. 用户接受在桌面之后、公开准备之前插入独立阶段及相应编号顺延。

若阶段八 dogfood 证明 Skills 是桌面主流程的必要前置能力，重新评审阶段位置，但不能因此绕过阶段七封存门禁或在 Renderer 中临时实现 Skills。

## 关联

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [Core 原生 Skills 系统](../specs/2026-09-15-core-native-skills-system.md)
- [ADR-0017：插入 CLI 体验阶段并顺延桌面路线](ADR-0017-insert-cli-experience-stage.md)
- [ADR-0015：不可信内容信任边界](ADR-0015-untrusted-content-trust-boundary.md)
