# coding=utf-8
"""octoasr port - port management"""

from __future__ import annotations

import click

from octoasr.cli.utils.config import load_config, save_config, config_exists
from octoasr.cli.utils.console import success, error, warning, info
from octoasr.cli.utils.constants import DEFAULT_PORT


@click.command()
@click.argument("new_port", type=int, required=False)
def port(new_port: int):
    """Port management

    \b
    View current port:
      octoasr port

    \b
    Set new port:
      octoasr port 9000
    """
    if not config_exists():
        click.echo(error("Not initialized, please run: octoasr start"))
        raise SystemExit(1)

    config = load_config()
    current_port = config.get("server", {}).get("port", DEFAULT_PORT)

    if new_port is None:
        click.echo(f"\n  Current port: {current_port}\n")
        return

    if new_port < 1024 or new_port > 65535:
        click.echo(error("Port must be between 1024-65535"))
        raise SystemExit(1)

    if new_port == current_port:
        click.echo(info(f"Port unchanged: {current_port}"))
        return

    if "server" not in config:
        config["server"] = {}
    config["server"]["port"] = new_port
    save_config(config)

    click.echo(success(f"Port changed: {current_port} -> {new_port}"))
    click.echo(warning("Restart required to take effect: octoasr restart"))
