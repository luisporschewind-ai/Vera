# 交互式 CLI 会话验收记录

更新日期：2026-09-11

## 结论

交互式 CLI 的本阶段离线实现、仓库外启动和真实 iOS 工程人工验收通过。用户现在可以从工程目录执行 `vera` 进入持续会话；自然语言任务、重复审批、Diff 展示、Checkpoint、验证、历史查询和跨进程安全回滚均复用同一个 Core 契约。

自动验收没有读取或使用用户的 DeepSeek API Key，没有运行 live 测试，也没有读取或修改 `/Users/admin/Desktop/VeraTestDemo`。随后由用户本人在本机终端使用其私有配置完成真实 DeepSeek 与 iOS 工程人工验收；该操作不是自动测试，也未向 Agent 暴露 API Key。

## 用户人工验收证据

- 日期：2026-09-11；执行者：用户本人。
- 工作区：`/Users/admin/Desktop/VeraTestDemo`。
- 启动方式：进入工程目录后执行 `vera`，CLI 正确显示规范化工作区并进入持续提示符。
- 任务：读取 `ViewController.swift`，把 `viewDidLoad` 中的背景色从 `.green` 修改为 `.red`。
- 发现过程：模型依次使用 `list_directory`、`search_text` 和 `read_file`，然后调用 `propose_changeset`。
- 审阅证据：CLI 展示完整 `.green -> .red` 统一 Diff 和内容哈希 `ffd3799135c47ec0dacf37a1f29d7792bbd338d793c2a324be8e6a81fc47bc1f`。
- 写入边界：用户明确批准 Change Set 后创建 Checkpoint，再应用文件修改。
- 验证边界：`grep -n backgroundColor VeraTestDemo/ViewController.swift` 被单独展示并再次取得用户批准。
- 结果：验证状态为 `passed`，run `run_98492fd8757646058118201dfd612db2` 以 `completed` 结束并返回 `Vera >`；用户确认实际结果符合预期。
- 同次操作发现：输入普通问候 `Hello` 时，模型完成请求但没有提出 Change Set，当前 Runtime 以 `no_changes_proposed` 失败；普通对话正常完成语义列为下一增量。

## 自动验证证据

- `uv run pytest -m "not live" --cov=vera --cov-report=term-missing`：84 项通过、2 项 live 排除。
- 覆盖率：89%；交互会话目标测试 6 项通过。
- `uv run ruff check src tests`：通过。
- `uv run ruff format --check src tests`：通过。
- `uv run mypy src`：通过。
- `uv build`：通过，生成 sdist 和 wheel。
- `git diff --check`：通过。
- 非 live 测试的全局 fixture 会清除供应商变量，并把 `VERA_PROVIDER_ENV_FILE` 指向测试临时目录中的不存在文件。

## 仓库外启动证据

- `uv tool install --editable /Users/admin/Vera`：成功。
- `command -v vera`：`/Users/admin/.local/bin/vera`。
- `/private/tmp/vera-cli-acceptance` 中执行 `vera --help`：成功，列出 `run`、`rollback`、`runs`、`config`。
- 使用假的占位供应商配置启动交互会话，只执行 `/help`、`/runs`、`/exit`：成功；未发送自然语言任务，因而没有模型请求。
- 启动横幅显示规范化工作区 `/private/tmp/vera-cli-acceptance`，并出现持续的 `Vera >` 提示符。

## 规格验收标准

1. 通过：临时工程启动显示绝对路径和 `Vera >`。
2. 通过：空行不创建 run，自然语言输入创建独立 run。
3. 通过：审批前展示权威统一 Diff 和内容哈希。
4. 通过：Fake Model 覆盖批准写入、拒绝和取消不写入。
5. 通过：同一个 run 可连续处理 Change Set 与验证命令审批。
6. 通过：一个 run 终止后返回提示符，并可启动第二个独立 run。
7. 通过：`/runs`、`/show`、`/help` 和未知命令不调用模型。
8. 通过：新 Runtime 可从持久化 Checkpoint 回滚；后续编辑时报告冲突且不覆盖。
9. 通过：提示符 Ctrl-C 保留会话；审批 Ctrl-C 取消当前 run；EOF 和退出命令正常结束。
10. 通过：JSON 一次性模式遇审批自动取消，不输出交互提示符。
11. 通过：自动测试只使用 Fake Model 和临时工作区。
12. 通过：非 live 测试、Ruff、格式、Mypy、构建和 Diff 检查成功。
13. 通过：editable tool 可从仓库外执行；自动验收仅使用假的占位 Key，用户人工验收使用其本机私有配置且 Key 未暴露。

## 已知限制与后续人工验收

- Vera 第一版的验证子进程使用当前系统用户权限，没有 OS 级沙箱；CLI 会在命令审批前明确提示。
- 进程重启后支持手动回滚，但不恢复未完成的模型消息或待审批请求。
- 真实 DeepSeek 驱动的 iOS 源码修改与命令验证已由用户本人通过；模拟器或真机视觉自动验收仍未纳入本阶段。
- 仓库尚未配置 Git remote，因此本阶段只能本地合并，不能推送远程。
