# 任务 0036：桌面打包、签名、升级、迁移与卸载

> 供 Cursor 执行：发布操作使用临时/本地 artifact；不得推送、发布或使用用户签名凭据，除非用户另行明确授权。

**状态：** Planned
**执行就绪：** 否；任务 0035 合并后
**分支：** `phase-7/0036-desktop-packaging-update-uninstall`
**依赖：** 任务 0035 已合并
**规格：** [阶段七桌面集成](../specs/2026-09-12-desktop-integration.md)

## 目标与边界

在 Intel macOS 上形成可复现的完整应用包：桌面壳、前端、Python Core onedir、runtime、compatibility/state migration manifest 一起构建；验证嵌套签名结构、Hardened Runtime、离线升级、失败恢复和安全卸载。真实在线发布属于阶段八。

## 逻辑文件

- `desktop/app/build/`：所选框架 build、entitlements 与资源配置。
- `desktop/app/resources/core/`：由脚本生成，不手工提交二进制。
- 新增 `scripts/build_desktop_app.py`。
- 新增 `scripts/verify_desktop_artifact.py`。
- 新增 `scripts/smoke_desktop_update.py`。
- 新增 `src/vera/desktop/artifact_manifest.py`、`update_compatibility.py`。
- 新增 `docs/INSTALL-DESKTOP.md`、`docs/UNINSTALL-DESKTOP.md`。
- 新增 `tests/desktop/test_artifact_manifest.py`、`test_update_compatibility.py`、`test_uninstall_scope.py`。
- 新增 `docs/evals/phase-7-desktop-packaging.md`，人工项初始为 `Not run`。

精确框架配置文件由任务 0031 写回。

## 打包不变量

- 不依赖系统 Python、用户 shell PATH 或开发仓库。
- Core onedir 与前端资源只由可重复脚本生成；生成目录不进入源码 import。
- `artifact-manifest.json` 记录 App/Core/protocol/state 版本、arch、每文件 hash/mode、license。
- 构建环境路径、Key、notary 凭据、用户 Home 和临时目录不进入产物或 manifest。
- 当前任务只声明 `darwin/amd64`；universal/arm64 需要原生运行证据。

## 测试先行步骤

### 1. 可重复 Core/App 组装

- 同一 commit/lock 在规范化时间和环境下产生可解释差异；
- 资源缺失、多余 executable、错误 arch、可写 bundle file 失败；
- Finder 等价环境启动并完成 hello；
- 未安装 Python 的测试账户/环境不影响启动；
- Workspace hash 始终不变。

### 2. Artifact manifest

- 每个 nested executable/library 都有 hash、mode、arch；
- App/Core/protocol/state matrix 一致；
- 未列出文件、symlink 逃逸、重复路径、绝对 build path 拒绝；
- license inventory 完整；
- canary secret 扫描。

### 3. macOS 签名结构

无用户证书的自动门禁：

- ad-hoc 签名按由内到外顺序覆盖 sidecar、dylib/framework、helper、App；
- `codesign --verify --deep --strict`、`codesign -d --entitlements :-` 和 `spctl` 结果记录；
- 不含 `get-task-allow`、JIT、unsigned executable memory、disable library validation、DYLD 等未批准 entitlement；
- Core 可在 Hardened Runtime 结构下启动和调用经过批准的验证命令。

真实 Developer ID/notarization/stapling 仅在用户提供签名环境授权后人工执行；否则记录 `Blocked`。

### 4. 离线完整应用升级

建立 old/current/future/corrupt fixtures：

1. 验证下载 artifact 的签名/manifest/compatibility。
2. active run 或 approval 时拒绝升级。
3. 静止点做空间检查和私有状态恢复副本。
4. 完整替换壳、Core、前端和 manifest，不允许局部版本。
5. 首启先 dry-run state migration，再原子迁移和校验。
6. 未知 future/corrupt/ENOSPC/签名错误保留旧 app 或原 State。
7. app rollback 只有旧 Core 能读当前 State 或恢复副本成功时允许。

测试模拟每一步中断，并断言无混合版本和 Workspace 变化。

### 5. 崩溃恢复

- 更新前、替换中、迁移中、首启后 crash；
- 新启动器能区分旧完整、新完整和损坏混合状态；
- 不自动删除唯一 app/state；
- 提供精确恢复建议和脱敏 manifest。

### 6. 卸载

- 删除 App 不触碰 Workspace、State 或 Keychain；
- 文档解释 macOS 拖入 Trash 的实际效果；
- “清除本地数据”先列出精确 state/cache/log/credential ID；
- 默认取消，确认后只处理列出的 Vera 路径和 credential；
- symlink、路径漂移、权限错误失败关闭；
- 操作后生成不含 secret/path body 的结果清单。

## 自动验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest tests/desktop/test_artifact_manifest.py tests/desktop/test_update_compatibility.py tests/desktop/test_uninstall_scope.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/build_desktop_app.py --platform darwin --arch amd64 --output /private/tmp/vera-desktop-app
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/verify_desktop_artifact.py --app /private/tmp/vera-desktop-app/Vera.app
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/smoke_desktop_update.py --fixtures tests/desktop/fixtures/updates --output /private/tmp/vera-desktop-update-smoke
```

具体 app 路径由所选 bundler 写回。再运行阶段七共同门禁。

## 人工验证

- Finder 启动、Gatekeeper、签名详情、Hardened Runtime；
- 有授权时 Developer ID、notary log、stapling 和隔离账户安装；
- 旧版本 → 当前版本、迁移失败、强制退出后重启；
- 拖 App 到 Trash，确认 Workspace/State/Key 不被误删；
- 用户显式执行“清除本地数据”的预览、取消和精确清理。

## 验收标准

- Intel macOS 完整 App 不依赖系统 Python/Terminal。
- 嵌套签名与 entitlement 最小化有机器证据。
- App/Core/协议/State 只以兼容整包运行。
- 更新/迁移/卸载任何失败都不修改 Workspace、不删除唯一状态。
- 未授权的真实签名或在线发布保持 Blocked/Not run。

## 提交

```bash
git diff --check
git commit -m "build: package and verify Vera desktop app"
```
