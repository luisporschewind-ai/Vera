# Vera 验证产物隔离与工作区无污染

**状态：** Accepted
**日期：** 2026-09-14
**所属阶段：** 阶段 6——CLI 功能与可靠性收口

## 背景

真实 Terminal.app 走查中，Vera 在 `VeraTestDemo` 工程内执行了经用户批准的 `xcodebuild` 验证命令。命令本身没有修改源码，但 Xcode CLI 默认在工程根目录生成 `build/`，留下约 106 MB、354 个构建文件；由于该工程没有 `.gitignore`，其中 352 个文件还进入了 Git 暂存区。

这些文件是 Xcode 的标准构建产物，不是 Vera 私有状态；但触发原因是 Vera 选择并执行了未隔离输出位置的验证命令。现有审批只展示 `argv` 与 `cwd`，没有说明验证会在工作区产生哪些派生文件。这违反 Vera 的可检查修改边界：用户批准验证命令，不等于批准把未声明产物写入工程或纳入提交。

本规格把“验证不得静默污染用户工作区”提升为阶段六正确性与可靠性门禁。当前已经生成的 `VeraTestDemo/build` 视为用户工作区中的既存数据；Vera 和实施 Agent 不得因为识别出来源就自动删除、取消暂存或修改 `.gitignore`。

## 目标

- 验证命令的源码读取目录与派生产物目录分离；派生产物默认写入 Vera 拥有的工作区外临时根目录。
- 在 Change Set hash、PolicyEngine 分类和命令审批前生成最终验证计划；用户看到并批准的是实际执行语义，而不是随后被静默改写的命令。
- 首版支持日常所需的 Xcode、SwiftPM、pytest、Mypy、Ruff、Git 只读检查和 TypeScript no-emit 检查。
- 无法证明无工作区写入、也没有隔离 Profile 的命令失败关闭，不启动进程。
- 验证成功、失败、超时、取消和异常都清理本次精确创建的外部产物根；清理失败可检查、不会转而删除工作区文件。
- 通过结构化 Event 向 TUI、Plain、JSON 和未来桌面客户端报告隔离方式、最终命令、清理结果和意外工作区变化。

## 非目标

- 不提供通用容器、虚拟机或 OS 级文件系统沙箱；Vera 仍以当前系统用户执行进程。
- 不保证任意未知构建工具都能自动重写输出路径；未知工具先拒绝，再通过独立规格增加 Profile。
- 不自动删除现有 `build/`、`.build/`、`DerivedData/`、`dist/`、缓存或其他可能属于用户的数据。
- 不自动修改用户工程的 `.gitignore`、Xcode Build Location、Scheme、项目文件或 Git 暂存区。
- 不把“产物在 `.gitignore` 中”视为无污染；被忽略文件仍会占用空间并改变工作区状态。
- 不改变 Change Set 对源码文件的审批、Checkpoint 与回滚权威。

## 核心原则

### 1. 修改权威

Vera 运行期间，用户工作区中的持久修改只能来自：

1. 已批准并由 `ChangeApplier` 应用的 Change Set；或
2. 用户明确批准、且审批卡已列出预期工作区写入路径的非验证命令。

`VerificationCommand` 默认属于“读取源码、在外部生成产物”的验证语义。它不能借由命令审批获得未声明的工作区写权限。

### 2. 先计划，再哈希和审批

```text
模型提出 VerificationCommand
→ VerificationArtifactPlanner 选择 Profile
→ 生成带 artifact_plan 的最终 VerificationCommand（最终 argv + 隔离根 + Profile 环境语义）
→ 纳入 Change Set content_hash / RecoverySnapshot
→ PolicyEngine 分类
→ 用户查看并批准最终计划
→ VerificationRunner 原样执行计划
```

Planner 必须在 `ChangeSetBuilder.build()` 之前运行。Runner 不得在审批后自行添加、删除或重排影响命令语义的参数。若恢复时计划或隔离根绑定发生变化，旧审批过期，必须重新生成并批准。

### 3. 工作区外产物根

每条验证命令使用独立根目录：

```text
macOS: /private/tmp/vera-verification/<installation-prefix>/<run-id>/<index>/
其他平台: <system-temp>/vera-verification/<installation-prefix>/<run-id>/<index>/
```

- 根目录必须位于规范化 workspace 之外；若 `relative_to(workspace)` 成功则拒绝。
- `installation-prefix` 使用 installation id 的单向短摘要，不暴露原值。
- 父目录和本次根目录权限为 `0700`，拒绝符号链接与非目录占位。
- 路径由 `run_id + verification index` 确定，纳入计划和恢复证据。
- 只允许清理本次计划绑定的精确根目录；不得递归清理系统临时目录、用户 Home、workspace 或未解析变量。

## 首版 Profile

### Xcode

- `xcodebuild` 使用 scheme/workspace 或 scheme/project 时，在最终 argv 中加入 `-derivedDataPath <root>/DerivedData`。
- 只有 target、无法使用 `-derivedDataPath` 时，最终 argv 必须显式加入工作区外的 `SYMROOT`、`OBJROOT`、`SHARED_PRECOMPS_DIR` 和 `DSTROOT`；模块缓存通过受控环境指向 `<root>/ModuleCache`。
- 已提供输出参数时，Planner 验证每个路径都位于本次根目录内；指向 workspace、Home 或任意其他目录则拒绝，不静默覆盖。
- `CODE_SIGNING_ALLOWED=NO` 等原有构建语义保持原样。

### SwiftPM

- `swift build`、`swift test` 和等价 `xcrun swift` 形式使用 `--scratch-path <root>/swiftpm`。
- 原命令已经声明 `--scratch-path` 时，只接受本次隔离根内路径。

### Python

- `pytest` 与 `python -m pytest` 使用 `PYTHONDONTWRITEBYTECODE=1`、`PYTEST_ADDOPTS=-p no:cacheprovider` 和 `COVERAGE_FILE=<root>/.coverage`。
- `mypy` 使用 `--cache-dir <root>/mypy`。
- Planner 不接受会更新 golden、snapshot、coverage HTML、文档或源码的写入选项；这些输出必须另立已批准 Change Set 或 Profile。

### Ruff、Git 与 TypeScript 只读检查

- `ruff check` 与 `ruff format --check` 的最终 argv 强制包含 `--no-cache`，避免生成 `.ruff_cache`。
- `git diff --check` 与 `git status` 使用 `GIT_OPTIONAL_LOCKS=0`，避免可选的索引刷新写入；其他 Git 子命令不属于该 Profile。
- `tsc` 只有同时包含 `--noEmit --incremental false` 时可作为只读验证。
- `ruff --fix`、`git add/commit/checkout/reset/clean`、缺少 `--noEmit` 的 `tsc`、`npm run build` 与未知脚本不属于只读验证。

### 未支持命令

无法匹配上述 Profile 的命令返回 `verification_artifact_isolation_unavailable`，不进入系统进程表。错误必须包含可行动建议：选择已支持的 no-write 形式、补充隔离 Profile，或把预期文件写入改成单独 Change Set。

## 运行与清理

- `VerificationRunner` 只执行 `artifact_plan` 非空且校验通过的 `VerificationCommand`，不能执行未经规划的普通命令。Profile 与 root 唯一确定 Runner 注入的安全环境，因此环境语义也随命令进入 hash、快照和审批。
- 运行前记录工作区观察值；运行后对照 Git 状态与已知派生产物路径，作为防御性检测。检测不是自动删除授权。
- 如果发现未包含在已批准 Change Set 中的工作区新增或修改，验证结果为 `workspace_polluted`，Run 进入 `verification_failed`，Event 只列脱敏相对路径和数量。
- 发现污染后不得自动 `rm`、`git clean`、`git restore`、取消暂存或覆盖文件；向用户提供检查与明确清理建议。
- 外部产物根在 `passed`、`failed`、`timed_out`、`cancelled`、`rejected` 和 `error` 后都尝试清理。
- 清理失败时返回 `artifact_cleanup_failed` 和精确外部路径，Run 不得宣称完全成功；原工作区仍不得作为清理回退目标。

## 结构化契约

`VerificationCommand` 增加可选的版本化 `artifact_plan`，旧 v1 记录缺失该字段时按“未规划”读取，但不得在新运行中直接执行。

```python
class VerificationArtifactPlan(ContractModel):
    schema_version: Literal[1] = 1
    profile: Literal["xcode", "swiftpm", "pytest", "mypy", "ruff_no_cache", "git_readonly", "tsc_no_emit"]
    root: str | None = None
    cleanup: Literal["always"] = "always"

class VerificationCommand(ContractModel):
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = 120
    required: bool = True
    artifact_plan: VerificationArtifactPlan | None = None
```

`verification.started` 至少包含 `index`、最终 `argv`、`cwd`、`artifact_profile` 和脱敏后的 `artifact_root`；`verification.completed` 增加 `workspace_mutations`、`artifact_cleanup_status` 和失败 code。JSON 客户端使用字段，不解析中文文案。

## 失败行为

| 情况 | 行为 |
|---|---|
| 未匹配隔离 Profile | `verification_artifact_isolation_unavailable`，不启动进程 |
| 输出路径位于 workspace | `verification_output_inside_workspace`，不请求宽泛批准、不启动进程 |
| 隔离根是符号链接或权限不安全 | `verification_artifact_root_unsafe`，不启动进程 |
| 审批后计划或 workspace 事实变化 | 旧审批过期，重新规划与审批 |
| 验证意外写入 workspace | `workspace_polluted`，验证失败，保留文件等待用户处理 |
| 外部产物清理失败 | `artifact_cleanup_failed`，报告精确外部根，不清理 workspace |
| 恢复时外部根不存在 | 以同一绑定安全重建；绑定不一致则重新审批 |

## 验收标准

1. 在无 `.gitignore` 的临时 Xcode 工程执行 Vera 生成的验证计划后，工程根不出现 `build/`、`DerivedData/`、模块缓存或 `.dSYM`。
2. Xcode scheme 与 target 两种命令都把全部已知产物路径指向 workspace 外本次根目录。
3. SwiftPM、pytest 和 Mypy 不在工程内生成 `.build`、`.pytest_cache`、`__pycache__`、`.coverage` 或 `.mypy_cache`。
4. Ruff 不生成 `.ruff_cache`，Git 只读检查不获取可选锁；`ruff --fix`、写入型 Git、缺少 no-emit 的 `tsc`、`npm run build` 和未知命令不会被误标成只读。
5. 最终 argv 与 artifact plan 在 Change Set hash、RecoverySnapshot、PolicyEngine 和审批卡之间一致。
6. 用户拒绝审批、Run 取消、超时、失败和成功都只清理本次外部根。
7. 预先存在的用户 `build/`、dirty 文件、暂存区和 `.gitignore` 完全不被自动改变。
8. 意外 workspace 写入产生稳定结构化失败，既不伪装成功，也不自动清理证据。
9. TUI、Plain 和 JSON 都能区分“验证失败”“工作区污染”和“外部产物清理失败”。
10. 自动测试使用临时工程与 Fake Process，不修改 `~/Desktop/VeraTestDemo` 或任何真实用户工程。
11. 真实 Terminal.app 回归由用户批准清理测试工程后执行；同一 Xcode 验证不再重建工程内 `build/`。
12. 完整非 live、Ruff、格式、Mypy、构建、wheel smoke 与 `git diff --check` 通过。

## 关联

- [阶段六：CLI 功能与可靠性收口](2026-09-12-cli-productization-and-polish.md)
- [阶段五：Core 安全、权限与可靠性加固](2026-09-12-core-security-and-reliability-hardening.md)
- [ADR-0002：Command → VeraRuntime → Event](../decisions/ADR-0002-command-event-contract.md)
- [ADR-0007：统一 PolicyEngine 与策略指纹](../decisions/ADR-0007-unified-policy-engine.md)
- [ADR-0018：验证产物必须在审批前规划并隔离](../decisions/ADR-0018-isolate-verification-artifacts.md)
- [任务 0042：验证产物隔离与工作区无污染](../tasks/0042-verification-artifact-isolation.md)
