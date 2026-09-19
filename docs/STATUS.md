# Vera 状态

**更新日期：** 2026-09-18
**当前阶段：** 阶段 8——Core 工具集、Policy v2 与原生 Git（In progress）
**仓库状态：** `main` 文档基线，阶段八实施使用隔离工作树；阶段五停在 Ready for manual acceptance，阶段六与阶段七已 Complete。用户于 2026-09-17 原文确认「CLI 版本达到预期，可以封存」，并于 2026-09-18 选择 Inline Execution，授权阶段八按 0059–0066 串行实施和创建计划内本地提交。

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

- [阶段七执行顺序](tasks/phase-7-execution-order.md)：任务 0034–0041、0043–0058 Done；阶段七 Complete。剩余量化 dogfood 样本转入后续 Bug 收敛阶段规划；封存确认不自动授权下一阶段实施。
- [阶段五执行顺序](tasks/phase-5-execution-order.md)：0024 自动门禁已完成；人工 dogfood 不足，阶段五保持 Ready for manual acceptance。
- [ADR-0017：插入 CLI 体验阶段并顺延桌面路线](decisions/ADR-0017-insert-cli-experience-stage.md)：Accepted；阶段七用于 CLI 体验与个人主力化。其接受时的后续编号已由 ADR-0020 再次校准。
- [验证产物隔离与工作区无污染](specs/2026-09-14-verification-artifact-isolation.md)与 [ADR-0018](decisions/ADR-0018-isolate-verification-artifacts.md)：Accepted；最终验证计划必须在审批前形成，构建/缓存产物写到 workspace 外。
- [阶段七：CLI 体验收口与个人主力化](specs/2026-09-13-cli-experience-and-personal-dogfood.md)：Accepted；[任务级实施计划](tasks/phase-7-execution-order.md)已完成。
- [持久化对话会话与个人主力 CLI](specs/2026-09-13-persistent-conversation-sessions.md)：Accepted；实施归入阶段七。
- [项目指令发现与 `VERA.md` 初始化](specs/2026-09-14-project-instructions-and-vera-init.md)与 [ADR-0019](decisions/ADR-0019-native-vera-project-instructions.md)：Accepted；任务 0043 计划在会话恢复后、视觉原型前实施，普通启动不得静默写工程。
- [阶段八：Core 工具集与风险分级 Policy v2](specs/2026-09-17-core-tooling-and-risk-tiered-policy.md)与 [Vera 原生 Git 能力](specs/2026-09-17-native-git-capability.md)：Accepted；[ADR-0021](decisions/ADR-0021-core-tools-before-desktop.md)已 Accepted，阶段八 In progress。
- [阶段八执行顺序](tasks/phase-8-execution-order.md)：Accepted；按 0059–0066 串行推进，0059、0060、0061 Done；0062 尚未启动，需用户重新授权。
- [阶段九：Core-native Skills](specs/2026-09-15-core-native-skills-system.md)与 [ADR-0020](decisions/ADR-0020-stage-core-native-skills.md)：Accepted；范围与安全边界不变，由 ADR-0021 顺延到阶段九，必须等待阶段八 Complete。
- [ADR-0013：首个桌面底版采用 Electron](decisions/ADR-0013-electron-desktop-baseline.md)：Accepted；当前实施编号由 ADR-0021 调整为阶段十，只固定未来方向，当前不引入 Electron 代码或依赖。
- [阶段十：桌面 Agent 工作台与 UI](specs/2026-09-12-desktop-agent-workbench-ui.md)：Draft；不启动阶段十。
- [不可信内容、提示词投毒与内容安全](specs/2026-09-12-untrusted-content-and-prompt-injection-defense.md)：Accepted；由任务 0030 与 ADR-0015 实施。

## 最近验证

- 2026-09-18 实施授权：用户选择方案 2（Inline Execution），授权阶段八按已接受计划串行实施并创建计划内本地提交；不包含 push、merge 或远程变更。
- 2026-09-18 任务 0059：ToolAction/Policy v2/workspace permission 基座完成；双轮安全审查关闭所有 Critical/Important，聚焦 `59 passed`、完整非 live `1176 passed, 2 deselected`，Ruff、格式、Mypy、wheel/sdist、diff 检查通过。下一项为 0060。
- 2026-09-19 任务 0060（已完成）：canonical `read/grep/find/ls` 与 ToolExecutor 已接入；Runtime 普通只读路径不再调用 `ToolRegistry.execute`，高风险 ToolAction 的审批、快照恢复、批准后复验及 action resolved 持久化已接入；本轮审查修复补齐 `find` glob 越界、外部 symlink、执行阶段 action binding stale、显式 V2 policy identity 保护，以及 `approved=True` 不得绕过 `DENY`；相关 Core 分组 `386 passed`，CLI/Presentation `213 passed`；共同 non-live `1208 passed, 2 deselected, 6 warnings`，Ruff、格式、Mypy、wheel/sdist、diff 检查全部通过。
- 2026-09-19 任务 0061（已完成）：新增 `FileMutationPlan`、只读 Planner、动作级 Checkpoint/Receipt、`write/edit` ToolExecutor 管线、审批恢复和累计 Diff；补齐落盘前输出上限、Checkpoint 绑定回滚和父目录竞态保护；相关分组 `555 passed`；共同 non-live `1208 passed, 2 deselected, 6 warnings`，Ruff、格式、Mypy、wheel/sdist、diff 检查全部通过；Terminal.app 独立状态目录下首屏与窄窗口视觉走查通过。0062 尚未启动，等待用户重新授权。
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

1. 0060/0061 门禁与本地提交已完成；0062 尚未启动，必须等待用户重新授权后再制定其实施计划。
2. 不自动删除、取消暂存或忽略 `VeraTestDemo` 索引里残留的 `AD build/`；未改 `.gitignore`。
3. 阶段五仍缺 20 次真实 dogfood 与三类真实工程走查，不得把阶段五标为 Complete。
4. 用户已确认「CLI 版本达到预期，可以封存」；该确认不自动授权下一阶段或 Electron 实施。
5. Skills 当前只有 Accepted 规划、无实现，且必须等待阶段八完成；市场、远程安装、自动更新、Plugin、Hook 与可执行能力继续保持独立且不进入 v1。
