---
name: inspire
description: "Execution-first Inspire platform playbook for agents driving the inspire CLI as a black-box tool, with on-demand references for platform workflows."
---

# Inspire Skill

把 `inspire` CLI 当黑盒使用。不要读 CLI 源码来猜平台状态；状态、事件、日志、资源余量都通过命令实时查询。

## 1. 运维约束

| 主题 | 约束 |
| --- | --- |
| 输出观察面 | Agent 默认使用人类格式。人类输出更短，隐藏低价值 raw ID，适合直接决策。`--json` 只是脚本接口；只有写脚本、接 `jq` 或必须消费结构化字段时才使用。 |
| 代理配置 | 代理通过 `inspire account add`、账号级 config、`inspire config show` 和 `inspire config check` 管理。任务命令直接写 `inspire <cmd>`，CLI 会读取持久配置。 |
| 项目路径 | 项目远端路径通过 `inspire init --discover` 写入仓库级 `.inspire/config.toml`。日常命令直接用 notebook name、job name 和配置内路径。 |
| 实时事实源 | `job list`、`notebook list`、`resources specs/list/nodes` 等状态查询以平台实时结果为准。本地 cache 只能当 SSH 会话、事件副本等非权威辅助信息。 |
| 资源申请 | 先查实时空余，再按真实需求申请。不要因为模型保守而主动缩小规模；只有调度语义、项目配额或实时空余明确不足时才降档。 |
| 默认 workspace | 默认只主动使用 `CPU 资源空间` 和 `分布式训练空间`。其它 workspace 需要仓库级 `INSPIRE.md` 或用户明确指定。 |
| 优先级 | `--priority` 接受 1 到 10。1 到 3 是低优先级，4 是普通优先级，5 到 10 是高优先级。需要稳定运行时传 5 或更高，并用 `inspire job status <name>` 核对人类输出中的优先级。 |
| 排错入口 | 任务 PENDING、CREATING 过久或 FAILED 原因不明时，第一步查 `inspire <res> events <name>`。不要凭猜测重提。 |
| 清理 | 终态且不再需要的资源用 `<res> delete <name> --yes` 清理；running 先 stop。不确定是否仍有人使用时跳过。 |
| 大操作 | 共享盘大规模 `mv`、`cp`、`rm` 前先看文件量和大小分布。超过 20 分钟的远程操作用后台任务和 sentinel 文件，不要让 `notebook exec` 长时间同步挂住。 |

## 2. 基础命令入口

### 2.1 账号、配置、资源

| 命令 | 用途 |
| --- | --- |
| `inspire account add <name>` | 添加账号、平台地址和代理配置，并可设为活动账号 |
| `inspire account {list,use,current,remove}` | 多账号管理 |
| `inspire init --discover` | 在当前仓库绑定 Inspire 项目、workspace、compute group 和远端路径 |
| `inspire config show --compact` | 查看合并后的账号、代理、镜像和路径配置 |
| `inspire config context` | 查看活动账号、当前项目、workspace alias 和 compute groups |
| `inspire config check` | 检查认证和平台连通性 |
| `inspire resources list --all --include-cpu` | 查实时 GPU/CPU 可用量 |
| `inspire resources nodes -A` | 查整节点空余 |
| `inspire resources specs --usage all` | 查 notebook、job、HPC、Ray 可用规格三元组 |
| `inspire project list` | 查项目配额、预算和优先级 |
| `inspire user whoami` | 查当前登录身份 |
| `inspire user permissions --workspace <name>` | 查 workspace 权限码 |

### 2.2 Notebook

| 命令 | 用途 |
| --- | --- |
| `inspire notebook list -A` | 列 notebook，默认看人类表格 |
| `inspire notebook create --workspace X --group Y -q <gpu,cpu,mem> --image URL --project P --wait` | 创建实例并等待 RUNNING |
| `inspire notebook status <name>` | 查实例详情 |
| `inspire notebook events <name>` | 查生命周期事件 |
| `inspire notebook ssh <name>` | 建立 SSH 通路 |
| `inspire notebook exec <name> "<cmd>"` | 运行一次性远程命令 |
| `inspire notebook shell <name>` | 打开持久交互 shell |
| `inspire notebook scp <name> <src> <dst>` | 传非 Git 文件，远端路径优先写绝对路径 |
| `inspire notebook {start,stop,delete} <name> --yes` | 生命周期操作 |
| `inspire notebook test <name>` | 连通性测试 |

Notebook 细节、镜像固化、远程命令语义和大文件操作：加载 [references/notebook.md](references/notebook.md)。

### 2.3 Job、HPC、Ray

| 命令 | 用途 |
| --- | --- |
| `inspire job create -n <name> -q <gpu,cpu,mem> --nodes N -c "<cmd>" --workspace X --group Y --image URL --priority 5` | 创建 GPU 多节点任务 |
| `inspire run "<cmd>" -q <gpu,cpu,mem> --nodes N --workspace X --group Y --image URL --watch` | 快速提交 GPU job 并跟日志 |
| `inspire job {list,status,logs,events,stop,delete} <name>` | 观测、止损和清理 GPU job |
| `inspire hpc create -n <name> -c "<slurm-body>" --compute-group G --workspace X -q <gpu,cpu,mem> --project P --image URL --image-type SOURCE_PRIVATE` | 创建 CPU Slurm/HPC 任务 |
| `inspire hpc {list,status,events,metrics,stop,delete} <name>` | 观测、止损和清理 HPC 任务 |
| `inspire ray create ...` | 创建 Ray 集群；仅在明确需要弹性计算时使用 |
| `inspire ray {list,status,events,instances,stop,delete} <name>` | 观测、止损和清理 Ray 集群 |

GPU job、HPC 两层资源模型、Ray 适用边界和示例：加载 [references/compute-workloads.md](references/compute-workloads.md)。

### 2.4 镜像、部署和只读辅助命令

| 命令 | 用途 |
| --- | --- |
| `inspire image list --source all` | 浏览镜像 |
| `inspire image save <notebook-name> -n X -v v1 --public --wait` | 从 notebook 保存镜像 |
| `inspire image set-default --job URL --notebook URL` | 写入项目默认镜像 |
| `inspire serving list`、`inspire serving status <name>`、`inspire serving metrics <name>` | 模型部署观测；权限受限，创建优先走 Web UI |
| `inspire model list`、`inspire model versions <model-id>` | 模型注册表只读浏览 |
| `inspire project detail <project-id>`、`inspire user api-keys` | 项目 / 用户 metadata 查询 |

## 3. 按需加载索引

| 什么时候加载 | 引用 |
| --- | --- |
| 需要选择 workspace、compute group、规格三元组、存储池或远端路径 | [references/resources-and-paths.md](references/resources-and-paths.md) |
| 要创建、连接、执行、传文件、保存镜像或维护 notebook | [references/notebook.md](references/notebook.md) |
| 要提交 GPU job、CPU HPC、Ray，或解释优先级和调度事件 | [references/compute-workloads.md](references/compute-workloads.md) |
| 要按 CPU 准备、数据处理、训练三阶段推进项目 | [references/workflows.md](references/workflows.md) |
| SSH bootstrap、大规模文件操作或 notebook 远程命令排障 | [references/notebook.md](references/notebook.md) |
| 安装、更新、账号初始化或代理 setup | [references/setup/install-and-config.md](references/setup/install-and-config.md)、[references/setup/proxy-setup.md](references/setup/proxy-setup.md) |
| OpenAPI 合约或 Browser API 端点背景 | [references/dev/openapi.md](references/dev/openapi.md)、[references/dev/browser-api.md](references/dev/browser-api.md) |

## 4. `--quota` 通用格式

`notebook create`、`job create`、`run`、`hpc create`、`ray create --head-quota` 和 Ray worker 的 `quota=` 都使用三元组：

```bash
<gpu>,<cpu>,<mem>
```

`mem` 以 GiB 计。CPU-only 写成 `0,<cpu>,<mem>`。三元组必须在当前 workspace 可见规格中唯一匹配；多个 compute group 撞上同一三元组时，加 `--group <name>` 或对应命令的 compute group 参数消歧。先用：

```bash
inspire resources specs --usage all
```

## 5. 项目上下文

仓库根可用 `INSPIRE.md` 记录非配置性上下文，建议包含：

- `Default Image`
- `Path Conventions`
- `Public Directory Layout`
- `Existing Notebooks`
- `Ongoing Jobs`

不要把账号配置、密码、代理密钥或 `.inspire/config.toml` 内容复制进 `INSPIRE.md`。配置由 CLI 合并和展示。
