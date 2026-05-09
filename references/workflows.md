# 三阶段项目工作流

## 1. 阶段 A：CPU 空间准备基底环境

默认先在 `CPU 资源空间` 起可上网 notebook，安装项目依赖、Slurm/Ray/训练依赖，并保存成项目镜像。这样后续 notebook、job、HPC、Ray 都复用同一基底，减少冷启动和重复安装。

仓库远端路径默认从 `me` path alias 开始；多个 repo 并列时用 `me:<repo>`。如果需要更短名字，先用 `inspire notebook set-path ... as repo` 写入仓库级 alias。

```bash
inspire notebook create --workspace CPU资源空间 --group CPU资源-2 -q 0,20,256 \
  --name <name>-base --image docker.sii.shaipower.online/inspire-studio/unified-base:v2 \
  --project <P> --wait

inspire notebook ssh <name>-base --cwd me
inspire notebook exec <name>-base --cwd me:<repo> "python --version && nvidia-smi || true"
inspire notebook install-deps <name>-base --slurm --ray
inspire image save <name>-base -n <img> -v v1 --public --wait
inspire image set-default --job <URL> --notebook <URL>
```

一次性临时任务可以跳过 `image save`。

## 2. 阶段 B：CPU 空间跑数据处理

固定规模批处理用 HPC；流式、长守护或异构 worker 才考虑 Ray。

| 形态 | HPC | Ray |
| --- | --- | --- |
| 任务边界 | 明确开始和结束 | 长时间流式或服务型 |
| 并发模型 | 固定 `ntasks × instance_count` | `min/max` 弹性伸缩 |
| 数据流 | GPFS 到处理再到 GPFS | worker 间走 Ray 对象存储 |
| 结束条件 | `srun` 退出自动结束 | driver 退出才结束 |

正式放量前先跑接近生产规模的 probe。小规模通过不代表正式规模稳定。

HPC 示例：

```bash
inspire hpc create -n <name>-preprocess \
  -c 'srun bash -lc "python preprocess.py"' \
  --compute-group HPC-可上网区资源-2 --workspace CPU资源空间 \
  -q 0,20,256 --cpus-per-task 16 --memory-per-cpu 12 \
  --number-of-tasks 1 --instance-count 1 \
  --project <P> --image <URL> --image-type SOURCE_PRIVATE
```

Ray 示例见 [compute-workloads.md](compute-workloads.md)。

## 3. 阶段 C：分布式训练空间

训练空间多数节点不可上网。依赖、权重和数据集先在可上网空间下载到共享盘，再进训练空间。

单节点调试：

```bash
inspire notebook create --workspace 分布式训练空间 --group H100 -q 1,20,200 \
  --name <name>-debug --image <ref> --project <P> --wait
inspire notebook ssh <name>-debug --cwd me:<repo>
inspire notebook exec <name>-debug --cwd me:<repo> "nvidia-smi"
```

多节点训练：

```bash
inspire job create -n <name>-train -q 8,160,1800 --nodes 2 \
  -c 'bash <repo>/train.sh' --workspace 分布式训练空间 --group H100 \
  --image <ref> --priority 5
```

`job create` / `run` 没有 `--cwd` 参数；配置了 `me` alias 时，CLI 会在远端先进入 `me` 根目录再执行命令。因此示例里的 `<repo>/train.sh` 是相对 `me` 的路径。

快速提交并跟日志：

```bash
inspire run 'bash <repo>/train.sh' -q 8,160,1800 --nodes 2 \
  --workspace 分布式训练空间 --group H100 --image <ref> --watch
```

训练失败或长时间排队时，先查：

```bash
inspire job events <name>-train --tail 50
inspire job logs <name>-train --tail 100
inspire job status <name>-train
```
