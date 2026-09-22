# 任务 0070：CLI 命令与三客户端结构化投影

**状态：** Done（代码与局部门禁通过）；阶段九仍未收口

**Goal：** 让 TUI、Plain 和 JSON 客户端消费同一组 Core Skill 事实，支持发现、查看、选择、清除与状态显示；人类文案只负责展示，不能成为控制逻辑输入。

**规格：** `docs/specs/2026-09-15-core-native-skills-system.md`

## 实现内容

- 新增 `/skills`、`/skills show <name|skill_id>`、`/skills use <name|skill_id>` 和 `/skills clear` 命令，复用 Core `SkillRegistry` 与 `SkillSelectionService`。
- `/skills show` 只输出稳定摘要、兼容性和资源事实，不输出 `SKILL.md` 正文、模板正文、私有绝对路径或包根目录；查看不会改变下一次 Run 的选择。
- Session status 增加 pending Skill selection 与 active Skill Snapshot 的结构化投影；状态面板仅显示来源、版本和快照身份等公共事实。
- `skill.listed`、`skill.shown`、`skill.selection.changed`、`skill.snapshot.bound` 统一进入 CLI Presenter、Plain/JSON 会话和 Timeline Projector。
- 增加列表、查看、选择、清除、冲突、客户端 parity 与无终端尺寸输出测试；测试断言事件 JSON、人类文案和时间线共享同一事实且不含 ANSI 或 Skill 正文。

## 验收证据

已通过：

```text
8 passed（Session 命令、Skill 投影、客户端 parity、PTY 无尺寸回归）
ruff check 受影响源文件和测试通过
ruff format --check 受影响源文件和测试通过
mypy 受影响 9 个源文件通过
```

重点覆盖：

- `/skills` 列表与详情不泄漏 Skill 正文和绝对路径；
- `/skills use` 保留稳定 reason code，`/skills clear` 清理 pending selection；
- `/skills show` 不改变 pending selection；
- TUI/Plain/JSON 使用同一结构化事件事实，不依赖人类文本判断成功；
- PTY 相关输出不依赖颜色、终端尺寸或 ANSI 序列。

## 未完成与边界

- 安装 wheel、旧 Session/Recovery/Journal 兼容和 NoSkill 完整回归属于任务 0071；
- 真实 Terminal.app、Python/Swift 工程 dogfood 与阶段验收属于任务 0072；
- 本任务不改变阶段八状态，不引入桌面代码；
- 本任务提交：`feat: expose core skills through cli clients`。
