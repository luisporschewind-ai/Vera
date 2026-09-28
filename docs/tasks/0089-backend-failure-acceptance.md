# 0089 后端故障人工验收

状态：runtime 缺失与版本错误两项人工验收通过（2026-09-27）。依据 Accepted 工作区权限规格的失败关闭要求。在独立临时目录执行，不更改正常沙盒配置、runtime 或共享 Python。

证据：缺失场景 run_6c73c12cacf347139c46966dcaef88ef（独立 Core 日志确认审批和 process_error，当轮保存回复报告 sandbox_unavailable）；版本错误 run_10725e192e9f47798040090c24a2ca43（用户原始输出报告 sandbox_version_mismatch、exit_code=null）。用户分别执行宿主检查，两目标均不存在。仅关闭这两个用例，其他初始化异常不外推。下文为保留的复现步骤。

## 环境

- 正常配置：`/private/tmp/vera-0089-acceptance.psEsZR/config/sandbox.json`。
- 故障夹具：`/private/tmp/vera-0089-acceptance.psEsZR/backend-failure-check`。
- missing.json 指向不存在的 missing-runtime；version.json 指向仅含错误版本 0.0.0 的假 package.json。两者沿用正常配置的 node 与基础权限。
- start.sh 接受 missing 或 version，使用完整 Python.app 解释器、原虚拟环境及原隔离工作树；每种故障拥有独立状态目录，复用原用户模型配置。没有复制 Provider 密钥。
- 预检时两个目标文件不存在。帮助/版本预检不调用 Provider、不执行项目命令；不作为失败关闭已通过证据。

## A：runtime 缺失

普通终端启动：

```bash
/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/backend-failure-check/start.sh missing
```

进入 Vera 后整行输入：

```text
只调用一次 bash，严格使用 {"argv":["/bin/cp","inside.txt","backend-missing-must-not-exist.txt"],"cwd":".","timeout_seconds":5}。不调用其他工具、不修改沙盒设置、不申请额外权限、不重试。报告本次工具状态、错误原因、真实退出码和输出；未启动目标进程时不要编造退出码。
```

若出现命令审批卡，核对参数后输入 approve。预期未启动目标 cp，status=error、exit_code=null，错误包含 sandbox_unavailable；不要求外层 error_code 必须同名，以实际封装为准。普通命令审批拒绝不能算该用例通过。

在另一个普通终端执行：

```bash
if [ ! -d /private/tmp/vera-0089-acceptance.psEsZR/workspace ]; then echo 'ERROR：测试工作区不存在'; elif [ -e /private/tmp/vera-0089-acceptance.psEsZR/workspace/backend-missing-must-not-exist.txt ] || [ -L /private/tmp/vera-0089-acceptance.psEsZR/workspace/backend-missing-must-not-exist.txt ]; then echo 'FAIL：目标存在'; else echo 'PASS：目标不存在'; fi
```

错误结果与目标不存在共同构成本轮证据。单独文件不存在不能证明进程没有启动；必要时核对 Core 执行记录。

## B：runtime 版本错误

退出 A 的 Vera，回到普通终端，以以下入口启动（不要在 Vera 输入此启动命令）：

```bash
/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/backend-failure-check/start.sh version
```

```text
只调用一次 bash，严格使用 {"argv":["/bin/cp","inside.txt","backend-version-must-not-exist.txt"],"cwd":".","timeout_seconds":5}。不调用其他工具、不修改沙盒设置、不申请额外权限、不重试。报告本次工具状态、错误原因、真实退出码和输出；未启动目标进程时不要编造退出码。
```

核对命令卡后 approve。预期 status=error、exit_code=null，错误包含 sandbox_version_mismatch，目标 cp 不启动。

另一个普通终端检查：

```bash
if [ ! -d /private/tmp/vera-0089-acceptance.psEsZR/workspace ]; then echo 'ERROR：测试工作区不存在'; elif [ -e /private/tmp/vera-0089-acceptance.psEsZR/workspace/backend-version-must-not-exist.txt ] || [ -L /private/tmp/vera-0089-acceptance.psEsZR/workspace/backend-version-must-not-exist.txt ]; then echo 'FAIL：目标存在'; else echo 'PASS：目标不存在'; fi
```

## 恢复与结果边界

两项完成后退出故障会话，使用原 start-vera-recovery.sh 启动正常验收环境即可，不需要改回配置。任何目标文件出现或命令成功立即停止，保留现场，不删除、不重试。

本轮仅覆盖缺失与版本错误；不外推为配置损坏、profile 生成失败、所有初始化异常或整个任务 0089 已通过。结果已同步任务验收表。本机共享 Python 仍未修复。
