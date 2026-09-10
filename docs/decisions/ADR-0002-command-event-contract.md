# ADR-0002：Command → VeraRuntime → Event 公共契约

**状态：** Accepted
**日期：** 2026-09-10

## 背景

CLI 是第一阶段的开发和验收入口，未来还会有 Wails 桌面客户端。若客户端解析人类可读文本，展示格式变化就会破坏协议边界，也会让审批和恢复难以验证。

## 决策

- 公共调用链固定为 `Command -> VeraRuntime -> Event`。
- 所有公共 Command、Event、Change Set、Approval 和 Verification Model 使用 Pydantic，并带 `schema_version: 1`。
- Event 使用单调递增的 `sequence`、稳定的 `run_id` 和明确的 `type`；Payload 只包含可 JSON 序列化且已脱敏的数据。
- CLI 人类模式只渲染 Event；JSON 模式逐行输出 Event JSON；未来 Wails 使用同一结构化协议，不解析 CLI 文本。
- Runtime 自己拥有状态转换和顺序保证；供应商 SDK 对象、Rich 对象和终端控制符不能进入 Core 契约。

## 后果

- 可以用 FakeModelAdapter 和临时 Git Fixture 对完整链路做确定性测试。
- Event Journal 能记录审批、应用、验证、失败和回滚证据，并支持 `runs` 查询。
- 契约变更必须增加版本或兼容转换，不能通过悄然改变字段含义解决。

## 验证与重审触发器

- 每个 Command/Event 具备序列化 round-trip 测试。
- CLI JSON 输出能被独立消费者逐行读取。
- 若桌面客户端需要无法由当前 Event 表达的交互，先扩展契约并新增 ADR，再修改 Runtime。
