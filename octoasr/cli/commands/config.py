# coding=utf-8
"""octoasr config - configuration management"""

from __future__ import annotations

import click

from octoasr.cli.utils.config import (
    load_config,
    save_config,
    config_exists,
    get_default_config,
)
from octoasr.cli.utils.console import success, error, print_header, print_footer
from octoasr.cli.utils.constants import CONFIG_FILE

import yaml


@click.group()
def config():
    """Configuration management"""
    pass


@config.command("show")
def config_show():
    """Show current configuration"""

    if not config_exists():
        click.echo(error("Not initialized, please run: octoasr start"))
        raise SystemExit(1)

    current_config = load_config()

    click.echo(f"\n  Config file: {CONFIG_FILE}")
    print_header("Configuration")

    yaml_str = yaml.dump(current_config, allow_unicode=True, default_flow_style=False)
    for line in yaml_str.strip().split("\n"):
        click.echo(f"  {line}")

    print_footer()


@config.command("reset")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def config_reset(yes: bool):
    """Reset to default configuration"""

    if not yes:
        click.confirm("Are you sure you want to reset the configuration?", abort=True)

    default_config = get_default_config()
    save_config(default_config)

    click.echo(success("Configuration reset to defaults"))
