# Core 联网资料检索实施记录

**状态：** Ready for manual acceptance（2026-09-28；仅静态检查，未跑回归或真实服务）

**依据：** [Core 联网技术资料检索方案](../specs/2026-09-24-core-web-research.md)；2026-09-28 用户要求阶段十一前规格实现，授权代码提交与合入 `main`，并明确由用户在 `main` 测试，本任务不运行回归。

## 编号和工作树

`main` 上并行任务编号仍在合并，先用主题名记录本任务，待所有并行工作稳定后统一分配编号，不重命名或覆盖其他任务文件。本任务由当前会话在独立工作树实施。

## 决定

- 首版选择 Tavily 的 Search 与 Extract 固定 API；Core 公共工具只暴露服务中立字段。若当前用户随后指定其他服务，以用户选择为准。
- `VERA_WEB_RESEARCH=1` 显式开启；未开启时零工具注册、零检索状态创建。开启但未配置 `TAVILY_API_KEY` 时工具返回稳定配置错误，不回退到其他联网路径。
- 每个 `web_search`、`web_read_result` 调用均为 `network_access` 和 `external_service`，必须单次审批。审批界面显示真实查询或已检索 URL；这两个字段随 `approval.required` 进入本地私有 Run Journal。查询和正文不进入其他公开事件或 Trace，正文只进入私有 Run 状态及现有模型工具消息。后续如引入远程事件订阅，须先做字段分级投影。
- 单 Run 最多 3 次搜索、5 次读取；每次最多 5 个结果；单次正文 8 KiB，累计 40 KiB；请求超时 10 秒。请求前扣预算，超时后不自动重试，避免恢复重放产生额外费用。
- 来源默认未验证为官方；结果始终标记外部不可信，引用必须使用本次返回的规范 URL。网页正文中的指令无授权效力。

## 文件职责和实施步骤

1. `web_research/contracts.py`、`store.py`：检查出站参数、规范化公开 HTTPS URL，私有 Run 状态和预算。检查：静态类型、格式与差异空白。
2. `web_research/provider.py`、`service.py`、`tools.py`：固定服务端点、响应归一化和两个 Core 工具。检查：静态类型、格式与差异空白。
3. `tools/executor.py`、`policy/permissions.py`、`runtime/approval_flow.py`、`runtime/tool_flow.py`、`bootstrap.py`：Run 绑定、每次审批、外部内容标记与显式开关。检查：静态类型、格式与差异空白。
4. 更新规格、状态和任务索引，审阅最终差异后提交。用户在 `main` 执行回归、真实服务和产品验收；本任务不据此声称人工验收完成。

## 待用户验收

- 检索公开官方文档、依赖版本、非私密报错，以及找不到可靠来源的负例。
- 审批卡显示的实际出站内容、关闭后无联网工具、预算和引用、断网/超时/额度、恢复后不自动重发。

## 当前核对

- `ruff check`：本任务触及的 Python 文件通过。
- `mypy src/vera`：254 个源文件无类型错误。
- Python 3.12 `compileall`：本任务触及的 Python 文件通过。
- `git diff --check`：通过。
- 按用户要求未运行回归测试、真实 Tavily 请求或 dogfood；上述静态结果不等于产品验收。
