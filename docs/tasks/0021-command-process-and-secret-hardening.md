# 任务 0021：命令、进程与秘密加固

> 供 Cursor 执行：按 `superpowers:executing-plans` 实施；先证明旧行为失败，再写最小修复。

**状态：** Done
**执行就绪：** 是
**分支：** `phase-5/0021-process-secret-hardening`
**依赖：** 任务 0020 已合并
**规格：** [阶段五 Core 加固](../specs/2026-09-12-core-security-and-reliability-hardening.md)

## 目标与边界

统一普通验证与 Eval Worker 的子进程安全边界：结构化 argv、workspace cwd、最小环境、输出上限、进程组取消和超时清理；扩充结构化秘密识别与全出口脱敏。

不开放任意 Shell，不新增自动批准，不读取或打印真实 Key，不用网络/live 测试作为验收。

## 设计约束

- 新增共享 `ProcessSupervisor`，`VerificationRunner` 与 `CaseProcessRunner` 只保留领域映射。
- POSIX 创建独立进程组，取消/超时执行 TERM → 有界等待 → KILL；其他平台提供等价能力或明确降级结果。
- 环境从空白基线和固定 allowlist 构造；Provider、云厂商、Agent 与 CI Token 默认不继承。
- stdout/stderr 按字节上限流式收集并标注截断，不先把无限输出完整读入内存。
- Redactor 接受字段名、header、URI 与文本模式；输出只能是脱敏值，不能把命中原文写入诊断。

## 实施步骤

### 1. 共享环境过滤器

**修改：**

- 新增 `src/vera/process/environment.py`
- `src/vera/verification/runner.py`
- `src/vera/evals/process_runner.py`
- 新增 `tests/process/test_environment.py`
- `tests/verification/test_runner.py`
- `tests/evals/test_process_runner.py`

**测试先行：**

1. 仅保留 PATH、locale、终端基础变量和显式任务变量。
2. `*_API_KEY`、`*_TOKEN`、`AUTHORIZATION`、云凭据、DeepSeek/GLM/OpenAI/Anthropic 变量均不继承。
3. 大小写变体和空值不会绕过；调用者不能通过 override 恢复禁止变量。
4. 运行聚焦测试，确认普通 Verification 现有环境继承导致失败。

**最小实现：** 提供 `build_child_environment(overrides, purpose)`，两个 Runner 共享同一禁止集和审计字段。

### 2. 进程组监督和有界输出

**修改：**

- 新增 `src/vera/process/supervisor.py`
- `src/vera/verification/runner.py`
- `src/vera/evals/process_runner.py`
- 新增 `tests/process/helpers/spawn_child.py`
- 新增 `tests/process/test_supervisor.py`
- `tests/verification/test_runner.py`
- `tests/evals/test_process_runner.py`

**测试先行：**

1. 父进程生成子进程后，取消和超时均清理整个组。
2. 忽略 TERM 的进程在宽限期后被 KILL，结果区分 `cancelled` 与 `timed_out`。
3. 连续输出超过限制时进程仍被收割，结果含 `stdout_truncated/stderr_truncated`，内存保持有界。
4. argv 中的空格和元字符按字面传入，绝不经 shell 解释。

**最小实现：** `ProcessRequest`、`ProcessResult`、`ProcessSupervisor.run()`；平台能力通过显式 adapter 封装。

### 3. PolicyEngine 命令回归矩阵

**修改：**

- `src/vera/tools/command_policy.py`
- `src/vera/policy/engine.py`
- `tests/tools/test_command_policy.py`
- `tests/policy/test_matrix.py`
- `tests/runtime/test_safe_editing_flow.py`

**测试先行：** 覆盖空 argv、相对/绝对可执行文件、shell 启动器、嵌套解释器、cwd 变化、禁止命令、需批准命令和等价参数重排。确认 Presenter 或 Runner 不能覆盖 PolicyDecision。

**最小实现：** 只补齐规范化与分类缺口；若测试要求新增政策，先同步规格或 ADR，不能扩大 allowlist 迁就用例。

### 4. 结构化秘密脱敏

**修改：**

- `src/vera/redaction.py`
- `src/vera/config.py`
- `src/vera/evals/corpus/__init__.py`
- `src/vera/persistence/journal.py`
- 新增 `tests/security/test_redaction_matrix.py`
- `tests/evals/test_corpus.py`
- `tests/persistence/test_journal.py`

**测试先行：**

1. Authorization/Bearer、URL query、JSON 字段、环境行、异常字符串及常见供应商变量均脱敏。
2. 短普通单词、文件 hash、run ID 不被误删。
3. TUI/Plain/JSON/Event/Journal/Evidence 的同一恶意 fixture 均无原秘密。
4. 随机高熵样本只在带凭据上下文时处理，避免不可解释的广泛误报。

**最小实现：** 将敏感字段、环境名和文本规则集中为 `SecretPolicy`；Redactor 处理结构化对象后再处理文本，所有出口复用。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY uv run pytest tests/process tests/verification tests/evals/test_process_runner.py tests/tools/test_command_policy.py tests/policy tests/security tests/persistence/test_journal.py -q
```

随后运行[阶段五共同门禁](phase-5-execution-order.md)，并检查没有 `shell=True`、整份 `os.environ.copy()`、无限 `communicate()` 缓冲或日志原文。更新任务证据后提交：

```bash
git commit -m "feat: harden child processes and secret handling"
```

## 验收标准

- 超时/取消无可观察孤儿进程，结果与副作用状态明确。
- Verification 与 Eval 环境策略一致，真实 Provider Key 不可传入。
- 大输出不会无限增长内存，截断事实进入结构化结果。
- 所有持久和展示出口通过同一脱敏矩阵。

## 验证结果

- 日期：2026-09-12
- 额外聚焦：`pytest tests/process tests/verification tests/evals/test_process_runner.py tests/tools/test_command_policy.py tests/policy tests/security tests/persistence/test_journal.py -q` → 51 passed
- 完整非 live：587 passed / 2 deselected；Ruff、format、Mypy、`uv build`、`git diff --check` 通过
- Diff 检查：无 `shell=True`、无 `os.environ.copy()`、无无限 `communicate()`
- 未读取真实 Provider Key，未运行 live，未修改用户工程，未引入桌面框架

## 未决事项

- 非 POSIX 平台使用 `FallbackProcessAdapter`（逐进程 TERM/KILL，不宣称进程组）
- 阶段五其余退出条件（恢复、三类真实工程、20 次 dogfood）属于任务 0022–0024，本任务不关闭阶段五
