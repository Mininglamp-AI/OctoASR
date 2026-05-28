# coding=utf-8
"""Manage torch/torchaudio installation in persistent user directory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from .constants import CONFIG_DIR

TORCH_LIB_DIR = CONFIG_DIR / "lib"
PYTHON_VERSION_FILE = TORCH_LIB_DIR / ".python_version"


def _current_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _is_torch_installed() -> bool:
    saved = TORCH_LIB_DIR / ".python_version"
    if saved.exists():
        saved_version = saved.read_text().strip()
        if saved_version != _current_python_version():
            return False

    original_path = sys.path[:]
    sys.path.insert(0, str(TORCH_LIB_DIR))
    try:
        import importlib
        importlib.import_module("torch")
        importlib.import_module("torchaudio")
        return True
    except ImportError:
        return False
    finally:
        sys.path[:] = original_path


def ensure_torch() -> bool:
    """Ensure torch and torchaudio are installed. Returns True if available."""
    if _is_torch_installed():
        add_torch_to_path()
        return True

    click.echo("  → Installing VAD dependencies (torch, torchaudio)...")
    click.echo("    This is a one-time download (~200 MB), please wait...")

    TORCH_LIB_DIR.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.check_call(
            [
                sys.executable, "-m", "pip", "install",
                "--target", str(TORCH_LIB_DIR),
                "--upgrade",
                "torch",
                "torchaudio",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ""
        click.echo(f"  ✗ Failed to install torch: {stderr[:200]}")
        click.echo("    Manual install: pip install --target ~/.mano-asr/lib torch torchaudio")
        return False

    PYTHON_VERSION_FILE.write_text(_current_python_version())

    add_torch_to_path()
    click.echo("  ✓ VAD dependencies installed")
    return True


def add_torch_to_path() -> None:
    """Add the persistent torch lib directory to sys.path if not already present."""
    lib_str = str(TORCH_LIB_DIR)
    if lib_str not in sys.path:
        sys.path.insert(0, lib_str)
