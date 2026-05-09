"""Inference serving (model deployment) commands for Inspire CLI."""

from __future__ import annotations

import click

from .serving_commands import configs_serving, list_serving, status_serving, stop_serving
from .serving_metrics import serving_metrics


@click.group()
def serving() -> None:
    """Manage inference servings (model deployment).

    Covers the observable lifecycle of model deployment services: list,
    status, available configs, resource metrics, and stop.

    \b
    Examples:
        inspire serving list
        inspire serving status <serving-name>
        inspire serving metrics <serving-name> --window 30m

    `create` is intentionally not wrapped — deployment configuration is
    platform-specific (model, port, replicas, custom domain, ...). Use the
    platform deployment page for creation, then return here for observation
    and stop.
    """


serving.add_command(list_serving)
serving.add_command(status_serving)
serving.add_command(stop_serving)
serving.add_command(configs_serving)
serving.add_command(serving_metrics)  # metrics (资源视图 time-series; per-replica pods)


__all__ = ["serving"]
