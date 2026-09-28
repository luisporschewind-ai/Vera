# 0089 工具链依赖调查与跨语言验收计划

状态：2026-09-28 SDK 查询、SwiftPM、新 scratch 清理及 Intel iOS 假工程最终 SRT backend build 均有通过证据；iOS 审批展示聚焦回归 7 passed。C Xcode 产物清理、实时 CLI iOS build、取消/超时卷清理和 C++/Go/Rust/Java 代表工程尚未验收。当前结论以 [修复实测记录](0089-apple-toolchain-repair.md) 为准，下文早期调查保留为历史。

目标：Vera 面向所有软件项目，macOS 优先不等于 Xcode 专用。本记录是任务 0089 的子记录，不新增或重排任务编号，不取代 Accepted 工作区权限规格；Git 初始化由独立规划任务处理。

## 1. 早期调查结论（后续结果见修复实测记录）

- 2026-09-28 用户批准 xcodebuild 自身二进制临时只读后，developer-access-lltt_ig6：Swift 编译/目录节点探针仍 exit 0，未授权子文件 errno=1；自身信息字典错误消失，xcrun exit 71，DVTLicenseAgreement 报 bundledLicenseInfoPath 断言失败。SDK 查询和 SwiftPM 尚未通过。
- 只读静态核对 DVTSystemPrerequisites 的默认路径实现，确认引用 Contents/Resources/LicenseInfo.plist、Contents/Resources/en.lproj/License.rtf 与 /Library/Preferences/com.apple.dt.Xcode.plist，三份路径均已定位；下一步申请仅这三文件临时只读，非许可证接受操作，不改系统记录。probe-xcrun-license-read.py 已准备且语法通过，新增范围未执行；不承诺这三文件覆盖所有后续动态依赖。证据：[自身读取复验](../evals/artifacts/0089-toolchain-dependency-audit/xcodebuild-self-read-result.json)。


- 2026-09-28 用户批准 DVTSystemPrerequisites 精确文件临时只读后，developer-access-_d16x9sv：Swift 探针编译和运行 exit 0，Developer R_OK 成功、未授权子文件仍 errno=1；xcrun exit 1，从缺库错误推进到“Unable to open executable info dictionary”。没有完成 SDK 查询或 SwiftPM 测试。
- 对本机 xcodebuild 只读反汇编确认：exitIfMinimumOSVersionNotMet 通过 _NSGetExecutablePath 获取自身路径，再调用 CFBundleCopyInfoDictionaryForURL；空返回才打印上述错误。otool -l 显示二进制含 __TEXT,__info_plist 节。现有授权未包含 /Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild 的文件读取，因此将该精确二进制只读作为下一项候选；不是新猜测的独立 plist 文件，也未按错误文案重装 Xcode。候选脚本 probe-xcrun-self-read.py 已准备且语法通过，未执行新增授权。原始结果见 [DVT 复验](../evals/artifacts/0089-toolchain-dependency-audit/dvt-prerequisites-result.json)。


- 2026-09-28 用户要求解决 Apple 工具链阻塞。再次只读核对 DVTSystemPrerequisites 精确二进制的直接依赖，均为已授权 /System 或 /usr/lib 下资源；不能据此断言完整 xcodebuild 动态依赖已满足。已准备带显式授权开关的临时 probe-xcrun-dvt-prerequisites.py，沿用已有工具链、SDK、Developer 目录节点及缓存重定向，仅候选新增这一个二进制读取。语法检查通过，新增权限未执行，等待用户确认。完整 libxcodebuildLoader 仍引用多个动态组件，因此若遇新拒绝将停止并记录，不自动扩大授权。

- 本机 xcrun 默认和显式 DEVELOPER_DIR 的宿主 SDK 查询均成功，无需安装、切换系统开发工具或修改安全设置。
- 实际链路：系统 xcrun → libxcselect → 选定 Xcode 的 libxcrun.dylib；当前 SDK 查询进一步启动 xcodebuild。xcodebuild 的静态加载和动态加载不能仅靠一条 otool -L 枚举完毕。
- 已确认的动态入口包括 Frameworks/libxcodebuildLoader.dylib、SharedFrameworks/DVTFoundation.framework、Frameworks/IDEFoundation.framework。DVTSystemPrerequisites 为当前实际报错的直接依赖。
- 静态候选遍历得到 96 个二进制、68 个 framework 根。26 条未确定的引用涉及 8 个不同名称；下文清单是候选边界，不是“必须全部开放”或真实运行期闭包。扫描优先使用常见 framework 根匹配 @rpath，不能代替 dyld 的实际 RPATH/加载顺序；weak-link、dlopen、插件、服务和资源文件尚需分别核对。
- 未执行这些 framework 的应用逻辑，未增加沙盒权限、安装软件、访问服务、提交或发布。

证据：[依赖图](../evals/artifacts/0089-toolchain-dependency-audit/apple-dependency-audit.json)、[工具入口盘点](../evals/artifacts/0089-toolchain-dependency-audit/toolchain-inventory.json)。工具入口盘点只记录路径、大小，不能据此声明工具可运行。

## 2. 早期批准范围与资源调查（历史快照）

| 类别 | 范围 | 证据和结论 |
|---|---|---|
| 已批准临时基础读取 | XcodeDefault.xctoolchain/usr、MacOSX.sdk、llbuild 精确库、SwiftBuild.framework、libxcrun.dylib、Contents/Info.plist、ToolchainInfo.plist | Swift 直接编译和执行已通过；不覆盖 SwiftPM 全流程 |
| 已批准目录节点读取 | Contents/Developer 的 literal file-read-data | R_OK 通过，未授权子文件仍 EPERM；仅临时诊断后端实现，未纳入产品 |
| 当前确定被拒依赖 | SharedFrameworks/DVTSystemPrerequisites.framework/Versions/A/DVTSystemPrerequisites | 真实 xcodebuild 加载报 blocked by sandbox；尚未授权 |
| 动态入口与静态候选 | 下文逐项路径及依赖图 | 不静默加入配置，需进一步筛选实际所需资源 |
| SDK 与工具链元数据 | 已批准 SDK 内 SDKSettings、精确 ToolchainInfo 与 Xcode Info | 不推导任意父目录或插件权限 |
| 系统临时缓存 | xcrun_db 指向本次专用目录 | 实测生成 16 字节缓存文件，系统临时目录写入错误消失；未修改真实缓存 |
| 构建产物 | Core 准备的 VerificationArtifactPlan.root | 失败场景清理通过；成功构建/测试后的清理还需验证 |

下列属于禁止自动扩大的范围：整个 Xcode.app、整个 SharedFrameworks、真实 HOME、系统临时目录、用户凭据、Keychain/设备/模拟器/网络服务。framework 名称包含这些功能不等于允许使用对应系统能力。

## 3. 原分步验收计划（执行结果见修复实测记录）

1. 按真实入口分别整理 xcrun SDK 查询、SwiftPM、Xcode 最小命令行工程的资源集合，不把三个集合混成全部权限。
2. 核对候选中的 @rpath 歧义、weak-link 与动态入口；输出精确文件、组件资源目录和 literal 目录节点三类清单。尚有歧义时不请求用户批准“完整依赖”或保证一次授权必能通过。
3. 对最终有限清单统一展示用途、递归性、有效期与只读范围，申请一次临时复验。超出已批准清单的需求必须停止，不能沿报错自动放权。
4. 使用假源码和无远程依赖的假工程；禁网、禁签名/设备/模拟器，缓存和产物重定向到专用目录；检查成功、预设失败、越界拒绝与清理。
5. 如仍需额外服务权限或大范围宿主状态访问，记为具体兼容性缺口，另作设计评审；不豁免该产品能力，也不以此阻止其他语言验收。
6. 临时验证成功后才形成产品适配变更：候选涉及 sandbox/settings.py、backend.py、cli_sandbox.py 与 verification/artifact_planner.py、artifact_root.py；先审阅接口与规格，再补失败测试、实现与回归。当前临时 profile 拼接不得直接包装为已发布功能。

## 4. 通用验收矩阵

共同要求：仅假工作区；输出真实退出码；成功及失败分类正确；缓存/产物受控；项目后代同样受限；外部读写拒绝；禁止下载依赖；缺少环境必须单独记录，不能算通过。

| 工程类型 | 最小验收 | 当前事实 | 下一步 |
|---|---|---|---|
| Python | 标准库 unittest，成功/失败、字节码/缓存隔离 | 常用 python3 目标为 0 字节；存在可用于 Core 的完整 Python.app，但不等于项目沙盒已授权 | 先明确选用完整运行时的精确读取集合；不修复或重装全局 Python |
| JavaScript / Node | 内建 node:test，含子进程及失败用例 | 找到 Node 入口；Core 的 SRT 使用 Node 不等于项目命令获得 Node 权限 | 核对运行时依赖，准备无 npm 安装的假工程 |
| TypeScript | 本地 tsc 编译/类型错误，随后测试 | 未核实可用离线 TypeScript 工具链 | 定位现有 tsc；缺失则标记环境缺失，不自动联网安装 |
| C / C++ | 编译小程序、断言、失败退出、产物隔离 | clang 系统入口存在，Xcode 工具链与 SDK 已临时批准 | 使用明确的编译器路径，避免系统入口隐式定位；C++ 另测标准库 |
| Go | 无第三方依赖 go test、编译缓存 | 找到本地安装入口，未执行 | 核对 GOROOT，GOCACHE/GOTMPDIR 指向专用目录，禁自动下载工具链 |
| Rust | 无外部 crate 的 cargo test、target 隔离 | 找到 rustc/cargo 入口，未执行 | 核对 sysroot/链接器，离线执行，不访问真实 Cargo 凭据 |
| Java | javac + 小型断言测试 | 只发现系统 java/javac 入口，未验证 JDK | 先确认真实 JDK；不以系统入口存在当作安装成功，不引入 Maven/Gradle 下载 |
| Swift 直接编译 | swiftc + 原生测试程序 | 已实测通过，含失败和越界拒绝 | 保留证据，不重复 |
| SwiftPM / Xcode | 包测试 / 最小工程构建、Core 产物清理 | SwiftPM 受 xcrun/xcodebuild 依赖限制；Xcode 工程未验 | 独立按有限清单推进，不代表 Vera 只面向 Xcode |

顺序：Node 与 Python 环境核对 → C/C++ → Go/Rust → Java/TypeScript 环境核对；Apple 兼容问题单独推进。以上是当前主流语言基线矩阵，不是永久封闭的语言白名单。Apple Silicon 已明确延期；Linux/Windows、联网授权保持原范围决定。

## 5. 候选 framework 根（只读调查结果，未新增授权）

以下仅方便逐项审核；实际申请可比此清单更小，不默认整目录授权。

- `/Applications/Xcode.app/Contents/Frameworks/DVTNFASupport.framework`
- `/Applications/Xcode.app/Contents/Frameworks/DevToolsCore.framework`
- `/Applications/Xcode.app/Contents/Frameworks/DevToolsSupport.framework`
- `/Applications/Xcode.app/Contents/Frameworks/IDEFoundation.framework`
- `/Applications/Xcode.app/Contents/Frameworks/IDENoticesFoundation.framework`
- `/Applications/Xcode.app/Contents/Frameworks/Xcode3Core.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/AppThinning.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/CodeCompletionFoundation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/ContentDelivery.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/ContentDeliveryServices.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/CoreDocumentation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/CoreSymbolicationDT.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DNTDocumentationModel.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DNTDocumentationSupport.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DNTSourceKitSupport.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DNTTransformer.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DTDeviceServices.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DTXConnectionServices.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTAppStoreConnect.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTDeviceFoundation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTDocumentation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTFoundation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTITunesSoftware.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTITunesSoftwareServiceFoundation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTInstrumentsFoundation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTInstrumentsUtilities.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTKeychain.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTKeychainService.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTKeychainUtilities.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTMacroFoundation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTPortal.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTServices.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTSmartSearch.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTSourceControl.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DVTSystemPrerequisites.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/DebugSymbolsDT.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/IDEDistribution.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/IDEResultKit.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/IndexStoreDB_LLVMSupport.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/IndexStoreDB_Support.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/Localization.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/MallocStackLoggingDT.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/Notarization.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/PackedPaths.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/SourceKit.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/SwiftBuild.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/SwiftParser.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/SwiftSyntax.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/SwiftSyntaxCShims.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/SymbolicationDT.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/Testing.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCResultKit.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCServices.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCSourceControl.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCStringsParser.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCTAutomationSupport.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCTDaemonControl.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCTHarness.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCTest.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCTestCore.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCTestSupport.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/XCUIAutomation.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/kperfdataDT.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/ktraceDT.framework`
- `/Applications/Xcode.app/Contents/SharedFrameworks/llbuild.framework`
- `/Library/Apple/System/Library/PrivateFrameworks/Mercury.framework`
- `/Library/Developer/PrivateFrameworks/CoreDevice.framework`
- `/Library/Developer/PrivateFrameworks/CoreDeviceUtilities.framework`

## 6. 未确定名称

- `@rpath/DVTDarwinup.framework/Versions/A/DVTDarwinup`
- `@rpath/DVTInternalCanary.framework/Versions/A/DVTInternalCanary`
- `@rpath/SWBProjectModel.framework/Versions/A/SWBProjectModel`
- `@rpath/SWBProtocol.framework/Versions/A/SWBProtocol`
- `@rpath/SWBUtil.framework/Versions/A/SWBUtil`
- `@rpath/XcodeKit.framework/Versions/A/XcodeKit`
- `@rpath/libRemarks.dylib`
- `@rpath/libswift_Concurrency.dylib`

## 7. 2026-09-28 继续修复（用户授权后续本问题所需操作）

用户明确授权「接下来的我都批准，你直接把这个问题修复，任务完成」。本轮在临时配置中批准选定 Xcode.app 及开发框架只读、必要系统元数据；不开放真实 HOME、网络、签名、设备或新增系统服务，不修改普通用户配置。前文逐文件等待审批为历史过程，以下为当前事实。

- 已复现 Xcode 26.0.1 的 DVTFilePathEventWatcher 崩溃；内核拒绝日志包含 `/usr/share/firmlinks`，增加该只读文件后 SDK 查询恢复。撤回诊断用 FSEvents Mach 服务规则后查询仍成功，只剩监听不可用提示，产品不增加此服务权限。
- `/private/var/select/sh` 是系统符号链接。路径规范化只保留目标，丢失读取链接节点的权限；拟仅对已批准的这个固定系统链接补充 SYMLINK 类型的 literal 规则，不开放父目录或任意目标。
- 正式修复范围：用户显式选择 Developer 目录并展示基础读取清单；后端仅从该配置产生 DEVELOPER_DIR，xcrun 缓存及 CoreFoundation HOME 使用执行专用目录；保留正式验证器生成的安全缓存变量。继续过滤任意环境、加载器注入与凭据。
- SwiftPM/Xcode 构建尚在验证；SDK 列表成功不等于编译、测试通过。诊断 profile 拼接尚不作为产品完成证据。
