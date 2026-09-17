# ADR-0018：验证产物必须在审批前规划并隔离

**状态：** Accepted
**日期：** 2026-09-14

## 背景

`VerificationRunner` 当前在用户 workspace 中以当前系统用户直接执行 `VerificationCommand`。即使命令不修改源码，Xcode、SwiftPM、pytest、Mypy 等工具也可能默认在 `cwd` 或工程根生成派生产物。真实走查已经证明，批准一个 `xcodebuild` 命令会在无 `.gitignore` 的工程内留下大量 `build/` 文件并进入 Git 暂存区。

Vera 的 Change Set、Checkpoint 和审批只覆盖显式源码变更。如果验证可以静默制造额外文件，用户看到的 Diff 与最终工作区就不再一致。

## 备选方案

### 方案 A：依赖 `.gitignore` 并在运行后删除常见目录

实现简单，但忽略文件仍然污染磁盘；目录名可能属于用户，运行后按名称删除存在误删风险。拒绝。

### 方案 B：所有验证都在完整 workspace 副本中运行

隔离最强，但复制大型工程成本高，会改变 Git、符号链接、绝对路径、Xcode Scheme 与依赖缓存行为，也引入新的镜像一致性问题。阶段六不采用，保留为未来 OS 沙箱或远程执行方向。

### 方案 C：命令 Profile 预规划外部产物路径，未知写入型命令失败关闭

对已知工具显式重写输出位置，对只读命令明确白名单；最终计划在哈希、策略和审批前形成。实现范围可控，审批事实与执行事实一致。采用。

## 决策

1. 新增 `VerificationArtifactPlanner`，在 `ChangeSetBuilder` 之前把模型提出的命令转换为带版本化 `artifact_plan` 的最终 `VerificationCommand`；Profile 与 root 唯一确定受控环境语义。
2. 最终 argv、cwd、Profile 和外部根纳入 Change Set hash、RecoverySnapshot、PolicyEngine 与审批事实。
3. `VerificationRunner` 只接受已规划命令；未知或可能写 workspace 且无隔离 Profile 的命令不执行。
4. 产物根使用 workspace 外 Vera 私有临时目录；运行结束只清理与本次计划精确绑定的根。
5. 运行后检测到意外 workspace 变化时失败关闭并保留证据，不自动删除、恢复、取消暂存或修改 `.gitignore`。
6. 首版 Profile 限于 Xcode、SwiftPM、pytest、Mypy、Ruff no-cache、Git optional-locks-disabled 和 TypeScript no-emit；新增生态必须另行评审。

## 后果

### 正面

- 验证不会再把常见构建和缓存产物留在用户工程。
- 用户批准的命令计划与实际执行语义一致。
- 清理目标由 Run 与 index 精确绑定，避免按通用目录名误删。
- TUI、Plain、JSON 和未来桌面客户端可以消费同一结构化隔离事实。

### 代价

- 某些依赖本地增量缓存的验证会变慢。
- 未支持的构建工具会先被拒绝，需要增加 Profile 后才能作为 Vera 验证运行。
- 旧 RecoverySnapshot 中没有 artifact plan，只能读取；恢复执行前需要重新规划和审批。

## 重新评审触发条件

- 外部产物 Profile 无法覆盖阶段五代表性工程的主要验证流程；
- 临时输出导致 Xcode/SwiftPM 等工具与正常工程行为出现不可接受差异；
- Vera 引入可验证的 OS 文件系统沙箱、临时 workspace 镜像或远程执行器；
- 真实 dogfood 发现合法验证频繁被错误拒绝。

## 关联

- [验证产物隔离与工作区无污染规格](../specs/2026-09-14-verification-artifact-isolation.md)
- [阶段六执行顺序](../tasks/phase-6-execution-order.md)
- [任务 0042](../tasks/0042-verification-artifact-isolation.md)
