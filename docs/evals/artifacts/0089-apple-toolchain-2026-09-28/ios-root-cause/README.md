## 2026-09-28 根因收口与当前交付（覆盖此前未验证假设）

**规格已接受；Core 单次授权及产物卷已接入代码；真实 SRT 假工程诊断构建已通过。最后接入产品的整条路径尚未复跑，由用户验收；0089 仍为 In progress。**

三个独立阻塞已由定向证据区分：

1. **simctl 崩溃：缺少 ICU 数据读取。** `/usr/share/icu/icudt76l.dat` 被拒时，最小 Foundation 程序日期格式器返回 NULL；只增加此文件只读后恢复。`simctl` 随后 exit 0。崩溃位于日期格式器，与继续增加 Mach 名称无关。
2. **Xcode 原子写入：已签名工具忽略临时目录后缀。** 内核明确拒绝宿主共享 `T/TemporaryItems/NSIRD_xcodebuild_*` 的创建；不是工作区不可写，也不是私有符号链接缺少写权限。此前猜测的链接写规则已撤回。将 DerivedData 放入独立 APFS 产物卷后，EPERM 降为 0：Foundation 的替换目录改为目标卷内，不必开放宿主共享 T。
3. **运行时发现：目录枚举与 Intel 启动服务分别不足。** 两个获批 bundle 内容可读，但祖先目录不能列出条目。只给这些祖先目录节点 `file-read-data + DIRECTORY + literal` 后，iOS 26 运行时可见但不可用；日志指向 `com.apple.CoreSimulator.SimLaunchHost-x86`。只加入这个精确第六服务后，运行时变为 available。

组合修复的真实 SRT 假 `VeraTestDemo` 构建耗时 29.57 秒，**BUILD SUCCEEDED / exit 0**，Main 和 LaunchScreen Storyboard 均编译通过，`cleanup_error=null`，产物卷正常卸载、假工程夹具删除。`supported platforms ... empty` 仍作为警告出现，因此不能再把该句单独当作失败根因。未授权的其他 device type 仍有 Malformed bundle 警告，不为消除警告扩大读取。

### 已接入代码与产品行为

- 六个服务通过固定 SRT 0.0.77 正式 `allowMachLookup` 接口，仅对获批的单次 unsigned generic iOS scheme build 生效。第六项限 Intel；Apple Silicon 实机继续延期封存，不声称已支持其完整服务链。
- Core 在批准后创建临时 APFS 稀疏镜像（逻辑容量上限 8 GiB，随使用增长），追加受审的 `-derivedDataPath`；审批展示该转换及产物销毁策略，绑定固定存储方案。结果区分原始 argv 与实际执行 argv。
- 此路径不接受用户指定的 DerivedData/result bundle/主要输出覆盖项，也不接受 target/test/archive 等其他动作；不偷偷覆盖用户输出路径。构建产物会销毁、无跨构建增量缓存。超出容量或挂载失败明确失败，不退回无沙盒。
- 镜像文件在子进程授权范围外，仅挂载卷授权。退出后精确卸载再删除，卸载失败保留现场并报告清理失败；不用强制卸载或扫描删除旧残留。
- `directory_listable` / `--list-directory` 是显式用户配置的目录节点列举权限，不读取子文件内容。ICU、两个 bundle 与工具链的递归只读仍独立审批，没有随服务能力自动授予。普通配置未改。

### 验收边界与继续入口

随后用户要求由 Codex 承担验收。最终产品 `SrtBackend` 假工程真实 SRT build 已通过（exit 0、Storyboard 成功、无 cleanup_error、产物卷清理、外部读取 EPERM）；审批展示聚焦回归 7 passed；FakeModel 拒绝后执行调用数 0。记录见 `product-backend-check.json`、`product-boundary-check.json`、`product-approval-presentation.json`、`product-approval-denial.json`。测试没有使用真实模型或实时 CLI；HumanPresenter 基于结构化审批事件渲染。取消/超时卸载和 VerificationRunner 服务审批仍待后续验收。

新证据位于 `docs/evals/artifacts/0089-apple-toolchain-2026-09-28/ios-root-cause/`。无需 VM 或独立用户会话即可跨过已定位阻塞；通用 Coding Agent 的 iOS/Swift 目标保留。没有提交、合并、推送、修改主线或原始工程、安装软件、修改宿主安全设置。旧 TemporaryItems 残留仍单独登记。

上游原始依据：Apple FileManager item replacement 在目标卷选择临时位置；Chromium 2026-09-11 回退说明签名程序忽略后缀变量：
https://chromium.googlesource.com/chromium/src/base/+/d201734b358d6205e0aa482fa806a19c92667d68
https://raw.githubusercontent.com/apple-oss-distributions/Libc/main/gen/confstr.c
