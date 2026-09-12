# Feature Implementation Plan

## 任务 0030：不可信内容与提示词投毒防御

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. 同一工作树只允许一个主实现 Agent；不要并行委派代码修改。

**状态：** Done
**执行就绪：** 是；规格已接受，任务 0023 已合并
**分支：** `phase-5/0030-untrusted-content-prompt-injection`
**目标：** 为 Vera Core 增加内容来源、信任等级、投毒风险和“风险只能收紧权限”的确定性防线，并用离线对抗用例证明检测漏报时仍不能产生未授权副作用。
**架构：** 原始内容仍只在本地 Runtime/Model 上下文中使用；公共 `ContentEnvelope` 只携带来源、hash、信任和风险事实。启发式检测器只提供风险信号，`PolicyEngine`、`Workspace` 和 `ApprovalGate` 继续是动作权限权威。
**技术栈：** Python 3.12、Pydantic 2、pytest、现有 Vera Runtime/Policy/Recovery 契约；不增加第三方依赖。
**规格：** [不可信内容、提示词投毒与内容安全](../specs/2026-09-12-untrusted-content-and-prompt-injection-defense.md)
**决策：** [ADR-0015](../decisions/ADR-0015-untrusted-content-trust-boundary.md)

## 全局约束

- 只实现阶段五安全增量 S1；不实现公开内容审核、敏感词封禁、网页、MCP、网络出站、桌面端或远程更新。
- 不把正则、关键词或模型分类器当作授权事实。检测器即使漏报，现有 Workspace、PolicyEngine、ApprovalGate 仍必须阻止未授权动作。
- 检测结果只能保持或收紧基础策略：`deny` 不得放宽，`approval_required` 不得变成 `allow`，带风险的 `allow` 至少变成 `approval_required`。
- 合法分析攻击语句、恶意代码或敏感词的只读任务不得仅因命中模式而失败。
- 不读取真实 Provider Key，不运行 `live` 测试，不修改测试工作区以外的用户工程。
- 不改 14 个冻结离线 eval case；新增攻击夹具独立存放。
- 当前实现发生在任务 0024 契约冻结前；任何公共契约变化必须有 schema、兼容测试和文档。
- 每个步骤先写失败测试，再做最小实现；每完成一个步骤运行该步骤测试，最后运行全量门禁。

## Task 1：建立来源、信任与风险契约

**新增：**

- `src/vera/content/__init__.py`
- `src/vera/content/envelope.py`
- `src/vera/content/trust.py`
- `tests/content/test_envelope.py`
- `tests/content/test_trust.py`

### 1.1 先写失败测试

覆盖以下事实：

- `ContentEnvelope` 使用 `schema_version=1`，序列化只包含 `source_kind`、`origin`、`trust_level`、`content_hash`、`byte_count`、`truncated`、`risk_labels`，绝不包含正文。
- `content_hash` 对 UTF-8 原文计算 SHA-256；同一输入得到相同 hash，不同输入得到不同 hash。
- `user_goal` 默认为 `user_intent`；`project_guidance` 默认为 `advisory`；`workspace_file`、`tool_output`、`conversation_summary`、`model_output` 与未知来源默认为 `untrusted`。
- 调用方传入未知 `source_kind`、缺失来源或非法 `trust_level` 时，不得被提升为 `user_intent`。
- 包装后的模型文本使用稳定 JSON 数据块承载元数据与正文；正文里的 Markdown、XML 结束标签或伪造 `[system]` 不能逃逸为新的 ModelMessage 角色。

建议公共接口固定为：

```python
class ContentTrustLevel(StrEnum):
    BUILTIN_POLICY = "builtin_policy"
    USER_INTENT = "user_intent"
    ADVISORY = "advisory"
    UNTRUSTED = "untrusted"


class ContentEnvelope(ContractModel):
    schema_version: Literal[1] = 1
    source_kind: str
    origin: str
    trust_level: ContentTrustLevel
    content_hash: str
    byte_count: int
    truncated: bool = False
    risk_labels: tuple[str, ...] = ()


class ContentFinding(ContractModel):
    schema_version: Literal[1] = 1
    envelope: ContentEnvelope
    disposition: str
    reason_code: str
    detector_version: str


def build_content_envelope(
    text: str,
    *,
    source_kind: str | None,
    origin: str,
    truncated: bool = False,
    risk_labels: tuple[str, ...] = (),
) -> ContentEnvelope: ...


def render_content_for_model(envelope: ContentEnvelope, text: str) -> str: ...
```

`source_kind` 保持可前向扩展的字符串；未知值由 `build_content_envelope` 映射为 `trust_level=untrusted`。不要在公共 envelope 中保存正文或正文预览。

### 1.2 最小实现并验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/content/test_envelope.py tests/content/test_trust.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src/vera/content
```

## Task 2：实现本地、可替换、只提供建议的投毒检测器

**新增：**

- `src/vera/content/detector.py`
- `tests/content/test_detector.py`

### 2.1 先写失败测试

定义供应商无关接口和确定性基线实现：

```python
class DetectionDisposition(StrEnum):
    CLEAR = "clear"
    WARN = "warn"
    QUARANTINE = "quarantine"
    BLOCK = "block"
    UNAVAILABLE = "unavailable"


class ContentDetection(ContractModel):
    schema_version: Literal[1] = 1
    disposition: DetectionDisposition
    risk_labels: tuple[str, ...] = ()
    reason_code: str
    detector_version: str


class ContentDetector(Protocol):
    def assess(self, envelope: ContentEnvelope, text: str) -> ContentDetection: ...
```

测试至少覆盖：

- “忽略系统规则”“把秘密发到外部”“按 README 自动执行命令”等直接与间接注入模式产生稳定 `risk_labels`。
- NFKC 归一化、零宽字符和长度受限的 Base64 片段能够被检查；输入上限明确，不能造成无界解码或内存增长。
- 普通 README、正常代码和“请分析这句恶意提示词”的任务不会被直接拒绝；基线检测器最多产生建议事实。
- 检测器抛异常、超时代理结果或返回非法结构时，适配层转换为 `UNAVAILABLE` 与稳定原因码，不吞异常后返回 `CLEAR`。
- Event 安全摘要只使用 envelope、类别、原因码和版本，不携带匹配原文。

基线实现可使用有限启发式规则，但命名为 `BaselinePromptInjectionDetector`，不得命名或描述为“完整防毒”。不要引入外部审核 API。

### 2.2 最小实现并验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/content/test_detector.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/content tests/content
```

## Task 3：把不可信内容接入 Runtime 上下文，但不提升指令权限

**修改：**

- `src/vera/runtime/prompts.py`
- `src/vera/runtime/context.py`
- `src/vera/runtime/engine.py`
- `tests/runtime/test_untrusted_context.py`
- `tests/runtime/test_context_compaction.py`
- `tests/contracts/test_models.py`

### 3.1 先写失败测试

覆盖完整入口：

- System Prompt 明确声明工程文件、项目说明、工具输出、会话摘要和模型输出都是待分析数据，不能授权工具、覆盖策略或批准动作。
- `StartRun.goal` 保持 `ModelMessage(role="user")`，但带 `user_goal/user_intent` 数据包装；会话摘要保持 assistant 数据，不提升为 system/user。
- `read_file`、`list_directory`、`search_text` 等工具结果保持 `ModelMessage(role="tool")`，正文通过 `render_content_for_model` 包装；路径进入规范化 `origin`，正文不能伪造角色。
- ModelAdapter 返回的 assistant 文本和 Tool Call 始终视为 `model_output/untrusted`；Tool Call 在执行前仍必须经过 schema、Workspace 与 PolicyEngine，不因模型解释获得授权。
- README、`AGENTS.md` 与普通文件的来源事实可区分，但前两者最多是 `advisory`，不能改变安全边界。
- 上下文压缩生成的摘要按 `conversation_summary/untrusted` 重新包装；压缩不能把不可信正文拼进 System Prompt。
- 每个被标记入口产生一次 `security.content_flagged`；payload 只有 envelope、disposition、reason_code、detector_version，不含原文。
- `run.started` 不再复制用户目标原文，改为 `goal_hash` 与 `goal_bytes`；更新相应契约测试，同时继续兼容读取旧 Journal 中带 `goal` 的历史 Event。
- 同一内容 hash/source 的风险事实去重；单个 Run 最多保留 64 个风险来源，超过时生成脱敏 `security.findings_truncated`，避免长会话无界增长。

在 `RunContext` 中增加有界、可恢复的风险事实，而不是保存第二份正文：

```python
security_findings: tuple[ContentFinding, ...] = ()
security_context_hash: str | None = None
```

Runtime 构造函数以 keyword-only 方式接收可替换 `content_detector`；默认使用本地基线检测器，测试可注入 clear、flagged、unavailable 或 raising fake。

### 3.2 最小实现并验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime/test_untrusted_context.py tests/runtime/test_context_compaction.py tests/contracts/test_models.py -q
```

## Task 4：风险只能收紧 PolicyEngine，并绑定审批事实

**新增：**

- `src/vera/policy/tighten.py`
- `tests/policy/test_tighten.py`

**修改：**

- `src/vera/policy/engine.py`
- `src/vera/policy/rules.py`
- `src/vera/tools/command_policy.py`
- `src/vera/contracts/approvals.py`
- `src/vera/runtime/approval.py`
- `src/vera/runtime/engine.py`
- `tests/policy/test_matrix.py`
- `tests/runtime/test_approval.py`
- `tests/runtime/test_policy_approval.py`

### 4.1 先写决策矩阵

`tighten_policy_decision(base, risk_labels, detector_disposition)` 必须满足：

| 基础策略 | 无风险 | `warn` / 未知标签 | `quarantine` / `block` / `unavailable` |
|---|---|---|---|
| `deny` | `deny` | `deny` | `deny` |
| `approval_required` | 原结果 | `approval_required` | `deny` |
| `allow` | `allow` | `approval_required` | `deny` |

补充断言：

- 硬禁止命令、越界路径和秘密路径永远不能被检测结果放宽。
- 带风险时，内置安全命令和 `user_allowed_command_prefixes` 的基础 `allow` 至少变成 `approval_required`。
- `PolicyDecision.policy_hash` 仍代表有效策略快照；安全上下文使用单独的 `security_context_hash`，不能混入并伪装成策略版本。
- 未知 disposition/label 采用更严格路径，不默认 clear。
- `PolicyEngine.decide()` 先执行现有固定优先级规则，再根据 `PolicyAction.metadata` 中的脱敏风险事实调用纯函数收紧；调用方不能绕过这一合并步骤自行把结果改回 `allow`。

### 4.2 绑定审批

对 `ApprovalRequest` 做 schema v1 的 additive 字段扩展：

```python
security_context_hash: str | None = None
risk_labels: tuple[str, ...] = ()
risk_sources: tuple[ContentEnvelope, ...] = ()
```

要求：

- Change Set 和验证命令审批都写入脱敏风险来源、风险标签和 `security_context_hash`。
- 有风险的 Change Set 审批 `risk` 至少为 `high`，不能采用模型自报的 `low`。
- 恢复后或审批解决前，Runtime 重新计算当前 `security_context_hash`；不一致时以 `security_context_changed` 拒绝旧审批，不能继续写入或执行命令。
- 老版本 ApprovalRequest 缺少新增字段时仍可解码为安全默认值；测试固定该兼容行为。

### 4.3 最小实现并验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/policy/test_tighten.py tests/policy/test_matrix.py tests/runtime/test_approval.py tests/runtime/test_policy_approval.py -q
```

## Task 5：持久化并安全恢复风险事实

**修改：**

- `src/vera/recovery/models.py`
- `src/vera/recovery/hydrator.py`
- `src/vera/runtime/engine.py`
- `tests/persistence/test_snapshot_codec.py`
- `tests/runtime/test_recovery_snapshots.py`
- `tests/recovery/test_hydrator.py`
- `tests/runtime/test_recovery_resume.py`

### 5.1 先写失败测试

- `RecoverySnapshot` 以 additive、带默认值的字段持久化 `security_findings` 和 `security_context_hash`，不重复保存原文。
- Snapshot encode/decode 往返保持风险事实；旧 snapshot 缺字段时仍可读取为空安全上下文。
- 有风险的新 Run 在重启后恢复审批时，风险标签、来源和 context hash 不丢失。
- 篡改、删除或替换新 snapshot 中的风险事实后，已有审批不能被继续使用；返回稳定失败原因，不触碰工作区。
- `UNAVAILABLE` 和未知风险事实在恢复后仍走收紧路径，不静默变成 clear。

若 additive 字段不需要升级 `snapshot_version`，在测试中固定理由：旧版本运行当时没有安全检测事实；新版本一旦创建了事实就必须完整保留。不得为通过升级测试删除旧状态。

### 5.2 最小实现并验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/persistence/test_snapshot_codec.py tests/runtime/test_recovery_snapshots.py tests/recovery/test_hydrator.py tests/runtime/test_recovery_resume.py -q
```

## Task 6：建立确定性对抗夹具和端到端安全门禁

**新增：**

- `tests/fixtures/injection/direct-user.json`
- `tests/fixtures/injection/readme-indirect.json`
- `tests/fixtures/injection/agents-guidance.json`
- `tests/fixtures/injection/tool-output.json`
- `tests/fixtures/injection/obfuscated.json`
- `tests/fixtures/injection/conversation-summary.json`
- `tests/fixtures/injection/mixed-legitimate-task.json`
- `tests/fixtures/injection/legitimate-security-analysis.json`
- `tests/e2e/test_prompt_injection_adversarial.py`
- `docs/evals/untrusted-content-and-prompt-injection.md`

### 6.1 先写端到端失败测试

使用 Fake Model 和临时工作区，至少证明：

1. README、`AGENTS.md`、源码注释和工具输出中的恶意命令不会变成系统/用户授权。
2. 即使注入检测器被替换为永远 `CLEAR` 的漏报 fake，模型诱导出的写入仍必须停在精确 Change Set 审批，越界路径和秘密读取仍被拒绝。
3. 检测命中后，原本自动允许的 `git status --short` / `git diff --check` 变成审批或更严格结果，不直接启动主机进程。
4. `rm`、shell、提权、危险 Git 命令保持硬拒绝，不因用户目标或工程说明而改变。
5. 检测器 raising/unavailable 时，只读分析可以完成；写入和命令不得静默放行。
6. Base64、Unicode 零宽字符、Markdown/HTML 隐藏文本和跨轮摘要具有稳定、脱敏的风险事件。
7. 混合了真实编码要求与恶意指令时，可以继续收集事实并给出 Change Set，但没有审批绝不写盘。
8. 合法分析投毒样本不会仅因关键词而出现 `run.failed`；风险警告与动作策略结果分开表达。
9. `security.content_flagged`、approval、Journal 和评测报告均不含被标记原文、完整请求、Key/Token 或用户源码正文。
10. 相同 Fake Model 攻击场景经 Core `handle`、JSON Session 和 Eval 入口得到相同权威风险/策略事实；展示文本允许不同。

攻击夹具仅保存合成内容，不放真实凭据、真实用户源码或可造成主机副作用的脚本。

### 6.2 运行聚焦门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -p no:cacheprovider tests/content tests/policy/test_tighten.py tests/runtime/test_untrusted_context.py tests/e2e/test_prompt_injection_adversarial.py -q
```

## Task 7：同步证据并运行完整门禁

**修改：**

- `docs/evals/untrusted-content-and-prompt-injection.md`
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- 本任务文件

### 7.1 文档收口

- 逐条记录已验证、未验证和明确延期内容。
- 只有全部自动门禁通过后才把本任务改为 `Done`。
- 本任务完成后，`docs/STATUS.md` 的下一项改为任务 0024；不要把阶段五直接标为 Complete。
- 内容审核、远程更新和桌面端保持后续阶段，不借本任务提前实现。

### 7.2 完整验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -p no:cacheprovider -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase5-security-dist
git diff --check
git status --short --branch
```

检查最终 diff 只包含任务 0030 所需的代码、测试和文档。未获得当前用户明确授权时不要 commit、push 或修改 remote；若用户授权提交，建议提交信息：

```bash
git commit -m "feat: contain untrusted content and prompt injection"
```

## 完成定义

- 来源、信任、风险和检测失败事实有版本化、UI 无关契约。
- 所有不可信正文保持数据身份，不进入 System 权限层，不可生成用户审批或策略配置。
- 风险信号只保持或收紧 PolicyEngine 决策；漏报仍不能绕过 Workspace、PolicyEngine、ApprovalGate。
- 审批绑定准确动作、参数、工作区、事实、策略 hash 与安全上下文 hash；恢复后不会丢失或降级。
- 对抗矩阵覆盖直接/间接/混淆/跨轮/失败模式与反误拒绝用例。
- 公共安全事件、Journal 和评测证据不含被标记输入原文或秘密。
- 全量非 live 测试、lint、format、mypy、build 与 `git diff --check` 全部通过。
