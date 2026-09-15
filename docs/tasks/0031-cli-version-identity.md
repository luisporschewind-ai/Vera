# 任务 0031：CLI 版本身份与 `--version`

> 供 Cursor 执行：阶段六人工走查发现 Medium 缺陷——`vera --version` 不存在，且首屏版本恒为 `0.1.0`，无法自证当前构建。

**状态：** In progress（`vera --version` 已 Terminal.app 复验通过；阶段六未封存）
**执行就绪：** 任务 0029 停在 Ready for manual acceptance；本项为阶段六修正，不封存阶段六
**分支：** `phase-6/0031-cli-version-identity`；已合入 `phase-6/0032-timeline-and-error-fidelity`
**依赖：** 任务 0029 自动部分已完成
**规格：** [阶段六 CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 目标与边界

让用户在任意目录执行 `vera --version` 即可确认正在运行的发行版本、安装类型和包装位置；editable/源码安装再附上 Vera 源码树短 commit。不得启动会话，不得要求工作区，不得探测用户工程 git，不得把动态构建身份写入持久 `vera_version`。

## 设计约束

- `__version__` 与 `pyproject.toml` 的 packaging version 仍为发行版本；持久快照继续写 `__version__`。
- 展示身份与包装版本分离；git 只针对 Vera 源码根，固定 argv、`shell=False`、短超时。
- `--json --version` 是单行 JSON 对象，不是 NDJSON Session。
- 不引入桌面端、不改 Core 权限、不读取 Provider Key。

## 实施步骤

### 1. 版本身份探测

**修改：**

- 新增 `src/vera/version.py`
- 新增 `tests/test_version.py`
- `src/vera/session/status.py`
- `src/vera/session/diagnostics.py`

探测发行版本、包装目录、`editable`/`wheel`/`unknown`，以及可选的源码 git。失败局部降级。`/status` 与 `/doctor` 消费同一展示版本。

### 2. CLI 开关

**修改：**

- `src/vera/cli.py`
- 新增 `tests/cli/test_version.py`
- `tests/cli/test_run.py`
- `scripts/smoke_installed_wheel.py`
- `docs/INSTALL.md`

`vera --version`、`vera -V`、`vera --version --json` 退出码 0；`--help` 列出该选项；无效工作区不影响版本查询。

### 3. 走查与状态

**修改：**

- `docs/evals/phase-6-manual-walkthrough.md`
- `docs/STATUS.md`
- `docs/tasks/phase-6-execution-order.md`
- 本任务文件

发现 1 标记为代码已修、待用户在 Terminal.app 复验。不把任务 0029 或阶段六标为 Complete。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest tests/test_version.py tests/cli/test_version.py tests/cli/test_run.py tests/session/test_status.py tests/session/test_diagnostics.py tests/test_package.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git diff --check
```

## 验收标准

- `vera --version` 与 `vera -V` 退出 0，输出含发行版本与包装目录。
- `--json --version` 为可解析单行 JSON，含 `name`、`version`、`location`、`install`。
- 源码/editable 安装的展示版本含短 commit；wheel 安装不含 git 字段。
- 版本查询不启动 TUI/会话，不要求工作区存在。
- `__version__` 仍为 `0.1.0`；任务 0029 保持 Ready for manual acceptance。
