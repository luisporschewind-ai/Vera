# 0089 Apple 工具链实测证据

日期：2026-09-28。真实 Intel macOS/SRT；临时假工程及测试副本。结论见 [修复记录](../../../tasks/0089-apple-toolchain-repair.md)。

- `sdk-result.json`：SDK 查询；没有保留 FSEvents 服务授权。
- `swiftpm-process-result.json`：真实 SwiftPM 编译测试退出 0；`swiftpm-result.json` 保留当时清理失败的结果，不回写成新代码结果。
- `swiftpm-scratch-cleanup-process-result.json` 与 `swiftpm-scratch-cleanup-result.json`：嵌套 scratch 与精确链接节点规则修复后，重新执行假 SwiftPM XCTest；进程 exit 0、1 项测试通过、`cleanup_error=null`，正式产物根已清理且工作区无 `.build`。先前未补链接节点时的 `couldNotFindTmpDir` 失败仍保留在临时夹具 `/private/tmp/vera-0089-acceptance.psEsZR/verification-swift-f0n3esl1`，不混入通过结果。
- `ios-*.json`：iOS Storyboard / CoreSimulator 阻塞证据。
- `ios-service-boundary-diagnostic.json`：新 scratch 布局下，假 iOS 工程仍因 CoreSimulator 服务受限失败；含 `-target` 构建与两个精确 Mach lookup 的只读假 device set 探针的有限事实。另以 `-scheme` 复验仍失败于支持平台解析，见任务记录；不将测试日志中的设备信息写入证据。
- `xcode-native-initial-*.json`：早期诊断命令构建；不是最终生产 Planner 参数证据。
- `xcode-native-final-*.json`：最终 Planner→Runner→SRT 命令行 C 工程构建退出 0；Runner reason_code=sandbox_cleanup_failed；正式产物根已清理、工作区无变更。
- `boundary-result.json`：工作区读取与外部读写/后代读取边界。
- `retained-temporary-roots.json`：只记录本次已识别且仍存在的执行临时根；非全机扫描，不表示其他目录可删除。
- Python probe 和 pbxproj 为本次复现入口，路径绑定当前临时环境，不是产品安装脚本。

本轮聚焦回归 48 passed；Ruff、格式、8 文件 Mypy 通过。没有执行全量测试；未验证 Apple Silicon 实机或 Runtime/CLI 全流程。

## 2026-09-28 系统服务授权方向复验

[授权后最小探针摘要](ios-approved-service-probe.json)记录了隔离环境变量下宿主 `simctl` exit 0、SRT 下五/七个精确 Mach 服务仍 exit -11、假 iOS 工程构建 exit 65 与工作区普通写入对照。只读诊断脚本 [simctl 探针](probe-ios-services.py) 和 [假工程构建探针](probe-ios-build-services.py) 仅用于任务 0089，不属于产品 profile；沙盒进程崩溃时 macOS 自动生成了系统崩溃报告，尚未读取其内容。复跑探针可能再次生成崩溃报告，需按最小试验边界执行。

用户批准后完成的 [iOS 后续诊断](ios-followup-diagnostic.json)：单份 `simctl` 崩溃报告显示 CoreFoundation 日期格式器的 `EXC_BAD_ACCESS`，尚不能证明触发原因；一次递归读取两份 CoreSimulator bundle 的假工程构建消除了 `Malformed bundle` 与 CoreSimulator 连接日志，但仍因 supported platforms 为空和 DerivedData 日志写入 `EPERM` 失败。输出中有 10 个 `Operation not permitted` 文本标记。同版 SRT 工作区边界下，嵌套路径 `touch` 与同目录 `mv` 都成功，故 EPERM 不能归结为一般工作区嵌套写入/重命名拒绝。

产品现在已接通 `apple_ios_build_services` 单次能力：Core 仅为未签名 generic iOS 项目 `xcodebuild ... build` 请求授权，审批绑定服务集合和解析后的可执行路径，展示五个具名服务、后代继承和当前用户模拟器状态风险；默认 profile 仍不含这些服务。固定 SRT 0.0.77 的官方 `allowMachLookup` profile 生成检查通过。授权机制已实现不代表 iOS 构建通过；当前假工程构建仍失败。

## 最新根因与成功证据

`ios-root-cause/` 保存 ICU 最小对照、精确原子写拒绝、专用卷修复写入、运行时目录发现/SimLaunchHost 单变量结果及最终 build exit 0。`build-success-excerpt.txt` 只保留两项 Storyboard 编译与成功标记；未复制其他用户设备信息。`.py.txt` 为当时诊断实现快照，不是当前产品复跑入口。新产品代码未复跑；旧 48/91 项结果不外推最终接入。上文“仍失败”和符号链接写权限猜测均为历史状态，已由最新证据取代。
