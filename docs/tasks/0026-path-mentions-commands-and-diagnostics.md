# 任务 0026：路径引用、命令目录与诊断

> 供 Cursor 执行：按 `superpowers:executing-plans` 实施；命令与补全必须来自共享 Catalog。

**状态：** Planned
**执行就绪：** 任务 0025 合并后
**分支：** `phase-6/0026-path-commands-diagnostics`
**依赖：** 任务 0025 已合并
**规格：** [阶段六 CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 目标与边界

完成安全 `@path` 补全、统一 Slash Command Registry 和 `/diff`、`/review`、`/doctor`、`/config`、`/usage`、`/shortcuts`、`/theme` 七个结构化命令。命令不得绕过 Core 或增加隐式写配置。

## 设计约束

- Catalog 同时提供名称、别名、分组、usage、参数 schema、可用条件和 handler key。
- TUI/Plain/JSON 的帮助、补全和执行都消费 Catalog，不保留 controller 中的平行 `if` 清单。
- `@path` 仅构造候选上下文引用，不等于读取、写入或执行批准。
- `/review` 只投影已有 Diff/Event/验证事实，不调用 Provider。
- `/doctor` 和 `/config` 永不显示秘密；缺失用量显示 `unavailable`，不能填零。

## 实施步骤

### 1. 安全路径候选

**修改：**

- 新增 `src/vera/session/path_mentions.py`
- `src/vera/terminal/widgets/completions.py`
- `src/vera/terminal/widgets/composer.py`
- 新增 `tests/session/test_path_mentions.py`
- `tests/terminal/test_completions.py`

**测试先行：** 覆盖空格、CJK、大小写、忽略规则、私有 state、隐藏目录、链接逃逸、目录/文件区分、超大目录上限。候选包含展示值与可核对的 workspace 相对规范路径；特殊文件和 workspace 外目标不出现。

### 2. 单一命令 Registry

**修改：**

- `src/vera/session/command_catalog.py`
- `src/vera/session/controller.py`
- `src/vera/session/actions.py`
- `src/vera/terminal/widgets/completions.py`
- `tests/session/test_command_catalog.py`
- `tests/session/test_controller.py`
- `tests/cli/test_driver.py`

先写测试断言现有和新增命令在 Catalog、帮助、补全、参数验证和三种 Session 模式中完全一致。未知命令给候选但不自动执行。再用 handler map 取代 `_slash` 分支和硬编码 `_help_text`。

### 3. Diff、Review 与 Usage

**修改：**

- 新增 `src/vera/session/queries.py`
- 新增 `src/vera/presentation/review.py`
- `src/vera/session/actions.py`
- `src/vera/session/controller.py`
- 新增 `tests/session/test_queries.py`
- 新增 `tests/presentation/test_review.py`

测试当前待审批/指定 run/未知 run/无 Diff；review 输出文件、风险、审批、验证和副作用事实且完全确定；usage 对缺字段显示 unavailable。命令只读，不启动模型、不写 workspace。

### 4. Doctor、Config、Shortcuts 与 Theme

**修改：**

- 新增 `src/vera/session/diagnostics.py`
- 新增 `src/vera/terminal/theme.py`
- `src/vera/config.py`
- `src/vera/session/controller.py`
- `src/vera/terminal/app.py`
- 新增 `tests/session/test_diagnostics.py`
- 新增 `tests/terminal/test_theme.py`

`DoctorReport` 每项为 `pass|warning|fail|unavailable`，检查版本、Python、终端能力、配置存在性、state 权限和 Git；提供同构脱敏 JSON。`/config` 只显示来源和脱敏值。主题仅当前会话生效，支持 default/high-contrast/no-color，不写配置、不加载代码。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_path_mentions.py tests/session/test_command_catalog.py tests/session/test_queries.py tests/session/test_diagnostics.py tests/presentation/test_review.py tests/terminal/test_completions.py tests/terminal/test_theme.py tests/cli/test_driver.py -q
```

再运行[阶段六共同门禁](phase-6-execution-order.md)。人工检查 `/help` 分组和七个新增命令的 Plain/JSON 表达，更新任务证据后提交：

```bash
git commit -m "feat: add path mentions commands and diagnostics"
```

## 验收标准

- `@path` 不越界、不跟随不可信链接、不暗示批准。
- 所有命令只有一个 Registry，参数与可用条件跨模式一致。
- 七个新增命令均有结构化结果；`/review` 不调用模型。
- 诊断、配置和用量不泄漏秘密，不把 unavailable 填成零。
