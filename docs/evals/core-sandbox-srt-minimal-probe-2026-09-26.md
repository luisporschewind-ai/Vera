# Anthropic Sandbox Runtime 最小试验：Intel macOS

**日期：** 2026-09-26
**任务：** [0087](../tasks/0087-core-sandbox-alternative-backend-probes.md)
**授权：** 用户明确回复“允许最小试验，继续验证”；范围为[选型审阅](core-sandbox-selection-review-2026-09-26.md)中的临时安装、假工程、有限本机网络和清理生命周期。
**结论：** `Blocked`。现成 runtime 可启动受限 Shell，但本轮严格读取策略下，系统 Git 的 Xcode 工具链发现和系统缓存访问未通过。原生编译、文件/网络负例、取消矩阵均 `Not run`；未选定产品后端。

## 环境与完整性

- Intel macOS 15.7.9；普通当前用户，从 Codex 外层沙盒之外启动固定 runtime，目标命令仍经生成的 `/usr/bin/sandbox-exec` profile 执行。
- 固定包 `@anthropic-ai/sandbox-runtime@0.0.77`，下载内容的 SHA-512 与事先记录的 npm integrity 一致。安装后的 macOS wrapper、manager、默认路径工具及 CLI 与已核验 tarball 对应文件逐字节一致；对照此前源码检查了关键控制路径，未宣称完整发布源码可复现构建。
- 依赖锁包含 5 包：runtime `0.0.77`、socks5-server `1.0.10`、commander `12.1.0`、node-forge `1.4.0`、zod `3.25.76`；均无 `hasInstallScript`。仍显式关闭安装脚本、audit、fund，所有 registry 地址和 integrity 已检查。
- 安装使用临时 HOME、npm config/cache；下载与安装累计约 64.41 秒，清理前目录约 37.43 MB，均在批准预算内。
- 锁 SHA-256：`7004395779ffd73d4fb42a9d71b094bf4dd90ff55b1bec608a77270045e5fc33`。
- 原始假夹具：`/private/tmp/vera-srt-probe._mev9a5n`，现已删除。可审阅的[证据清单](artifacts/0087-srt-0.0.77-intel-2026-09-26/SHA256.json)保留配置、依赖锁、夹具脚本、实际 profile 和结果；未保存带临时代理认证信息的原始 wrapper 字符串。

## 生成规则的执行前审阅

配置显式禁止根目录树读取，开放 OS/工具链所需候选路径与本次 workspace/artifacts/home/tmp；保留上游的根 inode 和目录 metadata 例外。只允许本次目录写入及上游设备 I/O 条目，并显式拒绝 `/tmp/claude` 与 `/private/tmp/claude`。这些拒绝确实出现在最终 profile 中；未对已有共享目录进行读写探测。

网络配置为空目的地白名单、strictAllowlist；生成规则只开放本次代理端口，未启用通用网络、Unix socket、local binding、Apple Events、weaker network isolation 或 TLS 解密。上游仍有 Mach 服务、共享内存等基础规则，本轮没有验证这些 IPC 能力是否符合 Vera 最终威胁模型，不能声称完整隔离。

初始 profile 已人工读取后才允许试验驱动执行。没有修改 runtime 源码或自动降级为无沙盒执行。

## 实际执行与停止点

| 用例 | 实际结果 | 判定 |
|---|---|---|
| runtime 初始化、生成 profile、启动 `/bin/bash` | 成功输出 `shell-ok`，没有旧探针的 dyld SIGABRT | 仅启动 `Verified` |
| `/usr/bin/git --version`，随后 `xcrun --find clang` | Git 包装器先失败，错误指向 `/var/select/developer_dir` 读取拒绝；`&&` 后的 xcrun 查询未执行 | 工具链门槛 `Blocked` |
| 只读路径归因 | 宿主 `lstat` 返回 Xcode 选择路径 `ENOENT`；`/Applications/Xcode.app/Contents/Developer` 存在；profile 未开放选择路径 | 明确的配置兼容缺口 |
| 一次单变量归因对照 | 保持同一权限配置，只在临时环境添加 `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`；重复 Git/xcrun 查询 | 越过首个错误，但仍退出 69 |
| 对照的新错误 | Git/xcrun 尝试创建宿主 `/var/folders/.../T/xcrun_db-*` 缓存，返回 `Operation not permitted`，并输出 Xcode license 提示 | 临时 HOME/TMPDIR 不足以收敛工具链访问；停止 |
| 编译及运行产物、工作区读写、假秘密、链接、网络正反例 | 在第一道工具链门槛即停止 | `Not run` |
| 取消/超时/多级后代、错误配置失败关闭 | 未进入对应测试阶段 | `Not run` |

归因对照属于已批准的失败后必要诊断，未新增文件权限、切换后端或运行后续矩阵。两次实际命令均远低于单命令 15 秒预算。

## 判断及限制

1. **旧的“Seatbelt 一启动就崩溃”不是本轮阻断。** 现成 runtime 已成功启动 Shell，这只是必要条件。
2. **本轮没有证明原生工具链适配成功。** 严格允许路径集合不完整，工具链对不存在的选择路径及宿主系统缓存仍有依赖。假 HOME/TMPDIR 不会自动重定向所有平台工具的访问。
3. **许可证提示不能直接当成宿主未接受协议。** 它可能与受限环境下的元数据读取或缓存失败有关；本轮没有读取真实许可配置、接受协议或运行修改配置的命令，具体来源尚未验证。
4. **这不是对 Seatbelt 或上游 runtime 的通用不可行结论。** 当前证据否定的是“这份严格配置已兼容宿主系统 Git/xcrun”；文件与网络安全目标尚无本轮实测结果。
5. **后续应先做工具链资源映射。** 区分工具链发现、只读系统元数据、可重定向缓存和不可避免的共享状态；不能通过开放整个 `/private/var`、真实 home 或关闭读取限制来凑通过。若无需额外权限即可重定向，准备确定的单变量复验；如必须访问原批准范围之外的宿主数据或写共享缓存，先列精确范围再申请。未经具体审阅不启动下一轮。

该候选仍值得继续做适配评估，但当前不具备扩大验证或接入 Vera 的通过依据。Vera Core/Broker、所有命令入口、arm64 和安装态均未验证。

## 清理证据

[清理记录](artifacts/0087-srt-0.0.77-intel-2026-09-26/cleanup.json)：本次两个命令进程组和 runtime 路径均无残留；两个先后使用的代理端口均返回 `ECONNREFUSED`。本次临时目录、npm 依赖/cache、假 HOME、夹具全部删除。

未创建账户或 VM，未执行 sudo，未改 Xcode 选择/许可、TCC/SIP、防火墙或真实工程；系统拒绝日志可能保留。上一轮独立的静态源码审阅目录未被当作本轮清理对象。仅更新沙盒文档工作树，未提交。
