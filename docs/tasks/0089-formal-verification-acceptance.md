# 0089 正式验证执行链验收

日期：2026-09-28。状态：Intel macOS Ruff 最小执行链通过；不代表任务整体完成。用户要求优先推进正式沙盒验证流程。

## 范围与方法

- 使用生产 VerificationArtifactPlanner → VerificationRunner → SandboxedSupervisor → SrtBackend → ProcessSupervisor。未替换为透传后端，也未修改规划后的 argv。
- 仅在临时假 workspace 内复制本机既有 Ruff，使用现有基础权限。无新目录授权、依赖安装、联网、宿主配置修改或真实工程改动。
- 观察用 ArtifactRoot 子类仅在正式 cleanup 前读取假 JSON 报告，实际创建与清理仍由生产实现执行。独立比较工作区文件哈希和产物目录不存在性。
- 此入口消费已批准命令，未再次覆盖模型请求、CLI 审批交互和 ChangeSet 应用；不把本结果当作完整 UI 端到端证据。

## 实测结果

| 场景 | 状态 | 退出码 | 报告及清理 |
|---|---|---|---|
| 正常 Python 文件 Ruff 检查 | passed | 0 | 空诊断报告真实生成，cleaned，产物根已移除 |
| 未定义变量的预期失败 | failed | 1 | F821 诊断报告真实生成，cleaned，产物根已移除 |
| 工作区外假文件读取 | failed | 1 | E902 / Operation not permitted，无假秘密正文，cleaned |

三项 workspace_mutations 均为空，独立工作区指纹不变。外部假文件在未隔离对照中可读取并产生含标记的 F821，真实沙盒仅报告权限拒绝；不以不存在文件冒充边界拒绝。

修复后夹具：formal-verification-bufl1dzv。原始结果与可复核脚本：[result.json](../evals/artifacts/0089-formal-verification-2026-09-28/result.json)、[probe.py](../evals/artifacts/0089-formal-verification-2026-09-28/probe.py)。脚本是本机临时路径验收夹具，不是通用安装入口。

## 同轮修复

发现 VerificationRunner 在监督器抛出 KeyboardInterrupt 或其他异常时跳过产物清理，与 cleanup=always 不符。将已准备产物的执行及结果采集放入 try/finally，正常和异常出口统一调用原有安全清理；异常继续传播，不伪造正常退出码。

新增两项回归先失败后通过；tests/verification/test_runner.py 共 16 passed。修复后上述真实 SRT 三场景复跑通过，Ruff 与 git diff --check 通过。未运行全量套件。

## 未覆盖

Xcode/SwiftPM 的工具链兼容性、其他语言矩阵、完整 Runtime/CLI 正式验证交互仍需分别验收；本轮只收口生产验证器的上述最小执行链。没有提交或合并。
