# coding=utf-8
"""mano-asr model - model management"""

from __future__ import annotations

from pathlib import Path

import click

from manoasr.cli.utils.config import load_config, save_config, config_exists, get_models_dir
from manoasr.cli.utils.console import success, error, warning, info, print_header, print_footer, interactive_select
from manoasr.cli.utils.constants import HOMEBREW_MODELS_DIR, LOCAL_MODELS_DIR, USER_MODELS_DIR, MODEL_TYPES, DEFAULT_MODEL_TYPE, model_namespace
from manoasr.cli.utils.process import get_pid, stop_process


def find_models(models_dir: Path) -> dict:
    result = {"asr": [], "vad": []}

    if not models_dir.exists():
        return result

    def scan_dir(directory: Path):
        for path in directory.iterdir():
            if not path.is_dir():
                continue
            if (path / "config.json").exists():
                name = path.name
                if "vad" in name.lower() or "fsmn" in name.lower():
                    result["vad"].append((name, path))
                else:
                    result["asr"].append((name, path))
            else:
                scan_dir(path)

    scan_dir(models_dir)
    return result


def get_available_models() -> dict:
    result = {"asr": [], "vad": []}
    seen = set()
    for models_dir in [USER_MODELS_DIR, HOMEBREW_MODELS_DIR, LOCAL_MODELS_DIR]:
        if models_dir.exists():
            found = find_models(models_dir)
            for category in ("asr", "vad"):
                for name, path in found[category]:
                    if name not in seen:
                        result[category].append((name, path))
                        seen.add(name)
    return result


def resolve_model_path(model_name: str) -> Path | None:
    for models_dir in [USER_MODELS_DIR, HOMEBREW_MODELS_DIR, LOCAL_MODELS_DIR]:
        if not models_dir.exists():
            continue
        candidate = models_dir / model_namespace(model_name) / model_name
        if candidate.exists():
            return candidate
        candidate = models_dir / "mlx-community" / model_name
        if candidate.exists():
            return candidate
        candidate = models_dir / model_name
        if candidate.exists():
            return candidate
    return None


def switch_engine(config: dict, engine_key: str) -> None:
    spec = MODEL_TYPES[engine_key]
    config["models"]["type"] = engine_key

    model_path = resolve_model_path(spec["default_model"])
    if not model_path:
        click.echo(info(f"Downloading {spec['label']} model..."))
        from manoasr.cli.utils.download import ensure_model
        model_path = ensure_model(spec["default_model"], is_vad=False)

    config["models"]["asr"] = str(model_path)
    save_config(config)


def restart_service_if_running() -> None:
    pid = get_pid()
    if not pid:
        return

    click.echo(info("Restarting service..."))
    if not stop_process(pid):
        click.echo(warning("Failed to stop service, please restart manually: mano-asr restart"))
        return

    from manoasr.cli.commands.service import _start_daemon, get_configured_port

    config = load_config()
    port = get_configured_port()
    debug = False
    _start_daemon(config, port, debug)


@click.group(invoke_without_command=True)
@click.pass_context
def model(ctx):
    """Model management"""
    if ctx.invoked_subcommand is not None:
        return

    if not config_exists():
        click.echo(error("Not initialized, please run: mano-asr start"))
        raise SystemExit(1)

    config = load_config()
    current = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)

    options = [
        {"key": key, "label": f"{key:<12}{spec['label']}"}
        for key, spec in MODEL_TYPES.items()
    ]

    chosen = interactive_select("Select ASR Engine", options, current=current)

    if chosen is None or chosen["key"] == current:
        return

    switch_engine(config, chosen["key"])
    spec = MODEL_TYPES[chosen["key"]]
    click.echo(success(f"Switched ASR engine: {chosen['key']} ({spec['label']})"))
    restart_service_if_running()


@model.command("info")
def model_info():
    """Show current model info"""

    if not config_exists():
        click.echo(error("Not initialized, please run: mano-asr start"))
        raise SystemExit(1)

    config = load_config()
    current_type = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
    spec = MODEL_TYPES.get(current_type, {})

    print_header("Current Model Config")
    click.echo(f"  Engine: {current_type} ({spec.get('label', current_type)})")
    click.echo(f"  ASR:  {Path(config['models']['asr']).name}")
    if config["models"].get("vad"):
        click.echo(f"  VAD:  {Path(config['models']['vad']).name}")
    else:
        click.echo(f"  VAD:  disabled")
    print_footer()


@model.command("list")
def model_list():
    """List available models"""

    if not config_exists():
        click.echo(error("Not initialized, please run: mano-asr start"))
        raise SystemExit(1)

    config = load_config()
    current_type = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
    current_asr = Path(config["models"]["asr"]).name
    current_vad = Path(config["models"]["vad"]).name if config["models"].get("vad") else None

    models = get_available_models()

    print_header("Available Models")

    click.echo(f"  Engine: {current_type}")
    click.echo("")

    click.echo("  ASR Models:")
    if models["asr"]:
        for name, path in models["asr"]:
            marker = "*" if name == current_asr else " "
            suffix = " (active)" if name == current_asr else ""
            click.echo(f"    {marker} {name}{suffix}")
    else:
        click.echo("    (none)")

    if models["vad"]:
        click.echo("\n  VAD Models:")
        for name, path in models["vad"]:
            marker = "*" if name == current_vad else " "
            suffix = " (active)" if name == current_vad else ""
            click.echo(f"    {marker} {name}{suffix}")

    print_footer()


@model.command("use")
@click.argument("model_name")
@click.option("--type", "-t", "model_type", type=click.Choice(["asr", "vad"]), default=None)
def model_use(model_name: str, model_type: str):
    """Switch model

    MODEL_NAME: Model name or engine type (funasr / qwen3-asr)
    """

    if not config_exists():
        click.echo(error("Not initialized, please run: mano-asr start"))
        raise SystemExit(1)

    if model_name in MODEL_TYPES:
        config = load_config()
        switch_engine(config, model_name)
        spec = MODEL_TYPES[model_name]
        click.echo(success(f"Switched ASR engine: {model_name} ({spec['label']})"))
        restart_service_if_running()
        return

    models = get_available_models()

    found_path = None
    found_type = model_type

    if not model_type:
        for name, path in models["asr"]:
            if name == model_name:
                found_path = path
                found_type = "asr"
                break

        if not found_path:
            for name, path in models["vad"]:
                if name == model_name:
                    found_path = path
                    found_type = "vad"
                    break
    else:
        for name, path in models[model_type]:
            if name == model_name:
                found_path = path
                break

    if not found_path:
        click.echo(error(f"Model not found: {model_name}"))
        click.echo(info("Run 'mano-asr model list' to see available models"))
        raise SystemExit(1)

    config = load_config()
    config["models"][found_type] = str(found_path)
    save_config(config)

    type_name = "ASR" if found_type == "asr" else "VAD"
    click.echo(success(f"Switched {type_name} model: {model_name}"))
    click.echo(warning("Restart required to take effect: mano-asr restart"))
