# ADR-0022：BYOK Provider 配置由用户控制

**状态：** Accepted（用户于 2026-09-25 确认）
**日期：** 2026-09-25

## 背景

Vera 将提供 DeepSeek、GLM、OpenAI 和自定义 OpenAI-compatible 模型的 BYOK 选择。`base_url` 与 `api_key_env` 共同决定 Key 发给谁。现有 `load_config` 合并用户和工程的 `providers`，而工程文件属于低信任输入；如果工程可以改这两个字段，就不能保证模型请求遵循用户对密钥和目的地的选择。

首版 Core 规格中“项目配置可选择供应商和模型”的表述需因 BYOK 信任边界收紧。用户明确要求多厂商的简单 Key 配置，并选择沿用私有环境文件和环境变量引用。

## 决策

- Provider Profile、endpoint、模型目录开关与顺序、默认项、Key 引用及 Provider 请求参数只能由用户本地配置或用户显式 CLI 操作决定。工程 `.vera/config.toml` 不得创建、覆盖或选择这些字段。
- 用户配置保存非秘密 Profile 元数据；真实 Key 只从进程环境或权限为 `0600` 的本地私有文件读取。CLI/未来 GUI 的配置交互调用同一个 Core 服务，不直接维护各自的文件格式。
- 若运行工作区包含实际使用的私有 Key 文件，则拒绝 BYOK Run；文件工具的路径过滤与子进程环境过滤仍保留作为纵深防护。
- 内置模型目录提供候选，但不会在无 Key、无用户启用或无明确默认时静默连接 Provider；Provider 切换不自动改变密钥来源或回退到另一厂商。
- 现有用户级 TOML 与 DeepSeek/GLM 环境变量入口保持兼容。用户选择的托管配置优先于同名旧用户配置；迁移不自动写入或复制真实 Key。
- 任何真实 Provider 连通验证必须由用户显式发起，默认测试只用假 Key 与离线 fixture。

## 被考虑的方案

- 继续允许工程配置合并 `providers`：操作少，但工程内容可改变密钥引用或请求目的地，不采用。
- 把真实 Key 写入 Profile JSON/TOML：方便配置，但易被输出、同步或提交，不采用。
- 首版改为系统钥匙串：有平台安全优势，但用户选择保留跨平台可用的私有文件与环境变量引用；钥匙串可在未来成为 `CredentialStore` 的替代实现。

## 后果与迁移

- 原来依赖工程 `.vera/config.toml` 定义 Provider 的工作区将得到明确配置错误及用户级迁移指引；原工程文件不被 Vera 自动修改。
- `docs/specs/2026-09-10-core-safe-editing-vertical-slice.md` 的配置优先级段落同步修订，记录工程配置只能收紧允许的低信任项目选项。
- CLI 配置和未来 GUI 共享 Core 的结构化目录、状态与动作契约；GUI 仍受阶段十入口门禁约束。

## 验证

- 使用假 Key 证明工程配置不能改 Provider endpoint、`api_key_env`、模型默认项或排序。
- 使用临时 HOME 与工作区包含关系证明私有 Key 文件不会暴露给工作区文件工具或结构化命令。
- 证明配置与诊断输出、错误、Event、Run/Session Journal、Snapshot 和子进程均不包含 Key。
- 验证旧用户配置和私有环境文件继续可用；禁用、切换和配置失败不触发自动跨厂商请求。
