# Vera 状态

**更新日期：** 2026-09-28
**当前阶段：** 阶段 8——Core 工具集、Policy v2 与原生 Git（In progress）
**仓库状态：** 2026-09-28 所有工作树与分支代码已汇入 `main`：阶段八工具/Policy/Git 与大文件拆分（`d7e75c1`）、Git 仓库初始化（`8db4c6e`）、0089 工作区权限沙盒、Trace（经 `codex/trace-on-main` 适配拆分后的 Core，并恢复阶段九 Skills 的 Runtime/Session 接线与 BYOK 启动入口）、Core 联网检索首版（默认关闭）、Skill 浮层、CLI 活动/审批卡与 Logo/缩放修正。阶段五停在 Ready for manual acceptance，阶段六与阶段七已 Complete；阶段八、九、十均不因代码合入自动变成 Complete。用户确认 CLI 封存的历史授权保持有效。2026-09-28 用户要求以阶段十一为里程碑，之前的任务与规格须对齐并落实，dogfood 统一在 `main` 由用户执行。

## 当前独立实施

- 2026-09-28 Apple iOS 阻塞已定位并在最终生产 SRT backend 假工程路径通过：真实 Xcode unsigned generic iOS build exit 0，Storyboard 成功，Core APFS 产物卷卸载/删除、`cleanup_error=null`，外部读取仍被拒。审批展示回归 7 passed（Intel 六个服务、once、临时卷/容量/销毁、后代及模拟器风险）；FakeModel 拒绝审批时执行调用数 0。Ruff、diff-check 通过。未跑全量、取消/超时或 CLI 人工交互；VerificationRunner Apple 服务路径未接通，故 0089 仍 In progress。ARM 实机延期，iOS/Swift 产品目标保留。证据见[任务记录](tasks/0089-apple-toolchain-repair.md)。

| 工作 | 当前结论 | 剩余事项 |
| --- | --- | --- |
| 阶段五 | Ready for manual acceptance | 20 次真实 dogfood、三类工程人工矩阵 |
| 阶段六、七 | Complete；CLI 已封存 | 不因此自动启动桌面 |
| 阶段八 0059–0066 | 代码已合入 `main`；阶段 In progress | 用户在 `main` 验收、遗留问题复核与状态确认 |
| 阶段九 0067–0072、0074 | 代码与拆分后的接线已合入 `main`；Ready for manual acceptance | 用户在 `main` 验收两类工程完整流程、负例/恢复矩阵、隔离 wheel 与状态确认 |
| CLI 0073、0075–0083 | Done；含 0078 人工复验闭环 | 后续发现另建问题，不重开已确认视觉项 |
| BYOK / 缓存 0084、0085 | 原版已获用户手工验收；阶段八合并后的启动入口已恢复并合入 `main`；In progress | 用户在 `main` 复验，4 个打包/安装 smoke 环境阻断 |
| 联网检索 | 用户 2026-09-28 授权实施；首版（Tavily、默认关闭、单次审批）已合入 `main`；Ready for manual acceptance | 用户在 `main` 回归与真实服务验收 |
| 三档权限 / 自动审核 | 设计与计划 Accepted，未实施 | 沙盒前置、冲突规格/ADR 修订和独立实施授权 |
| 0089 工作区权限沙盒 | 代码已合入 `main`；In progress | Apple 服务经 VerificationRunner、CLI 取消/运行中撤权收口 |
| 阶段十 Core Trace | In progress；规格 Accepted、任务 0086 已适配拆分后的 Core 并合入 `main` | 用户在 `main` 验收；历史测试结果不能代替本次集成验证 |
| 阶段十一 Electron | Not started；UI 规格 Draft | 阶段八、九、十 Complete 后再进入 |

- 2026-09-28 正式验证执行链最小验收通过：生产 Planner→Runner→真实 SRT 使用临时工作区内 Ruff，成功、预期失败、越界读取拒绝均符合预期；报告真实生成后清理，工作区指纹不变。同时修复 Ctrl+C/异常出口跳过产物清理，两项回归先失败后通过，验证器 16 passed。完整 Runtime/CLI 验证交互及 Xcode/SwiftPM 仍未据此通过，见 [正式验证记录](tasks/0089-formal-verification-acceptance.md)。

- 0089 限时收尾：plain 显式 /paste 整段收集、Ctrl+C 清理监督进程并取消当前任务、/tools 空分隔符修正已实施，用户已完成多行一次提交、/tools 与运行中 Ctrl+C 后继续查询权限的人工验收。三项验证/回滚旧失败在补齐现有 Ruff PATH 后通过；两项安装 smoke 受离线 openai 缓存缺失阻塞，无联网安装。运行中键入撤权、Apple 服务能力经正式 VerificationRunner 的覆盖仍未收口；常规 SRT VerificationRunner 已通过成功/失败/越界拒绝闭环。见 [收尾及手动步骤](tasks/0089-cli-final-acceptance.md)。

- 0089 真实项目验收暴露的重复读取与 CLI 刷屏已修复：默认取消固定 8 条工具结果淘汰、保留有界执行事实与正文省略标记、检测跨轮无进展；plain 活动汇总及 /tools 详情、交互时间线读取分组已实施。修正旧审批提示冲突。用户真实 parentSectionIOS 复验已显示紧凑汇总；日志为 27 次只读调用、12 次模型请求，无相同工具/input_hash 重复；/tools 详情入口随后经用户单次读取及查看详情补验通过。用户要求停止扩大测试，不宣称全量测试或任务整体通过。详见 [调查及修复记录](tasks/0089-read-loop-cli-investigation.md)。

- 已形成 [0089 工具链依赖调查与跨语言验收计划](tasks/0089-toolchain-acceptance-plan.md)：Vera 保持通用 Coding Agent 产品范围，覆盖 Python、JS/TS、C/C++、Go、Rust、Java、Swift。Apple 静态候选 96 个二进制/68 个 framework，尚有 8 类未确定名称及动态加载不确定性，不据此申请全目录权限或宣称依赖已完整。各语言入口存在不等于验收通过，普通配置与系统设置未改。
- xcrun 精确 Developer 目录节点读取获用户批准后，临时 literal 规则实测使 R_OK 成功，未授权子文件仍 EPERM；未递归开放 Developer。后续 xcrun 遇缓存目录与 xcodebuild 依赖限制；同范围显式 xcrun_db 后缓存错误消失，仍缺 DVTSystemPrerequisites 读取。SwiftPM 全流程未通过；诊断后端规则尚未纳入产品，普通配置未改变。
- xcrun 定位调查已确认宿主工作正常，系统入口调用 libxcselect；Xcode 提供实际 libxcrun.dylib。用户已批准该库与两份元数据三文件临时只读，复验推进到 Developer 目录访问检查，但 xcrun exit 74 / EPERM，SwiftPM 测试仍未开始；产物清理正常且工作区无变更。未开放 Developer 整目录，具体目录访问需求仍待定位，不将其猜测为仅需元数据权限。
- 2026-09-27 验证流程集成验收仍受阻：用户批准 SwiftBuild 组件后库加载成功，SwiftPM 转而在 xcrun 开发工具选择阶段 exit 1；同范围显式 DEVELOPER_DIR 诊断报 Developer/usr/bin/xcrun 不存在，宿主检查确认也不存在，不能据此猜测授权；已查到实际安装的 Developer/usr/lib/libxcrun.dylib，定位机制待进一步核对。Runner 均正确报告 failed、清理产物根、工作区无变更；未更改系统开发工具选择。SwiftPM 测试未开始，不能写为全流程通过。
- 2026-09-27 Swift 最小构建验收通过：用户补充批准 llbuild 精确库文件只读后，swift-build-h8kot57j 下真实 Core/SRT 编译 exit 0、两项断言通过、预期失败 exit 7、产物越界读写均 EPERM；专用模块缓存生成 26 个文件。临时工具链/SDK/库权限未保存到普通配置；Xcode 工程、VerificationRunner 和 CLI 全流程仍未据此验收，证据见任务 0089。
- 2026-09-27 Git 生命周期修正后通过：初始化被拒来自 SRT 对 Git 配置/Hook 祖先的保护，git init 不属于现有原生 Git 工具范围；采用已有假仓库元数据准备夹具，所有提交和分支命令仍在真实 SRT 内执行。修复 Core 提交消息读取私有状态目录的问题，改为校验后单独 argv 传递。最终夹具 git-lifecycle-8puvp3rk 验证提交、重复计划幂等、分支创建/切换、log/show 及外部/私有状态/Git 配置/Hook 拒绝通过；59 项回归通过。未扩权或修改普通配置，不代表支持 git init 或所有 Git 场景，详见原生 Git 验收记录。
- 2026-09-27 原生 Git 最小复验通过：经用户批准，仅临时开放 Xcode 内实际 Git 文件的读取，真实 Core/SRT 状态、工作区 Diff、版本查询成功，外部读取仍 EPERM。已修复发现错误分类及子 Git 的固定 PATH 选择，相关回归 58 passed；普通配置未保存新授权，未改宿主设置。详见 [0089 原生 Git 验收](tasks/0089-native-git-acceptance.md)。不外推完整 Git 生命周期或用户 CLI 验收。
- 2026-09-27：任务 0089 在隔离工作树 `/Users/admin/.codex/worktrees/workspace-permission-sandbox/Vera` 实施，采用 Accepted 工作区权限规格。当前代码覆盖 Core 文件读写授权、会话/单次 Grant、禁网 SRT 命令树、Bash/Git/验证统一受限执行、显式 CLI 沙盒设置和失败关闭。代码已于 2026-09-28 合入 `main`，不改变阶段八状态。
- Intel macOS 假数据边界及后续人工验收已通过工作区/单文件读写、目录只读/读写含子目录、Bash 单次参数/工具绑定与消费、授权撤销、审批展示及模型事实修复。IPv4/IPv6 loopback 网络被拒；工作区假 AF_UNIX stream 连接拒绝补验通过，前后对照均成功且服务未收到沙盒连接；不外推所有 IPC。具体证据及唯一活动验收清单见任务 0089 的“当前验收对齐”，不再沿用历史待验措辞。
- 后端 runtime 缺失/版本错误、真实 SRT 正常结束/超时/超时后继续执行、同进程组父子超时清理实际验收通过，其他初始化异常及逃离进程组不据此外推。独立 Core+SRT 主动取消、运行中撤销及父子清理通过（不代表 CLI 取消/运行中撤销交互通过）。基础 Core/SRT Git 生命周期已通过，仍待 Xcode/Swift 构建/测试及最终回归；CLI/特殊 Git 场景不据此外推。Apple Silicon 已由用户延期封存，不阻塞本轮 Intel 收口；Linux/Windows、联网授权不在本轮范围。
- 本机共享 Python 可执行文件检查为 0 字节，尚未修复；验收临时使用同版本完整 Python.app 解释器加载原虚拟环境。该环境问题与沙盒验收分开记录；没有重装/升级共享 Python。已执行的后端故障测试使用独立临时配置，正常沙盒配置保持不变。
- 相关聚焦回归、Ruff、格式检查和 Mypy 结果见 [任务 0089](tasks/0089-workspace-permission-sandbox.md)。该实现已合入 `main`，待用户统一验收。

## 已完成

- 阶段一、阶段二、阶段三、阶段四全部任务
- 阶段六：任务 0025–0029、0031–0033、0042
- 阶段七：任务 0034–0041、0043–0058；用户已确认封存
- [任务 0029：阶段六产品验收](tasks/0029-phase-6-product-acceptance.md)
- [任务 0042：验证产物隔离与工作区无污染](tasks/0042-verification-artifact-isolation.md)
- [任务 0033：用户消息、工具块与 tool_call_id](tasks/0033-cli-dogfood-bugs.md)
- [任务 0032：时间线信息层次与错误保真](tasks/0032-timeline-and-error-fidelity.md)
- [任务 0031：CLI 版本身份与 `--version`](tasks/0031-cli-version-identity.md)
- [任务 0028：终端兼容、可访问性与性能](tasks/0028-terminal-compatibility-accessibility-performance.md)
- [任务 0027：时间线、Diff、审批与错误体验](tasks/0027-timeline-diff-approval-and-errors.md)
- [任务 0026：路径引用、命令目录与诊断](tasks/0026-path-mentions-commands-and-diagnostics.md)
- [任务 0025：Composer、历史、粘贴与单条队列](tasks/0025-composer-history-paste-and-queue.md)
- [任务 0024：契约冻结与阶段五验收](tasks/0024-phase-5-contract-freeze-and-acceptance.md)（自动完成，Ready for manual acceptance）
- [任务 0030：不可信内容与提示词投毒防御](tasks/0030-untrusted-content-and-prompt-injection.md)
- [任务 0023：代表性工程与安装升级](tasks/0023-representative-projects-and-install-upgrade.md)
- [任务 0022：状态、恢复与长会话加固](tasks/0022-state-recovery-and-long-run-hardening.md)
- [任务 0021：命令、进程与秘密加固](tasks/0021-command-process-and-secret-hardening.md)
- [任务 0020：文件系统与审批事实加固](tasks/0020-workspace-filesystem-and-approval-hardening.md)
- [任务 0010：流式 RuntimeOutput](tasks/0010-streaming-runtime-output.md)
- [任务 0011：Textual TUI 外壳与模式路由](tasks/0011-textual-tui-shell.md)
- [任务 0012：对话时间线与披露策略](tasks/0012-tui-timeline-and-disclosure.md)
- [任务 0013：Composer、审批与任务控制](tasks/0013-tui-composer-and-approvals.md)
- [任务 0014：模式兼容与阶段三验收](tasks/0014-terminal-modes-and-acceptance.md)
- [任务 0015：评测契约、Corpus 与夹具隔离](tasks/0015-eval-contracts-and-fixtures.md)
- [任务 0016：Worker、Runner 与基础评分](tasks/0016-eval-runner-and-scoring.md)
- [任务 0017：恢复场景、指标与确定性](tasks/0017-eval-recovery-and-metrics.md)
- [任务 0018：评测 CLI 与 14 个冻结任务](tasks/0018-eval-cli-and-corpus.md)
- [任务 0019：阶段四完整验收](tasks/0019-eval-phase-4-acceptance.md)

## 活动任务

- [任务 0075：CLI 窗口缩放闪动修正](tasks/0075-cli-resize-flicker.md)：自动与 PTY 输出验证完成，Ready for manual acceptance；原生 Terminal.app 拖拽观感待复验。
- [Core 联网资料检索](specs/2026-09-24-core-web-research.md)：用户于 2026-09-28 确认授权实施并合入 `main`，自行在 `main` 做回归与真实服务验收。首版选 Tavily、默认关闭（`VERA_WEB_RESEARCH=1` 与 `TAVILY_API_KEY` 开启），每次联网独立单次审批；审批卡以中文字段显示服务、实际查询、来源与结果上限。[实施记录](tasks/core-web-research-implementation.md)为 Ready for manual acceptance；未调用真实服务，不据此宣称产品可用。

- [BYOK 多厂商模型配置](specs/2026-09-25-byok-model-configuration.md)、[Provider 上下文缓存用量](specs/2026-09-25-provider-context-cache-usage.md)与 [ADR-0022](decisions/ADR-0022-user-owned-byok-provider-configuration.md)：用户于 2026-09-25 确认 Accepted；[任务 0084](tasks/0084-byok-model-configuration.md) 和 [任务 0085](tasks/0085-provider-cache-usage.md) 已在隔离 worktree `codex/provider-cache-usage` 实施并合入 `main`。全量可运行非 live 套件 `1297 passed, 2 deselected`；4 个打包/安装 smoke 用例因网络无法获取 `hatchling` 未能启动。Ruff、Mypy 与差异空白检查通过。用户确认本轮手工测试步骤通过，并提供 GLM 与 DeepSeek 真实请求及 `/usage` 结果；阶段八/九与阶段十门禁不变。
- [Core Trace 与运行可观测性](specs/2026-09-26-core-trace-observability.md)：规格 Accepted，阶段十及桌面/预览顺延关系见[ADR-0023](decisions/ADR-0023-insert-core-observability-before-desktop.md)；[任务 0086](tasks/0086-core-trace-observability.md)由当前主 Agent 逐任务实施。用户于 2026-09-26 明确授权阶段十与阶段八/九并行，并由用户自行验证阶段八、九；阶段八/九状态不变，阶段十一桌面仍等待阶段八、九、十全部 Complete。
- [阶段七执行顺序](tasks/phase-7-execution-order.md)：任务 0034–0041、0043–0058 Done；阶段七 Complete。剩余量化 dogfood 样本转入后续 Bug 收敛阶段规划；封存确认不自动授权下一阶段实施。
- [阶段五执行顺序](tasks/phase-5-execution-order.md)：0024 自动门禁已完成；人工 dogfood 不足，阶段五保持 Ready for manual acceptance。
- [ADR-0017：插入 CLI 体验阶段并顺延桌面路线](decisions/ADR-0017-insert-cli-experience-stage.md)：Accepted；阶段七用于 CLI 体验与个人主力化。其接受时的后续编号已由 ADR-0020 再次校准。
- [验证产物隔离与工作区无污染](specs/2026-09-14-verification-artifact-isolation.md)与 [ADR-0018](decisions/ADR-0018-isolate-verification-artifacts.md)：Accepted；最终验证计划必须在审批前形成，构建/缓存产物写到 workspace 外。
- [阶段七：CLI 体验收口与个人主力化](specs/2026-09-13-cli-experience-and-personal-dogfood.md)：Accepted；[任务级实施计划](tasks/phase-7-execution-order.md)已完成。
- [持久化对话会话与个人主力 CLI](specs/2026-09-13-persistent-conversation-sessions.md)：Accepted；实施归入阶段七。
- [项目指令发现与 `VERA.md` 初始化](specs/2026-09-14-project-instructions-and-vera-init.md)与 [ADR-0019](decisions/ADR-0019-native-vera-project-instructions.md)：Accepted；任务 0043 计划在会话恢复后、视觉原型前实施，普通启动不得静默写工程。
- [阶段八：Core 工具集与风险分级 Policy v2](specs/2026-09-17-core-tooling-and-risk-tiered-policy.md)与 [Vera 原生 Git 能力](specs/2026-09-17-native-git-capability.md)：Accepted；[ADR-0021](decisions/ADR-0021-core-tools-before-desktop.md)已 Accepted，阶段八 In progress。
- [阶段八执行顺序](tasks/phase-8-execution-order.md)：Accepted；按 0059–0066 串行推进，0059–0065 Done；0066 已完成自动验收并进入 Ready for manual acceptance，Node/TypeScript 与本轮 Terminal.app 人工验收仍待完成。
- [阶段九：Core-native Skills](specs/2026-09-15-core-native-skills-system.md)与 [ADR-0020](decisions/ADR-0020-stage-core-native-skills.md)：Accepted；范围与安全边界不变，由 ADR-0021 顺延到阶段九，必须等待阶段八 Complete。
- [ADR-0013：首个桌面底版采用 Electron](decisions/ADR-0013-electron-desktop-baseline.md)：Accepted；当前实施编号由 ADR-0021 调整为阶段十，只固定未来方向，当前不引入 Electron 代码或依赖。
- [阶段十：桌面 Agent 工作台与 UI](specs/2026-09-12-desktop-agent-workbench-ui.md)：Draft；不启动阶段十。
- [不可信内容、提示词投毒与内容安全](specs/2026-09-12-untrusted-content-and-prompt-injection-defense.md)：Accepted；由任务 0030 与 ADR-0015 实施。

## 最近验证

- 2026-09-24 任务 0075 CLI 缩放闪动修正：回归先复现三次缩放六次整屏清除；调整为拖动中不清屏、停止 0.4 秒后清屏和全画面同次输出。终端相关 `166 passed`；真实 PTY 缩放输出确认拖动中 0 次、稳定后 1 次清屏。完整非 live `1172 passed, 2 deselected, 8 warnings`，两项离线 wheel 安装因缓存缺少 `openai` 失败，补齐测试缓存后单独重跑 `2 passed`；Ruff、格式、Mypy、diff 检查通过。原生 Terminal.app 拖拽观感仍待人工复验；阶段七保持 Complete。
- 2026-09-18 实施授权：用户选择方案 2（Inline Execution），授权阶段八按已接受计划串行实施并创建计划内本地提交；不包含 push、merge 或远程变更。
- 2026-09-18 任务 0059：ToolAction/Policy v2/workspace permission 基座完成；双轮安全审查关闭所有 Critical/Important，聚焦 `59 passed`、完整非 live `1176 passed, 2 deselected`，Ruff、格式、Mypy、wheel/sdist、diff 检查通过。下一项为 0060。
- 2026-09-19 任务 0060（已完成）：canonical `read/grep/find/ls` 与 ToolExecutor 已接入；Runtime 普通只读路径不再调用 `ToolRegistry.execute`，高风险 ToolAction 的审批、快照恢复、批准后复验及 action resolved 持久化已接入；本轮审查修复补齐 `find` glob 越界、外部 symlink、执行阶段 action binding stale、显式 V2 policy identity 保护，以及 `approved=True` 不得绕过 `DENY`；相关 Core 分组 `386 passed`，CLI/Presentation `213 passed`；共同 non-live `1208 passed, 2 deselected, 6 warnings`，Ruff、格式、Mypy、wheel/sdist、diff 检查全部通过。
- 2026-09-19 任务 0061（已完成）：新增 `FileMutationPlan`、只读 Planner、动作级 Checkpoint/Receipt、`write/edit` ToolExecutor 管线、审批恢复和累计 Diff；补齐落盘前输出上限、Checkpoint 绑定回滚和父目录竞态保护；相关分组 `555 passed`；共同 non-live `1208 passed, 2 deselected, 6 warnings`，Ruff、格式、Mypy、wheel/sdist、diff 检查全部通过；Terminal.app 独立状态目录下首屏与窄窗口视觉走查通过。
- 2026-09-19 任务 0062（已完成）：新增结构化 `BashInput`/`CommandActionPlan`、`BashTool`、命令风险矩阵与 `CommandClassifier`，接入 ToolExecutor、最小子进程环境、process Receipt/恢复和 `/permissions [trust|revoke]` 持久化可见性；本地提交 `7cbdfd9`、`a27ba4d`。
- 2026-09-20 任务 0063（已完成）：新增 Core-owned native Git discovery、porcelain-v2 status parser、workspace-bounded `status/diff/log/show/branch-list`、binary summary、linked worktree/submodule/sparse/unborn/detached/operation-state fixtures；五个 canonical Git read tools 已注册并纳入 CompatibilityManifest，`balanced` 下只读 Git 自动允许；通用 `bash` 的 Git 写子命令返回 `use_native_git_tool` 并拒绝执行。专项与受影响回归 `47 passed`，全量 non-live `1255 passed, 2 deselected, 4 errors`；4 个 error 均为 wheel/sdist fixture 无法解析 PyPI 的 hatchling 依赖，未伪造通过。Ruff、format、影响范围 Mypy 通过；本地提交 `c37af18`，未合并、未推送。
- 2026-09-20 任务 0064（已完成）：新增 `GitCommitPlan`、path-scoped `git_commit`、私有 index backup/失败恢复、消息安全、父提交/目标 blob/路径集合/剩余 staged diff 反向验证，并接入 ToolExecutor、Policy/Approval、Receipt 与 CompatibilityManifest；临时仓库覆盖多路径、无关 staged、新建/删除/重命名及特殊路径。专项 `22 passed`；全量 non-live `1268 passed, 2 deselected, 4 errors`，4 个 error 均为 wheel/e2e setup 无法解析 PyPI 的 hatchling 依赖；Ruff、format、Mypy、`git diff --check` 通过。本地提交 `de93fb2`、`781e756`，未合并、未推送。Hook/签名/崩溃幂等恢复/分支动作保留给 0065。
- 2026-09-20 任务 0065（已完成）：已落地 Hook facts 与 trusted/untrusted Policy 边界、签名配置/失败稳定错误、Hook 越界修改检测、Commit receipt facts 与不重复恢复、branch create/switch 及 ToolExecutor 接入；补齐 Run 级 `PendingGitOperation` 快照、Git 生命周期事件和 TUI/Plain/JSON 共用呈现。受影响测试 `70 passed`，全量 non-live `1295 passed, 2 deselected, 7 warnings`；Ruff、format、Mypy、`git diff --check` 通过。本地提交 `6d0e37f`、`aeec20e`、`494b095`，未合并、未推送。
- 2026-09-20 任务 0066（自动验收完成，待人工确认）：新增阶段八 E2E/native Git/client parity/PTY 矩阵，修复安装态 recovery→tools Git 循环导入；全量 non-live `1307 passed, 2 deselected, 8 warnings in 313.68s`，阶段八新增 `10 passed`，安全/拒绝/恢复专项 `35 passed`；Ruff、format、Mypy、wheel/sdist、`git diff --check` 通过，仓库外 installed wheel smoke `All checks passed!`。Python dogfood 通过并完成原生精确 commit `5e702ba`，Swift/Xcode 安全副本在外部 DerivedData 与 `CODE_SIGNING_ALLOWED=NO` 模拟器边界下构建成功并完成原生精确 commit `78afaed`；Node/TypeScript 因 `.ts` 测试发现 0 个且离线 `tsc` `ENOTCACHED` 暂阻塞。本工作树本地提交为 `86e36cf`、`136f817`，未合并、未推送。
- 2026-09-18 规格审批：用户确认阶段八两份规格，允许继续编写实施计划；未授权产品代码、提交、推送或阶段状态切换。
- 2026-09-18 路线校准（早期检查点）：ADR-0021 Accepted；先实施阶段八 Core 工具集、Policy v2 与原生 Git，再进入阶段九 Skills。当时规格仍为 Draft，尚未授权实现；后续规格接受与实施授权见上方记录。
- 2026-09-17 阶段七封存：用户接受把剩余量化 dogfood 样本转入后续 Bug 收敛阶段规划，并原文确认「CLI 版本达到预期，可以封存」。任务 0041 与阶段七转 Complete。
- 2026-09-17 Codex 收口代测：真实 Provider 工具后回答关闭发现 50；原生 Terminal.app 的路径/CJK、表格、Diff/审批/取消、欢迎/底栏与缩放关闭发现 42、53、54。临时 Git 工作区取消后无修改。0051–0053、0055–0058 Done。
- 2026-09-17 收口修正：普通 `session.message` 不再永久占用 footer；缩放前清屏并回 Home，消除真实 Terminal 右侧残影；footer 宽度不超过最新终端列数；滚动测试先解除 tail-follow。时序回归连续 12 轮 `24/24` 通过。
- 2026-09-17 最终门禁：`1122 passed, 2 deselected, 6 warnings in 264.02s`；`ruff check`、`ruff format --check`、`mypy src`、`git diff --check` 全部通过。
- 2026-09-17 交接：产品代码无未提交改动。进场白块用户通过；波动单条、左下→右上、一巡 2.5 秒用户口头 ok。表格/Diff（发现 53）与缩放/底栏裁切（发现 54）自动栏已过，Terminal.app 未复验。
- 2026-09-17 任务 0058：缩放后强制重绘、底栏按内宽铺满以免模型名被裁。聚焦 `37 passed`；`ruff`/`mypy`/`git diff --check` 通过。待 Terminal.app。
- 2026-09-17 任务 0057：对话表格按内容宽度排表、Diff 词界折行；进场单条亮带约 2.5 秒一巡（用户口头 ok）。表格/Diff 待 Terminal.app。
- 2026-09-17 任务 0056：进场三行点阵欢迎卡、缩行全路径、底栏分支/审批/模型、用户时间 AM/PM。Terminal.app：白块通过。
- 2026-09-17 任务 0055：工作轨上移、状态组默认收起、顶栏强化 `VERA` 字标。聚焦测试 `102 passed`；`ruff`/`mypy`/`git diff --check` 通过。待 Terminal.app。
- 2026-09-17 任务 0054：发现 51、52 Terminal.app 复验通过。`bd3f308` 让虚构「等待审批」去真正提出 Change Set，缺失的 `ruff`/`pytest`/`mypy` 在规划期拒绝。
- 2026-09-17 任务 0053：状态带 K 单位、运行状态左置、审批卡上下 margin 自动栏通过，待 Terminal.app 确认。
- 2026-09-17 任务 0052：发现 50（工具后 empty_model_response）自动栏通过，待 Terminal.app 复验。
- 2026-09-17 任务 0051：发现 42 折行与回答署名 Vera 自动栏通过，待 Terminal.app 复验。
- 2026-09-17 任务 0050：发现 49 Terminal.app 复验通过。`661a894` 让取消后旧循环停住，不再复活 run、不再 Worker 失败。
- 2026-09-17 任务 0049：发现 48 Terminal.app 复验通过。`cfeb240` 让运行中 Esc 发送一次取消。
- 2026-09-17 任务 0041 第 2 项：明确 ID、`/compact` 重启、Esc 取消、失败/恢复、无 Git、dirty 通过。
- 2026-09-17 任务 0048：发现 47 Terminal.app 复验通过。`5412f00` 让状态带显示当前会话预算已用/上限字节。
- 2026-09-17 任务 0041 第 4 项：0/A/B/C/D 通过。
- 2026-09-16 任务 0047：发现 44/45 Terminal.app 复验通过。`193d35b` 接受裸 `-r`；`fb4c256` 让 `/new`/`/clear` 回到干净首屏。
- 2026-09-16 任务 0046：发现 46 Terminal.app 复验通过。`2413834` 已去掉高对比时间线白边并在切主题后重绘。
- 2026-09-16 任务 0045：发现 43 Terminal.app 复验通过。`6c1ba9d` 已把非法 tool JSON 写回模型，不再整轮 `model_error`。
- 2026-09-16 任务 0044：发现 38–41 Terminal.app 复验通过。`b42ed76` 已把 propose 失败写回模型、sticky 贴标题下、缩放重绘、上下文占用显示 `<1%`。
- 2026-09-16 任务 0041 走查：发现 38–41。High：propose 失败未回写 tool 导致 thinking 400；sticky 叠在时间线中部。Medium：缩放右侧残留、上下文条 0%。工程未长出 `build/`。修正见 [任务 0044](tasks/0044-cli-dogfood-propose-and-sticky.md)。
- 2026-09-16 任务 0041：阶段七自动验收。[phase-7-cli-product-acceptance](evals/phase-7-cli-product-acceptance.md)；人工项见 [phase-7-manual-dogfood](evals/phase-7-manual-dogfood.md)。完整非 live `1068 passed, 2 deselected`；聚焦矩阵/PTY/性能 `22 passed`；仓库外 wheel smoke 退出码 0。阶段七 Ready for manual acceptance，不是 Complete。
- 2026-09-16 任务 0040：对话主轴、`occurred_at` 本地 `HH:mm`、用户消息滚动锚点、一行工具摘要、Composer `›`/`>` 回退与审批密度收口。共同门禁 `1057 passed, 2 deselected`。未改审批边界或 JSON/Plain 语义。
- 2026-09-16 任务 0039：字标 `VERA`、深海三主题、Welcome 首屏与双侧状态带落地。Fake 推理 `unavailable`，OpenAI 兼容适配器 `provider_default`。60×16 保留上下文百分比。共同门禁 `1036 passed, 2 deselected`。
- 2026-09-16 任务 0038：用户选择 A 字标、两行品牌、拟议深海色、连续对话主轴、一行工具摘要、60×16 上下文百分比。[视觉 Token](specs/2026-09-13-vera-cli-visual-tokens.md) Accepted。产品 TUI 未改。
- 2026-09-16 任务 0043：根目录 `AGENTS.md`/`VERA.md` 安全发现、Run 快照注入、`/instructions`、`/init` 与 `vera init` 通过；wheel smoke 与 PTY 无静默写入。真实 Terminal.app 三工程走查待用户，不记录说明正文。
- 2026-09-16 任务 0037：启动 `-c/-r`、`/sessions`、非 TTY picker 拒绝与 PTY 通过。
- 任务 0042：真实 Terminal.app Xcode 隔离复验通过（`run_187c2fe2abf94d7a91d35d790bb55568`，`passed`）。发现 36 审批卡复验通过（`run_54d549ca3e9d4e578f65443fb8f7302e`）。发现 37：模型 `artifact_plan` 已剥离并再提成功。
- 走查：`VeraTestDemo` 曾因未隔离的 `xcodebuild` 生成约 106 MB `build/`。用户手动删除磁盘 `build/` 后，隔离构建写入 `/private/tmp/vera-verification/.../000`，工程根未重建 `build/`。Git 索引仍有旧 `AD build/`，未取消暂存。
- 任务 0033：发现 1–3、8–17、19–34 已复验。第 4–7 项主路径已过。用户停止视觉走查。TUI 视觉冻结于 `25faf71`。
- 任务 0029：[phase-6-cli-product-acceptance](evals/phase-6-cli-product-acceptance.md)；人工走查见 [phase-6-manual-walkthrough](evals/phase-6-manual-walkthrough.md)
- 2026-09-16 门禁：完整非 live 产品测试 `922 passed, 2 deselected`；重建测试 uv cache 后 wheel smoke 2 passed；`ruff`/`mypy`/`git diff --check` 通过。
- 任务 0028：终端能力探测、尺寸矩阵、时间线预算与兼容记录
- 任务 0027：时间线披露、Diff 浏览、过期审批与退出码
- 任务 0026：`@path`、统一 Catalog 与七个只读诊断命令
- 任务 0025：Composer 历史、粘贴净化、单条队列与外部编辑器
- 任务 0024：[phase-5-core-hardening](evals/phase-5-core-hardening.md)
- 任务 0030：[untrusted-content-and-prompt-injection](evals/untrusted-content-and-prompt-injection.md)
- 任务 0023：[representative-projects-and-install-upgrade](evals/representative-projects-and-install-upgrade.md)
- 任务 0022：[state-recovery-and-long-run-hardening](evals/state-recovery-and-long-run-hardening.md)
- 任务 0021：[command-process-and-secret-hardening](evals/command-process-and-secret-hardening.md)
- 任务 0020：[workspace-filesystem-and-approval-hardening](evals/workspace-filesystem-and-approval-hardening.md)
- 阶段四总验收：[phase-4-evals-and-internal-readiness](evals/phase-4-evals-and-internal-readiness.md)
- 阶段四独立安全与路线审查：[phase-4-independent-security-and-alignment-review](evals/phase-4-independent-security-and-alignment-review.md)，64/64 项已检查，无需报告的安全漏洞。
- 仓库外 wheel smoke：`vera eval` validate/list/run/suite 均为 0，14/14 pass
- 任务 0018：[eval-cli-and-corpus](evals/eval-cli-and-corpus.md)
- 任务 0017：[eval-recovery-and-metrics](evals/eval-recovery-and-metrics.md)
- 阶段三总验收：[phase-3-rich-terminal-ui](evals/phase-3-rich-terminal-ui.md)

## 下一检查点

1. 用户在 `main` 统一验收本轮汇入的全部代码；验收前不得把阶段八、九、十或 0089 标为 Complete。
2. 收口任务 0089：复验 Xcode C 工程新清理路径，完成 Apple 构建的真实 CLI 审批/运行及 APFS 卷取消/超时清理检查，并决定 C++/Go/Rust/Java 代表样例是否属于本轮验收必需项。Intel iOS 假工程生产后端已通过。Apple Silicon 实机按用户决定延期封存，保留支持目标，不阻塞 Intel 验收。0089 不代替 0066 的真实 Terminal.app/TypeScript 验收。
3. 复核当前 main 的打包/隔离安装 smoke：0084/0085 仍有 4 个用例受 `hatchling` 获取失败阻断；阶段九旧 `openai` 缓存阻断也须在相应安装流程中关闭。
4. 阶段八：复核重构记录中的 Bash classifier、Git 全局配置读取、branch receipt recovery 问题及安装态，补齐可用 Node/TS runner/compiler 与 Terminal.app 全流程；用户明确确认后才可标 Complete。
5. 阶段九：补齐 Python、Swift/Xcode 安全副本完整 Skill 流程及人工负例/恢复矩阵，用户确认后才可标 Complete；市场、远程安装、自动更新、Plugin、Hook 与可执行能力继续不进入 v1。
6. 阶段五：补齐 20 次真实 dogfood 与三类工程人工矩阵；阶段七已接受的量化样本转移不自动关闭阶段五。
7. 核对阶段一 0002 的历史验收证据差异。未取得证据前不将原人工批准/验证/回滚写成已执行。
8. 已确认的 0078、0080–0083 人工项无需继续列为待验收。不自动删除、取消暂存或忽略 `VeraTestDemo` 索引里残留的 `AD build/`；未改 `.gitignore`。
9. 用户已确认「CLI 版本达到预期，可以封存」；该确认不自动授权 Electron 实施。三档权限/自动审核仅保留前置门禁；阶段十一桌面和阶段十二私有预览继续遵循新的前置门禁。
