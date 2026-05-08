# Contributing

感谢你改进 InspireSkill。这个仓库同时面向人类用户和 AI Agent，因此每个变更都要尽量保持命令行为可复现、输出语义清晰、文档与 CLI help 一致。

## 开发环境

CLI 工程在 `cli/` 目录内，推荐使用 `uv`：

```bash
cd cli
uv sync --dev
uv run inspire --help
```

安装提交前检查：

```bash
uv run pre-commit install --config ../.pre-commit-config.yaml
```

如需手动运行全部已配置检查：

```bash
uv run pre-commit run --config ../.pre-commit-config.yaml --all-files
```

## 提交前检查

常规变更至少运行：

```bash
cd cli
uv run pytest -q
uv run ruff check inspire tests --select E9,F63,F7,F82
uv run mypy
uv build
```

当前 Ruff 在 CI 中只启用关键错误 baseline，mypy 以非阻断 baseline 运行，避免历史风格债或类型债阻断所有 PR。不要在无关 PR 中引入全仓格式化；如果要扩大 lint 或 typing 覆盖，请单独提交并说明迁移范围。

## 变更要求

- 不要修改与任务无关的 CLI runtime 代码。
- 不要提交本地账号、代理、日志、缓存、构建产物或临时文件。
- 面向 Agent 的输出应默认保持人类可读，不暴露低价值 raw ID；脚本接口使用 `--json`。
- 新增或修改命令行为时，同步更新测试，并以 `inspire --help`、`inspire <command-group> --help` 或更具体 help 作为命令表面的事实来源。
- 中文文档使用全角中文标点；中文与英文、数字、公式相邻时保留半角空格。

## Pull Request

PR 描述应包含：

- 变更目的和影响范围。
- 已运行的验证命令及结果。
- 是否涉及 live Inspire 平台资源；如果涉及，说明创建对象、清理状态和残留风险。

CI 会运行单元测试、Ruff 关键错误检查、非阻断 mypy baseline 和构建验证。后续收紧 mypy 时，应单独说明迁移范围。
