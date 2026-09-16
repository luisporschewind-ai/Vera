# 阶段七实施计划：CLI 体验收口与个人主力化

> **供主实现 Agent 执行：** 必须按任务逐项使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`；每个实施步骤使用 `- [ ]` 跟踪。未经用户接受本计划、阶段六关闭及对应视觉审批门通过，不得开始实现。

**状态：** Ready for manual acceptance；0041 自动栏已完成，真实 Terminal.app 与封存原文未完成
**目标：** 在不改变 Core 权威与安全边界的前提下，把 Vera CLI 收口为用户愿意长期使用的个人主力 Coding Agent，并为阶段八桌面端冻结可复用的会话与视觉语义。
**架构：** 持久化会话由 UI 无关的 `ConversationSessionStore` 统一提供，项目说明由 UI 无关的 `ProjectInstructionService` 以 Run 快照加载，`SessionController` 负责事务编排，TUI、Plain、JSON 只消费结构化 Session Event；视觉层只投影既有 Core 事实。阶段按“存储契约 → 安全存储 → Controller 接入 → 启动恢复 → 项目指令与初始化 → 可见原型审批 → TUI 状态收敛 → 时间线/Composer 收口 → 真实 dogfood”推进。
**技术栈：** Python 3.12、Pydantic 2、Typer、Textual 8、pytest、PTY 测试、Ruff、Mypy、uv/hatchling。
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[持久化对话会话](../specs/2026-09-13-persistent-conversation-sessions.md)、[项目指令与 `VERA.md` 初始化](../specs/2026-09-14-project-instructions-and-vera-init.md)、[ADR-0016](../decisions/ADR-0016-persistent-conversation-sessions.md)、[ADR-0019](../decisions/ADR-0019-native-vera-project-instructions.md)。

## 全局约束

- [x] 阶段六任务 0033、任务 0042、必要复验和阶段六关闭事实完成后，再从最新干净 `main` 创建第一个阶段七分支。
- [ ] 每个任务只有一个主实现 Agent；前一任务完成测试、文档、提交并合并后，下一任务才从新的 `main` 开始。
- [ ] 每个行为变化遵循 Red → Green → Refactor；先看到针对该行为的失败，再写最小实现。
- [ ] 不读取真实 Provider Key，不修改用户真实工程，不把 live 网络作为自动门禁前提。
- [ ] 不把完整工具输出、Diff、审批、Checkpoint、Provider 请求或环境变量复制到 Session Journal。
- [ ] 不在 Widget、CSS 或 CLI 文案中推断 Core 成功、风险、权限或恢复事实。
- [ ] 上下文状态明确使用 Vera 会话预算；模型 token 窗口或推理强度没有权威值时显示“模型默认/不可用”，不得伪造精确值。
- [ ] 不引入 Electron、Tauri、Wails、桌面资源、Multi-Agent、RAG、插件市场、云同步或账号系统。
- [ ] 遇到与当前已接受规格冲突的实现需求，先回写规格或 ADR 并取得用户确认，不以代码绕过。
- [ ] 每项提交前检查最终 diff、`git diff --check`、任务证据和工作树范围；不得夹带上一阶段或用户的未提交改动。

## 任务顺序与门禁

| 顺序 | 任务 | 主要交付 | 进入下一项的门禁 |
|---|---|---|---|
| 1 | [0034 会话记录契约与 Codec](0034-session-record-contracts-and-codec.md) | 版本化 Record、Payload、Codec、冻结夹具 | 纯契约测试和兼容性负例通过 |
| 2 | [0035 安全 Session Journal、Store 与修复副本](0035-session-journal-store-and-repair.md) | 私有追加、发现、加载、损坏分类、非破坏修复 | 崩溃/权限/损坏矩阵通过 |
| 3 | [0036 Context 与 Controller 事务接入](0036-session-controller-persistence.md) | 同一 Turn 投影、先落盘后提交内存、`unsaved` | Controller 事务顺序与模式无关测试通过 |
| 4 | [0037 CLI 新建、继续、选择与会话维护](0037-cli-session-startup-and-resume.md) | `vera`、`-c`、`-r`、`/sessions`、恢复展示 | TUI/Plain/JSON/非 TTY/wheel 入口一致 |
| 5 | [0043 项目指令发现与 `VERA.md` 初始化](0043-project-instructions-and-init.md) | advisory 双文件加载、`/instructions`、审批式 init | 安全/无污染/三模式/wheel 回归通过 |
| 6 | [0038 CLI 视觉原型与设计 Token 冻结](0038-cli-visual-prototypes-and-tokens.md) | 三套可见原型、尺寸矩阵、用户选择记录 | 用户明确接受一个方向后才允许 0039 |
| 7 | [0039 Vera 标识、主题与启动状态实现](0039-cli-brand-theme-and-startup-chrome.md) | Logo 回退、主题、首屏、上下文/模型/推理双侧状态带 | 60×16/80×24/120×40 和回退测试通过 |
| 8 | [0040 时间线、Composer 与导航收口](0040-timeline-composer-and-navigation-polish.md) | 对话主轴、用户消息锚点/时间、输入箭头、审批密度、稳定滚动 | PTY、Pilot、快照、性能矩阵通过 |
| 9 | [0041 阶段七产品验收与个人 dogfood](0041-phase-7-product-acceptance-and-dogfood.md) | wheel 回归、真实 Terminal.app/工程证据、缺陷闭环 | 用户原文确认后才可封存阶段七 |
| — | [0044 走查发现 38–41](0044-cli-dogfood-propose-and-sticky.md) | propose 失败回写、sticky/缩放、上下文条 | Done；用户 Terminal.app 复验通过 |
| — | [0045 走查发现 43](0045-cli-dogfood-invalid-tool-arguments.md) | 非法 tool JSON 写回并重试，不杀死 Run | 局部测试通过；真实 Terminal.app 复验待用户 |

任务必须严格按 0034 → 0035 → 0036 → 0037 → 0043 → 0038 → 0039 → 0040 → 0041 执行。0043 完成项目上下文基线后再进入视觉任务；0038 是产品视觉审批任务，不得与 0039 并行实施；0039–0040 不得为了视觉便利回改持久化或项目指令语义。

## 契约与依赖图

```text
ConversationSessionRecord / SessionCodec
                  ↓
SessionJournal → ConversationSessionStore → SessionOpenRequest
                  ↓                         ↓
          ConversationTurnProjector → SessionController
                                            ↓
AGENTS.md / VERA.md → ProjectInstructionService → VeraRuntime Context
                                            ↓
                         TUI / Plain / JSON Session Event
                                            ↓
                    Vera Brand + Theme + Timeline Widgets
```

- `ConversationSessionRecord` 不使用现有 `vera.session.protocol.SessionRecord` 名称，避免把 JSON 客户端协议与磁盘记录混为一类。
- `ConversationTurnProjector` 只从稳定终态 Event 生成脱敏 Turn；磁盘与内存消费同一个 Turn，不保留两套摘要算法。
- `ConversationSessionStore` 是 `sessions/` 的唯一写入口；派生索引可删除重建，Journal 才是权威证据。
- `SessionController` 暴露新建/恢复来源、持久化健康、未保存状态和会话摘要；三个客户端不得直接读 JSONL。
- `ProjectInstructionService` 只读取 workspace 根目录普通文件；项目说明是 advisory，不是权限、审批或可执行配置。
- 品牌、颜色和排版只改变展示，不改变 Session Event 类型、审批默认值、退出码或 Run Journal。
- 用户消息时间来自 Event/持久化 Turn；底部状态带来自 `SessionStatus`/`ActivityState` 的 UI 无关投影，Widget 不读取 Provider 配置或猜测执行事实。

## 共同自动门禁

每个任务先运行任务文件列出的局部测试，再运行：

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

0037、0040、0041 还必须运行 PTY；0041 必须从 `/private/tmp` 中的全新虚拟环境安装本地 wheel，且清除 Provider Key。自动结果只能形成 `Ready for manual acceptance`，不能代替真实 Terminal.app 与真实工程结论。

## 提交边界

每项任务一个主提交，建议提交信息如下：

1. `feat: define persistent conversation session records`
2. `feat: add secure conversation session storage`
3. `feat: persist controller conversation turns`
4. `feat: add conversation session resume flows`
5. `feat: add Vera project instructions`
6. `docs: freeze Vera CLI visual direction`
7. `feat: add Vera terminal identity and themes`
8. `feat: polish terminal conversation workflow`
9. `docs: record phase seven CLI acceptance`

任务中的 Red/Green 小提交可以保留；合并前最终范围必须仍与对应任务一致。计划本身不授权自动提交、推送、合并或开始实现。

## 阶段完成定义

- 0034–0040 与 0043 全部完成并合并；0041 自动矩阵通过。
- 持久化会话退出/继续/选择/压缩/损坏/修复行为满足已接受规格，且不会重复工作区副作用。
- 根目录项目说明可见、可控且不授予权限；普通启动不写工作区，init 只在审批后更新 `VERA.md`。
- Vera TUI 在真实 Terminal.app 中具有明确标识、收敛状态带、用户消息滚动锚点与原始时间、独立输入箭头、连续审批布局和可靠输入导航；Plain/JSON 语义未被破坏。
- 真实个人 dogfood 中没有未关闭的 Critical/High，Medium 均有明确修复、接受或后续处置。
- 用户明确原文确认「CLI 版本达到预期，可以封存」。缺少该句时，阶段七最多保持 `Ready for manual acceptance`，阶段八保持 `Not started`。
