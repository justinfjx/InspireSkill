# Inspire Project Context

本文件是本仓库的启智上下文记录，必须和 `AGENTS.md`、`CLAUDE.md` 等本地 Agent 计划文件分开维护。Agent 专属文件可以记录短期执行计划；启智平台相关的长期协作约定、远端路径语义和资源边界写在这里。

不要在本文复制账号配置、密码、代理密钥、平台 session 或 `.inspire/accounts/<account>/config.toml` 内容。配置事实以 CLI 合并结果为准，本文只记录人类可读的项目约定。

## Project Role

InspireSkill 是启智平台 CLI、skill 和 reference 文档的源仓库。日常维护重点是让 CLI help、Agent skill、references 和平台真实行为保持一致，不把历史 release 状态或本地 agent 计划当作当前平台事实。

## Context Boundaries

- `SKILL.md`：只保留超出 CLI help 的平台操作模型和 reference 路由。
- `references/`：只保留帮助 Agent 做平台判断、执行闭环和边界选择的上下文；命令语法回到 CLI help。
- `references/dev/`：只用于维护 Browser API 封装、排查接口合同或明确的开发请求。
- `AGENTS.md` / `CLAUDE.md`：本地 agent 计划文件，不进入发布包，不承载启智项目上下文。
- `.inspire/`：本地账号隔离配置和仓库上下文，不提交。

## Default Principles

- 没有默认 workspace；创建和 live 查询资源时显式传 `--workspace` 或使用明确的 workload profile。
- 调度条件是 `workspace`、`project`、`group`、`quota`、`image`；远端路径只用 path alias 表达。
- 普通 CLI 输入输出保持 Name-only，平台 handle 只留在 resolver、debug 或专门 `id` 命令里。
- 公网准备、SII 内部源、离线 GPU 空间和镜像固化要分开判断。
