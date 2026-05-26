# coding=utf-8
"""Process management utilities"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from typing import Optional, Tuple

from .constants import PID_FILE, DEFAULT_PORT


def get_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return None


def save_pid(pid: int) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))


def remove_pid() -> None:
    PID_FILE.unlink(missing_ok=True)


def is_running() -> bool:
    return get_pid() is not None


def get_process_uptime(pid: int) -> Optional[str]:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "etime="],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            raw = result.stdout.strip()
            return format_uptime(raw)
    except Exception:
        pass
    return None


def format_uptime(etime: str) -> str:
    parts = etime.replace("-", ":").split(":")
    parts = [int(p) for p in parts]

    if len(parts) == 2:
        mins, secs = parts
        return f"{mins}m"
    elif len(parts) == 3:
        hours, mins, secs = parts
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"
    elif len(parts) == 4:
        days, hours, mins, secs = parts
        if days > 0:
            return f"{days}d {hours}h"
        return f"{hours}h {mins}m"

    return etime


def stop_process(pid: int, timeout: int = 10) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)

        for _ in range(timeout * 10):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                remove_pid()
                return True

        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)
        remove_pid()
        return True
    except ProcessLookupError:
        remove_pid()
        return True
    except PermissionError:
        return False


def get_port_process(port: int) -> Optional[Tuple[int, str]]:
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            pid = int(result.stdout.strip().split("\n")[0])
            ps_result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
            )
            name = ps_result.stdout.strip() if ps_result.returncode == 0 else "unknown"
            return (pid, name)
    except Exception:
        pass
    return None


def is_port_in_use(port: int = DEFAULT_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True
