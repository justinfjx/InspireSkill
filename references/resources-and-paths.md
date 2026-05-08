# 资源、规格与远端路径

## 什么时候加载

当任务需要选择 workspace、compute group、`--quota` 三元组、项目配额、远端共享盘路径，或需要解释为什么某个路径在实例里不可见时，加载本文档。

## 1. 资源查询入口

资源、规格、项目和用户相关能力以 CLI help 为准，不在 Agent 文档里维护硬编码清单。

```bash
inspire resources --help
inspire resources specs --help
inspire project --help
inspire user --help
```

日常先看 resources 的 human 表格，再按需锁定 workload、workspace 或 compute group。看项目预算和配额时使用 project 入口；确认当前身份、workspace 权限码或 API Key 元数据时使用 user 入口。

Agent 默认读取人类表格。结构化输出只用于脚本，不作为日常观察面。

## 2. 规格三元组

`--quota` / `-q` 的格式是：

```bash
<gpu>,<cpu>,<mem>
```

`mem` 以 GiB 计。例如 `1,20,200` 表示 $$1$$ 张 GPU、$$20$$ 核 CPU、$$200$$ GiB 内存；CPU-only 写 `0,4,32`。

GPU 型号由 workspace 和 compute group 决定，不写进三元组。三元组必须在当前可见规格里唯一匹配；如果多组撞上同一三元组，加 `--group <name>` 或命令对应的 compute group 参数。

## 3. 远端路径作用域

先决定作用域，再选存储池。

| 作用域 | 路径样例 | 定位 |
| --- | --- | --- |
| 项目个人 | `/inspire/<tier>/project/<topic>/<user>/...` | 每项目、每用户一份。适合代码、脚本、配置、调试输出 |
| 项目公共 | `/inspire/<tier>/project/<topic>/public/...` | 项目成员共享。适合数据集、权重、批量结果、checkpoint |
| 全局个人 | `/inspire/hdd/global_user/<user>/...` | 仅 hdd。跨项目个人盘，适合脚本、配置、小工具和跨项目小文件中转 |
| 全局公共 | `/inspire/hdd/global_public/...` | 仅 hdd。全平台共享，普通用户只读，稳定共享物由维护者统一放置 |

## 4. 存储池

| 池 | 项目路径前缀 | 定位 |
| --- | --- | --- |
| SSD `gpfs_flash` | `/inspire/ssd/project/<topic>/` | 训练 hot path、活跃工作集、checkpoint 热点 |
| HDD `gpfs_hdd` | `/inspire/hdd/project/<topic>/` | 通用空间，写前看剩余容量 |
| qb-ilm `qb_prod_ipfs01` | `/inspire/qb-ilm/project/<topic>/` | 大容量，顺序读带宽接近 SSD |
| qb-ilm2 `qb_prod_ipfs02` | `/inspire/qb-ilm2/project/<topic>/` | 新且空余多，新增大数据默认优先考虑 |

`global_*` 只在 hdd。需要 SSD 或 qb-ilm 速度时，走项目个人或项目公共路径。

## 5. 挂载隔离

实例只挂自身所在项目的 fileset。其它项目的 `/inspire/{hdd,ssd,qb-ilm,qb-ilm2}/project/<others>/` 在该实例里通常不存在，`ls` 报 `No such file` 不是权限问题。

跨项目搬小文件时，在两个项目各起一个 notebook，用 `/inspire/hdd/global_user/<user>/` 中转。大数据集或全量 checkpoint 超出个人 quota 时，联系项目管理员处理。

## 6. 路径配置入口

项目远端路径由 `inspire init --discover` 写入当前仓库的 `.inspire/config.toml`。查看生效配置用：

```bash
inspire config show --compact
inspire config context
```

不要把配置文件内容复制到 Agent 文档里；仓库级语义说明写在 `INSPIRE.md`。

## 7. 项目、负责人和用户元数据

日常看配额、预算和优先级时先查 `inspire project --help`，更细的项目详情和负责人下拉只在确认归属或预算拆分时使用。当前登录身份、workspace 权限码、用户级配额和 API Key 元数据从 `inspire user --help` 选择对应子命令；用户级配额普通账号通常不可用，失败时改看项目列表。

API Key 值只在创建时一次性下发；创建 / 删除走 Web UI `/userCenter`。
