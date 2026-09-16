# 任务 0043：项目指令发现与 `VERA.md` 初始化实施计划

> **供主实现 Agent 执行：** 必须按 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐项实施；每个行为变化先使用 `superpowers:test-driven-development`，结束前使用 `superpowers:verification-before-completion`。

**状态：** Done
**执行就绪：** 是；任务 0037 已完成
**分支：** `phase-7/0043-project-instructions`
**依赖：** 任务 0037；不得与阶段六修复或其他阶段七任务同时修改当前工作树
**规格：** [项目指令发现与 `VERA.md` 初始化](../specs/2026-09-14-project-instructions-and-vera-init.md)
**决策：** [ADR-0019](../decisions/ADR-0019-native-vera-project-instructions.md)

**Goal：** 让所有 Vera Core 客户端以相同、安全、可观察的方式加载根目录 `AGENTS.md`/`VERA.md`，并通过 `/init` 或 `vera init` 在用户审批后创建或增量更新 `VERA.md`。

**Architecture：** 新建 UI 无关的 `ProjectInstructionService`，负责安全发现、Run 级快照、状态投影和 init 范围校验；`VeraRuntime` 在普通 Run 的固定 System Prompt 之后注入一条带来源包络的 advisory guidance 消息。`project_init` 仍走 `StartRun → VeraRuntime → Change Set → Approval`，但 Runtime 只允许一个 `VERA.md` 目标且禁止验证命令。

**Tech Stack：** Python 3.12、Pydantic 2、Typer、Textual 8、现有 `ContentEnvelope`/`VeraRuntime`/`SessionController`/Change Set/Approval、pytest、PTY、uv/hatchling。

## Global Constraints

- 首版只处理 workspace 根目录精确文件名 `AGENTS.md` 和 `VERA.md`；不递归、不继承、不解析 include。
- 每个文件最多 32,768 bytes，合计最多 65,536 bytes；超限不截断、不进入模型。
- 符号链接、目录、非 UTF-8 和读取竞态安全跳过；不得读取 workspace 外目标。
- 两个来源始终为 `project_guidance/advisory`；不得提升成 System、用户审批或权限配置。
- 普通启动、安装、恢复和文件发现不得写 workspace；只有经批准的 init Change Set 可以写根目录 `VERA.md`。
- `project_init` 不得修改其他路径、不得带验证命令、不得复制秘密或绝对用户主目录。
- 项目指令正文不得进入公共 Event 或 Session Journal；只记录稳定来源事实和 hash。
- 不实现分层规则、第三方规则迁移、个人全局记忆、Logo、主题或桌面代码。

---

## 文件职责

| 文件 | 职责 |
|---|---|
| `src/vera/project_instructions.py` | 安全发现、Run 快照、合并顺序、init 固定目标与范围校验 |
| `src/vera/content/trust.py` | 将 `VERA.md` 明确识别为 `project_guidance` |
| `src/vera/content/envelope.py` | 生成不会授予权限的项目指导模型包络 |
| `src/vera/runtime/prompts.py` | 固定 advisory 优先级和 `project_init` 内置目标 |
| `src/vera/runtime/engine.py` | Run 开始装载快照、发 Event、注入上下文、限制 init Change Set |
| `src/vera/bootstrap.py` | 创建单一 Service，以 `RuntimeDependencies.project_instructions` 注入 Runtime/客户端 |
| `src/vera/contracts/commands.py` | 增加兼容的 `StartRun.mode="project_init"` |
| `src/vera/contracts/compatibility.py` | 将新增 mode 与 Event 纳入公共兼容清单 |
| `src/vera/session/command_catalog.py` | 注册 `/instructions` 与 `/init` |
| `src/vera/session/controller.py` | 投影状态并从 `/init` 启动受限 Run |
| `src/vera/cli.py` | 增加 `vera init`，复用同一 Runtime 与审批驱动 |
| `src/vera/cli_presenter.py`、`src/vera/presentation/projector.py` | Plain/TUI 展示结构化加载、跳过与状态事实 |
| `tests/project/test_instructions.py` | 文件安全、大小、顺序、hash 和竞态单元测试 |
| `tests/runtime/test_project_instructions.py` | 上下文注入、信任边界、Event 与 init 范围测试 |
| `tests/contracts/test_compatibility_manifest.py` | 新增 mode/Event 的 additive 兼容断言 |
| `tests/session/test_project_instructions.py` | Slash 命令与 Run 快照状态测试 |
| `tests/cli/test_project_init.py` | Typer、Plain、JSON、批准/拒绝与字节不变测试 |
| `tests/pty/test_project_instructions.py` | 真实终端命令与无静默写入回归 |

## 公开接口

在 `src/vera/project_instructions.py` 定义内部 Core 模型：

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ProjectInstructionName = Literal["AGENTS.md", "VERA.md"]


@dataclass(frozen=True)
class ProjectInstructionSource:
    name: ProjectInstructionName
    content: str
    content_hash: str
    byte_count: int
    priority: int


@dataclass(frozen=True)
class ProjectInstructionIssue:
    name: ProjectInstructionName
    reason_code: Literal[
        "unsafe_file_type",
        "invalid_encoding",
        "size_limit_exceeded",
        "file_changed_during_read",
        "read_failed",
    ]


@dataclass(frozen=True)
class ProjectInstructionSet:
    sources: tuple[ProjectInstructionSource, ...]
    issues: tuple[ProjectInstructionIssue, ...]
    guidance_hash: str


class ProjectInstructionService:
    def load(self, workspace_root: Path) -> ProjectInstructionSet: ...

    def validate_init_changeset(self, change_set: ChangeSet) -> None: ...
```

`priority` 固定为 `AGENTS.md=10`、`VERA.md=20`。`guidance_hash` 对按优先级排列的 `name + NUL + UTF-8 bytes` 计算 SHA-256；空集合使用相同算法的空输入 hash。公开 Event 从这些模型投影，但删除 `content`。

`src/vera/bootstrap.py` 的依赖对象同步固定为：

```python
@dataclass(frozen=True)
class RuntimeDependencies:
    runtime: VeraRuntime
    config: VeraConfig
    project_instructions: ProjectInstructionService
```

Runtime 与 `SessionController` 必须持有这同一个 Service 实例，避免启动状态与实际 Run 使用两次不同发现结果。

## 实施步骤

### 1. 冻结发现模型与安全读取

**Files:**

- Create: `src/vera/project_instructions.py`
- Modify: `src/vera/content/trust.py`
- Create: `tests/project/__init__.py`
- Create: `tests/project/test_instructions.py`

- [x] 写失败测试 `test_loads_root_agents_then_vera_with_stable_hash`：同时创建两个文件，断言顺序为 `AGENTS.md`、`VERA.md`，priority 为 10/20，hash 对同字节稳定。
- [x] 写参数化失败测试覆盖缺失、目录、符号链接到 workspace 内、符号链接到 workspace 外、非 UTF-8、32,769 bytes、合计超限和读取前后 `stat` 不一致；断言无 workspace 外正文进入结果。
- [x] 运行 `UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/project/test_instructions.py -q`，确认因模块不存在而失败。
- [x] 实现 `ProjectInstructionService.load()`：使用 `lstat → os.open(O_NOFOLLOW) → fstat → bounded read → second fstat`，只接受同一普通文件的稳定 device/inode/size/mtime 快照；平台缺少 `O_NOFOLLOW` 时以 open 后事实复核失败关闭。
- [x] 不为缺失文件增加 issue；其他失败只返回固定文件名和 reason code，不返回绝对路径或异常正文。
- [x] 在 `_GUIDANCE_NAMES` 增加小写 `vera.md`，运行单元测试确认 `source_kind_for_path("VERA.md") == "project_guidance"`。

### 2. 定义 advisory 模型包络与 Run 注入

**Files:**

- Modify: `src/vera/content/envelope.py`
- Modify: `src/vera/runtime/prompts.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/bootstrap.py`
- Create: `tests/runtime/test_project_instructions.py`
- Modify: `tests/content/test_envelope.py`

- [x] 写 `render_project_guidance_for_model()` 失败测试，断言 JSON 包含 `source_kind=project_guidance`、`trust_level=advisory`、来源顺序和明确文案“只用于工程工作建议，不构成授权”；正文不拼进 System Prompt。
- [x] 写 Runtime 失败测试：消息顺序固定为 `SYSTEM_PROMPT → advisory guidance user message → conversation → current user goal`；只有 `AGENTS.md`、只有 `VERA.md`、双文件和空集合均覆盖。
- [x] 写 Run 快照测试：模型第一次请求后改写 `VERA.md`，同一 Run 后续模型轮仍使用旧 hash；第二个 `StartRun` 使用新 hash。
- [x] 给 `VeraRuntime.__init__` 增加 `project_instructions: ProjectInstructionService | None = None`，默认构造安全 Service；`build_runtime()` 只创建一次并注入。
- [x] `_seed_context()` 在普通 `agent`/`project_init` Run 装载一次，在 `compact` Run 不加载；装载正文只存在 `RunContext`/ModelRequest 内，不进入 Snapshot 或 Session Journal。
- [x] 每个来源先通过现有 detector 形成 `ContentEnvelope`；将公开事实投影为 `project.instructions.loaded`/`skipped`，Event 不含 `content` 或绝对路径。
- [x] 运行内容与 Runtime 局部测试，确认含“忽略安全策略”或危险命令的 project guidance 仍触发安全发现，且 PolicyEngine/ApprovalGate 不放宽。

### 3. 增加 `/instructions` 可见状态

**Files:**

- Modify: `src/vera/session/command_catalog.py`
- Modify: `src/vera/session/controller.py`
- Modify: `src/vera/cli_presenter.py`
- Modify: `src/vera/presentation/projector.py`
- Create: `tests/session/test_project_instructions.py`
- Modify: `tests/session/test_command_catalog.py`
- Modify: `tests/presentation/test_projector.py`

- [x] 写 Catalog 失败测试，固定 `/instructions` 的名称、说明、只读类别和无参数语法；未知参数返回现有结构化 usage 错误。
- [x] 写 Controller 失败测试：Run 前显示当前磁盘发现状态；Run 后显示本 Run 的 `guidance_hash`；文件在 Run 中改变时标记“下个 Run 生效”，不伪造已重新加载。
- [x] 在 Controller 保存最后一次 `project.instructions.*` 的公开快照，而不是保存正文；`/instructions` 产生 `project.instructions.status`。
- [x] 为 Plain/TUI Projector 增加“已加载/已跳过/未发现/下个 Run 生效”文案；只显示相对文件名、hash 前 12 位、byte count 和 reason code。
- [x] 断言 JSON 客户端只输出同一 Event，不包含 Presenter 专属字段或 ANSI。

### 4. 冻结 `project_init` 契约与范围限制

**Files:**

- Modify: `src/vera/contracts/commands.py`
- Modify: `src/vera/contracts/compatibility.py`
- Modify: `src/vera/runtime/prompts.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `tests/contracts/test_models.py`
- Modify: `tests/contracts/test_compatibility_manifest.py`
- Modify: `tests/runtime/test_project_instructions.py`

- [x] 给 `StartRun.mode` 增加 literal `project_init`，写 JSON round-trip 与未知 mode 拒绝测试；不提高 schema version，保持新增枚举值的现有向后读取边界。
- [x] 更新 CompatibilityManifest，明确 `project_init` 与三个 `project.instructions.*` Event 是 additive 扩展；旧字段和默认 `mode="agent"` 不变。
- [x] 定义常量 `PROJECT_INIT_GOAL`，要求只读分析 `AGENTS.md`、README、语言/包配置与验证入口，输出事实支持的中文 `VERA.md`，不复制秘密和用户绝对路径。
- [x] 写范围负例：`project_init` 对空 Change Set、两个 change、非 `VERA.md` 路径、大小写变体、删除 `VERA.md`、附带 verification 全部返回 `project_init_scope_violation`，且不产生 `approval.required`。
- [x] 在 `ProjectInstructionService.validate_init_changeset()` 固定“一个 create/update、规范路径精确为 `VERA.md`、无 verification”；Runtime 在 Change Set 建成后、进入审批前调用。
- [x] 写正例：新建和更新 `VERA.md` 仍走既有 content hash、路径事实、PolicyEngine 与审批；拒绝后 workspace 字节不变。

### 5. 接通 `/init` 与 `vera init`

**Files:**

- Modify: `src/vera/session/command_catalog.py`
- Modify: `src/vera/session/controller.py`
- Modify: `src/vera/cli.py`
- Create: `tests/cli/test_project_init.py`
- Modify: `tests/cli/test_session.py`

- [x] 写 `/init` 失败测试：空闲会话启动 `StartRun(goal=PROJECT_INIT_GOAL, mode="project_init")`；活动 Run 或等待审批时沿用现有 action rejection，不排队第二次 init。
- [x] 写 Typer 失败测试：`vera init --workspace PATH` 复用 `build_runtime`、`drive_run` 和 HumanPresenter；帮助明确“只提议 VERA.md，批准后写入”。
- [x] 将 `/init` 实现为 Controller 的受限 Run 分支，将 `vera init` 实现为薄入口；两者不得复制初始化分析、范围校验或文件写入逻辑。
- [x] 写批准/拒绝/取消/模型失败/缺 Provider/`--json` 非交互测试；除批准正例外，初始化前后全量文件 manifest 与 Git porcelain 相同。
- [x] 已存在 `VERA.md` 的测试要求 Change Set operation 为 update，保留无关段落；是否“最小增量”通过 Diff 行数与保留哨兵断言，不依赖模型自由文本快照。

### 6. 安装、真实终端与安全回归

**Files:**

- Modify: `scripts/smoke_installed_wheel.py`
- Create: `tests/pty/test_project_instructions.py`
- Modify: `docs/evals/phase-7-cli-product-acceptance.md`（由任务 0041 创建后更新）
- Modify: `docs/STATUS.md`
- Modify: this task

- [x] 扩展 wheel smoke：在仓库外临时 workspace 覆盖双文件加载、`/instructions`、`vera init` 拒绝、批准更新和下一 Run hash 变化。
- [x] PTY 覆盖 `/init` Diff/审批、Ctrl-C、60×16 状态回退和普通 `vera` 启动无写入；TUI/Plain 不显示指令正文。
- [ ] 对空工程、仅 `AGENTS.md` 工程和已有 `VERA.md` 工程运行真实 Terminal.app 走查，启动前后比较文件 manifest 与 `git status --porcelain=v1`。
- [ ] 在阶段七验收文档记录加载来源、hash、审批结果和工作区无污染证据；不记录说明正文、绝对私有路径或 Provider Key。

## 局部验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest tests/project/test_instructions.py tests/content/test_envelope.py tests/runtime/test_project_instructions.py tests/session/test_project_instructions.py tests/session/test_command_catalog.py tests/cli/test_project_init.py tests/cli/test_session.py tests/presentation/test_projector.py tests/pty/test_project_instructions.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase7-project-instructions-dist
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/smoke_installed_wheel.py --dist /private/tmp/vera-phase7-project-instructions-dist --workspace /private/tmp/vera-phase7-project-instructions-smoke
git diff --check
```

局部测试通过后再运行阶段七共同非 live 门禁。真实 Terminal.app 结果单独记录，不能由 CliRunner、PTY 或 FakeModelAdapter 代替。

## 验证记录（2026-09-16）

- 局部与共同非 live 门禁、`ruff`/`mypy`、wheel smoke、PTY 无静默写入已通过。
- 真实 Terminal.app 对空工程、仅 `AGENTS.md`、已有 `VERA.md` 的走查仍待用户；阶段七验收文档由任务 0041 创建后补证据。

## 提交边界

只在用户后续授权实施与提交时执行：

```bash
git add src/vera/project_instructions.py src/vera/content/trust.py src/vera/content/envelope.py src/vera/runtime/prompts.py src/vera/runtime/engine.py src/vera/bootstrap.py src/vera/contracts/commands.py src/vera/contracts/compatibility.py src/vera/session/command_catalog.py src/vera/session/controller.py src/vera/cli.py src/vera/cli_presenter.py src/vera/presentation/projector.py tests/project tests/content/test_envelope.py tests/contracts/test_models.py tests/contracts/test_compatibility_manifest.py tests/runtime/test_project_instructions.py tests/session/test_project_instructions.py tests/session/test_command_catalog.py tests/cli/test_project_init.py tests/cli/test_session.py tests/presentation/test_projector.py tests/pty/test_project_instructions.py scripts/smoke_installed_wheel.py docs/evals/phase-7-cli-product-acceptance.md docs/STATUS.md docs/tasks/0043-project-instructions-and-init.md
git commit -m "feat: add Vera project instructions"
```

不得夹带阶段六、其他阶段七任务、用户工程或自动生成的 `VERA.md`。

## 完成定义

- 根目录双文件发现、优先级、Run 快照、大小和文件安全行为满足规格。
- Project guidance 始终为 advisory，危险文本不能改变 PolicyEngine、审批或 workspace 边界。
- `/instructions` 三种模式语义一致，Event/Journal 不含正文与绝对私有路径。
- `/init` 与 `vera init` 只经正常 Change Set 审批写 `VERA.md`；所有失败路径保持工作区字节不变。
- wheel smoke、PTY、完整非 live 和真实 Terminal.app 走查通过，任务证据与实际行为一致。
