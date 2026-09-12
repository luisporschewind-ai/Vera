# 阶段四独立安全与路线对齐审查

**状态：** Complete
**日期：** 2026-09-12
**审查范围：** `7381148..ca6e203`（阶段四任务 0015–0019）
**扫描 ID：** `f5a6040d-6f4e-49cd-9e94-0d95b2cf9fa3`

## 结论

- 64/64 个审查项已检查，未发现需要报告的安全漏洞。
- 没有发现未批准写入、命令执行、workspace 逃逸或审批绕过。
- 阶段四仍通过 Core Command/Event、PolicyEngine 和 ApprovalGate 工作，没有让 Eval 或 Presenter 成为第二套 Runtime。
- 文档准确声明：Vera 第一版没有 OS 沙箱；离线 Fake Model 评测不能证明真实 Provider 的质量。
- 审查未读取真实 Provider Key、未调用 live Provider、未修改用户工程。

## 已检查范围

1. Eval Corpus、Fixture 与 Worker 的 workspace 隔离。
2. 评测命令、子进程环境和网络禁用边界。
3. 证据目录、文件权限、原子发布和脱敏。
4. Runtime 审批绑定、Policy hash、workspace identity 与写入前复核。
5. Checkpoint、Journal、Snapshot、恢复和回滚的数据完整性。
6. TUI、Plain、JSON、Eval 对共享 Core 契约的依赖。
7. 路线图、规格、ADR、任务、状态与实际实现的一致性。
8. 阶段四完整非 live 门禁和 wheel 外安装 smoke 证据。

## 非阻断加固项

以下问题未构成阶段四可利用漏洞，但必须在阶段五作为成熟度工作处理：

- 证据发布不得修改预先存在的父目录权限，suite report 应复用排他、原子、私有写入器。
- 文件操作应进一步防御 `resolve/lstat/read` 之间的符号链接替换和 TOCTOU 竞态。
- 凭据检测与脱敏应覆盖更多结构化字段、供应商变量和高熵 Token，同时避免记录待检测秘密本身。
- 验证命令应统一环境 allowlist，并明确监督超时后的整个子进程组。
- 审批应补充“当前事实变化即过期”的契约与回归矩阵。

这些工作分别进入任务 0020、0021、0022 和 0024；在对应任务通过前，阶段五不能完成。

## 审查限制

- 本次是代码、契约和离线证据审查，不等同于操作系统级渗透测试。
- 没有使用用户的 DeepSeek/GLM Key，也没有评价真实模型输出质量。
- 真实终端、真实工程和长期 dogfood 仍由阶段五、阶段六的人工验收补齐。
