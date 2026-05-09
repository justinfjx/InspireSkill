---
name: inspire
description: "Execution-first Inspire platform playbook for agents driving the inspire CLI as a black-box tool, with on-demand references for platform workflows."
---

# Inspire Skill

把 `inspire` CLI 当黑盒工具使用。不要读 CLI 源码来推断平台状态；状态、事件、日志、资源余量全部通过命令实时查询。

## 1. 运维约束

| 主题 | 约束 |
| --- | --- |
| 输出观察面 | Agent 默认使用人类格式。人类输出更短，隐藏低价值 raw ID，适合直接决策。`--json` 是脚本接口，只在写脚本、接 `jq` 或必须消费结构化字段时使用。 |
| 代理配置 | 代理通过 `inspire account add`、账号级 config、`inspire config show` 和 `inspire config check` 管理。任务命令直接写 `inspire <cmd>`，CLI 会读取持久配置。 |
| 项目路径 | 项目远端路径只通过仓库级 `[path_aliases]` 表达。`inspire init --discover` 会写入 `me`、`public`、`global-me` 和按存储池区分的 alias；`notebook exec` / `shell` 默认用 `me`，临时切目录用 `--cwd me:<subdir>`，新增持久 alias 用 `inspire notebook set-path ... as <alias>`。 |
| 实时事实源 | `job list`、`notebook list`、`resources specs` / `list` / `nodes` 等状态查询以平台实时结果为准。本地 cache 只能存放 SSH 会话、事件副本等非权威辅助信息。 |
| 资源申请 | 先查实时空余，再按真实需求申请。不要因为模型保守而主动缩小规模；只有调度语义、项目配额或实时空余明确不足时才降档。 |
| 默认 workspace | 默认只主动使用 `CPU 资源空间` 和 `分布式训练空间`。其它 workspace 需要仓库级 `INSPIRE.md` 或用户明确指定。 |
| 优先级 | `--priority` 接受 1 到 10。1 到 3 是低优先级，4 是普通优先级，5 到 10 是高优先级。需要稳定运行时传 5 或更高，并用 `inspire job status <name>` 核对人类输出中的优先级。 |
| 排错入口 | 任务 PENDING、CREATING 过久或 FAILED 原因不明时，第一步查 `inspire <res> events <name>`。不要凭猜测重试或重提。 |
| 清理 | 终态且不再需要的资源用 `<res> delete <name> --yes` 清理；running 先 stop。不确定是否仍有人使用时跳过。 |
| 大操作 | 共享盘大规模 `mv`、`cp`、`rm` 前先看文件量和大小分布。超过 20 分钟的远程操作使用后台任务 + sentinel 文件，不要让 `notebook exec` 长时间同步挂住。 |

## 2. CLI 命令查询入口

命令列表、子命令功能和参数说明以 CLI help 为准，不在 SKILL 或 references 中维护硬编码清单。需要确认某个操作时，先查 help，再执行实时查询或提交。

```bash
inspire --help
inspire <command-group> --help
inspire <command-group> <subcommand> --help
```

在本仓库源码 checkout 内验证 CLI 行为时，用：

```bash
cd cli
uv run inspire --help
uv run inspire notebook --help
uv run inspire hpc create --help
```

`inspire --help` 的 `Commands` 区给出当前版本真实命令组；`inspire <command-group> --help` 给出该组所有子命令；`inspire <command-group> <subcommand> --help` 给出参数、默认值、必填项和注意事项。不要把旧文档、记忆或历史示例当作命令存在性的事实来源。

常见任务的语义背景仍按需加载 reference：

- Notebook 细节、镜像固化、远程命令语义和大文件操作：加载 [references/notebook.md](references/notebook.md)。
- GPU job、HPC 两层资源模型、Ray 适用边界和示例：加载 [references/compute-workloads.md](references/compute-workloads.md)。
- Workspace、compute group、规格三元组、存储池和路径隔离：加载 [references/resources-and-paths.md](references/resources-and-paths.md)。

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

## 4. 项目上下文

仓库根可用 `INSPIRE.md` 记录非配置性上下文，建议包含：

- `Default Image`
- `Path Conventions`
- `Public Directory Layout`
- `Existing Notebooks`
- `Ongoing Jobs`

不要把账号配置、密码、代理密钥或 `.inspire/config.toml` 内容复制进 `INSPIRE.md`。配置由 CLI 合并和展示。
