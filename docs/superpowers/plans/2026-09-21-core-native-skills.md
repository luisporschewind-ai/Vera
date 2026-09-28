# Core-native Skills 阶段九实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在 Vera Core 与 CLI 中交付一个受限的本地单 Skill 系统，使用户能够发现、审阅、显式选择、冻结、恢复和清除工作方法包，同时不扩大任何工具、权限、Workspace、网络或审批能力。

**当前阶段映射：** 现行路线中这是阶段九。原规格文件保留了 ADR-0020 接受时的旧阶段编号；本计划以 ADR-0021 校准后的“阶段八 Tools/Policy/Git → 阶段九 Skills → 阶段十桌面”为准。用户已明确授权：阶段八人工验收暂缓时，可以先实施阶段九；不因此把阶段八标记为 Complete，也不合并或删除已有分支/工作树。

**架构：** 新增 UI 无关的 `vera.skills` 控制面，分离 Manifest 解析、来源发现、Registry、显式 Selection、私有 Snapshot Store 和 Context 装配。公共结果只暴露 `SkillSummary`、`SkillSelection`、`SkillSnapshot` 与稳定错误；私有 Store 保存规范化 Manifest、冻结文件表和原始字节。Runtime 只在 Run 启动时绑定 Snapshot，之后从冻结副本装配带 provenance 的 Context；所有既有 Tool/Policy/Approval/Verification/Checkpoint/Recovery 权威保持不变。

**技术栈：** Python 3.12、Pydantic 2、严格 TOML/UTF-8 解析、现有 `PrivateAtomicWriter`、`EventJournal`、`SessionStore`、`RecoverySnapshot`、`ContentEnvelope`、Typer/Textual/Plain/JSON 客户端、pytest、PTY。

**规格：** `docs/specs/2026-09-15-core-native-skills-system.md`、`docs/decisions/ADR-0020-stage-core-native-skills.md`、`docs/decisions/ADR-0021-core-tools-before-desktop.md`。

## 全局约束

- v1 只支持 `builtin`、`user`、`workspace` 三种本地来源，不访问网络，不实现远程安装、市场、评分、支付、自动更新或远程执行。
- v1 只允许用户显式选择一个主 Skill；不实现自动候选、多 Skill 组合、依赖解析或 Multi-Agent。
- Skill 包只读取 `skill.toml`、`SKILL.md` 和 Manifest 明确声明的 `references/`、`templates/` UTF-8 普通文件；不执行任何包内脚本。
- `workspace` Skill 永远是 `untrusted`；`builtin` 与 `user` 也只能是 `advisory`，任何来源都不能成为 `builtin_policy`。
- Skill 内容不能注册 Tool、扩大 Workspace、改变 Policy/Approval、读取 Provider Key、声明网络、绕过 FileMutationPlan、Verification、Checkpoint 或 Recovery。
- Manifest 使用严格封闭 Schema；拒绝未知字段、非法 SemVer、绝对路径、`.`、`..`、NUL、重复规范路径、规范化冲突、符号链接、特殊文件和越界路径。
- 单包最多 32 个文件；`SKILL.md` 与每个资源最多 64 KiB；冻结和装配总内容最多 128 KiB；超限或非法 UTF-8 直接失败，不静默截断。
- `snapshot_id` 必须绑定格式版本、`skill_id`、来源、规范化 Manifest、排序后的文件表、长度和原始字节；绝对源路径不得进入公共身份或公共 Event/Journal。
- Snapshot 写入 `<state_dir>/skills/snapshots/sha256/<digest>/`，目录 `0700`、文件 `0600`，先写私有临时目录并 fsync，再原子发布。
- Run 与恢复只读取冻结 Snapshot；原始包修改、移动或删除不能改变活动 Run；Snapshot 缺失、损坏或未知版本必须停止，不回退读取原包。
- 最后一个权威引用消失后至少保留 30 天；引用不确定、元数据损坏或路径校验失败时拒绝清理并保留数据。
- 未选择 Skill 的普通 Run 必须保持 `NoSkill` 行为：不扫描 Skill 目录、不创建 Snapshot、不注入 Context、不新增 Skill Event/Journal 事实。
- 所有新公共契约、Event、错误和 Session 记录必须 additive；旧 Run、旧 Journal、旧 RecoverySnapshot 和旧三客户端行为继续可读。

## 文件与边界总览

### 新增 Core 模块

- `src/vera/skills/models.py`：内部规范化 Manifest、来源、文件事实、候选和冻结记录。
- `src/vera/skills/manifest.py`：严格 TOML/Manifest/资源路径/版本兼容性解析。
- `src/vera/skills/discovery.py`：三种允许来源根的非递归安全发现，不跟随符号链接。
- `src/vera/skills/registry.py`：生成 `SkillSummary`、处理来源内唯一性、跨来源冲突和稳定排序。
- `src/vera/skills/selection.py`：显式选择、完整 `skill_id` 消歧、`none` 状态和稳定原因码。
- `src/vera/skills/snapshot_store.py`：冻结、加载、校验、引用扫描、30 天宽限和精确清理。
- `src/vera/skills/context.py`：从冻结 Snapshot 按规范顺序读取内容并生成受限 `ContentEnvelope`。

### 现有公共/控制面文件

- `src/vera/contracts/skills.py`、`src/vera/contracts/errors.py`、`src/vera/contracts/compatibility.py`：公共契约、稳定错误码和兼容性清单。
- `src/vera/persistence/private_writer.py`、`src/vera/persistence/recovery_snapshot.py`、`src/vera/persistence/session_store.py`：沿用现有私有写入、恢复和会话持久化边界。
- `src/vera/runtime/context.py`、`src/vera/runtime/engine.py`、`src/vera/runtime/prompts.py`：Run 绑定、Snapshot 恢复和 Context 注入。
- `src/vera/bootstrap.py`、`src/vera/config.py`：服务注册、Skills 根目录和状态目录配置。
- `src/vera/session/command_catalog.py`、`src/vera/session/controller.py`、`src/vera/session/models.py`、`src/vera/cli_presenter.py`、`src/vera/cli_json_session.py`、`src/vera/cli_plain_session.py`、`src/vera/presentation/event_copy.py`、`src/vera/presentation/projector.py`：CLI 与三客户端结构化投影。

### 规划期只新增、不改产品实现

- `docs/tasks/0067-skill-discovery-contracts.md`、`docs/tasks/0068-skill-snapshots.md`、`docs/tasks/0069-skill-runtime-context.md`、`docs/tasks/0070-skill-cli-projection.md`、`docs/tasks/0071-skill-compatibility.md`、`docs/tasks/0072-phase-9-skills-acceptance.md`：阶段九正式任务记录，待本计划确认后按任务分别建立。
- `docs/evals/phase-9-core-native-skills.md`：自动矩阵、安装态、PTY、Terminal.app 和两个真实工程证据。
- `docs/STATUS.md`、`docs/ROADMAP.md`、`docs/tasks/phase-9-execution-order.md`：只在任务 0072 验收收口时更新；不得在计划阶段提前把阶段九标为 Complete。

## Review Focus

以下五类最容易出现“名义通过、真实越界”的问题；每类都必须有归属任务的失败测试：

1. **源包竞态与路径穿越：** `skill.toml` 或资源在两次 stat/read 之间变化、符号链接替换、`..`/绝对路径和 Unicode 规范化冲突时，必须拒绝且不留下半成品 Snapshot。由任务 0067、0068 覆盖。
2. **不可信 Skill 权限升级：** workspace `SKILL.md` 诱导 sudo、读取 Key、声明网络、注册 Tool 或跳过审批时，只能作为 `untrusted` Context，不能改变 PolicyDecision。由任务 0069 覆盖。
3. **Snapshot 与原始源脱钩：** Run 开始后修改、删除或移动原始包，继续运行和恢复必须读取同一冻结字节；缺失/损坏 Snapshot 必须停止。由任务 0068、0069 覆盖。
4. **选择与身份混淆：** 同名跨来源、非法 Manifest、版本不兼容和 `name`/`skill_id` 混用时，不得静默选择另一个候选。由任务 0067、0070 覆盖。
5. **公共证据泄漏：** Event、Journal、SessionRecord、错误、Plain/JSON/TUI 输出不能包含完整 Skill 正文、模板、完整用户目标、Provider Key 或私有绝对路径。由任务 0069、0070、0071 覆盖。

## 任务拆分与执行顺序

任务严格按 `0067 → 0068 → 0069 → 0070 → 0071 → 0072` 串行执行。每项先写 Red 测试，再写最小实现；每项结束都运行局部门禁、`git diff --check` 并创建一个独立本地提交。所有实现使用新的阶段九隔离工作树；现有 `main`、阶段八工作树、阶段五/七规划工作树和本规划工作树全部保留。

### Task 1 — 0067：Skill Manifest、Discovery、Registry 与公共契约

**交付：** 能安全发现三种来源的候选，并为有效、冲突、非法、不兼容包生成确定的 `SkillSummary`；尚不接入 Runtime 或 CLI。

**文件：**

- Create: `src/vera/contracts/skills.py`, `src/vera/skills/__init__.py`, `src/vera/skills/models.py`, `src/vera/skills/manifest.py`, `src/vera/skills/discovery.py`, `src/vera/skills/registry.py`
- Modify: `src/vera/contracts/errors.py`, `src/vera/contracts/compatibility.py`, `src/vera/config.py`
- Test: `tests/contracts/test_skills.py`, `tests/skills/test_manifest.py`, `tests/skills/test_discovery.py`, `tests/skills/test_registry.py`

**接口：**

- `ManifestLoader.load(package_root: Path) -> ParsedSkillPackage`
- `SkillDiscovery.discover(workspace_root: Path) -> tuple[SkillCandidate, ...]`
- `SkillRegistry.summaries(workspace_root: Path) -> tuple[SkillSummary, ...]`
- `SkillRegistry.resolve(selector: str, workspace_root: Path) -> SkillSelection`
- 公共模型：`SkillSummary`、`SkillSelection`、`SkillSnapshot`；内部模型不得把包正文放入公共模型。

- [ ] **Step 1：建立 Manifest Red 测试**：固定示例 Manifest、未知字段、非法版本、非法名称、缺失 `SKILL.md`、资源重复规范路径、绝对路径、`..`、NUL、符号链接和超限输入。
- [ ] **Step 2：运行 Red**：`uv run pytest tests/contracts/test_skills.py tests/skills/test_manifest.py -q`；预期因 `vera.skills` 和公共模型不存在而失败。
- [ ] **Step 3：实现严格解析**：使用 `tomllib` 与显式 Pydantic 模型；规范化但不跟随资源符号链接；只允许规格定义字段和三种资源根；不读取未声明文件。
- [ ] **Step 4：建立 Discovery/Registry Red 测试**：覆盖 builtin/user/workspace 根、缺失根、同名冲突、invalid/incompatible、稳定排序和不暴露绝对路径。
- [ ] **Step 5：实现发现与摘要**：`SkillDiscovery` 只扫描允许根的直接子目录；`SkillRegistry` 生成 `available/conflict/invalid/incompatible`，冲突不静默覆盖。
- [ ] **Step 6：实现选择消歧**：裸名称仅在全局规范名唯一时成功；完整 `builtin:name`/`user:name`/`workspace:name` 可消歧；失败返回稳定 reason code，不回退到其他来源。
- [ ] **Step 7：注册错误与兼容清单**：加入规格中的稳定错误码，标记新契约和 Event 为 additive；保留旧 decoder 行为。
- [ ] **Step 8：运行局部门禁并提交**：`uv run pytest tests/contracts/test_skills.py tests/skills/test_manifest.py tests/skills/test_discovery.py tests/skills/test_registry.py -q`、Ruff、format、Mypy、`git diff --check`；提交 `feat: add core skill discovery contracts`。

### Task 2 — 0068：SkillSnapshotStore、原子冻结与安全清理

**交付：** 能把已解析 Skill 冻结为内容寻址 Snapshot，并在源变化、损坏、恢复和清理场景下失败关闭。

**文件：**

- Create: `src/vera/skills/snapshot_store.py`, `src/vera/skills/snapshot_codec.py`
- Modify: `src/vera/persistence/private_writer.py`, `src/vera/persistence/recovery_snapshot.py`, `src/vera/contracts/recovery.py`, `src/vera/contracts/errors.py`
- Test: `tests/skills/test_snapshot_store.py`, `tests/skills/test_snapshot_cleanup.py`, `tests/persistence/test_skill_snapshot_codec.py`, `tests/recovery/test_skill_snapshot_recovery.py`

**接口：**

- `SkillSnapshotStore.freeze(package: ParsedSkillPackage, *, state_dir: Path) -> FrozenSkillSnapshot`
- `SkillSnapshotStore.load(snapshot_id: str, *, state_dir: Path) -> FrozenSkillSnapshot`
- `SkillSnapshotStore.scan_references(runs: ..., sessions: ...) -> SnapshotReferenceReport`
- `SkillSnapshotStore.collect(now: datetime, references: SnapshotReferenceReport) -> SnapshotCleanupReport`
- `FrozenSkillSnapshot.context_files() -> tuple[FrozenSkillFile, ...]`

- [ ] **Step 1：写冻结 Red 测试**：固定 Snapshot hash 输入顺序、同内容同来源复用、不同来源身份不同 hash、目录/文件权限和公共描述不含正文。
- [ ] **Step 2：写失败关闭测试**：覆盖源文件竞态、符号链接替换、特殊文件、权限失败、非法 UTF-8、超限、磁盘写入失败和半成品清理。
- [ ] **Step 3：实现规范化文件快照与 hash**：按相对路径排序，绑定格式版本、来源身份、Manifest、长度和原始字节；绝不把绝对源路径放入 `snapshot_id`。
- [ ] **Step 4：实现原子发布**：复用 `PrivateAtomicWriter` 的 0700/0600 与 fsync 语义，先写 `<state_dir>/skills/snapshots/sha256/.tmp-*`，校验后原子发布到精确 digest 目录。
- [ ] **Step 5：写 Codec/恢复 Red 测试**：缺失、损坏、未知版本、hash 不匹配时返回稳定错误；RecoverySnapshot 只保存 `snapshot_id` 和公共事实，不保存正文。
- [ ] **Step 6：实现加载与恢复绑定**：`load()` 重新验证格式、目录权限、文件 hash 和文件类型；不允许恢复时读取当前原始 Skill 包。
- [ ] **Step 7：实现引用扫描和宽限清理**：从权威 Run/Session 记录计算引用；活动/可恢复引用永不删除；无引用至少 30 天后才尝试精确清理；不确定时返回 `skill_snapshot_cleanup_refused`。
- [ ] **Step 8：运行局部门禁并提交**：覆盖存储、Codec、恢复、清理测试和现有 persistence/recovery 回归；提交 `feat: add immutable skill snapshots`。

### Task 3 — 0069：Session Selection、Run 绑定与 Context 装配

**交付：** 用户选择只影响下一次 Run；Run 开始前冻结并绑定 Snapshot，Context 只读取冻结文本；`NoSkill` 和不可信内容边界保持安全。

**文件：**

- Create: `src/vera/skills/selection.py`, `src/vera/skills/context.py`
- Modify: `src/vera/runtime/context.py`, `src/vera/runtime/engine.py`, `src/vera/runtime/prompts.py`, `src/vera/runtime/state.py`, `src/vera/persistence/recovery_snapshot.py`, `src/vera/session/models.py`, `src/vera/session/controller.py`, `src/vera/bootstrap.py`
- Test: `tests/skills/test_selection.py`, `tests/skills/test_context.py`, `tests/runtime/test_skills.py`, `tests/runtime/test_skill_recovery.py`, `tests/session/test_skill_selection.py`

**接口：**

- `SkillSelectionService.select(selector: str, workspace_root: Path) -> SkillSelection`
- `SkillSelectionService.clear() -> SkillSelection`
- `SkillContextAssembler.assemble(snapshot: FrozenSkillSnapshot) -> tuple[ContentEnvelope, ...]`
- `VeraRuntime._bind_skill_snapshot(context: RunContext) -> Iterator[EventEnvelope]`
- `RunContext.skill_snapshot: SkillSnapshot | None`

- [ ] **Step 1：写 Session Red 测试**：设置、清除、重启恢复、同名冲突、活动 Run 不被后续 clear 改变；选择失败保留用户输入。
- [ ] **Step 2：实现选择持久化**：增加版本化 `skill.selection.changed` 事实和会话记录；选择状态是“下一次 Run”意图，不伪装成活动 Snapshot。
- [ ] **Step 3：写 Context Red 测试**：固定 `SKILL.md → references → templates` 顺序、provenance、advisory/untrusted trust、总大小限制和正文不进入公共事件。
- [ ] **Step 4：实现 Context 装配**：只从 Snapshot Store 读取；使用现有 `ContentEnvelope`/投毒检测链；任何 Skill 文本只能以受限 user/tool context 注入，不能成为 system policy。
- [ ] **Step 5：写 Runtime 绑定 Red 测试**：成功 Run 产生 `skill.snapshot.bound`；冻结失败不创建半初始化 Run；源包 Run 中修改后后续模型请求仍看到旧 Snapshot。
- [ ] **Step 6：接入 Runtime 与 Recovery**：在 Run 启动阶段选择、冻结、绑定 Snapshot；把 `snapshot_id` 写入 RunContext/RecoverySnapshot；恢复只加载 Snapshot，不重新 discovery。
- [ ] **Step 7：写 `NoSkill` 回归**：默认 Run 不扫描三类 Skill 根、不创建 Snapshot、不产生 Skill Event/Journal、不改变消息顺序、Tool/Policy/Approval 和旧 Recovery。
- [ ] **Step 8：写恶意 Skill 回归**：Skill 文本声称 sudo、读取 Key、网络、Tool 注册或跳过审批时，Policy/Approval 结果必须与未加载权限时相同或更严格。
- [ ] **Step 9：运行局部门禁并提交**：运行 Skills、Runtime、Recovery、Session 及现有 `tests/runtime/test_untrusted_context.py` 等回归；提交 `feat: bind skills to recoverable runs`。

### Task 4 — 0070：CLI 命令与 TUI/Plain/JSON 结构化投影

**交付：** 三种客户端都能发现、查看、选择、清除和显示 Skill 状态，消费同一 Core 事实，不解析人类文案判断成功。

**文件：**

- Modify: `src/vera/session/command_catalog.py`, `src/vera/session/controller.py`, `src/vera/session/status.py`, `src/vera/cli_presenter.py`, `src/vera/cli_plain_session.py`, `src/vera/cli_json_session.py`, `src/vera/presentation/event_copy.py`, `src/vera/presentation/projector.py`, `src/vera/contracts/compatibility.py`
- Test: `tests/session/test_skill_commands.py`, `tests/cli/test_skill_commands.py`, `tests/presentation/test_skill_projection.py`, `tests/e2e/test_skill_client_parity.py`, `tests/pty/test_skills.py`

**接口：**

- `/skills` → `SkillSummary[]`
- `/skills show <name|skill_id>` → `SkillSummary` + 安全 Manifest/resource facts
- `/skills use <name|skill_id>` → `skill.selection.changed`
- `/skills clear` → `skill.selection.changed(mode=none)`
- `/status` → pending `SkillSelection` 与 active `SkillSnapshot` 分栏展示

- [ ] **Step 1：写 CommandCatalog Red 测试**：命令、参数、补全、未知 selector、冲突和错误码均有结构化结果。
- [ ] **Step 2：注册命令与 Controller 路由**：只通过 SkillService 调用 Discovery/Registry/Selection；普通启动和普通 Run 不隐式扫描 Skill。
- [ ] **Step 3：写三客户端 parity 测试**：同一 Summary/Selection/Snapshot/Error 在 TUI、Plain、JSON 中字段和状态一致；JSON 无 ANSI，不含正文和绝对路径。
- [ ] **Step 4：实现 presenter/projector**：新增人类可读标题、来源、trust、version、hash 前缀和 reason code；`SKILL.md`、模板和私有 Store 路径不直接展开。
- [ ] **Step 5：写 PTY 60×16/80×24 测试**：列表、冲突、选择、清除、Snapshot 绑定和失败状态都可读，不依赖颜色或终端宽度。
- [ ] **Step 6：更新 CompatibilityManifest**：增加命令、Event、错误和 Session 记录为 additive；旧客户端遇到未知 Skill 事实仍可继续渲染。
- [ ] **Step 7：运行局部门禁并提交**：运行 Session/CLI/Presentation/PTY/parity 测试和静态检查；提交 `feat: expose core skills through cli clients`。

### Task 5 — 0071：NoSkill、兼容迁移与安装态整合

**交付：** 证明 Skills 是可选控制面，不破坏旧 Run/Journal/Session/Recovery；安装 wheel 后仍能使用无 Skill 与显式 Skill 路径。

**文件：**

- Modify: `src/vera/persistence/session_codec.py`, `src/vera/persistence/session_store.py`, `src/vera/persistence/recovery_snapshot.py`, `src/vera/persistence/snapshot_codec.py`, `src/vera/bootstrap.py`, `scripts/smoke_installed_wheel.py`
- Test: `tests/persistence/test_skill_compatibility.py`, `tests/runtime/test_no_skill_compatibility.py`, `tests/e2e/test_skill_installation.py`, `tests/e2e/test_skill_recovery.py`

- [ ] **Step 1：写旧状态回归**：加载不含 Skill 字段的 session/journal/recovery fixture，断言字段默认 none、旧 hash 不变、旧 decoder 不拒绝。
- [ ] **Step 2：写安装态 Red 测试**：从 wheel 运行 `/skills`、NoSkill Run、显式 user/workspace Skill、源包修改后恢复和 Snapshot 缺失拒绝。
- [ ] **Step 3：实现兼容迁移与 bootstrap**：只增加可选 decoder 字段和 SkillService 依赖；不存在 Skill 根时不创建目录、不产生写入。
- [ ] **Step 4：实现 installed-wheel smoke**：复用现有无 Provider Key、外部 workspace/state 和 workspace 外产物约束；验证公共输出不泄漏 Skill 正文。
- [ ] **Step 5：运行完整非 live 门禁**：`uv run pytest -m 'not live' -q`、Ruff、format、Mypy、`uv build --wheel --sdist`、installed wheel smoke、`git diff --check`。
- [ ] **Step 6：提交兼容收口**：提交 `fix: preserve no-skill compatibility in installed clients`。

### Task 6 — 0072：阶段九自动验收、真实 dogfood 与阶段收口

**交付：** 形成可审阅的阶段九验收记录。自动证据只能达到 `Ready for manual acceptance`；真实 Terminal.app、Python/Swift 工程和用户确认后才允许阶段九 Complete。

**文件：**

- Create: `tests/e2e/test_phase_9_skills.py`, `tests/e2e/test_phase_9_no_skill.py`, `tests/e2e/test_phase_9_client_parity.py`, `tests/pty/test_phase_9_skills.py`, `docs/evals/phase-9-core-native-skills.md`
- Modify after evidence: `docs/tasks/0067-skill-discovery-contracts.md`, `docs/tasks/0068-skill-snapshots.md`, `docs/tasks/0069-skill-runtime-context.md`, `docs/tasks/0070-skill-cli-projection.md`, `docs/tasks/0071-skill-compatibility.md`, `docs/tasks/0072-phase-9-skills-acceptance.md`, `docs/tasks/phase-9-execution-order.md`, `docs/STATUS.md`, `docs/ROADMAP.md`

- [ ] **Step 1：建立离线矩阵**：覆盖三来源、Manifest 失败、冲突/消歧、路径/竞态、Snapshot、恢复、清理、恶意 workspace Skill、NoSkill 和三客户端 parity；全部使用临时 workspace/state/Fake Model。
- [ ] **Step 2：运行 Red 并回归到归属任务**：任何失败必须回到 0067–0071 修复，不在验收任务堆旁路逻辑。
- [ ] **Step 3：运行 PTY 矩阵**：60×16 与 80×24 覆盖 `/skills`、`show/use/clear/status`、冲突、错误、Snapshot 绑定和恢复。
- [ ] **Step 4：运行安装态 wheel smoke**：仓库外安装 wheel，验证 NoSkill、user Skill、workspace Skill、Snapshot 变化和失败关闭；清除 Provider Key 与网络依赖。
- [ ] **Step 5：记录完整自动门禁**：精确记录 passed、deselected、warnings、构建和未运行 live；区分 Verified、Blocked、Not run、Assumption。
- [ ] **Step 6：准备真实人工验收清单**：Terminal.app 完成发现、show、use、clear、status、失败和恢复；Python 与 Swift/Xcode 安全副本完成至少一次显式 Skill dogfood，验证工程根和产物隔离。
- [ ] **Step 7：自动证据收口**：缺人工证据时将 0072 和阶段九写为 `Ready for manual acceptance`，不写 Complete。
- [ ] **Step 8：用户确认后再更新状态**：只有用户明确接受阶段九结果，才把任务/阶段标为 Done/Complete；阶段十桌面仍需独立进入规划，不自动引入 Electron。
- [ ] **Step 9：提交文档收口**：在用户确认后创建 `docs: record phase nine skills acceptance` 本地提交；不 push、不删除任何旧分支或工作树。

## 共同门禁

每个实现任务至少运行：

```bash
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/private/tmp/vera-uv-cache \
  env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY \
  VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file \
  uv run pytest -m 'not live' -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git diff --check
```

任务 0070/0072 追加 PTY；任务 0071/0072 追加 wheel/sdist 和仓库外安装态 smoke。任何网络、Provider Key、桌面工程原目录或用户已有工作树都不进入自动测试。

## 计划自审结果

- 规格覆盖：Manifest/来源/冲突由 0067；Snapshot/恢复/清理由 0068；Selection/Context/权限边界/NoSkill 由 0069；CLI 与三客户端由 0070；旧状态和安装态由 0071；完整矩阵与人工验收由 0072。
- 阶段边界：本计划只定义 Skills Core 与 CLI，不实现 Plugin、Hook、远程分发、桌面、Multi-Agent 或脚本执行。
- 兼容边界：旧状态默认 `NoSkill`，新字段/Event/命令 additive，恢复不读取可变原包。
- 分支边界：阶段八工作树、主线和其他规划工作树均保留；阶段九实现必须使用独立工作树，不能在已有阶段八或规划工作树中混合产品代码。
- 当前状态：本文件是实施计划，不代表阶段九已经 Complete，也不替代后续每个任务的 Red/Green 验证和用户验收。
