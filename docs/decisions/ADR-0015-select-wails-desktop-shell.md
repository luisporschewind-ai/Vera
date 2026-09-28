# ADR-0015：选择 Wails 作为 Vera 桌面壳

**状态：** Accepted
**日期：** 2026-09-12
**批准依据：** 用户明确确认「可定为 Wails」

## 背景

Vera 阶段七需要桌面壳承载窗口、系统 WebView、原生目录选择、应用生命周期、Core sidecar 监督、打包、签名和升级。业务权威仍属于独立 Python Vera Core；桌面端不得解析 CLI 文本，也不得把 Core 规则重写到 Go 或 Renderer。

最初规划准备对 Wails、Tauri、Electron 做等量 Spike 后再选择。用户现已基于产品偏好和长期维护方向明确选择 Wails，并希望避免 Electron。因此框架选择从“竞争性评测”改为“用户决策 + 强制可行性验证”。

该决定表示 Vera 采用 Wails，不表示 Wails 已在当前环境通过发布级验证，也不表示 Wails 客观上优于所有候选。

## 决策

1. Vera 阶段七桌面壳固定为 Wails。
2. Wails Go 后端负责窗口、原生选择器、窄化 binding、`CoreSupervisor` 和应用级更新协调。
3. Python Core 继续作为独立、受监督的 onedir sidecar，使用 ADR-0014 定义的 framed stdio 协议。
4. Renderer 只消费结构化状态并发送窄化 Action；不得获得通用文件、Shell、进程或 credential 能力。
5. Vue/React 等 UI 技术单独评估，不由 Wails 模板默认值决定。
6. Wails stable major/patch 在执行日重新确认；pre-GA 版本不得成为默认产品基线。
7. 任务 0031 改为 Wails 发布可行性验证，不再实现或排名 Tauri/Electron。

## 强制验证门禁

Wails 必须在任务 0031 证明：

- 从签名应用包固定路径启动和监督 Python Core；
- framed stdio、背压、stderr、半帧、超限帧和协议污染行为可控；
- Renderer/Go binding 能力面可审计且足够窄；
- Core、Go 后端、WebView 的退出和崩溃不会留下孤儿进程；
- Intel macOS release `.app`、Core sidecar、嵌套依赖和 manifest 可打包与验证签名结构；
- 完整应用升级、迁移失败回滚和 Finder 启动路径成立；
- Workspace、审批、Diff、验证、恢复与回滚仍由同一个 Python Core 决策。

选择 Wails 不授权跳过任何门禁。门禁失败时必须暂停阶段七并请求用户决策。

## 不自动回退

Tauri 和 Electron 不再是阶段七的并行实现或必测候选。Wails 验证失败时：

1. 记录可复现证据和失败边界；
2. 判断是否属于可测试、可维护的 Wails 适配问题；
3. 停止任务并交用户选择修订范围或重新评估框架；
4. 未经新决策不得自动切换 Tauri/Electron。

## 后果

### 正面

- 框架方向明确，移除三套壳的重复 Spike 和决策悬置。
- Go 后端与 Python Core 的责任边界可以提前写实。
- 避免把 Electron/Node/Chromium 作为默认产品依赖。
- 仍保留协议、Core 和前端状态模型的框架独立性。

### 代价

- 不再获得三候选同机横向性能数据。
- 团队需要承担 Go/Wails 生命周期、签名、更新和稳定版本跟踪成本。
- 若 Wails 硬门禁失败，必须重新决策，阶段七会暂停。
- macOS system WebView 的差异需要真实平台验证，不能用框架宣传替代。

## 未由本 ADR 决定

- Vue、React 或其他 UI 框架；
- Wails v2 与未来 stable major 的执行日精确版本；
- Apple Silicon、Windows 或 Linux 支持状态；
- App Store 与 Developer ID 直接分发路线；
- 在线更新服务或阶段八发布策略。

## 重审触发器

- Wails 无法通过任务 0031 任一硬门禁；
- stable 版本停止维护或许可证发生不兼容变化；
- Wails 无法在不扩大 Renderer 权限的情况下承载 CoreSupervisor；
- 打包、嵌套签名或原子升级只能依赖不可维护 workaround；
- 用户明确要求重新比较桌面壳。

## 关联文档

- [阶段七桌面集成规格](../specs/2026-09-12-desktop-integration.md)
- [ADR-0014：桌面壳与 Python Core 采用受监督 sidecar 进程边界](ADR-0014-desktop-core-process-boundary.md)
- [任务 0031：Wails 桌面壳验证与限时 Spike](../tasks/0031-desktop-framework-measurement-spikes.md)
- [阶段七执行顺序](../tasks/phase-7-execution-order.md)
