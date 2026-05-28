"""Browser (web-session) APIs for the web UI file browser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from inspire.platform.web.browser_api.core import _browser_api_path, _get_base_url, _request_json
from inspire.platform.web.session import WebSession, get_web_session

__all__ = [
    "FileDirectoryInfo",
    "SystemStorageInfo",
    "WebDAVConnectionInfo",
    "get_sftpgo_connection_info",
    "list_file_directories",
    "list_project_file_directories",
    "list_system_storage_types",
]


@dataclass
class SystemStorageInfo:
    """Storage entry exposed by the file browser."""

    name: str
    cluster_id: str = ""
    is_primary: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "SystemStorageInfo":
        return cls(
            name=str(data.get("name") or "").strip(),
            cluster_id=str(data.get("cluster_id") or "").strip(),
            is_primary=bool(data.get("is_primary", False)),
            raw=dict(data),
        )


@dataclass
class FileDirectoryInfo:
    """Top-level directory entry returned by the file browser."""

    name: str
    directory: str
    is_share: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "FileDirectoryInfo":
        return cls(
            name=str(data.get("name") or "").strip(),
            directory=str(data.get("directory") or "").strip(),
            is_share=_parse_is_share(data.get("is_share")),
            raw=dict(data),
        )


def _parse_is_share(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return 1 if value else 0
    text = str(value or "").strip().lower()
    if text in {"1", "true"}:
        return 1
    if text in {"0", "false", ""}:
        return 0
    return 0


@dataclass
class WebDAVConnectionInfo:
    """SFTPGo/WebDAV connection metadata for browser-side file operations."""

    address: str
    auth: str
    webdav_port: int
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "WebDAVConnectionInfo":
        port_raw = data.get("webdav_port")
        try:
            port = int(str(port_raw or "0"))
        except (TypeError, ValueError):
            port = 0
        return cls(
            address=str(data.get("address") or "").strip(),
            auth=str(data.get("auth") or "").strip(),
            webdav_port=port,
            raw=dict(data),
        )


def _files_referer(workspace_id: str | None = None) -> str:
    suffix = f"?spaceId={workspace_id}" if workspace_id else ""
    return f"{_get_base_url()}/jobs/files{suffix}"


def list_system_storage_types(
    *,
    workspace_id: str,
    session: Optional[WebSession] = None,
) -> list[SystemStorageInfo]:
    """List storage tiers shown by the web UI file browser."""
    workspace_id = str(workspace_id or "").strip()
    if not workspace_id:
        raise ValueError("workspace_id is required")
    if session is None:
        session = get_web_session()

    data = _request_json(
        session,
        "POST",
        _browser_api_path("/file/get_system_storage_type_list"),
        referer=_files_referer(workspace_id),
        body={"filter": {"workspace_id": workspace_id}},
        timeout=30,
    )
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")

    items = data.get("data", {}).get("system_storages", [])
    if not isinstance(items, list):
        return []
    return [
        storage
        for item in items
        if isinstance(item, dict)
        if (storage := SystemStorageInfo.from_api_response(item)).name
    ]


def list_file_directories(
    *,
    workspace_id: str,
    storage_type: str,
    name: str,
    cluster_id: str | None = None,
    session: Optional[WebSession] = None,
) -> list[FileDirectoryInfo]:
    """List top-level directories of a file-browser category.

    ``name`` is the category key used by the frontend, e.g. ``project``,
    ``global_public`` or ``global_user``.
    """
    workspace_id = str(workspace_id or "").strip()
    storage_type = str(storage_type or "").strip()
    name = str(name or "").strip()
    cluster_id = str(cluster_id or "").strip()
    if not workspace_id or not storage_type or not name:
        raise ValueError("workspace_id, storage_type and name are required")
    if session is None:
        session = get_web_session()

    filter_body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "system_storage_type": storage_type,
        "name": name,
    }
    if cluster_id:
        filter_body["cluster_id"] = cluster_id

    data = _request_json(
        session,
        "POST",
        _browser_api_path("/file/dir/list"),
        referer=_files_referer(workspace_id),
        body={"filter": filter_body},
        timeout=30,
    )
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")

    items = data.get("data", {}).get("files", [])
    if not isinstance(items, list):
        return []
    return [
        entry
        for item in items
        if isinstance(item, dict)
        if (entry := FileDirectoryInfo.from_api_response(item)).directory
    ]


def list_project_file_directories(
    *,
    workspace_id: str,
    session: Optional[WebSession] = None,
    storage_names: Optional[set[str]] = None,
) -> list[FileDirectoryInfo]:
    """List project storage directories across non-share storage tiers."""
    workspace_id = str(workspace_id or "").strip()
    if not workspace_id:
        raise ValueError("workspace_id is required")
    if session is None:
        session = get_web_session()

    requested = {name.strip() for name in (storage_names or set()) if name.strip()}
    storages = list_system_storage_types(workspace_id=workspace_id, session=session)
    entries: list[FileDirectoryInfo] = []
    for storage in storages:
        storage_name = storage.name
        if not storage_name or storage_name.startswith("share-"):
            continue
        if requested and storage_name not in requested:
            continue
        try:
            entries.extend(
                list_file_directories(
                    workspace_id=workspace_id,
                    storage_type=storage_name,
                    cluster_id=storage.cluster_id,
                    name="project",
                    session=session,
                )
            )
        except Exception:
            continue
    return entries


def get_sftpgo_connection_info(
    *,
    storage_name: str,
    usage: str | None = None,
    session: Optional[WebSession] = None,
) -> WebDAVConnectionInfo:
    """Fetch WebDAV connection metadata used by browser-side file operations."""
    storage_name = str(storage_name or "").strip().lower()
    usage = str(usage or "").strip()
    if not storage_name:
        raise ValueError("storage_name is required")
    if session is None:
        session = get_web_session()

    body: dict[str, Any] = {"storage_name": storage_name}
    if usage:
        body["usage"] = usage

    data = _request_json(
        session,
        "POST",
        _browser_api_path("/file/sftpgo/connection_info"),
        referer=_files_referer(),
        body=body,
        timeout=30,
    )
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")

    payload = data.get("data")
    if not isinstance(payload, dict):
        return WebDAVConnectionInfo(address="", auth="", webdav_port=0)
    return WebDAVConnectionInfo.from_api_response(payload)
