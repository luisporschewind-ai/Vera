# 任务 0068：SkillSnapshotStore、原子冻结与安全清理

**状态：** Done（代码与局部门禁通过）；阶段八仍保持原状态

**Goal：** 将已验证的 Skill 包冻结为内容寻址、私有、可恢复的 Snapshot，使运行和恢复不再依赖会漂移的原始 Skill 目录。

**规格：** `docs/specs/2026-09-15-core-native-skills-system.md`

## 实现内容

- 新增 `SkillSnapshotCodec` 与 `SkillSnapshotStore`，Snapshot 位于 `<state_dir>/skills/snapshots/sha256/<snapshot_id>/`。
- Snapshot ID 绑定格式版本、`skill_id`、来源、规范化 Manifest、排序后的路径、长度和原始字节；绝对源路径不进入 Snapshot 内容或公共描述。
- 冻结前后重新验证原包，源包变化、非法资源和写入失败均失败关闭；临时目录写入后 fsync，再原子发布，目录 `0700`、文件 `0600`。
- 加载时重新校验版本、文件类型、路径、UTF-8、逐文件 hash、聚合 hash 和 Snapshot ID；缺失、损坏、版本未知不回退读取源包。
- 新增引用扫描和保守清理：引用或引用状态不确定时保留；无引用至少 30 天后才清理，并返回 `skill_snapshot_cleanup_refused` 事实。
- `RecoverySnapshot` 以 additive 可选字段保存公共 `SkillSnapshot` 事实，不保存 Skill 正文，旧恢复快照仍可读取。

## 验收证据

已通过：

```text
25 passed（Snapshot、Codec、恢复及既有 persistence 回归）
ruff check src tests 通过
ruff format --check src tests 通过
mypy src 通过
git diff --check 通过
```

覆盖内容包括：

- 同内容同来源复用、不同来源身份隔离、权限和公共路径/正文不泄漏；
- 源包修改后冻结拒绝且不发布半成品；
- Snapshot 缺失、损坏、篡改、版本未知、路径异常和 hash 不匹配失败关闭；
- 活动/可恢复引用、最近 Snapshot、30 天孤儿 Snapshot 和不确定引用扫描的清理边界；
- 旧 `SnapshotCodec`/`RecoverySnapshotStore` 回归与带 Skill 公共事实的恢复往返。

## 未完成与边界

- 本任务还没有把 Snapshot 接入 Runtime、Session 选择或 Context；这些属于任务 0069；
- 本任务不提供 CLI，不扫描或执行 Skill 脚本，不修改阶段八状态；
- 真实 Terminal.app、安装 wheel 和真实工程 dogfood 留到任务 0072；
- 本任务提交：`feat: add immutable skill snapshots`。
