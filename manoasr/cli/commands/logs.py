# coding=utf-8
"""mano-asr logs - view logs"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta

import click

from manoasr.cli.utils.console import error, info, warning, success, key_value, print_header, print_footer
from manoasr.cli.utils.constants import LOG_FILE


def parse_log_line(line: str) -> dict | None:
    pattern = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+) \[(\w+)\] (.+)$"
    match = re.match(pattern, line)
    if not match:
        return None
    return {
        "timestamp": match.group(1),
        "level": match.group(2),
        "message": match.group(3),
    }


def analyze_logs(lines: list[str], hours: int = 24) -> dict:
    cutoff = datetime.now() - timedelta(hours=hours)

    stats = {
        "total": 0,
        "errors": 0,
        "warnings": 0,
        "api_errors": [],
        "performance": [],
        "by_status": defaultdict(int),
        "transcriptions": 0,
        "last_model_type": None,
        "last_model": None,
    }

    for line in lines:
        parsed = parse_log_line(line)
        if not parsed:
            continue

        try:
            ts = datetime.strptime(parsed["timestamp"], "%Y-%m-%d %H:%M:%S,%f")
            if ts < cutoff:
                continue
        except ValueError:
            continue

        stats["total"] += 1

        if parsed["level"] == "ERROR":
            stats["errors"] += 1
        elif parsed["level"] == "WARNING":
            stats["warnings"] += 1

        msg = parsed["message"]

        starting_match = re.search(r"mano-asr starting model_type=(\S+) model=(\S+)", msg)
        if starting_match:
            stats["last_model_type"] = starting_match.group(1)
            stats["last_model"] = starting_match.group(2)

        if "API error" in msg:
            status_match = re.search(r"status=(\d+)", msg)
            msg_match = re.search(r"msg=([^\s]+)", msg)
            if status_match:
                status = int(status_match.group(1))
                stats["by_status"][status] += 1
                stats["api_errors"].append({
                    "time": parsed["timestamp"],
                    "status": status,
                    "msg": msg_match.group(1) if msg_match else "unknown",
                })

        if "Transcribe OK" in msg:
            stats["transcriptions"] += 1
            elapsed_match = re.search(r"elapsed_ms=(\d+)", msg)
            if elapsed_match:
                stats["performance"].append(int(elapsed_match.group(1)))
            model_match = re.search(r"model_type=(\S+)\s+model=(\S+)", msg)
            if model_match:
                stats["last_model_type"] = model_match.group(1)
                stats["last_model"] = model_match.group(2)

    return stats


@click.command()
@click.option("-f", "--follow", is_flag=True, help="Follow log output")
@click.option("-n", "--lines", default=50, help="Show last N lines")
@click.option("--errors", is_flag=True, help="Show errors only")
@click.option("--stats", is_flag=True, help="Show statistics")
@click.option("--hours", default=24, help="Stats time range (hours)")
def logs(follow: bool, lines: int, errors: bool, stats: bool, hours: int):
    """View logs

    Examples:
      mano-asr logs              Show last 50 lines
      mano-asr logs -f           Follow log output
      mano-asr logs --errors     Show errors only
      mano-asr logs --stats      Show statistics
    """

    if not LOG_FILE.exists():
        click.echo(info("No logs yet"))
        return

    if stats:
        _show_stats(hours)
        return

    try:
        if follow:
            click.echo(info(f"Following log: {LOG_FILE}"))
            click.echo(info("Press Ctrl+C to stop\n"))
            subprocess.run(["tail", "-f", str(LOG_FILE)])
        elif errors:
            result = subprocess.run(
                ["grep", "-E", r"\[(ERROR|WARNING)\]", str(LOG_FILE)],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                output_lines = result.stdout.strip().split("\n")
                for line in output_lines[-lines:]:
                    _colorize_log_line(line)
            else:
                click.echo(success("No error logs"))
        else:
            result = subprocess.run(
                ["tail", "-n", str(lines), str(LOG_FILE)],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    _colorize_log_line(line)
            else:
                click.echo(info("Log is empty"))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        click.echo(error(f"Failed to read log: {e}"))
        raise SystemExit(1)


def _colorize_log_line(line: str):
    if "[ERROR]" in line:
        click.echo(click.style(line, fg="red"))
    elif "[WARNING]" in line:
        click.echo(click.style(line, fg="yellow"))
    elif "API error" in line:
        click.echo(click.style(line, fg="red"))
    elif "Transcribe OK" in line:
        text_match = re.search(r"text=(.+)$", line)
        if text_match:
            prefix = line[:line.find("text=")]
            text = text_match.group(1)
            click.echo(click.style(prefix, fg="green") + click.style(f"text={text}", fg="cyan"))
        else:
            click.echo(click.style(line, fg="green"))
    else:
        click.echo(line)


def _show_stats(hours: int):
    print_header(f"Log Stats (last {hours} hours)")

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
    except Exception as e:
        click.echo(error(f"Failed to read log: {e}"))
        return

    stats = analyze_logs(all_lines, hours)

    if stats["last_model_type"] or stats["last_model"]:
        click.echo(key_value("Engine", stats["last_model_type"] or "unknown"))
        click.echo(key_value("Model", stats["last_model"] or "unknown"))
        click.echo(f"  {'─' * 35}")

    click.echo(key_value("Total Entries", str(stats["total"])))
    click.echo(key_value("Transcribed", click.style(str(stats["transcriptions"]), fg="green") if stats["transcriptions"] else "0"))
    click.echo(key_value("Errors", click.style(str(stats["errors"]), fg="red" if stats["errors"] else None)))
    click.echo(key_value("Warnings", click.style(str(stats["warnings"]), fg="yellow" if stats["warnings"] else None)))

    if stats["by_status"]:
        click.echo(f"\n  {'─' * 35}")
        click.echo("  Status Codes:")
        for status, count in sorted(stats["by_status"].items()):
            color = "red" if status >= 500 else ("yellow" if status >= 400 else None)
            click.echo(f"    {status}: {click.style(str(count), fg=color)}")

    if stats["performance"]:
        avg_ms = sum(stats["performance"]) / len(stats["performance"])
        max_ms = max(stats["performance"])
        click.echo(f"\n  {'─' * 35}")
        click.echo("  Performance:")
        click.echo(key_value("Avg Latency", f"{avg_ms:.0f}ms"))
        click.echo(key_value("Max Latency", f"{max_ms}ms"))

    if stats["api_errors"]:
        click.echo(f"\n  {'─' * 35}")
        click.echo("  Recent Errors:")
        for err in stats["api_errors"][-5:]:
            click.echo(click.style(f"    [{err['time']}] {err['status']} - {err['msg']}", fg="red"))

    print_footer()
