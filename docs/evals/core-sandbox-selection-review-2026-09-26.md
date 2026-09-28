# Vera 沙盒剩余候选与可执行路线评估

**日期：** 2026-09-26
**状态：** 架构评估；随后经用户批准执行最小试验，原生工具链门槛 Blocked。结果见[运行记录](core-sandbox-srt-minimal-probe-2026-09-26.md)；未选定产品后端。
**关联：** [0087](../tasks/0087-core-sandbox-alternative-backend-probes.md)、[共同矩阵](core-sandbox-backend-matrix.md)、[Accepted 规格](../specs/2026-09-24-core-execution-sandbox.md)。
**当前请求：** 核查独立身份、VM 两个剩余候选，对齐主流产品的功能和运行方式，提出具体可执行的路线。敏感动作继续逐项申请。

## 结论与证据等级

| 候选 | 结论 | 依据与边界 |
|---|---|---|
| 独立 macOS 账户 + 普通文件权限/ACL | 否决作为独立完整后端 | 既有 UID 502 探针已读到 world-readable 假秘密；账户切换本身没有网络隔离。“再加 OS 策略”尚未指明可交付机制，不构成完整方案 |
| VM 执行域 | 保留；可实施为独立开发环境 | 有成熟虚拟化实现。仍需准备 guest 工具链、数据传输和网络策略；不等于透明使用宿主已有工具链。当前没有 Vera VM 运行证据 |
| XPC + App Sandbox | 不推荐作为通用原生 Runner | XPC 可做 IPC/权限拆分，但不能消除 App Sandbox 的 xcrun 与动态执行授权限制。原探针启动受阻仅是夹具结果，不是这个架构判断的依据 |
| Seatbelt 命令树 | 用户已重新开放现成 runtime 评估；首选验证候选 | 先前失败已定位为自写 profile 的根目录读取拒绝，未证明该系统机制不可用。用户本轮选择“优先原生体验，允许重新评估现成 Seatbelt runtime”；产品后端尚未选定 |

不能把未运行 VM 标为 Failed，也不能把某个 VM 产品能启动 Linux 当成 Vera 完整沙盒已验证。

## 主流产品的实际边界

- [Cursor Run Modes](https://cursor.com/docs/agent/security/run-modes)：macOS 使用 Seatbelt / sandbox-exec 限制命令及后代；不兼容动作可进入单独审查/批准流程。
- [Cursor 工程文章](https://cursor.com/blog/agent-sandboxing)：比较过 App Sandbox、容器、VM、Seatbelt；指出容器的 Linux 工具链限制和 VM 的启动/内存代价，最终采用 Seatbelt。
- [Claude Code 沙盒](https://code.claude.com/docs/en/sandboxing)：macOS 使用 Seatbelt；允许配置不受限重试及不可用时的处理方式，也可禁止回退。并不承诺所有项目命令均在同一严格沙盒中无条件成功。
- [Anthropic Sandbox Runtime](https://github.com/anthropics/sandbox-runtime)：公开 CLI/库，可封装任意进程；macOS 仍调用 sandbox-exec，Linux 使用 bubblewrap。当前 README 标记 Beta Research Preview，需要锁定版本、审阅配置与独立验收。默认读取范围宽，不能照搬为 Vera 的最小读取授权。

因此，“主流产品体验”应具体落实为正常命令可执行、越界有清晰审批、取消与日志可靠、隔离状态真实。Vera 原规格另外要求完整 Core 隔离、限制未授权读取和失败关闭；不能因为参考主流产品就自动删掉这些更强承诺。

## 独立身份为什么不能单独交付

既有[临时账户记录](core-sandbox-alternative-preflight.md#临时非管理员账户执行记录2026-09-26)包含实际正例：UID 502 在空环境和假 HOME/TMPDIR 下成功运行原生 Git/xcrun，也成功读取 world-readable 合成秘密。

这已经否证“换成非管理员账户即可隔离未授权读取”。ACL 只约束配置过的对象；覆盖用户所有现有及未来数据，需要扩大宿主权限管理范围。网络出口还需要另一套强制机制。把这些空缺称为“OS 强制策略”没有解决实现选择。该身份机制可用于 Broker 凭据保护，或受控 VM 内的权限拆分，不选作宿主通用 Runner 的独立后端。本轮无需再次创建宿主账户来重复该基线。

## VM 能做什么，不能据此承诺什么

[Apple Linux VM 文档](https://developer.apple.com/documentation/virtualization/creating-and-running-a-linux-virtual-machine)提供 Intel 和 Apple Silicon 的同架构 Linux guest 路线；[Lima](https://lima-vm.io/docs/config/vmtype/)提供 VZ/QEMU 管理实现。这允许保留同一 Vera Core 契约，在不同宿主架构上运行各自的 guest 镜像。

Linux guest 可承担有 Linux 工具链的项目；不能在其中运行 macOS 的 xcrun/Xcode/Simulator。Apple 的 [VZMacPlatformConfiguration](https://developer.apple.com/documentation/virtualization/vzmacplatformconfiguration)面向 Apple Silicon macOS guest。Intel macOS guest 可以另查第三方虚拟化产品，但必须核对具体 guest/host 版本和 Xcode/Simulator 工作流，不能拿“支持 Intel 宿主”代替“支持目标 macOS guest”。

**本机只读预检：** x86_64、macOS 15.7.9，安装了 Docker Desktop 4.91.0。固定本地 Docker socket `/Users/admin/.docker/run/docker.sock` 不存在，未取得运行中的 daemon；未使用未知或远程 Docker context，未启动 Docker。PATH 未发现 Lima、QEMU、Parallels CLI、VMware CLI 或 UTM CLI；常见 Applications 路径未找到这些 VM App。工具未找到不等于硬件不支持。

Docker Desktop 支持 Intel/Apple Silicon，并不表示名为 Docker Sandboxes 的产品也支持 Intel。[Docker Sandboxes 当前安装要求](https://docs.docker.com/ai/sandboxes/install/)列出的 macOS 架构为 Apple silicon；因此不把它直接指定为 Vera 的双架构统一依赖。

### 可实施的 VM 架构

1. 宿主只有可信启动器、用户审批界面和最小 Broker。Provider Key 留在 Broker；不给 guest 通用宿主命令接口或任意文件接口。
2. 按工作区创建专用 guest/磁盘。只传入批准的工程快照与工具链材料，默认无宿主 home、Docker socket、SSH agent、共享剪贴板和广泛目录挂载。
3. Core 在 guest 内运行；项目命令经更窄 Runner 域。Linux guest 可采用非特权用户、namespace/bubblewrap 等实现，明确隔开 Core 状态与 Runner。macOS guest 的内层 Runner 边界须另设计，不能从外层 VM 通过推定。
4. 首个探针禁网；后续联网须由强制隔离机制限定到代理，代理核验目的地和 Grant。仅设置 HTTP_PROXY 不算网络隔离。guest 默认 NAT 也不等于阻止访问宿主和局域网。
5. 结果经受控通道导出；宿主校验路径、链接、基线冲突和审批后应用 Diff。取消销毁执行域并确认后台后代结束。

该架构有具体实现基础，但改变了“透明使用宿主既有工具链”的体验，镜像初始化、缓存、磁盘和 VM 生命周期成为产品能力。不得把 Linux 项目成功推广为所有 macOS 原生项目成功。

### VM 最小试验与停损条件（未运行）

- 先在专用临时目录准备锁定版本的 VM 管理器与镜像，明确下载源、校验值、许可、实际大小及磁盘/内存/CPU预算，再申请完整创建—运行—清理授权。避开用户现有 Docker daemon，以免启动既有自动重启工作负载。
- 首轮只启一台独立 Linux VM，假工程、无 Provider Key、无宿主目录共享、无宿主 agent/socket 转发；虚拟网卡断开或使用等价的可验证禁网配置。具体启动配置要先审阅，不依赖运行时默认值。
- 正例：同一 guest 内执行 Git、本地解释器任务、编译/运行一个小程序、创建预期产物。负例：读取未传入的宿主假秘密、通过链接越界、直接联网、访问宿主 IPC 均失败；有正常对照及执行域证据，不能把不存在的路径或无服务监听当成全部边界已证。
- 通过后才加入 Core 离线 Fake Model、Runner 内层隔离、代理出口、取消后代和 Diff 回传。测量冷启动、热启动、内存和文件同步后，再判断是否符合产品体验。
- 首轮通过只允许“Intel/Linux guest 原型通过”这一结论；Apple Silicon、macOS guest、真实工程与安装态独立验收。

## 面向本地原生体验的建议（用户已开放候选）

用户本轮明确选择“优先原生体验，允许重新评估现成 Seatbelt runtime”。建议采用 **Vera Policy/Approval → SandboxGrant → 适配层 → 固定版本 Anthropic Sandbox Runtime → Seatbelt 命令树** 作为首选验证路线。Node sidecar 属于后端实现细节；Python Core 和客户端契约不依赖供应商 CLI 文本。

这是对先前排除决定的显式修订，仍属于 Seatbelt 路线。确认仅授权评估方向，不自动授权安装依赖、重启服务、运行新敏感探针或实现产品。原生透明性并不意味着所有工具零配置；需要额外文件、网络或 IPC 的动作仍须申请相应 Grant。

可执行的最小验证顺序：

1. 锁定源码版本/依赖/许可，审阅 macOS profile、网络代理、配置合并与退出行为；配置由 Vera Grant 生成，项目不能自行扩权。
2. 经批准在全新假夹具运行原版 runtime：shell、系统 Git、xcrun 实际工具定位、一个编译并运行的小项目；同时验证假秘密拒读、越界拒写、禁网和孙进程继承。
3. 缺少“正常任务成功 + OS 拒绝证据”任一侧即停止；不把退出码 0、修好 profile 启动或一次工具版本查询视为完成。
4. 通过才把 Bash/Git/验证入口接到同一 Runner，记录后端身份、能力、错误与取消事实。完整 Core/Broker 隔离仍单独实施和验收。

## 固定版本源码审阅（2026-09-26；未执行 runtime）

本轮读取官方仓库与 npm 元数据，在临时目录保存源码供静态核对；没有安装 npm 依赖或执行 runtime。以下是限定范围的源码审阅，不是完整安全审计。

| 项目 | 核对结果 |
|---|---|
| npm 发布包 | `@anthropic-ai/sandbox-runtime@0.0.77`；解包大小 8,810,353 bytes、171 files |
| npm integrity | `sha512-uOe6kkAbo91r5shXXBxZ1DKbOpWmnXkNDDujXrFJRaHSG7D7s8b7Yfsu0pGDkYFgKZ2ECtVCNisl6pCYcaMF7A==` |
| 源码快照 | `ddbeb74711c4097014ef3056791efa83f553116c`，package.json 同为 `0.0.77`；npm 元数据未提供 gitHead，尚未核对发布包与源码等价性 |
| 许可与成熟度 | Apache-2.0；README 仍标 Research Preview，不能从 Claude Code 使用同类机制推定该 npm 包已满足 Vera 的生产门槛 |
| 运行要求 | Node `>=20.11.0`；当前 Node `v21.7.1` 仅满足声明的版本范围，不作为产品发行基线 |
| 直接依赖 | `@pondwader/socks5-server ^1.0.10`、`commander ^12.1.0`、`node-forge ^1.4.0`、`zod ^3.24.1`；需另生成并审阅完整依赖锁，固定顶层版本不等于固定依赖树 |

来源：[npm 元数据](https://registry.npmjs.org/@anthropic-ai%2fsandbox-runtime/latest)、[固定源码 package.json](https://github.com/anthropics/sandbox-runtime/blob/ddbeb74711c4097014ef3056791efa83f553116c/package.json)、[LICENSE](https://github.com/anthropics/sandbox-runtime/blob/ddbeb74711c4097014ef3056791efa83f553116c/LICENSE)。

### 可以继续验证的依据与必须适配的差异

1. **前次启动崩溃有直接对应处理。** `macos-sandbox-utils.ts` 的 `generateReadRules` 明确说明拒绝根 inode 会导致 dyld 在 exec 前中止，并在禁止根树读取时补回 `(allow file-read* (literal "/"))`。这会暴露根目录项名称；另允许目录 metadata 以支持路径解析。不得宣称未授权路径完全不可见。该实现与前次故障相关，但本机能否正常执行仍需实测。
2. **默认允许广泛读取。** CLI 默认 `denyRead: []`，`allowRead: []` 不代表禁止其他读取。Vera 拟明确禁止根树内容，再开放必要 OS/工具链、当次 workspace 与运行资源；额外保留根 inode/目录 metadata 的兼容例外。工作区中明确禁止的假秘密必须仍拒绝，防止宽 allow 覆盖窄 deny。具体允许路径须以生成后的 profile 审阅和正反例为准。
3. **默认写路径有额外范围。** `sandbox-utils.ts` 始终附加 `/tmp/claude` 及其规范路径；仅改 HOME/TMPDIR 不足以收窄。试验必须显式 `denyWrite` 这两个共享路径，设置 `CLAUDE_CODE_TMPDIR` 到本次独占 tmp，并将其加入允许范围；同时检查 HOME 下便利写目录和全部最终规则。若无法完全收敛到批准范围，停止执行。
4. **网络有 OS 限制与代理两层。** 显式设置 `allowedDomains: []` 会启用限制，Seatbelt 仅开放代理所需端口，HTTP/SOCKS 代理拒绝目的地。若省略网络配置，可能没有网络限制；Vera 必须拒绝缺失配置，不能沿用库默认。首轮禁用 `allowLocalBinding`、全 Unix socket、Apple Events、weaker network isolation 和 TLS 中间人功能。`allowLocalBinding` 会开放额外监听和 localhost 连接，不可当作无害开关。
5. **不能把库的每种模式都开放给模型。** `filesystem.disabled` 可关闭文件约束；macOS wrapper 在所有约束都缺失时能直接返回原命令。Vera 只接受由可信适配层生成的完整配置，拒绝这些组合，并核验最终启动确实进入 sandbox-exec；初始化或包缺失时失败关闭。项目内配置不能扩权。
6. **CLI 不替代 Vera 的进程监督。** macOS CLI 仍通过 shell 字符串执行，取消对直接 child 发信号，部分信号退出映射为 0；不能据此证明整棵进程树被终止。适配层须保持参数边界、脱敏事件、真实取消/超时结果、进程树清理，并检测后台与新 session 后代。首轮只运行固定假命令，不接受模型拼接命令。
7. **Runner 通过仍不证明 Core 隔离。** runtime/代理作为可信后端辅助进程先独立运行，Core/Broker 的受限启动、动态 Grant 与凭据 IPC 另行设计和验证。后续 Linux 可评估其 bubblewrap 后端；Intel 成功不能代替 arm64 或 Linux 实测。

源码依据：[macOS profile](https://github.com/anthropics/sandbox-runtime/blob/ddbeb74711c4097014ef3056791efa83f553116c/src/sandbox/macos-sandbox-utils.ts)、[默认路径与环境](https://github.com/anthropics/sandbox-runtime/blob/ddbeb74711c4097014ef3056791efa83f553116c/src/sandbox/sandbox-utils.ts)、[配置与启动](https://github.com/anthropics/sandbox-runtime/blob/ddbeb74711c4097014ef3056791efa83f553116c/src/sandbox/sandbox-manager.ts)、[CLI 生命周期](https://github.com/anthropics/sandbox-runtime/blob/ddbeb74711c4097014ef3056791efa83f553116c/src/cli.ts)。

## 下一步最小试验申请范围（历史申请，现已执行）

用户随后明确回复“允许最小试验，继续验证”，批准以下生命周期。本轮在原生工具链门槛停止，完成一次必要归因对照和清理；下列后续用例没有自动获得通过。详见[运行记录](core-sandbox-srt-minimal-probe-2026-09-26.md)。

**准备和影响范围：**

- 只在新建 `/private/tmp/vera-srt-probe.<随机值>` 内下载固定包、生成依赖锁、解包和安装依赖。使用临时 HOME、npm cache/config；禁用安装脚本、audit/fund 和全局安装。只向 npm registry 下载，执行前核对顶层 integrity、锁中依赖完整性和发布代码与已读源码的关键差异；不自动换版本或修改上游源码。
- 预算：临时目录最多 500 MiB；下载/安装总超时 180 秒，各命令最多 15 秒、编译最多 60 秒，总运行最多 5 分钟；单次测试执行树、最多两个临时 loopback 服务。超过预算或出现预料外写路径立即停止。
- 运行可能需要从 Codex 外层沙盒之外启动，避免嵌套沙盒干扰；目标命令仍由本次 runtime 的 Seatbelt 约束。以当前普通用户运行，无 sudo、账户、VM、守护服务、系统配置或真实工程改动。OS 可能正常产生进程/拒绝日志；不承诺机器完全无痕。
- 假工程与假秘密分离；`env -i`、临时 HOME/TMPDIR/编译缓存、固定可信 PATH，不读取真实 home、npmrc、Keychain 或凭据。读取宿主系统工具链是验证原生命令的必要授权；不运行真实工程脚本。
- 先审阅完整生成配置/profile，尤其是默认附加写路径、IPC 和代理出口；不能满足批准范围则不启动命令。运行期间不测试公网或局域网目标，仅使用本次自己的 loopback listener；不启用证书生成/导入或 TLS 解密。

**顺序和停止点：**

| 次序 | 正例 | 负例与通过要求 |
|---|---|---|
| 1 启动/原生工具 | shell、系统 Git、xcrun 定位工具、假 C/Swift 小程序编译并运行，产物位于本次目录 | 实际生成 sandbox-exec profile 并进入命令树；启动失败则停止，不进行无沙盒补跑来充当通过 |
| 2 文件与后代 | 假 workspace 读写、artifacts 写入；无约束假数据基线成功 | 孙进程读 world-readable 假秘密、写夹具内未授权目录、通过符号链接越界均拒绝；失败须有 syscall/OS 对应证据，路径不存在不算拒绝 |
| 3 网络 | 本次 loopback 服务的无约束基线成功；临时代理允许固定假目标时能取得固定响应 | `allowedDomains: []` 时代理拒绝；清空代理环境后直连活跃监听端口仍由 OS 拒绝。允许一个目标时另一个仍拒绝。若库拒绝 loopback 作为代理目标，记录能力限制，不改成公网测试 |
| 4 生命周期与失败关闭 | 固定多级后代启动并记录本次 PID/身份 | 取消、超时后全部本次后代停止；错误/缺失配置或初始化失败不得执行哨兵命令。不把 CLI 退出 0 当成清理成功 |

首个门槛失败只做必要归因，记录后停止，不再进行无边界的 profile 调参。对“正常执行 + OS 拒绝 + 后代清理”均取得证据后，才扩大到包管理器、自装工具、Grant/Broker、更多 IPC/FD/链接边界和两种架构安装态。

**清理：** 仅停止本次明确记录的服务和进程树；先确认无后代残留，再删除本次清单内的临时目录，保留脱敏命令、profile、版本/锁哈希、结果和必要拒绝证据到本工作树。不得按进程名称批量 kill 或删除已有 `/tmp/claude`。清理遇到权限或身份不明即报告，不扩大操作范围。

**试验前判断：** 值得做上述最小试验；尚未证明可用于 Vera 产品。该路线具备具体代码、发行包和原生 OS 执行入口；缺口集中在 Vera 策略适配、生命周期与验收，不能仅以“成熟产品也用 Seatbelt”取代这些证据。
