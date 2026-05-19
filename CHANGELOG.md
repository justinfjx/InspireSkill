# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的记录结构，版本号遵循语义化版本风格。未发布变更先进入 `Unreleased`，发布时再归档到具体版本。

## Unreleased

当前无未发布变更。

## 5.1.14（2026-05-19）

### Fixed

- 临时兼容 Ubuntu 22.04 / `jammy` Notebook 的 SSH bootstrap：已存在的 22.04 OpenSSH 会被直接接受；缺失 OpenSSH 或检测到 24.04 OpenSSH 时，会通过 apt 联网安装 / 降级到 22.04 OpenSSH，覆盖 `paper-repro:v2` 这类镜像的 SSH 配置路径。该分支要求 notebook 位于可上网区，失败时会给出明确错误和远端日志路径。

## 5.1.13（2026-05-19）

### Fixed

- 修复多账号在同一工作区切换时复用旧项目配置的问题：项目级配置现在按活动账号写入 `./.inspire/accounts/<account>/config.toml`，避免 workspace、path alias 和 workload profile 在不同账号之间串用。
- 修复同一进程内多次 `inspire account use` 后可能继续使用旧账号运行时缓存的问题：OpenAPI token/client、Browser API base URL / prefix 和资源 availability 进程缓存会随账号切换刷新。
- 修复 Web session 过期刷新时误清其它账号登录缓存的问题：默认只清当前账号的 `web_session.json`，保留被切走账号的登录态，方便快速切回。
- 修复 Notebook rtunnel proxy state 的账号隔离边界：真实账号 alias 使用 `~/.inspire/accounts/<account>/rtunnel-proxy-state.json`，Notebook SSH bridges 和 Web session 继续保留在同一账号目录；切换账号不会删除被切走账号的本地缓存。

## 5.1.11（2026-05-17）

### Changed

- 同步 SII 内部源文档：更新 PIP / PyPI、Conda、npm、Maven、PyTorch wheel、Docker 镜像仓库、OSS 和 NTP 的 Agent 可执行入口。
- 收敛内部源说明边界：根 `SKILL.md` 继续只保留公网 / 内部源判断原则，具体地址集中在 `references/resources-and-paths.md`，避免日常入口过重。
- 更新 notebook 基底环境示例，使用新的 PyPI 内部源配置路径。

## 5.1.10（2026-05-13）

### Fixed

- 修复部分可上网 GPU Notebook 自定义镜像缺失 fontconfig 配置时，Chromium 能启动但在启智登录成功后渲染 SPA 过程中崩溃，导致 `inspire init` 报 `Playwright Chromium closed during Inspire login` 的问题。登录流程现在在认证 cookie 可用后立即通过 Browser API 捕获 session 和 workspace 列表，不再依赖完整渲染启智前端页面。

## 5.1.9（2026-05-13）

### Fixed

- 修复 `inspire init` 在 Notebook 容器首次接受 Playwright 系统依赖安装后，仍转入 username / password 重新确认提示的问题。现在浏览器运行时修复完成后会直接使用原账号配置刷新 Web session，只有真实账号或 session 失败时才提示重新确认登录信息。

## 5.1.8（2026-05-13）

### Fixed

- 收紧 Playwright 系统依赖安装边界：安装器和 `inspire account add` 不再主动运行 `playwright install --with-deps chromium`，避免在已有镜像环境中无提示改动 apt 层；它们只预装浏览器二进制并做启动探测。
- `inspire init` 仍会在 Chromium 无法启动时提示安装 Linux 系统依赖，只有用户确认后才运行 `--with-deps` 修复。已有可用 Playwright / Chromium 运行时会被 launch probe 识别并直接复用。

## 5.1.7（2026-05-13）

### Fixed

- 修复启智 Notebook 的最小 Ubuntu 镜像内安装 InspireSkill 后，`inspire init` 因 Playwright Chromium 缺少 `libglib-2.0.so.0` 等系统动态库而在 `BrowserType.launch` 阶段失败的问题。Linux root + `apt-get` 环境下，安装器、`account add` 和 `init` 的浏览器修复路径现在会使用 `playwright install --with-deps chromium`。
- 改善 Playwright 浏览器启动失败诊断：当 Chromium 可执行文件缺失或系统依赖缺失时，`inspire init` 会给出可执行的修复命令，并在交互初始化路径中重新尝试安装浏览器运行时。

## 5.1.6（2026-05-13）

### Fixed

- 修复启智 Notebook 容器内运行 `inspire init` 时，Playwright Chromium 在 `page.goto()` 阶段关闭并报 `Target page, context or browser has been closed` 的问题。所有 CLI Playwright 启动入口现在统一带上容器兼容参数，覆盖 root/no sandbox 和小 `/dev/shm` 环境。
- 登录浏览器仍异常关闭时，CLI 现在会给出浏览器运行时 / 容器环境诊断，不再直接暴露 Playwright 底层 `Page.goto` 错误，也不再把这类失败误导成账号密码问题。

## 5.1.5（2026-05-13）

### Fixed

- 修复 `inspire init` 在账号 Web session 失效后重新登录时只提示密码、不允许修正平台登录 username 的问题。现在重新登录会确认 `auth.username` 是否为登录 ID（手机号、学号 / 工号或邮箱等），并在登录成功后把确认后的 username 和密码写回当前账号配置。
- 改善账号初始化提示、登录失败错误和安装配置文档，明确 `INSPIRE_USERNAME` / `auth.username` 必须是平台登录 ID，不是网页显示名；在启智 Notebook 容器内安装时仍需要独立生成 CLI Web session，不会继承打开 Notebook 的浏览器 SSO 登录态。

## 5.1.4（2026-05-12）

### Changed

- 统一 CLI 查询命令边界：删除历史分页暴露，统一使用 `--limit/-n`；`resources specs` 收敛为各 workload 的 `quota` 命令；查询类 `--group` 明确支持 keyword / substring，操作类 `--group` 继续要求完整 compute group 名称。
- 统一 CLI 操作命令边界：操作命令只接受单一明确 workspace，不再接受 `all`、`current` 或 raw workspace ID；删除 command-local `--json`，统一使用全局 `inspire --json ...`；删除类命令统一为 `--yes/-y`。
- 收紧 workload create / batch 参数：`--profile` 与显式调度条件互斥，batch defaults 与 item 合并后同样校验；Ray create 删除 `--head-*`，统一使用普通 head 条件参数，并严格校验 repeatable `--worker` schema。
- 收紧边角命令参数：`notebook shell` 和 `notebook ssh test` 不再依赖隐式缓存目标；`image save` 必须显式传 `--workspace`；`image` 可见性统一为 `--visibility private|public`；`init --global/--project` 改为 `--scope project|global`。
- 将 quota 从 `resources` 命名空间拆出到 `notebook quota`、`job quota`、`hpc quota`、`ray quota` 和 `serving quota`，避免把配额语义混进资源节点查询。

### Fixed

- 测试套件全局禁用 CLI 启动阶段的后台 update check，避免 CI 中反复调用 CLI 时派生大量孤儿 Python 进程并拖挂 Python 3.12 作业。
- CI 恢复普通 `uv run pytest -q` 执行路径，并保留 job 级超时保护。

## 5.1.3（2026-05-11）

### Changed

- 清扫 Agent 手册和 references 的上下文污染：移除内部源说明网址残留、旧 project 元数据提示，以及“为了说明没用而提到没用入口”的文档内容。
- Clarify internal mirror usage and `image save` workflow: 内部源可以优先在目标 notebook 中按实际可达性配置，依赖跑通后仍应保存镜像；保存过程中 notebook 暂不可操作，保存完毕后不会自动停止。
- 统一本地文档和记忆里的操作者叫法：泛指操作者、读者、命令消费者和维护执行者时统一写 `Agent`；平台登录实体、权限主体和 API 字段按技术语义写“账号”、`user_id`、`username`、`/user/detail` 等。
- 将开发原则维护进 `CONTRIBUTING.md`，覆盖事实来源、Name-only 合同、配置边界、平台 workflow、文档边界、验证和交付要求。

## 4.1.4（2026-05-09）

### Changed

- 收紧 Browser API 开发文档，只保留当前仓库已闭合的 wrapper / helper / CLI 合同。

## 4.1.3（2026-05-09）

### Fixed

- `uv tool` 更新路径增加 package index refresh，避免 PyPI 已发布新版本但本地 `uv` 缓存仍返回旧版本。
- 安装脚本的 `uv tool install` 同样强制刷新索引，保证重装路径和 `inspire update` 行为一致。

## 4.1.2（2026-05-09）

### Fixed

- 强化 `inspire update` 的全局更新路径：从本地 checkout 或 repo venv 运行时，也会更新 `uv tool` / `pipx` 管理的全局 `inspire`。
- `uv tool` 安装源如果残留为本地 `file://` 路径，`inspire update` 会重置为官方 PyPI 包，避免开发机路径污染全局安装。
- `inspire update` 完成后会验证全局 executable、agent skill 目录和旧 `INSPIRE_TARGET_DIR` / 长环境前缀残留，避免 CLI 最新但 Agent 仍读取旧文档。
- CLI 最新版本检查改为以 PyPI 发布版本为主，GitHub `main` 只作为网络或包索引失败时的 fallback。

## 4.1.0（2026-05-08）

### Added

- 新增 pre-commit 配置，用于提交前检查 YAML、TOML、合并冲突、大文件、行尾和 Ruff 关键错误。
- 新增 GitHub Issue 模板、Pull Request 模板、贡献指南、CI workflow 和 mypy 检查入口，补齐基础协作入口。
- 新增 `inspire job shell`，支持进入 running training job 实例，包含 `--rank`、`--instance` 和 `--pick` 选择器。

### Changed

- `inspire init` 默认进入 discover 流程；首次没有账号时会内联创建 `default` 账号并继续初始化。
- `scripts/install.sh` 安装 CLI 后会尽量自动安装 Playwright Chromium，减少首次 SSO 登录的中断。
- `inspire job create` 的远端日志包装改为 `tee`，同时保留网页 stdout/stderr 和共享盘日志文件，并默认设置 `PYTHONUNBUFFERED=1`。

### Fixed

- `inspire notebook exec` 在没有项目远端路径配置时回落到远端默认登录目录，不再要求 `INSPIRE_TARGET_DIR`。
- `inspire notebook ssh --command` 现在转发本机 stdin，支持管道输入到远端命令。
- `inspire notebook scp`、`notebook connections` 和 `ssh --command` 共用 active account 的 tunnel cache。

## 4.0.0

### Added

- 发布面向 Inspire 平台的 agent-native CLI，覆盖 notebook 生命周期、作业提交、资源查询、SSH、镜像和路径操作。
