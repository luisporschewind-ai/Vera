# 任务 0069：Session Selection、Run 绑定与 Context 装配

**状态：** Done（代码与局部门禁通过）；阶段九仍未收口

**Goal：** 让用户显式选择的单 Skill 只影响下一次 Run；Run 启动前冻结并绑定 Snapshot，Context 只读取冻结内容，并维持 NoSkill 与不可信内容边界。

**规格：** `docs/specs/2026-09-15-core-native-skills-system.md`

## 实现内容

- 新增 `SkillSelectionService`：显式选择、清除、冲突/失效选择保留 selector，成功选择只消费一次，不向其他来源静默回退。
- 新增 `SkillContextAssembler`：按 `SKILL.md → references → templates` 稳定顺序从 Frozen Snapshot 装配；只产生带 hash、来源和 trust 的 `ContentEnvelope`，正文不进入公共事实。
- `RunContext` 增加可选 `skill_snapshot` 与冻结 Context；Runtime 在 `run.started` 前完成冻结，成功后记录 `skill.snapshot.bound`，冻结/装配失败不建立半初始化 Run。
- `builtin/user` Skill Context 固定为 `advisory`，workspace Skill 固定为 `untrusted`；所有 Skill 内容以 user-context 数据进入模型，不修改 `SYSTEM_PROMPT`，不能成为 `builtin_policy`。
- RecoverySnapshot 保存可选公共 Skill Snapshot 事实；恢复重新加载私有 Snapshot，不重新读取原始 Skill 包。
- Session 状态增加 pending `SkillSelection` 的 additive 投影；NoSkill 默认不扫描、不建目录、不产生 Skill Event。
- bootstrap 只注册 Skill 控制面，不主动扫描任何来源目录。

## 验收证据

已通过：

```text
78 passed（Selection、Context、Runtime/Recovery、既有 Runtime/Session 回归）
ruff check src tests 通过
ruff format --check src tests 通过
mypy src 通过
git diff --check 通过
```

重点覆盖：

- 选择、消费、清除、失效 selector 保留和下一次 Run 语义；
- advisory/untrusted trust、固定装配顺序、正文与公共事件隔离；
- Snapshot 绑定事件、持久化绑定事实、原始包修改后的恢复一致性；
- 默认 NoSkill 行为及既有审批、Runtime、Session、项目指令回归。

## 未完成与边界

- `/skills`、`show`、`use`、`clear`、`status` 命令和 TUI/Plain/JSON parity 属于任务 0070；
- Session 选择的完整事件/磁盘迁移与安装态兼容属于任务 0071；
- 本任务不改变阶段八状态，不引入桌面代码；
- 本任务提交：`feat: bind skills to recoverable runs`。
