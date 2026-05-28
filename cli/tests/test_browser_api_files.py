from __future__ import annotations

from typing import Any

from inspire.platform.web.browser_api import files as files_module


class _FakeSession:
    workspace_id = "ws-default"


def test_list_system_storage_types_posts_workspace_filter(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, Any] = {}

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
        return {
            "code": 0,
            "data": {
                "system_storages": [
                    {"name": "hdd", "cluster_id": "cluster-stg-id-1", "is_primary": True}
                ]
            },
        }

    monkeypatch.setattr(files_module, "_request_json", fake_request_json)

    storages = files_module.list_system_storage_types(
        workspace_id="ws-x",
        session=_FakeSession(),
    )

    assert storages[0].name == "hdd"
    assert storages[0].cluster_id == "cluster-stg-id-1"
    assert storages[0].is_primary is True
    assert captured["method"] == "POST"
    assert captured["path"].endswith("/file/get_system_storage_type_list")
    assert captured["referer"].endswith("/jobs/files?spaceId=ws-x")
    assert captured["body"] == {"filter": {"workspace_id": "ws-x"}}


def test_list_file_directories_posts_frontend_directory_filter(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, Any] = {}

    def fake_request_json(session, method, path, *, referer, body=None, timeout=30):  # noqa: ANN001
        captured.update(
            {
                "method": method,
                "path": path,
                "referer": referer,
                "body": body,
            }
        )
        return {
            "code": 0,
            "data": {
                "files": [
                    {
                        "name": "CI-情境智能",
                        "directory": "/inspire/hdd/project/embodied-multimodality/public",
                        "is_share": 0,
                    }
                ]
            },
        }

    monkeypatch.setattr(files_module, "_request_json", fake_request_json)

    entries = files_module.list_file_directories(
        workspace_id="ws-x",
        storage_type="hdd",
        cluster_id="cluster-stg-id-1",
        name="project",
        session=_FakeSession(),
    )

    assert entries[0].directory == "/inspire/hdd/project/embodied-multimodality/public"
    assert captured["method"] == "POST"
    assert captured["path"].endswith("/file/dir/list")
    assert captured["referer"].endswith("/jobs/files?spaceId=ws-x")
    assert captured["body"] == {
        "filter": {
            "workspace_id": "ws-x",
            "system_storage_type": "hdd",
            "cluster_id": "cluster-stg-id-1",
            "name": "project",
        }
    }


def test_file_directory_info_accepts_boolean_is_share() -> None:
    entry = files_module.FileDirectoryInfo.from_api_response(
        {
            "name": "Demo",
            "directory": "/inspire/hdd/project/topic-a/user-a",
            "is_share": True,
        }
    )

    assert entry.is_share == 1


def test_get_sftpgo_connection_info_posts_storage_name(monkeypatch) -> None:  # noqa: ANN001
    captured: dict[str, Any] = {}

    def fake_request_json(session, method, path, *, referer, body=None, timeout=30):  # noqa: ANN001
        captured.update(
            {
                "method": method,
                "path": path,
                "referer": referer,
                "body": body,
            }
        )
        return {
            "code": 0,
            "data": {
                "address": "https://file-server.sii.edu.cn",
                "auth": "BasicOpaque",
                "webdav_port": 81,
            },
        }

    monkeypatch.setattr(files_module, "_request_json", fake_request_json)

    info = files_module.get_sftpgo_connection_info(
        storage_name="HDD",
        usage="download",
        session=_FakeSession(),
    )

    assert info.address == "https://file-server.sii.edu.cn"
    assert info.auth == "BasicOpaque"
    assert info.webdav_port == 81
    assert captured["method"] == "POST"
    assert captured["path"].endswith("/file/sftpgo/connection_info")
    assert captured["referer"].endswith("/jobs/files")
    assert captured["body"] == {"storage_name": "hdd", "usage": "download"}


def test_list_project_file_directories_fans_out_across_non_share_storages(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        files_module,
        "list_system_storage_types",
        lambda **_: [
            files_module.SystemStorageInfo(
                name="hdd",
                cluster_id="cluster-stg-id-1",
                is_primary=True,
            ),
            files_module.SystemStorageInfo(
                name="share-hdd",
                cluster_id="",
                is_primary=False,
            ),
            files_module.SystemStorageInfo(
                name="ssd",
                cluster_id="cluster-stg-id-2",
                is_primary=False,
            ),
        ],
    )
    calls: list[tuple[str, str]] = []

    def fake_list_file_directories(**kwargs: object) -> list[files_module.FileDirectoryInfo]:
        calls.append((str(kwargs["storage_type"]), str(kwargs.get("cluster_id") or "")))
        return [
            files_module.FileDirectoryInfo(
                name="Demo",
                directory=f"/inspire/{kwargs['storage_type']}/project/topic-a/public",
            )
        ]

    monkeypatch.setattr(files_module, "list_file_directories", fake_list_file_directories)

    entries = files_module.list_project_file_directories(
        workspace_id="ws-x",
        session=_FakeSession(),
    )

    assert calls == [("hdd", "cluster-stg-id-1"), ("ssd", "cluster-stg-id-2")]
    assert [entry.directory for entry in entries] == [
        "/inspire/hdd/project/topic-a/public",
        "/inspire/ssd/project/topic-a/public",
    ]
