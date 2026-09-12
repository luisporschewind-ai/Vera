# 命令、进程与秘密加固验收记录

更新日期：2026-09-12

## 结论

任务 0021 离线实现通过。Verification 与 Eval Worker 共用 `ProcessSupervisor` 与 `build_child_environment`：空白基线 allowlist、禁止 Provider/云/CI Token 继承、POSIX 进程组 TERM→KILL、流式有界输出。`SecretPolicy` 作为字段名、环境名和文本规则的单一来源，TUI/Plain/JSON/Journal/Evidence 复用同一脱敏。

未运行 live，未读取真实 DeepSeek/GLM Key，未修改用户工程。

## 规格验收对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | 结构化 argv、`shell=False`、cwd 位于工作区 | 通过 |
| 2 | PolicyEngine 对禁止/需批准/允许保持单一权威；Presenter 不覆盖 | 通过 |
| 3 | 取消/超时清理进程组；忽略 TERM 后 KILL；结果区分 `cancelled`/`timed_out` | 通过 |
| 4 | 子进程环境 allowlist；Provider/云/CI Token 不继承，override 不能恢复 | 通过 |
| 5 | 超大 stdout/stderr 流式截断并收割进程 | 通过 |
| 6 | Authorization/Bearer、URL query、JSON 字段、环境行、异常字符串脱敏 | 通过 |
| 7 | 短单词、文件 hash、run ID 不误删；高熵只在凭据上下文处理 | 通过 |

## 自动验证证据

- 额外聚焦：51 passed
- `pytest -m "not live"`：587 passed，2 deselected
- Ruff / format / Mypy / `uv build` / `git diff --check`：通过
- Diff：`src/` 无 `shell=True`、`os.environ.copy()`、`communicate()`

## 已知限制

- 非 POSIX 明确降级为单进程 TERM/KILL，不宣称 OS 沙箱
- 阶段五恢复、三类真实工程与 20 次 dogfood 仍待 0022–0024
