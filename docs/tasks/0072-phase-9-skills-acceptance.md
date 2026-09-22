# 任务 0072：阶段九自动验收与人工验收准备

**状态：** Ready for manual acceptance

**Goal：** 汇总阶段九 Core-native Skills 的自动证据，明确安装态环境阻断和人工验收边界；没有人工验收或用户确认时，不将阶段九标记为 Complete。

**规格：** `docs/specs/2026-09-15-core-native-skills-system.md`、`docs/decisions/ADR-0020-stage-core-native-skills.md`

## 自动证据

已 Verified：

- 任务 0067–0071 的局部测试、Ruff、format、Mypy 和 `git diff --check`；
- 阶段九新增矩阵：`5 passed`，覆盖三来源、冲突/消歧、非法 Manifest、workspace 不可信来源、Snapshot 绑定、NoSkill 和 JSON/人类/时间线 parity；
- 全量非 live 自动门禁：`1169 passed, 2 deselected, 8 warnings`，另有两个既有安装态测试分别因离线依赖缓存出现 1 error、1 failed；
- 排除已确认环境阻断的两个旧 wheel smoke 文件后：`1165 passed, 2 deselected, 8 warnings`；
- `uv build --wheel --sdist` 成功；
- 从 wheel 解包并使用当前依赖运行 NoSkill/Snapshot 检查通过；
- 全仓库 `mypy src`：182 个源文件无问题；Ruff/format 全部通过。

Blocked：

- 仓库外隔离 venv 的 offline wheel smoke 未完成：uv 缓存缺少 `openai>=2,<3`，安装在依赖解析阶段失败；证据保留于 `/private/tmp/vera-phase9-nonlive.txt`。

Not run：

- 用户当前没有电脑，未执行原生 Terminal.app 60×16/80×24 人工走查；
- 未在 Python 工程安全副本和 Swift/Xcode 工程安全副本上做真实 Skill dogfood；
- 未得到“阶段九可以封存”的用户确认。

## 人工验收清单

待用户有电脑后，在独立安全副本和隔离状态目录中完成：

1. Terminal.app 运行 `/skills`、`/skills show`、`/skills use`、`/skills clear`、`/status`；确认成功/失败原因可读，正文、私有绝对路径和 ANSI 不泄漏。
2. 分别验证 builtin/user/workspace 来源、同名冲突、完整 `skill_id` 消歧、非法包和源包修改/删除后的失败关闭。
3. 运行一个 Python 工程副本和一个 Swift/Xcode 工程副本：显式选择 Skill，确认工程根、验证产物和 Skill Snapshot 不越界、不执行包内脚本。
4. 中断并恢复一个绑定 Skill 的 Run；确认恢复读取同一 Snapshot，缺失/损坏 Snapshot 停止，不回读可变原始包。
5. 确认 NoSkill 默认 Run 的消息顺序、Tool/Policy/Approval、Journal/Recovery 与既有行为一致。

## 阶段结论

阶段九自动实现已达到 `Ready for manual acceptance`。阶段八仍为 `In progress`；本任务依据用户明确授权在阶段八完全收口前并行实施阶段九，不改变阶段八状态，也不启动阶段十或引入桌面代码。
