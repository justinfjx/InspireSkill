# Image 管理

选择现有镜像、从 notebook 固化镜像、注册外部镜像、调整可见性或清理镜像时，先查本手册。Notebook 内怎么安装依赖看 [notebook.md](notebook.md)；job / notebook 如何调度看对应业务手册。

命令是否存在、参数名和默认值以 CLI help 为准：

```bash
inspire image --help
inspire image <subcommand> --help
```

## 1. 镜像在工作流中的位置

镜像是把“已经装好的运行环境”固化下来，并在 notebook、job、HPC、Ray 或 serving 间复用的方式。公网下载放在 `CPU资源空间` 的可上网 CPU notebook；只缺平台内包、内部 Docker 镜像或对象存储访问时，优先在目标 notebook 里配置 SII 内部源，`分布式训练空间` 等 GPU 空间也可能直接跑通。环境验证通过后再 `image save` 成项目镜像，后续 workload 复用该稳定环境。

镜像不负责保存数据集、权重和 checkpoint；这些应放在共享盘路径里，用 path alias 管理。

## 2. 选择哪条镜像路径

| 目标 | 镜像路径 | 判断依据 |
| --- | --- | --- |
| 直接使用官方或已有自定义镜像 | `image list` / `image detail` | 镜像已经存在，且状态可用于调度 |
| 把运行中的 notebook 环境固化 | `image save` | 依赖是在平台 notebook 里装好的 |
| 把外部 Docker 镜像纳入平台 | `image register` | 镜像是在本地、CI 或外部 registry 构建的 |
| 调整共享范围 | `image set-visibility` | 同项目或协作方需要复用，或实验镜像应收回私有 |
| 清理废弃镜像 | `image delete` | 确认没有活跃 notebook、job、HPC 或 serving 依赖它 |

镜像能被调度的最低要求：状态为 `READY`，地址或名称能被对应命令接受，并且目标 workspace / project 有权限读取它。

## 3. 浏览和选择镜像

```bash
inspire image list
inspire image list --source private
inspire image list --source all
inspire image detail <name>:<version>
```

选择镜像时先看状态、版本、来源和可见性。提交 notebook、job 或 HPC 前，如果镜像刚保存或刚注册，必须确认已经 `READY`；不要只看创建命令成功。

## 4. 从 notebook 固化：`image save`

适用于“在 notebook 里装好环境，再保存成项目通用基底”。创建 notebook、安装依赖和远程验证属于 [notebook.md](notebook.md)；本文只覆盖固化动作和后续镜像状态。

```bash
inspire image save <notebook-name> --workspace <WORKSPACE> -n <img-name> -v v1 --visibility public --wait
```

使用要点：

- `NOTEBOOK` 是 notebook 名称。
- 用 `--wait` 等到镜像进入 `READY`，否则后续任务可能拉不到镜像。
- `--visibility public|private` 控制平台可见性；敏感依赖、内部数据或个人实验镜像默认保持私有。
- `image save` 会触发一段中等时长的镜像保存过程；保存过程中不可操作该 notebook；保存完毕后 notebook 不会被自动停止，仍可继续连接和使用。
- 固化后再用 `image list` 或 `image detail` 确认名称、版本和状态。

## 5. 注册外部镜像：`image register`

适用于镜像已在本地、CI 或外部 registry 构建完成，需要让平台能调度它。不要用 `register` 保存运行中的 notebook；那是 `image save` 的职责。

### Push 工作流

平台创建一个镜像槽并返回 registry URL，Agent 把镜像推上去：

```bash
inspire image register -n my-img -v v1.0
# 根据 CLI 输出的 registry URL 执行：
docker tag <local-image> <registry-url>
docker push <registry-url>
# 平台检测到推送后自动标记为 READY
```

### Address 工作流

镜像已托管在公开或私有 registry，直接注册地址：

```bash
inspire image register -n my-img -v v1.0 --method address
```

注册后同样要等 `READY`。如果平台一直无法拉取镜像，优先怀疑 registry 权限、镜像地址不完整、tag 不存在或目标 workspace 无法访问该 registry。

## 6. 可见性

可见性翻转用于已经存在的自定义镜像：

```bash
inspire image set-visibility <name>:<version> --visibility public
inspire image set-visibility <name>:<version> --visibility private
```

公开前确认镜像内没有账号 token、私有 wheel、内部数据或临时调试文件。

## 7. 清理原则

只删除确认不再使用的自定义镜像。清理前至少确认：

- 没有正在运行或排队的 notebook、job、HPC、Ray 或 serving 依赖该镜像。
- 后续创建命令不再显式引用它。
- 协作者不再用这个版本复现实验。
