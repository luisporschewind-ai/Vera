# 任务 0073：已接受 V4 四行加粗 Logo

**状态：** Ready for manual acceptance
**授权：** 2026-09-24 用户确认 V4 加粗设计并要求按图实现；不含提交、推送或阶段切换。
**范围：** 阶段七封存后的定向视觉修正。
**规格：** [视觉 Token](../specs/2026-09-13-vera-cli-visual-tokens.md)

## 设计与实现边界

- [已接受设计图](../evals/artifacts/vera-logo-v4.png)、[冻结模板](../evals/artifacts/vera-logo-v4.json)一一对应；以 27 列 × 4 行字符和 54×16 点核对字形。
- 保留 V 收尖、R 独立斜腿、A 外撇下摆与一个空白字符字距；字重来自点阵，不额外施加终端 bold。
- 四行欢迎区、三行右侧事实、静态 logo 色、四行扫光、ASCII/高对比/无色回退；任务后仍是一行。
- 在隔离工作树实施，保留正式工作区现有 Skills/会话改动。通过验证后仅同步本任务文件，不提交。
- 字符一致不等于跨字体像素一致；Terminal.app 人工验收单列。

## 验证计划

- 冻结模板逐字符、逐点对照；欢迎区第四行完整、三尺寸布局与第一次任务收起。
- 运行 terminal/presentation、Phase 7 矩阵及相关 PTY 回归，Ruff、格式、Mypy、git diff --check。
- 用产品输出重渲染设计图，核对正常/放大视图；必要时原生终端本地离线预览。
- 不调用真实 Provider；测试产物写入临时目录或工作区外。

## 验证结果

- 设计核对：产品 `select_brand_mark` 输出与冻结 JSON 四行字符串完全一致；逐点解码核对全部 54×16 点，字间空列为 6/13/20。
- 将产品输出传入设计原渲染器，重绘 PNG 与已接受 V4 PNG 的 `cmp` 比较通过（文件逐字节一致）。这证明同一渲染条件下字形还原，不代表跨字体像素相同。
- 原生 Terminal.app 离线 TUI：临时 workspace/state、FakeModel、无 Provider 请求，170×43；实际 `render_lines` 为 27 列 × 4 行，与模板逐字符一致，静态色 `#548EA0`，无额外 bold。[真实终端截图](../evals/artifacts/vera-logo-v4-terminal.png)。预览进程已退出，专用预览窗口已关闭。
- 聚焦品牌/欢迎区/三尺寸/主题检查：26 passed；新增主题/字重检查纳入下面的扩展回归。
- 全仓 Ruff、格式检查（457 files）、Mypy（182 source files）、`git diff --check` 通过。
- terminal/presentation、Phase 7 矩阵及 PTY 扩展回归：267 passed in 377.50s。
- 正式 `/Users/admin/.local/bin/vera` 已核对为 editable 安装，导入源为 `/Users/admin/Vera/src/vera`；同步本任务代码后重新启动生效。
- 用户对实际安装后的最终主观视觉验收待完成；不改变阶段八/九状态。
