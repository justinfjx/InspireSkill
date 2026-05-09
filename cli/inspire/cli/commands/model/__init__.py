"""Model registry commands for Inspire CLI."""

from __future__ import annotations

import click

from .model_commands import list_model, status_model, versions_model


@click.group()
def model() -> None:
    """Browse the platform model registry.

    Read-only commands for inspecting models and their versions on the
    platform model registry. Use `serving` for deployed service observation
    and lifecycle commands.
    """


model.add_command(list_model)
model.add_command(status_model)
model.add_command(versions_model)


__all__ = ["model"]
