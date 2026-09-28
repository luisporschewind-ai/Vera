# 阶段八工具、Policy v2 与原生 Git 验收证据

> 2026-09-26 文档对齐：本记录来自 `codex/phase-8-tooling-policy-git`（核对时 HEAD `5b6d789`）。实现及验证属于该隔离分支，尚未合入 `main`；同步文档不代表代码集成或本轮重新测试。

**任务：** [0066 阶段八验收与真实 dogfood](../tasks/0066-phase-8-tooling-git-acceptance.md)
**记录日期：** 2026-09-20
**结论：** 自动验收通过，任务进入 `Ready for manual acceptance`；这不是阶段八 `Complete`。

## 1. 证据边界

- 所有自动测试使用临时 workspace、临时 state、Fake Model 和脱敏 Git 身份，没有读取 Provider Key，也没有调用真实 Provider。
- wheel smoke 在仓库外临时目录完成；Core smoke 临时 workspace 位于 wheel 输出目录之外，避免把 smoke 自身写入被校验的 workspace。
- Python、Swift dogfood 使用 `/private/tmp` 安全副本；没有修改 `/Users/admin/Desktop/VeraTestDemo`。Node/TypeScript 使用 `/private/tmp/vera-phase8-dogfood.qExzsd/typescript`。
- 本记录只记录结果、命令和错误分类，不记录私有源码、秘密或 token。

## 2. Acceptance Matrix

| 条目 | 结果 | 证据 |
|---|---|---|
| A canonical read/grep/find/ls 与 legacy decoder | Verified | `tests/e2e/test_phase_8_tooling_policy.py` 固定 `read/edit/grep/find/ls/bash` 注册名和 `CompatibilityManifest`；阶段八全量 non-live 通过。 |
| B trusted balanced write/edit | Verified | 同一 E2E 矩阵覆盖三类代表性工程的 edit、approval resolve 和最终文件内容；低风险执行通过。 |
| C untrusted/review/high-risk/forbidden | Verified | bash shell 语法、`git push`、不可信 hook 的 deny 断言通过；既有 Policy/Approval/Recovery 回归也通过。 |
| D structured bash | Verified | `tests/e2e/test_phase_8_tooling_policy.py` 覆盖 argv-only allow 与 shell/Git write deny；既有 `tests/tools/test_bash.py` 和 PTY 门禁通过。 |
| E multi-action Diff/Checkpoint/Receipt/stale/crash recovery | Verified | 阶段八全量 non-live 包含 0061、0062、0065 恢复与客户端事件回归；安全/恢复专项 `35 passed`。 |
| F native Git read | Verified | `tests/e2e/test_phase_8_native_git.py` 覆盖 status/diff/log/show、allow 边界；0063 的 linked worktree、submodule、sparse、unborn、detached、operation-state fixture 保留通过。 |
| G exact commit | Verified | 临时仓库覆盖 path-scoped commit；新文件提交后 staged 状态为空，提交消息和路径反向验证通过；既有 Git commit transaction 回归通过。 |
| H hooks/signing/identity/recovery/branch | Verified | 不可信 hook 在 commit 前 deny；0065 的 hook facts、签名错误、幂等恢复、branch create/switch、Run snapshot/event 回归通过。 |
| I TUI/Plain/JSON/Event/Journal/CompatibilityManifest parity | Verified | `tests/e2e/test_phase_8_client_parity.py` 对同一 `git.operation.*` facts 做 Plain/TUI/JSON 对照；PTY plain 输出无 ANSI；clean-install import 回归通过。 |
| J Python/Node/TypeScript/Swift/Xcode dogfood | Partial; see §4 | Python 与 Swift/Xcode 有真实副本证据；Node/TypeScript 受本机工具与 fixture 运行能力限制，未伪造通过。 |

## 3. 自动门禁

### 全量测试

```text
uv run --offline pytest -q -m 'not live'
1307 passed, 2 deselected, 8 warnings in 313.68s (0:05:13)
```

8 个 warning 均来自 Python 3.12 `pty.py` 在多线程进程中调用 `forkpty()` 的 DeprecationWarning，不是测试失败。

专项结果：

```text
阶段八新增 E2E + PTY：10 passed
安全/拒绝/崩溃恢复/Bash/Git/恢复专项：35 passed
```

静态与构建：

```text
uv run --offline ruff check src tests          # All checks passed
uv run --offline ruff format --check src tests # 473 files already formatted
uv run --offline mypy src                      # Success: no issues found in 192 source files
git diff --check                               # passed
uv build --offline --wheel --sdist             # wheel 与 sdist 均成功
```

安装态 wheel smoke 使用：

```text
uv build --offline --wheel --out-dir <temporary-dist>
uv run --offline python scripts/smoke_installed_wheel.py \
  --dist <temporary-dist> --workspace <temporary-workspace>
All checks passed!
```

该 smoke 实际从安装 wheel 运行 Core 的 write/edit/read、shell deny、Git init/config/commit/status/exact commit；过程中发现并修复了 clean-install 的 recovery→tools Git 循环导入，以及 smoke workspace 与 dist 校验根重叠的问题。

## 4. 三类工程 dogfood

### Python：Verified

- `/private/tmp/vera-phase8-dogfood.qExzsd/python` 安全副本完成源码 edit，并先由旧断言得到 1 个真实失败，再更新测试断言。
- `PYTHONPATH=src uv run --offline --project /Users/admin/Vera/tmp/vera-phase8-tooling-policy-git pytest -q`：`1 passed`。
- 同一命令链 Ruff：`All checks passed`。
- 通过原生 `GitCommitTool` 完成精确 commit `5e702ba Dogfood Python edit`，随后完成 branch create/switch；临时仓库最终工作区干净。

### Node/TypeScript：Blocked / Not verified

- 多文件 edit 已完成，但本机 Node `v21.7.1` 对该 `.ts` fixture 的 `node --test` 发现 `0` 个测试：`1..0`、`tests 0`、`pass 0`，因此不能计为测试通过。
- 离线 `npm exec --offline -- tsc --noEmit --incremental false` 因本机 npm cache 没有 `tsc`，返回 `ENOTCACHED`；没有联网安装依赖，也没有把网络可达性误记为代码通过。
- 结论是运行环境/fixture 能力阻塞，不是 Vera Core 的 TypeScript 语义通过证据；后续需在有可用 TypeScript runner/compiler 的真实工程重新验收。

### Swift/Xcode：Verified with signing boundary

- 使用 `/Users/admin/Desktop/VeraTestDemo` 的安全副本 `/private/tmp/vera-phase8-swift-git.T7vv4H`，源码 edit 为 `ViewController.swift` 背景色变更。
- `xcodebuild -list` 成功识别 `VeraTestDemo` scheme；第一次普通 build 暴露原工程 provisioning profile 缺失，随后使用明确的本地模拟器验收参数 `-sdk iphonesimulator -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO`。
- 使用外部 `-derivedDataPath /private/tmp/vera-phase8-swift-git.T7vv4H-derived` 构建，结果：`** BUILD SUCCEEDED **`。
- 通过原生 `GitCommitTool` 完成 `78afaed Dogfood Swift edit`；修改副本工作区干净，工程根未写入 DerivedData。

## 5. 未运行与人工门

- 原生 Terminal.app 前置测试已执行：`vera --help` exit 0；`vera --version` exit 0 并显示 `0.1.0+d7f5932`；`TERM=dumb vera` exit 2 并提示使用 `--plain`/`--json`；`vera eval validate/list/run --json` 分别 exit 0，14 个离线 eval suite 为 `pass`。
- 该 Terminal.app 前置测试没有改变隔离工作树；当前新增的 `.pytest_cache`/`__pycache__` 均为既有 ignored cache，`git status --short --branch` 仍干净。
- 未运行真实 Provider、真实 API Key、网络依赖安装和 `git push`；这些不是本任务的离线自动门禁，且 `bash` 的远程 Git 写操作仍保持拒绝边界。
- 未完成真实 Terminal.app 的本轮人工全流程验收；PTY 只能证明文本/无 ANSI 契约，不能替代原生 Terminal.app 视觉和交互验收。
- 因此本证据只允许将 0066 和阶段八推进到 `Ready for manual acceptance`。只有用户明确确认阶段八结果后，才可将任务/阶段标为 Done/Complete；阶段九后来已于 2026-09-21 获得单独并行实施授权，不关闭本阶段门禁。
