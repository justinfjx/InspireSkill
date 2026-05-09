# Notebook 工作流

创建、连接、执行、传文件、诊断、暴露容器端口，或在 notebook 内准备基底环境时，先查本手册。镜像保存、注册、默认值和可见性看 [image-management.md](image-management.md)；workspace、compute group、quota 和 path alias 概念看 [resources-and-paths.md](resources-and-paths.md)。

## 1. CLI help 查询

notebook 子命令、参数和功能说明以 CLI help 为准，不在手册里维护速查表。

```bash
inspire notebook --help
inspire notebook create --help
inspire notebook exec --help
inspire notebook scp --help
```

需要确认单个操作时，先查对应子命令的 `--help`，再结合本文档的约束选择 workspace、compute group、路径和执行方式。

## 2. `shell` 与 `exec`

`inspire notebook shell <name>` 是持久 SSH 会话，cwd、环境变量和 history 会保留到 `exit`。多个终端并开就是多个独立会话，互相共享同一容器资源。

`inspire notebook exec <name> "<cmd>"` 是一次性独立子进程。两次调用之间不共享 cwd 或环境变量。需要连续状态时，把状态放在同一条命令里：

```bash
inspire notebook exec <name> --cwd me:<repo> "export X=1 && ./run.sh"
```

不传 `--cwd` 时，CLI 默认使用 `me` path alias；没有 `me` 时才落到远端 `$HOME`。路径 alias 支持 `me`、`me:<subdir>` 和 `me/<subdir>` 形式。需要长期使用的子目录可以先登记成专用 alias：

```bash
inspire notebook set-path <name> /inspire/ssd/project/<topic>/<user>/<repo> as repo
inspire notebook exec <name> --cwd repo "pwd"
```

超过 20 分钟的任务写成远端后台进程和 sentinel 文件，再从本机轮询，不要让 `exec` 同步等待。

## 3. SSH bootstrap

`inspire notebook ssh <name>` 对任何镜像、计算组和公网状态都应可用。CLI 会在容器里启动 sshd 和 rtunnel，通路缓存到本地。

冷启动时间很贵时，可以 `image save` 派生镜像固化环境；一次性任务用完即弃即可。

### 诊断入口

首选自动化诊断：

```bash
inspire notebook test <name>
```

该命令检查 SSH bootstrap 全链路并输出各阶段耗时，是排查连接问题的首选入口。test 失败时，再查看下表对照。

### Bootstrap 机制

CLI 在容器内跑 bootstrap shell 做两件事：

1. 起 sshd：如果 `/usr/sbin/sshd` 不在，先从 `/inspire/hdd/global_public/inspire-skill-bootstrap/v1/sshd-debs/` 安装离线 deb，再补 `sshd` 用户和最小 `/etc/ssh/sshd_config`。
2. 起 rtunnel：直接 exec `/inspire/hdd/global_public/inspire-skill-bootstrap/v1/rtunnel/linux-<arch>/rtunnel`，把容器 `22222` 暴露给平台 WSS。

两步都不走外网。失败时先看：

- `/tmp/rtunnel-server.log`
- `/tmp/sshd-bootstrap.log`
- `/var/log/dpkg.log` 末尾
- `ps -ef | grep -E '[s]shd -p 22222|[r]tunnel'`

`notebook test` 也失败时的常见原因：

| 现象 | 处理 |
| --- | --- |
| 没能从 `global_public` kit 拿到 rtunnel | 容器里检查 `ls /inspire/hdd/global_public/inspire-skill-bootstrap/v1/rtunnel/linux-amd64/rtunnel`。不存在通常是平台挂载覆盖问题，联系启智平台运维。 |
| `exec format error` / rtunnel 秒退 | kit 中二进制架构不匹配或文件损坏。上报时附 `uname -m` 和 `file /inspire/hdd/global_public/inspire-skill-bootstrap/v1/rtunnel/linux-*/rtunnel`。 |
| `dpkg: error processing archive ...` | 容器已有 openssh 组件且版本冲突，可在 notebook 终端里手动 `dpkg -i --force-overwrite /inspire/hdd/global_public/inspire-skill-bootstrap/v1/sshd-debs/*.deb`。 |
| `Privilege separation user sshd does not exist` | 离线 deb 安装没有跑完整 postinst。CLI bootstrap 会补 `useradd -r -M -d /run/sshd -s /usr/sbin/nologin sshd`。 |
| `/etc/ssh/sshd_config: No such file or directory` | CLI bootstrap 会写最小 config。不要手动写 `Port` / `ListenAddress`，否则会和命令行参数叠加导致 bind 冲突。 |

需要手工复现时，在容器终端里跑：

```bash
KIT=/inspire/hdd/global_public/inspire-skill-bootstrap/v1
ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
RT_BIN="$KIT/rtunnel/linux-$ARCH/rtunnel"

[ -x /usr/sbin/sshd ] || dpkg -i "$KIT/sshd-debs"/*.deb
getent passwd sshd >/dev/null || useradd -r -M -d /run/sshd -s /usr/sbin/nologin sshd
[ -f /etc/ssh/sshd_config ] || printf 'UsePAM no\nStrictModes no\nSubsystem sftp /usr/lib/openssh/sftp-server\n' > /etc/ssh/sshd_config

mkdir -p /run/sshd && ssh-keygen -A >/dev/null 2>&1
/usr/sbin/sshd -p 22222 -o ListenAddress=127.0.0.1 -o PermitRootLogin=yes \
  -o PasswordAuthentication=no -o PubkeyAuthentication=yes

nohup "$RT_BIN" 22222 31337 >/tmp/rtunnel-server.log 2>&1 &
```

之后回本机重跑 `inspire notebook ssh <notebook-name>`。

## 4. Notebook HTTPS proxy 与容器端口

`inspire notebook connections --no-check` 会列出本机已经缓存过的 notebook 连接。人类格式主要用于快速确认缓存名、SSH 用户 / 端口和联网状态；不同安装版本是否展示完整 URL 可能不同。需要稳定读取平台 notebook proxy URL 时，用 JSON：

```bash
inspire --json notebook connections --no-check \
  | jq -r '.data.bridges[] | select(.name == "<notebook-name>").proxy_url'
```

`proxy_url` 通常长这样：

```text
https://<notebook-domain>/ws-<workspace-id>/project-<project-id>/user-<user-id>/<jupyter|vscode>/<notebook-id>/<token>/proxy/<port>/?token=<token>
```

`/proxy/31337/` 是 InspireSkill SSH bootstrap 默认使用的容器内 rtunnel 端口；对应上文手工命令里的 `nohup "$RT_BIN" 22222 31337 ...`。这个 URL 可被本机 `rtunnel` 客户端当作 WebSocket 入口，用来把本机 SSH ProxyCommand 接到容器内 `22222`。

同一个 notebook proxy 也可用于访问容器里已经监听的其它 HTTP 服务：把 URL 里的 `/proxy/31337/` 改成 `/proxy/<container-port>/`，再追加服务路径即可。例如容器里有 OpenAI-compatible 服务监听 `30000` 时，base URL 可写成：

```text
https://<notebook-domain>/ws-.../<jupyter|vscode>/<notebook-id>/<token>/proxy/30000/v1
```

这条路径和 SSH / rtunnel 是两种不同用途：

| 路径 | 适用场景 | 访问方式 |
| --- | --- | --- |
| Notebook HTTPS proxy `/proxy/<port>/` | 给浏览器、OpenAI SDK、Gradio、FastAPI、SGLang、vLLM 等 HTTP 服务提供平台 URL | 走启智 Web 域名、登录态 / 项目权限 / notebook token，并由服务自身决定是否还要 API key |
| SSH rtunnel / ProxyCommand | 让本机 CLI 执行 `ssh`、`scp`、`exec`、`shell` 等运维动作 | 本机 `rtunnel` 客户端经 notebook proxy 接容器内 SSHD |

安全边界要分清：

- 启智登录态、项目权限和 notebook URL token 控制谁能到达 notebook proxy；不要把带 token 的 URL 发到公开渠道。
- notebook proxy 只是网络通路，不等于业务鉴权。对 LLM API、Gradio、FastAPI 等可消费算力或数据的服务，应在服务本身开启 API key、登录或其它应用层鉴权。
- 本机临时 gateway 不应直接绑定 `0.0.0.0` 给小组使用；这会绕开启智访问控制，把安全边界变成本机防火墙和局域网状态。小组共享优先使用 notebook HTTPS proxy，或使用 Tailscale / SSH tunnel 等私有通路。
- 如果服务开启了 API key，验证顺序应包括：无 key 请求返回 `401` 或等价拒绝；带 key 的 `/health`、`/v1/models` 或业务 smoke test 返回成功。

常用排查命令：

```bash
inspire notebook connections --no-check
inspire notebook exec <name> "ss -ltnp | grep ':<container-port>' || true"
inspire notebook exec <name> "curl -sS -o /tmp/probe.out -w '%{http_code}\n' http://127.0.0.1:<container-port>/health"
```

如果本机 `curl https://.../proxy/<port>/...` 因代理、证书或内网网络限制失败，可先用已登录启智的浏览器验证同一个 URL；最终共享给他人前，仍要用服务自身 API key 做一次无 key / 有 key 对照测试。

## 5. 事件与指标观察

`inspire notebook events <name>` 看调度、镜像拉取、容器启动、停止、保存镜像等生命周期原因。notebook 卡在 `PENDING`、`CREATING` 或失败时先看 events。

`inspire notebook metrics <name>` 看平台 `资源视图` 的历史资源曲线，不需要进入容器。适合判断实例是否真的吃到 GPU、CPU / 内存是否贴边、磁盘或网络是否在持续传输。

常用入口：

```bash
inspire notebook events <name> --tail 50
inspire notebook metrics <name> --window 30m
inspire notebook metrics <name> --metric gpu,gpu_mem,cpu,mem --sparkline --no-plot
```

默认 `metrics` 查询 `core` 指标，即 GPU 使用率、GPU 显存、CPU 和内存；`--metric all` 会加上磁盘读写和网络读写。需要给人看趋势时保留默认 PNG 图；只想在终端快速判断时用 `--no-plot --sparkline`。

分工原则：

| 工具 | 主要回答 |
| --- | --- |
| `events` | 平台为什么还没调度、为什么启动失败、生命周期走到哪一步 |
| `metrics` | 资源是否在工作、GPU / CPU / 内存是否打满、I/O 是否还有流量 |
| `exec` / `ssh` | 进容器查进程、日志、文件、应用自身状态 |

终态且不再需要的 notebook 要清理；running notebook 先 stop，再 delete。不确定是否仍有人使用时跳过。失败或卡住时先看 events 和 test 输出，不要凭猜测重复创建同规格实例。

## 6. 代码与文件流转

| 文件流转类型 | 做法 |
| --- | --- |
| 独立 repo 日常同步 | 本地 `git push`，远端 `git pull` |
| 多仓库工作区 | 通过 `inspire init --discover` 配好 `me`，多个 repo 并列放在 `me:<repo>` |
| 非 Git 文件 | `notebook scp`，远端路径优先写 path alias，例如 `me:<repo>/file` |
| 目标计算组不可上网但共享路径可见 | 在同一路径的可上网区 notebook 做 git 操作，离线训练实例只读共享盘结果 |

`notebook scp` 不是源码同步工具。源码走 `git push` + 远端 `git pull`，否则容易慢且不一致。

日常闭环：

```bash
git push origin <branch>
inspire notebook exec <notebook-name> --cwd me:<repo> "git pull && git log -1 --oneline"
inspire notebook ssh <notebook-name> --cwd me:<repo>
inspire notebook exec <notebook-name> --cwd me "hostname"
```

少量非 Git 文件用 alias 传，不要回到绝对路径：

```bash
inspire notebook scp <notebook-name> ./config.yaml me:<repo>/config.yaml
inspire notebook scp <notebook-name> --download me:<repo>/outputs/ ./outputs/ -r
```

大规模 `mv` / `cp` / `rm` 前先探形状：

```bash
ls -A <dir> | wc -l
du -sh --max-depth=1 <dir>
```

按形状选策略：

| 形状 | 策略 |
| --- | --- |
| 顶层 fan-out 大且大小均匀 | `find <root> -mindepth 1 -maxdepth 1 -print0 \| xargs -0 -n 1 -P 16 rm -rf --` |
| 一两个巨型子树 | 下钻一两层再 fan-out，否则并行度实际只有 1 路 |
| 百万级小文件 | 优先 GNU `find -delete` 或 `rsync --delete-after empty/ target/`，减少 fork 和 metadata 压力 |

超过 20 分钟的操作一律 `nohup ... &` + sentinel 文件，本地轮询远端 sentinel；不要让 `notebook exec` 同步挂住。并行度不要无脑拉到 64 以上，GPFS metadata server 是共享资源，`-P 16` 通常已经够。

## 7. 基底 notebook 与镜像

项目刚开始时，建议在可上网 CPU 空间用统一基底镜像起一个基底 notebook，把 Slurm、Ray、分布式训练依赖和项目依赖一次性装好。本文只描述 notebook 内部准备和验证；固化为镜像、设置默认镜像和可见性由 [image-management.md](image-management.md) 负责。

> 下述示例中的 `<GROUP>`、`<WORKSPACE>`、`<IMAGE_URL>` 仅为占位格式。实际值以 `inspire resources specs` 和 `inspire config context` 的实时输出为准。

```bash
inspire notebook create --workspace <WORKSPACE> --group <GROUP> -q 0,20,256 \
  --name cpu-box --image <IMAGE_URL> \
  --project <P> --wait

inspire notebook ssh cpu-box
inspire notebook exec cpu-box "apt-get update && apt-get install -y <deps> && pip install <pkgs>"
```

依赖验证通过后，转到 [image-management.md](image-management.md) 执行 `image save`、确认 `READY`，再按项目需要设置默认镜像。

已有 Ubuntu 镜像需要补 Slurm/Ray 依赖时：

```bash
inspire notebook install-deps <name> --slurm --ray
```

该命令会先 probe 再安装，已存在的组件会跳过。普通 notebook 中 Slurm 命令因无 controller 报错是平台设计，只有 `hpc create` 路径下才注入 controller。
