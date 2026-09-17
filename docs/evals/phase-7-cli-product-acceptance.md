# 验收：阶段七 CLI 体验收口

**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[持久化对话会话](../specs/2026-09-13-persistent-conversation-sessions.md)、[项目指令与 `VERA.md` 初始化](../specs/2026-09-14-project-instructions-and-vera-init.md)  
**任务：** [0041](../tasks/0041-phase-7-product-acceptance-and-dogfood.md)  
**日期：** 2026-09-16  
**结果：** 自动门禁通过。Terminal.app 第 1–4 项走查已过；发现 38–41、43–48 已复验关闭。20 次 dogfood 与封存原文未完成。阶段七保持 **Ready for manual acceptance**。未收到「CLI 版本达到预期，可以封存」。

严重度：Critical（权限/数据/错误应用）、High（主流程不可用/输入丢失/状态误导）、Medium（高频摩擦）、Low（视觉细节）。

## 质量门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/e2e/test_phase_7_product_matrix.py tests/pty tests/performance -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase7-acceptance-dist
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/smoke_installed_wheel.py --dist /private/tmp/vera-phase7-acceptance-dist --workspace /private/tmp/vera-phase7-acceptance-workspace
git diff --check
```

自动证据（2026-09-16）：

- 完整非 live：`1068 passed, 2 deselected, 7 warnings in 728.48s`。清除 Provider 环境；`PATH` 含 `.venv/bin`，否则 `ruff` 验证命令会报 `No such file or directory`（首次未带 PATH 时 5 项 `verification_failed`，补 PATH 后复跑通过，不计入产品回归）。
- 聚焦：`tests/e2e/test_phase_7_product_matrix.py tests/pty tests/performance` → `22 passed in 36.36s`
- `ruff check src tests` 通过；`ruff format --check src tests` 通过（415 files already formatted）；`mypy src` 通过（169 source files）
- `uv build --out-dir /private/tmp/vera-phase7-acceptance-dist` 产出 `vera_agent-0.1.0.tar.gz` 与 `vera_agent-0.1.0-py3-none-any.whl`
- `scripts/smoke_installed_wheel.py --dist /private/tmp/vera-phase7-acceptance-dist --workspace /private/tmp/vera-phase7-acceptance-workspace` 退出码 0（约 150s）；覆盖 `--help`/`--version`、无 Provider、非 TTY 默认模式、`-c`/`-r`、JSON `/sessions`、v1 Journal 列表重建、inspect/repair dry-run、`/instructions`、`vera init` 不写工作区、`vera run/eval`
- `git diff --check` 无空白错误
- warning 来自 Typer `is_flag` 与既有 `tests/pty` 的 `forkpty` DeprecationWarning
- PTY：`test_pty_json_resume_picker_has_no_ansi` 在 5s 超时下会只收到 stdin 回显后被 SIGTERM；探针冷启动约 11s，超时改为 20s 后稳定通过。沙箱复跑会因 `out of pty devices` 失败，不计入产品回归

## 阶段七体验规格（12 条）

| # | 条件 | 栏 | 说明 |
|---|---|---|---|
| 1 | 启动即可识别 Vera、工作区、会话、模型、权限 | 自动验证且通过 | 任务 0039；Pilot/快照。Terminal.app 第 1 项已过 |
| 2 | 深海/Unicode/ASCII/高对比/无色 | 自动验证且通过 | 任务 0039；产品矩阵三主题 |
| 3 | 用户/助手主轴，工具次级，Diff/审批/验证/失败可辨 | 自动验证且通过 | 任务 0040；层级测试 |
| 4 | 用户消息锚点与原始 `HH:mm` | 自动验证且通过 | 任务 0040；产品矩阵锚点。滚动替换人工通过 |
| 5 | Composer 箭头不进草稿；状态带上下文/模型/推理 | 自动验证且通过 | 任务 0039/0040。80×24 连续可读人工通过；发现 47 占用数字已复验 |
| 6 | 审批卡无中断空白，三按钮连续可见 | 自动验证且通过 | 任务 0040 尺寸矩阵。第 4 项 C 人工通过 |
| 7 | 60×16/80×24/120×40 与 Resize | 自动验证且通过 | 产品矩阵 Resize。人工 60×16、Resize、NO_COLOR、dumb、异常退出通过；120×40 未单独定档 |
| 8 | 退出/继续/选择/损坏不重复副作用 | 自动验证且通过 | 产品矩阵失败路径；wheel `-c`/`-r` |
| 9 | 项目说明不授权限，init 须审批 | 自动验证且通过 | 任务 0043；wheel `/instructions`/`vera init` |
| 10 | TUI 视觉不改 Plain/JSON 语义 | 自动验证且通过 | `test_phase_7_cli_semantics.py` 与产品矩阵跨表面 |
| 11 | 完整非 live、PTY、Pilot、快照、静态门禁、wheel | 自动验证且通过 | 见质量门禁 |
| 12 | 用户原文封存确认 | Not run | 必须用户写出「CLI 版本达到预期，可以封存」 |

## 持久化会话规格（18 条）

| # | 条件 | 栏 | 说明 |
|---|---|---|---|
| 1 | `vera` 即使有历史也新建 | 自动验证且通过 | 任务 0037 |
| 2 | `-c` 只恢复本 workspace 最近可恢复会话 | 自动验证且通过 | 产品矩阵 + wheel |
| 3 | `-r` TTY 选择；明确 ID 三模式可恢复 | 自动验证且通过 | 任务 0037；TTY 选择与明确 ID（TUI）人工通过。Plain/JSON 明确 ID 人工 `Not run` |
| 4 | 恢复后第二轮含必要上下文 | 自动验证且通过 | 产品矩阵 continue 含第一轮用户文本 |
| 5 | `/compact` 后重启只注入摘要 | 自动验证且通过 | 任务 0036 store 测试。真实重启人工通过 |
| 6 | Journal 不复制工具/Diff/审批正文 | 自动验证且通过 | 任务 0034–0036 |
| 7 | 完成/失败/取消/已应用 turn 可恢复 | 自动验证且通过 | 任务 0036 |
| 8 | 权限、符号链接、sequence、版本、损坏分类 | 自动验证且通过 | 任务 0035 |
| 9 | 崩溃追加前/中/后不重复副作用 | 自动验证且通过 | 任务 0035/0036 |
| 10 | workspace 不匹配、未来版本、中间损坏拒绝注入 | 自动验证且通过 | 产品矩阵失败路径 |
| 11 | 保存失败保留 Run，显示 `unsaved` | 自动验证且通过 | 产品矩阵 |
| 12 | TUI 恢复不铺开旧工具噪音 | 自动验证且通过 | 任务 0040 有界时间线。观感人工 `Not run` |
| 13 | Plain/JSON 无 ANSI/提示符 | 自动验证且通过 | 产品矩阵与 wheel |
| 14 | 恢复后 `/status` `/context` `/new` `/clear` `/compact` `/sessions` | 自动验证且通过 | 任务 0037。人工 `/new`/`/clear`/`/compact`/`/sessions` 通过 |
| 15 | 自动测试不读真实 Key、不改真实工程 | 自动验证且通过 | 门禁清除 Provider 环境 |
| 16 | 静态门禁与 wheel smoke | 自动验证且通过 | 见质量门禁 |
| 17 | Terminal.app 主路径走查 | 自动验证且通过 | [dogfood](phase-7-manual-dogfood.md) 第 1 项已过 |
| 18 | 持续 dogfood 无未关闭 Critical/High，且用户封存 | Not run | 第 12 条 + 20 次 Run |

## 项目指令规格（8 条）

| # | 条件 | 栏 | 说明 |
|---|---|---|---|
| 1 | 双文件存在/缺失加载顺序确定 | 自动验证且通过 | 任务 0043 |
| 2 | `VERA.md` 不能覆盖 Policy/Approval | 自动验证且通过 | 任务 0043 |
| 3 | 符号链接、非 UTF-8、竞态、大小上限跳过 | 自动验证且通过 | 任务 0043 |
| 4 | Run 快照，恢复不把旧 hash 当当前事实 | 自动验证且通过 | 任务 0043 |
| 5 | `/instructions` 三模式不泄露正文 | 自动验证且通过 | 任务 0043；wheel |
| 6 | `/init` 与 `vera init` 只提议根 `VERA.md` | 自动验证且通过 | 任务 0043 |
| 7 | 已存在文件时最小增量；取消/拒绝不写 | 自动验证且通过 | 任务 0043 |
| 8 | 自动、wheel、真实 Terminal.app 无静默写入 | 自动部分通过；Terminal.app `Not run` | 任务 0043 待用户三工程走查 |

## 已接受限制

- 真实 Terminal.app、20 次跨日 dogfood、封存原文均未完成，不把阶段七标为 Complete。
- iTerm2 / Warp / Linux / Windows Terminal 仍为阶段六遗留 `Not run`，不阻塞本任务自动栏。
- `VeraTestDemo` Git 索引残留 `AD build/`，未取消暂存、未改 `.gitignore`。

## 明确未做

- 未将阶段七标为 Complete，未开始阶段八，未引入桌面框架
- 未读取真实 Provider Key，未跑 live
- 未把 Textual Pilot、SVG 或快照当作 Terminal.app 证据
- 未收到「CLI 版本达到预期，可以封存」
