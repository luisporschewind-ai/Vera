# 任务 0039：Vera 标识、主题与启动状态实现

> 供主实现 Agent 执行：只有任务 0038 的视觉规格为 Accepted 后才能按 `superpowers:test-driven-development` 实施。

**状态：** Planned
**执行就绪：** 否；等待任务 0038 的用户视觉确认
**分支：** `phase-7/0039-cli-brand-theme`
**依赖：** 任务 0038
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、任务 0038 产生并获接受的视觉 Token 规格

## 目标与边界

把已确认的 Vera 标识、深海主题、高对比/无色回退、启动状态区和 Composer 下方双侧状态带实现到 TUI。实现只投影 `SessionStatus`、TerminalCapabilities 与既有 Event，不改变 Core、审批、权限或 Run 语义；推理强度没有权威值时必须显示“模型默认/不可用”，不能由 UI 猜测。

## 展示接口

新增 `src/vera/terminal/brand.py`：

```python
BrandMode = Literal["full", "compact", "ascii"]

class BrandMark(BaseModel):
    mode: BrandMode
    lines: tuple[str, ...]
    accessible_label: str

def select_brand_mark(*, columns: int, rows: int, unicode: bool, no_color: bool) -> BrandMark: ...
```

新增 `VeraWelcome` Widget，只接收 `BrandMark` 与结构化 `SessionStatus`。`VeraHeader` 保留长期状态带职责，不能同时复制完整首屏内容。

新增 `src/vera/presentation/footer_status.py`，把 `SessionStatus` 与当前 `ActivityState` 投影为 UI 无关的 `FooterStatus`：会话上下文已用/上限/比例、模型 profile/name、有效推理强度状态、活动文案、取消提示和未读数。`src/vera/terminal/widgets/status_line.py` 只排版该模型；不得读取配置文件、检查模型名或解析回答文本。

`src/vera/session/models.py` 增加 Provider 中立事实，具体接口固定为：

```python
class ReasoningStatus(BaseModel):
    mode: Literal["explicit", "provider_default", "unavailable"]
    effort: str | None = None

class SessionStatus(BaseModel):
    # 保留既有字段
    reasoning: ReasoningStatus
```

`explicit` 要求 `effort` 非空且对应值已经被当前 Adapter 请求采用；其他两态要求 `effort is None`。本任务没有显式推理配置入口时，真实 Provider 默认填 `provider_default`，Fake/无法确认能力的 Adapter 填 `unavailable`。

## 实施步骤

### 1. Logo 选择与纯文本回退

- [ ] 新增 `tests/terminal/test_brand.py`，先覆盖 full/compact/ascii 阈值、无 Nerd Font、行宽、CJK 邻接和 accessible label。
- [ ] 新增 `src/vera/terminal/brand.py`，逐字符保证选中形态不超过可用列；60×16 不超过视觉规格冻结的最大行数。
- [ ] `TERM=dumb`、非 Unicode 或不可靠宽度时使用 ASCII，不输出控制字符或 Emoji。

### 2. 语义 Theme Token

- [ ] 扩展 `tests/terminal/test_theme.py`，覆盖 default/high-contrast/no-color 三组完整 Token、`NO_COLOR` 优先级和未知主题拒绝。
- [ ] 扩展 `src/vera/terminal/theme.py`，让主题名映射冻结的语义 Token；`theme.tcss` 只引用这些语义，不按 Event 文案匹配颜色。
- [ ] 修改 `src/vera/terminal/theme.tcss`，统一背景、表面、正文、弱化、焦点、成功、警告、危险和 Diff 色；无色主题保留边框/标签/符号差异。

### 3. 启动首屏

- [ ] 新增 `src/vera/terminal/widgets/welcome.py` 和 `tests/terminal/test_welcome.py`，覆盖 new/resumed、Git clean/dirty、非 Git、saved/unsaved 和权限摘要。
- [ ] 首屏固定优先级：Vera 标识 → workspace/session/model → 权限边界 → 可执行下一步；次要诊断留给 `/status`/`/doctor`。
- [ ] 更新 `src/vera/terminal/app.py` 组合 Welcome、Header、Timeline、Composer、StatusLine；Resize 后只切换 BrandMode，不重建 SessionController。

### 4. 运行状态语义

- [ ] 先新增 `tests/presentation/test_footer_status.py`，覆盖上下文 0%、正常、warning、100% 上限，模型 profile/name，显式推理强度、`provider_default`、`unavailable`，以及 idle/running/approval/verification/completed/cancelled/failed/recovery/unsaved。
- [ ] 扩展 `SessionStatus` 的 Provider 中立推理状态；当前执行链只有在 Adapter 已实际采用显式强度时才能标记 `explicit`，否则使用 `provider_default` 或 `unavailable`。本任务不增加虚假的强度切换入口。
- [ ] 实现 `FooterStatus` 纯投影，并扩展 `tests/terminal/test_status_line.py` 与 `test_app.py`，固定左侧“会话上下文条 + 百分比”、右侧“模型 + 推理强度”、中部活动/取消/未读提示的优先级。
- [ ] 修改 `VeraHeader`/`VeraStatusLine`，避免顶部与底部重复模型和活动事实；状态始终有文字，颜色和动画只增强，不作为唯一信息。
- [ ] 终端进度采用固定宽度短条形而非环形；高对比/无色保留边界与百分比，60×16 按任务 0038 用户确认的优先级缩短字段但不伪造零值。
- [ ] `VERA_NO_ANIMATIONS`、reduced motion 或 no-color 时使用静态符号，不伪造进度百分比。

### 5. 尺寸、快照与终端能力

- [ ] 更新 `tests/terminal/test_layout_matrix.py`、`test_snapshots.py` 和快照夹具，固定 60×16、80×24、120×40 的 new/resumed/approval/failure。
- [ ] 断言小终端仍可看到审批事实和 Composer；Logo 必须先降级或隐藏，不能挤走操作区。
- [ ] 添加 Plain/JSON 回归，证明视觉改动没有 ANSI 泄漏或结构化字段变化。

## 局部验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/presentation/test_footer_status.py tests/session/test_status.py tests/terminal/test_brand.py tests/terminal/test_theme.py tests/terminal/test_welcome.py tests/terminal/test_status_line.py tests/terminal/test_layout_matrix.py tests/terminal/test_snapshots.py tests/terminal/test_app.py tests/cli/test_plain_session.py tests/cli/test_json_session.py -q
git diff --check
```

再运行共同门禁，更新证据后提交：

```bash
git commit -m "feat: add Vera terminal identity and themes"
```

## 验收标准

- 默认启动可明确识别 Vera，并优先显示 workspace/session/model/权限和下一步。
- Composer 下方双侧状态带持续显示真实的会话上下文占用、模型与有效推理强度；Provider 缺值时不显示伪造档位。
- 活动、取消和未读提示与上述事实共享单一状态带，顶部不再重复造成散乱。
- full/compact/ascii 自动降级，不依赖 Nerd Font 或颜色。
- 三类主题语义一致，状态移除颜色后仍可理解。
- Plain/JSON、审批默认值、Core Event 和退出码未被视觉实现改变。
