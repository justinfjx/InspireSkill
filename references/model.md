# Model Registry

浏览模型仓库、查看模型版本，或判断 model registry 和 serving 的边界时，先查本手册。模型上传、模型注册、部署创建和 serving 运维不在这里展开；部署生命周期看 [compute-workloads.md](compute-workloads.md) 的 serving 部分。

命令是否存在、参数名和默认值以 CLI help 为准：

```bash
inspire model --help
inspire model <subcommand> --help
```

## 1. 定位与边界

`inspire model` 是启智平台模型仓库的浏览入口。

- 所有当前命令均为**只读**，不包含上传、注册、修改或删除能力
- 模型上传 / 注册仍需在平台模型仓库页面完成

## 2. 与 `serving` 的关系

| 命令组 | 定位 | 不负责 |
| --- | --- | --- |
| `model` | 浏览模型仓库，选择模型和版本 | 不创建部署、不停止服务 |
| `serving` | 观察和停止已经存在的模型部署服务 | 不上传模型、不浏览模型版本 |

流程通常是先用 `model` 找到目标模型和版本，再到平台部署页面创建 serving 服务；服务启动后，用 `serving` 观察状态、资源指标或停止服务。`model` 是“找模型和看版本”，`serving` 是“管理已经部署的服务”。

## 3. 操作判断

| 目标 | 入口 | 后续动作 |
| --- | --- | --- |
| 看当前 workspace 有哪些模型 | `model list` | 找到候选模型名后再看详情 |
| 看某个模型的元数据和版本摘要 | `model status <model-name>` | 确认存储路径、版本和可部署性 |
| 看历史版本 | `model versions <model-name>` | 选择要部署或复现的版本 |
| 创建或修改部署服务 | 平台部署页面 | 转到 [compute-workloads.md](compute-workloads.md) |

```bash
inspire model list
inspire model list --workspace <WORKSPACE>
inspire model status <model-name>
inspire model versions <model-name>
```

## 4. 限制

- CLI 不覆盖模型上传或注册；模型首次入库必须通过平台模型仓库页面。
- model registry 与 model deployment 是两个不同的平台模块；前者是仓库浏览，后者是服务生命周期管理。
- 日常默认看 human 输出；只有脚本消费字段或需要精确结构时才用 `--json`。
