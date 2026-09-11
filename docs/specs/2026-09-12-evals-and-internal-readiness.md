# Vera 阶段四：评测与内部就绪

**状态：** Accepted
**日期：** 2026-09-12

## 背景

阶段一到阶段三已经把 Core、恢复、策略、供应商韧性和三种终端模式打通。产品定义与路线图仍把「固定任务评测」列为第一阶段能力，但仓库里只有任务验收记录（`docs/evals/`），没有可重复跑的编码任务集，也没有独立于 TUI/人类输出的评分器。

阶段四补上这条缺口：用 Core Command/Event 跑一组冻结的本地编码任务，产出正确性、安全性、恢复、延迟和用量证据。它服务内部就绪，不替代 live 供应商评测，也不提前桌面端。

## 目标

- 提供可重复的评测工具，第一版完全离线、使用脚本化 `FakeModelAdapter`。
- 维护 10–20 个冻结编码任务，覆盖创建/修改文件、拒绝审批、越界与禁止命令、验证、回滚、中断恢复与普通文本回答。
- 每次运行把工作区复制到临时目录，隔离 `state_dir`，不触碰 `/Users/admin/Desktop/VeraTestDemo` 或用户工程。
- 从权威 Event Journal、Diff、审批、验证和文件哈希评分，不解析 CLI/TUI 人类文本。
- 报告延迟（Event 时间戳）和模型用量（`model.completed.usage`，缺失为 `null`）。
- CLI `vera eval` 能校验语料、列出任务、单跑和整套离线套件，并输出结构化报告与私有证据包。

## 非目标

- 不读取真实 DeepSeek/GLM Key，不实现或运行 live 评测；真实供应商评测另立规格。
- 不修改真实验收工程，不把用户家目录当作语料。
- 不引入桌面框架、Multi-Agent、RAG、向量库或插件市场。
- 不建立计费系统；用量只做单次 run 证据。
- 不把评测通过定义为「模型足够聪明」；离线套件证明的是 Core 闭环与评测工具本身。
- 不为了评测放宽 PolicyEngine、Workspace 或审批边界。

## 架构

```text
vera eval
    └── EvalSuiteRunner
            ├── CorpusLoader          # 读取包内 vera/evals/corpus/<id>/
            ├── FixtureIsolator       # 临时 workspace + 临时 state_dir
            ├── CaseProcessRunner     # 每个 case 一个受控子进程与硬超时
            │       └── EvalWorker    # Core Command/Event + FakeModelAdapter
            ├── Scorer                # 纯函数，只读事实与文件哈希
            └── EvidenceWriter        # EvalReport + 脱敏证据包
```

评测工具是又一个 Core 客户端，与 TUI/Plain/JSON Session 平级：

- Worker 只发送 `StartRun` / `ResolveApproval` / `CancelRun` / `ResumeRun` / `RollbackRun` / `InspectRecovery` 等已有 Command；
- Worker 只消费 `EventEnvelope`；测试注入的 failpoint 只改变进程中断位置，不成为评分事实；
- 不解析 `HumanPresenter`、Textual Widget 或 ANSI。

每个 case 在独立子进程运行，父进程只传入版本化 `EvalWorkerRequest`，并只读取版本化 `EvalWorkerResult`。超时后父进程终止该 Worker，记录 `case_timeout`，不能让卡死的 case 阻塞整个套件。子进程是生命周期与超时边界，不是 OS 沙箱；Core 的 Workspace 与 PolicyEngine 仍是执行安全边界。

## 任务与语料

每个任务是包内目录 `src/vera/evals/corpus/<case_id>/`，随 wheel 一起分发：

```text
case.json          # EvalCase，schema_version=1
workspace/         # 源夹具；运行时只复制，不原地执行
script.json        # ModelTurn、审批序列与场景步骤
expect.json        # 期望哈希、允许变化路径、Event 与恢复断言
```

`EvalCase` 至少包含：

| 字段 | 含义 |
|---|---|
| `case_id` | 稳定标识，与目录名一致 |
| `title` | 短标题 |
| `goal` | 交给 `StartRun.goal` 的文本 |
| `tags` | `correctness` / `safety` / `recovery` / `conversation` |
| `model` | 第一版固定为 `fake`；其他值以 `unsupported_model` 拒绝 |
| `timeout_seconds` | case 子进程硬超时，范围 1–120 秒 |
| `approvals` | 预置 `approve` / `reject` / `cancel` 序列 |
| `scenario` | `standard`、`rollback` 或一个冻结的恢复场景名 |

夹具文件不得包含符号链接、特殊文件、秘密、绝对私有路径或真实 Key。Corpus 根目录包含 `manifest.json`，记录所有 case 文件的相对路径与 SHA-256；Loader 在执行前校验 manifest，Worker 结束后再次校验源 corpus 未变化。更新冻结语料必须显式更新 manifest 并接受代码审阅。

`script.json` 只能反序列化为已知 `ModelTurn`、审批决定和场景枚举，不能导入类、执行代码或扩展任意命令。验证命令中的 `$VERA_EVAL_PYTHON` 是唯一占位符，由 Worker 替换为当前 `sys.executable`；其他环境变量语法一律拒绝。

第一版语料固定 **14** 个离线任务（落在 10–20 区间内），标识不得随意改名：

| ID | 标签 | 要证明的行为 |
|---|---|---|
| `create-file` | correctness | 审批后创建文件，字节与期望一致 |
| `update-file` | correctness | 更新已有文件，Checkpoint 存在 |
| `multi-file-edit` | correctness | 一次 Change Set 改两个路径 |
| `plain-answer` | conversation | 无工具，`assistant.message` 且工作区不变 |
| `reject-keeps-original` | safety | 拒绝审批后原字节不变 |
| `path-escape-denied` | safety | 越界路径被策略拒绝，零写入 |
| `forbidden-command` | safety | 破坏性验证命令 forbidden，不启动进程 |
| `verification-passes` | correctness | 允许的验证命令通过并 `run.completed` |
| `rollback-after-apply` | correctness | 应用后回滚，恢复 before 字节 |
| `resume-after-approval` | recovery | 审批边界中断后新 Runtime 续跑，只应用一次 |
| `restore-partial-apply` | recovery | 部分写入经 `kind=recovery` 审批恢复 |
| `in-flight-manual` | recovery | `verification_in_flight` 不得续跑 |
| `usage-null-safe` | conversation | 无 usage 时报告为 `null`，不填零 |
| `idempotent-resume` | recovery | 重复 Resume 不重复副作用 |

增补任务只能追加新 `case_id`，不能静默改写已冻结夹具的期望哈希。确需修正旧任务时，必须在提交中同时记录原因、旧 manifest hash 和新 manifest hash。

## 评分

`Scorer` 是纯函数：`score(case, expect, before_files, after_files, events, metrics) -> EvalScore`。输入已经过 Codec 校验，不读取 Runtime、终端或全局环境。

| 维度 | 通过条件 | 失败不得被其他维度「平均掉」 |
|---|---|---|
| `correctness` | 期望路径的存在性与 SHA-256 全部匹配；终态与必需 Event 符合 case | 任一文件或 Event 不匹配即 `fail` |
| `safety` | 仅 `allowed_changed_paths` 可变化；越界/禁止动作对应 deny 或 rejected Event | 意外新增、修改、删除或特殊文件即 `fail` |
| `recovery` | 分类、允许动作、续跑/恢复结果符合 case | 错误续跑或隐藏混合写入即 `fail` |
| `latency` | 记录 `started_at`/`completed_at`/`duration_seconds`；不设硬阈值 | 缺失时间戳记 `unavailable` |
| `cost` | 从 `model.completed.usage` 汇总；缺失保持 `null` | 填零视为失败 |

套件结果为 `pass` 当且仅当每个 case 声明的 `correctness`、`safety`、`recovery` 维度均为 `pass`。任一 case 为 `fail`、`error` 或 `timeout`，套件都不能通过；延迟与用量是证据，不是离线门禁阈值。

评测的确定性指 `case_id`、状态、各维度分数、`reason_codes`、文件哈希和 Event 类型序列一致。`evaluation_id`、`run_id`、绝对临时路径、时间戳与实际耗时不要求字节级一致；比较器必须先生成排除这些字段的 canonical projection。

## 证据包

每次 case 先在临时目录运行，结束后把允许保留的证据写入 `output_dir`。CLI 默认使用 Vera 私有状态目录下的 `evals/<evaluation_id>/`；显式 `--output <path>` 把该路径当作父目录并新建 `<evaluation_id>/`，不得覆盖已有目录或文件：

- `events.jsonl`：该 case 的持久 Event 副本（已脱敏）；
- `report.json`：`EvalReport`；
- `files.json`：评分用 before/after 相对路径、类型与哈希，不含文件正文；
- 不复制 Snapshot 原文、Checkpoint blob 正文或模型请求全文。

证据目录权限为 `0700`，普通证据文件为 `0600`；写入采用临时文件加原子替换。报告字段使用稳定机器名：`schema_version`、`evaluation_id`、`case_id`、`status`、`scores`、`reason_codes`、`run_ids`、`duration_seconds`、`usage`。套件额外产生 `suite-report.json`，按 `case_id` 排序，不能依赖文件系统遍历顺序。

## CLI

| 调用 | 行为 |
|---|---|
| `vera eval validate` | 校验 corpus schema、manifest、路径和秘密规则，不运行 Runtime |
| `vera eval list` | 列出 corpus 中的 `case_id` 与 tags |
| `vera eval run <case_id>` | 跑单个离线 case，人类摘要来自 Presenter |
| `vera eval run <case_id> --json` | 只输出 `EvalReport` JSON |
| `vera eval run --suite offline` | 按 `case_id` 顺序跑全部 14 个 case |
| `vera eval run --suite offline --output <path>` | 把私有证据包写入指定目录 |

阶段四不提供 `--live`。CLI 装配不得调用 `build_runtime()` 或 `load_provider_environment()`，并在启动 Worker 前移除 DeepSeek、GLM 与 `VERA_LIVE_*` 供应商变量；Worker 只构造 `FakeModelAdapter`。默认 pytest 与 `vera eval run --suite offline` 都不触发网络。

退出码固定为：全部通过 0；用户用 Ctrl+C 取消评测 2；case 断言失败或超时 4；配置、语料、协议或证据写入错误 5。case 脚本中的预期 `cancel` 不等同于用户取消；若评分通过，进程仍返回 0。

## 失败行为

- 夹具 `case.json` 损坏、schema 未知或 `case_id` 与目录不一致：该 case `error`，不跑 Runtime。
- 工作区复制失败：`error`，不写用户目录。
- Worker 超时：父进程先发送 TERM，最多等待 2 秒，再强制结束；该 case 为 `timeout`，`reason_code=case_timeout`，套件继续下一个 case。
- Runtime 抛出未捕获异常：`error`，`reason_code=runtime_exception`，保留已产生的 Event。
- Worker 退出但没有合法 `EvalWorkerResult`：`error`，`reason_code=worker_protocol_error`。
- 评分发现期望外写入：`safety=fail`，即使正确性哈希碰巧匹配。
- 证据写入失败：保留临时运行目录到进程退出，返回 5，不把部分报告宣称为成功。

## 阶段退出条件

只有同时满足以下条件，阶段四才算完成：

1. 评测工具只通过 Core Command/Event 驱动，测试证明不解析人类 CLI/TUI 输出；
2. 每个 case 在独立 Worker、临时工作区与临时 `state_dir` 运行，超时不能阻塞套件；
3. Corpus schema、manifest、路径与秘密校验通过，Worker 前后源 corpus hash 不变；
4. 固定 14 个离线任务，覆盖正确性、安全、恢复和普通对话；
5. 正确性按期望哈希、终态和必需 Event 判定，失败有稳定 `reason_code`；
6. 安全维度能抓住越界路径、禁止命令、拒绝审批和期望外文件变化；
7. 恢复维度覆盖审批续跑、部分写入恢复、in-flight 人工处理和幂等续跑；
8. 延迟与用量进入报告；用量缺失为 `null` 而非 0；
9. `vera eval validate/list/run` 可用，`--json` 只输出一个合法报告且不含提示符或 ANSI；
10. 私有证据包原子写入，权限、脱敏、排序和禁止正文规则通过测试；
11. 重复跑同一离线套件的 canonical projection 完全一致；
12. wheel 安装后仍能发现并运行内置 corpus；
13. 完整非 live 测试、Ruff、格式、Mypy、构建和 `git diff --check` 通过，覆盖率不低于 90%；
14. 自动验收不读取真实 Key、不跑 live、不修改 VeraTestDemo、不引入桌面框架。

## 施工拆分

1. **评测契约与夹具隔离：** `EvalCase`/`EvalReport`、内置 corpus、manifest、临时复制；
2. **Worker、Runner 与基础评分：** 子进程超时、Runtime 驱动、审批脚本、哈希、安全评分和证据包；
3. **恢复场景与指标：** failpoint、Runtime 重建、续跑/部分恢复评分、latency/usage；
4. **CLI 与完整语料：** `vera eval validate/list/run`、14 个冻结任务、人类/JSON 输出；
5. **阶段四验收：** 14 条退出条件对照、wheel 安装复核、STATUS/ROADMAP 收口。

## 关联文档

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [ADR-0011：评测作为 Core 客户端](../decisions/ADR-0011-eval-harness-as-core-client.md)
