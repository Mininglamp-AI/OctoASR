# coding=utf-8
"""mano-asr service commands: start/stop/restart/status"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from manoasr.cli.utils.config import load_config, config_exists, save_config, get_default_config
from manoasr.cli.utils.console import (
    success,
    error,
    warning,
    info,
    bold,
    key_value,
    print_header,
    print_footer,
)
from manoasr.cli.utils.process import (
    get_pid,
    save_pid,
    stop_process,
    is_port_in_use,
    get_port_process,
    get_process_uptime,
)
from manoasr.cli.utils.constants import DEFAULT_PORT, LOG_FILE, CONFIG_DIR, LOG_DIR, MODEL_TYPES, DEFAULT_MODEL_TYPE
from manoasr.cli.utils.download import ensure_default_models, ensure_model, find_model_in_dirs


def get_configured_port() -> int:
    if config_exists():
        config = load_config()
        return config.get("server", {}).get("port", DEFAULT_PORT)
    return DEFAULT_PORT


def _do_init() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    asr_path, vad_path = ensure_default_models(DEFAULT_MODEL_TYPE)

    config = get_default_config()
    config["models"]["asr"] = str(asr_path)
    if vad_path:
        config["models"]["vad"] = str(vad_path)
    else:
        config["models"]["vad"] = None
    save_config(config)

    asr_name = Path(config["models"]["asr"]).name
    click.echo(success(f"Auto-initialization complete"))
    click.echo(f"    ASR model: {asr_name}")
    if config["models"].get("vad"):
        vad_name = Path(config["models"]["vad"]).name
        click.echo(f"    VAD model: {vad_name}")
    click.echo(f"    Port: {config['server']['port']}")

    return config


def _check_service_health(port: int, timeout: float = 2.0) -> tuple[bool, str]:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            pass
        return True, "healthy"
    except socket.timeout:
        return False, "timeout"
    except ConnectionRefusedError:
        return False, "connection refused"
    except Exception as e:
        return False, str(e)


@click.command()
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (for debugging)")
@click.option("--debug", "-d", is_flag=True, help="Debug mode (log transcription results)")
def start(foreground: bool, debug: bool):
    """Start mano-asr service (auto-init on first run)"""

    if not config_exists():
        click.echo(info("First run, initializing..."))
        _do_init()
        click.echo("")

    config = load_config()
    port = config.get("server", {}).get("port", DEFAULT_PORT)

    asr_path = Path(config.get("models", {}).get("asr", ""))
    if not asr_path.exists() or not (asr_path / "config.json").exists():
        model_type_key = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
        spec = MODEL_TYPES.get(model_type_key, {})
        model_name = spec.get("default_model", asr_path.name)
        click.echo(info("ASR model not found, downloading..."))
        asr_path = ensure_model(model_name, is_vad=False)
        config["models"]["asr"] = str(asr_path)
        save_config(config)

    vad_path_str = config.get("models", {}).get("vad")
    if vad_path_str:
        vad_path = Path(vad_path_str)
        if not vad_path.exists():
            click.echo(info("VAD model not found, downloading..."))
            try:
                from manoasr.cli.utils.constants import DEFAULT_VAD_MODEL
                vad_path = ensure_model(DEFAULT_VAD_MODEL, is_vad=True)
                config["models"]["vad"] = str(vad_path)
                save_config(config)
            except SystemExit:
                click.echo(warning("VAD model unavailable, continuing without VAD"))
                config["models"]["vad"] = None
                save_config(config)

    pid = get_pid()
    if pid:
        healthy, health_msg = _check_service_health(port)
        if healthy:
            click.echo(warning(f"mano-asr service is already running (PID: {pid})"))
            return
        else:
            port_info = get_port_process(port)
            if port_info and port_info[0] != pid:
                click.echo(warning(f"Service process exists (PID: {pid}) but port is occupied"))
                click.echo(error(f"Port {port} is in use by: {port_info[1]} (PID: {port_info[0]})"))
                click.echo(f"\n    Solution:")
                click.echo(f"      1. Kill the process: kill {port_info[0]}")
                click.echo(f"      2. Then restart: mano-asr restart")
                raise SystemExit(1)
            else:
                click.echo(warning(f"Service process exists (PID: {pid}) but not responding, restarting..."))
                stop_process(pid)

    if is_port_in_use(port):
        process_info = get_port_process(port)
        click.echo(error(f"Port {port} is already in use"))
        if process_info:
            pid, name = process_info
            click.echo(f"    Process: {name} (PID: {pid})")
        click.echo(f"\n    Solution:")
        click.echo(f"      1. Kill the process: kill {process_info[0] if process_info else '<PID>'}")
        click.echo(f"      2. Or change port: mano-asr port <port>")
        raise SystemExit(1)

    if foreground:
        _run_server(config, port, debug)
    else:
        _start_daemon(config, port, debug)

    from manoasr.cli.utils.update_checker import check_and_notify
    check_and_notify()


def _run_server(config: dict, port: int, debug: bool = False):
    model_type_key = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
    spec = MODEL_TYPES.get(model_type_key, {})
    asr_name = Path(config["models"]["asr"]).name

    click.echo(success("mano-asr service started (foreground)"))
    click.echo(f"    Address: http://127.0.0.1:{port}")
    click.echo(f"    Engine:  {model_type_key} ({spec.get('label', model_type_key)})")
    click.echo(f"    Model:   {asr_name}")
    if debug:
        click.echo(f"    Debug:   enabled")
    click.echo(f"    Press Ctrl+C to stop\n")

    import uvicorn

    from manoasr.cli.utils.constants import PROJECT_ROOT

    sys.path.insert(0, str(PROJECT_ROOT))

    import server

    server.MODEL_PATH = config["models"]["asr"]
    server.VAD_MODEL_PATH = config["models"].get("vad")
    server.HOST = "0.0.0.0"
    server.PORT = port
    server.LOAD_ON_STARTUP = config.get("server", {}).get("load_on_startup", True)
    server.DEBUG_MODE = debug

    model_type_key = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
    spec = MODEL_TYPES.get(model_type_key)
    if spec:
        server.MODEL_TYPE = spec["server_type"]

    uvicorn.run(server.app, host="0.0.0.0", port=port, log_level="info")


def _start_daemon(config: dict, port: int, debug: bool = False):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    daemon_path = Path(__file__).parent.parent / "daemon.py"

    cmd = [
        sys.executable,
        str(daemon_path),
        "--model",
        config["models"]["asr"],
        "--port",
        str(port),
    ]
    if config["models"].get("vad"):
        cmd.extend(["--vad", config["models"]["vad"]])

    model_type_key = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
    spec = MODEL_TYPES.get(model_type_key)
    if spec:
        cmd.extend(["--model-type", spec["server_type"]])

    if config.get("server", {}).get("load_on_startup", True):
        cmd.append("--load-on-startup")
    if debug:
        cmd.append("--debug")

    with open(LOG_FILE, "a") as log:
        process = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    save_pid(process.pid)

    model_type_key = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
    spec = MODEL_TYPES.get(model_type_key, {})
    asr_name = Path(config["models"]["asr"]).name

    click.echo(success("mano-asr service started"))
    click.echo(f"    Address: http://127.0.0.1:{port}")
    click.echo(f"    PID:     {process.pid}")
    click.echo(f"    Engine:  {model_type_key} ({spec.get('label', model_type_key)})")
    click.echo(f"    Model:   {asr_name}")
    if debug:
        click.echo(f"    Debug:   enabled")


@click.command()
def stop():
    """Stop mano-asr service"""

    pid = get_pid()
    if not pid:
        click.echo(warning("mano-asr service is not running"))
        return

    click.echo(info("Stopping service..."))

    if stop_process(pid):
        click.echo(success("mano-asr service stopped"))
    else:
        click.echo(error(f"Failed to stop process {pid}, please kill manually: kill -9 {pid}"))
        raise SystemExit(1)


@click.command()
@click.option("--debug", "-d", is_flag=True, help="Debug mode (log transcription results)")
@click.pass_context
def restart(ctx, debug: bool):
    """Restart mano-asr service"""

    pid = get_pid()
    if pid:
        click.echo(info("Stopping service..."))
        if not stop_process(pid):
            click.echo(error("Failed to stop service"))
            raise SystemExit(1)
        click.echo(success("Service stopped"))

    click.echo(info("Starting service..."))
    ctx.invoke(start, foreground=False, debug=debug)


@click.command()
def status():
    """Show mano-asr service status"""

    print_header("mano-asr Service Status")

    pid = get_pid()
    port = get_configured_port()

    if pid:
        uptime = get_process_uptime(pid) or "unknown"
        healthy, health_msg = _check_service_health(port)

        if healthy:
            click.echo(key_value("Status", bold("running")))
        else:
            click.echo(key_value("Status", warning(f"unhealthy ({health_msg})")))
            port_info = get_port_process(port)
            if port_info and port_info[0] != pid:
                click.echo(warning(f"  Port {port} is in use by: {port_info[1]} (PID: {port_info[0]})"))
                click.echo(info(f"    Suggestion: mano-asr restart or kill {port_info[0]}"))

        click.echo(key_value("PID", str(pid)))
        click.echo(key_value("Port", str(port)))
        click.echo(key_value("Uptime", uptime))

        if config_exists():
            config = load_config()
            model_type_key = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
            spec = MODEL_TYPES.get(model_type_key, {})
            click.echo(f"  {'─' * 35}")
            click.echo(key_value("Engine", f"{model_type_key} ({spec.get('label', model_type_key)})"))
            click.echo(key_value("ASR Model", Path(config["models"]["asr"]).name))
            if config["models"].get("vad"):
                click.echo(key_value("VAD Model", Path(config["models"]["vad"]).name))
    else:
        click.echo(key_value("Status", "not running"))

    print_footer()

    from manoasr.cli.utils.update_checker import check_and_notify
    check_and_notify()
