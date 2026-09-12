# 任务 0030：桌面进程协议与 Core service

> 供 Cursor 执行：阶段七入口门禁满足后，按测试先行实现框架无关 Core sidecar；不得引入任何桌面框架。

**状态：** Planned
**执行就绪：** 否；等待阶段七入口门禁
**分支：** `phase-7/0030-desktop-protocol-core-service`
**依赖：** 任务 0024、0029 已完成；`ADR-0013`、`ADR-0014` 已 Accepted
**规格：** [阶段七桌面集成](../specs/2026-09-12-desktop-integration.md)
**架构：** [ADR-0014](../decisions/ADR-0014-desktop-core-process-boundary.md)

## 目标与边界

新增与 Wails 实现细节无关的桌面协议、专用 Core service entrypoint、conformance fixture 和 Python onedir 构建基线。只复用最终冻结的 Session/Core 契约，不实现窗口、WebView 或产品 UI。

不得把 `vera --json` 子命令直接当桌面服务，不得解析 Presenter 文本，不得监听本机网络端口。

## 文件结构

- 新增 `src/vera/desktop/__init__.py`：只导出桌面协议公共类型。
- 新增 `src/vera/desktop/framing.py`：Content-Length 帧 reader/writer 与硬上限。
- 新增 `src/vera/desktop/messages.py`：`DesktopEnvelope`、hello、error、snapshot 和 request/response model。
- 新增 `src/vera/desktop/compatibility.py`：协议区间与任务 0024 manifest 协商。
- 新增 `src/vera/desktop/server.py`：I/O loop、单 Session worker、control action 和 bounded queue。
- 新增 `src/vera/desktop/entrypoint.py`：stdout/stderr 纪律、固定参数、退出码。
- 修改 `pyproject.toml`：增加内部 `vera-core-desktop` script；不改变默认 `vera`。
- 新增 `docs/desktop-protocol.md`：wire grammar、message 表、版本与失败语义。
- 新增 `tests/desktop/fixtures/fake_core.py` 与 `tests/desktop/conformance_cases.json`。
- 新增 `tests/desktop/test_framing.py`、`test_messages.py`、`test_handshake.py`、`test_server.py`、`test_lifecycle.py`、`test_conformance.py`。
- 新增 `scripts/build_desktop_core.py` 与 `scripts/measure_desktop_candidate.py`，供任务 0031 复用。

## 接口

### 产生

- `read_frame(stream, *, max_header_bytes=8192, max_payload_bytes=8388608) -> dict[str, JsonValue]`
- `write_frame(stream, payload: Mapping[str, JsonValue]) -> None`
- `DesktopEnvelope`：协议、process/message/reply/sequence/session/operation/type/payload。
- `ProtocolRange` 与 `NegotiatedProtocol`。
- `DesktopCoreServer.run(stdin, stdout, stderr) -> int`。
- `DesktopCoreServer.stop(reason)`：幂等、可由 control loop 调用。
- Fake Core 与 JSON conformance report schema。

### 消费

- 任务 0024 `CompatibilityManifest` 与最终 `ContractCodec`。
- 阶段六最终结构化 `SessionAction`、`SessionSnapshot`、`RuntimeOutput` 和只读查询结果。
- 任务 0022 `OperationReceipt` 或其最终等价接口。
- `build_runtime`、`SessionController`、`Redactor`、`PrivateWriter`。

## 测试先行步骤

### 1. 帧 codec

先写失败测试覆盖：

- UTF-8、多帧粘连、Header 分段、payload 分段和 EOF；
- 8 MiB 边界、超限、负数、溢出、重复 Header、重复 JSON key；
- NaN/Infinity、非对象顶层、非法 UTF-8、未知 Content-Type；
- stdout 恰好只包含帧。

最小实现只能按字节长度读取，不得 `readline()` 整个 payload 或无限分配。

### 2. Envelope 与协商

先写 golden JSON 和 round-trip，覆盖：

- major 无交集失败；
- minor/capability 取交集；
- compatibility manifest hash 不匹配；
- 未知 message type、缺失 operation id、重复 message id；
- 相同 operation id/相同 input 返回同一回执，相同 ID/不同 input 失败。

### 3. Core service 并发边界

I/O loop 独立处理 hello/health/cancel/shutdown；业务动作进入单 Session worker。测试证明：

- 一个 active run，未决审批时拒绝新 prompt；
- Event 顺序不丢，StreamFrame 在背压时只合并不冒充最终 Event；
- queue 超限不会丢持久 Event 或无限增长；
- Renderer 不消费时 Core 能进入可诊断 backpressure，而不是 OOM。

### 4. Session open 与结构化动作

使用临时 Workspace 和 Fake Model：

- hello 前的 session.open 拒绝；
- Core 规范化 Workspace 并返回 identity/权限/Git/恢复快照；
- prompt、审批、Diff 查询、验证、取消、恢复、回滚全部发送结构化 model；
- 测试禁止发送 `/diff`、`/rollback` 等 raw Slash 作为桌面按钮动作；
- Core Event 与现有 CLI 客户端的权威事实一致。

### 5. 生命周期和崩溃夹具

覆盖：

- 10 秒 handshake timeout；
- stdin EOF、idle shutdown、active cancel/shutdown；
- 半帧退出、stdout 污染、stderr flood、假死；
- prompt/approval/写入后/验证四个 crash point；
- 重启后只读 recovery scan，不自动重发。

Fake Core 通过命令行固定枚举选择场景，不接受任意 shell 参数。

### 6. onedir Core 基线

`build_desktop_core.py` 接受显式 source、output、platform、arch 和 version；只写调用者指定临时目录。测试：

- bundle 自带 Python 3.12 与依赖；
- Finder 等价空 shell 环境可启动；
- artifact manifest 包含每个文件 hash、mode、arch 和 license；
- bundle 扫描无 Key/canary、用户路径和 build secret；
- onefile 不成为默认产物。

## 自动验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest tests/desktop -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_desktop_core.py --source . --output /private/tmp/vera-desktop-core --platform darwin --arch amd64 --version 0.1.0
```

随后运行[阶段七共同门禁](phase-7-execution-order.md)。构建脚本不得联网、读取用户 Key 或修改用户 Workspace。

## 验收标准

- 桌面协议、Core 业务契约和持久状态版本完全分层。
- 无桌面框架即可跑完整 conformance 和 crash fixture。
- stdout 零污染，framing/队列/诊断有硬上限。
- 结构化按钮动作不依赖 Slash 或 CLI 文本。
- operation 重放不重复副作用，结果未知不自动重发。
- onedir Core 可作为三框架相同输入。

## 提交

完成并更新证据后：

```bash
git diff --check
git commit -m "feat: add desktop Core process protocol"
```
