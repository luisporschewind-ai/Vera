# Vera 状态

**更新日期：** 2026-09-10
**当前阶段：** 阶段 1——Core 契约与安全编辑垂直切片
**仓库状态：** 离线 Core 垂直切片已合并到 `main`；暂无远程仓库。

## 已验证基线

- 工作目录：`/Users/admin/Vera`
- 当前开发分支：`main`
- 初始检查点：仓库治理与 SDD 基线
- Agent 实现：任务 1–11 的 Python Core、Runtime 和内部 CLI；任务 12 离线验收已完成
- 依赖清单：`pyproject.toml`、`.python-version`、`uv.lock`

## 已完成任务

- [任务 0001：建立 Vera 仓库](tasks/0001-bootstrap-repository.md)
- 任务 0002 的离线实现与验收步骤已完成；真实供应商和人工验收仍开放

阶段 1 的 Core 契约和安全编辑垂直切片范围已经接受；实现正在通过活动任务记录推进。

## 活动任务

- [任务 0002：Core 安全编辑垂直切片](tasks/0002-core-safe-editing-vertical-slice.md)
- 当前检查点：任务 12 离线 E2E 与构建已通过；真实供应商和人工验收未执行

## 最近验证

- 必需文件和文档链接目标：通过
- 占位符与行尾空白扫描：通过
- `git diff --check`：通过
- Agent 源码与依赖清单扫描：Python Core 与 CLI 已建立
- Git 状态：合并提交 `b8604eb` 位于 `main`；工作树干净
- `uv 0.12.10`：通过官方独立安装器安装，项目环境同步完成
- 任务 1 包测试：1 项通过；Ruff 和 Mypy 通过
- 任务 2 契约与状态机：10 项测试通过；Ruff 和 Mypy 通过
- 任务 3 配置、脱敏和 Event Journal：8 项测试通过；Ruff 和 Mypy 通过
- 任务 4 Workspace 边界与只读工具：8 项测试通过；Ruff 和 Mypy 通过
- 任务 5 ChangeSet 生成与审批完整性：5 项测试通过；Ruff 和 Mypy 通过
- 任务 6 Checkpoint、原子应用与冲突安全回滚：4 项测试通过；Ruff 和 Mypy 通过
- 任务 7 命令策略与验证证据：7 项测试通过；Ruff 和 Mypy 通过
- 任务 8 可替换 ModelAdapter：2 项非 live 测试通过；Ruff 和 Mypy 通过；live 测试未联网
- 任务 9 VeraRuntime 发现循环：2 项测试通过；Ruff 和 Mypy 通过
- 任务 10 审批、应用、验证与回滚编排：11 项 Runtime 测试通过；Ruff 和 Mypy 通过
- 任务 11 CLI 人类/JSON 模式：4 项 CLI 测试通过；`vera --help`、Ruff 和 Mypy 通过
- 任务 12 离线验收：55 项非 live 测试通过，覆盖率 84%；Ruff/格式/Mypy/build 通过

## 已接受方向

- 正式开发只在本仓库进行。
- `/Users/admin/Coding-harness` 保持只读，仅作为原型参考。
- 产品交付遵循 Core-first、内部 CLI-first、桌面 later。
- 公开发布前先完成私有稳定性和评测证据。
- Runtime、Command/Event 契约以及私有状态与 Checkpoint 设计已通过 ADR 接受。

## 仍待决策

- 更广泛的供应商行为和真实供应商评测阈值
- 评测语料与阈值
- 桌面框架
- 许可证与发布策略

## 下一检查点

离线 Core 垂直切片已具备证据；下一检查点是用户明确选择并授权一次真实供应商验证，以及指定可恢复项目副本完成人工验收。任务保持 In progress。
