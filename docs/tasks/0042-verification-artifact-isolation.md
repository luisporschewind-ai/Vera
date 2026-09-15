# 任务 0042：验证产物隔离与工作区无污染实施计划

> **供主实现 Agent 执行：** 必须按 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐项实施；每个行为变化先使用 `superpowers:test-driven-development`，结束前使用 `superpowers:verification-before-completion`。

**状态：** In progress
**执行就绪：** 步骤 1–8 自动部分已落地；真实 Terminal.app Xcode 回归未跑，阶段六保持 In progress
**分支：** `phase-6/0042-verification-artifact-isolation`（工作树另有 0033 TUI 未提交改动；未获提交授权；提交时只纳入 0042 文件）
**依赖：** 任务 0033 已 Done；不得与其他 Agent 同时改同一工作树
**规格：** [验证产物隔离与工作区无污染](../specs/2026-09-14-verification-artifact-isolation.md)
**决策：** [ADR-0018](../decisions/ADR-0018-isolate-verification-artifacts.md)

**Goal：** 让 Vera 的验证命令在审批前形成可哈希、可恢复的隔离计划，把构建和缓存产物写到 workspace 外，并对未知写入型命令失败关闭。

**Architecture：** `VerificationArtifactPlanner` 在 `ChangeSetBuilder` 前生成带 `artifact_plan` 的最终 `VerificationCommand`；`VerificationRunner` 拒绝 plan 为空的命令，并由 `VerificationArtifactRoot` 创建和清理精确临时根。Runtime 将同一命令绑定到 Change Set、PolicyEngine、审批和 Event，意外 workspace 变化只报告、不自动删除。

**Tech Stack：** Python 3.12、Pydantic 2、现有 `VeraRuntime`/`PolicyEngine`/`ProcessSupervisor`、pytest、临时目录、Xcode/SwiftPM 命令 Profile。

## 新 session 交接

- 0042 自动步骤 1–8 已在分支 `phase-6/0042-verification-artifact-isolation` 落地，未提交。
- 现有工作树仍含 0033 TUI 未提交改动（`src/vera/terminal/`、`theme.tcss` 等）。提交 0042 时不要夹带这些文件。
- 不自动删除、取消暂存或忽略 `/Users/admin/Desktop/VeraTestDemo/build`。
- 不开始阶段七/八，不引入 Electron，不把阶段六标为 Complete。
- 未经用户明确要求不要提交。
- 剩余：真实 Terminal.app 对 `VeraTestDemo` 的 Xcode 隔离回归；用户单独批准后才处理既有 `build/`。

## Global Constraints

- 不读取真实 Provider Key，不运行 live 测试，不自动修改 `/Users/admin/Desktop/VeraTestDemo`。
- 不自动删除、取消暂存或忽略当前已有的 `VeraTestDemo/build`。
- 不把外部产物隔离描述为 OS 沙箱；进程仍使用当前系统用户权限。
- 最终执行计划必须在 Change Set hash 和命令审批前生成；Runner 不得审批后静默改 argv。
- 只清理本 Run、本 verification index 精确绑定的 workspace 外根，拒绝符号链接和宽泛路径。
- 未匹配 Profile 的潜在写入命令不执行，不以“用户已经批准命令”放宽工作区写权限。

---

## 文件职责

| 文件 | 职责 |
|---|---|
| `src/vera/contracts/verification.py` | 版本化 artifact plan、planned command 与结果字段 |
| `src/vera/verification/artifacts.py` | Profile 识别、最终 argv/环境语义、隔离根绑定与安全清理 |
| `src/vera/verification/runner.py` | 只执行已规划命令，报告清理和 workspace 变化 |
| `src/vera/runtime/engine.py` | 在 Change Set 前规划，并把同一计划用于策略、审批、执行和 Event |
| `src/vera/runtime/context.py` | 持久保存当前 planned command，不维护第二套派生字段 |
| `src/vera/workspace/changeset.py` | 对最终 planned command 计算既有 content hash |
| `src/vera/recovery/models.py` | 通过 Change Set 保存计划，旧记录保持可读但执行前重规划 |
| `tests/verification/test_artifacts.py` | Profile、路径、安全根与清理的纯单元测试 |
| `tests/verification/test_runner.py` | 执行、超时、取消、清理和污染结果 |
| `tests/runtime/test_safe_editing_flow.py` | 规划→哈希→审批→执行的端到端 Runtime 契约 |
| `tests/runtime/test_recovery_snapshots.py` | 计划恢复、旧快照和审批过期 |
| `tests/e2e/test_verification_artifact_isolation.py` | 多生态临时工程不产生 workspace 产物 |

## 公开接口

在 `src/vera/contracts/verification.py` 定义：

```python
class VerificationArtifactPlan(ContractModel):
    schema_version: Literal[1] = 1
    profile: Literal["xcode", "swiftpm", "pytest", "mypy", "ruff_no_cache", "git_readonly", "tsc_no_emit"]
    root: str | None = None
    cleanup: Literal["always"] = "always"


class VerificationArtifactPlanner:
    def plan(
        self,
        command: VerificationCommand,
        *,
        workspace_root: Path,
        installation_id: str,
        run_id: str,
        index: int,
    ) -> VerificationCommand: ...
```

`VerificationCommand.artifact_plan` 默认为 `None`，保证旧数据可解码；新 Runtime 只把 Planner 返回的最终 `VerificationCommand` 放入 Change Set。Runner 根据受信任的 `profile + root` 确定固定环境键，不接受模型提供的任意环境变量。

## 实施步骤

### 1. 冻结契约与兼容读取

**Files:**

- Modify: `src/vera/contracts/verification.py`
- Test: `tests/contracts/test_models.py`
- Test: `tests/persistence/test_recovery_snapshot.py`

- [x] 在 `tests/contracts/test_models.py` 写失败测试：七种合法 Profile 可序列化，相对 root、`cleanup != always`、额外字段被拒绝；workspace 内 root 的上下文判断留给 Planner 测试。
- [x] 运行 `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts/test_models.py -q`，确认因 `VerificationArtifactPlan` 不存在而失败。
- [x] 实现上述 Pydantic 模型，并给 `VerificationCommand` 增加 `artifact_plan: VerificationArtifactPlan | None = None`。
- [x] 写旧 v1 Change Set/RecoverySnapshot 无 `artifact_plan` 仍可解码的测试；同时断言它不能被新 Runner 直接执行。
- [x] 运行两个契约测试文件，确认通过。

### 2. 建立安全、确定性的产物根

**Files:**

- Create: `src/vera/verification/artifacts.py`
- Create: `tests/verification/test_artifacts.py`

- [x] 写 `artifact_root()` 失败测试，固定结果为 `<temp>/vera-verification/<installation-sha256前12位>/<run-id>/<index三位>/`。
- [x] 写路径安全负例：workspace 位于系统 temp 内、父路径为符号链接、目标已是普通文件、run id 含分隔符、index 为负数时拒绝。
- [x] 实现 `VerificationArtifactRoot.prepare()`：逐级检查非符号链接目录，以 `0700` 创建本次精确根，不 chmod 调用方拥有的既存父目录。
- [x] 实现 `VerificationArtifactRoot.cleanup()`：先确认 root 仍位于固定 Vera temp 前缀、仍匹配 installation/run/index、不是符号链接，再删除本次根；任一校验失败返回 `artifact_cleanup_failed`，不执行删除。
- [x] 用只含哨兵文件的临时目录测试 cleanup；断言相邻 Run 目录和 workspace 字节不变。

### 3. Xcode 与 SwiftPM Profile

**Files:**

- Modify: `src/vera/verification/artifacts.py`
- Test: `tests/verification/test_artifacts.py`

- [x] 写 Xcode scheme 测试：输入 `xcodebuild -project Demo.xcodeproj -scheme Demo build`，输出追加 `-derivedDataPath <root>/DerivedData`，原参数顺序保持。
- [x] 写 Xcode target 测试：输入 `xcodebuild build -project Demo.xcodeproj -target Demo`，输出追加外部 `SYMROOT`、`OBJROOT`、`SHARED_PRECOMPS_DIR`、`DSTROOT`，环境包含外部模块缓存。
- [x] 写拒绝测试：原 argv 的 `-derivedDataPath`、`SYMROOT` 或 `OBJROOT` 指向 workspace、Home 或其他临时目录时返回 `verification_output_inside_workspace`/`verification_output_not_owned`。
- [x] 写 SwiftPM 测试：`swift build`、`swift test`、`xcrun swift test` 追加 `--scratch-path <root>/swiftpm`；原有 scratch path 只接受本次 root 内路径。
- [x] 实现 `_plan_xcode()` 与 `_plan_swiftpm()`，保证返回值是带 plan 的全新冻结 `VerificationCommand`，不修改输入对象。

### 4. Python、只读与拒绝 Profile

**Files:**

- Modify: `src/vera/verification/artifacts.py`
- Test: `tests/verification/test_artifacts.py`

- [x] 写 pytest 测试：`pytest` 与 `python -m pytest` 产生固定环境 `PYTHONDONTWRITEBYTECODE=1`、`PYTEST_ADDOPTS=-p no:cacheprovider`、`COVERAGE_FILE=<root>/.coverage`。
- [x] 写 Mypy 测试：缺少 cache 参数时追加 `--cache-dir <root>/mypy`；指向 workspace 的既有 cache 参数拒绝。
- [x] 写 Ruff 测试：`ruff check` 与 `ruff format --check` 的最终 argv 含 `--no-cache`，重复参数归一化，`ruff --fix` 拒绝。
- [x] 写 Git 测试：只接受 `git diff --check` 与 `git status`，Runner 环境固定加入 `GIT_OPTIONAL_LOCKS=0`；写入型 Git 子命令拒绝。
- [x] 写 TypeScript 测试：只接受同时含 `--noEmit --incremental false` 的 `tsc`。
- [x] 写拒绝矩阵：`ruff --fix`、写入型 Git、`tsc` emit、`npm run build`、`sh -c`、未知可执行文件返回 `verification_artifact_isolation_unavailable`。
- [x] 实现 Profile 分派；错误对象只包含稳定 code、命令 basename 和建议，不回显秘密参数。

### 5. 在 Change Set 与审批前规划

**Files:**

- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/workspace/changeset.py`
- Modify: `src/vera/runtime/context.py`
- Test: `tests/runtime/test_safe_editing_flow.py`
- Test: `tests/tools/test_command_policy.py`

- [x] 写失败测试：同一原始命令经 Planner 后的最终 argv/artifact plan 出现在 `ChangeSet.verification`，并改变 `content_hash`。
- [x] 写审批测试：`approval.required` 的 argv、cwd、Profile/root 与 Change Set 内计划一致；PolicyEngine 分类的也是最终命令。
- [x] 在 `VeraRuntime._propose()` 中依序规划 `proposal.verification`，再传给 `ChangeSetBuilder.build()`；规划失败产生结构化 tool/verification 拒绝，不生成可批准 Change Set。
- [x] `RunContext.pending_command` 保存已规划的 `VerificationCommand`；不得在 `_verify()` 或批准回调重新规划。
- [x] 运行 Runtime 与 CommandPolicy 局部测试，确认审批指纹变化会使旧批准过期。

### 6. Runner 执行、检测与清理

**Files:**

- Modify: `src/vera/verification/runner.py`
- Modify: `src/vera/contracts/verification.py`
- Modify: `src/vera/runtime/engine.py`
- Test: `tests/verification/test_runner.py`

- [x] 写未规划命令测试：Runner 返回 `rejected` + `verification_not_planned`，Fake Supervisor 调用次数为 0。
- [x] 写已规划命令测试：ProcessRequest 使用最终 argv、workspace cwd 和 Planner 固定环境；环境仍经过 `build_child_environment`，不能注入模型提供的键。
- [x] 写 passed/failed/timed_out/cancelled/error 参数化测试，断言每种状态都调用一次精确 cleanup。
- [x] 写 cleanup 失败测试，断言结果 code 为 `artifact_cleanup_failed`，不会调用 workspace 删除或 Git 命令。
- [x] 写防御性检测测试：Fake 命令在临时 workspace 新建 `build/sentinel` 后，结果为 `workspace_polluted`，Event 只含相对路径和数量，文件保留。
- [x] 扩展 `VerificationResult` 与 `verification.started/completed` Payload，保留旧字段并新增 `artifact_profile`、`artifact_root`、`artifact_cleanup_status`、`workspace_mutations`、`reason_code`。

### 7. Recovery 与幂等行为

**Files:**

- Modify: `src/vera/recovery/models.py`
- Modify: `src/vera/runtime/engine.py`
- Test: `tests/runtime/test_recovery_snapshots.py`
- Test: `tests/persistence/test_recovery_snapshot.py`

- [x] 写快照 round-trip 测试，断言 planned verification 的 argv/root/Profile 完整保存。
- [x] 写恢复测试：同一绑定且外部根不存在时安全重建；命令/root/installation/workspace 任一不一致时旧审批过期。
- [x] 写旧快照测试：可以只读检查，但 resume 在执行验证前返回需重新规划/审批，不直接运行无 plan 命令。
- [x] 实现恢复校验；不得把“临时根不存在”误判为用户 workspace 损坏。

### 8. 多生态无污染回归

**Files:**

- Create: `tests/e2e/test_verification_artifact_isolation.py`
- Modify: `docs/evals/phase-6-cli-product-acceptance.md`
- Modify: `docs/evals/phase-6-manual-walkthrough.md`
- Modify: `docs/STATUS.md`
- Modify: this task

- [x] 用临时 Git 工程记录验证前完整文件清单与 Git porcelain，运行 Xcode/SwiftPM/Python Profile 的 Fake Process，再断言验证后完全相同。
- [x] 在 macOS/Xcode 可用环境增加真实 `xcodebuild` 测试标记；产物根必须位于 `/private/tmp`，临时工程根不得出现 `build/`。
- [x] 将本次 `VeraTestDemo/build` 记录为阶段六发现，不伪造“已清理”或“已复验”。
- [x] 在用户明确批准前，不删除现有 build、不取消暂存、不写 `.gitignore`；批准后先保存 `git status`，只处理精确目标，再复验同一流程不重建。
- [x] 更新阶段六验收映射；任务 0042 与真实 Terminal.app 回归未完成前，阶段六保持 `In progress`。

## 局部验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest tests/contracts/test_models.py tests/verification/test_artifacts.py tests/verification/test_runner.py tests/tools/test_command_policy.py tests/runtime/test_safe_editing_flow.py tests/runtime/test_recovery_snapshots.py tests/persistence/test_recovery_snapshot.py tests/e2e/test_verification_artifact_isolation.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git diff --check
```

局部测试通过后再运行阶段六完整非 live、PTY、Textual Pilot、构建和 wheel smoke。真实 Xcode/Terminal.app 复验单独记录，不能由 Fake Process 或临时夹具代替。

## 提交边界

只在用户后续授权实施与提交时执行：

```bash
git add src/vera/contracts/verification.py src/vera/verification/artifacts.py src/vera/verification/runner.py src/vera/verification/__init__.py src/vera/runtime/engine.py src/vera/runtime/context.py src/vera/workspace/changeset.py src/vera/recovery/models.py src/vera/presentation/errors.py src/vera/cli_presenter.py src/vera/evals/runtime_factory.py src/vera/evals/corpus tests/contracts/test_models.py tests/verification/test_artifacts.py tests/verification/test_runner.py tests/tools/test_command_policy.py tests/runtime/test_safe_editing_flow.py tests/runtime/test_recovery_snapshots.py tests/runtime/test_recovery_resume.py tests/persistence/test_recovery_snapshot.py tests/e2e/test_verification_artifact_isolation.py tests/e2e/test_crash_recovery.py tests/e2e/test_phase_5_representative_projects.py tests/e2e/test_prompt_injection_adversarial.py tests/cli/fakes.py tests/fakes.py tests/evals docs/evals/phase-6-cli-product-acceptance.md docs/evals/phase-6-manual-walkthrough.md docs/STATUS.md docs/tasks/0042-verification-artifact-isolation.md docs/tasks/phase-6-execution-order.md
git commit -m "fix: isolate verification artifacts from workspaces"
```

不得把当前 0033 的未提交代码、阶段七规划文档或 `VeraTestDemo` 内容夹带进该提交。

## 完成定义

- 所有首版 Profile 生成的最终命令、环境语义和外部根均可审查、可哈希、可恢复。
- Xcode、SwiftPM、pytest 和 Mypy 的派生产物不留在临时测试工程中。
- 未规划/未知写入命令不启动；意外污染不自动清理用户证据。
- 当前 `VeraTestDemo/build` 只有在用户单独批准后才处理，处理范围和可恢复性有记录。
- 自动门禁与真实 Terminal.app Xcode 回归通过，阶段六无未关闭的同类 High 问题。

## 验证证据（2026-09-15）

- 分支：`phase-6/0042-verification-artifact-isolation`（起点 `25faf71`），未提交。
- 聚焦：上述 8 个测试文件 **106 passed**。
- `ruff check src tests`、`ruff format --check src tests`、`mypy src`、`git diff --check` 通过。
- 完整非 live：`919 passed, 2 deselected`；wheel smoke 两项因共享 `UV_CACHE_DIR=/private/tmp/vera-uv-cache` 缺少 `idna`/`pydantic_core` 的 `WHEEL` 元数据失败（安装期 os error 2），与本任务行为无关。
- 评测 corpus `verification-passes` / `in-flight-manual` 改为 `ruff check`；`forbidden-command` 在 propose 阶段失败关闭，不启动验证。
- 未读取真实 Provider Key，未跑 live，未改 `src/vera/terminal/`，未删除或取消暂存 `/Users/admin/Desktop/VeraTestDemo/build`。

## 未决

- 真实 Terminal.app 对 `VeraTestDemo` 的 Xcode 隔离回归未跑；既有 `build/` 仍为发现记录。
- 共享 uv cache 损坏导致两项既有 wheel smoke 无法在本机复跑；不把阶段六标为 Complete。
- 阶段六保持 In progress，不开始阶段七/八。
