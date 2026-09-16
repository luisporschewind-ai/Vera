# 阶段七人工 dogfood

**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)  
**任务：** [0041](../tasks/0041-phase-7-product-acceptance-and-dogfood.md)  
**日期：** 2026-09-16  
**结果：** 2026-09-16 原生 Terminal.app 开始主路径走查。发现 38–41 为 High/Medium，修正见 [任务 0044](../tasks/0044-cli-dogfood-propose-and-sticky.md)。第 2–5 项仍为 `Not run`。自动测试不能填写“实际”栏。

严重度：Critical（权限/数据/错误应用）、High（主流程不可用/输入丢失/状态误导）、Medium（高频摩擦）、Low（视觉细节）。

## 共用记录栏

| 字段 | 含义 |
|---|---|
| 日期 | 走查日期 |
| 环境 | 终端、尺寸、locale、颜色/动画、工程 |
| 工程 | 真实工程短名，不写私有路径正文 |
| 步骤 | 实际操作顺序 |
| 预期 | 规格要求的可观察结果 |
| 实际 | 用户观察到的结果；未走查保持 `Not run` |
| 严重度 | Critical / High / Medium / Low / 无 |
| 证据 | 脱敏文本或截图路径；禁止 Key、请求正文、源码正文 |

## 1. 主路径：新建到继续

| 字段 | 内容 |
|---|---|
| 日期 | 2026-09-16 |
| 环境 | 原生 macOS Terminal.app 96×42；`vera 0.1.0+b284bb2`；deepseek-flash；审批 manual |
| 工程 | VeraTestDemo（Swift/Xcode） |
| 步骤 | 新会话 → 请为第四个页面添加测试按钮并点击提示测试 |
| 预期 | 会话可恢复；第二轮理解“刚才/继续”；审批默认 Cancel；验证产物不污染工程；旧 run 证据仍可打开 |
| 实际 | 部分走查。工程根未长出 `build/`。未进入审批：两次 `propose_changeset` 报 `verification_artifact_isolation_unavailable` 后任务失败 `model_error` / `provider_request_invalid` / thinking 模式未回传 `reasoning_content`。用户消息 sticky 不在标题下而叠在时间线中部。缩放后右侧有残留。会话上下文条保持 0%。未做到退出/`-c`/旧 run。 |
| 严重度 | High（发现 38、39）；Medium（发现 40、41） |
| 证据 | 脱敏：失败诊断含 `HTTP 400` 与 `reasoning_content`；验证错误码 `verification_artifact_isolation_unavailable`；无工作区副作用 |

## 2. 恢复与会话维护

| 字段 | 内容 |
|---|---|
| 日期 | |
| 环境 | 原生 Terminal.app |
| 工程 | |
| 步骤 | `-r` 选择历史、明确 ID 恢复、`/compact` 后重启、`/new`、`/clear`、取消、失败、恢复、无 Git、dirty workspace |
| 预期 | 选择器可用；compact 后旧对话仍可查看；`/new`/`/clear` 不丢 Run 证据；无 Git/dirty 有克制提示 |
| 实际 | Not run |
| 严重度 | |
| 证据 | |

## 3. 尺寸、兼容与导航

| 字段 | 内容 |
|---|---|
| 日期 | |
| 环境 | 60×16、80×24、120×40、Resize、`NO_COLOR`、`TERM=dumb`、关闭动画、CJK |
| 工程 | |
| 步骤 | 复制、滚动、异常退出；确认用户消息锚点替换且右侧时间不变 |
| 预期 | 输入不被挡；审批事实不丢；锚点替换正确；箭头不进入实际输入 |
| 实际 | Not run |
| 严重度 | |
| 证据 | |

## 4. 信息层级与状态带

| 字段 | 内容 |
|---|---|
| 日期 | |
| 环境 | 80×24 原生 Terminal.app |
| 工程 | |
| 步骤 | 观察对话主轴、工具一行摘要、Diff/审批/验证/失败、底部状态带 |
| 预期 | 审批卡上下无中断空白；状态带左右在 80×24 连续可读；无显式推理时显示“模型默认/不可用”；上下文是会话预算不是精确 token 窗口 |
| 实际 | Not run |
| 严重度 | |
| 证据 | |

## 5. 持续个人 dogfood（20 次）

目标：至少 5 个不同自然日、2 个真实工程、累计 20 个完成/失败/取消 Run，其中至少 5 次跨进程继续或恢复。每条只记脱敏摩擦。

| # | 日期 | 工程 | 步骤摘要 | 结果 | 跨进程 | 严重度 | 证据 |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-16 | VeraTestDemo | 第四页加测试按钮 | 失败 `model_error` | 否 | High | 发现 38 |
| 2 | | | | Not run | | | |
| 3 | | | | Not run | | | |
| 4 | | | | Not run | | | |
| 5 | | | | Not run | | | |
| 6 | | | | Not run | | | |
| 7 | | | | Not run | | | |
| 8 | | | | Not run | | | |
| 9 | | | | Not run | | | |
| 10 | | | | Not run | | | |
| 11 | | | | Not run | | | |
| 12 | | | | Not run | | | |
| 13 | | | | Not run | | | |
| 14 | | | | Not run | | | |
| 15 | | | | Not run | | | |
| 16 | | | | Not run | | | |
| 17 | | | | Not run | | | |
| 18 | | | | Not run | | | |
| 19 | | | | Not run | | | |
| 20 | | | | Not run | | | |

## 缺陷处置

| # | 来源 | 摘要 | 严重度 | 处置 |
|---|---|---|---|---|
| 38 | 主路径 | `propose_changeset` 验证隔离失败只发 `tool.completed`，不写回 `role=tool`；thinking 下一轮 400：`reasoning_content` must be passed back | High | [任务 0044](../tasks/0044-cli-dogfood-propose-and-sticky.md) 本阶段修复 |
| 39 | 主路径 | 用户消息 sticky 叠在时间线中部，不贴标题下方 | High | 0044 本阶段修复 |
| 40 | 主路径 | 窗口缩放后右侧单元格残留 | Medium | 0044 本阶段修复 |
| 41 | 主路径 | 短会话后上下文条仍显示 0%（200000 字节预算四舍五入） | Medium | 0044 本阶段修复（占用>0 显示 `<1%`） |
| — | 主路径 | 工程根未长出 `build/` 等产物 | 无 | 通过 |

发现 38/39 关闭前不把阶段七标为 Complete。
