"""Tunnel test command."""

from __future__ import annotations

import sys

import click

from inspire.bridge.tunnel import (
    BridgeProfile,
    TunnelNotAvailableError,
    load_tunnel_config,
    run_ssh_command,
)
from inspire.cli.context import Context, EXIT_CONFIG_ERROR, EXIT_GENERAL_ERROR, pass_context
from inspire.cli.formatters import human_formatter, json_formatter


def _bridge_public_payload(bridge: BridgeProfile) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": bridge.name,
        "proxy_url": bridge.proxy_url,
        "ssh_user": bridge.ssh_user,
        "ssh_port": bridge.ssh_port,
        "has_internet": bridge.has_internet,
    }
    if bridge.notebook_name:
        payload["notebook_name"] = bridge.notebook_name
    if bridge.rtunnel_port is not None:
        payload["rtunnel_port"] = bridge.rtunnel_port
    return payload


@click.command("test")
@click.argument("notebook")
@pass_context
def tunnel_test(ctx: Context, notebook: str) -> None:
    """Test SSH connection to a cached notebook and show timing.

    NOTEBOOK is the cached notebook name.

    \b
    Examples:
        inspire notebook ssh test my-notebook
    """
    import time

    bridge = notebook
    config = load_tunnel_config()
    bridge_profile = config.get_bridge(bridge)

    if not bridge_profile:
        if ctx.json_output:
            click.echo(
                json_formatter.format_json_error(
                    "ConfigError",
                    "No cached notebook connection",
                    EXIT_CONFIG_ERROR,
                    hint="Create one with: inspire notebook ssh connect <notebook> --workspace <workspace>",
                ),
                err=True,
            )
        else:
            click.echo(
                human_formatter.format_error(
                    "No cached notebook connection. Create one with: "
                    "inspire notebook ssh connect <notebook> --workspace <workspace>"
                ),
                err=True,
            )
        sys.exit(EXIT_CONFIG_ERROR)

    try:
        start = time.time()
        result = run_ssh_command(
            "hostname", bridge_name=bridge_profile.name, config=config, timeout=30
        )
        elapsed = time.time() - start

        hostname = result.stdout.strip()

        if ctx.json_output:
            if result.returncode == 0:
                click.echo(
                    json_formatter.format_json(
                        {
                            "notebook": bridge_profile.name,
                            "hostname": hostname,
                            "elapsed_ms": int(elapsed * 1000),
                            "bridge": _bridge_public_payload(bridge_profile),
                        }
                    )
                )
            else:
                click.echo(
                    json_formatter.format_json_error(
                        "TunnelError",
                        f"Connection failed: {result.stderr}",
                        EXIT_GENERAL_ERROR,
                    ),
                    err=True,
                )
                sys.exit(EXIT_GENERAL_ERROR)
        else:
            if result.returncode == 0:
                click.echo(
                    human_formatter.format_success(
                        f"Notebook '{bridge_profile.name}': Connected to {hostname}"
                    )
                )
                click.echo(f"Response time: {elapsed:.2f}s")
            else:
                click.echo(human_formatter.format_error(f"Connection failed: {result.stderr}"))
                sys.exit(EXIT_GENERAL_ERROR)

    except TunnelNotAvailableError as e:
        if ctx.json_output:
            click.echo(
                json_formatter.format_json_error("TunnelError", str(e), EXIT_GENERAL_ERROR),
                err=True,
            )
        else:
            click.echo(human_formatter.format_error(str(e)), err=True)
        sys.exit(EXIT_GENERAL_ERROR)
    except Exception as e:
        if ctx.json_output:
            click.echo(
                json_formatter.format_json_error("Error", str(e), EXIT_GENERAL_ERROR),
                err=True,
            )
        else:
            click.echo(human_formatter.format_error(f"Connection failed: {e}"), err=True)
        sys.exit(EXIT_GENERAL_ERROR)
