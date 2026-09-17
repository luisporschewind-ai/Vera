# ADR-0019：以 `VERA.md` 作为原生项目指令并兼容 `AGENTS.md`

**状态：** Accepted
**日期：** 2026-09-14

## 背景

成熟 Coding Agent 通常允许工程保存版本化项目说明，减少每次会话重复解释结构、命令和规范。Vera 当前能够按需读取 `AGENTS.md` 等工程说明并将其标为 advisory，但没有稳定的自动发现、可见状态或原生初始化入口。

Vera 仓库自身已经使用共享 `AGENTS.md`，因此若 Vera 默认生成或覆盖同名文件，会与 Cursor、Codex、Claude Code 等其他 Agent 的共享约定产生所有权冲突。另一方面，只兼容通用文件会削弱 Vera 自己的产品身份，也无法表达 Vera 专属行为。

## 决策

- Vera 原生项目指令文件固定为 workspace 根目录的 `VERA.md`；首版同时只读兼容根目录 `AGENTS.md`。
- 加载顺序固定为 `AGENTS.md` 后 `VERA.md`。在 advisory 工程建议层内部，`VERA.md` 对非安全冲突具有更高优先级。
- 两种来源都使用 `project_guidance/advisory`，不能授权工具、命令、网络、秘密、workspace 扩张、持久化或绕过审批。
- 文件发现和注入由 UI 无关 Core 完成；CLI 与未来桌面端只消费结构化状态，不各自扫描 Markdown。
- 首版只查 workspace 根，不支持父目录、子目录、include、远程来源或第三方专属规则文件。
- `/init` 和 `vera init` 通过受限 `project_init` Run 分析工程，只能提出 `VERA.md` Change Set，并复用既有 PolicyEngine、ApprovalGate 和写入链。
- Vera 不在普通启动、安装、恢复或发现共享规则时静默创建文件，也不自动生成、覆盖或迁移 `AGENTS.md`。
- 项目指令按 Run 快照；每个新 Run 重新读取，会话 Journal 只保留来源与 hash 事实，不复制正文。

## 备选方案

### 只使用 `AGENTS.md`

跨工具兼容最好，但 Vera 会与其他 Agent 共同拥有同一文件，自动初始化和 Vera 专属约定容易覆盖用户现有协作规则，因此不采用为原生方案。

### 只使用 `VERA.md`

品牌和所有权清楚，但忽略大量已有工程的共享规则，用户需要复制维护两份说明，因此不采用。

### 自动读取所有已知产品文件

兼容面看似更大，但不同产品的语义、优先级和 include 规则并不一致，会造成不可预测冲突，也可能把第三方专属指令错误提升，因此首版不采用。

### 首次运行直接生成文件

操作最少，但会污染用户工程并制造未经批准的 Git 变化，违反 Vera 的 Change Set 与审批边界，因此不采用。

## 后果

- Vera 拥有清晰、可识别的原生项目入口，同时能直接利用现有 `AGENTS.md` 基线。
- 用户需要理解 `VERA.md` 是项目指导而非权限配置；CLI 必须提供 `/instructions` 解释实际来源和生效 hash。
- 自动加载 advisory 内容增加上下文占用和投毒输入面，因此必须有严格大小、文件类型、来源标记、检测与公开 Event 限制。
- `StartRun`、Runtime 上下文种子、命令目录、Presenter、CLI 入口和安装 smoke 都需要新增兼容行为。
- 若未来需要 monorepo 分层、父目录继承、include、第三方文件迁移或跨项目个人偏好，必须建立新规格并重新审查优先级与安全边界。

## 验证与重审触发器

- 用冻结矩阵验证缺失、双文件、超限、非 UTF-8、符号链接、读取竞态与 Run 快照行为。
- 用对抗夹具证明项目说明不能扩大权限、跳过审批或自动执行命令。
- 用 `/init` 范围负例证明任何非 `VERA.md` 修改与附带验证命令都被拒绝。
- 在真实 Terminal.app 和至少三个真实工程中确认普通启动不产生工作区写入。
- 当 `AGENTS.md` 生态标准、Provider 消息角色或 Vera 的项目/个人记忆模型变化时重审。

## 关联

- [项目指令发现与 `VERA.md` 初始化](../specs/2026-09-14-project-instructions-and-vera-init.md)
- [ADR-0007：统一 PolicyEngine 与策略指纹](ADR-0007-unified-policy-engine.md)
- [ADR-0015：不可信内容信任边界与提示词投毒分层防御](ADR-0015-untrusted-content-trust-boundary.md)
- [任务 0043：项目指令发现与初始化](../tasks/0043-project-instructions-and-init.md)
