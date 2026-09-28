# 0089 Unix socket 禁用边界补验

状态：人工运行通过（2026-09-27）。用户输出与 us-l6qeopdg/result.json 一致：前后对照均 exited/0 并读取 UNIX_FAKE_ONLY；中间真实 SRT 客户端 exited/1、stdout 空、CONNECT_ERROR errno=1 Operation not permitted。连接计数在沙盒后保持 1，最终为 2，server_errors 为空。入口报告临时监听已关闭，助手另行确认 work/s.sock 不存在。下文保留复现步骤。

## 范围和对照

临时入口位于 `/private/tmp/vera-0089-acceptance.psEsZR/run-unix-socket-check.sh`。使用同版本完整 Python.app 解释器加载现有 Core；不修复共享 Python、不修改正常配置。用户输入 approve 后创建唯一 us-* 目录和其 work/s.sock，仅监听自己创建的 AF_UNIX socket，不使用 TCP/UDP、不连接已有系统 socket、不请求真实系统服务。

socket 位于授予读写的测试工作区，客户端与 socket 均可从文件范围访问，因此不能用工作区外路径拒绝代替通信边界。服务端只发送 UNIX_FAKE_ONLY 换行；同一个 Perl 客户端顺序执行无沙盒对照、实际 SandboxedSupervisor/SrtBackend、无沙盒复核。前后对照使用最小环境，不继承 Provider 凭据。此入口不经过模型或产品 CLI 审批 UI。

## 操作

普通终端执行：

```bash
/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/run-unix-socket-check.sh
```

看到 Type approve 后手动输入 approve，等待自动完成。若误输入空行，NOT_STARTED 表示未运行，不能判为通过。

通过条件全部满足：

1. BASELINE_BEFORE：退出码 0，stdout=UNIX_FAKE_ONLY 换行，服务收到 1 次连接。
2. SANDBOX：status=exited，非零退出，stdout 空，stderr 为 CONNECT_ERROR 或 SOCKET_ERROR 且 errno=1（EPERM）；仅后端错误、工具缺失或超时不能计通过。
3. BASELINE_AFTER：退出码 0，stdout 同前，证明服务仍有效。
4. 沙盒执行后连接总数仍为 1，最终总数为 2，无服务异常，排除沙盒实际连接成功。
5. PASS 总结及 CLEANUP：关闭本轮监听、移除自己创建的 socket，保留 result.json 和客户端供核对。

异常或非预期结果停止并保留输出，不连接其他服务重试、不改变策略。本用例只证明该工作区 Unix stream socket 的连接拒绝，不外推所有 IPC、Mach 服务或其他 socket 类型。

## 文档边界

新有效对照和拒绝证据已更新任务 0089 与 STATUS，替代此前“对照无效、待补验”的当前状态；旧探针仍作为历史记录保留。本轮没有连接系统现有服务，不外推所有 IPC 类型。
