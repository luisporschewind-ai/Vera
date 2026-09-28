# 0089 原生 Git 最小验收

状态：经用户批准的临时验收中，已有假仓库的 Core/SRT 状态、Diff、版本、精确提交、重复计划不重复提交、分支创建/切换、log/show 均通过（2026-09-27）。工作区外及 Core 私有状态读取、Git 配置与 Hook 路径写入仍拒绝。不是用户 CLI 端到端验收；不包含 git init、真实 Hook/签名、任意 Git 工作流。

## 生命周期修正及提交修复（当前结论）

- 初始化原因已查明：SRT 0.0.77 的强制拒绝集合包括 .git/hooks、.git/config，移动保护同时拒绝受保护路径祖先的 file-write-create，故空工作区创建 .git 被拒。Accepted 原生 Git 规格提供已有仓库的读、提交与分支工具，没有 git init 工具；不能把此测试准备失败写成提交/分支失败，也不能通过移除保护扩大通用命令权限。本轮不支持沙盒内初始化新仓库。
- 修正夹具：可信测试准备复制此前已存在的假仓库 .git 元数据，检查无符号链接，在新夹具中写入专用假身份配置；这不是沙盒 git init 成功证据。基线提交和后续 Core Git 命令全部使用真实 SRT；没有无沙盒 Git 重试。旧失败夹具与证据保留。
- 继续复验发现真正的提交缺陷：Core 使用 `commit -F` 要求命令读取 workspace 外的私有 state/git-commit/message 文件，真实返回 EPERM（git-lifecycle-gs9twn_0/result.json）。修复为已校验、已绑定计划哈希的消息作为 `-m` 的单独 argv 值，不做 Shell 解析，不开放私有状态目录。Receipt、index 备份及恢复仍由可信 Core 管理。
- 新回归先出现 git_commit_failed，修复后通过；覆盖前导连字符、引号、Shell 字面量、多段中文消息。Git 与沙盒相关回归 59 passed（32.24 秒），Ruff、格式、Mypy 及差异检查通过。
- 最终证据：`/private/tmp/vera-0089-acceptance.psEsZR/git-lifecycle-8puvp3rk/result.json`，passed=true。恰有基线与精确变更两个提交；重复执行同一计划 HEAD 不变；创建并切换 codex/probe-next 后工作区干净；log/show 核对成功。外部假文件和 state/sentinel.txt 读取均 EPERM；.git/config 写入拒绝且字节未变；.git/hooks 创建拒绝且不存在。
- 中间夹具 git-lifecycle-gmj0c0k5 的功能检查通过，但 Core 的环境过滤没有继承夹具提供的身份变量，Git 使用系统推导身份；最终夹具改为准备阶段写入假仓库本地身份，并断言两条记录均为 Vera Fake Probe。未修改用户配置或真实仓库身份。
- 系统 gitattributes 路径读取仍有 EPERM 警告，测试中的简单文本操作成功不代表依赖系统 attributes、外部 helper、Hook、签名或 linked worktree 的所有场景兼容。基础读取集合没有增加，普通启动配置保持原样。

## 修复记录

- 根因：当前受限 PATH 选择 /usr/bin/git 系统入口，会探测开发工具选择路径；实际 Git 位于 /Applications/Xcode.app/Contents/Developer/usr/bin/git，其直接依赖为已有基础集合内的系统库。GitDiscovery 把初始 rev-parse 的所有非零结果都当作非仓库。
- 最小实现：用户配置增加可选 git_executable，CLI sandbox setup 增加 --git-executable，在原审批预览里展示所选文件及精确只读路径；没有自动发现或静默保存，旧配置保持原行为。
- 后端只将直接 argv[0]=git 或 /usr/bin/git 解析为所选文件；不修改后续参数，不解析 Shell 字符串、不继承项目/环境中的可执行选择。所选文件必须有精确基础只读授权且在所有命令可写根之外；缺失、变为链接、不可执行均失败关闭，不回退到别的 Git。后代自己执行 Git、Git helper 和所有工具链场景不据此宣称可用。
- 分类：EPERM/EACCES → git_permission_denied；xcode-select/xcrun 工具链错误 → git_toolchain_unavailable；明确的 not a git repository → git_not_repository；其余发现失败 → git_process_error。stderr 仅用于有界错误分类，不触发安装、放权或重试。
- 先写失败测试：4 failed / 1 passed，复现三项误分类及缺失显式 Git 选择能力；最小实现后发现/后端组合 18 passed。新增配置兼容、拒绝审批不保存、显式批准保存、Git 缺失不回退用例，扩展回归 tests/git + Git 兼容/后端/状态/安全回归共 57 passed（68.15 秒），Ruff 通过，Mypy 四个受影响源文件通过，git diff --check 通过。
- 用户批准后执行 check-git-fix.py。首次复验版本成功，但发现阶段的子 Git 仍通过 PATH 找到系统入口，报 ls-tree returned unexpected return code 1。补失败测试后，将已验证 Git 的父目录加入固定 PATH，使该子进程也选择同一个文件；不继承外部 PATH/GIT_EXEC_PATH/DEVELOPER_DIR，不新增父目录或兄弟文件读取权限。配置文件所在目录含冒号时失败关闭；非 Git 命令启动前也验证配置，避免后代使用失效配置。
- 再次真实复验通过，证据：`/private/tmp/vera-0089-acceptance.psEsZR/native-git-m3nrvti4/fix-result.json`。原配置的 status/diff 正确返回 git_permission_denied；仅增加指定 Git 文件的临时只读权限后，status 正确返回 AM sample.txt 与 untracked.txt，diff 正确显示 GIT_BEFORE → GIT_AFTER，版本为 Apple Git-155；读取假工作区外 b.txt 仍 exit 1 / EPERM / stdout 空。
- 正常 sandbox.json 未保存新配置；未批准整个 Xcode 目录，未安装软件或修改系统设置，未提交、合并、推送。此证据覆盖本次发现流程的子 Git，不覆盖所有 helper、提交/分支/Hook 或构建工具链。
- 最终验证：上述扩展范围 58 passed（30.89 秒），Ruff 检查与格式检查通过，四个受影响源文件 Mypy 通过，git diff --check 通过。使用完整 Python.app 解释器加载原虚拟环境，未修复或替换共享 Python。

## 初次预检（历史）

### 首次生命周期尝试（历史，初始化受阻）

- 已准备 `/private/tmp/vera-0089-acceptance.psEsZR/check-git-lifecycle.py`，语法检查通过，尚未执行；无批准参数时不创建夹具。
- 计划在既有临时验收根下新建独立假仓库，以同一精确 Git 文件临时只读授权执行：空模板初始化、一次基线提交、一次 Core 精确提交、重复同一计划检查不重复提交、创建/切换 `codex/probe-next`、状态/log/show 核对及工作区外假文件读取拒绝。
- Core 状态目录保持在假 workspace 外，不为通过测试将状态目录放入工作区或新增基础读取；失败保存证据并停止，不无沙盒重试。提交身份使用 example.invalid 假邮箱，不使用真实身份、Hook、签名、远程或网络。
- 此脚本验证 Core Git 工具与真实 SRT 集成，不代表 CLI 审批 UI 验收；提交与分支只作用于新建假仓库，证据保留，不修改普通配置或真实产品仓库历史。
- 用户于 2026-09-27 批准“临时提交和分支测试”后执行一次。夹具 `/private/tmp/vera-0089-acceptance.psEsZR/git-lifecycle-lclnltfc` 的 result.json 记录：真实 SRT 内 `git init --quiet --template= --initial-branch=codex/probe-base` exited/1，stderr 指向 workspace/.git 的 Operation not permitted。独立目录检查 workspace 为空；没有创建提交或分支，后续步骤未执行，不能据此判定已有仓库的提交/分支必然失败。
- 只读诊断发现 SRT 0.0.77 对 .git/hooks 和 .git/config 有强制写入保护，且对受保护路径祖先生成 file-write-create/move 限制；Vera 明确使用 allowGitConfig=false。这是当前重点诊断方向，未凭一次 EPERM 将所有 Git 写入归为不可用。未更改保护规则、扩权、用无沙盒初始化绕过失败或修改正常配置。
- 当前结果：本轮生命周期测试未通过，阻塞在假仓库初始化；此前状态/Diff 只读复验仍有效。下一步需区分夹具准备与产品支持范围，定位初始化保护冲突，再在原批准的临时范围内验证；新增基础权限仍另行申请。

## 夹具及证据

- 专用目录：`/private/tmp/vera-0089-acceptance.psEsZR/native-git-m3nrvti4`，结果保存在 result.json。
- 仅初始化假仓库，使用空 template、独立 HOME、禁用全局/系统 Git 配置；分支 codex/acceptance。没有提交、远程、网络或真实仓库修改。
- sample.txt 的 GIT_BEFORE 换行加入假仓库 index，随后工作区内容改为 GIT_AFTER 换行；另有 untracked.txt。宿主原生 Git 对照输出 AM sample.txt、?? untracked.txt，工作区 diff 正确显示 BEFORE→AFTER。
- 将现有正常 SRT 配置注入真实 SandboxedSupervisor，调用 GitStatusTool、GitDiffTool(scope=working, paths=sample.txt)，两者均返回 ok=false、git_not_repository。
- 沙盒内单独 `/usr/bin/git --version` exited/1，stderr 报 xcode-select 无法读取 `/var/select/developer_dir`，Operation not permitted。未执行报错中的 sudo、install 或 switch 建议。
- 宿主只读检查该 developer_dir 路径为不存在，因此不能写成“已有 symlink 被拒”；被拒的是工具对该路径的探测，实际工具链定位和必要权限仍需进一步诊断。

## 初次预检结论（历史，已由上方复验更新）

1. 仓库有效，当前基础运行权限下 Apple Git 无法正常完成工具链发现；该预检未通过，不能要求用户把同一用例重复跑成成功。
2. GitDiscovery 对 rev-parse 的非零退出统一转成 git_not_repository，掩盖了本次原生工具/权限错误。已定位到错误映射，但本轮没有修复产品代码。
3. 没有扩大基础目录白名单、修改宿主开发工具选择、安装软件或关闭沙盒。下一步诊断并形成最小适配，涉及扩大授权的实际试验按既有用户边界申请。
4. 本轮不计入 Git 状态/Diff 已通过，不外推提交、分支、Hook、构建/测试等全流程；任务 0089 保持 In progress。
