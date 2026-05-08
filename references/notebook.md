# Notebook 工作流

## 什么时候加载

当任务需要创建 notebook、SSH 连接、远程执行、传文件、保存镜像、安装 Slurm/Ray 依赖，或判断 `shell` 与 `exec` 的差异时，加载本文档。

## 1. CLI help 查询

notebook 子命令、参数和功能说明以 CLI help 为准，不在 Agent 文档里维护速查表。

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
inspire notebook exec <name> "cd <repo> && export X=1 && ./run.sh"
```

超过 $$20$$ 分钟的任务写成远端后台进程和 sentinel 文件，再从本机轮询，不要让 `exec` 同步等待。

## 3. SSH bootstrap

`inspire notebook ssh <name>` 对任何镜像、计算组和公网状态都应可用。CLI 会在容器里启动 sshd 和 rtunnel，通路缓存到本地。

冷启动时间很贵时，可以 `image save` 派生镜像固化环境；一次性任务用完即弃即可。

CLI 在容器内跑 bootstrap shell 做两件事：

1. 起 sshd：如果 `/usr/sbin/sshd` 不在，先从 `/inspire/hdd/global_public/inspire-skill-bootstrap/v1/sshd-debs/` 安装离线 deb，再补 `sshd` 用户和最小 `/etc/ssh/sshd_config`。
2. 起 rtunnel：直接 exec `/inspire/hdd/global_public/inspire-skill-bootstrap/v1/rtunnel/linux-<arch>/rtunnel`，把容器 `22222` 暴露给平台 WSS。

两步都不走外网。失败时先看：

- `/tmp/rtunnel-server.log`
- `/tmp/sshd-bootstrap.log`
- `/var/log/dpkg.log` 末尾
- `ps -ef | grep -E '[s]shd -p 22222|[r]tunnel'`

常见现象：

| 现象 | 处理 |
| --- | --- |
| 没能从 `global_public` kit 拿到 rtunnel | 容器里检查 `ls /inspire/hdd/global_public/inspire-skill-bootstrap/v1/rtunnel/linux-amd64/rtunnel`。不存在通常是平台挂载覆盖问题，找 SII 运维。 |
| `exec format error` / rtunnel 秒退 | kit 中二进制架构不匹配或文件损坏。提 issue 时附 `uname -m` 和 `file /inspire/hdd/global_public/inspire-skill-bootstrap/v1/rtunnel/linux-*/rtunnel`。 |
| `dpkg: error processing archive ...` | 容器已有 openssh 组件且版本冲突，可在 Web 终端里手动 `dpkg -i --force-overwrite /inspire/hdd/global_public/inspire-skill-bootstrap/v1/sshd-debs/*.deb`。 |
| `Privilege separation user sshd does not exist` | 离线 deb 安装没有跑完整 postinst。CLI bootstrap 会补 `useradd -r -M -d /run/sshd -s /usr/sbin/nologin sshd`。 |
| `/etc/ssh/sshd_config: No such file or directory` | CLI bootstrap 会写最小 config。不要手动写 `Port` / `ListenAddress`，否则会和命令行参数叠加导致 bind 冲突。 |

需要手工复现时，在容器 Web 终端里跑：

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

## 4. 代码与文件流转

| 文件流转类型 | 做法 |
| --- | --- |
| 独立 repo 日常同步 | 本地 `git push`，远端 `git pull` |
| 多仓库工作区 | 通过 `inspire init --discover` 配好项目远端工作目录，多个 repo 并列放置 |
| 非 Git 文件 | `notebook scp`，远端路径优先写绝对路径 |
| 目标计算组不可上网但共享路径可见 | 在同一路径的可上网区 notebook 做 git 操作，离线训练实例只读共享盘结果 |

`notebook scp` 不是源码同步工具。源码走 `git push` + 远端 `git pull`，否则容易慢且不一致。

日常闭环：

```bash
git push origin <branch>
inspire notebook exec <notebook-name> "cd <repo> && git pull && git log -1 --oneline"
inspire notebook ssh <notebook-name>
inspire notebook exec <notebook-name> "hostname"
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
| 一两个巨型子树 | 下钻一两层再 fan-out，否则并行度实际只有 $$1$$ 路 |
| 百万级小文件 | 优先 GNU `find -delete` 或 `rsync --delete-after empty/ target/`，减少 fork 和 metadata 压力 |

超过 $$20$$ 分钟的操作一律 `nohup ... &` + sentinel 文件，本地轮询远端 sentinel；不要让 `notebook exec` 同步挂住。并行度不要无脑拉到 $$64$$ 以上，GPFS metadata server 是共享资源，`-P 16` 通常已经够。

## 5. 基底 notebook 与镜像

项目刚开始时，建议在可上网 CPU 空间用 `docker.sii.shaipower.online/inspire-studio/unified-base:v2` 起一个基底 notebook，把 Slurm、Ray、分布式训练依赖和项目依赖一次性装好，再保存成项目通用镜像。

```bash
inspire notebook create --workspace CPU资源空间 --group CPU资源-2 -q 0,20,256 \
  --name cpu-box --image docker.sii.shaipower.online/inspire-studio/unified-base:v2 \
  --project <P> --wait

inspire notebook ssh cpu-box
inspire notebook exec cpu-box "apt-get update && apt-get install -y <deps> && pip install <pkgs>"
inspire image save cpu-box -n <img> -v v1 --public --wait
inspire image set-default --job <URL> --notebook <URL>
```

已有 Ubuntu 镜像需要补 Slurm/Ray 依赖时：

```bash
inspire notebook install-deps <name> --slurm --ray
```

该命令会先 probe 再安装，已存在的组件会跳过。普通 notebook 中 Slurm 命令因无 controller 报错是平台设计，只有 `hpc create` 路径下才注入 controller。
