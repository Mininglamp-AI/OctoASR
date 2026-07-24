# coding=utf-8
"""OctoASR CLI entry"""

import os
import warnings
import logging

os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
warnings.filterwarnings("ignore", message=".*model of type.*")
logging.getLogger("transformers").setLevel(logging.ERROR)

try:
    import transformers
    transformers.logging.set_verbosity_error()
except ImportError:
    pass

import click

from octoasr import __version__
from octoasr.cli.commands import service, transcribe, port, model, config, logs, doctor, mentions


@click.group(invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="Show version")
@click.pass_context
def cli(ctx, version):
    """OctoASR: Local speech-to-text service

    Run 'octoasr help' to see all commands
    """
    if version:
        click.echo(f"octoasr {__version__}")
        return

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(service.start)
cli.add_command(service.stop)
cli.add_command(service.restart)
cli.add_command(service.status)

cli.add_command(transcribe.transcribe)
cli.add_command(port.port)
cli.add_command(model.model)
cli.add_command(config.config)
cli.add_command(logs.logs)
cli.add_command(doctor.doctor)
cli.add_command(mentions.mentions)


@cli.command("help")
def help_cmd():
    """Show help"""
    help_text = """
  OctoASR - Local speech-to-text service

  Usage:
    octoasr <command> [options]

  Service:
    start         Start service (auto-init on first run)
    stop          Stop service
    restart       Restart service
    status        Show service status

  Features:
    transcribe    Transcribe audio file
    port          Port management (view/set)
    model         Model management (list/use/info)
    config        Config management (show/reset)
    logs          View logs (--errors/--stats)
    doctor        Environment check
    mentions      Manage @mention replacements (opens web page)

  Other:
    help          Show this help
    --version     Show version

  Examples:
    octoasr start                    Start service
    octoasr transcribe audio.wav     Transcribe audio
    octoasr port 9000                Set port
    octoasr model use <name>         Switch model
    octoasr logs --stats             Show log stats
    octoasr logs --errors            Show error logs only
    octoasr mentions                 Open @mention replacements page
    octoasr mentions --no-browser    Print the page link only
"""
    click.echo(help_text)


def main():
    cli()


if __name__ == "__main__":
    main()
