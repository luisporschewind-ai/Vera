# ADR-0001：Python Core Runtime 与依赖边界

**状态：** Accepted
**日期：** 2026-09-10

## 背景

Vera 需要先交付 UI 无关的 CLI Core。第一阶段的重点是可检查、可恢复的 Agent 运行时，而不是桌面壳或供应商 SDK 的深度绑定。Runtime 还必须能在本地控制状态、审批、工作区边界、Checkpoint、验证和回滚。

## 决策

- 使用 Python 3.12（`>=3.12,<3.13`）实现 Vera Core。
- 使用薄自研 `VeraRuntime` 作为唯一运行时权威；模型只提供意图，不能直接写文件。
- 使用 `uv` 管理项目环境和跨平台锁文件，提交 `uv.lock`。
- 使用 Pydantic 2 定义可序列化的 Core 契约，使用 Typer/Rich 提供 CLI。
- 使用 OpenAI Python Client 作为供应商传输适配层；DeepSeek、GLM 通过独立的 OpenAI-compatible `ModelAdapter` 接入。
- 第一阶段不采用 Vercel AI SDK、OpenAI Agents SDK 或 LangGraph 作为 Vera Runtime，不让供应商协议类型渗透到 Core 契约。

## 后果

- Python 代码和测试可以直接表达文件、进程、哈希与恢复语义，适合先完成 CLI Core。
- 未来桌面客户端只需消费同一组 Command/Event，不需要复制 Runtime。
- `ModelAdapter` 必须承担供应商请求、响应和 Tool Call 的标准化；Provider Key 不能进入 Event Journal。
- 依赖升级必须经过锁文件、离线测试和规格检查；桌面壳选择延后到 Core 稳定之后。

## 验证与重审触发器

- `uv run pytest`、Ruff、Mypy 和 `uv build` 全部通过。
- 如果 Python Runtime 无法满足性能、发布或跨平台要求，必须新增 ADR 记录证据后再改变语言或运行时边界。
