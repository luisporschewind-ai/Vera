# Core 沙盒替代后端：Intel macOS 只读预检与临时对照

**状态：** 无主机配置变更的预检已完成；临时账号与假数据探针生命周期已结束并清理；Seatbelt profile 启动失败，VM 候选未运行
**任务：** [0085](../tasks/0085-core-sandbox-alternative-backend-probes.md)
**矩阵：** [共同验收用例](core-sandbox-backend-matrix.md)
**环境：** 2026-09-25，开发机 `x86_64`、macOS `15.7.9`，`kern.hv_support=1`

## 预检事实

- 当前普通用户 UID 为 `501`；用户按批准创建临时标准账户 `vera_runner_probe`（UID `502`、GID `20`，组列表不含管理员组），指定 home 为 `/private/tmp/vera_runner_probe_home`。该账户、临时 home、探针 ACL 与假数据根已完成清理，核验账户记录、home、fixture root 与 UID 502 进程均不存在。无沙盒基线下，`/usr/bin/xcrun`、`/usr/bin/git` 和 `/usr/bin/sandbox-exec` 均存在；`xcrun --find swiftc` 找到 `/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc`，系统 Git 报 `2.50.1 (Apple Git-155)`。
- `man sandbox-exec` 在本机把工具标为 `DEPRECATED`。它只用于研究对照；当前证据不能说明其 profile 语法、发行支持或未来版本稳定性满足开源产品后端要求。
- Apple [`VZMacPlatformConfiguration`](https://developer.apple.com/documentation/virtualization/vzmacplatformconfiguration)描述的是 Apple silicon 上的 macOS guest；[Virtualization](https://developer.apple.com/documentation/virtualization)虽可在 Intel Mac 上运行 Linux guest，该路径不能验证本机 Xcode/Simulator 原生项目。`kern.hv_support=1` 仅是硬件接口预检。

## 仓库外假数据对照

临时根为 `/private/tmp/vera-sandbox-alt.XlqgrZ/`，含假 `workspace/`、`artifacts/` 与世界可读的 `outside/fake_secret.txt`；不含真实工程、Provider Key 或个人文件。未创建账户、VM、系统规则或产品代码。所有运行通过本机 `/usr/bin/sandbox-exec`；下表不把该机制视为后端选型。

| 对照 | OS 限制 | 观察 | 结论 |
|---|---|---|---|
| `research.sb` | `allow default`，仅拒绝假 `outside/` 读取与网络 | `xcrun --find swiftc`、`git --version`、workspace 读取成功；假秘密读取和 loopback 连接均报 `Operation not permitted` | OS 可分别拒绝所列动作，但文件权限过宽，**不能**满足共同安全基线 |
| `runner-v5.sb` | `deny default`，只允许系统/Xcode 与假 workspace 读取、artifacts 写入；无网络授权 | `xcrun --find swiftc` 与 `git --version` 返回 0；workspace 读与 artifacts 写成功；世界可读假秘密读取、workspace 写、loopback 出口由 OS 拒绝 | 固定路径的窄配置出现部分正反例；工具命令均报缓存写入失败，不能计作干净的原生工程通过 |
| `runner-v5.sb + xcrun_nocache` | 同上，另传 `xcrun_nocache=1` 并试 `xcrun --no-cache` | 两命令约 10 秒后失败；`xcrun` 转而调用 `xcodebuild -find`，工具链初始化无法读取 SDK；Git 包装器同样无法定位 Xcode 工具并提示安装 Command Line Developer Tools | `Failed`，该变量不能修复当前配置；进程已中断，无证据证明任意 Xcode 项目可构建 |

`runner-v5.sb` 中系统只读范围仍较宽（如 `/Library`、`/private/var`），尚未证明任意用户数据均不可读；没有独立 UID、动态 Grant、真实构建、Git Hook、完整 Core、Broker IPC 或安装态。`xcrun` 和 Git 的失败信息均指向当前 UID 的 `/var/folders/.../T/xcrun_db-*` 缓存创建被 OS 拒绝；即使命令返回 0，也不能据此认为工具链工作流已通过。Apple `xcrun` man page 说明 `xcrun_nocache` 等同 `--no-cache`，但本机对照转为 `xcodebuild -find` 后无法初始化所需 SDK，因此不能靠该变量绕过缓存边界。把当前用户的通用临时目录整体授给 Runner 可能暴露其他应用数据，不作为本轮修复。独立身份的专属临时目录是待验证假设。

本机 `com.apple.sandbox.reporting:violation` 日志确认 `file-read-data` 拒绝假秘密、`file-write-create` 拒绝 workspace 新文件、`network-outbound remote:*:9` 拒绝 loopback。`nc` 单独返回 1 与无监听端口的基线相同，因此网络结论依赖该 OS 拒绝日志，不能仅凭退出码。早期 `deny default` 配置曾令工具以 `SIGABRT` 退出；日志指向根目录 `/` 的 `file-read-data` 被拒绝，补足根目录元数据后才出现上述结果，不把崩溃记为越界拒绝。

早期崩溃使 macOS 自动在当前用户的 `~/Library/Logs/DiagnosticReports/` 写入 `true`、`cat`、`xcrun`、`git` 的诊断文件。这是原型运行的附带产物，未清理或纳入正式证据；后续实验应避免重复触发，并在清理前核对确属本次生成。

临时原始产物的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `research.sb` | `51ed2b6407c0bb3682229a98bb4035f694ab03a51ef874b77e2095d27d660f` |
| `runner-v5.sb` | `cc65d84a3f9f1fc7680657bd719f1770d4acf18850239bdf3382f97dc380acdd` |
| `logs/research-results.json` | `650daae97d4990d8c4a86e90854230bbd9b2d070967e69ef6a059b93e6c62bcf` |
| `logs/strict-results.json` | `f5be579e6cc813337c1095789336a2fa1e7170bb69645fd536b9ece7150fe4e3` |
| `logs/strict-os-denials.txt` | `b88b77e8d33af8921feecbb03550d756a432bb6a7bd8ea6f22470eba1965c2c3` |
| `logs/child-tree-result.json` | `68d5016fc27d4f748eb8f7ed623a711bbf9a6f504996cb0ac9a1153e0f37c5cb` |

这些文件仍在临时根，尚未脱敏入库或发布；清理前应判断是否需要保留可复现夹具。矩阵中 `separate-identity-plus-os-policy` 仍为 `Not run`，上述同 UID 对照不改变其状态。

## 固定路径子进程树对照

2026-09-25 使用仓库外假工程与 `runner-v5.sb` 启动脚本后代（`cat`、`bash`、`nc`）。脚本报告：假秘密读取被拒、workspace 写入被拒、临时 artifacts 写入允许、网络连接被拒；总退出码为 0，artifact 文件存在，源码写入文件不存在。macOS unified log 对应记录分别为子进程 `cat` 的 `file-read-data`、`bash` 的 `file-write-create`、`nc` 的 `network-outbound remote:*:9` 拒绝。该结果证明此固定配置在同 UID 下对子进程树生效；不验证完整 Vera Core、独立身份、任意工具链或产品后端。原始 JSON 保留于临时根，SHA-256 为 `68d5016fc27d4f748eb8f7ed623a711bbf9a6f504996cb0ac9a1153e0f37c5cb`。

## 动态临时路径 Seatbelt 预探针（2026-09-25）

用户解除测试延期后，在 `/private/tmp/vera-sandbox-0082-candidate.0AFSj0/` 创建全新假工程、假秘密和产物目录。按本次假工程路径生成临时 Seatbelt profile，以 `sandbox-exec` 启动项目脚本；脚本再派生 `cat`、`bash` 与 `nc`。初次调用被 Codex 外层执行沙盒以 `sandbox_apply: Operation not permitted` 拒绝，未启动探针；用户授权的重试在假 workspace 作为 cwd 后完成，没有 `getcwd` 干扰。未创建账户/VM，未安装软件，未改系统配置或访问真实凭据。

| 行为 | 实际结果 | 判定 |
|---|---|---|
| 子进程读取 workspace 外的假秘密 | `/bin/cat` 输出 `Operation not permitted`，退出码 1 | `Verified`，文件负例 |
| 子进程写 workspace 内未授权文件 | `/bin/bash` 输出 `Operation not permitted`，退出码 1；目标文件不存在 | `Verified`，写入负例 |
| 写入批准的假 artifacts 根 | 成功，假产物存在 | `Verified`，产物正例 |
| 子进程访问 loopback `127.0.0.1:9` | `nc` 退出码 1；本次 `log show` 未找到可关联的 `network-outbound` 拒绝 | `Not run`，退出码无法区分 OS 拒绝与无监听端口 |

这是同 UID 下、固定 profile 规则针对新的临时路径展开的研究对照，不是受支持 API/发行方式或产品动态 Grant 实现；不能将结果提升为 `command-tree-seatbelt-candidate` 通过。原始 profile、脚本和输出已按授权清理；以下 SHA-256 用于审计并可按相同夹具重建：`runner.sb` `c2811b18875095687af9268fa8a59f884366733a263d222ab5de8ffdb18a74b9`；`project.sh` `057036b93f845507849924b269390e620b45c3e3e4c78fcf06dc8adfc2b00ea8`；`result.txt` `d34a4e4359a4dc36526cf5b363da32f7b7594a3a09eea17cbdfd6425b052d93e`；`secret.err` `38d3fee106e36c5a5b168c4b25de9a23fbd517cc3114a1edd1db4b9efa3d92b0`；`write.err` `9b3f84eb361645389c222ab8abed327c78d2303259e2d37eb969ccc37c7cff99`。

## 命令树 Seatbelt 候选：官方源码只读核对（2026-09-25）

- [Claude Code 沙盒文档](https://code.claude.com/docs/en/sandboxing)明确内置 OS 沙盒覆盖 Bash 等命令及其后代；内建文件工具仍走另一套权限机制。macOS 使用 Seatbelt；这支持 Vera 先划定 Runner 命令树边界的实施顺序，不能证明完整 Core 已受隔离。
- Anthropic 的开源 [Sandbox Runtime README](https://github.com/anthropics/sandbox-runtime/blob/main/README.md)将自身标为 Beta Research Preview，并明确 macOS 实现使用 `sandbox-exec` 启动动态生成的 Seatbelt profile，网络经宿主侧代理端口约束。其默认读取策略是“未列入 `denyRead` 则可读”，因此 Vera 不能照搬默认配置来满足未授权工程和秘密读取的拒绝要求。
- [macOS profile 生成源码](https://github.com/anthropics/sandbox-runtime/blob/main/src/sandbox/macos-sandbox-utils.ts)说明可从公开实现研究规则生成与路径保护，但不提供 Vera 在 Intel、Apple Silicon 上的发行、签名或工具链通过证据。本机 `man sandbox-exec` 已标 deprecated；被其他产品使用并不消除该接口的维护与支持风险。
- 下一证据门槛仍是用仓库外假数据验证原生命令、文件/网络/凭据负例、Unix socket 与后代继承，并检查动态 Grant、工具链缓存、签名安装和升级。用户已解除测试延期；截至本次更新，没有下载、安装或运行 Anthropic 包，也没有创建账户、VM 或改变主机配置。

**结论：** 命令树方向的资料核对与动态临时路径文件/后代预探针完成；`command-tree-seatbelt-candidate` 仍未通过。既有同 UID 对照证明有限文件边界可生效，但网络新证据未归因，`xcrun`/Git 缓存写入失败、动态 Grant、签名发行与 `sandbox-exec` deprecated 风险仍未解决。

## 独立身份候选的主机改动清单（用户已批准，执行完成并清理）

要检验“独立系统身份 + 强制文件/网络边界”，准备了仅针对 Runner 的最小实验清单；用户已批准完整创建、测试和清理生命周期。实际状态如下：

1. 已创建**一个临时、非管理员本地测试账户** `vera_runner_probe`，UID `502`、GID `20`，shell 为 `/usr/bin/false`，home 指向 `/private/tmp/vera_runner_probe_home`。完成基线与启动探针后已删除账号；只读核验无账户记录和 UID 502 遗留进程。
2. 已在 `/private/tmp/vera-runner-0085-account.prFWCK/` 创建假 workspace、假产物目录、世界可读假秘密、独立 TMPDIR 与动态 Seatbelt profile。无沙盒 `env -i` 下该账户可读假秘密，原生 Git 和 `xcrun --find swiftc` 成功。Seatbelt 启动 SIGABRT，文件/网络负例未运行。fixture root、home 和 ACL 已删除并核验不存在。
3. 未改全局防火墙、`pf`、TCC、SIP、Xcode 选择路径、真实项目或现有用户 ACL。`sysadminctl` 删除记录时终止 UID 502 全部剩余进程；随后停止临时账号 launchd 域并清除获批的精确临时路径。没有账户或探针文件遗留。

用户于 2026-09-25 批准按以上范围创建一个临时非管理员账户、运行假数据探针，并删除本次账户、ACL 与临时数据。完整生命周期已于 2026-09-26 完成；结果与残留核验见下节。单账户 Runner 实验即使通过，也仅说明候选值得继续；完整 Core 的第二隔离域、Broker、动态授权、安装态和第二台 Intel Mac 仍须后续实验。若无法说明附加 OS 限制的可维护性，或需要给 Runner 当前用户的宽泛私有缓存权限，应停止该候选，不以 UID 分离本身宣称沙盒。

## 临时非管理员账户执行记录（2026-09-26）

- 无沙盒 `env -i` 基线：UID 502 能读世界可读的合成假秘密；原生 `/usr/bin/git --version` 返回 `2.50.1 (Apple Git-155)`；`/usr/bin/xcrun --find swiftc` 找到所选 Xcode 的 `swiftc`。三项均为 `Verified`，证明假秘密夹具确实可读，且工具在该账户的临时 `HOME`/`TMPDIR` 下可启动。
- 首次 Seatbelt 运行在 `sandbox-exec -f runner.sb` 处以 SIGABRT（退出码 134）终止，项目脚本未进入；同一 profile 改由 `/usr/bin/true` 作为目标也复现 134。故这是目标进程启动阶段失败，不能把文件或网络边界标为通过或失败，相关策略用例记为 `Not run`。
- 下一次只改变一项：删除 `(deny network-outbound)`；`(deny default)` 仍默认拒绝未明确放行的网络。Seatbelt 公开源码参考实现也是在默认拒绝下按需增加网络放行规则，[源码](https://github.com/anthropics/sandbox-runtime/blob/main/src/sandbox/macos-sandbox-utils.ts)。用户原生 Terminal 复测仍在 `sandbox-exec` 启动时以 134 退出；这否证了“显式网络拒绝规则导致崩溃”的假设。当时 profile 崩溃根因尚未确定，后续 PID 日志分析已定位到根路径读取拒绝。
- 后续只读查看两份 macOS 崩溃报告和对应时间窗、按进程 PID 筛选的 `com.apple.sandbox.reporting` 统一日志后，根因已确认：`true`（PID 99648，2026-09-26 10:25:05.949）与 `sh`（UID 502，PID 1778，2026-09-26 11:14:28.350）均被策略拒绝 `file-read-data /`；两份 `.ips` 的 dyld 启动栈都停在 `dyld4::CacheFinder::CacheFinder`，早于目标程序主逻辑。删除网络拒绝规则无效，是因为触发项为文件读取根路径。该 profile 必须允许对字面根路径 `/` 的必要读取/元数据访问；不可用 `(subpath "/")` 放开整棵文件系统。旧临时 profile 已按授权清理，当前不能重新计算其摘要；本机先前的 `runner-v5.sb` 明确加入 `(literal "/")` 后，系统命令可进入执行阶段，这与本次拒绝证据相符，但不能替代该 UID profile 的重跑验证。
- 日志查询只读且限定在两份报告各自的 15 秒窗口与两个 PID；未运行探针、未创建账户/改系统状态。用户于 2026-09-26 决定不采用 `sandbox-exec` / Seatbelt 命令树方式实现 Vera；该路径退出产品候选，以上结果作为历史诊断保留。本机 `man sandbox-exec` 标记 `DEPRECATED`。其余三条待评估路径为独立系统身份 + OS 强制策略、XPC 隔离 Runner、VM 执行域；均未选定或通过完整矩阵。
- 最终清理由用户在 Terminal.app 完成：临时 home 内未发现 sandbox-exec 崩溃报告；先停止仅属 UID 502 的 launchd 域，再由 `sysadminctl` 删除账户（日志确认终止 UID 502 的全部剩余进程），删除指定临时 home 和 fixture root。之后只读核验 `id` 报无此用户、两个临时路径不存在，特权只读 `ps -u 502` 报没有匹配 UID。ACL 随精确 fixture/home 路径删除。未访问真实工程、home 内容、Provider Key、网络外部地址或全局主机设置。

VM 候选尚无适用于 Intel 上原生 macOS 工具链的可执行最小方案；创建镜像、下载 guest 或安装第三方虚拟化软件不在上述请求内。它需要独立方案及资源、许可、共享目录、网络、回滚清单。

## 官方平台候选与待验证边界

## macOS：XPC Runner + 动态工作区书签（候选，Not run）

Apple 说明每个 XPC Service 有独立沙盒；传统 `NSTask`/`posix_spawn` 本身不能为各进程建立独立沙盒。[App Sandbox 文件访问文档](https://developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox)还说明 URL bookmark 可把获准的文件访问传给另一个进程，并可用于用户选择目录及跨进程访问。由此形成一个待验证候选：Core 维持自己的沙盒，独立 XPC Runner 服务执行不可信工程命令，Broker 只传递当次授权所需的 workspace bookmark 与受限 IPC。

以上官方能力不能证明 XPC Runner 能无损运行任意原生工程工具链，也不能证明子进程会只继承所需书签范围。候选必须在隔离测试机上用假工程实测动态 workspace 读写、假 Core/Provider 状态拒绝、工具链命令、脚本孙进程、网络、取消和服务重启；当前 Intel 开发机不运行该实验。

## Linux：Landlock Runner（候选，Not run）

Linux 内核的 [Landlock 文档](https://docs.kernel.org/userspace-api/landlock.html)定义文件层级权限。TCP bind/connect 限制始于 ABI v4、跨线程同步始于 ABI v8、pathname UNIX socket 限制始于 ABI v9、UDP 规则始于 ABI v10；运行时须探测 ABI，缺少共同语义时失败关闭，不能按内核版本字符串猜测。Landlock 目前不能显式约束经 `/proc/<pid>/fd/*` 访问的 pipe/socket 等非用户可见文件对象，因此 Broker/Runner 启动前须明确关闭所有非白名单继承 FD，并把这项列为独立负例。TCP 端口规则不等于固定 Provider 目的 IP；[seccomp 文档](https://docs.kernel.org/userspace-api/seccomp_filter.html)只描述 syscall 过滤，仍需与文件、进程和网络控制组合实测。

## Windows：AppContainer / 实验性 CreateProcessInSandbox（候选，Not run）

[AppContainer 官方说明](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)列出文件、网络、进程和凭据隔离；[CreateAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile)会创建当前用户下的 per-app profile、文件夹及 ACL，属于需要明确生命周期与清理的本机状态变更。另有微软文档记录的 [CreateProcessInSandbox API](https://learn.microsoft.com/en-us/windows/win32/secauthz/createprocessinsandbox)：它目前标为 Windows 11 experimental，使用 `processmodel.dll` 动态查找且没有公开头文件；文档还规定不能继承 handles，并明确 AppContainer 调用方不能再调用它创建嵌套 sandbox，嵌套威胁模型尚未定案。这使 Core/Runner 两层边界需要由沙盒外 Broker 创建 Runner，不能假定被隔离 Core 可自行派生更窄 Runner。

API 的每路径文件授权、network proxy 及失败时拒绝静默降级值得在 Windows 测试机验证，但实验性状态与兼容性尚不足以支持产品选型。上述 Linux、Windows 和 macOS 候选在[共同矩阵](core-sandbox-backend-matrix.md)仍标 `Not run`；官方文档不是运行证据，不得据此推导 `Supported`。
