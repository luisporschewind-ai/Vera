# 0089 用户提供项目验收

日期：2026-09-27。状态：VeraTestDemo 读取、编辑审批及读回手动验收通过；Python 小改动与四项标准库测试通过；Vue 标题修改与离线构建通过。iOS 构建及其他未覆盖范围仍待验证。属于任务 0089，不增加阶段或替代跨语言产品目标。

用户指定顺序：桌面 VeraTestDemo → python-demo → vue-demo；随后提供更复杂真实工程。

## 后续真实项目：parentSectionIOS

用户指定下载目录工程继续验收。原路径 /Users/admin/Downloads/parentSectionIOS；约 591 MB，多模块 CocoaPods iOS 项目，主入口 Example/FlyPrarentSctionIOS.xcworkspace，Podfile 引用 Module 下本地业务组件及现有 Pods。主测试 target 存在，但 Example/Tests/Tests.swift 是模板断言与空性能测试，不作为业务覆盖证据。

已准备副本：/private/tmp/vera-0089-acceptance.psEsZR/real-projects-g21oo820/parentSectionIOS。5961 个普通文件逐一核对源副本哈希，21 个链接检查位于原工程内部；保留依赖目录内部 dist/build 等发布文件。排除 Git 元数据、Xcode 用户状态、环境文件、私钥/签名文件和缓存；原工程未修改。清单 parentSectionIOS-manifest.json 保留在副本根的父目录。

启动器：/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/start-parent-acceptance.sh。下一轮先跨模块只读定位首页与导航文案，再对明确的小改动进行审批和读回。未运行 pod install、构建、签名、模拟器或业务网络请求。完整 iOS 构建仍受已记录工具链兼容缺口约束，不能因为采用更复杂项目就标记通过。

### parentSectionIOS 手动结果（2026-09-27）

用户附件 d0c0932d-0b5e-4193-b55d-1bd01009d8f7，会话 session_3a4d8a414a604acf80ce66fbe2428a9c：主 workspace、scheme 中 App/测试 target、本地模块及首页标题位置的主要定位结果正确；run_1d602e8e839d46c78429ec070d3c962f 的单行 Diff 经 approve 后 applied；run_ff0dcc29d26f48ef807eca0cf1b0cb05 独立读回确认“智学家长端 · 验收”。现场比较源与副本的目标文件，仅有指定标题一行差异，原文件仍为原标题。编辑审批及读回验收通过；未构建或执行 App。

同时记录阅读效率与事实表述缺口：run_983b5e48308f4762a3691b3ff08b5547 在单轮中调用 50 次只读工具（ls 17、read 17、grep 12、find 4），Podfile 重读 5 次，多次重复读取 scheme/workspace。模型末尾称未枚举 scheme 目录，但日志已出现该目录 ls；不能将其全部总结视为已核实事实。存在对根目录 grep 的调用，日志未展示完整参数，不能仅凭模型自述确认完全避开 Pods。上述不影响已观察到的标题修改结果，但不能标记复杂项目阅读效率与指令遵循全面通过；根因尚未定位，不预先归因于模型或上下文机制。

后续调查已确认固定 8 条工具结果淘汰与连续重复检测局限，以及 plain presenter 的两类内部事件默认渲染问题；详见 [定位及实施记录](0089-read-loop-cli-investigation.md)。已实施并由用户完成 plain 汇总与 /tools 补验。

## 隔离准备

- 原始目录：`/Users/admin/Desktop/{VeraTestDemo,python-demo,vue-demo}`，未修改。
- 副本根：`/private/tmp/vera-0089-acceptance.psEsZR/real-projects-g21oo820`。
- 启动：`/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/start-demo-acceptance.sh <项目名>`。
- 排除 Git 元数据、环境文件、私钥/签名文件、虚拟环境、旧构建产物、Python 缓存及 Xcode 用户状态；因此副本不用于 Git 验收。
- Vue 复制已有 node_modules，未安装依赖或运行包脚本；检查被复制链接不指向原项目外部。
- 准备缺陷更正：初次复制误将 node_modules 内的 dist/build 目录也当作旧产物排除，因此初始 Vue 副本不完整。后续已从原 node_modules 仅补齐缺失项，详见下文；项目根构建产物排除规则不能递归套用到依赖目录。
- 文件哈希逐一与源文件比对通过：iOS 21、Python 5、Vue 529 个常规文件；清单位于副本根 source-manifest.json。此证据仅证明准备时副本一致，不代表项目功能测试完成。
- 启动器语法检查通过；VeraTestDemo 实际启动并执行 /permissions、/exit 成功：工作区为副本、manual、沙盒已配置、额外文件授权无。未调用模型或项目构建。

## 顺序与范围

1. VeraTestDemo：UIKit iOS 工程，先读取控制器、拒绝按钮文案修改并读回，再批准同一修改并读回；检查审批卡 Diff 和模型事实一致。无测试 target。Xcode 依赖问题及 iOS SDK 权限未解决，构建/模拟器不能记为通过。
2. python-demo：标准库项目，读取 greet/is_even 后小改动和离线 unittest。全局 Python 入口损坏；项目执行需要核对完整 Python.app 运行时并审批所需只读范围，不能沿用 Core 能启动就认为项目已授权。
3. vue-demo：已有 Vue/Vite 依赖，小改标题、审批和离线 build。未设置 test 脚本，不声称存在单元测试。Node 项目执行资源需单独确认；不下载依赖、不启动服务。

本轮先完成真实代码上的读写/审批手动流程，项目构建按各自实际环境和权限继续验收。运行中 CLI 取消/撤销仍不能用已通过的 Core 测试替代。

## VeraTestDemo 用户手动结果

用户提供终端记录（附件 c912deb8-a579-4348-8226-730570e0aec8），会话 session_9f8a77953d0c4a4b932653ae9a3cd9e0：

- 实际工作区为隔离副本；沙盒已配置，额外文件授权无。启动前终端位于 python-demo 不影响启动器所选工作区。
- 读取控制器正确报告按钮文案与 SecondViewController 展示逻辑。
- run_755ca251d8df4ac18c492c55692ee7a5 展示单行 Diff；reject 后返回 approval_rejected，随后独立 read 确认仍为“打开新页面”。
- run_02c64de64a1740bab1674bd03b281bcb 再次展示单行 Diff；approve 后 applied，随后独立 read 确认“查看演示页面”。
- 审批事实回报正确；模型给出的代码行号前后不一致，不将其作为验收证据。
- 此结果覆盖读取、拒绝不落盘、批准落盘和读回，不覆盖 iOS 构建、模拟器或运行中 CLI 取消。

## Python 用户手动进度

- 会话 session_670f9f30ec1f4732bb25033e61486c79 经用户批准 Python 3.12 运行时目录 session 只读授权，run_f77114d7b66f4bd6bb75ef8c3441eb0d 执行 feature.py 成功（exit 0，is_even(4) = True）。
- 附件 726e30fa-777c-402b-816d-a68404f2ae15 显示：多行粘贴被 plain CLI 分拆成多个输入；后续行进入审批输入，出现两次无效审批输入。测试创建请求未完成，不能归因为模型忽略完整请求。
- run_cbbbc9f964a640b2b80b8280c9b65ab5 的 main.py 单行文案修改经 approve 后 applied，读回成功。
- run_bfdde81b316d4bab9dca13268d7cedb4 启动 unittest 后 exit 1，ModuleNotFoundError: test_demo。测试模块未创建，四项功能测试尚未执行；不能记为沙盒拒绝或测试通过。
- 后续手动步骤改用单行输入：先明确创建 test_demo.py，审批成功后再运行四项测试。多行粘贴与审批输入混用曾记为 CLI 交互缺口；现补充显式 /paste 收集入口，待用户复验，不声明任意直接粘贴自动合并。
- 补验附件 0831677f-6e2a-4593-964a-cd37ed1ee4ca：run_33115a3822834955ac231028e42f60c3 展示 test_demo.py 新建 Diff，用户 approve 后 applied；run_db2912e570de48889cf6dd19a5e83a8d 使用同一会话授权运行 unittest，exit 0、stdout 空、stderr 显示四个独立测试全部 ok、Ran 4 tests / OK。覆盖 greet 新文案以及 is_even 的 4、3、0 输入，未安装第三方依赖。
- Python 本轮读取、修改审批、新建测试、沙盒执行闭环通过。此结论不覆盖 webstats 联网、交互式 main、其他 Python 版本或正式 VerificationRunner 流程；先前多行输入缺口仍保留。

## Vue 用户手动进度与夹具修复

- session_292d44f4f9964d738a7080699025e8b4：run_378cac58c3e34b3883143ecccafcd26c 完成 src/App.vue 标题单行修改，Diff、approve、applied 正常；随后批准 Node 单文件 session 只读权限。
- run_606b0ab6c1dd43c08e4e3f73108811e4 构建 exit 1，ERR_MODULE_NOT_FOUND 指向 vite/dist/node/cli.js；不是已确认的沙盒拒绝。
- 只读核对证明原项目 cli.js 存在（30099 字节），副本 vite/dist 缺失。根因是本任务准备副本时的递归排除规则，不能归因为原项目依赖安装损坏。
- 已仅补齐副本 node_modules 缺失的 279 个文件/目录项，未覆盖既有文件；对原依赖的全部 759 个普通文件逐一比对哈希，链接目标也核对一致。src/App.vue 修复前后哈希不变；未改桌面原项目、安装依赖、执行包脚本或增加权限。
- 证据：副本根 vue-dependency-repair.json。依赖完整性修复已验证，实际沙盒构建仍待用户复验；不将文件恢复当作构建通过。
- 用户复验 run_0903b75b638546fe8dad2ce250efe05f：同一会话、相同 Node 单文件读取授权，命令经 approve 后真实沙盒构建成功，status=exited、exit_code=0、ok=true、stderr 空。Vite 8.3.0 转换 13 个模块，输出 dist/index.html、CSS 与 JS，报告 built in 652ms；未安装依赖、增加权限或启动服务器。Vue 本轮标题修改审批与离线构建闭环通过，不代表浏览器交互、开发服务器或正式 VerificationRunner 全流程通过。
