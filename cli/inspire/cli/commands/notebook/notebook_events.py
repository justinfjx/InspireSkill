"""`inspire notebook events <name>` — lifecycle timeline for a notebook instance.

Notebook events are a platform lifecycle timeline: scheduling, image pulls,
container start, stop, save, and related messages. The platform may return an
empty list for long-terminated notebooks; that is a normal steady state, not
an error. Notebooks run as one instance, so there is no ``--instance`` flag.
"""

from __future__ import annotations

from typing import Optional

import click

from inspire.cli.context import Context, pass_context
from inspire.cli.utils.events import run_events_command
from inspire.platform.web.browser_api.notebooks import list_notebook_events


@click.command("events")
@click.argument("name")
@click.option("--workspace", required=True, help="Workspace name or 'all'.")
@click.option(
    "--json",
    "json_output_local",
    is_flag=True,
    help="Output as JSON. Equivalent to top-level `--json`.",
)
@click.option(
    "--type",
    "type_filter",
    help="Filter events by `type` (Normal / Warning; case-insensitive prefix match).",
)
@click.option(
    "--reason",
    "reason_filter",
    help="Filter events whose `reason` contains this substring (case-insensitive).",
)
@click.option(
    "--tail",
    type=int,
    help="Show only the last N events (applied after --type/--reason).",
)
@pass_context
def events(
    ctx: Context,
    name: str,
    workspace: str,
    json_output_local: bool,
    type_filter: Optional[str],
    reason_filter: Optional[str],
    tail: Optional[int],
) -> None:
    """Show platform events for a notebook instance.

    \b
    Examples:
      inspire notebook events <name> --workspace 分布式训练空间
      inspire --json notebook events <name> --workspace 分布式训练空间
      inspire notebook events <name> --workspace 分布式训练空间 --type Warning
      inspire notebook events <name> --workspace 分布式训练空间 --reason FailedScheduling
    """
    from inspire.cli.commands.notebook import notebook_lookup as _nb
    from inspire.cli.utils.notebook_cli import WEB_AUTH_HINT, get_base_url, load_config, require_web_session
    from inspire.config import ConfigError
    from inspire.config.workspaces import resolve_workspace_query_scope
    from inspire.cli.context import EXIT_CONFIG_ERROR
    from inspire.cli.utils.errors import exit_with_error as _handle_error

    session = require_web_session(ctx, hint=WEB_AUTH_HINT)
    config = load_config(ctx)
    try:
        workspace_ids, _ = resolve_workspace_query_scope(
            config,
            workspace=workspace,
            session=session,
        )
    except ConfigError as e:
        _handle_error(ctx, "ConfigError", str(e), EXIT_CONFIG_ERROR)
        return
    notebook_id, _ = _nb._resolve_notebook_id(
        ctx,
        session=session,
        config=config,
        base_url=get_base_url(),
        identifier=name,
        json_output=getattr(ctx, "json_output", False),
        workspace_ids=workspace_ids,
    )
    run_events_command(
        ctx,
        resource_id=notebook_id,
        resource_type="notebook",
        resource_name=name,
        fetch=lambda: list_notebook_events(notebook_id),
        json_output_local=json_output_local,
        type_filter=type_filter,
        reason_filter=reason_filter,
        tail=tail,
    )
