# Job、HPC 与 Ray

## 什么时候加载

当任务需要提交 GPU 多节点 job、CPU Slurm/HPC、Ray 弹性集群，或需要解释优先级、HPC 两层资源、Ray 适用边界、调度事件时，加载本文档。

## 1. GPU 多节点任务：`job`

`inspire job` 覆盖 GPU 多节点工作负载，包括分布式训练、批量推理和并发单节点 worker pool。`job` 是 GPU 路径；`hpc` 是 CPU Slurm 路径。

命令列表、参数和单命令功能以 CLI help 为准。先用 `inspire job --help` 看可用子命令；需要提交、查看、日志、事件、停止、删除或指标时，再分别查 `inspire job <subcommand> --help`。快速提交入口也可查 `inspire run --help`。

`job list`、name-to-ID 解析和状态判断都应使用平台实时结果，不把本地历史 cache 当事实来源。

## 2. 优先级

`--priority` 是 1 到 10 的数字，平台映射为三档：

| 数值 | 平台语义 |
| --- | --- |
| 1 到 3 | 低优先级，会被高优任务抢占 |
| 4 | 普通优先级 |
| 5 到 10 | 高优先级，适合稳定训练 |

需要稳定运行时传 5 或更高。提交后用人类输出核对：

```bash
inspire job status <name>
```

如果显示为 LOW，先 stop，再用更高优先级重提。

## 3. HPC 两层资源模型

`hpc create` 有两层资源，不能混：

| 层级 | 参数 | 含义 |
| --- | --- | --- |
| 节点级 | `--quota gpu,cpu,mem` 和 `--instance-count` | 选择平台计算资源规格，以及申请多少个这样的节点 |
| Slurm 级 | `--number-of-tasks`、`--cpus-per-task`、`--memory-per-cpu` | 告诉 Slurm 如何在节点配额内切任务 |

不传 Slurm 级参数时，默认 `cpus-per-task = quota.cpu`、`memory-per-cpu = quota.mem // quota.cpu`、`number-of-tasks = 1`，即整节点一个 task。

HPC 关键约束：

1. `-c` 只写 Slurm 正文，平台自动补 `#SBATCH` 头；程序必须显式 `srun` 启动。
2. `--compute-group "<name>"` 按 name 传。
3. Slurm 级参数超出节点规格时可能静默排队。
4. `--image` 必须是完整 Docker 地址，并带可用 Slurm 环境；通用基底是 `docker.sii.shaipower.online/inspire-studio/unified-base:v2`。
5. 平台自身吃约 0.3 核 CPU 和 384 MB 内存，应用层并发压到 `cpus-per-task - 4` 或更低。

CPU 空间里只有 `HPC-可上网区资源-2` 支持 `inspire hpc create`。该组的 `500GB` 规格可能静默排队；真需要大内存交互处理时，退化成在 `CPU资源-2` 开 notebook。

示例：

```bash
inspire hpc create -n <name>-preprocess \
  -c 'srun bash -lc "python preprocess.py"' \
  --compute-group HPC-可上网区资源-2 --workspace CPU资源空间 \
  -q 0,20,256 \
  --cpus-per-task 16 --memory-per-cpu 12 \
  --number-of-tasks 1 --instance-count 1 \
  --project <P> --image docker.sii.shaipower.online/inspire-studio/unified-base:v2 \
  --image-type SOURCE_PRIVATE
```

平台自动注入类似以下 Slurm 头，不要在正文重复维护：

```bash
#SBATCH -o /hpc_logs/slurm-%j.out
#SBATCH -e /hpc_logs/slurm-%j.err
#SBATCH --ntasks=*
#SBATCH --cpus-per-task=*
#SBATCH --mem=*G
#SBATCH --time=*
```

`status=SUCCEEDED` 不等于 payload 真跑过。每个新 entrypoint 写唯一 fingerprint 到共享盘，再用同项目 notebook 回读验证。

## 4. Ray 适用边界

默认不要使用 Ray，除非任务明确需要弹性 worker、长守护、流式处理或异构 worker。固定规模 GPU 走 `job`，固定规模 CPU 走 `hpc`。

Ray 当前主要在 `CI-情境智能` workspace 和 `CPU资源-2` 计算组可用，整体仍偏试验性。使用前先查：

```bash
inspire resources specs --usage ray
```

示例：

```bash
inspire ray create -n <name>-pipeline \
  -c 'python driver.py --mode run_and_exit' \
  --head-image docker.sii.shaipower.online/inspire-studio/unified-base:v2 \
  --head-group CPU资源-2 --head-quota 0,2,8 \
  --worker 'name=w1;image=docker.sii.shaipower.online/inspire-studio/unified-base:v2;group=CPU资源-2;quota=0,4,16;min=1;max=8;shm=32' \
  -p <P> --workspace CPU资源空间
```

Ray 特有坑：

- 镜像必须带 Ray runtime。
- `--head-quota` 和 worker `quota=` 用 Ray 专属配额表。
- `min` 和 `max` 都必须大于等于 1。
- driver 不退出，集群就一直占配额；长守护任务要接受手动 stop 的运维模型。

## 5. 事件优先

任务卡住或失败时优先查事件：

```bash
inspire job events <name> --tail 50
inspire hpc events <name> --tail 50
inspire ray events <name> --tail 50
```

`job` 和 `ray` 可以进一步看 pod/instance 级原因；HPC 只暴露 job-level 事件。

## 6. HPC 异常状态对照

| 现象 | 优先怀疑 |
| --- | --- |
| `slurmctld BackOff` | 镜像不带 Slurm 运行环境 |
| `steps=-/0` | 正文没用 `srun` 启动程序 |
| `nodes=[]` | 调度未分配；可能是配额 / 优先级问题 |
| `status=SUCCEEDED` 但目录 / `stdout.log` / 报告为空 | CPU 并发或内存贴边；应用层应留 `cpus-per-task - 4` 和约 384 MB 内存余量 |
| `quota match failed` / 0 候选 | `--quota gpu,cpu,mem` 在当前 workspace 找不到对应规格。用 `inspire resources specs --usage hpc` 重选；多组撞名时加 `--group <name>` 消歧 |
| `image not found` | 镜像地址不完整；必须是 `host/namespace/name:tag` 全形式 |
| `429` | 已内置退避；持续失败就等几分钟 |

## 7. 模型部署：`serving`

`inspire serving` 面向模型部署服务，普通训练 / 预处理任务不要走它。账号需有 `inference_serving.create` 或等价权限；普通账号在 Web UI 上点"部署服务"可能被静默踢回首页，CLI create 也不会可靠。

命令列表、参数和单命令功能以 CLI help 为准。先用 `inspire serving --help` 看可用子命令；需要列部署、看状态、停止服务、查看可用配置或读取指标时，再分别查 `inspire serving <subcommand> --help`。

`list` / `configs` 只在 Browser API；`status` / `stop` OpenAPI 和 Browser API 都有，CLI 优先选 OpenAPI。创建部署的参数过多且强绑定 Web 表单，CLI 暂不覆盖，直接用 Web UI `/jobs/modelDeployment`。
