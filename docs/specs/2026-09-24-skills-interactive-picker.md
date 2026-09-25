# Vera CLI Skill 列表与交互选择

**状态：** Accepted（2026-09-24 用户确认书面规格并要求编写实施计划）
**日期：** 2026-09-24
**所属阶段：** 阶段九——Core-native Skills 体验补全
**上位规格：** [Core 原生 Skills 系统](2026-09-15-core-native-skills-system.md)

## 意图与验收目标

用户希望在 Vera 中输入 `/skills` 后看到真正可操作的 Skill 列表，了解 Skill 属于系统内置、用户本地还是当前项目，并用 ↑↓ 选择、Enter 确认。用户已明确：Enter **只选择下一次任务 Run 的 Skill**，返回输入框等待提问；不能因此自动提交草稿或启动模型请求。当前 `/skills` 已返回结构化 `skill.listed`，但 TUI 只把它投影为文字，必须另输 `/skills use <selector>`，因此发现与使用之间仍有交互断点。

完成的可观察结果：安装了 `user:interview-term-brief` 的用户能用 `/skills` 找到它，按 Enter 后看到选择成功并回到原输入位置，接着输入问题才触发任务；无需记忆或手输完整 `skill_id`。这一能力属于阶段九的 CLI 人工验收前置补全，不代表阶段九自动 Complete，也不改变 Provider 配置要求。

## 范围与方案

采用主 TUI 内的独立 Skill 选择浮层，不复用只适合命令/参数补全的 Composer 弹窗，也不另起一个终端应用。浮层只消费现有 `skill.listed` 的公共 `SkillSummary`，不扫描文件、不读取 Skill 正文、不解析 Manifest。Core 的 `SkillRegistry`、`SkillSelectionService`、`SkillSelection`、Snapshot 与 Run 绑定仍是唯一权威。浮层选择时向同一个 `SessionController` 发送已有的 `/skills use <skill_id>` 会话动作；TUI 不直接修改 pending selection，也不根据人类文案推断成功。

不增加 `skill.toml` 字段或按用途的分类体系；不做自动触发、多 Skill、安装器、远程发现、Plugin、Hook 或桌面 UI。Plain/JSON 继续通过 `/skills` 获取同一结构化列表，通过 `/skills use <selector>` 选择，不模拟需要终端按键的浮层。

## 列表与分类

列表按下表顺序分为三个可见组；组内按规范名称、再按完整 `skill_id` 稳定排序，缺失规范名称的无效行排在组末：

| 组名 | `source_kind` | 含义 |
| --- | --- | --- |
| 系统内置 | `builtin` | Vera 安装包内的只读 Skill |
| 用户本地 | `user` | 当前用户配置目录的 Skill |
| 当前项目 | `workspace` | 当前 workspace 的 Skill，信任级别仍为 `untrusted` |

有效行至少显示名称、简短描述、来源、`availability` 和必要时的完整 `skill_id`；缺少规范名称的损坏包只能显示安全的「无效 Skill」占位和来源/原因码，不能暴露目录路径。当前会话待用 Skill 用文字标记，不能只靠颜色。`conflict` 表示不同来源同名时，若完整 `skill_id` 能唯一指向有效包，该行仍可选择；UI 必须提交完整 ID，绝不按来源静默择一。若同一来源中出现重复 `skill_id`，列表行不可选，Core 也必须拒绝歧义，不能选第一个候选。`invalid` 与 `incompatible` 行保留原因码供审阅，但不能通过 Enter 选择。空列表应说明三个来源均未发现可列出的 Skill，不伪造默认项。

列表只显示公共摘要，不展示 `SKILL.md`、模板正文、绝对包路径、Provider Key 或私有 Snapshot 路径。分类只是来源说明，不赋予系统内置或用户 Skill 新的执行权限。

## 交互状态

1. 用户在 TUI 空闲状态（无活动 Run、无待处理审批）提交精确的 `/skills`，Core 产生 `skill.listed`；TUI 根据其 `items` 打开选择浮层。活动 Run 或待处理审批期间 `/skills` 仍可列出结构化结果，但不打开浮层，避免改变现有 Esc 取消与审批键盘语义；用户可在空闲后再打开。`/skills show`、`/skills use`、`/skills clear` 维持原有命令含义，不打开浮层。
2. 浮层获取键盘焦点。↑↓ 在可选行之间移动；组标题、无效、不兼容和重复 ID 行不可选。超出可视区域时滚动选中行，在 60×16 中仍保留标题、来源、选中行与 Esc/Enter 提示，不遮挡 Composer。Enter 以所选行完整 `skill_id` 发送现有会话动作，且仅发送一次；等待回应期间禁用重复 Enter 和 Esc，避免把已提交的选择误当作已取消。
3. 只有收到结构化 `skill.selection.changed` 且 `status=selected`、`skill_id` 与所提交 ID 一致后，浮层才关闭并把焦点还给 Composer。原草稿与光标位置不变；不发送 `SubmitPrompt`，不启动 Run。下一次任务 Run 按上位规格消费该选择，`/status` 显示待用选择。
4. 未提交选择时 Esc 关闭浮层，不改变原待用 Skill 或草稿。选择被 Core 拒绝或列表打开后来源失效时，保留列表并显示 Core 原因码；会话关闭或动作发送失败时关闭列表并显示错误，不显示虚假的成功。用户可重新打开 `/skills` 获取最新事实。如果同一 `skill_id` 的包内容在列出后改变但仍合法，最终选择以 Core 重新解析的版本为准，确认状态必须显示实际版本；不能自动回退到同名其他来源。
5. 底栏"已选择 … 等待下一次任务"提示必须跟随 Core 事实（2026-09-25 增补，任务 0083）：收到任何 `status=selected` 的 `skill.selection.changed`（浮层或 `/skills use`）时显示实际 `skill_id` 与版本；Run 绑定后一次性消费、`/skills clear` 或选择失败产生的未选择事件到达时移除该提示，不覆盖其他无关提示。
6. 重新打开列表时获取最新 `skill.listed`，不依赖上次浮层缓存；已经待用的 Skill 以文字标记。用户在活动 Run 期间仍可按既有 `/skills use <skill_id>` 显式设置下一次任务 Run 的待用选择，不修改活动 Run 的 Snapshot。

## 客户端与控制边界

TUI 的可选行由 `SkillSummary` 和当前 `SkillSelection` 构成，只读投影；Core 仍负责解析完整 ID、校验来源、写入会话选择与冻结下一次 Run 的 Snapshot。Plain/JSON 中的 `/skills` 仍返回列表事实，不能因没有按键 UI 而改变选择语义。事件顺序、错误码、会话持久化和 NoSkill 默认路径不得倒退。选中一个 Skill 不等于执行包内脚本、授予 Tool/网络权限或批准文件修改。

## 验证与人工验收

- Core/Session：三来源摘要、跨来源同名完整 ID、同来源重复 ID 拒绝、损坏与不兼容包、列表打开后源包变化；Enter 最终只产生一次显式选择，未产生 Run。
- TUI Pilot：↑↓、Enter、Esc、空列表、禁用行、长列表滚动、草稿/光标保留、选择失败、重复 Enter、活动 Run 与审批状态；不依赖文案判断成功。
- 客户端 parity：TUI、Plain、JSON 读取同一 `skill.listed`/`skill.selection.changed` 事实；Plain/JSON 不输出 TUI 控制字符；NoSkill、Session 恢复与原有命令回归。
- 真实 Terminal.app：60×16 和 80×24、默认 / Light / 高对比 / 无色主题；用 `interview-term-brief` 从 `/skills` 选中、回到输入框、手动提问，并在 Python 与 Swift/Xcode 安全工程副本完成既定阶段九 dogfood。真实 Provider 或安装态环境阻断必须单独记录，不以 Pilot 代替人工通过。

**实施修订（2026-09-24）：** 规格已 Accepted 并完成计划实施；浮层框线与斜杠互斥已用户确认。任务记录见 [0074](../tasks/0074-phase-9-skill-picker-plan.md)。阶段九整体仍待封存确认。
