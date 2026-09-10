# Vera 状态

**更新日期：** 2026-09-10
**当前阶段：** 阶段 1——Core 契约与安全编辑垂直切片
**仓库状态：** 治理基线和实施计划已提交到 `main`；当前开发在 `codex/core-safe-editing`；暂无远程仓库。

## 已验证基线

- 工作目录：`/Users/admin/Vera`
- 当前开发分支：`codex/core-safe-editing`
- 初始检查点：仓库治理与 SDD 基线
- Agent 实现：仅有任务 1 的 Python 包骨架
- 依赖清单：`pyproject.toml`、`.python-version`、`uv.lock`

## 已完成任务

- [任务 0001：建立 Vera 仓库](tasks/0001-bootstrap-repository.md)

阶段 1 的 Core 契约和安全编辑垂直切片范围已经接受；实现正在通过活动任务记录推进。

## 活动任务

- [任务 0002：Core 安全编辑垂直切片](tasks/0002-core-safe-editing-vertical-slice.md)
- 当前检查点：任务 2 契约与状态机已通过 10 项测试，准备提交

## 最近验证

- 必需文件和文档链接目标：通过
- 占位符与行尾空白扫描：通过
- `git diff --check`：通过
- Agent 源码与依赖清单扫描：任务 1 骨架已建立
- Git 状态：治理与实施计划检查点 `a1aaffb` 位于 `main`；功能开发在 `codex/core-safe-editing`
- `uv 0.12.10`：通过官方独立安装器安装，项目环境同步完成
- 任务 1 包测试：1 项通过；Ruff 和 Mypy 通过

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

完成任务 1 治理与包基础，再在任务 2 实现版本化 Core 契约和状态机。
