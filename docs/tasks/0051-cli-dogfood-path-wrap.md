# 任务 0051：走查发现 42（折行）与回答署名 Vera

> 供主实现 Agent 执行：阶段七 Low 视觉与自称修正。不开始阶段八。

**状态：** Done
**执行就绪：** 是
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0041 自动门禁
**规格：** [CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)、[富终端 UI](../specs/2026-09-11-rich-terminal-ui.md)

## 背景

用户 2026-09-16 在 `vera -c` 续写走查中看到：助手 Markdown 把 `FourthViewController.swift`、`Base.lproj` 从中间折行。中文与反引号路径之间没有空格时，Rich 把整段当成一个词并按单元格切断。2026-09-17 Python 工程走查再次看到「安全边界」被拆成「安 / 全边界」，时间线标题为「助手」，自我介绍称「Vera Core 的受控编码 Agent」。

## 目标与边界

- 标识符/文件名（含 `.` `_` `-`）尽量整段换行，不从中间切断。
- 中文词（如「安全边界」）不按单元格从中间切断。
- 长路径优先在 `/` 处换行。
- 时间线回答标题为 `Vera`；系统提示自称 Vera，不再使用「受控编码 Agent」。
- 不改审批、不读取真实 Key、不引入桌面框架。

## 实施步骤

- [x] 失败测试：CJK 紧邻路径、长 `/` 路径、「安全边界」在给定宽度下保持完整。
- [x] 助手 Markdown 按路径/CJK 感知折行；按正文内容宽度渲染，避免二次切断。
- [x] Projector 标题与 `SYSTEM_PROMPT` 自称改为 Vera。

## 验证

```bash
uv run pytest tests/terminal/test_blocks.py tests/presentation/test_projector.py tests/runtime/test_untrusted_context.py -q
git diff --check
```

## 验证证据

- 2026-09-17：上列测试与 `test_project_instructions` 共 `62 passed`；`ruff`/`mypy` 对改动模块通过。
- 2026-09-17 Codex 按用户授权在原生 Terminal.app / 脱敏 Python 临时工程代测：`FourthViewController.swift`、`Base.lproj` 保持完整，长路径在 `/` 边界换行，「安全边界」未被切开；回答标题为 `Vera`。发现 42 关闭。

## 未决

- 20 次 dogfood 仍归 0041。
- 2026-09-17 用户原文确认「CLI 版本达到预期，可以封存」。
