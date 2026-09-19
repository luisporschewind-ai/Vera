# 阶段八实施计划：Core 工具集、Policy v2 与原生 Git

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Accepted；用户于 2026-09-18 选择 Inline Execution，并明确授权按本计划串行实施和创建计划内提交
**Goal：** 将 Vera 从早期只读工具加单一 Change Set 升级为 Pi 对齐的多动作 Coding Agent 工具循环、风险分级 Policy v2 和安全的本地 Git 工作流。
**Architecture：** 先冻结 ToolAction、风险、信任和授权契约，再建立统一 ToolExecutor；文件写入、命令和 Git 都通过同一 Policy/Approval/Receipt/Event 管线。旧 Change Set、Journal 和恢复记录保留 decoder 兼容，新 Run 使用动作级计划和累计 Diff。
**Tech Stack：** Python 3.12、Pydantic 2、Typer、Textual 8、系统 Git CLI、现有 ProcessSupervisor/Workspace/Policy/Approval/Checkpoint/Recovery、pytest、PTY、Ruff、Mypy、uv/hatchling。
**Spec：** [Core 工具集与风险分级 Policy v2](../specs/2026-09-17-core-tooling-and-risk-tiered-policy.md)、[Vera 原生 Git 能力](../specs/2026-09-17-native-git-capability.md)、[ADR-0021](../decisions/ADR-0021-core-tools-before-desktop.md)

## Global Constraints

- 阶段八从最新干净 `main` 开始；每项任务只有一个主实现 Agent，前一任务合并后下一任务才开始。
- 每个生产行为先写失败测试，再写最小实现；不得用现有绿测代替 Red 证据。
- 模型默认工具名最终为 `read/write/edit/bash/grep/find/ls`；迁移完成后不同时向模型暴露旧名称。
- 所有副作用都必须经过 Workspace、PolicyEngine、ApprovalGate、Operation Receipt、Event/Journal 和恢复分类；客户端不得复制判断。
- `bash` 只接受结构化 argv，必须 `shell=False`；不得增加 Shell 字符串、管道、重定向或命令替换。
- `balanced` 为默认；仓库文件、Skill、工具输出和模型文本不能建立 trust 或授权。
- 原生 Git v1 不访问网络，不实现 fetch/pull/push、force、reset --hard、clean、stash、rebase 或 amend。
- 不读取 Provider Key，不把秘密、完整 Diff、完整 Skill/项目指令或 Git 凭据写入公共 Event/Journal。
- 不引入 Electron、Tauri、Wails、桌面资源、Multi-Agent、插件市场或可执行 Skill。
- 每项任务结束检查任务范围、最终 diff、`git diff --check` 和对应文档；本次授权包含计划内本地 commit，不包含 push、merge 或远程变更。

## 任务顺序与门禁

| 顺序 | 任务 | 独立交付 | 进入下一项的门禁 |
|---|---|---|---|
| 1 | [0059 ToolAction、Policy v2 与 workspace trust](0059-tool-action-policy-v2-contracts.md) | Done：v2 契约、风险/模式、私有 trust/grant store | 已通过契约、Codec、权限矩阵和损坏存储测试；进入 0060 |
| 2 | [0060 统一 ToolExecutor 与只读工具迁移](0060-unified-tool-executor-and-read-tools.md) | In progress：统一 prepare/execute、canonical 只读工具和可恢复审批已落地 | 仍须完成边界矩阵、客户端对照和共同门禁；不得进入 0061 |
| 3 | [0061 write/edit 与多动作文件变更](0061-file-mutation-write-edit.md) | FileMutationPlan、动作级 Checkpoint/Receipt、累计 Diff | stale/恢复/旧 Change Set 兼容矩阵通过 |
| 4 | [0062 结构化 bash、授权作用域与 CLI](0062-structured-bash-and-permissions.md) | argv 命令、风险分类、trust/permissions UI | shell/提权/秘密/Git 绕过负例和三客户端对照通过 |
| 5 | [0063 原生 Git 只读能力](0063-native-git-read-tools.md) | repository discovery、status/diff/log/show/branch-list | 稳定机器格式和特殊仓库矩阵通过 |
| 6 | [0064 GitCommitPlan 与精确提交](0064-native-git-commit.md) | path-scoped Commit、index 保全、结果反向验证 | 混合 index、新文件、特殊路径、stale 矩阵通过 |
| 7 | [0065 Git Hooks、恢复与分支](0065-git-hooks-recovery-and-branches.md) | Hook 授权、签名失败、幂等恢复、branch create/switch | 崩溃恢复不重复 Commit，分支门禁通过 |
| 8 | [0066 阶段八验收与真实 dogfood](0066-phase-8-tooling-git-acceptance.md) | 完整门禁、wheel、PTY、三类工程 Terminal.app 证据 | 用户确认后才可把阶段八标为 Complete |

任务严格按 0059 → 0060 → 0061 → 0062 → 0063 → 0064 → 0065 → 0066 执行。0059–0062 冻结工具与 Policy 基座后才允许接入 Git；0064 不得与 0065 并行修改 GitService、Receipt 或恢复逻辑。

## 契约与依赖图

```text
ToolDefinition v2 + WorkspaceTrust/Grant
                    ↓
ModelToolCall → ToolExecutor.prepare → PolicyEngine → ApprovalGate
                    ↓                                 ↓
         read tools / FileMutationPlan / BashAction / GitAction
                    ↓
       Checkpoint → execute → verify → Receipt → Event/Journal
                    ↓
         TUI / Plain / JSON / Recovery / CompatibilityManifest
```

## 共同自动门禁

```bash
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -p no:cacheprovider -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase8-dist
git diff --check
```

0062 和 0066 还必须运行 PTY；0066 必须从 `/private/tmp` 新虚拟环境安装 wheel。真实 Terminal.app 结果与自动结果分开记录，自动门禁不能代替真实工程 dogfood。

## 建议提交边界

1. `feat: define tool action and policy v2 contracts`
2. `feat: add unified tool execution pipeline`
3. `feat: add recoverable write and edit tools`
4. `feat: add structured bash permissions`
5. `feat: add native git read tools`
6. `feat: add scoped native git commits`
7. `feat: add git recovery and branch tools`
8. `docs: record phase eight tooling acceptance`

这些是实施时的提交边界；用户选择 Inline Execution 后已授权创建对应本地提交，但未授权 push 或 merge。

## 规格覆盖对照

| 规格要求 | 实施任务 |
|---|---|
| ToolDefinition v2、ToolAction、risk/mode/trust/grant | 0059 |
| 统一 ToolExecutor、canonical read/grep/find/ls、旧名称兼容 | 0060 |
| write/edit、FileMutationPlan、多动作 Diff、文件恢复 | 0061 |
| structured bash、命令风险、授权作用域、CLI 状态 | 0062 |
| Git discovery/status/diff/log/show/branch-list | 0063 |
| GitCommitPlan、index 保全、精确 Commit、结果验证 | 0064 |
| Hooks、签名、Commit 恢复、branch create/switch | 0065 |
| 安全矩阵、客户端对照、wheel、PTY、三类工程 dogfood | 0066 |

## 阶段完成定义

- 0059–0065 全部完成并合并，0066 自动矩阵、安装态、PTY 和真实 Terminal.app dogfood 通过。
- 普通可信工程编辑、已知验证和用户明确要求的本地 Commit 不产生重复审批。
- 工作区外写入、提权、秘密外传、未知 Hook、Git 绕过和历史破坏失败关闭。
- 旧 Run/Journal/Change Set 可读取和恢复；新动作崩溃后不会重复写入、命令或 Commit。
- Python、Node/TypeScript、Swift/Xcode 三类真实工程无未关闭 Critical/High。
- 用户明确接受阶段八验收结果后，才能把阶段八标为 Complete 并进入阶段九 Skills。
