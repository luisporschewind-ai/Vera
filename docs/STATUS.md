# Vera 状态

**更新日期：** 2026-09-28
**当前阶段：** 阶段 8——Core 工具集、Policy v2 与原生 Git（In progress）
**仓库状态：** `main` 已合入阶段八工具/Policy/Git 与大文件拆分（`d7e75c1`），随后合入 Git 仓库初始化切片（`8db4c6e`）；截至本次记录，后续合并仍存在未解决冲突，不能视为完成。阶段十 Trace 正在隔离分支适配拆分后的 Core，尚未合入。对齐时还发现阶段八合并使阶段九 Skills 的 Runtime/Session 接线和 BYOK 启动入口失效，隔离分支同步恢复这些入口。阶段五停在 Ready for manual acceptance，阶段六与阶段七已 Complete；阶段八、九、十均不因代码合入自动变成 Complete。用户确认 CLI 封存的历史授权保持有效。2026-09-28 用户要求以阶段十一为里程碑，之前的任务与规格须对齐并落实，dogfood 统一在 `main` 由用户执行；本轮不运行回归测试。

## 当前工作汇总（2026-09-26）

详细核对与缺口见[非沙盒任务与文档对齐记录](evals/2026-09-26-task-document-alignment.md)。沙盒由另一会话维护，本次只保留既有依赖，不改其文档和实施状态。

| 工作 | 当前结论 | 剩余事项 |
| --- | --- | --- |
| 阶段五 | Ready for manual acceptance | 20 次真实 dogfood、三类工程人工矩阵 |
| 阶段六、七 | Complete；CLI 已封存 | 不因此自动启动桌面 |
| 阶段八 0059–0066 | 代码已合入 `main`；阶段 In progress | 用户在 `main` 验收、遗留问题复核与状态确认 |
| 阶段九 0067–0072、0074 | 代码已合入；拆分后的接线在隔离分支修复中；Ready for manual acceptance | 用户在 `main` 验收两类工程完整流程、负例/恢复矩阵、隔离 wheel 与状态确认 |
| CLI 0073、0075–0083 | Done；含 0078 人工复验闭环 | 后续发现另建问题，不重开已确认视觉项 |
| BYOK / 缓存 0084、0085 | 原版已合入并获用户手工验收；阶段八合并后的启动入口在隔离分支修复中；In progress | 用户在 `main` 复验，4 个打包/安装 smoke 环境阻断 |
| 联网检索 | 方向 Accepted，未实施 | 服务选型、审批细则、排序和实施授权 |
| 三档权限 / 自动审核 | 设计与计划 Accepted，未实施 | 沙盒前置、冲突规格/ADR 修订和独立实施授权 |
| 阶段十 Core Trace | In progress；规格 Accepted、任务 0086 集成中 | 拆分后的 Core 适配提交、用户在 `main` 验收；历史测试结果不能代替本次集成验证 |
| 阶段十一 Electron | Not started；UI 规格 Draft | 阶段八、九、十 Complete 后再进入 |

## 已完成与历史交付

- 阶段一至四在路线图中已记录 Complete；其中阶段一任务 0002 / 原始验收记录仍有人工链路证据差异，见对齐记录，不代填通过。
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

## 任务与规格入口

- [Core 联网资料检索](specs/2026-09-24-core-web-research.md)：用户于 2026-09-28 授权阶段十一里程碑前完成规格实现，并自行在 `main` 做回归与真实服务验收。隔离工作树首版选 Tavily、默认关闭，每次联网独立审批；[实施记录](tasks/core-web-research-implementation.md)为 Ready for manual acceptance。Ruff、Mypy、编译与差异空白检查通过，未运行回归或真实服务，不据此宣称产品可用。

- [BYOK 多厂商模型配置](specs/2026-09-25-byok-model-configuration.md)、[Provider 上下文缓存用量](specs/2026-09-25-provider-context-cache-usage.md)与 [ADR-0022](decisions/ADR-0022-user-owned-byok-provider-configuration.md)：用户于 2026-09-25 确认 Accepted；[任务 0084](tasks/0084-byok-model-configuration.md) 和 [任务 0085](tasks/0085-provider-cache-usage.md) 已在隔离 worktree `codex/provider-cache-usage` 实施并合入 `main`。全量可运行非 live 套件 `1297 passed, 2 deselected`；4 个打包/安装 smoke 用例因网络无法获取 `hatchling` 未能启动。Ruff、Mypy 与差异空白检查通过。用户确认本轮手工测试步骤通过，并提供 GLM 与 DeepSeek 真实请求及 `/usage` 结果；阶段八/九与阶段十门禁不变。
- [Core Trace 与运行可观测性](specs/2026-09-26-core-trace-observability.md)：规格 Accepted，阶段十及桌面/预览顺延关系见[ADR-0023](decisions/ADR-0023-insert-core-observability-before-desktop.md)；[任务 0086](tasks/0086-core-trace-observability.md)由当前主 Agent 逐任务实施。用户于 2026-09-26 明确授权阶段十与阶段八/九并行，并由用户自行验证阶段八、九；阶段八/九状态不变，阶段十一桌面仍等待阶段八、九、十全部 Complete。
- [阶段七执行顺序](tasks/phase-7-execution-order.md)：任务 0034–0041、0043–0058 Done；阶段七 Complete。剩余量化 dogfood 样本转入后续 Bug 收敛阶段规划；封存确认不自动授权下一阶段实施。
- [阶段五执行顺序](tasks/phase-5-execution-order.md)：0024 自动门禁已完成；人工 dogfood 不足，阶段五保持 Ready for manual acceptance。
- [ADR-0017：插入 CLI 体验阶段并顺延桌面路线](decisions/ADR-0017-insert-cli-experience-stage.md)：Accepted；阶段七用于 CLI 体验与个人主力化。其接受时的后续编号已由 ADR-0020 再次校准。
- [验证产物隔离与工作区无污染](specs/2026-09-14-verification-artifact-isolation.md)与 [ADR-0018](decisions/ADR-0018-isolate-verification-artifacts.md)：Accepted；最终验证计划必须在审批前形成，构建/缓存产物写到 workspace 外。
- [阶段七：CLI 体验收口与个人主力化](specs/2026-09-13-cli-experience-and-personal-dogfood.md)：Accepted；[任务级实施计划](tasks/phase-7-execution-order.md)已完成。
- [持久化对话会话与个人主力 CLI](specs/2026-09-13-persistent-conversation-sessions.md)：Accepted；实施归入阶段七。
- [项目指令发现与 `VERA.md` 初始化](specs/2026-09-14-project-instructions-and-vera-init.md)与 [ADR-0019](decisions/ADR-0019-native-vera-project-instructions.md)：Accepted；任务 0043 已 Done，普通启动不得静默写工程。
- [阶段八：Core 工具集与风险分级 Policy v2](specs/2026-09-17-core-tooling-and-risk-tiered-policy.md)与 [Vera 原生 Git 能力](specs/2026-09-17-native-git-capability.md)：Accepted；[ADR-0021](decisions/ADR-0021-core-tools-before-desktop.md)已 Accepted，阶段八 In progress。
- [阶段八执行顺序](tasks/phase-8-execution-order.md)：Accepted；实现在隔离分支 `codex/phase-8-tooling-policy-git`，0059–0065 Done，0066 Ready for manual acceptance；尚未合入 `main`。
- [阶段九执行顺序](tasks/phase-9-execution-order.md)：任务 0067–0071 自动实现完成；0072 Ready for manual acceptance；0074 Skill 浮层 Done（主路径用户复验）；会话持久化 `37b1c30` 已合入。
- [任务 0075：缩放闪动](tasks/0075-cli-resize-flicker.md)：Done；用户确认 Terminal.app 闪烁已解决。
- [任务 0076：Light 主题](tasks/0076-cli-light-theme.md)：Done；行内代码可读性修正已复验。
- [任务 0077：奶油风主题](tasks/0077-cli-cream-theme.md)：Done；正文与行内代码可读性修正已复验。
- [任务 0078：CLI 状态动效与回答逐行呈现](tasks/0078-cli-activity-and-paced-replies.md)：Done；2026-09-25 四项人工复验闭环，第四项经 0080 修正后通过。
- [任务 0079：Apple Terminal 启动字符](tasks/0079-apple-terminal-startup-probe.md)：Done；用户确认启动时不再出现 `p`。
- [任务 0080：主题回答与用户消息可读性](tasks/0080-cli-theme-readability.md)：Done；用户已在 Terminal.app 确认修改后无问题。
- [任务 0081：Logo 右侧四行信息与视觉层级](tasks/0081-cli-header-four-line-facts.md)：Done；用户已在 Terminal.app 视觉验收通过。
- [任务 0082：DSML 工具调用标记泄漏](tasks/0082-leaked-tool-call-markup.md)：Done；用户已在 Terminal.app 复验确认。
- [任务 0083：底栏 Skill 提示过时](tasks/0083-skill-footer-stale-selection.md)：Done；用户已在 Terminal.app 复验确认。
- [阶段九自动验收记录](evals/phase-9-core-native-skills.md)：自动门禁与新增矩阵已记录；隔离 wheel 安装曾因 offline 缓存缺少 `openai` 阻断，须复核；Terminal.app/`VeraTestDemo` 真实 Provider Skill 主路径已由用户 dogfood；Python、Swift/Xcode 副本完整修改/验证、负例/恢复矩阵和封存确认仍待。
- [阶段九：Core-native Skills](specs/2026-09-15-core-native-skills-system.md)与 [ADR-0020](decisions/ADR-0020-stage-core-native-skills.md)：Accepted；范围与安全边界不变。通常入口仍为阶段八 Complete；本次按用户明确授权并行实施，不改变阶段八状态。
- [阶段顺序更新](decisions/ADR-0023-insert-core-observability-before-desktop.md)：阶段十为 Core Trace 与运行可观测性，阶段十一桌面，阶段十二私有预览；ADR-0021 仅其编号顺序由本 ADR 取代。
- [三档权限与自动审核机制](specs/2026-09-25-approval-permission-profiles-and-auto-review.md)及[实施计划](tasks/approval-permission-profiles-implementation-plan.md)：Accepted；用户确认“完全访问”对齐 OpenAI 的无沙盒、无审批边界，仅当前会话生效，新会话恢复默认。产品实施须等完整 Core/Runner 沙盒完成、冲突的 Accepted 文档修订并接受，以及另行实施授权。沙盒规格当前仍在独立工作树，尚未合入 `main`。
- [Skill 交互列表](specs/2026-09-24-skills-interactive-picker.md)：Accepted 且已实施；浮层框线与斜杠互斥经用户确认。
- [视觉 Token](specs/2026-09-13-vera-cli-visual-tokens.md)：Accepted；2026-09-24 增补 Light 与奶油，内置主题为深海 / Light / 奶油 / 高对比 / 无色五套。
- [ADR-0013：首个桌面底版采用 Electron](decisions/ADR-0013-electron-desktop-baseline.md)：Accepted；当前实施编号由 ADR-0023 调整为阶段十一，只固定未来方向，当前不引入 Electron 代码或依赖。
- [阶段十一：桌面 Agent 工作台与 UI](specs/2026-09-12-desktop-agent-workbench-ui.md)：Draft；不启动阶段十一。
- [不可信内容、提示词投毒与内容安全](specs/2026-09-12-untrusted-content-and-prompt-injection-defense.md)：Accepted；由任务 0030 与 ADR-0015 实施。

## 最近验证

以下为按日期保留的历史证据，较早的“待复验”由后续确认覆盖；不同分支、不同提交的通过结果不能互相替代。

- 2026-09-26 文档对齐：同步阶段八 0059–0066、验收与重构记录（只同步文档，代码未合入），补齐索引；0078 依已有人工证据转 Done，0084/0085 修正为手工已过、安装态仍阻断。阶段五、八、九及桌面门禁未放宽。校验记录见本次对齐报告。
- 2026-09-26 BYOK / 缓存交付：`d616283` 经 `9354bb3` 合入 main；用户 GLM/DeepSeek 与 `/usage` 手工检查通过。可运行非 live `1297 passed, 2 deselected`，4 个打包/安装 smoke 因 `hatchling` 获取失败未启动；不是全部测试通过。

- 2026-09-25 原生 Terminal.app：用户按验收步骤检查 0081 四行信息对齐、层级、五套主题、窄窗裁切与未改动区域，原文确认「0081 通过」，任务转 Done。

- 2026-09-25 本地分批提交（用户授权，未推送）：`fd10f4f` 主题可读性与 Logo 右侧四行信息（0076–0081）；`8ad463d` DSML 标记泄漏修复（0082）；`d215bcd` 底栏 Skill 提示同步（0083）。`main` 领先 `origin/main`。

- 2026-09-25 原生 Terminal.app：用户确认任务 0082（DSML 标记泄漏）与 0083（底栏 Skill 提示）修正均已验证无问题，两项转 Done。

- 2026-09-25 任务 0083：底栏"已选择 Skill · 等待下一次任务"在 Run 消费或 `/skills clear` 后不消失。现在 TUI 按每条 `skill.selection.changed` 同步底栏；`/skills use` 命令也会显示提示。聚焦 `49 passed`；终端与会话目录 `285 passed`，唯一失败为已知不稳定的缩放防抖计时测试（单独重跑 2 过 1 败）。Ruff、Mypy 通过；Terminal.app 待用户复验。

- 2026-09-25 任务 0082：`deepseek-flash` 把 `propose_changeset` 调用以 `<｜DSML｜…>` 原始标记写进正文，Vera 当作回答显示并标 Done，工具实际未执行。现在适配器不再推送标记，Runtime 回写一次纠正，仍泄漏则以 `leaked_tool_call_markup` 失败。聚焦 `31 passed`，扩展回归 `416 passed`；Ruff、Mypy 通过。未运行全量测试，真实 Provider 待用户复验。

- 2026-09-25 任务 0081：Logo 右侧品牌版本/项目名/路径/模型四行与文字层级落地，长内容裁切保持对齐。相关回归 `35 passed`；三尺寸五主题检查、Ruff、Mypy、差异检查通过；原生 Terminal.app 已截图查看，用户视觉验收待确认。未运行全量测试。

- 2026-09-25 原生 Terminal.app：用户确认 0078 状态切换/Done、状态组展开、滚动/Resize，以及 0080 主题修正复验通过。Light/奶油回答可读性与五套主题用户消息底色已收口；相关终端测试 `77 passed`，Ruff check/format、Mypy 受影响源文件和差异检查通过。全量回归由用户执行。
- 2026-09-24 任务 0078/0079 并入 `main`：状态工作轨动效、回答逐行呈现、审批卡间距与中文标签、状态组初次展开及 Apple Terminal 启动字符修正。合并前聚焦测试 `62 passed`；合并后聚焦测试 `105 passed`，Ruff check/format、Mypy `src` 与差异检查通过。按用户要求，本轮不运行全量测试，Terminal.app 合并结果由用户验收。
- 2026-09-24 任务 0077：新增奶油风会话主题；视觉 Token 规格增补奶油列；`/theme cream` 与 `/theme 奶油` 等价。
- 2026-09-24 文档同步：将 Skill 持久化、0074 浮层（框线/斜杠互斥）、0075 缩放、0076 Light、以及用户 Terminal.app/`VeraTestDemo`/`deepseek-flash` 主路径 dogfood 写入任务与规格；阶段九仍非 Complete。
- 2026-09-24 任务 0076：新增 Light 会话主题（`f32fb58`）；视觉 Token 规格增补 Light 列；`/theme light` 与 `/theme Light` 等价。
- 2026-09-24 任务 0074 收口：用户确认浮层框线干净；确认 Skill 浮层与斜杠补全不再层级冲突（`77704e1`）。主路径：浮层选中 `interview-term-brief` → 提问生效 → Snapshot 绑定与一次性消费正确。
- 2026-09-24 任务 0075：用户确认原生 Terminal.app 缩放闪烁已解决；仅缩窗防抖 + 同步更新清屏生效。
- 2026-09-24 Skill 浮层实施：用户确认 0074 计划并授权实施；落地分组 Skill 浮层、歧义 ID 拒绝（`02ed5f8`、`c94382c`）；会话持久化已先提交（`37b1c30`）。
- 2026-09-24 Skill 生效修正：`/skills use` 的待用选择现随 Session Journal 恢复，`/model` 切换不丢失，`/compact` 不误消费；Run 绑定 Snapshot 后先落盘一次性消费，再向客户端交付绑定事件。聚焦与完整非 live 门禁见 [0072](tasks/0072-phase-9-skills-acceptance.md)。
- 2026-09-18 实施授权：用户选择方案 2（Inline Execution），授权阶段八按已接受计划串行实施并创建计划内本地提交；不包含 push、merge 或远程变更。
- 2026-09-21 阶段九自动验收：新增矩阵 `5 passed`；全量非 live `1169 passed, 2 deselected, 8 warnings`，另有 1 error + 1 failed，均为 offline wheel 依赖缓存缺少 `openai`；排除该环境阻断后 `1165 passed, 2 deselected, 8 warnings`。任务 0067–0071 完成，0072 Ready for manual acceptance。
- 2026-09-21 实施授权：用户明确允许阶段九不等待阶段八完全完成；阶段九使用独立分支/工作树 `codex/phase-9-skills`。当时不合并、不推送、不删除既有分支或工作树。
- 2026-09-22 GitHub 同步完成：Phase 9 实现与验收准备已合并到 `main`（`4665ab2`）；`origin/main`、`origin/codex/phase-9-skills`、`origin/codex/phase-8-tooling-policy-git`、规划分支与 Phase 6 修正分支均已核对对齐。阶段九仍为 Ready for manual acceptance。
- 2026-09-22 同步授权：用户要求将当前代码和文档更新推送到 GitHub 以保持进度对齐；本次允许合并阶段九实现并推送相关本地分支，不改变阶段八/九状态，也不启动阶段十。
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

1. 复核当前 main 的打包/隔离安装 smoke：0084/0085 仍有 4 个用例受 `hatchling` 获取失败阻断；阶段九旧 `openai` 缓存阻断也须在相应安装流程中关闭。
2. 阶段八：在隔离分支复核重构记录中的 Bash classifier、Git 全局配置读取、branch receipt recovery 问题及安装态，补齐可用 Node/TS runner/compiler 与 Terminal.app 全流程。经用户确认并单独授权集成后再合入 main；本轮不合并代码。
3. 阶段九：补齐 Python、Swift/Xcode 安全副本完整 Skill 流程及人工负例/恢复矩阵，用户确认后才可标 Complete。
4. 阶段五：补齐 20 次真实 dogfood 与三类工程人工矩阵；阶段七已接受的量化样本转移不自动关闭阶段五。
5. 核对阶段一 0002 的历史验收证据差异。未取得证据前不将原人工批准/验证/回滚写成已执行。
6. 已确认的 0078、0080–0083 人工项无需继续列为待验收；后续回归应按当前提交记录。`VeraTestDemo` 历史 `AD build/` 记录不在本轮复核/清理范围。
7. 联网检索、三档权限/自动审核与阶段十仅保留各自前置门禁；Trace 已获实施授权但须等阶段八、九 Complete。阶段十一桌面和阶段十二私有预览继续遵循新的前置门禁；沙盒任务由另一会话继续。
