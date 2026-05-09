"""`inspire user` subcommands."""

from __future__ import annotations

from typing import Optional

import click

from inspire.cli.context import (
    Context,
    EXIT_API_ERROR,
    EXIT_AUTH_ERROR,
    EXIT_CONFIG_ERROR,
    pass_context,
)
from inspire.cli.formatters import json_formatter
from inspire.cli.utils.auth import AuthenticationError
from inspire.cli.utils.errors import exit_with_error as _handle_error
from inspire.config import Config, ConfigError
from inspire.config.workspaces import select_workspace_id
from inspire.platform.web import browser_api as browser_api_module
from inspire.platform.web.session import get_web_session


def _resolve_workspace_id(config: Config, workspace: Optional[str]) -> Optional[str]:
    if workspace is None:
        return None
    return select_workspace_id(config, explicit_workspace_name=workspace)


@click.command("whoami")
@pass_context
def whoami_user(ctx: Context) -> None:
    """Show the logged-in user."""
    try:
        session = get_web_session()
        info = browser_api_module.get_current_user(session=session) or {}

        if ctx.json_output:
            click.echo(json_formatter.format_json(info))
            return

        click.echo("Current User")
        click.echo(f"Name:      {info.get('name', 'N/A')}")
        click.echo(f"Login:     {(info.get('extra_info') or {}).get('login_name', 'N/A')}")
        click.echo(f"Role:      {info.get('global_role', 'N/A')}")
        if info.get("email"):
            click.echo(f"Email:     {info.get('email')}")

    except AuthenticationError as e:
        _handle_error(ctx, "AuthenticationError", str(e), EXIT_AUTH_ERROR)
    except Exception as e:
        _handle_error(ctx, "APIError", str(e), EXIT_API_ERROR)


@click.command("quota")
@pass_context
def quota_user(ctx: Context) -> None:
    """Show the current user's quota.

    \b
    Note: user-level quota is admin-only on qz.sii.edu.cn. Regular users may
    see `用户不存在`; use `inspire project list` for per-project remaining
    budget and GPU caps instead.
    """
    try:
        session = get_web_session()
        data = browser_api_module.get_user_quota(session=session)
        if ctx.json_output:
            click.echo(json_formatter.format_json(data))
            return
        if not data:
            click.echo("No quota data returned.")
            return
        click.echo("User Quota")
        for k, v in data.items():
            click.echo(f"  {k}: {v}")

    except AuthenticationError as e:
        _handle_error(ctx, "AuthenticationError", str(e), EXIT_AUTH_ERROR)
    except Exception as e:
        msg = str(e)
        if "用户不存在" in msg or "user does not exist" in msg.lower():
            msg = (
                f"{msg}\n\n"
                "Hint: user-level quota is admin-only on qz.sii.edu.cn; regular "
                "users may see this error. Use `inspire project list` for "
                "per-project remaining budget and GPU caps."
            )
        _handle_error(ctx, "APIError", msg, EXIT_API_ERROR)


@click.command("api-keys")
@pass_context
def api_keys_user(ctx: Context) -> None:
    """List the current user's API keys.

    Values are not returned by list — only metadata. Create/delete are not
    wrapped; use the platform user center for those.
    """
    try:
        session = get_web_session()
        items = browser_api_module.list_user_api_keys(session=session)

        if ctx.json_output:
            click.echo(json_formatter.format_json({"total": len(items), "items": items}))
            return

        if not items:
            click.echo("No API keys found.")
            return

        click.echo(f"API Keys (total={len(items)})")
        for i, item in enumerate(items, 1):
            name = item.get("name") or item.get("title") or item.get("id") or "?"
            created = item.get("create_at") or item.get("created_at") or ""
            last_used = item.get("last_used_at") or item.get("last_used") or ""
            suffix = []
            if created:
                suffix.append(f"created={created}")
            if last_used:
                suffix.append(f"last_used={last_used}")
            click.echo(f"  [{i}] {name}  " + "  ".join(suffix))

    except AuthenticationError as e:
        _handle_error(ctx, "AuthenticationError", str(e), EXIT_AUTH_ERROR)
    except Exception as e:
        _handle_error(ctx, "APIError", str(e), EXIT_API_ERROR)


@click.command("permissions")
@click.option("--workspace", default=None, help="Workspace name (from [workspaces])")
@pass_context
def permissions_user(
    ctx: Context, workspace: Optional[str],) -> None:
    """Show per-workspace permission matrix (`/user/permissions/{ws}`)."""
    try:
        config, _ = Config.from_files_and_env(require_credentials=False)
        resolved_workspace = _resolve_workspace_id(config, workspace)
        session = get_web_session()
        perms = browser_api_module.get_user_permissions(
            workspace_id=resolved_workspace, session=session
        )

        if ctx.json_output:
            click.echo(json_formatter.format_json({"workspace_id": resolved_workspace, "permissions": perms}))
            return

        if not perms:
            click.echo("No permissions granted in this workspace.")
            return

        workspace_label = workspace or "(current workspace)"
        click.echo(f"Permissions in workspace {workspace_label} ({len(perms)} granted)")
        for p in sorted(perms):
            click.echo(f"  {p}")

    except ConfigError as e:
        _handle_error(ctx, "ConfigError", str(e), EXIT_CONFIG_ERROR)
    except AuthenticationError as e:
        _handle_error(ctx, "AuthenticationError", str(e), EXIT_AUTH_ERROR)
    except Exception as e:
        _handle_error(ctx, "APIError", str(e), EXIT_API_ERROR)


__all__ = [
    "whoami_user",
    "quota_user",
    "api_keys_user",
    "permissions_user",
]
