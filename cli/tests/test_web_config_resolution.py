"""Tests for web-facing config resolution helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from inspire.cli.utils.notebook_cli import get_base_url
from inspire.platform.web.browser_api.notebooks import _config_compute_groups_fallback


def test_notebook_cli_base_url_reads_account_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v4.0.0: base_url is account-scope.

    With env unset, ``get_base_url()`` returns the active account's
    stored ``[api].base_url``. Project layer cannot carry account-scope
    keys (loader rejects them), so prefer_source no longer applies here.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    account_dir = fake_home / ".inspire" / "accounts" / "alice"
    account_dir.mkdir(parents=True)
    (account_dir / "config.toml").write_text(
        '[auth]\nusername = "alice"\npassword = "pw"\n'
        '[api]\nbase_url = "https://account.example"\n'
    )
    (fake_home / ".inspire" / "current").write_text("alice\n")

    project_dir = tmp_path / "repo" / ".inspire"
    project_dir.mkdir(parents=True)
    (project_dir / "config.toml").write_text("")
    monkeypatch.chdir(tmp_path / "repo")
    monkeypatch.delenv("INSPIRE_BASE_URL", raising=False)

    assert get_base_url() == "https://account.example"


def test_notebook_compute_group_fallback_uses_layered_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / ".inspire"
    project_dir.mkdir()
    (project_dir / "config.toml").write_text(
        """
[[compute_groups]]
name = "H200 A"
id = "lcg-test-1"
gpu_type = "H200"
"""
    )
    monkeypatch.chdir(tmp_path)

    groups = _config_compute_groups_fallback()

    assert len(groups) == 1
    assert groups[0]["logic_compute_group_id"] == "lcg-test-1"
    assert groups[0]["name"] == "H200 A"
