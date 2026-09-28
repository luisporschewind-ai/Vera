# 任务 0089：工作区权限沙盒实施

**状态：** In progress

**2026-09-28 最新：** [Apple 工具链修复实测](0089-apple-toolchain-repair.md)：最终生产 SRT backend 下 Intel 假 iOS 工程 Storyboard build exit 0；APFS 产物卷卸载清理、外部读取拒绝、审批展示 7 项回归及审批拒绝零执行均通过。0089 整体仍 In progress；活动边界见下表。
**规格：** [Accepted 工作区权限沙盒](../specs/2026-09-26-workspace-permission-sandbox.md)
**授权：** 2026-09-26 用户确认方案并要求实施；本轮项目执行默认禁网，联网能力后续规划。Native 执行方法沿用已有选择，不重复申请实施许可。提交、合并、安装到真实用户环境和敏感宿主操作另按既有边界处理。
**工作树：** `/Users/admin/.codex/worktrees/workspace-permission-sandbox/Vera`；基线 `5b6d789`，包含阶段八 ToolExecutor、Bash、原生 Git。主线未提交的权限档位规划和原沙盒文档工作树保留。与主线最新 0084/0085、ADR-0022 避免冲突，历史沙盒任务在本工作树映射为 0086/0087/0088、ADR-0023。

## 实施约束

- 2026-09-27 用户明确要求：因暂无 M 芯片 Mac，Apple Silicon（arm64）实机测试延期封存，移出本轮活动验收项，不阻塞当前 Intel macOS 验收与本轮任务收口。保留双架构支持目标；arm64 状态为未验证，不视为通过，待设备可用且用户重新安排后恢复测试。其余验收门槛保持有效。
- 先文件授权契约与测试，再后端与执行入口；权限缺失失败关闭，不用 mock 通过推定 OS 验收。
- 本轮不提供网络 Grant、代理启动或网络审批；OS 命令网络默认拒绝，Core 的既有 Provider 通道不传给命令。
- 外部授权只读/读写、一次/会话明确区分，不持久恢复额外会话权限。项目不能自行注册权限。
- 原规格的完整 Core/Broker 独立 OS 隔离不再是首版门槛。既有危险动作审批、Diff/恢复、凭据防护继续适用。
- 固定版本 SRT 使用其已有 macOS profile 生成接口，禁网模式不启动网络代理。上游包缺失、版本不匹配、生成失败或平台不支持均不得启动原命令。

## 执行步骤

1. **统一文件权限契约。** 新建 `src/vera/sandbox/access.py`：会话绑定工作区、请求与批准、撤销/清理、一次授权消费；绑定规范路径和资源身份。`tests/sandbox/test_access.py` 先证明未授权拒绝、只读不能写、批准 A 不开放 B、一次消费、会话撤销、符号链接和目录替换不可扩大授权。
2. **禁网执行适配。** 新建 `src/vera/sandbox/backend.py`、`src/vera/sandbox/srt_bridge.mjs` 和固定依赖清单。后端接收 `ProcessRequest` 和已授权根，输出受限 argv/env；复用 `ProcessSupervisor` 监督，不接收项目自定义 profile。`tests/sandbox/test_backend.py` 验证缺依赖不启动、参数保真、默认禁网、专用 HOME/TMP、受保护路径和错误分类。
3. **连接 Core 入口。** 在现有 ToolExecutor/Runtime 审批与执行路径绑定会话权限，文件访问与命令采用同一范围；Git 和验证共用受限进程入口，消除验证的直接 subprocess 旁路。对外部文件修改仍保持既有变更计划和恢复流程。增加 Core 集成用例，检查拒绝前未读取内容、授权后只开放批准范围、恢复不复活权限。UI 使用 Core 的结构化审批和状态。
4. **复验及交付状态。** 跑相关聚焦回归、Ruff/Mypy、差异检查；在已批准的假数据边界内准备 OS 验收入口。需要新宿主敏感动作时先完成全部可离线验证工作再申请。Intel/arm64 安装态及未运行项逐项记录，不宣称平台整体支持。

## Review Focus

未经批准的文件内容不能在风险分析/预览阶段读取；符号链接或目录替换不能改变已批准对象；一次 Grant 不得被其他操作复用；缺失 runtime 不得变成无沙盒执行；Core/Provider 状态和网络能力不能泄漏给命令。网络错误不得走文件权限批准路径。

## 当前验收对齐（2026-09-28，优先于下方历史待验措辞）

任务保持 In progress；以下为当前状态，下方执行记录保留历史过程，旧的“待验”不得重新当作活动清单。

| 项目 | 当前证据与状态 |
|---|---|
| 工作区读写、越界读写、链接及子进程边界 | Intel 人工通过 |
| 单文件 read/read_write、内建/Bash 一致性、相邻文件拒绝 | 人工通过 |
| 审批拒绝、write/edit Diff 预览、模型审批事实及压缩历史 | 人工通过；模型偶发解释偏差另记，不等于权限失效 |
| session 重启失效、整体/单条撤销、内建 read once | 人工通过 |
| 目录 read/read_write session 含子目录 | 人工通过；内建创建、Bash 子目录创建及读回成功，相邻 write/Bash 写入均拒绝且目标不存在 |
| Bash once 精确参数、工具绑定、消费后失效 | 人工通过 |
| 后端不可用时失败关闭 | 独立配置的 runtime 缺失/版本错误人工验收通过；其他初始化失败不据此外推 |
| 真实 SRT 超时、取消、运行中撤销和后代清理 | 正常结束、超时后继续执行、同进程组父子超时清理人工通过；独立 Core+真实 SRT 主动取消及运行中撤销通过；CLI Ctrl+C 清理与返回输入已补修；用户在批准命令后取消并继续查询权限的交互验收通过。未覆盖逃离进程组。Plain 运行中撤销存在交互限制 |
| 命令禁网 | IPv4/IPv6 loopback 实测通过；工作区 AF_UNIX stream 连接拒绝补验通过，前后有效对照、服务端连接计数均符合预期 |
| 原生 Git、构建/测试及缓存产物全流程 | 已有假仓库 Core/SRT 状态、Diff、版本、精确提交、重复计划幂等、分支创建/切换、log/show 通过；外部及私有状态读取、Git 配置/Hook 写入仍拒绝。Swift 直接编译、两个断言、预期失败、模块缓存及产物越界拒绝通过；正式 VerificationArtifactPlanner→真实 SRT→VerificationRunner 的 Ruff 成功/失败/越界拒绝、报告生成清理及工作区不变已通过；新临时目录布局下 SwiftPM XCTest 1 项、产物及 scratch 清理复验通过，原生 C Xcode 构建曾成功但整体清理失败，尚未按最新 scratch/产物策略复验；iOS 假工程现已在最终生产 SRT backend build exit 0，审批结构/展示回归 7 passed、拒绝零执行。Apple 服务能力由 Bash 单次审批触发；实时 Vera CLI 人工构建、取消/超时期间卷卸载尚未验收。普通 Ruff VerificationRunner 成功/失败/越界拒绝闭环已通过，但未覆盖 Apple 服务能力。git init 转独立规划，CLI Git 交互和特殊 Git 场景未据此外推；普通配置未保存临时授权 |
| 最终回归与证据收口 | 本轮 iOS 生产 backend + 审批定向验收及 Ruff/diff-check 已通过；仍需有限的 Xcode C 清理复验、Apple build 实时 CLI 与取消/超时卷清理。两项 wheel 安装 smoke 受离线 openai 缓存缺失阻塞，属于打包/安装门槛，未安装依赖、不算通过；不跑全量。见 [CLI 收尾记录](0089-cli-final-acceptance.md) |
| 跨语言工程覆盖 | 已建立 [工具链调查与跨语言验收矩阵](0089-toolchain-acceptance-plan.md)，覆盖 Python、JS/TS、C/C++、Go、Rust、Java、Swift；Python 修改与四项 unittest、Vue 修改与离线构建、Swift 直接编译已通过；Intel iOS 假工程经最终 backend build 成功；C 命令行 Xcode 构建成功但清理未按最新策略复验；C++、Go、Rust、Java 等仍未验收。Apple 兼容性单独推进，不缩减产品范围 |
| Apple Silicon | 用户明确延期封存，非本轮阻塞项；Linux/Windows 与联网授权不纳入本轮 |

### 本轮新增人工证据

- 2026-09-27 按用户要求完成 Apple 工具链只读静态依赖调查并建立跨语言矩阵。候选遍历 96 个二进制/68 个 framework 根，26 条未确定引用涉及 8 个名称；包含 @rpath 歧义、未找到路径，尚不构成完整动态运行期依赖清单，也未获新增权限批准。原始依赖图与入口盘点保存在 docs/evals/artifacts/0089-toolchain-dependency-audit；详细资源分类、缓存重定向、分阶段验证及跨语言状态见 [验收计划](0089-toolchain-acceptance-plan.md)。未执行新增 framework 应用逻辑、安装软件或修改系统。
- 2026-09-27 用户批准 Developer 目录节点临时只读后，候选 literal file-read-data 规则实测通过：`developer-access-nohrkulm/result.json` 显示 stat/F_OK/R_OK/X_OK 均成功；未授权子文件 usr/share/man/man1/xcrun.1 打开失败 errno=1。该规则仅在临时诊断后端追加，未修改产品后端或普通配置。随后 xcrun --sdk macosx exit 71，涉及系统临时目录缓存写入拒绝及 xcodebuild 的 DVTSystemPrerequisites 加载拒绝，尚未成功定位 SDK。
- 同一已批准读取范围内追加显式 SDK 绝对路径与 `xcrun_db=假workspace/xcrun-cache` 的诊断：`developer-access-r1cr3fhv/result.json`，目录节点/子文件边界仍符合预期；缓存写入错误消失，但 xcodebuild 仍因 DVTSystemPrerequisites 不可读失败。没有开放系统临时目录或新增 framework。这是可行的缓存重定向候选证据，不代表 SwiftPM 或正式验证流程通过；不执行报错中的系统切换建议。
- 2026-09-27 目录检查根因已精确定位：本机 libxcrun.dylib 的只读反汇编显示报错之前调用 access(path, 4)，即 R_OK。在当前全部已批准权限下，`developer-access-0vpr5324/result.json` 的原生 Swift 探针实测：stat 成功、F_OK 成功、X_OK 成功，R_OK 返回 -1/EPERM。不是笼统的“缺少目录元数据”。已准备临时后端追加单条 `allow file-read-data (literal Developer绝对路径)` 的候选试验，仅匹配目录节点（可允许列出该层名称），不递归授权子文件；同时验证未授权子文件仍无法打开并复测 xcrun。尚未获批或执行此新增权限，未改产品后端/普通配置。
- 2026-09-27 用户批准 libxcrun.dylib、Xcode Contents/Info.plist、ToolchainInfo.plist 三文件临时只读后复验：`verification-swift-ah4xcnij/result.json`，SwiftPM exit 1，内部 xcrun exit 74，stderr 为 developer directory '/Applications/Xcode.app/Contents/Developer' isn't accessible (Operation not permitted)。错误已越过缺失入口阶段，但不能宣称 SDK 定位成功；测试未开始。Runner status=failed、cleanup=cleaned、workspace_mutations=[]，产物根移除且无 .build。libxcrun 导入 access/stat/opendir/realpath；尚未确认具体被拒系统调用，不能仅从错误推断只需 metadata 权限。当前目录 read 授权为递归范围，不直接加入 Developer 整目录以绕过该检查；新增更细粒度目录访问适配需明确设计和批准。普通配置未改变。
- 2026-09-27 xcrun 只读调查：`nm -u /usr/bin/xcrun` 显示调用 _xcselect_invoke_xcrun，otool 显示依赖 /usr/lib/libxcselect.dylib 与 libSystem；本机 Developer/usr/lib/libxcrun.dylib 存在，直接依赖仅为已有系统范围内的 CoreServices/CoreFoundation/libSystem。宿主默认与显式 DEVELOPER_DIR + --no-cache 的 SDK 查询均成功，返回 MacOSX26.0.sdk（链接到已批准的 MacOSX.sdk）；不需要据错误提示安装或切换系统配置。库字符串引用 SDKSettings.plist、ToolchainInfo.plist 与 Xcode Contents/Info.plist。准备精确补充这一个 dylib、Contents/Info.plist、XcodeDefault.xctoolchain/ToolchainInfo.plist 三文件的临时只读复验，尚未批准执行；这只是待验证最小集合，不宣称已枚举完整运行期依赖。现有 SDKSettings 位于已批准 SDK 内。Swift/SwiftPM 仅为跨语言矩阵的一类样例，不缩减通用 Coding Agent 产品范围。
- 上述显式 DEVELOPER_DIR 诊断的进一步核对：宿主上的 Developer/usr/bin/xcrun 也不存在，因此该报错不能判为“真实存在但未授权”，更不能据此申请无效路径。需继续核对 xcrun 在该 Xcode 安装下的实际定位/依赖机制，暂不追加猜测权限。
- 2026-09-27 用户批准 SwiftBuild.framework 临时只读后复验：`verification-swift-ngtiplif/result.json` 显示库加载阶段已越过，但 SwiftPM 的 `/usr/bin/xcrun --sdk macosx --show-sdk-path` 访问 /var/select/developer_dir 被 EPERM 拒绝，exit 1、status=failed。随后同一权限范围内仅加显式 DEVELOPER_DIR 的诊断（不代表正式 Planner 输出）在 `verification-swift-afgb0eap/result.json` 中报 `/Applications/Xcode.app/Contents/Developer/usr/bin/xcrun` 不存在；后续宿主核对同样不存在，未将其当作新增授权目标。两次均 cleaned、workspace_mutations=[]、产物根消失、无 .build；没有执行报错中的 sudo/install/switch 建议。SwiftPM 成功验收仍未完成，新增文件访问须另行批准。
- 2026-09-27 VerificationArtifactPlanner → VerificationRunner → 真实 SRT 的 SwiftPM 验收已执行：`verification-swift-dtwcg9fs/result.json` 记录 status=failed、exit_code=-6，swift-package 加载 SwiftBuild 组件内 SWBBuildService 被拒；测试未开始。artifact_cleanup_status=cleaned、workspace_mutations=[]，独立检查专用产物根已移除且 workspace/.build 不存在，因此只确认本次失败处理与清理。只读依赖核对显示 swift-package 及 SWBBuildService 依赖同一 SwiftBuild.framework 下多个 SWB 组件；已准备可选该组件目录临时只读参数，待用户批准，不自动扩大范围。Xcode 工程与 SwiftPM 成功运行仍待验。
- 2026-09-27 用户批准 llbuild 精确文件临时只读后复验通过：`/private/tmp/vera-0089-acceptance.psEsZR/swift-build-h8kot57j/result.json` passed=true。compile exited/0、stdout/stderr 空；两个断言输出 SWIFT_TESTS_PASS count=2、exit 0；预设失败输出 EXPECTED_TEST_FAILURE、exit 7；生成的原生程序越界读写均 exit 13 / EPERM / stdout 空，外部写入目标确认不存在。假 workspace/build/module-cache 内生成 26 个缓存文件，编译产物位于 workspace/build/probe。普通配置不变，无依赖下载、系统设置变更或真实工程修改。本次是 Core/SRT 直接编译与执行，不能外推 Xcode 工程、VerificationRunner、CLI 或所有工具链路径均已验收。
- 历史首次 Swift 编译夹具 swift-build-esru1q5l/result.json：仅工具链与 SDK 授权时，swift-driver 的 llbuild 加载被拒、exit -6。后续按用户追加批准仅允许 `/Applications/Xcode.app/Contents/SharedFrameworks/llbuild.framework/Versions/A/llbuild` 只读，未开放整个 SharedFrameworks。
- 后端故障：版本错误 `run_10725e192e9f47798040090c24a2ca43` 的用户输出为 approve 后 status=error、error_code=process_error、exit_code=null、stderr=sandbox_version_mismatch；宿主检查目标不存在。缺失场景 `run_6c73c12cacf347139c46966dcaef88ef` 的独立 state-missing 日志确认精确 cp 参数、approval.resolved=approve 和 process.completed 为 error/process_error；保存的当轮回复报告 exit_code=null、stderr=sandbox_unavailable，用户宿主检查确认目标不存在。两项通过，不把模型文本当作原始进程载荷，不外推其他初始化异常。
- 目录只读：授权前拒绝 `run_2ea6b7e293624b29ac9dfcf8c263c660`；目录授权 `run_f13619159d9a46f8ac5aa49938ab56d1`；根文件/子文件 read 成功 `run_ff85b88529634b94a3c1b630a03b9609`、`run_c6211d0bfa174ee686d8536a0a6111e6`；Bash 子文件成功 `run_b62dc8e7aced454289fe1a2ca5b0ead7`；范围外 read/Bash 拒绝 `run_5078df6cc75544ad818ea106e4f9c884`、`run_4d0359b4476146b0b7cefe5080feebf4`；写入拒绝 `run_422c6c1a80ac445184cfa2ed4ada8f09`。宿主只读检查确认 nested/should-not-exist.txt 不存在。
- Bash once：授权 `run_f2b9b32e09ff4b33ae36a5836de471f2`；timeout 6 与绑定的 5 不符，拒绝且授权仍在 `run_754cc3e71ff8435e92f98a18615e0480`；read 不可借用 `run_09e4cff05c224ff49781e03f6ade047b`；匹配命令首次成功 `run_27e6523d9d074b53ac4656aafa23d5fd`；权限列表清空后第二次拒绝 `run_8ccdf4e0cc954c9c928d7122958adcc3`。read 失败时模型引用旧目录授权的解释不准确；实际拒绝及后续授权消费符合预期，不标记模型表达完全无误。
- 原始用户输出附件标识：目录 `4e8b955c-be6d-4e98-a693-7e8e5e69a8a7`，Bash once `2b4b5475-8743-4374-a51b-836974e986d1`；以上 run ID 用于关联本地验收日志，不将模型自由文字当成权限记录。

### 环境与下一项

- 用户批准 Git 临时复验后，已通过真实 Core/SRT 状态、Diff、版本及外部读取拒绝对照。首次复验发现子 Git 仍选择系统入口，补固定 PATH 选择及失败测试后复验成功；只授权一个 Git 文件，未开放父目录。最终相关回归 58 passed（30.89 秒），原配置未改变。细节见原生 Git 验收记录；不外推完整 Git/工具链或 CLI 验收。
- 历史首次[原生 Git 预检](0089-native-git-acceptance.md)未通过：native-git-m3nrvti4 假仓库宿主 status/diff 正常，当时 SRT 下误报 git_not_repository；实际为 xcode-select 探测被 EPERM 拒绝。已由上方修复与临时授权复验更新。
- Unix socket [补验](0089-unix-socket-acceptance.md)已通过：us-l6qeopdg/result.json 与用户输出一致，前后基线均成功，中间真实 SRT 返回 CONNECT_ERROR errno=1、退出码 1、stdout 空；沙盒后连接数 1、最终 2，服务无异常。仅测试工作区内假 AF_UNIX stream 服务；临时监听已关闭且 socket 路径已确认不存在。替代历史无效对照的当前待验结论，不外推全部 IPC。
- [目录读写授权补验](0089-directory-write-acceptance.md)已通过：session_39293ee09e1b4529bd7309f08b8d69e4 下，内建创建、Bash 子目录创建及两结果读回成功；相邻 write 被 file_access_approval_required 拒绝，相邻 Bash cp 被 EPERM 拒绝，宿主检查确认目标不存在。各 run ID 见补验记录。Unix socket 亦已补验通过；当前下一项为原生 Git 与选定工具链构建/测试可用性，随后最终回归；CLI 运行中交互缺口继续保留。
- 主动取消/运行中撤销已准备独立 Core+真实 SRT 验收入口 run-lifecycle-control.sh（位于原临时验收根目录），--check 预检通过；主动取消 control-cancel-hw8z1z29 人工通过（cancelled/-9，父子 37919/37920 在触发后 2.056 秒内均消失，早于自然退出），运行中撤销 control-revoke-4ucopa9n 亦通过（授权前置读取成功，revoke 后 cancelled/-9，父子 38122/38123 在 2.053 秒内消失，后续 cat 被 EPERM 拒绝）。用户手动 approve/Enter 后分别触发取消事件或 AccessSession.revoke；检查父子清理，撤销后再验证假文件读取被拒。未经过 Runtime ApprovalGate/CLI 交互，因此即使通过也不关闭 Plain 运行中撤销 UI 缺口，详见生命周期验收第 6 节。
- 真实沙盒父子清理第二轮人工通过：run_d4ef7a30bca94e47af3fc754158dbfb7 返回 timed_out/timeout、exit_code=-9；监视器先观察 parent=37379、child=37380 均存活，再确认两 PID 在启动后 7 秒内消失，早于 20 秒自然退出上限。夹具父子忽略 SIGTERM、保持同进程组；不外推逃离进程组、手动取消或运行中撤销。步骤和证据见进程生命周期验收第 5 节。
- 共享 Homebrew Python 3.12.2 的 bin/python3.12 于本轮检查时为 0 字节，Vera 原虚拟环境链接受影响。疑似终端记录被粘贴为重定向命令，原因未作确定归责。共享安装尚未修复、重装或升级。
- 临时启动入口 `/private/tmp/vera-0089-acceptance.psEsZR/start-vera-recovery.sh` 使用同安装内完整的 Python.app 解释器及原虚拟环境；帮助、版本检查与后续用户交互成功。不代表全局 Python 已恢复，也不将本问题归为沙盒缺陷。
- [后端故障人工验收](0089-backend-failure-acceptance.md)的缺失/版本错误两项已通过。[真实 SRT 进程生命周期验收](0089-process-lifecycle-acceptance.md)的正常结束、超时、超时后继续使用人工通过：run_4dbc5e27e39e4b7cbead830182245bb9、run_30fef936ab9d4408bd6eceacaeb1624e、run_f538863a7ebe492eb73f088f2f89ee1c；超时返回 timed_out/timeout、exit_code=-15。同进程组父子清理现已补验通过；主动取消已由独立入口补验；运行中撤销也由独立入口补验通过；目录 read_write 授权边界亦补验通过，CLI 交互缺口仍保留。
- 本轮只对齐文档与准备验收夹具；没有产品代码修改，没有提交、合并或推送。

## 执行记录（历史，当前状态以上表为准）

- 模型事实修复人工复验通过（用户提供 DeepSeek 原始 CLI 输出）：当轮批准关联 `run_4cd15d8dfe164c9798905a82a0e551a6`、文本格式与正确字节数 `run_8c57204cb0a64937826525b991b442ed`、跨轮历史 `run_c1f86e56fbaf4fd1b14f9cdb8758c54a`、命令拒绝 `run_5ff08e8fbb2246b1ae50687000483a4c`、区分两条审批 `run_f2ed9a90ca2a4ca5a43cfe0d972f09b6`、压缩后保留决定 `run_cac4bdd2a98f4b3cb4f9d03b86a91989`。此前助手验收步骤中的 byte_count=14 为计数错误，已更正为 15；代码测试按 UTF-8 实际长度计算无误。任务 0089 仍 In progress，其余未验项不因此通过。
- 2026-09-27 模型事实保真修复：用户授权制定并执行[修复计划](0089-model-facts-repair-plan.md)。当前工具结果新增 Core 审批关联（approval_id/action_id/decision）；read/read_file 将文件文本直接封装，并显式区分 text/json/empty。普通工具轮次也保留 Core 事件白名单形成的有界历史摘要，包括审批决定、工具结果、授权 ID。历史只用于解释，不恢复权限；旧记录不伪造补全。
- 新增跨轮、UTF-8/转义/截断、历史容量、持久化/压缩重载及重启后拒绝越界访问的回归。独立复核发现压缩事实只在内存补全的缺口，已修复为持久化最终摘要，新增测试先失败后通过。最终组合回归 `405 passed`，Ruff、格式、Mypy（232 个源文件）、差异检查通过。真实 Provider 多轮表达仍待人工复验，未提交/合并。
- 补记人工验收：单条撤销 A 后内建与 Bash 读取 A 均被拒，而 B 两入口仍成功（`run_fd6461513f0046f3b035821e27ba510d`、`run_9d8d86a7e3294ec0b0df86cb6296274f`、`run_b7d6b0904461495e93f45e1c976d52ba`、`run_e9bbd25ee63244ec82ee4ff0e6015bda`）。write 审批预览拒绝后内容不变，重新提交批准后应用，edit 审批预览与恢复复读均正确（`run_72dd47270e6940ef94f2fb96fabc2ab7`、`run_ade848e6ef0a4759858b2e1fab215b91`、`run_1ebc66d880034d0697597f469f294d44`、`run_c4a59383a4634c9582f922a0a9498c74`）。Core 行为与审批展示通过；模型否认历史/审批和误读包装的问题由上述修复处理，尚不宣称真实模型复验通过。
- 单文件读写授权人工验收通过：A 获批 read_write/session（`run_52fbb0d3dbbe4fc29fb6ca1985c7b66b`），write 修改 A 成功（`run_aecd149b27fb4923be5ad0e037f91a4b`），Bash 读到新内容（`run_26f43ef2b9bc42c9ba4efb3be4bc1dc1`），相邻未授权 B 的 write 被拒（`run_7e602104dfd547f699c775e2093dab56`），edit 恢复 A 并复读确认原内容（`run_2e6b3da0f442409c92a71247f572fc15`、`run_819d4beb81ae46ec992b20a3402c3add`）。模型自述额外添加 target_tool/target_arguments，作为参数遵循偏差保留；当前 session 授权仍以路径、读写模式和期限界定，不将该附加字段解释为只允许 read。
- 同组发现 write/edit 审批仅显示工具名、缺少可审阅变更。修正 ToolExecutor.approval_description：直接使用已有 mutation plan 输出目标路径、操作和 unified diff，不由客户端重新计算、不增加预读，也不改变授权或执行规则；Plain 沿用脱敏和终端字符净化。两个外部文件 Runtime→审批→Plain 回归先失败后通过，并确认批准前内容未变。相关 `tests/sandbox tests/runtime/test_write_edit_tools.py tests/runtime/test_tool_executor.py tests/cli/test_presenter.py` 共 `53 passed`；审批展示留待用户重启后人工复验。文件边界功能通过与审批展示待验分别记录。
- 2026-09-27 后续人工验收：拒绝命令审批正确显示 `approval_rejected`（`run_f308c9a512894e22b0501b31ead9389e`）；重启后旧授权失效（`run_dbf626075f8c4b5ba8ef22b8c37dedde`）；只读授权写入被拒且复读 A 内容不变（`run_debd9b4c0f0a4c66bc675e0c2f27be8c`、`run_370206f2eac8420bb572a3f7864b7d0e`）。内建 read 读 A 成功、读 B 被拒、write/edit 写 A 被拒、复读不变均由用户提供原始 CLI 输出确认。单次授权 B 首次读取成功、再次读取被拒且权限列表为空（`run_8ed4ada68eb640bca9395cc8daddd4b9`、`run_641395aad21e494f9ed5d9ff2fe0ae2b`）。整体撤销后内建 read 与 Bash 均拒绝读取 B（`run_31bf864693c8474cafc4dfae00274fbe`、`run_18df2f03440b446681d7b45691406f43`）。这些新证据更新下文较早的待验状态，不代表任务整体验收完成。
- 本轮修复 `/permissions revoke-file <grant_id>` 被通用单参数校验阻止的问题，并更新帮助。新增解析器→真实权限处理器用例，先复现失败，再确认只撤销 A、保留 B；人工验收待用户重启后安排。
- 运行中撤销通路已有实现：AccessSession 撤销活动授权触发取消事件，SandboxedSupervisor 将事件传入严格进程组监督器。本轮补真实父子进程测试，确认撤销后父子均结束，包括忽略 SIGTERM 的进程。只运行假数据临时目录进程，没有系统配置变更。测试后端为透传夹具，因此证明 Core 取消及进程组清理链路，不作为 SRT OS 隔离证据；Plain CLI 运行中无法交互输入撤销命令仍是交互限制，运行中撤销端到端人工验收未完成。
- 本轮 `tests/sandbox tests/session tests/process` 共 `121 passed`；Ruff、格式检查通过。未提交、合并。
- 规格已按用户最新确认收窄并接受；实施工作树已创建，原工作树均保留。
- Ruling：按本次明确实施授权连续执行，使用上述短计划组织工作；不按技能通用模板再次申请相同实施许可，不创建未授权提交。
- 会话权限、文件 I/O、ToolExecutor/审批、Bash/Git/验证进程、恢复与 CLI 状态/设置已接通。单次授权绑定目标工具和参数；会话授权不写入恢复状态。默认命令禁网，缺失/错误 SRT runtime 失败关闭。provider 密钥默认路径及显式路径已纳入私有根保护。
- Intel macOS 假数据探针：工作区内读写通过；越界读写、符号链接逃逸、子 Shell 越界读取被 OS 拒绝；批准只读文件后仅可读目标，批准读写后目标可写；IPv4 与 IPv6 loopback 被 OS 拒绝。Unix socket 探针因基线工具自身失败而未验证。原始证据见 [`docs/evals/artifacts/0089-workspace-permission-sandbox-intel-2026-09-26/`](../evals/artifacts/0089-workspace-permission-sandbox-intel-2026-09-26/)。
- 回归：`PATH="/Users/admin/Vera/.venv/bin:$PATH" uv run --offline pytest -q tests/sandbox tests/process tests/tools tests/verification tests/runtime tests/test_bootstrap.py tests/pty/test_permissions_v2.py tests/refactor/test_public_imports.py` → `253 passed, 1 warning`。`tests/sandbox tests/pty/test_permissions_v2.py tests/refactor/test_public_imports.py` 聚焦复跑 → `30 passed, 1 warning`。
- 静态检查：`ruff check --no-cache src tests`、`ruff format --check src tests` 通过；Mypy 在 232 个源文件上通过。`git diff --check` 通过。
- 独立终审指出默认与显式 Provider 凭据路径未列入 private roots，以及目录替换竞态可能重定向授权；已各自补回归用例并修复。原子替换期间，仅由可信 Core 按临时文件描述符身份更新匹配的会话授权；一次授权仍在操作开始时消费。
- 验收边界：当前仅有 Intel macOS 假数据 OS 证据；Apple Silicon、Xcode/Swift 真实命令全流程、Git 使用场景生命周期与 Unix socket 均未完成端到端验收。本实现不声明这些项目已通过，不安装或更改真实用户环境。
- 人工走查修正：用户报告 `/permissions` 仍显示 `no OS sandbox`。根因是权限投影固定 `os_sandbox=False`，没有读取 Runtime 的受限进程入口。已让 `/permissions` 与 `/status` 共同消费注入的 supervisor，新增 `sandbox_state` 区分未接入、未配置、已配置与后端未确认。已配置仅代表命令必须走 OS 沙盒入口，执行时仍检查 runtime、版本、平台和权限；不代表 OS 探针通过。未配置明确显示项目命令禁用，工作区 trust 保持独立含义。
- 本轮验证：新增两项状态闭环用例先失败后通过，覆盖 Plain/结构化事件和 `/status` 一致性，并用不存在的 runtime 路径证明不会把配置状态表述成已验证。相关 `tests/sandbox tests/session tests/cli/test_session.py tests/cli/test_session_presenter.py tests/pty/test_permissions_v2.py` 共 `133 passed, 1 warning`；Ruff、格式、Mypy（232 个源文件）通过。未运行新 OS 探针，未提交或合并。
- 人工验收 5.1：用户提供真实 Bash 读取 `inside.txt` 的成功输出（退出码 0，stdout `INSIDE_ONLY\n`）。5.2 尚未验证：模型拒绝调用 `cp`，随后经用户交互改走 `write` 创建副本，不能作为命令写入隔离的通过证据。
- Ruling：按阶段八命令策略与当前工作区沙盒规格，区分普通内容编辑与用户明确指定的结构化命令执行。修正旧系统提示词对所有文件修改使用 `write/edit` 的笼统要求，明确复制/构建/格式化命令可提交 Core 决策，仍受 Policy、Approval 与执行边界约束；专用 Git、提权等硬拒绝保持适用。验收不得擅自替换工具或把等价输出当作原执行证据；命令不承诺内建编辑的恢复保证。此修正不调整任何 Core 放行规则；模型是否按要求调用仍须实测，提示词不是安全边界。
- 提示词修正验证：不可信内容、项目指令、Bash 和外部文件授权相关回归 `25 passed`；Ruff、格式和差异检查通过。临时目录内对精确 `cp` 参数进行 Core 决策检查：未批准不调度，批准后仅一次模拟调度；没有执行真实 OS 命令。5.2 留待用户重启后以新目标 `inside-copy-bash.txt` 复测。
- 后续人工结果：用户确认 5.2 的 Bash `cp` 和副本 `cat` 均成功；5.3 越界读、5.4 越界写、5.5 链接越界和 5.6 `find -exec cat` 子进程读取均返回 OS 权限拒绝。5.4 另有宿主只读检查确认目标路径不存在。5.2 前额外调用 `ls` 仍作为调用遵循问题保留，不将文件检查与命令执行次数混为一谈。
- 5.7 人工发现文件授权卡只显示 Change Set hash，没有路径/权限/期限。已修复 Plain 展示器缺失 `kind=tool` 分支的问题：文件授权展示 Core 的规范路径、只读/读写、文件/递归目录范围、有效期和用途；Bash 审批展示绑定的 argv/cwd/timeout。两类询问不再使用 Change Set 文案，验证命令也不再宣称不提供 OS 沙盒。要求用户拒绝旧卡并重启重测，未代替用户批准。
- 此修正的真实 Runtime→审批事件→Plain 展示回归先失败后通过（文件、目录、Bash 共 3 项），相关回归 `73 passed, 1 warning`；Ruff、格式、Mypy（232 个源文件）及差异检查通过。5.7 仍待人工确认授权卡和授权后的 A/B 访问结果。
- 5.7 后续人工确认：单文件只读/session 授权卡完整显示范围并获批准（`run_06e54ce61c0743fc94d5f3274aee231a`）；A 读取成功（`run_599f10105f4a4132952c5180ba0755cc`），同目录 B 读取被拒（`run_dabdda634e5d491fabe45c7456725890`）。只读授权后的写入拒绝仍未收到人工结果，不标记通过。
- 用户拒绝 A 的命令执行审批（`run_f23f1342872240fa9829a2df174ed828`）后，模型只收到空内容，未能说明用户拒绝。查明 Core 已生成 `approval_rejected`，但模型消息投影丢弃了 `ToolResult.ok/error_code`。现将两字段保留在内容封装外层，不改变正文、内容哈希或不可信标记，也不伪造进程退出码。命令审批拒绝不撤销既有文件 Grant。
- 新增真实 Runtime→拒绝审批→后续模型请求回归，先复现缺少结果字段，再验证模型收到 `ok=false/error_code=approval_rejected`，且 supervisor 零调用、没有 process.started。相关 `tests/sandbox tests/runtime tests/content tests/cli/test_presenter.py` 共 `173 passed`；首次执行缺少开发工具 PATH 导致 14 项验证计划用例失败，补齐 `/Users/admin/Vera/.venv/bin` 后完整复跑通过。Ruff、格式、Mypy（232 个源文件）、差异检查通过。真实模型拒绝说明留待用户重启后验收；任务仍 In progress，未提交/合并。

### 用户指定三项目验收（2026-09-27）

用户选择桌面 VeraTestDemo、python-demo、vue-demo，依次在隔离副本进行真实代码验收，再提供更复杂工程。副本和启动器已准备、iOS 副本 CLI 启动检查通过；手动编辑/审批及各语言运行尚待验收。详见 [三项目验收记录](0089-demo-project-acceptance.md)。原项目未修改，不将 Xcode 兼容阻塞解释为缩减产品语言范围。
