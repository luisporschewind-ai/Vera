# 任务 0028：终端兼容、可访问性与性能

> 供 Cursor 执行：按 `superpowers:executing-plans` 实施；性能证据必须记录机器与终端，不能把单机结果泛化成全平台承诺。

**状态：** Planned
**执行就绪：** 任务 0027 合并后
**分支：** `phase-6/0028-terminal-compatibility-performance`
**依赖：** 任务 0027 已合并
**规格：** [阶段六 CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 目标与边界

保证小终端、无色/低能力终端、CJK、键盘-only、Resize、长输出和异常退出可用；让 500 block 与 10,000 行折叠输出不拖垮输入响应。

## 实施步骤

### 1. 终端能力与动画策略

**修改：**

- 新增 `src/vera/terminal/capabilities.py`
- `src/vera/terminal/theme.py`
- `src/vera/terminal/streaming.py`
- `src/vera/terminal/app.py`
- 新增 `tests/terminal/test_capabilities.py`
- `tests/terminal/test_streaming.py`

测试 `NO_COLOR`、`TERM=dumb`、`VERA_NO_ANIMATIONS`、非 TTY 和 reduced-motion 配置；动画上限 10 FPS、Markdown 刷新不超过 20 FPS。能力不明时采用保守静态展示。

### 2. 尺寸、CJK 与键盘-only

**修改：**

- `src/vera/terminal/app.py`
- `src/vera/terminal/widgets/composer.py`
- `src/vera/terminal/widgets/timeline.py`
- `src/vera/terminal/widgets/approval.py`
- `tests/terminal/test_layout_matrix.py`
- `tests/terminal/test_keyboard_flows.py`

用 60×16、80×24、120×40 Pilot 覆盖启动、输入、Diff、审批、失败和恢复；CJK/英文 locale 下关键字段不被截断。鼠标不可用时，Tab/Shift+Tab、方向键、Enter、Esc/Ctrl+C 完成全部主流程。

### 3. 有界时间线与长输出虚拟化

**修改：**

- `src/vera/terminal/widgets/timeline.py`
- `src/vera/presentation/projector.py`
- 新增 `src/vera/terminal/performance.py`
- 新增 `tests/performance/test_terminal_timeline.py`

先写 500 block、10,000 行折叠输出、持续 stream+Resize 压力测试，断言折叠内容不按行创建 Widget。实现窗口化 block 挂载、懒加载详情和确定性 cache；未决审批/失败/Diff 不得被预算逐出。

### 4. PTY 与退出恢复

**修改：**

- 新增 `tests/pty/test_terminal_lifecycle.py`
- `src/vera/terminal/app.py`
- `src/vera/cli.py`

PTY 测试正常退出、Ctrl+C、异常、Provider 错误、Resize 风暴、stdin 关闭，断言 alternate screen、光标、回显和终端 mode 恢复；Plain/JSON 不输出 TUI 控制序列。

### 5. 兼容矩阵记录

**修改：**

- 新增 `docs/evals/phase-6-terminal-compatibility-matrix.md`
- `docs/INSTALL.md`

自动记录 Pilot/PTY 环境；人工列出 Terminal.app（必过）、iTerm2、Warp、常见 Linux 终端和 Windows Terminal。未实测项为 `Not run`，不得推断支持。记录版本、尺寸、locale、颜色、动画和结果。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/terminal tests/pty tests/performance/test_terminal_timeline.py -q
```

在参考 Intel Mac 上另记录启动、按键 p95、展开/折叠时间；数值与规格阈值对照。再运行[阶段六共同门禁](phase-6-execution-order.md)，更新任务证据并提交：

```bash
git commit -m "feat: harden terminal compatibility and performance"
```

## 验收标准

- 三种尺寸、无色、静态动画、CJK 和键盘-only 自动矩阵通过。
- 长输出不按行创建 Widget，输入响应达到记录阈值或有明确差异。
- 所有退出路径恢复终端状态，Plain/JSON 无控制序列污染。
- 兼容矩阵只陈述实际证据。
