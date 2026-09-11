# ADR-0011：评测工具作为隔离的 Core 客户端

**状态：** Accepted
**日期：** 2026-09-12

## 背景

Vera 已有 Core、恢复、策略和三种 Terminal 呈现模式，但现有 `docs/evals/` 主要记录开发任务是否通过，不能重复衡量一组固定编码任务。若评测解析 CLI/TUI 文本、直接操作 Workspace，或默认调用真实供应商，它会复制产品逻辑、削弱安全边界并产生不可控成本。

## 决策

- 评测工具作为 TUI、Plain、JSON Session 之外的第四个 Core 客户端，只发送既有 Core Command 并消费持久 `EventEnvelope`。
- 第一版只运行随 Vera wheel 分发的 14 个脚本化 Fake Model case，不实现 live Provider 路径。
- 每个 case 使用独立 Worker 子进程、临时 workspace 和临时 `state_dir`；父进程执行硬超时并继续剩余 case。
- Worker 子进程是生命周期与超时边界，不宣称 OS 沙箱；Workspace、PolicyEngine、审批和命令策略继续承担执行安全边界。
- Corpus 使用版本化 Pydantic Codec 和 SHA-256 manifest，禁止符号链接、特殊文件、绝对私有路径、秘密和任意代码加载。
- Scorer 是纯函数，只根据 before/after 文件清单、持久 Event 和指标计算正确性、安全与恢复结果，不读取人类输出。
- 评测证据写入 Vera 私有状态目录或显式 `--output`，只保存脱敏 Event、报告和文件哈希，不复制 Snapshot、Checkpoint blob、模型请求或文件正文。
- 可重复性通过 canonical projection 判断；随机 ID、临时路径、时间戳和实际耗时不参与确定性比较。
- `vera eval` 不调用 `build_runtime()` 或 `load_provider_environment()`；启动 Worker 前清除全部已知供应商变量。

## 后果

- CLI/TUI 文案和布局变化不会改变评分，桌面客户端以后也能复用同一评测契约。
- 固定离线套件可稳定进入默认测试和 CI，不消费真实模型预算。
- 安装包体积会增加少量 corpus 数据；构建测试必须确认 wheel 包含并能发现这些资源。
- 子进程增加协议、超时和清理复杂度，但能阻止单个卡死 case 阻塞整个套件。
- 离线通过只能证明 Core 链路和评测工具符合冻结脚本，不能证明真实模型质量。

## 被拒绝的方案

- **解析 CLI/TUI 输出评分：** 与展示文案耦合，无法成为未来桌面客户端共享的证据。
- **默认运行真实 Provider：** 不确定、收费、依赖网络，并违反当前凭据边界。
- **全部在调用进程内运行：** 无法可靠终止卡死 case，也难以验证重启恢复路径。
- **直接在 corpus 源目录执行：** 会污染冻结夹具，无法证明源数据未被修改。

## 验证与重审触发器

- 必须验证 Worker 超时、退出异常、协议损坏、临时目录清理和剩余 case 继续执行。
- 必须验证 corpus manifest、wheel 资源发现、源 hash 不变和 canonical projection 重跑一致。
- 如果未来引入真实模型评测、并行 Worker 或容器/沙箱，应另立规格和 ADR，不能通过扩展 Fake corpus 静默改变本决策。
