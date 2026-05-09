"""Model registry commands for Inspire CLI."""

from __future__ import annotations

import click

from .model_commands import list_model, register_model, status_model, versions_model


@click.group()
def model() -> None:
    """Use the platform model repository.

    Inspect registered models, inspect versions, and register platform-visible
    model directories. Use `serving` for deployed service lifecycle commands.
    """


model.add_command(list_model)
model.add_command(register_model)
model.add_command(status_model)
model.add_command(versions_model)


__all__ = ["model"]
