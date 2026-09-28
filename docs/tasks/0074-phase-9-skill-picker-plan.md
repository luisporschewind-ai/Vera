# Vera CLI Skill 交互列表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `/skills` 结构化列表上增加 TUI 内可分类、可上下选择的浮层；Enter 只选中下一次任务 Run 的 Skill 并回到输入框。
**Architecture:** Core 继续负责发现、冲突、选择和 Run Snapshot。主 TUI 新增独立浮层 Widget，只消费 `skill.listed` 的公共摘要；选中后向 `SessionController` 发送已有 `/skills use <skill_id>`，等待结构化 `skill.selection.changed` 确认。Plain/JSON 不引入按键 UI，也不改变命令语义。
**Tech Stack:** Python 3.12、Pydantic、Textual 8、Rich、pytest、Textual Pilot、PTY。
**Spec:** [已接受的 Skill 交互列表规格](../specs/2026-09-24-skills-interactive-picker.md)，上位规格为 [Core 原生 Skills 系统](../specs/2026-09-15-core-native-skills-system.md)。
**状态：** Native 实施与自动验证完成；未提交、未推送，人工验收待执行。

## Global Constraints

- 本计划属于阶段九体验补全；阶段八、阶段九状态不自动切换，阶段十不得开始。
- 仅 `builtin`、`user`、`workspace` 三来源；单次仅显式选择一个 Skill，不新增 `skill.toml` 字段、权限或自动触发。
- Enter 仅设置下一次任务 Run 的待用 Skill，不发送 `SubmitPrompt`，不读取 Provider Key，不执行 Skill 包脚本。
- TUI 只消费 `SkillSummary`/`SkillSelection` 和结构化 Event；不自行扫描目录、解析 Manifest 或按人类文案判断成功。
- 系统内置、用户本地、当前项目按此顺序分组；`invalid`/`incompatible` 与重复 `skill_id` 不可选，跨来源同名但完整 ID 唯一的 `conflict` 可选。
- 60×16 可安全操作，80×24 为完整基线；高对比和无色主题不能仅靠颜色表达选择与错误。
- 当前正式工作树含另一项尚未提交的 Skill 会话持久化修正（`src/vera/session/controller.py` 等）。用户已选择将该修正按文件原样带入隔离工作树、保留正式工作树原样，暂不提交或推送。新功能在包含该修正的基线上验证 `tests/session/test_skill_commands.py`。
- 若在隔离工作树实施，先运行 `uv run python -c 'import vera; print(vera.__file__)'` 核对导入的是该工作树源码；必要时显式设置该工作树的 `PYTHONPATH` 或使用独立环境，不能把正式工作树的 editable 安装误当测试通过。
- 每项实施保持单一主 Agent；每项提交、合并或推送都以用户对本计划执行与 Git 边界的明确授权为前提。绝不使用 `git add .` 或重置正式工作树。

## Review Focus

1. 同一来源两个目录声明同一个 `skill_id`：Task 1 的测试必须证明完整 ID 也拒绝歧义，已选择的 ID 在绑定前出现重复时不能静默取第一个。
2. 损坏包没有规范名称/ID、描述包含 Rich 标记或控制字符：Task 2 的测试必须证明安全占位、禁用选择、没有路径或样式注入。
3. Composer 已有草稿或弹出列表后连按两次 Enter：Task 3 的 Pilot 必须证明只发一次 `/skills use`，草稿/光标保留且没有 `SubmitPrompt`。
4. 活动 Run/待审批时输入 `/skills`：Task 3 的 Pilot 必须证明只保留原列表事实，不盖住审批，也不改变现有 Esc 取消含义。
5. 列出后来源删除、变更或 worker 报错：Task 3 的 Pilot 必须证明不显示假成功；拒绝时保留列表和原因，worker 报错时安全关闭，合法变更则显示 Core 返回的实际版本。

## 文件职责与实施顺序

| 文件 | 职责 |
| --- | --- |
| `src/vera/skills/registry.py` | 拒绝同来源重复完整 ID，保持 Core 选择权威 |
| `src/vera/terminal/widgets/skill_picker.py`（新增） | 纯行模型、来源分组、禁用规则与浮层键盘状态 |
| `src/vera/terminal/app.py` | 将 `skill.listed`/`skill.selection.changed` 接到浮层并向 Core 发既有动作 |
| `src/vera/terminal/theme.tcss` | 浮层在 60×16/80×24 与三主题下的尺寸和语义色 |
| `tests/skills/test_registry.py`、`tests/terminal/test_skill_picker.py`、`tests/terminal/test_skill_picker_integration.py` | 对应 Core、Widget、TUI 集成的红绿测试 |
| `tests/e2e/test_phase_9_client_parity.py`、`tests/pty/test_phase_9_skills.py` | 确认 Plain/JSON 结构化事实、PTY 输出和无 ANSI 回归 |
| `docs/tasks/0074-phase-9-skill-picker-plan.md`、`docs/STATUS.md` | 记录实施结果与剩余 Terminal.app/Provider 门禁 |

---

### Task 1: Core 完整 ID 歧义失败关闭

**Files:** Modify `src/vera/skills/registry.py`; Test `tests/skills/test_registry.py`、`tests/session/test_skill_commands.py`。
**Interfaces:** Consumes `SkillRegistry.resolve(selector: str, workspace_root: Path) -> SkillSelection` 和 `package_for(selection: SkillSelection, workspace_root: Path) -> SkillCandidate | None`；不改签名。Produces 与现有稳定 `skill_name_conflict` 一致的失败选择，供 Widget 禁用重复 ID。

- [ ] **Step 1: 写失败测试。** 在 `tests/skills/test_registry.py` 增加以下用例，并在 Session 测试中用 `/skills use user:python-review` 断言同一来源重复 ID 失败：

```python
import shutil


def test_registry_rejects_duplicate_full_id_even_after_prior_selection(tmp_path: Path) -> None:
    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user.mkdir()
    workspace.mkdir()
    package = write_skill(user)
    registry = SkillRegistry(SkillDiscovery(builtin_root=builtin, user_root=user))
    prior = registry.resolve("user:python-review", workspace)
    assert prior.status == "selected"
    shutil.copytree(package, user / "duplicate-directory")

    rejected = registry.resolve("user:python-review", workspace)
    assert rejected.status == "invalid"
    assert rejected.reason_codes == ("skill_name_conflict",)
    assert registry.package_for(prior, workspace) is None
```

- [ ] **Step 2: 验证红灯。** `uv run pytest tests/skills/test_registry.py::test_registry_rejects_duplicate_full_id_even_after_prior_selection -q`；预期当前 `resolve` 错选第一个、`package_for` 返回第一个包，测试 FAIL。
- [ ] **Step 3: 最小实现。** `resolve` 的完整 ID 分支在 `len(exact) > 1` 时返回 `SkillSelection(mode="explicit", selector=selector, status="invalid", reason_codes=("skill_name_conflict",))`；`package_for` 改成收集同 ID 的有效候选，仅 `len(matches) == 1` 才返回 `matches[0]`。保持现有跨来源同名、完整 ID 唯一时可选择的语义。

```python
if len(exact) > 1:
    return SkillSelection(
        mode="explicit", selector=selector, status="invalid",
        reason_codes=("skill_name_conflict",),
    )

matches = [
    item for item in self.candidates(workspace_root)
    if item.package is not None and item.package.skill_id == selection.skill_id
]
return matches[0] if len(matches) == 1 else None
```

- [ ] **Step 4: 验证绿灯及旧行为。** `uv run pytest tests/skills/test_registry.py tests/session/test_skill_commands.py -q`；预期全部 PASS，既有跨来源冲突用例仍通过。
- [ ] **Step 5: 审阅并在授权后提交。** `git diff -- src/vera/skills/registry.py tests/skills/test_registry.py tests/session/test_skill_commands.py`、`git diff --check`；仅经用户授权才 `git add` 这三个文件并 `git commit -m "fix: reject ambiguous skill ids"`。

### Task 2: 可分类的 Skill 浮层 Widget

**Files:** Create `src/vera/terminal/widgets/skill_picker.py`、`tests/terminal/test_skill_picker.py`; Modify `src/vera/terminal/theme.tcss`。
**Interfaces:** Consumes `tuple[SkillSummary, ...]` 与 `SkillSelection`；Produces `build_skill_picker_rows(summaries: tuple[SkillSummary, ...], *, selected_skill_id: str | None) -> tuple[SkillPickerRow, ...]` 和 `SkillPicker` Widget 的 `Chosen(skill_id: str)` 消息。Task 3 只能接收 `Chosen`，不得在 UI 里解析 Manifest。

- [ ] **Step 1: 写纯模型失败测试。** 测试三组顺序、缺名无效行、跨来源同名可选、同来源重复 ID 禁用、当前待用标记；输入构造只用公共 `SkillSummary`：

```python
def test_picker_rows_group_and_disable_ambiguous_ids() -> None:
    items = (
        SkillSummary(source_kind="workspace", trust_level="untrusted",
                     availability="available", skill_id="workspace:review",
                     name="review", description="工程检查"),
        SkillSummary(source_kind="user", trust_level="advisory",
                     availability="conflict", skill_id="user:review",
                     name="review", description="用户检查"),
        SkillSummary(source_kind="user", trust_level="advisory",
                     availability="conflict", skill_id="user:review",
                     name="review", description="重复身份"),
        SkillSummary(source_kind="builtin", trust_level="advisory",
                     availability="invalid", reason_codes=("skill_manifest_invalid",)),
    )
    rows = build_skill_picker_rows(items, selected_skill_id="workspace:review")
    assert [row.label for row in rows if row.kind == "heading"] == [
        "系统内置", "用户本地", "当前项目"
    ]
    assert all(not row.selectable for row in rows if row.skill_id == "user:review")
    assert any(row.skill_id == "workspace:review" and "待用" in row.label for row in rows)
    assert any("无效 Skill" in row.label for row in rows)
```

- [ ] **Step 2: 验证红灯。** `uv run pytest tests/terminal/test_skill_picker.py::test_picker_rows_group_and_disable_ambiguous_ids -q`；预期 `build_skill_picker_rows` 未定义而 FAIL。
- [ ] **Step 3: 锁定不可信展示输入。** 同一测试文件加入无规范名称与控制字符用例，断言不可选、原因可读，且 Rich 标签只作为普通文本显示：

```python
def test_picker_invalid_summary_has_safe_plain_label() -> None:
    item = SkillSummary(
        source_kind="workspace", trust_level="untrusted", availability="invalid",
        description="[red]\x1b[31m", reason_codes=("skill_manifest_invalid",),
    )
    rows = build_skill_picker_rows((item,), selected_skill_id=None)
    row = next(row for row in rows if row.kind == "skill")
    assert not row.selectable
    assert "无效 Skill" in row.label
    assert "skill_manifest_invalid" in row.label
    assert "\x1b" not in row.label
    assert Text(row.label).spans == []
```
- [ ] **Step 4: 实现行模型与安全标签。** `SkillPickerRow` 使用 `kind: Literal["heading", "skill"]`、`label: str`、`skill_id: str | None`、`selectable: bool`；固定来源顺序 `builtin/user/workspace`，组内规范名与完整 ID 排序，缺名无效行排末。用 `Counter` 统计完整 ID；只有 `availability in {"available", "conflict"}`、ID 非空且计数为 1 时可选。将标签作为 Rich `Text` 的纯文本交给 `OptionList`，不解析 Manifest 描述中的 Rich 标记；删除控制字符，由 Widget 的宽度约束安全截断，不添加目录路径或正文。

```python
@dataclass(frozen=True, slots=True)
class SkillPickerRow:
    kind: Literal["heading", "skill"]
    label: str
    skill_id: str | None = None
    selectable: bool = False


def safe_skill_label(item: SkillSummary, *, selected_skill_id: str | None) -> str:
    def clean(value: str) -> str:
        return "".join(ch for ch in value if ch.isprintable()).strip()

    source_label = {"builtin": "系统内置", "user": "用户本地", "workspace": "当前项目"}
    name = clean(item.name or "无效 Skill")
    description = clean(item.description or "")
    marker = " [待用]" if item.skill_id == selected_skill_id else ""
    identity = item.skill_id if item.availability == "conflict" else ""
    reasons = ",".join(item.reason_codes)
    detail = " · ".join(
        part for part in (
            source_label[item.source_kind], description, item.availability, identity, reasons
        ) if part
    )
    return f"{name}{marker} — {detail}"


def build_skill_picker_rows(
    summaries: tuple[SkillSummary, ...], *, selected_skill_id: str | None
) -> tuple[SkillPickerRow, ...]:
    counts = Counter(item.skill_id for item in summaries if item.skill_id)
    rows: list[SkillPickerRow] = []
    for source, heading in (("builtin", "系统内置"), ("user", "用户本地"),
                            ("workspace", "当前项目")):
        group = sorted(
            (item for item in summaries if item.source_kind == source),
            key=lambda item: (item.name is None, item.name or "", item.skill_id or ""),
        )
        if not group:
            continue
        rows.append(SkillPickerRow(kind="heading", label=heading))
        for item in group:
            selectable = bool(item.skill_id and counts[item.skill_id] == 1
                              and item.availability in {"available", "conflict"})
            label = safe_skill_label(item, selected_skill_id=selected_skill_id)
            rows.append(SkillPickerRow(kind="skill", label=label,
                                       skill_id=item.skill_id, selectable=selectable))
    return tuple(rows)
```

- [ ] **Step 5: 写 Widget 键盘失败测试并实现。** `SkillPicker` 用同一主 Screen 内的 `OptionList`（不 `push_screen`，避免 Timeline 查询切到新 Screen）；组标题和禁用行使用 disabled `Option`。`open(rows)` 显示并聚焦首个可选项；`OptionSelected` 只发送一次 `Chosen(skill_id)` 并进入 pending；`close()` 隐藏；`reject(code)` 保留列表并显示原因；`action_escape()` 在未 pending 时关闭，pending 时不声称取消。测试用 `app.run_test(size=(60, 16))`、`pilot.press("down", "enter")`、`pilot.press("escape")` 核对选中 ID、禁用行跳过、空列表和无重复消息。

```python
class SkillPicker(Vertical):
    class Chosen(Message):
        def __init__(self, skill_id: str) -> None:
            super().__init__()
            self.skill_id = skill_id

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        skill_id = str(event.option.id) if event.option.id else None
        if self.pending_skill_id is not None or skill_id is None:
            return
        self.pending_skill_id = skill_id
        self.post_message(self.Chosen(skill_id))
```

- [ ] **Step 6: 样式和验收。** `#skill-picker` 使用独立 overlay、最大可视高度不超过 60×16 可用区域，置于 Composer 上方；高对比/无色用现有语义 Token，选中行有文字指示。运行 `uv run pytest tests/terminal/test_skill_picker.py -q`、`uv run ruff check src/vera/terminal/widgets/skill_picker.py tests/terminal/test_skill_picker.py` 和 `uv run ruff format --check` 对应文件。审阅 `git diff --check`；仅经用户授权才提交该任务文件，提交信息 `feat: add grouped skill picker widget`。

### Task 3: 将 `/skills` 与选择确认接到 TUI

**Files:** Modify `src/vera/terminal/app.py`; Create `tests/terminal/test_skill_picker_integration.py`。
**Interfaces:** Consumes Task 2 的 `SkillPicker.open/close/reject` 与 `SkillPicker.Chosen`。Produces 现有 `ExecuteSlashCommand(raw=f"/skills use {skill_id}")`，只以 `skill.selection.changed` 的结构化 `selection` 确认完成。

- [ ] **Step 1: 写 TUI Pilot 失败测试。** 使用 `tests.terminal.test_app.make_controller`，在临时 `user` 根下用 `write_skill(user)` 建测试包，再把 `SkillSelectionService(SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user)))` 注入测试 Runtime；在 `app.run_test(size=(80, 24))` 内发送真实 `controller.dispatch(ExecuteSlashCommand(raw="/skills"))` 得到的 `skill.listed`，断言浮层打开。拦截 `app.bridge.submit`，按 Enter 两次，应只有一个 `/skills use user:python-review`，没有 `SubmitPrompt`；再投递 Core 的真实选择事件，断言浮层关闭、Composer 草稿和光标位置不变。

```python
listed = next(item for item in controller.dispatch(ExecuteSlashCommand(raw="/skills"))
              if isinstance(item, EventEnvelope) and item.type == "skill.listed")
app.on_runtime_output_received(RuntimeOutputReceived(listed))
assert app.query_one(SkillPicker).display is True
await pilot.press("enter", "enter")
assert captured == [ExecuteSlashCommand(raw="/skills use user:python-review")]
assert not any(isinstance(item, SubmitPrompt) for item in captured)
```

- [ ] **Step 2: 验证红灯。** `uv run pytest tests/terminal/test_skill_picker_integration.py -q`；预期当前 TUI 没有 `SkillPicker`，至少打开列表用例 FAIL。
- [ ] **Step 3: 最小接线。** `compose()` 增加 `SkillPicker(id="skill-picker")`；`on_runtime_output_received()` 保留现有 Timeline 投影，再对 `skill.listed` 解析 `SkillSummary.model_validate` 并在 idle 时调用 `picker.open(rows)`，同时隐藏命令补全。仅在 `SkillPicker.Chosen` 收到后通过 `bridge.submit` 发完整 ID。收到 `skill.selection.changed` 时校验 `SkillSelection.model_validate(payload["selection"])` 的 `status`、`skill_id` 与 pending：匹配则关闭浮层、恢复 Composer 焦点并显示实际 `version`；拒绝则 `picker.reject(reason_codes[0])`。遇到坏 payload 或 Worker 失败时安全关闭/报告，不能按文案判定。

```python
def on_skill_picker_chosen(self, message: SkillPicker.Chosen) -> None:
    self.bridge.submit(ExecuteSlashCommand(raw=f"/skills use {message.skill_id}"))

def action_escape(self) -> None:
    picker = self.query_one(SkillPicker)
    if picker.display and not picker.pending_skill_id:
        picker.close()
        self.query_one(PromptComposer).focus()
        return
    if picker.display and picker.pending_skill_id:
        return
    if self.controller.active_run_id is not None:
        self.action_cancel_or_clear()
        return
    try:
        completions = self.query_one(CompletionList)
    except NoMatches:
        return
    if completions.display:
        completions.hide()
```

- [ ] **Step 4: 补异常与现有行为测试。** 在同一测试文件覆盖 Esc 不改选择、禁用行 Enter 不发送、活动 Run/审批时只列出不打开、源包删掉后失败保留列表和原因、合法变更显示 Core 实际版本、worker 失败关闭、空列表/坏 `items` 不崩溃、60×16/80×24 resize、三主题和打开/关闭后焦点回归。核心断言如下；执行 `uv run pytest tests/terminal/test_skill_picker_integration.py tests/terminal/test_keybindings.py tests/terminal/test_composer.py -q`，预期全部 PASS，且 `/skills show/use/clear` 不触发浮层。

```python
controller.mark_active("run_1")
app.on_runtime_output_received(RuntimeOutputReceived(listed))
assert app.query_one(SkillPicker).display is False
controller._active_run_id = None

app.on_runtime_output_received(RuntimeOutputReceived(listed))
assert app.query_one(SkillPicker).display is True
await pilot.press("escape")
assert app.query_one(SkillPicker).display is False
assert controller.snapshot().skill_selection.mode == "none"

app.on_runtime_output_received(RuntimeOutputReceived(listed))
app.query_one(SkillPicker).pending_skill_id = "user:python-review"
app.on_worker_stopped(WorkerStopped(None, "worker_failed:dispatch_failed"))
assert app.query_one(SkillPicker).display is False
```

- [ ] **Step 5: 审阅并在授权后提交。** `uv run ruff check src/vera/terminal/app.py tests/terminal/test_skill_picker_integration.py`、`uv run ruff format --check` 对应文件、`uv run mypy src`、`git diff --check`。只在用户授权后按路径暂存并 `git commit -m "feat: select skills from tui list"`。

### Task 4: 客户端、安装包与阶段九验收记录

**Files:** Modify `tests/e2e/test_phase_9_client_parity.py`、`tests/pty/test_phase_9_skills.py`、`tests/terminal/test_skill_picker_integration.py`、`docs/tasks/0074-phase-9-skill-picker-plan.md`、`docs/STATUS.md`。
**Interfaces:** 消费前三项交付的 Core 选择与 TUI 浮层；不引入新的 SessionAction、Event schema 或 Provider 连接。

- [ ] **Step 1: 写客户端 parity/PTY 断言。** 在现有 E2E 测试中，用同一 `skill.listed` 事件检查公共 `items` 只含安全摘要；在现有 Plain PTY 用例中保持 `/skills`、`/skills use`、`/status` 的文本与无 ANSI 行为。TUI Pilot 另断言列表选择后 `controller.snapshot().skill_selection.skill_id == "user:python-review"`，下一次真实 `SubmitPrompt` 才有 `skill.snapshot.bound`，选择本身没有 `run.started`。

```python
assert listed.payload["items"][0]["skill_id"] == "user:python-review"
assert "# Skill" not in str(listed.payload)
assert "\x1b" not in str(listed.payload)
assert not any(item.type == "run.started" for item in selection_outputs)
assert any(item.type == "skill.snapshot.bound" for item in prompt_outputs)
```

- [ ] **Step 2: 验证红绿与阶段九门禁。** 新增集成断言先对现状 FAIL，前三项实现后 PASS。执行 `uv run pytest tests/skills/test_registry.py tests/session/test_skill_commands.py tests/terminal/test_skill_picker.py tests/terminal/test_skill_picker_integration.py tests/e2e/test_phase_9_client_parity.py tests/pty/test_phase_9_skills.py -q`；再运行清除真实 Provider 环境的完整非 live suite：

```bash
env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY \
  VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file \
  PYTHONDONTWRITEBYTECODE=1 uv run pytest -m 'not live' -q
```

若两个既有 offline wheel 安装测试仍因缓存缺 `openai>=2,<3` 阻断，保留错误原文，再以相同环境变量运行下列排除已知阻断的 suite；不把安装态写成通过：

```bash
env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY \
  VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file \
  PYTHONDONTWRITEBYTECODE=1 uv run pytest -m 'not live' \
  --ignore=tests/e2e/test_phase_4_wheel_smoke.py \
  --ignore=tests/e2e/test_phase_5_install_upgrade.py -q
```

- [ ] **Step 3: 静态与手动准备。** `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src`、`git diff --check`。用独立状态目录和 FakeModel 做 60×16/80×24 PTY/TUI 预检；真实 Terminal.app、真实 Provider、Python 与 Swift/Xcode 安全工程副本 dogfood 仍需用户验收，不由 Pilot 或占位 Key 代替。
- [ ] **Step 4: 同步证据文档。** 在本计划与 `docs/STATUS.md` 中写入准确的通过数、环境阻断和未跑的人工项；阶段九仍为 `Ready for manual acceptance`，直到真实验收和用户确认。审阅全 diff，不碰无关工作树和已有 Logo/Skill 修正文件。
- [ ] **Step 5: 仅经用户授权提交/推送。** 按本任务实际修改的路径逐一暂存，计划内提交信息 `test: verify skill picker client parity`；推送或合并另需明确授权，不因自动测试通过而自行执行。

## 覆盖核对与执行交接

| 已接受规格要求 | 对应任务 |
| --- | --- |
| 三来源分组、状态、待用标记与安全摘要 | Task 2 |
| 跨来源同名可选、同来源重复 ID 拒绝 | Task 1、Task 2 |
| ↑↓、Enter 只选择、Esc、长列表与窄屏 | Task 2、Task 3 |
| Core 权威确认、错误与来源变化、草稿/焦点 | Task 3 |
| 活动 Run/审批不打开浮层、Plain/JSON 保持语义 | Task 3、Task 4 |
| NoSkill/Session 恢复/安装态和真实终端门禁 | Task 4 |

## 2026-09-24 Native 执行记录

用户确认由一个主 Agent 串行 Native 实施，并选择“主工作树不动、隔离工作树带入现有修复副本、暂不提交/推送”。执行位置为 `/Users/admin/.codex/worktrees/skill-picker-native/Vera`；带入的 11 个文件与主工作树逐项 SHA-256 一致，`import vera` 指向隔离工作树源码。Task 1–4 的代码、测试和文档已在此工作树修改；计划内提交步骤因本次没有 Git 授权而保留未执行，未合并、未推送、未删除工作树。

Core 现拒绝同来源重复完整 `skill_id`，包括“先选中、后出现重复包”的绑定路径。TUI 新增按系统内置、用户本地、当前项目分组的独立浮层，禁用无效/不兼容/重复 ID 行，显式标出当前待用与键盘高亮；Enter 仅向 Core 发送一次既有 `/skills use <skill_id>`，收到匹配的结构化确认才返回原草稿/光标，不触发 Run。内部 worker 完成消息补动作关联，避免迟到的列表 worker 错误关闭选择浮层；`/skills list` 仍只显示列表事实，不打开精确 `/skills` 的浮层。

自动证据：

- 新增矩阵：`33 passed`，覆盖 Core 消歧、Session、浮层 Widget/TUI、公开事件 parity 与 Plain PTY。
- 完整非 live：`1199 passed, 2 deselected, 8 warnings`，另有 1 failed、1 error，均为两个既有隔离 wheel 安装测试在 `--offline` 下缺少 `openai>=2,<3` 缓存；不能视作安装态通过。
- 排除 `tests/e2e/test_phase_4_wheel_smoke.py` 与 `tests/e2e/test_phase_5_install_upgrade.py` 后：`1195 passed, 2 deselected, 8 warnings`。
- `ruff check src tests`、`ruff format --check src tests`、`mypy src`（183 个源文件）和 `git diff --check` 通过。全仓 `ruff check .` 被未改动的旧 `docs/evals/artifacts/_gen_phase7_visuals.py` 的 25 项错误阻断；全仓 `ruff format --check .` 也包含多份历史文档代码块及本计划示例，不作为产品代码格式通过的证据。
- 全量回归曾有一次既有 `tests/pty/test_session_resume.py::test_pty_json_resume_picker_has_no_ansi` 子进程输出完整但记录退出码 1；单项重跑及其后全量重跑均通过。保留为间歇性 PTY harness 风险，未改无关 harness。

未执行：真实 Terminal.app 60×16/80×24 视觉/键盘验收、真实 Provider、用户的 `interview-term-brief` 真实提问、Python 与 Swift/Xcode 安全工程副本 dogfood；Pilot、FakeModel 和占位 Key 不替代这些人工项。阶段九维持 `Ready for manual acceptance`，阶段八维持 `In progress`，阶段十不启动。
