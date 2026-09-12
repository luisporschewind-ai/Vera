# 任务 0035：桌面 Provider、配置、私有状态与日志

> 供 Cursor 执行：不得用明文文件、argv、普通环境或 Renderer storage 作为 credential store 回退。

**状态：** Planned
**执行就绪：** 否；任务 0034 合并后
**分支：** `phase-7/0035-desktop-config-secrets-logs`
**依赖：** 任务 0034 已合并
**规格：** [阶段七桌面集成](../specs/2026-09-12-desktop-integration.md)

## 目标与边界

为桌面设置建立 Core 权威的非秘密配置、OS credential store 抽象、最小权限私有状态、壳/Core 分离日志和本地崩溃诊断。阶段七不自动上传遥测或崩溃数据。

## 文件结构

- 新增 `src/vera/secrets/__init__.py`、`base.py`、`errors.py`。
- 新增 `src/vera/secrets/macos_keychain.py`；其他平台没有原生验证前只提供明确 `unsupported` adapter。
- 新增 `src/vera/desktop/settings.py`：结构化非秘密设置动作与 metadata。
- 修改 `src/vera/config.py`、`bootstrap.py`：Provider 从 SecretStore 取值，不进入普通 child env。
- 修改 `src/vera/desktop/messages.py`：secret write/delete 与 config inspect 消息为明确不可记录类型。
- 修改 `src/vera/redaction.py`、`persistence/private_writer.py`。
- 新增 `desktop/app/frontend/src/views/SettingsView.*`、`components/SecretField.*`、`views/DiagnosticsView.*`。
- 新增 `desktop/app/native/diagnostics.*`：壳生命周期日志和预览/导出。
- 新增 `tests/secrets/`、`tests/desktop/test_settings.py`、`tests/security/test_desktop_secret_canary.py`。

原生/前端扩展名由任务 0031 写回。

## 接口

- `SecretStore.set(provider_profile, secret_name, value) -> SecretMetadata`。
- `SecretStore.get_for_provider(provider_profile, secret_name) -> SecretValue`：只在 Core Provider 装配内部调用。
- `SecretStore.delete(...) -> SecretMetadata`。
- `SecretStore.inspect(...) -> SecretMetadata`：永不返回明文。
- `ConfigService.inspect_effective() -> RedactedConfigSnapshot`。
- `DiagnosticsBuilder.preview() -> DiagnosticManifest`、`export_exact(destination)`。

Secret 值使用不可打印 wrapper 或等价结构，`repr/str/model_dump` 不得返回明文。

## 测试先行步骤

### 1. SecretStore contract

- set/get/delete/inspect；
- service/profile 隔离与非法名称；
- Keychain locked/denied/missing/duplicate；
- Renderer 只能得到 configured/source/timestamp；
- adapter unsupported 时失败关闭，不写明文。

### 2. macOS Keychain

- 使用测试专用 service/account 和随机 canary；
- argv/日志/异常不包含 secret；
- 权限拒绝返回稳定 code；
- 测试结束只删除本次精确 credential；
- 不扫描或删除用户其他 Keychain 项。

需要真实 Keychain UI 的项目列为人工；自动测试可以使用可注入 fake adapter。

### 3. Provider 装配

- Desktop Core 不从 Renderer storage、argv 或任意环境获取 Key；
- 已存 secret 只在 Provider call 边界短暂可用；
- 工具子进程环境过滤后不含 Key；
- model error/Event/usage 无 secret；
- 切换 profile 不泄漏旧 provider。

### 4. 非秘密配置

- 展示值、来源、是否生效和脱敏值；
- 用户配置与项目配置优先级符合既有规则；
- 项目配置不能授权命令或指定 credential；
- 无效配置保留旧有效值并给出可行动错误；
- Renderer 不直接改任意配置文件。

### 5. 私有状态和日志

- private dir `0700`、file `0600`、原子写入、不跟随 symlink；
- Core State、壳日志、WebView cache 分离；
- 文件/字节/保留期达到上限后精确轮换；
- 日志不含 source body、完整 Diff、请求正文、env 或 secret；
- Renderer localStorage/IndexedDB/cache 扫描无敏感对象。

### 6. 崩溃诊断

- 默认只收集 app/core version、platform、lifecycle code、脱敏 error code 和 manifest；
- 用户预览前不导出；
- 阶段七无 network upload；
- 导出目录由原生 save panel 选择；
- canary 扫描失败时拒绝生成“可分享”结论。

## 自动验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest tests/secrets tests/security/test_desktop_secret_canary.py tests/desktop/test_settings.py -q
```

再运行所选桌面壳/前端门禁和阶段七共同门禁。

## 人工验证

- macOS Keychain 首次授权、拒绝、锁定、修改与删除；
- 设置页保存后不回显已存明文；
- Finder/Console/应用日志和导出包 canary 复核；
- Web Inspector storage 中无 Key/源码/完整 Diff；
- 无 SecretStore 时错误真实、可行动。

## 验收标准

- 存储的 Key 只由 Core Provider 边界读取。
- Renderer、普通环境、日志、State、Crash、打包产物无 secret。
- 私有状态权限、上限、轮换和删除范围可证明。
- 阶段七无自动遥测或上传。

## 提交

```bash
git diff --check
git commit -m "feat: secure desktop config secrets and logs"
```
