# 验收：Worker、Runner 与基础评分

**规格：** [2026-09-12-evals-and-internal-readiness](../specs/2026-09-12-evals-and-internal-readiness.md)
**任务：** [0016](../tasks/0016-eval-runner-and-scoring.md)
**日期：** 2026-09-12
**结果：** Pass（非 live；未跑 `tests/live`；未读真实 DeepSeek/GLM Key；未修改 VeraTestDemo）

## 质量门禁

- `tests/evals` 67 passed
- Worker 只构造 `FakeModelAdapter`，测试拦截 `build_runtime` / `load_provider_environment`
- 评分只使用 FileFact 与 Event 类型，不解析 CLI/TUI 文本
- 子进程超时路径：TERM 等待 2 秒再 kill 精确进程；Worker 子进程是生命周期隔离，不是 OS 沙箱
- 证据包不覆盖已有目录，不含文件正文
- 未运行 live，未读取供应商 Key

## 证据

| 项 | 测试 |
| --- | --- |
| 文件哈希与安全 allowlist | `tests/evals/test_scoring.py`、`test_files.py` |
| Fake adapter 离线装配 | `tests/evals/test_runtime_factory.py` |
| 脚本审批与 `$VERA_EVAL_PYTHON` | `tests/evals/test_script_driver.py` |
| Worker 结果与异常映射 | `tests/evals/test_worker.py` |
| 环境清除与超时 | `tests/evals/test_process_runner.py` |
| 证据包与套件继续 | `tests/evals/test_evidence.py`、`test_runner.py` |
