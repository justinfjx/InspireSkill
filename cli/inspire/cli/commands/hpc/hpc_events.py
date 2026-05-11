"""`inspire hpc events <name>` — job-level platform events for an HPC job.

Use `inspire hpc instances <name> --workspace <workspace>` for the
pod/component inventory. Events remain scoped to the HPC job object.
"""

from __future__ import annotations

from typing import Optional

import click

from inspire.cli.context import Context, EXIT_CONFIG_ERROR, pass_context
from inspire.cli.commands.hpc.hpc_commands import _resolve_hpc_name_in_workspace
from inspire.cli.utils.errors import exit_with_error as _handle_error
from inspire.cli.utils.events import run_events_command
from inspire.config import Config, ConfigError
from inspire.platform.web.browser_api.hpc_jobs import list_hpc_job_events
from inspire.platform.web.session import get_web_session


@click.command("events")
@click.argument("name")
@click.option("--workspace", required=True, help="Workspace name.")
@click.option(
    "--json",
    "json_output_local",
    is_flag=True,
    help="Output as JSON. Equivalent to top-level `--json`.",
)
@click.option(
    "--reason",
    "reason_filter",
    help="Filter events whose `reason` contains this substring (case-insensitive).",
)
@click.option(
    "--tail",
    type=int,
    help="Show only the last N events (applied after --reason).",
)
@pass_context
def events(
    ctx: Context,
    name: str,
    workspace: str,
    json_output_local: bool,
    reason_filter: Optional[str],
    tail: Optional[int],
) -> None:
    """Show job-level platform events for an HPC job.

    \b
    Examples:
      inspire hpc events <name> --workspace CPU资源空间
      inspire --json hpc events <name> --workspace CPU资源空间
      inspire hpc events <name> --workspace CPU资源空间 --reason Deleted
    """
    try:
        config, _ = Config.from_files_and_env(require_credentials=False)
        session = get_web_session()
        job_id = _resolve_hpc_name_in_workspace(
            ctx,
            config=config,
            session=session,
            name=name,
            workspace=workspace,
            limit=10000,
        )
    except ConfigError as e:
        _handle_error(ctx, "ConfigError", str(e), EXIT_CONFIG_ERROR)
        return
    run_events_command(
        ctx,
        resource_id=job_id,
        resource_type="hpc",
        resource_name=name,
        fetch=lambda: list_hpc_job_events(job_id),
        json_output_local=json_output_local,
        type_filter=None,  # HPC events lack `type`; filter not applicable
        reason_filter=reason_filter,
        tail=tail,
    )
