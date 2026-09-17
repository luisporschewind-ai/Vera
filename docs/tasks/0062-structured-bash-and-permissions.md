# 任务 0062：结构化 bash、授权作用域与 CLI 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Planned；已授权串行实施，依赖 0061 完成
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

- [ ] **Step 1: 写输入和 shell 负例** — 拒绝空 argv、NUL、cwd 逃逸、超时越界；确认字符串 `"a | b"` 只是一个 argv 元素，不解释管道、重定向、`$()` 或 glob。
- [ ] **Step 2: 运行 Red** — `uv run pytest tests/tools/test_bash.py -q`，预期 BashTool 不存在。
- [ ] **Step 3: 实现 BashTool** — 规范化 cwd，构造最小环境，调用 `ProcessSupervisor.run(ProcessRequest(...))`；输出 UTF-8 replacement 解码、有界截断、稳定 timeout/cancel/error code。
- [ ] **Step 4: 写风险矩阵** — 覆盖 rg/find、pytest/ruff/mypy、构建、格式化、代码生成、包安装、后台服务、shell 启动器、sudo/su、rm、Git 写子命令、网络工具和秘密环境名。
- [ ] **Step 5: 实现 CommandClassifier v2** — 只读/已规划验证按事实允许；工作区写入、安装、网络、Hook 为 high/approval；提权、秘密、Git 绕过和宽泛删除 deny。
- [ ] **Step 6: 写授权作用域测试** — `once` 仅精确 action；`run` 绑定 tool/effect/argv constraint；`workspace` 额外绑定 identity/Policy 版本/到期，参数变化不命中。
- [ ] **Step 7: 接入审批与 Receipt** — 已允许计划执行一次；进程启动后崩溃且无法证明副作用时恢复为 `manual_required`，不自动重跑未知命令。
- [ ] **Step 8: CLI 状态与审批卡** — `/status` 显示 trust/mode/sandbox；`/permissions` 支持查看、trust、revoke；审批卡仅展示 Core 提供的可用作用域。
- [ ] **Step 9: 三客户端和 PTY 对照** — TUI/Plain/JSON 对同一决策语义一致；60×16 下仍能看清 effect、cwd、argv 摘要与风险，正文脱敏。
- [ ] **Step 10: 运行局部与共同门禁** — `uv run pytest tests/tools/test_bash.py tests/tools/test_command_policy_v2.py tests/session/test_permissions_v2.py tests/pty/test_permissions_v2.py -q` 后运行共同门禁。
- [ ] **Step 11: 提交（仅用户授权后）** — 提交信息 `feat: add structured bash permissions`。

## Done

- `bash` 不解释 Shell 语言，取消/超时回收进程组。
- 常用低风险验证不重复打断，高风险与硬拒绝边界可解释。
- trust 和授权可查看、撤销、失效，客户端不拥有安全判断。
