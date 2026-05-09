"""Unit tests for `inspire.platform.web.browser_api.models`."""

from __future__ import annotations

from typing import Any

import pytest

from inspire.platform.web.browser_api import models as models_module
from inspire.platform.web.browser_api.models import (
    ModelInfo,
    create_model,
    get_model_detail,
    list_model_version_records,
    list_model_versions,
    list_models,
)


class _FakeSession:
    def __init__(self, workspace_id: str | None = "ws-default") -> None:
        self.workspace_id = workspace_id


def _install_fake_request(
    monkeypatch: pytest.MonkeyPatch, response: dict, record: dict
) -> None:
    def _fake(session, method, url, *, referer=None, body=None, timeout=30, **kwargs):
        record["session"] = session
        record["method"] = method
        record["url"] = url
        record["referer"] = referer
        record["body"] = body
        record["timeout"] = timeout
        return response

    monkeypatch.setattr(models_module, "_request_json", _fake)


def test_list_models_posts_current_filter_shape_and_parses_response(monkeypatch) -> None:
    record: dict[str, Any] = {}
    _install_fake_request(
        monkeypatch,
        {
            "code": 0,
            "data": {
                "list": [
                    {
                        "model": {
                            "model_id": "model-1",
                            "id": "42",
                            "name": "demo-model",
                            "status": 2,
                            "version": 3,
                            "project_id": "project-1",
                            "workspace_id": "ws-1",
                            "user_id": "user-1",
                            "is_vllm_compatible": True,
                            "created_at": "1770000000000",
                            "updated_at": "1770000100000",
                            "model_type": ["NaturalLanguageProcessing", "TextGeneration"],
                            "tags": ["demo"],
                            "model_size_gi": 12.5,
                        },
                        "project_name": "Project One",
                        "user_name": "Alice",
                    }
                ],
                "total": 8,
            },
        },
        record,
    )

    items, total = list_models(
        workspace_id="ws-1",
        page=2,
        page_size=10,
        keyword="demo",
        user_id="user-1",
        project_ids=["project-1"],
        session=_FakeSession(),
    )

    assert total == 8
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ModelInfo)
    assert item.model_id == "model-1"
    assert item.name == "demo-model"
    assert item.latest_version == "3"
    assert item.project_name == "Project One"
    assert item.user_name == "Alice"
    assert item.model_type == ["NaturalLanguageProcessing", "TextGeneration"]
    assert item.tags == ["demo"]
    assert item.model_size_gi == 12.5
    assert record["method"] == "POST"
    assert record["url"].endswith("/model/list")
    assert record["body"] == {
        "page": 2,
        "page_size": 10,
        "filter_by": {
            "keyword": "demo",
            "user_id": "user-1",
            "project_id": ["project-1"],
        },
        "workspace_id": "ws-1",
    }
    assert record["referer"].endswith("/jobs/modelService?spaceId=ws-1")


def test_list_models_rejects_nonzero_code(monkeypatch) -> None:
    _install_fake_request(monkeypatch, {"code": 100002, "message": "bad"}, {})
    with pytest.raises(ValueError, match="API error: bad"):
        list_models(session=_FakeSession())


def test_model_detail_and_version_endpoints(monkeypatch) -> None:
    record: dict[str, Any] = {}
    _install_fake_request(monkeypatch, {"code": 0, "data": {"ok": True}}, record)

    assert get_model_detail("model-1", session=_FakeSession(), workspace_id="ws-1") == {
        "ok": True
    }
    assert record["method"] == "POST"
    assert record["url"].endswith("/model/detail")
    assert record["body"] == {"model_id": "model-1"}

    assert list_model_versions("model-1", session=_FakeSession()) == {"ok": True}
    assert record["method"] == "GET"
    assert record["url"].endswith("/model/model-1/versions")

    assert list_model_version_records("model-1", session=_FakeSession()) == {"ok": True}
    assert record["method"] == "GET"
    assert record["url"].endswith("/model/model-1")


def test_create_model_posts_registration_body(monkeypatch) -> None:
    record: dict[str, Any] = {}
    _install_fake_request(
        monkeypatch,
        {"code": 0, "data": {"model_id": "model-new"}},
        record,
    )

    result = create_model(
        name="demo",
        project_id="project-1",
        workspace_id="ws-1",
        model_source_path="/inspire/project/model",
        model_type=["NaturalLanguageProcessing", "TextGeneration"],
        tags=["vllm"],
        description="demo model",
        session=_FakeSession(),
    )

    assert result == {"model_id": "model-new"}
    assert record["method"] == "POST"
    assert record["url"].endswith("/model/create")
    assert record["body"] == {
        "name": "demo",
        "project_id": "project-1",
        "workspace_id": "ws-1",
        "model_source_path": "/inspire/project/model",
        "model_source_type": 1,
        "model_type": ["NaturalLanguageProcessing", "TextGeneration"],
        "tags": ["vllm"],
        "description": "demo model",
    }
