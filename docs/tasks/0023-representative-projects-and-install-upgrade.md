# 任务 0023：代表性工程与安装升级

> 供 Cursor 执行：按 `superpowers:executing-plans` 实施；仓库夹具与临时目录是自动测试目标，用户真实工程不在自动范围内。

**状态：** Planned
**执行就绪：** 任务 0022 合并后
**分支：** `phase-5/0023-projects-install-upgrade`
**依赖：** 任务 0022 已合并
**规格：** [阶段五 Core 加固](../specs/2026-09-12-core-security-and-reliability-hardening.md)

## 目标与边界

以 Swift/Xcode、Python、Node/TypeScript 三类最小工程验证共享 Core 全链路，并验证本地 wheel 的全新安装、重复安装、升级、错误配置和仓库外启动。自动测试不能读取真实 Key、联网、运行用户项目或修改 `/Users/admin/Desktop/VeraTestDemo`。

## 夹具设计

新增受版本控制的最小文本夹具：

- `tests/fixtures/projects/swift-minimal/Demo.xcodeproj/project.pbxproj`
- `tests/fixtures/projects/swift-minimal/Demo/ViewController.swift`
- `tests/fixtures/projects/python-minimal/pyproject.toml`
- `tests/fixtures/projects/python-minimal/src/demo/__init__.py`
- `tests/fixtures/projects/python-minimal/tests/test_demo.py`
- `tests/fixtures/projects/typescript-minimal/package.json`
- `tests/fixtures/projects/typescript-minimal/tsconfig.json`
- `tests/fixtures/projects/typescript-minimal/src/index.ts`
- `tests/fixtures/projects/typescript-minimal/test/index.test.ts`

夹具不包含二进制、依赖目录、真实签名、外部包下载或秘密。每个 case 先复制到 pytest 临时目录，再由 Fake Model 驱动。

## 实施步骤

### 1. 三类工程确定性工作流

**修改：**

- 上述夹具文件
- 新增 `tests/e2e/test_phase_5_representative_projects.py`
- `tests/fakes.py`
- `src/vera/evals/corpus/__init__.py`

**测试先行：** 为每类工程参数化以下场景，并先确认当前缺少夹具/case 而失败：

1. 只读理解与普通对话不产生 Change Set。
2. 单文件修改和多文件修改生成准确 Diff，approve 后只改预期文件。
3. reject/cancel 为零写入。
4. 验证成功、验证失败后回滚、运行中断后恢复。
5. 路径逃逸和危险命令被拒绝。

**最小实现：** 扩展离线 case factory；所有命令使用当前 Python 解释器执行仓库内确定性 helper，不要求主机安装 Xcode、Node 或 npm。

### 2. 用户可执行的真实工程验收脚本说明

**修改：**

- 新增 `docs/evals/phase-5-representative-project-manual-checklist.md`
- `README.md`

文档分别给出三类工程副本的启动、自然语言任务、预期审批、验证、恢复和清理步骤。明确：

- 用户自行选择并备份工程副本；Vera 不自动发现或修改桌面工程。
- 用户持有 Provider Key；记录中不得粘贴 Key、完整请求或源码正文。
- 未实际执行的行保持 `Not run`，Cursor 不得代填通过。

### 3. wheel 全新安装与仓库外 smoke

**修改：**

- 新增 `tests/e2e/test_phase_5_install_upgrade.py`
- 新增 `scripts/smoke_installed_wheel.py`
- `pyproject.toml`
- `docs/INSTALL.md`（若文件不存在则创建）

**测试先行：**

1. 构建 wheel，在 `/private/tmp` 下新建隔离 venv 并离线安装本地 wheel。
2. 在非仓库 cwd 验证 `vera --help`、默认模式路由、`--plain`、`--json`、`vera eval validate/list`。
3. 缺失配置、不可写 state、未知 schema 有稳定错误和退出码。
4. 测试前后目标工程目录 hash 完全一致。

脚本接受显式 wheel、venv 和 workspace 路径，不自行删除宽泛目录；清理只由 pytest tmp_path 或调用者完成。

### 4. 版本升级与原数据保留

**修改：**

- `src/vera/persistence/journal_codec.py`
- `src/vera/persistence/snapshot_codec.py`
- `src/vera/persistence/migration.py`
- `src/vera/config.py`
- `tests/e2e/test_phase_5_install_upgrade.py`
- `docs/INSTALL.md`

**测试先行：** 使用已封存的上一 schema fixture 验证可迁移路径；未知新版本、损坏数据和迁移写失败均保留原始字节并给出手工建议。重复迁移结果相同，不修改 workspace。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY uv run pytest tests/e2e/test_phase_5_representative_projects.py tests/e2e/test_phase_5_install_upgrade.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase5-dist
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/smoke_installed_wheel.py --dist /private/tmp/vera-phase5-dist --workspace /private/tmp/vera-phase5-smoke-workspace
```

再运行[阶段五共同门禁](phase-5-execution-order.md)。检查仓库与 `/Users/admin/Desktop/VeraTestDemo` 状态未改变，更新任务证据后提交：

```bash
git commit -m "test: cover representative projects and installation"
```

## 验收标准

- 三类临时工程的关键工作流使用同一 Core 通过。
- wheel 在仓库外运行，错误配置和升级路径失败关闭并保留原数据。
- 自动测试无网络、无真实 Key、无用户工程副作用。
- 人工清单真实、可执行，未执行项不伪装为通过。
