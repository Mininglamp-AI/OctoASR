# coding=utf-8
"""mano-asr mentions - open the mention replacements management page"""

from __future__ import annotations

import webbrowser

import click

from manoasr.cli.utils.console import success, error, warning, info, bold
from manoasr.cli.utils.config import config_exists
from manoasr.cli.commands.service import get_configured_port, _check_service_health


@click.command()
@click.option("--no-browser", is_flag=True, help="Only print the link, do not open the browser")
def mentions(no_browser: bool):
    """Manage @mention replacements

    Opens a web page where you can add, edit and delete the
    nickname -> canonical name replacements stored in
    ~/.mano-asr/mentions/user.json

    \b
    Usage:
      mano-asr mentions              Open the page in your browser
      mano-asr mentions --no-browser Just print the link
    """
    if not config_exists():
        click.echo(error("Not initialized, please run: mano-asr start"))
        raise SystemExit(1)

    port = get_configured_port()
    url = f"http://127.0.0.1:{port}/mentions"

    running, _ = _check_service_health(port)

    click.echo()
    click.echo(info(f"Mention manager: {bold(url)}"))

    if not running:
        click.echo(warning("Service is not running. Start it first with: mano-asr start"))
        click.echo()
        return

    if no_browser:
        click.echo(success("Open the link above in your browser."))
        click.echo()
        return

    opened = webbrowser.open(url)
    if opened:
        click.echo(success("Opened in your default browser."))
    else:
        click.echo(warning("Could not open a browser automatically. Open the link above manually."))
    click.echo()
