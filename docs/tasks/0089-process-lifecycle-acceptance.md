# 0089 实际沙盒进程生命周期验收

状态：首轮与第二轮人工通过（2026-09-27）。正常命令结束、超时终止、超时后会话继续可用，以及同进程组父子超时清理已有实际 SRT 证据。第三轮独立 Core+SRT 主动取消及运行中撤销亦通过；CLI 取消/运行中撤销交互和逃离进程组不在已通过范围。

用户提供正常 SRT 配置下 session_d1b63afa44be4b579b41d8ff7237fa6d 的原始 CLI 输出：

- 正常对照 run_4dbc5e27e39e4b7cbead830182245bb9：sleep 1 / timeout 5，exited、exit_code=0。
- 超时 run_30fef936ab9d4408bd6eceacaeb1624e：sleep 15 / timeout 2，ok=false、error_code=timeout、status=timed_out、exit_code=-15，stdout/stderr 为空。
- 超时后下一条 run_f538863a7ebe492eb73f088f2f89ee1c：sleep 1 / timeout 5，exited、exit_code=0。
- 三次均用户批准，未新增文件权限。未测量独立墙钟时长，未采集子进程存活证据，不宣称后代清理已通过。下文保留复现步骤。

## 1. 切回正常配置

在故障会话的 Vera 提示符输入 `/exit`，回到普通终端后运行：

```bash
/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/start-vera-recovery.sh
```

在 Vera 输入 `/permissions revoke`，确认额外文件权限为无、沙盒已配置。本轮不要使用 backend-failure-check 的入口。

## 2. 正常结束对照

```text
只调用一次 bash，严格使用 {"argv":["/bin/sleep","1"],"cwd":".","timeout_seconds":5}。不调用其他工具、不新增权限、不重试，仅报告本次真实的 ok、error_code、status、exit_code、stdout、stderr。
```

命令审批核对后 approve。预期 ok=true、status=exited、exit_code=0、stdout/stderr 为空。

## 3. 超时

```text
只调用一次 bash，严格使用 {"argv":["/bin/sleep","15"],"cwd":".","timeout_seconds":2}。不调用其他工具、不新增权限、不重试，仅报告本次真实的 ok、error_code、status、exit_code、stdout、stderr。不要把超时描述成审批拒绝，也不要自行填写退出码。
```

命令审批核对后 approve。批准后等待返回，不发送 Ctrl+C 或 /cancel。预期 ok=false、error_code=timeout、status=timed_out。exit_code 按工具真实结果记录，不固定要求为 null、1 或 124；目标已启动，与后端故障不同。计时不含模型请求、审批等待和后续模型回复；总交互时长不能当成精确进程时长。

## 4. 超时后继续使用

再次执行第 2 步的相同请求并 approve。预期退出码 0。该调用由用户明确发起，用于验证超时后下一次命令可用，不是自动重试超时命令。

## 结果边界

- 使用系统 sleep，不读写文件，不联网，不需要 Python，也不向任何已有进程发送信号。
- 本节仅描述首轮超时证据；后续父子清理与 Core 取消结果见第 5、6 节。
- 若正常对照失败、返回 sandbox_unavailable/version_mismatch、长时间不返回或模型未按参数执行，保留输出并停止，不切换后端、不修改策略。
- 收到结果后同步任务 0089 当前验收表；本文件的“预期”不是已通过证据。

## 5. 第二轮：超时清理父子进程（人工通过）

用户返回 run_d4ef7a30bca94e47af3fc754158dbfb7：approve 后 ok=false、error_code=timeout、status=timed_out、exit_code=-9，stdout 为 PROBE_READY parent=37379 child=37380，stderr 为空。独立监视器先报告 OBSERVED_ALIVE，同一对 PID 随后在启动后 7 秒内均消失（PASS），早于 20 秒自然退出上限。结合两窗口证据，确认本次忽略 SIGTERM 的同进程组父子被超时清理；不凭父进程退出码推断子进程状态。下文保留原步骤，不应直接重复使用已有 PID 文件。

夹具：临时 workspace/timeout-child-probe.pl，使用系统 /usr/bin/perl。父子继承忽略 SIGTERM，均最多等待 20 秒，不脱离进程组；只在工作区记录启动时间和两个 PID，不访问网络或真实文件。语法检查通过，未执行预探针。

只读监视器：临时根目录 watch-timeout-child.pl；使用 kill(0, pid) 存活探测，不发送终止信号、不修改进程。要求实际观察到两进程存活，且它们在启动后 12 秒内均消失；不能以 20 秒自然退出当通过。未观察到存活、记录已存在或等待启动超过 90 秒均为无效/待排查，不自动清理、不自动重试。

1. 正常配置 Vera 会话，提交以下请求，先停在审批卡，不批准：

```text
只调用一次 bash，严格使用 {"argv":["/usr/bin/perl","timeout-child-probe.pl"],"cwd":".","timeout_seconds":5}。这是临时父子进程超时清理验收。不调用其他工具、不新增权限、不修改脚本、不重试。报告真实的 ok、error_code、status、exit_code、stdout、stderr，不根据父进程结果推断子进程已经退出。
```

2. 另一个普通终端执行：

```bash
/usr/bin/perl /private/tmp/vera-0089-acceptance.psEsZR/watch-timeout-child.pl
```

3. 看到 READY 后，90 秒内回到审批卡输入 approve，随后不按 Ctrl+C、不发送 /cancel。
4. 预期 Vera 返回 timed_out/timeout，stdout 含 PROBE_READY 和两个 PID；退出码按真实值记录，不固定为 -9 或 -15。
5. 监视器必须先报告 OBSERVED_ALIVE，然后 PASS: both PIDs gone ...；失败或 INCONCLUSIVE 保留输出，不重试、不手动 kill。脚本有 20 秒自然结束上限；上限仅减少残留风险，不替代清理证据。
6. 用户返回两窗口输出后再判定。本组不覆盖逃离进程组、手动取消或运行中撤销权限。

## 6. 第三轮：Core 主动取消与运行中撤销通过（独立入口）

运行中撤销证据：用户输出与 control-revoke-4ucopa9n/result.json、post-revoke.json 一致。授权期间读到 GRANT_READ=CONTROL_FAKE_ONLY；观察 parent=38122、child=38123 存活后，用户触发 revoke，返回 cancelled/-9，2.053 秒内两 PID 均消失、before_natural_exit=true。后续同会话真实 SRT cat 返回 exited/1、stdout 为空、stderr=Operation not permitted，确认撤销后新命令无读取权限。

主动取消证据：用户输出与 control-cancel-hw8z1z29/result.json 一致，先观察 parent=37919、child=37920 存活，用户触发取消后 status=cancelled、exit_code=-9、group_managed=true；2.056 秒后两 PID 均消失且 before_natural_exit=true。此前 control-cancel-rtj2gn9k 返回 NOT_STARTED，未执行测试，不计通过或失败。

Plain CLI 同步执行时不能接收撤销命令，因此临时准备 lifecycle-control.py 与 run-lifecycle-control.sh，直接连接 AccessSession、SandboxedSupervisor 与正常配置的真实 SrtBackend。不是模拟后端，也不经过模型、Runtime ApprovalGate 或 CLI 取消 UI；不得据此关闭 CLI 交互缺口。

每轮在原假数据根目录创建新的 control-cancel-* / control-revoke-*，内有专用 workspace、假 grant.txt 和结果 JSON；不修改原配置或已有假文件。复用已验证的 Perl 父子夹具，忽略 SIGTERM、自然结束上限 20 秒；进程请求 timeout=15 秒。预检 --check 只验证导入、配置及原夹具可读，已通过；没有启动测试进程。

普通终端先执行：

```bash
/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/run-lifecycle-control.sh cancel
```

核对 FIXTURE 为临时测试目录，输入 approve 后才启动测试进程。看到 OBSERVED_ALIVE 和 ACTION_READY 后，6 秒内按 Enter，调用 cancel_event.set()。预期 status=cancelled、group_managed=true、parent_gone=true、child_gone=true、before_natural_exit=true 和 PASS: cancel。退出码按实际值记录。

第一项通过后执行：

```bash
/bin/sh /private/tmp/vera-0089-acceptance.psEsZR/run-lifecycle-control.sh revoke
```

入口明确展示临时 grant.txt 只读授权，用户输入 approve 后才由夹具调用 AccessSession.resolve；这不是产品审批卡。测试进程启动时读取该假文件，看到 OBSERVED_ALIVE/ACTION_READY 后 6 秒内按 Enter，调用 AccessSession.revoke(grant_id)，而非取消事件。预期同上 cancelled 和两 PID 消失，stdout 含 GRANT_READ=CONTROL_FAKE_ONLY。随后在同一 AccessSession 下以真实沙盒执行 cat ../grant.txt，预期非零退出、stdout 为空、stderr 包含 Operation not permitted；记录 POST_REVOKE，最后 PASS: revoke。

夹具异常或输入超时会以取消事件收尾，仅作用于自身创建的测试进程；这种收尾不能判定本用例通过。不手动 kill、不自动重试。结果分别保留为 result.json、post-revoke.json。主动取消与运行中撤销均通过；不代表产品 CLI 交互已通过。
