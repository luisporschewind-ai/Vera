# 阶段九：Core-native Skills 自动验收记录

**记录状态：** Ready for manual acceptance
**记录日期：** 2026-09-21
**实现工作树：** `/Users/admin/.codex/worktrees/phase-9-skills/Vera`
**实现分支：** `codex/phase-9-skills`

## 矩阵结果

| 能力 | 自动证据 | 状态 |
| --- | --- | --- |
| builtin/user/workspace 发现 | 0067、阶段九矩阵测试 | Verified |
| Manifest 严格校验、路径/符号链接/版本错误 | Manifest 与 Discovery 测试 | Verified |
| 同名冲突与完整 `skill_id` 消歧 | Registry、Selection、阶段九矩阵 | Verified |
| Snapshot 内容寻址、原子发布、权限和清理 | 0068 测试 | Verified |
| Run 前绑定、Context 顺序、workspace `untrusted` | 0069、untrusted context、阶段九矩阵 | Verified |
| 源包修改/删除后的恢复 | Skill recovery 与安装态解包检查 | Verified（安装 venv 受缓存阻断） |
| `/skills`、`show`、`use`、`clear`、`status` | Session、projection、parity、PTY 测试 | Verified（人工 Terminal.app 待执行） |
| NoSkill 默认路径 | 0069、0071、阶段九 NoSkill 测试 | Verified |
| 旧 Session/Journal/Recovery 兼容 | 0071 fixture 与全量回归 | Verified |
| wheel/sdist 构建 | `uv build --wheel --sdist` | Verified |
| 仓库外隔离 wheel 安装 | `smoke_installed_wheel.py` | Blocked：offline 缓存缺 `openai` |
| 真实 Terminal.app | 用户当前无电脑 | Not run |
| Python 与 Swift/Xcode 工程副本 dogfood | 用户当前无电脑 | Not run |

## 自动门禁

```text
阶段九新增矩阵：5 passed in 7.45s
全量非 live：1169 passed, 2 deselected, 8 warnings
全量非 live 另有：1 error + 1 failed（均为隔离 wheel 依赖缓存阻断）
排除两个已确认阻断的旧 wheel smoke 文件：1165 passed, 2 deselected, 8 warnings
uv build --wheel --sdist：成功
mypy src：Success，182 source files
Ruff check：通过
Ruff format --check：通过
git diff --check：通过
```

失败证据：

```text
No solution found when resolving dependencies:
Because openai was not found in the cache and vera-agent==0.1.0 depends on openai>=2,<3
```

完整输出保存在 `/private/tmp/vera-phase9-nonlive.txt`。这属于环境阻断，不改写为代码失败，也不能替代可联网/完整缓存环境的重跑。

## 待人工验收

待用户有电脑后，使用独立状态目录和工程安全副本完成：

- Terminal.app 60×16 与 80×24 的 `/skills` 全路径、冲突、失败、状态和恢复；
- Python 工程副本一次显式 Skill dogfood；
- Swift/Xcode 工程副本一次显式 Skill dogfood；
- 源包变化、Snapshot 缺失/损坏、NoSkill 对照；
- 工程根与验证产物隔离、无包内脚本执行；
- 用户明确确认阶段九结果后，才可更新任务/阶段为 Complete，并另行规划阶段十。
