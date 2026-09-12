# 文件系统与审批事实加固验收记录

更新日期：2026-09-12

## 结论

任务 0020 离线实现通过。`WorkspacePaths` 以不可变 `PathFact` 作为读写前事实；Change Set / Apply / Checkpoint 在写入前复核 inode、类型与内容；审批绑定 `fact_hash`，事实变化或缺少绑定输出 `approval.expired` 且零副作用；私有证据与 suite report 使用原子写入，不修改既有父目录权限。

未运行 live，未读取真实 DeepSeek/GLM Key，未修改用户工程。

## 规格验收对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | `..`、绝对路径、Unicode、内部链接与逃逸链接 | 通过 |
| 2 | FIFO、Socket、目录冒充文件失败关闭；设备只做类型判定 | 通过 |
| 3 | 检查后替换 inode / 换成链接，旧 `PathFact` 验证失败 | 通过 |
| 4 | 多文件 Change Set 任一事实变化，预检在第一笔写入前失败 | 通过 |
| 5 | 审批绑定事实；过期/未知/跨 run 失败关闭；旧 schema 不能授权新写入 | 通过 |
| 6 | 拒绝、取消、过期不创建 Checkpoint、不写文件 | 通过 |
| 7 | 证据与 suite report 原子、`0600`/`0700`，既有父目录 mode 不变 | 通过 |

## 自动验证证据

- 额外聚焦：78 passed
- `pytest -m "not live"`：559 passed，2 deselected
- Ruff / format / Mypy / `uv build` / `git diff --check`：通过

## 已知限制

- Presenter 只展示 `approval.expired`，不决定是否允许
- 阶段五命令环境、损坏状态、真实工程与 dogfood 仍待 0021–0024
