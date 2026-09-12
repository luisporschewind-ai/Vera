# 任务 0032：桌面壳基础、生命周期与 Workspace

> 供 Cursor 执行：只使用任务 0031 已接受的桌面壳与 UI 框架；本任务不实现完整 Agent 工作流。

**状态：** Planned
**执行就绪：** 否；任务 0031 的 Wails 验证结果经用户批准后
**分支：** `phase-7/0032-shell-lifecycle-workspace`
**依赖：** 任务 0030、0031 已合并
**规格：** [阶段七桌面集成](../specs/2026-09-12-desktop-integration.md)

## 目标与边界

建立选定桌面壳的最小产品骨架、窄化 Renderer bridge、`CoreSupervisor`、原生 Workspace picker、握手/状态页、Renderer attach 和安全退出。所有 Core 业务继续通过任务 0030 协议。

任务 0031 必须在允许本任务执行前，把下列逻辑路径映射为所选框架的精确原生文件和命令；未映射时本任务保持不可执行：

- `desktop/app/native/core_supervisor.*`
- `desktop/app/native/bridge.*`
- `desktop/app/native/workspace_picker.*`
- `desktop/app/frontend/src/core/client.ts`
- `desktop/app/frontend/src/state/lifecycle.ts`
- `desktop/app/frontend/src/views/StartupView.*`
- `desktop/app/frontend/src/views/WorkspaceView.*`

统一前端路径固定为 `desktop/app/frontend`；可信原生后端使用 Go/Wails。精确目录、生成文件边界和命令由任务 0031 按执行日 stable major 写回。

## 接口

### 原生后端只暴露

- `get_app_bootstrap()`：App/version/platform/arch，不含环境和 secret。
- `choose_workspace()`：调用原生目录 picker，返回用户选择 token，不声称授权。
- `open_workspace(selection)`：转给 Core `session.open`，返回 Core 快照。
- `attach_ui(last_transport_sequence)`：重放有界缓存或要求 snapshot/page。
- `send_session_action(envelope)`：校验来源、大小、状态后转发。
- `request_shutdown(mode)`：`stay_open | cancel_and_quit`。
- `export_diagnostics(destination)`：只导出用户已预览的脱敏包。

禁止任何通用 `spawn/readFile/writeFile/openExternal` bridge。

### CoreSupervisor

- `start()`：固定 app bundle 内 sidecar 路径、固定 argv、最小环境。
- `state()`：`stopped/starting/handshaking/ready/session_open/draining/crashed/blocked`。
- `send(frame)`、`subscribe(output)`、`shutdown()`、`terminate_after_timeout()`。
- `attach(last_sequence)`：有界重放，不生成业务事实。

## 测试先行步骤

### 1. 安全 Renderer 基线

写 API surface snapshot 和负例：

- 只加载本地打包资源，CSP 拒绝 inline/eval/远程脚本；
- 禁止任意导航、新窗口和未校验外部 URL；
- Renderer 无 Node/Go/Rust 全局能力；
- bridge sender/window/origin 不匹配时拒绝；
- payload > 8 MiB、未知 method、额外字段拒绝。

### 2. CoreSupervisor

用任务 0030 Fake Core 覆盖：

- fixed absolute path，不查 `PATH`；
- hello success/mismatch/timeout；
- stderr flood、stdout corruption、EOF、crash；
- idle shutdown 10 秒、TERM 3 秒、KILL；
- 父进程退出无孤儿；
- 5 分钟 3 次 crash 后 blocked。

### 3. Workspace 选择

临时目录覆盖：

- picker cancel 零副作用；
- 用户选择值与 Core 规范化值同时可核对；
- Home/root/symlink/只读/无 Git/权限错误局部展示；
- workspace identity/Policy snapshot 来自 Core；
- 切换前存在 active run 或 approval 时拒绝；
- 不自动打开上次 Workspace、不自动恢复任务。

### 4. Renderer attach

- reload 后使用 `last_transport_sequence` attach；
- 缓冲完整时准确重放；
- 缓冲缺口时 snapshot + run event page；
- 永不重发 prompt/approval；
- StreamFrame 缺口显示“未完成流”，最终 Event 决定状态。

### 5. 安全退出

- active/pending 时默认 `stay_open`；
- `cancel_and_quit` 只发送一次 cancel，等待持久终态；
- window crash 与正常 quit 分类不同；
- 首版无后台 Core。

## 自动验证

- 所选框架的 native unit/integration tests。
- 前端 lint、typecheck、unit、component tests。
- Fake Core lifecycle/conformance。
- API surface/CSP/navigation snapshot。
- `git diff --check` 与阶段七共同门禁。

精确命令由任务 0031 根据 ADR-0015 写回本任务后执行。

## 人工验证

- Finder 启动、不依赖 shell PATH；
- 原生目录 picker、TCC、取消与只读路径；
- 窗口 reload/close/force quit、休眠唤醒；
- Intel macOS 上无孤儿 Core；
- 小窗口、键盘和 CJK 启动页。

## 验收标准

- Renderer 只有窄化 bridge，无法绕过 Core。
- Core 生命周期和 Workspace 事实可见、可诊断。
- attach 不重发动作，quit 不遗留后台 Agent。
- 尚未实现的工作流入口明确禁用，不用 mock 文本伪装成功。

## 提交

```bash
git diff --check
git commit -m "feat: add desktop shell lifecycle and workspace"
```
