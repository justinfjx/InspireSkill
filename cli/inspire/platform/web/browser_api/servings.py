"""Browser API wrappers for inference servings (model deployment).

Browser API fills in everything the UI needs on the `/jobs/modelDeployment` page:
listing, create / detail / stop / delete, configs per workspace, and the
user+project pickers for the create dialog. Reverse-engineered via Chrome and
frontend bundle inspection — see
[cli/scripts/reverse_capture/](../../../../scripts/reverse_capture/).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from inspire.platform.web.browser_api.core import (
    _browser_api_path,
    _get_base_url,
    _request_json,
)
from inspire.platform.web.session import DEFAULT_WORKSPACE_ID, WebSession, get_web_session

__all__ = [
    "ServingInfo",
    "list_servings",
    "list_serving_user_project",
    "get_serving_configs",
    "get_serving_detail",
    "create_serving",
    "stop_serving",
    "start_serving",
    "delete_serving",
]


_REFERER_PATH = "/jobs/modelDeployment"


def _referer() -> str:
    return f"{_get_base_url()}{_REFERER_PATH}"


def _resolve_workspace(
    workspace_id: Optional[str], session: Optional[WebSession]
) -> tuple[WebSession, str]:
    if session is None:
        session = get_web_session()
    if workspace_id is None:
        workspace_id = session.workspace_id or DEFAULT_WORKSPACE_ID
    return session, workspace_id


def _check_response(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")
    payload = data.get("data")
    return payload if isinstance(payload, dict) else {}


@dataclass
class ServingInfo:
    inference_serving_id: str
    name: str
    status: str = ""
    replicas: int = 0
    node_num_per_replica: int = 0
    image: str = ""
    model_name: str = ""
    model_version: str = ""
    framework: str = ""
    service_type: str = ""
    project_id: str = ""
    project_name: str = ""
    workspace_id: str = ""
    logic_compute_group_id: str = ""
    quota: str = ""
    priority: str = ""
    created_at: str = ""
    updated_at: str = ""
    created_by: str = ""
    raw: dict[str, Any] | None = None


def _merge_filter(
    filter_by: Optional[dict[str, Any]],
    *,
    my_serving: bool,
    keyword: Optional[str] = None,
    project_ids: Optional[Iterable[str]] = None,
    statuses: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    merged = dict(filter_by or {})
    merged.setdefault("my_serving", my_serving)
    if keyword:
        merged["keyword"] = keyword
    if project_ids:
        values = [str(v).strip() for v in project_ids if str(v).strip()]
        if values:
            merged["project_id"] = values
    if statuses:
        values = [str(v).strip() for v in statuses if str(v).strip()]
        if values:
            merged["status"] = values
    return merged


def list_servings(
    workspace_id: Optional[str] = None,
    *,
    my_serving: bool = True,
    page: int = 1,
    page_size: int = 20,
    filter_by: Optional[dict[str, Any]] = None,
    keyword: Optional[str] = None,
    project_ids: Optional[Iterable[str]] = None,
    statuses: Optional[Iterable[str]] = None,
    session: Optional[WebSession] = None,
) -> tuple[list[ServingInfo], int]:
    """List inference servings via `POST /api/v1/inference_servings/list`.

    Returns `(items, total)`. `my_serving=True` mirrors the UI's "我的部署"
    default; pass `False` to see the workspace-wide "全部部署" view.
    """
    session, workspace_id = _resolve_workspace(workspace_id, session)
    body = {
        "page": page,
        "page_size": page_size,
        "filter_by": _merge_filter(
            filter_by,
            my_serving=my_serving,
            keyword=keyword,
            project_ids=project_ids,
            statuses=statuses,
        ),
        "workspace_id": workspace_id,
    }
    data = _request_json(
        session,
        "POST",
        _browser_api_path("/inference_servings/list"),
        referer=f"{_referer()}?spaceId={workspace_id}",
        body=body,
        timeout=30,
    )
    payload = _check_response(data)
    raw_items = payload.get("inference_servings") or payload.get("list") or []
    total = int(payload.get("total") or len(raw_items) or 0)

    def _pick(item: dict, *keys: str, default: str = "") -> str:
        for k in keys:
            v = item.get(k)
            if v is not None and v != "":
                return str(v)
        return default

    def _pick_nested(item: dict, key: str, *inner_keys: str) -> str:
        payload = item.get(key)
        if isinstance(payload, dict):
            for inner_key in inner_keys:
                value = payload.get(inner_key)
                if value not in (None, ""):
                    return str(value)
        return ""

    def _pick_int(item: dict, *keys: str) -> int:
        for key in keys:
            value = item.get(key)
            if value in (None, ""):
                continue
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return 0
        return 0

    def _created_by(item: dict) -> str:
        cb = item.get("created_by")
        if isinstance(cb, dict):
            return cb.get("name") or cb.get("id") or ""
        return str(cb or "")

    return (
        [
            ServingInfo(
                inference_serving_id=_pick(it, "inference_serving_id", "id"),
                name=_pick(it, "name", "service_name"),
                status=_pick(it, "status", "phase"),
                replicas=_pick_int(it, "replicas", "replica_count"),
                node_num_per_replica=_pick_int(
                    it, "node_num_per_replica", "single_replica_instance_count"
                ),
                image=_pick(it, "image", "mirror_url", "image_url"),
                model_name=(
                    _pick(it, "model_name", "model_display_name")
                    or _pick_nested(it, "model", "name", "model_name")
                ),
                model_version=_pick(it, "model_version", "version"),
                framework=_pick(it, "framework", "deploy_framework", "deployment_framework"),
                service_type=_pick(it, "service_type", "serving_type", "deploy_type"),
                project_id=_pick(it, "project_id"),
                project_name=_pick(it, "project_name")
                or _pick_nested(it, "project", "name", "project_name"),
                workspace_id=_pick(it, "workspace_id", default=workspace_id),
                logic_compute_group_id=_pick(it, "logic_compute_group_id"),
                quota=_pick(it, "quota", "resource_spec", "resource_spec_name"),
                priority=_pick(it, "priority", "task_priority"),
                created_at=_pick(it, "created_at"),
                updated_at=_pick(it, "updated_at"),
                created_by=_created_by(it),
                raw=it if isinstance(it, dict) else None,
            )
            for it in raw_items
            if isinstance(it, dict)
        ],
        total,
    )


def list_serving_user_project(
    workspace_id: Optional[str] = None,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    """Available projects + users for the create-serving dialog.

    Returns the raw `data` dict (`{projects: [...], users: [...]}`). The shape
    mirrors the UI drop-downs so we don't collapse it into typed objects here.
    """
    session, workspace_id = _resolve_workspace(workspace_id, session)
    data = _request_json(
        session,
        "POST",
        _browser_api_path("/inference_servings/user_project/list"),
        referer=_referer(),
        body={"workspace_id": workspace_id},
        timeout=30,
    )
    return _check_response(data)


def get_serving_configs(
    workspace_id: Optional[str] = None,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    """Serving-time configs for a workspace (image / quota presets).

    Calls `GET /api/v1/inference_servings/configs/workspace/{workspace_id}`.
    Returns the raw `data` dict, typically `{configs: [...]}`.
    """
    session, workspace_id = _resolve_workspace(workspace_id, session)
    data = _request_json(
        session,
        "GET",
        _browser_api_path(f"/inference_servings/configs/workspace/{workspace_id}"),
        referer=_referer(),
        timeout=30,
    )
    return _check_response(data)


def get_serving_detail(
    inference_serving_id: str,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    """Browser API variant of serving detail.

    Calls `GET /api/v1/inference_servings/{id}`, matching the current web UI.
    """
    if session is None:
        session = get_web_session()
    data = _request_json(
        session,
        "GET",
        _browser_api_path(f"/inference_servings/{inference_serving_id}"),
        referer=_referer(),
        timeout=30,
    )
    return _check_response(data)


def create_serving(
    *,
    workspace_id: str,
    project_id: str,
    name: str,
    logic_compute_group_id: str,
    model_id: str,
    model_version: int | str,
    mirror_id: str,
    command: str,
    port: int,
    resource_spec_price: dict[str, Any],
    description: str = "",
    replicas: int = 1,
    node_num_per_replica: int = 1,
    shm_gi: int | None = None,
    task_priority: int = 1,
    custom_domain: str | None = None,
    inference_serving_type: str = "CUSTOM",
    model_source: str | None = None,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    """Create a custom model deployment via the Browser API.

    The payload mirrors the current `/jobs/modelDeployment` form. In
    particular, images are sent by `mirror_id`, and resource specs are sent as
    a nested `resource_spec_price` proto-style object rather than an OpenAPI
    `spec_id`.
    """
    if session is None:
        session = get_web_session()
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "inference_serving_type": inference_serving_type,
        "name": name,
        "logic_compute_group_id": logic_compute_group_id,
        "model_id": model_id,
        "model_version": int(model_version),
        "mirror_id": mirror_id,
        "command": command,
        "port": int(port),
        "description": description,
        "replicas": int(replicas),
        "node_num_per_replica": int(node_num_per_replica),
        "task_priority": int(task_priority),
        "resource_spec_price": dict(resource_spec_price),
    }
    if custom_domain:
        body["custom_domain"] = custom_domain
    if shm_gi is not None:
        body["shm_gi"] = int(shm_gi)
    if model_source:
        body["model_source"] = model_source

    data = _request_json(
        session,
        "POST",
        _browser_api_path("/inference_servings/create"),
        referer=f"{_referer()}?spaceId={workspace_id}",
        body=body,
        timeout=60,
    )
    return _check_response(data)


def _serving_action(
    *,
    action: str,
    inference_serving_id: str,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    if session is None:
        session = get_web_session()
    data = _request_json(
        session,
        "POST",
        f"/api/v2/inference_serving?Action={action}",
        referer=_referer(),
        body={"inference_serving_id": inference_serving_id, "version": 0},
        timeout=30,
    )
    return _check_response(data)


def stop_serving(
    inference_serving_id: str,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    """Stop a model deployment via `Action=StopServing`."""
    return _serving_action(
        action="StopServing",
        inference_serving_id=inference_serving_id,
        session=session,
    )


def start_serving(
    inference_serving_id: str,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    """Start a model deployment via `Action=StartServing`."""
    return _serving_action(
        action="StartServing",
        inference_serving_id=inference_serving_id,
        session=session,
    )


def delete_serving(
    inference_serving_id: str,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    """Delete a model deployment entry via `DELETE /inference_servings/{id}`."""
    if session is None:
        session = get_web_session()
    data = _request_json(
        session,
        "DELETE",
        _browser_api_path(f"/inference_servings/{inference_serving_id}"),
        referer=_referer(),
        timeout=30,
    )
    return _check_response(data)
