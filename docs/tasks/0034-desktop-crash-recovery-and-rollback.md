# 任务 0034：桌面崩溃、恢复与回滚

> 供 Cursor 执行：恢复界面只展示并发送 Core 结构化决策，不从 UI 缓存推断文件状态。

**状态：** Planned
**执行就绪：** 否；任务 0033 合并后
**分支：** `phase-7/0034-desktop-recovery-rollback`
**依赖：** 任务 0033 已合并
**规格：** [阶段七桌面集成](../specs/2026-09-12-desktop-integration.md)

## 目标与边界

把 Renderer attach、Core crash/假死、新 Core 只读扫描、六类恢复、恢复审批、回滚和人工处理做成诚实的桌面流程。任何不确定 action 都不自动重发。

## 逻辑文件

- `desktop/app/frontend/src/state/recovery.ts`。
- `desktop/app/frontend/src/views/RecoveryCenterView.*`。
- `desktop/app/frontend/src/components/CoreCrashBanner.*`。
- `desktop/app/frontend/src/components/RecoveryCard.*`。
- `desktop/app/frontend/src/components/RollbackCard.*`。
- `desktop/app/native/core_supervisor.*`：补充 crash/unresponsive/restart policy。
- `tests/desktop/e2e/test_crash_recovery.*` 与前端 component tests。

具体扩展名由任务 0031 写回。

## 测试先行步骤

### 1. Renderer attach 与 gap

- 完整 bounded buffer 重放；
- buffer gap 触发 snapshot/event page；
- StreamFrame 丢失只标记 incomplete；
- Event sequence 冲突进入 error，不合并猜测；
- attach 不生成新 operation id。

### 2. Core crash

对 prompt、pending approval、部分应用、验证、回滚边界注入 crash：

- UI 立即撤销“正在安全完成”的假象；
- 显示 process instance、退出分类和“副作用待核对”；
- 新 Core 只执行 handshake + InspectRecovery；
- prompt/approval/write/verification/rollback 计数不增加；
- 5 分钟 3 次 crash 进入 blocked。

### 3. 假死与用户控制

- 15 秒 health 无响应标记 unresponsive，但不自动 kill；
- “等待”“请求取消”“强制重启”三项含真实后果；
- 强制重启需要二次明确确认，记录 operation；
- 进程可能恢复时重复点击不产生并发 Core。

### 4. 六类恢复

逐一覆盖：

- `resumable_approval`
- `resumable_verification`
- `safe_to_abandon`
- `recoverable_partial_apply`
- `manual_required`
- `legacy_not_resumable`

按钮可用性与 Core classification 完全一致；`manual_required` 不显示一键修复。

### 5. 恢复审批与回滚

- 恢复计划展示 path/action/hash/Workspace/policy；
- 默认 reject/cancel；
- 事实变化使旧计划 expired；
- Rollback 冲突保护用户后续修改；
- operation 重放返回已有回执；
- 完成/冲突/人工处理是不同终态。

## 自动验证

- 任务 0030 crash conformance + 任务 0022 recovery/idempotency suite。
- 桌面 E2E 对每个 failpoint 断言 Workspace hash/Event/operation 次数。
- CoreSupervisor orphan/crash-loop tests。
- 前端恢复 reducer/component accessibility。
- 阶段七共同门禁。

## 人工验证

- Activity Monitor/`ps` 核对 Core PID 与无孤儿；
- 强制结束 Renderer/Core/App 后重启；
- 实际恢复中心、部分写入审批、回滚冲突；
- 休眠唤醒、窗口 reload 和重复点击。

## 验收标准

- UI 重连与 Core 崩溃语义分开。
- 任何未知结果不自动重放。
- 六类恢复和回滚完全由 Core 事实驱动。
- crash loop、假死和人工处理都有安全停止点。

## 提交

```bash
git diff --check
git commit -m "feat: add desktop crash recovery and rollback"
```
