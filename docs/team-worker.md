# run_worker 使用文档

导入：`from haishui_cli.team.worker import WorkerSpec, run_worker`（须子模块直导）。5 参数均为必填位置参数。

| 参数 | 类型 | 作用 |
|---|---|---|
| `spec` | `WorkerSpec` | 待执行派遣（只读 goal/context/task_id/attempt/toolsets，不回写） |
| `role_system` | `str` | 角色人设；非空经 env+prompt 双通道注入 |
| `model` | `Optional[str]` | 非空追加 `-m`；None 继承全局 |
| `timeout` | `int` | 超时秒数，直传 subprocess |
| `usage_dir` | `Path` | 用量文件目录；`{task_id}.a{attempt}.json` 经 `--usage-file` 交子进程落盘 |

**返回** `Dict[str, Any]`：正常 4 键 `ok/output/exit_code/seconds`；stdout/stderr 先 strip；`ok`=退出码 0 且 stdout 非空；`output` 取 stdout，空则回落 stderr；普通失败带真实码、无 error 键。超时/异常兜底：`ok=False`、`output=""`、`exit_code=-1`，额外带 `error`（仅此两分支）。线程安全（纯子进程）。
