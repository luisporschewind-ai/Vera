# 阶段七人工 dogfood

**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)  
**任务：** [0041](../tasks/0041-phase-7-product-acceptance-and-dogfood.md)  
**日期：** 2026-09-16  
**结果：** 2026-09-16 至 2026-09-17 原生 Terminal.app 第 1–4 项走查通过。发现 38–41、43–49 已复验关闭。发现 42 Low 未关。20 次 dogfood 未完成。未收到封存原文。

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
| 环境 | 原生 macOS Terminal.app；先 96×42，继续时 101×52；`vera -c`；deepseek-flash；审批 manual |
| 工程 | VeraTestDemo（Swift/Xcode） |
| 步骤 | 新会话 → 第四页加测试按钮 → 审批/验证 → 退出 → `vera -c` → 输入「继续」 |
| 预期 | 会话可恢复；第二轮理解“刚才/继续”；审批默认 Cancel；验证产物不污染工程；旧 run 证据仍可打开 |
| 实际 | 首次失败后 `b42ed76` 复验通过。`vera -c` 标题为「恢复会话」，「继续」能引用上一轮 changeset/run 与第四页已落地。Sticky 贴标题下，上下文条 `<1%`。`6c1ba9d` 后续写第五页通过。`/runs` 与 `/show` 通过。助手列表把 `FourthViewController.swift` / `Base.lproj` 从中间折行（发现 42）。 |
| 严重度 | 发现 38–41、43 已复验关闭；`/runs` 通过 |
| 证据 | 脱敏：失败诊断含 `HTTP 400` 与 `reasoning_content`；验证错误码 `verification_artifact_isolation_unavailable`；无工作区副作用 |

## 2. 恢复与会话维护

| 字段 | 内容 |
|---|---|
| 日期 | 2026-09-16 |
| 环境 | 原生 Terminal.app |
| 工程 | VeraTestDemo |
| 步骤 | `-r` 选择历史、明确 ID 恢复、`/compact` 后重启、`/new`、`/clear`、取消、失败、恢复、无 Git、dirty workspace |
| 预期 | 选择器可用；compact 后旧对话仍可查看；`/new`/`/clear` 不丢 Run 证据；无 Git/dirty 有克制提示 |
| 实际 | `193d35b` 后 `vera -r` 可打开选择器并恢复会话。`fb4c256` 后 `/new`/`/clear` 回到干净首屏。2026-09-17：明确 ID、`/compact` 后重启、失败/恢复、无 Git、dirty 通过。C 首次 Esc 无效（发现 48）；`cfeb240` 后运行中 Esc 取消复验通过。取消后曾 Error / Worker 失败（发现 49）；`661a894` 后复验通过。 |
| 严重度 | 发现 44–45、48–49 已复验关闭 |
| 证据 | 用户确认选择器、明确 ID、`/new`/`/clear`、`/compact`、Esc 取消、失败/恢复、无 Git、dirty 通过 |

## 3. 尺寸、兼容与导航

| 字段 | 内容 |
|---|---|
| 日期 | 2026-09-16 |
| 环境 | 原生 Terminal.app；Resize、滚动、复制、高对比、60×16、NO_COLOR、TERM=dumb、异常退出 |
| 工程 | VeraTestDemo |
| 步骤 | 复制、滚动、异常退出；确认用户消息锚点替换且右侧时间不变 |
| 预期 | 输入不被挡；审批事实不丢；锚点替换正确；箭头不进入实际输入 |
| 实际 | 全部通过。`TERM=dumb vera` 拒绝 TUI 并提示 `--plain`/`--json`；`TERM=dumb vera --plain` 可会话后退出；随后普通 `vera` 仍进 TUI。120×40 未单独定档（曾用约 110×46）。`VERA_NO_ANIMATIONS` 未单独跑。 |
| 严重度 | 无 |
| 证据 | 用户确认 A/B/C/D 通过 |

## 4. 信息层级与状态带

| 字段 | 内容 |
|---|---|
| 日期 | 2026-09-17 |
| 环境 | 80×24 原生 Terminal.app |
| 工程 | VeraTestDemo |
| 步骤 | 观察对话主轴、工具一行摘要、Diff/审批/验证/失败、底部状态带 |
| 预期 | 审批卡上下无中断空白；状态带左右在 80×24 连续可读；无显式推理时显示“模型默认/不可用”；上下文是会话预算不是精确 token 窗口；短条旁显示当前已用/上限字节 |
| 实际 | 0 定尺寸、B 对话主轴、C Diff/审批/验证、D 失败可辨通过。A 首次只有百分比/`<1%`（发现 47）；`5412f00` 后短条旁显示当前会话预算已用/上限字节，复验通过。 |
| 严重度 | 发现 47 已复验关闭 |
| 证据 | 用户确认 0/A/B/C/D 通过 |

## 5. 持续个人 dogfood（20 次）

目标：至少 5 个不同自然日、2 个真实工程、累计 20 个完成/失败/取消 Run，其中至少 5 次跨进程继续或恢复。每条只记脱敏摩擦。

| # | 日期 | 工程 | 步骤摘要 | 结果 | 跨进程 | 严重度 | 证据 |
|---|---|---|---|---|---|---|---|
| 1 | 2026-09-16 | VeraTestDemo | 第四页加测试按钮 | 失败 `model_error` | 否 | High | 发现 38，已修 |
| 2 | 2026-09-16 | VeraTestDemo | 同路径复验 `b42ed76` | 通过 | 否 | 无 | 发现 38–41 关闭 |
| 3 | 2026-09-16 | VeraTestDemo | `vera -c` 后输入「继续」 | 完成（只读，未改文件） | 是 | Low | 发现 42 折行 |
| 4 | 2026-09-16 | VeraTestDemo | `vera -c` 后「新建第五页并从第四页接入跳转」 | 失败 `model_error` | 是 | High | 发现 43，已修 |
| 5 | 2026-09-16 | VeraTestDemo | 同路径复验 `6c1ba9d` | 通过 | 是 | 无 | 发现 43 关闭 |
| 6 | 2026-09-17 | VeraTestDemo | 运行中 Esc 取消「解释第四个 VC」 | 失败 Worker | 否 | High | 发现 49，已修 |
| 7 | 2026-09-17 | VeraTestDemo | 同路径复验 `661a894` | 通过（已取消） | 否 | 无 | 发现 49 关闭 |
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
| 38 | 主路径 | propose 失败未回写 tool，thinking 下一轮 400 | High | 0044 修复；用户 2026-09-16 Terminal.app 复验通过 |
| 39 | 主路径 | sticky 叠在时间线中部 | High | 0044 修复；复验通过 |
| 40 | 主路径 | 缩放右侧残留 | Medium | 0044 修复；复验通过 |
| 41 | 主路径 | 短会话上下文条显示 0% | Medium | 0044 修复；复验通过 |
| — | 主路径 | 工程根未长出 `build/` | 无 | 通过 |
| 42 | `vera -c` | 助手 Markdown 路径高亮把 `FourthViewController.swift`、`Base.lproj` 从中间折行 | Low | 本阶段可修或后续汇总；不挡继续/恢复 |
| 43 | `vera -c` 续写 | 大 `propose_changeset` 参数 JSON 非法/截断后整轮 `model_error` | High | 0045 修复；用户 2026-09-16 Terminal.app 复验通过 |
| 44 | 会话维护 | `vera -r` 无参数：Option requires an argument | High | 0047 修复；用户 2026-09-16 Terminal.app 复验通过 |
| 45 | 会话维护 | `/new`/`/clear` 后上一会话仍显示，未清屏 | High | 0047 修复；用户 2026-09-16 Terminal.app 复验通过 |
| 46 | 主题 | `/theme high-contrast` 残影、右侧异常 | Medium | 0046 修复；用户 2026-09-16 Terminal.app 复验通过 |
| 47 | 信息层级 | 状态带短条旁只显示百分比/`<1%`，看不到当前会话预算已用/上限字节 | Medium | 0048 修复；用户 2026-09-17 Terminal.app 复验通过 |
| 48 | 会话维护 | 运行中按 Esc 取消无效；状态带写了 Esc 但未绑定 | High | 0049 修复；用户 2026-09-17 Terminal.app 复验通过 |
| 49 | 会话维护 | Esc 取消后出现 Error「当前有运行中的任务」和 Worker 失败 | High | 0050 修复；用户 2026-09-17 Terminal.app 复验通过 |

发现 38–41、43–49 已关闭。第 1–4 项走查已过。发现 42 Low 未关。20 次 dogfood 未完成，阶段七仍不 Complete。
