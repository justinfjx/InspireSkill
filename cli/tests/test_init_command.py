from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from inspire.cli.context import EXIT_GENERAL_ERROR, EXIT_SUCCESS
from inspire.cli.commands.init import discover as discover_module
from inspire.cli.commands.init import init_cmd as init_cmd_module
from inspire.cli.main import main as cli_main
from inspire.config import Config


def test_init_template_project_succeeds_with_active_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    account_config_path = tmp_path / "accounts" / "alice" / "config.toml"
    monkeypatch.setattr(
        Config,
        "writable_config_path",
        classmethod(lambda cls: account_config_path),
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, ["init", "--template", "--scope", "project", "--force"])

    project_config = repo_dir / ".inspire" / "config.toml"
    assert result.exit_code == EXIT_SUCCESS
    assert project_config.exists()
    assert "Inspire CLI Configuration" in project_config.read_text(encoding="utf-8")


def test_init_fails_fast_when_no_active_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    monkeypatch.setattr(
        Config,
        "writable_config_path",
        classmethod(lambda cls: None),
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, ["init", "--template", "--scope", "project", "--force"])

    assert result.exit_code == EXIT_GENERAL_ERROR
    assert "No active account configured. Run `inspire account add` first." in result.output
    assert not (repo_dir / ".inspire" / "config.toml").exists()


def test_init_defaults_to_discover_mode_with_active_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)

    account_config_path = tmp_path / "accounts" / "alice" / "config.toml"
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        Config,
        "writable_config_path",
        classmethod(lambda cls: account_config_path),
    )
    monkeypatch.setattr(
        init_cmd_module,
        "snapshot_paths",
        lambda global_path, project_path: {"global": global_path, "project": project_path},
    )
    monkeypatch.setattr(init_cmd_module, "current_account", lambda: "alice")
    monkeypatch.setattr(init_cmd_module, "list_accounts", lambda: ["alice"])

    def fake_run_init_action(func, effective_json, force, **kwargs):  # noqa: ANN001
        calls["func"] = func
        calls["json"] = effective_json
        calls["force"] = force
        calls["kwargs"] = kwargs

    monkeypatch.setattr(init_cmd_module, "run_init_action", fake_run_init_action)
    monkeypatch.setattr(init_cmd_module, "emit_init_json", lambda **kwargs: None)

    runner = CliRunner()
    result = runner.invoke(cli_main, ["init", "--force"])

    assert result.exit_code == EXIT_SUCCESS, result.output
    assert calls["func"] is init_cmd_module._init_discover_mode
    assert calls["force"] is True


def test_init_bootstraps_first_account_before_discover(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("HOME", str(tmp_path))

    calls: dict[str, object] = {}
    monkeypatch.setattr(init_cmd_module, "normalize_environment", lambda **kwargs: None)
    monkeypatch.setattr(init_cmd_module, "snapshot_paths", lambda *args, **kwargs: {})
    monkeypatch.setattr(init_cmd_module, "emit_init_json", lambda **kwargs: None)

    def fake_run_init_action(func, effective_json, force, **kwargs):  # noqa: ANN001
        calls["func"] = func
        calls["kwargs"] = kwargs

    monkeypatch.setattr(init_cmd_module, "run_init_action", fake_run_init_action)

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["init", "--force", "--username", "zillionx", "--base-url", "https://qz.sii.edu.cn"],
        input="\nsecret\nsecret\n\n",
    )

    assert result.exit_code == EXIT_SUCCESS, result.output
    assert "Creating the first account" in result.output
    assert "Active account: default" in result.output
    assert calls["func"] is init_cmd_module._init_discover_mode
    assert (tmp_path / ".inspire" / "current").read_text(encoding="utf-8") == "default\n"
    account_config = (
        tmp_path / ".inspire" / "accounts" / "default" / "config.toml"
    ).read_text(encoding="utf-8")
    assert 'username = "zillionx"' in account_config
    assert 'base_url = "https://qz.sii.edu.cn"' in account_config


def test_discover_relogin_confirms_configured_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = type(
        "Cfg",
        (),
        {
            "username": "仝",
            "password": "",
            "base_url": "https://qz.sii.edu.cn",
        },
    )()
    prompts: list[tuple[str, object]] = []

    def fake_prompt(text: str, **kwargs):  # noqa: ANN001
        prompts.append((text, kwargs.get("default")))
        if text.startswith("Platform login username"):
            return "253108120116"
        if text == "Password":
            return "secret"
        raise AssertionError(f"unexpected prompt: {text}")

    monkeypatch.setattr(discover_module.click, "prompt", fake_prompt)

    username, password, base_url = discover_module._resolve_credentials_interactive(
        cfg,
        cli_username=None,
        cli_base_url=None,
        confirm_config_username=True,
    )

    assert username == "253108120116"
    assert password == "secret"
    assert base_url == "https://qz.sii.edu.cn"
    assert prompts[0] == ("Platform login username (login ID, not display name)", "仝")


def test_persist_prompted_credentials_updates_auth_username() -> None:
    global_data = {
        "auth": {"username": "仝"},
        "api": {"base_url": "https://qz.sii.edu.cn"},
    }
    account_section = {"password": "old-secret"}

    discover_module._persist_prompted_credentials(
        global_data=global_data,
        account_section=account_section,
        prompted_credentials=(
            "253108120116",
            "new-secret",
            "https://qz.sii.edu.cn",
        ),
    )

    assert global_data["auth"]["username"] == "253108120116"
    assert global_data["auth"]["password"] == "new-secret"
    assert global_data["api"]["base_url"] == "https://qz.sii.edu.cn"
    assert "password" not in account_section
