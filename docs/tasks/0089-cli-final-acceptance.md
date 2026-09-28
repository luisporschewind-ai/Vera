# 0089 CLI 收尾与最小复验

2026-09-27，用户授权先处理可独立修复的问题，并在 20 分钟内交付手动步骤。延续 0089，保留现有工作树，不提交、安装依赖或增加工具链权限。

## 本轮最小修复约定

- plain 增加显式 `/paste` 收集模式：逐行保留内容和空行，单独一行 `/end` 才提交一次；`/cancel` 或 Ctrl+C 丢弃整段。内容中的 approve 不作为审批输入。此入口不宣称任意直接多行粘贴均已支持。
- plain 运行期间 Ctrl+C 先由进程监督器清理本次进程，再通过既有 Core CancelActiveRun 结束任务并回到输入；审批期间 Ctrl+C 保持取消语义。无终端并发输入架构改造，运行中键入撤权命令仍不支持。
- 修正 /tools 成功条目末尾空分隔符。
- 只复验对应回归和已知失败；Apple 工具链新增访问与联网安装保持未授权，不执行。

## 检查记录

- 原三项代表项目验证/失败回滚测试：补齐现有 Ruff 的 PATH 后 3 passed，无需改产品代码。这些用例使用公共验证夹具，不代表三种原生工具链都通过。
- 两项安装检查：使用可用 Python、uv 与绝对 PYTHONPATH 后均阻塞于离线缓存缺少 openai>=2,<3；wheel 构建已完成，安装及后续 smoke 未通过。没有下载依赖。
- 会话/活动显示聚焦检查 26 passed；新增中断进程回收及 CLI 入口/模式检查 14 passed（两组有重叠，不合计成独立用例数）。真实临时 sleep 在模拟 KeyboardInterrupt 后退出；假模型取消后会话可继续。Ruff 与 git diff --check 通过。临时启动器 /help、/exit 成功，无模型调用。
- 后续状态更新：SwiftPM XCTest 清理已通过；Intel iOS 假工程现已通过最终生产 SRT backend，Apple 服务审批由 HumanPresenter 定向回归覆盖。仍未完成：Vera 实时 CLI iOS 构建人工流程、APFS 卷取消/超时清理；正式 SRT VerificationRunner 的一般 Ruff 成功/失败/越界闭环已在独立记录通过，但 Apple 服务 capability 不经该入口。两项 wheel install smoke 当时受离线 openai 缓存阻塞；运行中 plain 输入撤权与其他语言矩阵仍待验收。Apple Silicon 按用户决定延期。

## 用户最小步骤（重启后，约 3–5 分钟）

1. 退出旧 Vera，在系统终端运行 `/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/start-parent-acceptance.sh`。
2. 在 `Vera >` 输入 `/paste` 并回车，再粘贴以下完整三行；收集期间不应开始任务：

```text
仅调用一次 read，参数为 {"path":"Example/Podfile"}。
不调用其他工具、不运行命令、不申请权限、不重试。
完成后只报告读取是否成功，不输出文件正文。
```

3. 单独一行输入 `/end`。应只开始一个任务、汇总读取一次。完成后 `/tools` 应显示一个成功条目且无末尾空分隔符。
4. 输入以下单行请求，出现命令审批后输入 approve：

```text
仅调用一次 bash，严格使用 {"argv":["/bin/sleep","30"],"cwd":".","timeout_seconds":60}。不调用其他工具、不新增权限、不重试。
```

5. approve 后等约 2 秒，在进程运行期间按一次 Ctrl+C。应显示任务取消并回到 `Vera >`，不等待 30 秒；不要在审批提示尚未批准时按键，否则只覆盖审批取消。
6. 输入 `/permissions` 确认会话仍可用。终端返回只能验证 CLI 交互；子进程清理的补充证据以本轮监督器检查为准，不仅凭 UI 宣称任意后代都已清理。

上述步骤只读取测试副本和运行短暂 sleep；不安装依赖、改项目文件、联网或增加权限。实际原生终端结果由用户补充，不能由自动化结果替代。

## 用户补验结果

- session_85580ca9e7d74f39935fe91f09d6bf8a：run_8876698095c84f94b50d2b105221865b 在 /end 后才开始；三行请求完整合并，read Example/Podfile 一次成功，/tools 仅一个成功条目且无空分隔符。显式多行收集验收通过；粘贴期间提示符可能连在一起是现存排版表现，不影响一次提交语义。
- run_cca48470b2dd4fe593cf816eb2ea27f5：用户 approve 后按 Ctrl+C，CLI 显示 run 取消并回到 Vera >，随后 /permissions 正常、额外权限为无。运行中取消与会话继续使用人工通过，不据终端文字单独推断所有后代进程状态。
- 当前取消提示出现两行（带 run ID 与通用提示），作为轻微显示冗余记录；本轮不追加修复或重复测试。其余阻塞保持原记录，0089 未整体完成。
