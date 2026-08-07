# coding=utf-8
"""OctoASR doctor - environment check"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import click

from octoasr.cli.utils.config import load_config, config_exists
from octoasr.cli.utils.console import success, error, warning, print_header, print_footer
from octoasr.cli.utils.process import is_port_in_use


def check_python() -> tuple[bool, str]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        return True, f"Python {version}"
    return False, f"Python {version} (requires 3.10+)"


def check_ffmpeg() -> tuple[bool, str]:
    if shutil.which("ffmpeg"):
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version_line = result.stdout.split("\n")[0] if result.stdout else ""
            if "version" in version_line.lower():
                parts = version_line.split()
                for i, p in enumerate(parts):
                    if p.lower() == "version" and i + 1 < len(parts):
                        return True, f"ffmpeg {parts[i + 1]}"
            return True, "ffmpeg (installed)"
        except Exception:
            return True, "ffmpeg (installed)"
    return False, "ffmpeg (not installed)"


def check_ffprobe() -> tuple[bool, str]:
    if shutil.which("ffprobe"):
        return True, "ffprobe (installed)"
    return False, "ffprobe (not installed)"


def check_mlx() -> tuple[bool, str]:
    try:
        import mlx

        version = getattr(mlx, "__version__", "unknown")
        return True, f"MLX {version}"
    except ImportError:
        return False, "MLX (not installed)"


def check_config() -> tuple[bool, str]:
    if config_exists():
        return True, "Config file exists"
    return False, "Config file not found"


def check_model(model_path: str, model_type: str) -> tuple[bool, str]:
    path = Path(model_path)
    if path.exists() and (path / "config.json").exists():
        return True, f"{model_type} model: {path.name}"
    return False, f"{model_type} model: {path.name} (not found)"


def check_port(port: int) -> tuple[bool, str]:
    if is_port_in_use(port):
        return False, f"Port {port} is in use"
    return True, f"Port {port} available"


@click.command()
def doctor():
    """Environment check"""

    print_header("Environment Check")

    all_passed = True

    checks = [
        check_python(),
        check_ffmpeg(),
        check_ffprobe(),
        check_mlx(),
        check_config(),
    ]

    if config_exists():
        config = load_config()
        if config.get("models", {}).get("asr"):
            checks.append(check_model(config["models"]["asr"], "ASR"))
        if config.get("models", {}).get("vad"):
            checks.append(check_model(config["models"]["vad"], "VAD"))
        if config.get("models", {}).get("mention"):
            checks.append(check_model(config["models"]["mention"], "Mention"))
        port = config.get("server", {}).get("port", 8787)
        checks.append(check_port(port))

    for passed, message in checks:
        if passed:
            click.echo(success(message))
        else:
            click.echo(error(message))
            all_passed = False

    print_footer()

    from octoasr.cli.utils.update_checker import check_and_notify
    check_and_notify()

    if all_passed:
        click.echo(success("All checks passed\n"))
    else:
        click.echo(warning("Some checks failed, please fix the issues above\n"))
        raise SystemExit(1)
