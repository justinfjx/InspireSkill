"""Browser API wrappers for the model registry.

Reverse-engineered from the current `/jobs/modelService` page. No OpenAPI
counterpart exists, so model registry browsing and registration are Browser
API-only. See `cli/scripts/reverse_capture/` for the capture methodology.

Wire-format notes:
- `POST /api/v1/model/list` body
  `{page, page_size, filter_by:{keyword?, user_id?, project_id?[]}, workspace_id}`.
- `POST /api/v1/model/detail` body `{model_id}` returns the model head record.
- `GET /api/v1/model/{model_id}` returns detailed version records.
- `GET /api/v1/model/{model_id}/versions` returns compact version status records.
- `POST /api/v1/model/create` registers a new model from a platform-visible path.
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
    "ModelInfo",
    "create_model",
    "get_model_detail",
    "list_model_version_records",
    "list_model_versions",
    "list_models",
]


_REFERER_PATH = "/jobs/modelService"


def _referer(workspace_id: str | None = None) -> str:
    url = f"{_get_base_url()}{_REFERER_PATH}"
    if workspace_id:
        return f"{url}?spaceId={workspace_id}"
    return url


def _resolve_workspace(
    workspace_id: Optional[str], session: Optional[WebSession]
) -> tuple[WebSession, str]:
    if session is None:
        session = get_web_session()
    if workspace_id is None:
        workspace_id = session.workspace_id or DEFAULT_WORKSPACE_ID
    return session, workspace_id


@dataclass
class ModelInfo:
    model_id: str
    name: str
    id: str = ""  # numeric internal id
    description: str = ""
    project_id: str = ""
    project_name: str = ""
    workspace_id: str = ""
    user_id: str = ""
    user_name: str = ""
    status: str = ""
    has_published: bool = False
    is_vllm_compatible: bool = False
    created_at: str = ""
    updated_at: str = ""
    latest_version: str = ""
    model_type: list[str] | None = None
    tags: list[str] | None = None
    model_path: str = ""
    model_source_path: str = ""
    model_source_type: int = 0
    model_size_gi: float = 0.0
    version_description: str = ""
    fail_reason: str = ""
    plaza_publish_status: str = ""
    raw: dict[str, Any] | None = None


def _parse_model(item: dict[str, Any]) -> ModelInfo:
    """Flatten the `/model/list` item shape (`{model: {...}, ...}`) into `ModelInfo`."""
    if not isinstance(item, dict):
        return ModelInfo(model_id="", name="")
    model_payload = item.get("model")
    inner: dict[str, Any] = model_payload if isinstance(model_payload, dict) else item
    version_value = item.get("latest_version") or item.get("next_version") or inner.get("version")
    return ModelInfo(
        model_id=str(inner.get("model_id") or inner.get("id") or ""),
        name=str(inner.get("name") or inner.get("model_name") or ""),
        id=str(inner.get("id") or ""),
        description=str(inner.get("description") or ""),
        project_id=str(inner.get("project_id") or item.get("project_id") or ""),
        project_name=str(item.get("project_name") or inner.get("project_name") or ""),
        workspace_id=str(inner.get("workspace_id") or item.get("workspace_id") or ""),
        user_id=str(inner.get("user_id") or item.get("user_id") or ""),
        user_name=str(item.get("user_name") or inner.get("user_name") or ""),
        status=str(inner.get("status") if inner.get("status") is not None else ""),
        has_published=bool(inner.get("has_published", False)),
        is_vllm_compatible=bool(inner.get("is_vllm_compatible", False)),
        created_at=str(inner.get("created_at") or ""),
        updated_at=str(inner.get("updated_at") or ""),
        latest_version=str(version_value or ""),
        model_type=list(inner.get("model_type") or []),
        tags=list(inner.get("tags") or []),
        model_path=str(inner.get("model_path") or ""),
        model_source_path=str(inner.get("model_source_path") or ""),
        model_source_type=int(inner.get("model_source_type") or 0),
        model_size_gi=float(inner.get("model_size_gi") or 0.0),
        version_description=str(inner.get("version_description") or ""),
        fail_reason=str(inner.get("model_fail_reason") or ""),
        plaza_publish_status=str(inner.get("plaza_publish_status") or ""),
        raw=item,
    )


def _merge_filter(
    filter_by: Optional[dict[str, Any]],
    *,
    keyword: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[Iterable[str]] = None,
    model_types: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    merged = dict(filter_by or {})
    if keyword:
        merged["keyword"] = keyword
    if user_id:
        merged["user_id"] = user_id
    if project_ids:
        values = [str(v).strip() for v in project_ids if str(v).strip()]
        if values:
            # The backend expects repeated project_id values; a bare string is
            # rejected by protobuf decoding.
            merged["project_id"] = values
    if model_types:
        values = [str(v).strip() for v in model_types if str(v).strip()]
        if values:
            merged["model_type"] = values
    return merged


def list_models(
    workspace_id: Optional[str] = None,
    *,
    page: int = 1,
    page_size: int = -1,
    filter_by: Optional[dict[str, Any]] = None,
    keyword: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[Iterable[str]] = None,
    model_types: Optional[Iterable[str]] = None,
    session: Optional[WebSession] = None,
) -> tuple[list[ModelInfo], int]:
    """List models via `POST /api/v1/model/list`.

    Returns `(items, total)`. `page_size=-1` mirrors the UI (fetch all).
    """
    session, workspace_id = _resolve_workspace(workspace_id, session)
    body = {
        "page": page,
        "page_size": page_size,
        "filter_by": _merge_filter(
            filter_by,
            keyword=keyword,
            user_id=user_id,
            project_ids=project_ids,
            model_types=model_types,
        ),
        "workspace_id": workspace_id,
    }
    data = _request_json(
        session,
        "POST",
        _browser_api_path("/model/list"),
        referer=_referer(workspace_id),
        body=body,
        timeout=30,
    )
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")

    payload = data.get("data") or {}
    raw_items = payload.get("list") or []
    total = int(payload.get("total") or len(raw_items) or 0)
    return [_parse_model(it) for it in raw_items if isinstance(it, dict)], total


def get_model_detail(
    model_id: str,
    session: Optional[WebSession] = None,
    workspace_id: Optional[str] = None,
) -> dict[str, Any]:
    """Get model detail via `POST /api/v1/model/detail`.

    Returns the raw `data` dict — typically
    `{model: {...}, project_name, user_avatar, user_name}`.
    """
    if session is None:
        session = get_web_session()
    data = _request_json(
        session,
        "POST",
        _browser_api_path("/model/detail"),
        referer=_referer(workspace_id),
        body={"model_id": model_id},
        timeout=30,
    )
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")
    return data.get("data") or {}


def list_model_versions(
    model_id: str,
    session: Optional[WebSession] = None,
    workspace_id: Optional[str] = None,
) -> dict[str, Any]:
    """List compact version status records via `/model/{model_id}/versions`.

    Returns the raw `data` dict (`{list: [...], total}`).
    """
    if session is None:
        session = get_web_session()
    data = _request_json(
        session,
        "GET",
        _browser_api_path(f"/model/{model_id}/versions"),
        referer=_referer(workspace_id),
        timeout=30,
    )
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")
    return data.get("data") or {}


def list_model_version_records(
    model_id: str,
    session: Optional[WebSession] = None,
    workspace_id: Optional[str] = None,
) -> dict[str, Any]:
    """List detailed version records via `GET /api/v1/model/{model_id}`.

    This is the richer endpoint behind the model detail drawer. It includes
    model paths, source paths, sizes, publish status, and running-serving count.
    """
    if session is None:
        session = get_web_session()
    data = _request_json(
        session,
        "GET",
        _browser_api_path(f"/model/{model_id}"),
        referer=_referer(workspace_id),
        timeout=30,
    )
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")
    return data.get("data") or {}


def create_model(
    *,
    name: str,
    project_id: str,
    workspace_id: str,
    model_source_path: str,
    model_type: Optional[Iterable[str]] = None,
    tags: Optional[Iterable[str]] = None,
    description: str = "",
    model_source_type: int = 1,
    session: Optional[WebSession] = None,
) -> dict[str, Any]:
    """Register a model in the platform model repository.

    The first version is inferred by the backend. `model_source_type=1` matches
    the UI path-registration flow for a platform-visible directory.
    """
    if session is None:
        session = get_web_session()
    body = {
        "name": name,
        "project_id": project_id,
        "workspace_id": workspace_id,
        "model_source_path": model_source_path,
        "model_source_type": int(model_source_type),
        "model_type": [str(v) for v in (model_type or []) if str(v).strip()],
        "tags": [str(v) for v in (tags or []) if str(v).strip()],
        "description": description,
    }
    data = _request_json(
        session,
        "POST",
        _browser_api_path("/model/create"),
        referer=_referer(workspace_id),
        body=body,
        timeout=60,
    )
    if data.get("code") != 0:
        raise ValueError(f"API error: {data.get('message')}")
    return data.get("data") or {}
