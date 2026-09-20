# 任务 0071：NoSkill、兼容迁移与安装态整合

**状态：** Done（非 live 代码门禁通过；隔离 wheel 安装受依赖缓存阻断）；阶段九仍未收口

**Goal：** 证明 Skills 是可选控制面，不破坏旧 Run、Journal、Session、Recovery；在安装 wheel 后维持 NoSkill 与显式 Skill 的控制路径。

**规格：** `docs/specs/2026-09-15-core-native-skills-system.md`

## 实现内容

- 保持旧 Session journal 与 Recovery Snapshot decoder 的 additive 兼容：旧记录没有 Skill 字段时默认 `None`，既有格式和 hash 约束不改变。
- 增加旧 session fixture、旧 Recovery Snapshot、NoSkill Runtime、外部 user/workspace 根和 Snapshot 缺失失败关闭回归。
- 扩展 `scripts/smoke_installed_wheel.py`：安装态检查 `/skills` 列表/详情/选择/状态/清除、公共输出不泄漏正文和绝对路径、安装 wheel 内 NoSkill Run，以及 Snapshot 冻结、源包变化后的冻结字节读取和缺失拒绝。
- 不存在 Skill 根目录时继续保持不扫描、不创建 `state/skills`、不产生 Skill Event；bootstrap 只注入服务，不主动创建 Skill 目录。

## 验收证据

已通过：

```text
5 passed（兼容、NoSkill、外部根、Snapshot 恢复边界）
全量非 live：1164 passed, 2 deselected, 6 warnings
ruff check 受影响脚本和测试通过
ruff format --check 受影响脚本和测试通过
mypy 受影响 persistence/bootstrap 源文件通过
uv build --wheel --sdist 成功
wheel 解包后运行新增 NoSkill/Snapshot 检查通过
```

安装态阻断（环境证据，非代码失败）：

```text
uv pip install --offline ... vera_agent-0.1.0-py3-none-any.whl
No solution found ... openai was not found in the cache
```

同一阻断导致既有 `test_phase_4_wheel_smoke.py` 出现 1 error、既有 `test_phase_5_install_upgrade.py` 出现 1 failed；完整日志保存在 `/private/tmp/vera-phase9-nonlive.txt`。因此未宣称隔离 venv 安装态 Verified，只记录为环境 Blocked。

## 未完成与边界

- 真实可联网/完整依赖缓存下的隔离 wheel smoke 需重跑；本任务不把环境阻断改写成代码通过。
- 真实 Terminal.app、Python/Swift 工程 dogfood 与阶段验收属于任务 0072；
- 本任务不改变阶段八状态，不引入桌面代码；
- 本任务提交：`fix: preserve no-skill compatibility in installed clients`。
