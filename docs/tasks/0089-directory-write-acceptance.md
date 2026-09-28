# 0089 目录读写授权补验

状态：人工验收通过（2026-09-27）。read_write/session 的创建文件、子目录写入、跨工具读取及相邻路径写入拒绝均有用户原始输出。

证据：session_39293ee09e1b4529bd7309f08b8d69e4；授权 run_a43702fe92e14a84ac0931ce278a673b；内建创建 run_87a1b9588a9a48408552af3fe9f2d290；Bash 子文件创建 run_0475cf5b7725436d965be7cb00612ccb；两文件读回 run_5266be83ebb940a78d9d84bd03b9cb07；相邻 write 拒绝 run_cadf127dbea640a8a663529eec4fc4fb；相邻 Bash 写入 EPERM run_6bbacdeecf57462990c33e6eba429149。用户宿主检查确认 directory-write-denied.txt 不存在。原始附件标识 e5ac19ce-1047-450d-969a-b10212fc4f66。下文保留复现步骤，文件已存在，不应原样重复当作新建测试。

## 准备与范围

2026-09-27 在原临时 outside 下独占新建 directory-write-test/nested，未修改历史文件；directory-write-denied.txt 尚不存在。正常启动入口为原 start-vera-recovery.sh，不使用故障配置，不调用已损坏的 Python。用户在 Vera 先执行 /permissions revoke，确认无额外文件权限。

## 顺序

以下请求每次仅指定的工具一次，不改参数、不新增权限、不预读、不自动重试。只有授权申请及获准范围内修改/命令的真实审批卡才输入 approve。

1. 仅调用 request_file_access：

```json
{"path":"/private/tmp/vera-0089-acceptance.psEsZR/outside/directory-write-test","mode":"read_write","scope":"session","reason":"验证目录读写授权包含子目录且不扩大到相邻路径"}
```

审批卡应显示精确目录、包含子目录、读写、本次会话。返回 recursive=true。

2. 仅调用 write（核对创建 Diff 后 approve）：

```json
{"path":"/private/tmp/vera-0089-acceptance.psEsZR/outside/directory-write-test/root.txt","content":"DIRECTORY_WRITE_ONLY\n"}
```

预期 ok=true、status=applied、operation=create。

3. 仅调用 bash（核对命令后 approve）：

```json
{"argv":["/bin/cp","inside.txt","../outside/directory-write-test/nested/from-bash.txt"],"cwd":".","timeout_seconds":5}
```

预期 exited/0，证明新子文件无需逐文件另申请。

4. 仅调用 bash 读取两个结果（命令审批 approve）：

```json
{"argv":["/bin/cat","../outside/directory-write-test/root.txt","../outside/directory-write-test/nested/from-bash.txt"],"cwd":".","timeout_seconds":5}
```

预期 exited/0，stdout 为 DIRECTORY_WRITE_ONLY\nINSIDE_ONLY\n。

5. 仅调用 write 尝试相邻未授权路径：

```json
{"path":"/private/tmp/vera-0089-acceptance.psEsZR/outside/directory-write-denied.txt","content":"MUST_NOT_BE_WRITTEN\n"}
```

预期 file_access_approval_required、无写入。如果意外出现新增授权/写入审批卡，reject 并停止，不借该卡扩大权限。

6. 仅调用 bash 尝试同一相邻路径（本条命令审批 approve，以检验 OS 文件边界）：

```json
{"argv":["/bin/cp","inside.txt","../outside/directory-write-denied.txt"],"cwd":".","timeout_seconds":5}
```

预期非零退出、stdout 空、stderr 包含 Operation not permitted。

7. 普通终端宿主只读确认目标不存在，不使用 Python：

```bash
if [ ! -d /private/tmp/vera-0089-acceptance.psEsZR/outside ]; then echo 'ERROR：测试目录不存在'; elif [ -e /private/tmp/vera-0089-acceptance.psEsZR/outside/directory-write-denied.txt ] || [ -L /private/tmp/vera-0089-acceptance.psEsZR/outside/directory-write-denied.txt ]; then echo 'FAIL：目标存在'; else echo 'PASS：目标不存在'; fi
```

任何结果不符均停止并保留现场，不删除文件、不重试、不扩大授权。结果已同步任务验收表；本轮不替代其他目录竞态、链接或进程生命周期用例。
