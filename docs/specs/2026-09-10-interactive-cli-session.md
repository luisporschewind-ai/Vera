# Vera 交互式 CLI 会话规格

**状态：** Accepted
**日期：** 2026-09-10

## 目标

在现有 `VeraRuntime` 和 Command/Event 契约之上提供可长期运行的内部交互式 CLI。用户进入任意本地代码工程后执行 `vera`，即可把当前目录作为工作区，用自然语言连续发起多个独立编码任务。每个任务必须完整展示工具活动、Change Set、统一 Diff、审批、Checkpoint、写入和验证证据，任务结束后返回输入提示符。

本增量补齐 CLI 客户端和 Runtime 生命周期，不改变 Core-first 架构。CLI 只能发送 Command、消费 Event 和收集用户决定；它不能直接修改项目、伪造状态或绕过审批。未来桌面客户端仍复用同一套 Core 契约，不解析终端文本。

## 用户流程

用户在目标工程中启动 Vera：

```text
cd /path/to/project
vera

Vera 0.1.0
工作区：/path/to/project
模型：deepseek
输入 /help 查看命令，输入 /exit 退出。

Vera > 把页面背景色改为绿色
……读取和搜索事件……

拟修改 1 个文件：
--- a/ViewController.swift
+++ b/ViewController.swift
@@ ...
-view.backgroundColor = .blue
+view.backgroundColor = .green

批准这个 Change Set？输入 approve 或 reject：approve
……Checkpoint 和应用事件……

验证命令：xcodebuild ...
该进程以当前系统用户权限运行，Vera 第一版不提供 OS 沙箱。
批准这条命令？输入 approve 或 reject：approve
……验证结果……

任务完成：run_...
Vera >
```

输入一条自然语言指令只创建一个新 run。任务之间共享当前工作区、模型配置和同一个 Runtime 实例，但不共享完整模型消息历史；模型必须从当前文件状态重新获取上下文。这样可以限制费用和上下文漂移，并保持每个 run 的日志、审批和恢复边界独立。

## CLI 行为

### 启动

- `vera` 不带子命令时进入交互式会话，工作区默认为启动时的当前目录。
- `vera --workspace /path` 可以显式选择工作区。
- `vera --model deepseek` 可以显式选择模型配置；未指定时使用配置中的默认项，只有一个可用项时自动选择该项。
- 启动时展示版本、规范化后的工作区和模型配置名称，不展示 API Key、Base URL 中的凭据或完整环境变量。
- 工作区不存在、不是目录、模型配置缺失或密钥缺失时，在进入提示符前明确失败。
- 空输入不创建 run；终端 EOF、`/exit` 和 `/quit` 正常结束会话。

为了让用户从工程目录直接执行 `vera`，CLI 启动时可以读取私有供应商环境文件。默认路径是 `~/.config/vera/deepseek.env`，也可通过 `VERA_PROVIDER_ENV_FILE` 指定其他文件。解析器只接受已知变量的 `NAME=value` 或 `export NAME=value` 行，不执行 Shell、不展开命令、不覆盖当前进程中已经存在的变量；POSIX 平台上文件存在但组或其他用户可读写时必须拒绝加载。

### 任务驱动

- 每条自然语言输入向同一 `VeraRuntime` 发送一个 `StartRun`。
- CLI 持续消费 Event，直到 run 进入终止状态，或 Runtime 输出 `approval.required`。
- 收到审批请求后，CLI 先展示审批绑定的目标、哈希、风险和完整可审阅内容，再只接受 `approve`、`reject` 或 `cancel`。
- `approve` 和 `reject` 通过 `ResolveApproval` 返回 Runtime；`cancel` 通过 `CancelRun` 返回 Runtime。
- 一个 run 可以连续产生多道审批。每次处理决定后，CLI 必须继续驱动同一个 run，直至终止，不能在第二道审批处退出。
- run 完成、失败、取消或验证失败后，CLI 展示 run ID 和终态，然后返回 `Vera >`，会话本身不退出。
- `Ctrl-C` 在提示符处清空当前输入并保留会话；run 等待审批时第一次 `Ctrl-C` 取消当前 run，再次 `Ctrl-C` 或 EOF 退出会话。

### 内置会话命令

第一版支持：

- `/help`：显示会话命令和审批输入说明；
- `/runs`：按最近事件时间倒序列出 run ID、目标摘要和终态；
- `/show <run-id>`：显示该 run 已脱敏的 Event；
- `/rollback <run-id>`：根据持久化 Checkpoint 请求安全回滚；
- `/exit`、`/quit`：退出会话。

未知 `/` 命令只报告错误，不发送给模型。参数缺失或多余时显示用法，不结束会话。

### 保留的一次性命令

- `vera run "目标" --workspace /path --model deepseek` 继续支持人类终端模式，并复用交互会话相同的多审批驱动器。
- `vera run ... --json` 保持非交互：逐行输出 JSON Event；遇到审批时发送 `CancelRun`，不读取标准输入，也不隐式批准。
- `vera runs list`、`vera runs show` 和 `vera rollback` 保留，内部与会话命令复用相同服务。

## Runtime 与持久化补齐

现有 `VeraRuntime.handle(Command)` 和版本化 Event 契约保持不变。新增的 CLI 会话驱动器只负责重复执行以下循环：

```text
发送 Command
  -> 消费 Event
  -> 遇到 approval.required 时收集决定
  -> 发送 ResolveApproval 或 CancelRun
  -> 继续消费 Event
  -> 直到 run 终止
```

Runtime 必须在审批恢复后继续同一 run。Change Set 审批后可能产生验证命令审批，命令审批后也可能继续后续验证，CLI 不预设审批次数。

`/rollback <run-id>` 必须能在 Vera 重启后工作。它从私有状态目录读取 Checkpoint 清单和工作区根目录，重新校验当前文件与应用后哈希，再调用现有冲突安全回滚能力。它不恢复未完成的模型消息、待审批请求或 Agent 循环；进程崩溃后的 run 续跑仍属于后续阶段。

持久化回滚只能追加 `rollback.completed` 或 `rollback.conflicted` 等新 Event，不能改写已有 Journal。找不到 run、Checkpoint 损坏、工作区不存在或文件已被用户继续修改时，必须明确失败或报告冲突，不能覆盖文件。

## 展示边界

- 人类模式必须优先展示摘要、文件路径、统一 Diff、审批风险、命令参数、验证结果和终态。
- `changeset.proposed` 的统一 Diff 是审批前的权威展示来源；CLI 不能根据文件现状自行重新生成另一个 Diff。
- 普通读取结果默认不输出完整文件内容，只显示工具名称和成功、失败或截断状态，避免终端被上下文淹没。
- JSON 模式只输出 Event JSON Lines，不包含提示符、颜色控制字符或人类说明。
- 所有持久化和展示内容继续经过统一脱敏。

## 安装与调用

开发阶段使用 uv 把当前仓库以 editable tool 安装到用户命令路径：

```bash
uv tool install --editable /Users/admin/Vera
```

安装成功后，在新终端中运行 `command -v vera` 和 `vera --help` 必须成功。CLI 命令使用小写 `vera`；产品名称在文案中仍写作 Vera。

安装流程不能复制 API Key。供应商凭据继续由用户私有环境文件或当前进程环境提供；环境文件内容不能进入 Event、日志、异常详情或终端回显。

## 失败行为

- 模型或只读工具在审批前失败：run 失败并回到提示符，项目文件不变。
- 用户拒绝或取消 Change Set：run 取消并回到提示符，项目文件不变。
- Checkpoint 或写入失败：沿用 Core 恢复语义，展示准确终态后回到提示符。
- 验证命令被拒绝：不执行命令，保留已批准的文件修改和 Checkpoint，并明确显示验证未完成。
- 验证失败：保留修改和 Checkpoint，显示失败证据，允许用户随后执行 `/rollback <run-id>`。
- 供应商网络错误：不自动切换到另一个供应商，不进行 SDK 之外的隐藏重试。
- 单个 run 失败不能导致整个交互会话退出；不可恢复的配置或状态目录错误除外。

## 非目标

本增量不包含：

- 全屏 TUI、鼠标操作、复杂终端布局或逐 Token 流式渲染；
- 多行编辑器、命令历史搜索、自动补全或自定义主题；
- 多 Agent、子 Agent、长期记忆或跨 run 的完整聊天上下文；
- 在提示符中执行任意 Shell 命令；
- 自动批准 Change Set 或未进入安全策略的命令；
- 崩溃后恢复未完成的模型会话或待审批请求；
- Wails、Electron、Tauri 或其他桌面外壳；
- iOS 模拟器或真机的自动视觉验收。

## 验收标准

1. 在临时工程目录执行 `vera`，启动横幅显示该目录的规范化绝对路径，并出现 `Vera >`。
2. 输入自然语言目标后创建一个 run；输入空行不创建 run。
3. Fake Model 产生 Change Set 时，CLI 在询问决定前显示完整统一 Diff 和内容哈希。
4. 输入 `approve` 后 Runtime 创建 Checkpoint 并应用精确字节；输入 `reject` 或 `cancel` 时目标文件保持不变。
5. 同一个 run 在 Change Set 审批之后再产生验证命令审批时，CLI 再次询问并继续处理，直至输出终态。
6. 一个 run 结束后提示符再次出现，可以在同一进程中启动第二个独立 run。
7. `/runs`、`/show <run-id>`、`/help` 和未知命令不会调用模型，也不会退出会话。
8. `/rollback <run-id>` 在新的 Vera 进程中可以从持久化 Checkpoint 恢复文件；文件被后续修改时报告冲突且不覆盖。
9. `Ctrl-C`、EOF、`/exit` 和 `/quit` 按本规格退出或取消，不留下未经说明的写入状态。
10. `vera run ... --json` 遇到审批时保持取消语义，输出中没有提示符或 ANSI 控制字符。
11. 自动测试使用 Fake Model 和临时工作区，不修改 `/Users/admin/Desktop/VeraTestDemo` 或其他真实用户工程。
12. 完整非 live 测试、Ruff、格式检查、Mypy、包构建和 `git diff --check` 全部通过。
13. editable tool 安装后，可以从 Vera 仓库之外执行 `vera --help`；密钥不出现在命令输出、Event 或构建产物中。

## 关联文档

- [Core 安全编辑垂直切片规格](2026-09-10-core-safe-editing-vertical-slice.md)
- [ADR-0001：Python Core 与 Runtime](../decisions/ADR-0001-python-core-runtime.md)
- [ADR-0002：Command/Event 契约](../decisions/ADR-0002-command-event-contract.md)
- [ADR-0003：私有状态与 Checkpoint](../decisions/ADR-0003-private-state-and-checkpoints.md)
- 实施任务和计划在本规格接受后创建。
