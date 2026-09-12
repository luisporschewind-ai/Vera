# 任务 0031：Wails 桌面壳验证与限时 Spike

**状态：** Planned
**执行就绪：** 否；阶段七入口门禁与任务 0030 完成后
**分支：** `phase-7/0031-wails-validation-spike`
**依赖：** 任务 0030 已合并，桌面协议 conformance harness 已冻结
**规格：** [阶段七桌面集成](../specs/2026-09-12-desktop-integration.md)
**架构：** [ADR-0014：桌面与 Core 进程边界](../decisions/ADR-0014-desktop-core-process-boundary.md)、[ADR-0015：选择 Wails 桌面壳](../decisions/ADR-0015-select-wails-desktop-shell.md)

## 目标

Wails 已由用户明确选定为 Vera 阶段七桌面壳。本任务不再通过 Wails、Tauri、Electron 横向排名决定框架，而是在 Intel macOS 上用真实 release artifact 验证 Wails 是否满足 Vera 的进程、安全、打包和维护门禁。

选择不等于免验证。任一硬门禁失败时，任务必须停止并请求用户决定是调整 Wails 集成、缩小范围，还是重新开启其他框架评估；不得暗中切换 Tauri/Electron，也不得用脆弱 workaround 把失败标成通过。

Vue 3 与 React 仍在浏览器夹具中独立测量，不由 Wails 模板默认值决定。

## 执行前版本规则

1. Spike 当天重新检查 Wails 官方稳定通道、支持策略和许可证。
2. 只使用当天最新受支持的 stable patch，禁止 alpha、beta、nightly、RC 和已 EOL major。
3. 若 Wails v3 到执行日仍未 GA，使用 Wails v2 stable；可记录 v3 观察，不把 pre-GA 版本作为产品基线。
4. 把精确版本、下载来源、lockfile、Go module 和 artifact hash 写入证据。
5. 不把规划日的版本判断复制为执行日事实。

规划日只确认当前官方资料仍把 Wails v2 作为稳定通道、Wails v3 处于 pre-GA；该事实必须在 Spike 当天重新核对。

## 硬门禁

任一项失败即标记 `Blocked`，不能靠加权分补偿：

1. Go 可信后端能从签名应用包内的固定绝对路径启动同一个 Python Core onedir sidecar。
2. 能可靠双向读写 framed stdio，不按文本行破坏帧，也不把 Go/Wails 日志混入协议 stdout。
3. Renderer 无任意文件、进程、Shell、Key store 或通用 sidecar 权限。
4. Wails binding、本地资源、CSP、导航和来源检查可收窄；远程内容不能获得本地能力。
5. Core 正常退出、崩溃、父进程退出、TERM/KILL 和 crash loop 不留下孤儿。
6. release `.app` 能包含 Core/Python 依赖并生成可核对 manifest；Finder 启动不依赖 Terminal `PATH`。
7. macOS app 与嵌套 sidecar 可做 ad-hoc/Developer ID 结构签名验证，且不关闭关键签名保护。
8. 完整应用更新可把 Wails 壳、Core、资源和兼容清单作为一个签名原子版本处理。
9. 使用受支持稳定版本，许可证与 Vera 未来分发边界兼容。
10. 同一 Fake Model 工作流可完成 Workspace、prompt、stream、审批、Diff、验证、取消、崩溃恢复和回滚。

## 共同 Spike 夹具

任务 0030 产出并冻结：

- `tests/desktop/fixtures/fake_core.py`：可脚本化握手、Event、StreamFrame、半帧、超限、卡死、崩溃和 EOF。
- `tests/desktop/conformance_cases.json`：不含真实 Provider 或用户文件的固定场景。
- `scripts/build_desktop_core.py`：生成当前平台/架构的 PyInstaller onedir baseline。
- `scripts/measure_desktop_candidate.py`：统一启动、采样、崩溃注入和 JSON 报告。

Wails 适配层只能实现：

- `start_core`
- `send_frame`
- `receive_frame`
- `attach_renderer`
- `request_shutdown`
- `force_terminate`

适配层不得复制 Core 的 Policy、审批、Workspace、恢复或回滚语义。

桌面壳验证使用无框架 HTML/CSS/TypeScript 页面，只包含 Core 状态、临时 Workspace、prompt、500 个 timeline item、10,000 行 Diff、approve/reject/cancel 和 Renderer reload。不得在此环节引入 Vue/React，以免把 UI 技术差异算入 Wails 壳验证。

所有场景使用 Fake Model、临时 Workspace 和临时 `VERA_STATE_DIR`；移除 Provider Key、Token、签名凭据和 CI secret，不联网调用 Provider，也不读取用户工程。

## Wails 适配约束

- Go 后端使用 `exec.Cmd` 或等价原生 API 拥有 Core；不得把任意命令或通用进程 API 暴露给 JavaScript。
- 只导出窄化、类型化的 Go binding，并对公开方法生成 API surface snapshot。
- `CoreSupervisor` 独立于 Wails window/view 生命周期；Renderer reload 不杀死仍健康的 Core。
- 核实 stdin/stdout 的二进制 chunk 行为、背压、stderr 排空、半帧和超限帧处理。
- 测量 Core 如何进入 `.app`、嵌套签名顺序、退出清理、更新能力和已知缺口。
- 核对 macOS system WebView、Intel build 和 universal build 产物；universal 只记录构建，不声称 arm64 已运行。
- Wails 生成代码不得成为 Renderer 绕过窄桥接层的第二套能力入口。

## 统一场景

1. Finder 启动，10 秒内完成 Core handshake。
2. 用原生 picker 选择临时 Workspace，显示 Core 规范化事实。
3. 发送 prompt，接收 100 个 StreamFrame 和最终 Event；流式帧可合并，最终 Event 不丢。
4. 展示 500 item timeline 与 10,000 行 Diff，UI 保持响应。
5. 处理 Change Set 与命令审批；Renderer 不能绕过 Core。
6. cancel active run，确认一次副作用和进程组清理。
7. Renderer reload 后 attach，不重发 prompt/approval。
8. 在 prompt、等待审批、模拟写入后、验证中四个位置使 Core 崩溃；新 Core 只读恢复。
9. 注入半帧、8 MiB 边界、超限帧、stdout 垃圾、stderr flood 和 15 秒无响应。
10. 正常 quit、父进程 kill、Core 忽略 TERM；确认无孤儿。
11. 构建 release app，扫描 secret、动态库、架构、manifest、权限和签名结构。
12. 从本地旧版本 fixture 做完整应用升级和失败回滚；Workspace hash 不变。

## 测量方法

报告必须记录 Mac/Intel CPU/RAM、macOS、显示缩放、Xcode/Command Line Tools、Python、Go、Node、WebView、Wails、bundler、updater 和 Python freezer 精确版本，以及 app/Core commit、lockfile hash、机器电源和温度异常。

对 release artifact 执行：

- 冷启动到窗口可见、Core ready、首个可交互帧：10 次，报告 median/p95/max。
- idle 60 秒后的进程数、总 RSS 和 Core RSS：5 次。
- 1000 个 Event + 5000 个 StreamFrame 的吞吐、p95 端到端延迟和丢帧分类：5 次。
- 500 timeline、10,000 行 Diff 下输入 p95、滚动 p95、峰值 RSS：5 次。
- clean build、warm build、增量前端 build：各 3 次。
- `.app`、压缩分发包、Core sidecar、前端资源和依赖总大小。
- Core crash 检测、重启到恢复报告、正常退出与强杀清理时长：各 5 次。

数据保留原始 JSON 和汇总，不只保留截图或主观结论。

## 就绪评分

硬门禁通过后，每项按 0–5 分评分，再乘权重；评分用于暴露剩余风险，不再用于选择其他桌面壳：

| 维度 | 权重 |
|---|---:|
| Renderer/Go Backend 权限收窄与攻击面 | 25 |
| Core sidecar 生命周期与协议可靠性 | 20 |
| 打包、嵌套签名、更新与迁移 | 20 |
| 启动、内存、体积与长列表性能 | 15 |
| 稳定版本、维护成本、文档与升级节奏 | 10 |
| 平台/WebView 可预测性 | 10 |
| **合计** | **100** |

评分解释：5 表示官方路径清晰且适配薄；4 表示有低成本、受测适配；3 表示维护或平台差异明显；2 以下表示依赖脆弱 workaround。全部硬门禁通过且总分不低于 80 才可进入任务 0032；低于 80 或存在 Critical/High 风险时停止并交用户复核。

## UI 技术独立测量

Vue 3 与 React 使用同一 Vite 浏览器夹具、TypeScript model、test IDs、数据和 Playwright/Vitest 场景，比较：

- 500 timeline item、10,000 行 Diff 和 stream 合并；
- 审批默认焦点、键盘-only、CJK、缩放与基础无障碍；
- 类型错误、未知 Event fallback、断线/attach；
- production bundle、首帧、输入 p95 和峰值内存；
- 单元/组件测试、虚拟列表依赖和完成同一小变更的成本。

权重为：团队熟悉度与可维护性 30、大时间线/Diff 性能 25、TypeScript 与测试 20、无障碍 15、依赖与 bundle 10。两个候选都通过且差距不超过 5/100 时优先 Vue；否则按证据或继续讨论。UI 决策另写 `ADR-0016`，不修改 Wails 选择。

## 时间盒

总上限 3 个工程日：

| 工作 | 上限 |
|---|---:|
| 版本复核、共同 fixture、Core onedir | 0.5 天 |
| Wails release Spike 与窄 binding | 1 天 |
| 生命周期、权限、打包、签名结构和更新测量 | 0.75 天 |
| Vue/React 浏览器 Spike | 0.5 天 |
| 报告、风险复核和后续任务回写 | 0.25 天 |

达到时间盒仍未通过的项标记 `Blocked` 并记录最后证据。不得私自延长、降低门禁或切换框架。

## 产物

- `docs/evals/phase-7-wails-validation.md`：环境、raw report、硬门禁、评分和限制。
- [ADR-0015](../decisions/ADR-0015-select-wails-desktop-shell.md)：追加验证证据；若证据反驳决策则进入 `Reconsidering`，不得自行替换。
- 必要时 `docs/decisions/ADR-0016-desktop-ui-framework.md`：Vue/React 决策。
- `docs/evals/artifacts/phase-7-wails/*.json`：无秘密的原始测量。
- 更新任务 0032–0037 的 Wails 精确文件路径和验证命令。

Spike 壳代码不直接作为产品实现合并；任务 0032 按验证后的最小结构重新建立可维护基线。

## 自动验证

- Wails adapter 运行任务 0030 的完整 conformance suite。
- 测量 JSON schema、次数、单位、缺失值和机器信息完整。
- Renderer API surface snapshot 不含通用文件、Shell、进程或 Key store 能力。
- canary secret 扫描 release app、stdout/stderr、日志和 raw report。
- app/Core/Workspace hash、孤儿 PID 和 update fixture 结果可机器检查。
- Vue/React 使用相同 UI test IDs、数据和浏览器版本。

## 人工验证

- Finder 启动、原生 picker、窗口关闭/重载、休眠唤醒与 TCC。
- 视觉、键盘、CJK、缩放、VoiceOver 基础和大 Diff。
- Developer ID/notarization 需要用户证书和网络；缺失时记录 `Blocked`，不能用 ad-hoc 签名代替结论。
- 用户审阅 Wails 硬门禁、原始数值、评分和剩余风险后，批准进入任务 0032。

## 提交边界

只提交测量工具、脱敏证据、ADR 证据补充和更新后的后续计划，不提交 Spike 产品壳：

```bash
git diff --check
git commit -m "docs: validate Wails desktop shell"
```

用户未批准验证结果时，任务不得标记 `Done`。

## 官方参考

- [Wails 官方仓库与稳定通道](https://github.com/wailsapp/wails)
- [Wails v2 构建平台与 universal 参数](https://wails.io/docs/reference/cli/)
- [Wails v2 Go/JavaScript binding](https://v2.wails.io/docs/howdoesitwork/)
- [Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Apple App Sandbox 文件访问](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox)
- [PyInstaller onedir/onefile 行为](https://pyinstaller.org/en/stable/operating-mode.html)
