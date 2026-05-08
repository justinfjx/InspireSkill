from __future__ import annotations

import pytest
from click.testing import CliRunner

from inspire.cli.commands.job import job_commands
from inspire.cli.main import main as cli_main
from inspire.cli.utils import job_shell
from inspire.platform.web.browser_api import jobs as jobs_module


class _FakeSession:
    workspace_id = "ws-default"
    storage_state = {
        "cookies": [
            {"name": "inspire-session", "value": "cookie-v1", "domain": "qz.sii.edu.cn"}
        ]
    }
    cookies = None


def test_list_job_instances_uses_job_id_camel_case(monkeypatch) -> None:  # noqa: ANN001
    captured = {}

    def fake_request_json(session, method, path, *, referer, body=None, timeout=30):  # noqa: ANN001
        captured.update(
            {
                "session": session,
                "method": method,
                "path": path,
                "referer": referer,
                "body": body,
                "timeout": timeout,
            }
        )
        return {"code": 0, "data": {"items": [], "total": 0}}

    monkeypatch.setattr(jobs_module, "_request_json", fake_request_json)

    items, total = jobs_module.list_job_instances(
        "job-abc",
        page_num=2,
        page_size=7,
        session=_FakeSession(),
    )

    assert items == []
    assert total == 0
    assert captured["method"] == "POST"
    assert captured["path"].endswith("/train_job/instance_list")
    assert captured["body"] == {"jobId": "job-abc", "page_num": 2, "page_size": 7}


def test_build_remote_cmd_url_and_headers(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(job_shell, "_get_base_url", lambda: "https://qz.sii.edu.cn")
    monkeypatch.setattr(job_shell, "_browser_api_path", lambda path: f"/api/v1{path}")

    url = job_shell.build_remote_cmd_ws_url("job-abc", "worker-0")
    headers = job_shell.build_remote_cmd_headers(_FakeSession())

    assert url == (
        "wss://qz.sii.edu.cn/api/v1/train_job/remote_cmd?"
        "job_id=job-abc&instance_name=worker-0"
    )
    assert headers["Origin"] == "https://qz.sii.edu.cn"
    assert headers["Cookie"] == "inspire-session=cookie-v1"


def test_select_job_instance_requires_selector_for_multiple_running() -> None:
    instances = job_shell.normalize_job_instances(
        [
            {"name": "worker-0", "instance_status": "instance_running"},
            {"name": "worker-1", "instance_status": "instance_running"},
            {"name": "worker-2", "instance_status": "instance_failed"},
        ]
    )

    with pytest.raises(job_shell.JobShellError, match="Multiple running instances"):
        job_shell.select_job_instance(instances)

    assert job_shell.select_job_instance(instances, pick=2).name == "worker-1"
    assert job_shell.select_job_instance(instances, rank=0).name == "worker-0"
    assert job_shell.select_job_instance(instances, instance_name="worker-1").name == "worker-1"


def test_open_job_shell_retries_once_after_401(monkeypatch) -> None:  # noqa: ANN001
    calls = []
    refreshed = _FakeSession()

    def fake_run_remote_shell(*, session, **kwargs):  # noqa: ANN001
        del kwargs
        calls.append(session)
        if len(calls) == 1:
            raise job_shell.JobShellAuthError("401")
        return 0

    monkeypatch.setattr(job_shell, "run_remote_shell", fake_run_remote_shell)
    monkeypatch.setattr(job_shell, "get_web_session", lambda force_refresh=False: refreshed)

    assert job_shell.open_job_shell(
        job_id="job-abc",
        instance_name="worker-0",
        session=_FakeSession(),
    ) == 0
    assert len(calls) == 2
    assert calls[1] is refreshed


def test_job_shell_command_opens_selected_instance(monkeypatch) -> None:  # noqa: ANN001
    captured = {}

    monkeypatch.setattr(job_commands, "resolve_job_id", lambda ctx, job, **kwargs: "job-abc")
    monkeypatch.setattr(job_commands, "get_web_session", lambda: _FakeSession())

    def fake_list_job_instances(job_id, *, page_num, page_size, session):  # noqa: ANN001
        captured["list"] = {
            "job_id": job_id,
            "page_num": page_num,
            "page_size": page_size,
            "session": session,
        }
        return (
            [
                {"name": "worker-0", "instance_status": "instance_running"},
                {"name": "worker-1", "instance_status": "instance_running"},
            ],
            2,
        )

    def fake_open_job_shell(*, job_id, instance_name, session):  # noqa: ANN001
        captured["shell"] = {
            "job_id": job_id,
            "instance_name": instance_name,
            "session": session,
        }
        return 0

    monkeypatch.setattr(job_commands.browser_api_module, "list_job_instances", fake_list_job_instances)
    monkeypatch.setattr(job_commands, "open_job_shell", fake_open_job_shell)
    monkeypatch.setattr(job_commands, "_close_web_client", lambda: None)

    result = CliRunner().invoke(cli_main, ["job", "shell", "train-a", "--pick", "2"])

    assert result.exit_code == 0, result.output
    assert captured["list"]["job_id"] == "job-abc"
    assert captured["shell"]["job_id"] == "job-abc"
    assert captured["shell"]["instance_name"] == "worker-1"
    assert "Press Ctrl-]" in result.output


def test_job_shell_command_rejects_multiple_selectors() -> None:
    result = CliRunner().invoke(
        cli_main,
        ["job", "shell", "train-a", "--rank", "0", "--pick", "1"],
    )

    assert result.exit_code != 0
    assert "Use only one of --rank, --instance, or --pick" in result.output
