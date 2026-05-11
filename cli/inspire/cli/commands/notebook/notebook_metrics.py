"""`inspire notebook metrics <name>` — notebook resource-utilization history."""

from __future__ import annotations

from typing import Optional

from inspire.cli.context import Context
from inspire.cli.utils.metrics_shared import build_metrics_command
from inspire.platform.web import browser_api as browser_api_module
from inspire.platform.web.session import WebSession


def _resolve_notebook_lcg(task_id: str, session: WebSession) -> Optional[str]:
    """Pull ``logic_compute_group_id`` from the notebook detail payload."""
    detail = browser_api_module.get_notebook_detail(notebook_id=task_id, session=session)
    if not isinstance(detail, dict):
        return None
    start_cfg = detail.get("start_config")
    if isinstance(start_cfg, dict):
        lcg = start_cfg.get("logic_compute_group_id")
        if isinstance(lcg, str) and lcg.strip():
            return lcg.strip()
    grp = detail.get("logic_compute_group")
    if isinstance(grp, dict):
        for key in ("logic_compute_group_id", "compute_group_id"):
            value = grp.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _notebook_name_to_id(ctx: Context, name: str) -> str:
    from inspire.cli.commands.notebook import notebook_lookup as _nb
    from inspire.cli.utils.notebook_cli import WEB_AUTH_HINT, get_base_url, load_config, require_web_session
    from inspire.config.workspaces import resolve_workspace_query_scope

    session = require_web_session(
        ctx,
        hint=WEB_AUTH_HINT,
    )
    config = load_config(ctx)
    base_url = get_base_url()
    workspace_ids, _ = resolve_workspace_query_scope(
        config,
        workspace=str(getattr(ctx, "workspace", "") or ""),
        session=session,
    )
    nb_id, _ = _nb._resolve_notebook_id(
        ctx,
        session=session,
        config=config,
        base_url=base_url,
        identifier=name,
        json_output=getattr(ctx, "json_output", False),
        workspace_ids=workspace_ids,
    )
    return nb_id


notebook_metrics = build_metrics_command(
    resource_name="notebook",
    resource_label="Notebook",
    name_resolver=_notebook_name_to_id,
    lcg_resolver=_resolve_notebook_lcg,
)


__all__ = ["notebook_metrics"]
