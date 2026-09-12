# 任务 0037：阶段七桌面集成验收

> 供 Cursor 执行：自动证据完成后停在 `Ready for manual acceptance`；真实桌面走查和平台支持不能由 Agent 代签。

**状态：** Planned
**执行就绪：** 否；任务 0030–0036 全部合并后
**分支：** `phase-7/0037-desktop-acceptance`
**依赖：** 任务 0030–0036 已合并
**规格：** [阶段七桌面集成](../specs/2026-09-12-desktop-integration.md)

## 目标

逐项映射阶段七 15 条退出条件，运行完整自动门禁，完成 Intel macOS 人工桌面走查，形成不夸大签名、OS sandbox 或跨平台支持的验收报告。

## 文件

- 新增 `docs/evals/phase-7-desktop-acceptance.md`。
- 新增 `docs/evals/phase-7-desktop-manual-walkthrough.md`。
- 新增 `tests/e2e/test_phase_7_desktop_matrix.py`。
- 修改 `docs/STATUS.md`、`docs/ROADMAP.md`、本任务文件；只在实际证据达到状态时更新。
- 校准 `docs/specs/README.md`、`docs/decisions/README.md`、`docs/tasks/README.md`。

## 自动验收矩阵

### 协议与生命周期

- framing/handshake/version/capability/manifest；
- operation idempotency、Event/Stream ordering、backpressure；
- Core start/stop/EOF/TERM/KILL/crash/unresponsive/crash loop；
- Renderer attach 和 event gap。

### 产品工作流

- Workspace、权限、prompt、stream、tools；
- Change Set、Diff、审批/过期/拒绝；
- verification success/failure/cancel；
- 六类 recovery、部分恢复、rollback conflict；
- 同场景 CLI/Desktop Core 事实 parity。

### 安全与秘密

- Renderer API/CSP/navigation/sender allowlist；
- 无通用 file/shell/process/sidecar capability；
- child env allowlist 与 no OS sandbox 文案；
- canary 覆盖 Key、argv、Envelope、Event、Stream、State、日志、Crash、WebView storage、App。

### 打包与数据完整性

- Finder 环境 Core ready；
- artifact manifest、arch、license、nested signing/entitlements；
- offline update/current/future/corrupt/migration crash；
- uninstall/reset scope；
- 所有场景 Workspace hash 不变或只发生被明确批准的测试修改。

## 人工走查

在用户明确选择的临时/备份工程上：

1. Finder 首启、Core handshake、版本和“当前用户权限/无已验证 OS 沙箱”。
2. 原生 Workspace picker、Git/权限/identity、危险根目录提示。
3. 普通对话、单/多文件修改、时间线和大 Diff。
4. approve/reject/cancel/expired 与验证 success/failure。
5. Renderer reload、Core force quit、App force quit、只读恢复和回滚冲突。
6. Provider 设置、Keychain 授权/拒绝、配置错误和诊断预览。
7. CJK、键盘-only、缩放、高对比、VoiceOver 基础、休眠唤醒。
8. Finder 安装/升级/迁移失败/卸载与本地数据保留。
9. 有用户授权时验证 Developer ID/notarization；没有时保持 `Blocked`。

每项记录环境、步骤、预期、实际、严重度和脱敏证据。初始全部 `Not run`。

## 平台矩阵

报告每个平台/架构分别列：

- build；
- native run；
- WebView；
- Core packaging；
- process cleanup；
- SecretStore；
- signing/update；
- manual workflow。

只有所有必要列有当前原生证据时才标 `Supported`。本阶段预期最多能把 `macOS Intel` 标为已测候选；Apple Silicon、Windows、Linux 默认 `Not tested`，不能由框架宣传或 cross-build 改写。

## 分级与状态

- Critical：Renderer 可直接执行/写入、未批准副作用、Workspace 逃逸、Key 泄漏、大范围不可恢复破坏。
- High：审批绕过、错误恢复/更新导致不一致、孤儿进程继续执行、签名/manifest 绕过、虚假成功。
- Medium：有明确恢复路径但主要流程高频失败或安全表达降级。
- Low：不影响边界和数据完整性的视觉/诊断问题。

任何 Critical/High 未关闭时阶段七不能完成。Medium 必须修复或由用户明确接受。

## 验证命令

运行：

1. 阶段七执行顺序中的 Python 共同门禁；
2. 任务 0031 写入的所选桌面壳/前端全部门禁；
3. `tests/desktop`、`tests/e2e/test_phase_7_desktop_matrix.py`；
4. Core/app build、artifact verification、offline update smoke；
5. `git diff --check`、最终 diff 和 secret/path 扫描。

报告必须保存精确命令、exit code、case 数、artifact hash、机器环境和未运行项，不能只写“全部通过”。

## 完成条件

只有以下全部成立才可把任务标 `Done`、路线图阶段七标 `Complete`：

- 规格 15 条退出条件逐项有证据；
- 自动门禁全部通过；
- 用户完成 Intel macOS 人工走查并书面确认桌面版本达到本阶段预期；
- 无 Critical/High，Medium 已处置；
- `ADR-0014`、`ADR-0015` 和实际 UI 技术决策均 Accepted；
- 打包/签名/升级/迁移/卸载状态没有夸大；
- 文档与当前 app/Core/protocol/state manifest 一致。

缺少用户人工确认或签名环境时只能写 `Ready for manual acceptance` 或 `Blocked`；不能提前进入阶段八。

## 提交

用户确认前只可提交真实自动证据和 `Ready for manual acceptance` 状态。最终状态提交需用户明确授权：

```bash
git diff --check
git commit -m "docs: record Vera phase seven desktop readiness"
```
