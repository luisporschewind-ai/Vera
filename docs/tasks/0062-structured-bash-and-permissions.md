# 任务 0062：结构化 bash、授权作用域与 CLI 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Done；已完成并创建本地提交，未合并、未推送
**Goal：** 实现 `shell=False` 的结构化 `bash` 工具、命令风险分类、一次/Run/workspace 授权和统一 CLI 可见性。
**Architecture：** `BashTool` 只生成 `CommandActionPlan`；CommandClassifier 根据 argv/cwd/effects/目标授权分类，ProcessSupervisor 是唯一进程执行器。CLI 只展示 Core 返回的 trust、模式、决策和授权摘要。
**Tech Stack：** Python 3.12、Pydantic 2、ProcessSupervisor、Typer、Textual、pytest/PTY。
**Spec：** `docs/specs/2026-09-17-core-tooling-and-risk-tiered-policy.md`

## Files

- Create: `src/vera/contracts/process_actions.py`
- Create: `src/vera/tools/bash.py`
- Modify: `src/vera/tools/command_policy.py`
- Modify: `src/vera/process/environment.py`
- Modify: `src/vera/process/supervisor.py`
- Modify: `src/vera/persistence/operation_receipt.py`
- Modify: `src/vera/session/permissions.py`
- Modify: `src/vera/session/command_catalog.py`
- Modify: `src/vera/session/controller.py`
- Modify: `src/vera/presentation/projector.py`
- Modify: `src/vera/terminal/widgets/approval.py`
- Test: `tests/tools/test_bash.py`
- Test: `tests/tools/test_command_policy_v2.py`
- Test: `tests/session/test_permissions_v2.py`
- Test: `tests/pty/test_permissions_v2.py`

## Interfaces

```python
class BashInput(BaseModel):
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=1800)

class CommandActionPlan(ContractModel):
    action_id: str
    argv: tuple[str, ...]
    cwd: str
    executable: str
    risk_level: RiskLevel
    writes_workspace: bool
    input_hash: str
    policy_hash: str
```

## Steps

- [x] **Step 1: 写输入和 shell 负例** — 拒绝空 argv、NUL、cwd 逃逸、超时越界；确认字符串 `"a | b"` 只是一个 argv 元素，不解释管道、重定向、`$()` 或 glob。
- [x] **Step 2: 运行 Red** — 已补充 `tests/tools/test_bash.py`，当前实现后 7 项通过。
- [x] **Step 3: 实现 BashTool** — 规范化 cwd，构造最小环境，调用 `ProcessSupervisor.run(ProcessRequest(...))`；输出 UTF-8 replacement 解码、有界截断、稳定 timeout/cancel/error code。
- [x] **Step 4: 写风险矩阵** — 已覆盖只读验证、构建/格式化/代码生成、后台服务、安装、网络、shell、提权、删除、Git 写子命令和秘密参数。
- [x] **Step 5: 实现 CommandClassifier v2** — `CommandClassifier` 已按 argv 事实分类；硬拒绝与 high 风险均由 Core 决策。
- [x] **Step 6: 写授权作用域测试** — Bash 的 once/run/workspace 匹配、精确 argv 绑定和 forbidden shell 边界已补测；CLI 无效作用域与权限摘要已覆盖。
- [x] **Step 7: 接入审批与 Receipt** — 进程计划只在批准后执行一次并写入 process Receipt；进程启动后崩溃且无法证明副作用时恢复为 `manual_required`，不自动重跑未知命令。
- [x] **Step 8: CLI 状态与审批卡** — `/status` 显示 trust/mode/sandbox；`/permissions` 支持查看、trust、revoke 并原子持久化；审批卡仅展示 Core 提供的可用作用域。
- [x] **Step 9: 三客户端和 PTY 对照** — TUI/Plain/JSON 对同一决策语义一致；60×16 PTY 下可见 effect、cwd、argv 摘要与风险，正文仍脱敏。
- [x] **Step 10: 运行局部与共同门禁** — 局部专项 `94 passed`；全量 `1241 passed, 2 skipped, 7 warnings`；Ruff、format、Mypy、`git diff --check` 与离线 wheel/sdist 均通过。2 个 skip 为 live provider 测试，未伪造为通过。
- [x] **Step 11: 提交** — `7cbdfd9 feat: add structured bash permissions`；CLI 权限摘要补齐见后续收口提交。

## Done

- `bash` 不解释 Shell 语言，取消/超时回收进程组。
- 常用低风险验证不重复打断，高风险与硬拒绝边界可解释。
- trust 和授权可查看、撤销、失效，客户端不拥有安全判断。
