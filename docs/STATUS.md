# Vera 状态

**更新日期：** 2026-09-16
**当前阶段：** 阶段 6——CLI 功能与可靠性收口（In progress）
**仓库状态：** 阶段五停在 Ready for manual acceptance。任务 0025–0029 自动部分已完成，任务 0031–0033 代码在当前工作树。任务 0042 隔离实现已提交 `940bd29`；发现 36/37（命令审批展示与模型 `artifact_plan` 剥离）随本提交纳入。阶段七 CLI 体验与阶段八桌面集成都未开始；不引入 Electron 代码。暂无远程时可不推送。

## 已完成

- 阶段一、阶段二、阶段三、阶段四全部任务
- [任务 0029：阶段六产品验收](tasks/0029-phase-6-product-acceptance.md)（自动完成，Ready for manual acceptance）
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

- [任务 0033：用户消息、工具块与 tool_call_id](tasks/0033-cli-dogfood-bugs.md)：Done。视觉走查由用户停止；TUI 修正留在未提交工作树。不封存阶段六。
- [任务 0042：验证产物隔离与工作区无污染](tasks/0042-verification-artifact-isolation.md)：In progress。隔离实现、发现 36 审批卡与发现 37 模型 `artifact_plan` 剥离均已复验并纳入本分支。阶段六保持 In progress。
- [任务 0032：时间线信息层次与错误保真](tasks/0032-timeline-and-error-fidelity.md)：代码已合入当前工作树；待 Terminal.app 复验滚动与失败文案。
- [任务 0031：CLI 版本身份与 `--version`](tasks/0031-cli-version-identity.md)：已合入当前工作树；待 Terminal.app 复验 `vera --version`。
- [阶段六执行顺序](tasks/phase-6-execution-order.md)：0025–0029 自动部分已完成；0031–0033 已合入或收口；0042 真实 Xcode 隔离、发现 36 审批卡与发现 37 均已复验。
- [阶段五执行顺序](tasks/phase-5-execution-order.md)：0024 自动门禁已完成；人工 dogfood 不足，阶段五保持 Ready for manual acceptance。
- [ADR-0017：插入 CLI 体验阶段并顺延桌面路线](decisions/ADR-0017-insert-cli-experience-stage.md)：Accepted；阶段七用于 CLI 体验与个人主力化，原桌面阶段顺延为阶段八。
- [验证产物隔离与工作区无污染](specs/2026-09-14-verification-artifact-isolation.md)与 [ADR-0018](decisions/ADR-0018-isolate-verification-artifacts.md)：Accepted；最终验证计划必须在审批前形成，构建/缓存产物写到 workspace 外。
- [阶段七：CLI 体验收口与个人主力化](specs/2026-09-13-cli-experience-and-personal-dogfood.md)：Accepted；[任务级实施计划](tasks/phase-7-execution-order.md)已写成，等待用户接受，尚未开始实现。
- [持久化对话会话与个人主力 CLI](specs/2026-09-13-persistent-conversation-sessions.md)：Accepted；实施归入阶段七。
- [项目指令发现与 `VERA.md` 初始化](specs/2026-09-14-project-instructions-and-vera-init.md)与 [ADR-0019](decisions/ADR-0019-native-vera-project-instructions.md)：Accepted；任务 0043 计划在会话恢复后、视觉原型前实施，普通启动不得静默写工程。
- [ADR-0013：阶段八首个桌面底版采用 Electron](decisions/ADR-0013-electron-desktop-baseline.md)：Accepted；只固定未来实施方向，不改变 CLI 封存门禁，当前不引入 Electron 代码或依赖。
- [阶段八：桌面 Agent 工作台与 UI](specs/2026-09-12-desktop-agent-workbench-ui.md)：Draft；不启动阶段八。
- [阶段八后候选：Core 原生 Skills 与能力扩展](specs/2026-09-15-core-native-skills-system.md)：Draft；当前无实现。[ADR-0020](decisions/ADR-0020-stage-core-native-skills.md)为 Proposed，先与插件市场分离规划，阶段八完成且规格/ADR Accepted 后才建立实施任务。
- [不可信内容、提示词投毒与内容安全](specs/2026-09-12-untrusted-content-and-prompt-injection-defense.md)：Accepted；由任务 0030 与 ADR-0015 实施。

## 最近验证

- 走查新发现：`VeraTestDemo` 曾因未隔离的 `xcodebuild` 在工程根生成约 106 MB `build/`。用户 2026-09-15 手动删除磁盘 `build/` 后，`vera 0.1.0+940bd29` 的真实构建写入 `/private/tmp/vera-verification/.../000`，工程根未重建 `build/`。Git 索引仍有旧 `AD build/`，未取消暂存。
- 任务 0042：真实 Terminal.app Xcode 隔离复验通过（`run_187c2fe2abf94d7a91d35d790bb55568`，`passed`）。发现 36 审批卡复验通过（`run_54d549ca3e9d4e578f65443fb8f7302e`：命令/Profile/产物根可见，用户 Reject）。发现 37：模型 `artifact_plan` 已剥离并再提成功。阶段六未封存。
- 任务 0033：走查发现 1–3、8–17、19–34 已复验。第 4–7 项主路径已过。用户 2026-09-15 停止视觉走查。当前冻结视觉：用户卡片 `$secondary` 填充、无蓝色描边、上下内边距 1 格、12 小时 AM/PM 灰色时间、左右 2 列与输入框对齐、时间线滚动条隐藏、输入区无独立底色。`VeraTestDemo/build` 仍为发现记录，未清理。阶段六未封存。
- 任务 0029：[phase-6-cli-product-acceptance](evals/phase-6-cli-product-acceptance.md)；人工走查见 [phase-6-manual-walkthrough](evals/phase-6-manual-walkthrough.md)，七项均为 Not run
- 任务 0028：终端能力探测、尺寸矩阵、时间线预算与兼容记录
- 任务 0027：时间线披露、Diff 浏览、过期审批与退出码
- 任务 0026：`@path`、统一 Catalog 与七个只读诊断命令
- 任务 0025：Composer 历史、粘贴净化、单条队列与外部编辑器
- 完整非 live：736 passed / 2 deselected
- 任务 0024：[phase-5-core-hardening](evals/phase-5-core-hardening.md)
- 任务 0030：[untrusted-content-and-prompt-injection](evals/untrusted-content-and-prompt-injection.md)
- 完整非 live：683 passed / 2 deselected
- 任务 0023：[representative-projects-and-install-upgrade](evals/representative-projects-and-install-upgrade.md)
- 完整非 live：634 passed / 2 deselected
- 任务 0022：[state-recovery-and-long-run-hardening](evals/state-recovery-and-long-run-hardening.md)
- 任务 0021：[command-process-and-secret-hardening](evals/command-process-and-secret-hardening.md)
- 完整非 live：587 passed / 2 deselected
- 任务 0020：[workspace-filesystem-and-approval-hardening](evals/workspace-filesystem-and-approval-hardening.md)
- 阶段四总验收：[phase-4-evals-and-internal-readiness](evals/phase-4-evals-and-internal-readiness.md)
- 阶段四独立安全与路线审查：[phase-4-independent-security-and-alignment-review](evals/phase-4-independent-security-and-alignment-review.md)，64/64 项已检查，无需报告的安全漏洞。
- 完整非 live：535 passed / 2 deselected；覆盖率 91%；manifest `8169f95abcb3bf1ccd30bfbadc1c2fee5464b7fdea3ce3909ea0fbc962a4d659`
- 仓库外 wheel smoke：`vera eval` validate/list/run/suite 均为 0，14/14 pass
- 任务 0018：[eval-cli-and-corpus](evals/eval-cli-and-corpus.md)
- 任务 0017：[eval-recovery-and-metrics](evals/eval-recovery-and-metrics.md)
- 阶段三总验收：[phase-3-rich-terminal-ui](evals/phase-3-rich-terminal-ui.md)

## 下一检查点

1. 任务 0042 真实 Xcode 隔离、发现 36 审批卡与发现 37 已过。阶段六仍有 0031/0032 待复验与索引残留 `AD build/`，完成前不得关闭。
2. 不自动删除、取消暂存或忽略 `VeraTestDemo` 索引里残留的 `AD build/`；未改 `.gitignore`。
3. 阶段七持久化会话、项目指令、TUI 视觉体验和个人 dogfood 的[任务级实施计划](tasks/phase-7-execution-order.md)已补齐；新增用户消息滚动锚点/时间、底部上下文/模型/推理状态带、输入箭头、状态层级与审批密度验收；阶段六关闭前不开始实现。
4. 阶段五仍缺 20 次真实 dogfood 与三类真实工程走查，不得把阶段五标为 Complete。
5. 未经确认「CLI 版本达到预期，可以封存」，不得将阶段七标为 Complete、不得开始阶段八、不得引入 Electron 或其他桌面端代码。
6. Skills 当前只有 Draft 规划，无实现；不得在规格接受和前置阶段完成前建立市场、远程安装或可执行 Skill 旁路。
