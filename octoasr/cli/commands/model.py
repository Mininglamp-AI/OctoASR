# coding=utf-8
"""OctoASR model - model management"""

from __future__ import annotations

import json
from pathlib import Path

import click

from octoasr.cli.utils.config import load_config, save_config, config_exists, get_models_dir
from octoasr.cli.utils.console import success, error, warning, info, print_header, print_footer, interactive_select
from octoasr.cli.utils.constants import (
    HF_REPO_MAP,
    HOMEBREW_MODELS_DIR,
    LOCAL_MODELS_DIR,
    DEFAULT_MENTION_MODEL,
    MENTION_AUTO_UPGRADE_CONFIG_KEY,
    MODELSCOPE_REPO_MAP,
    MODEL_TYPES,
    DEFAULT_MODEL_TYPE,
    USER_MODELS_DIR,
    model_namespace,
)
from octoasr.cli.utils.process import get_pid, stop_process


def find_models(models_dir: Path) -> dict:
    result = {"asr": [], "vad": [], "mention": []}

    if not models_dir.exists():
        return result

    def scan_dir(directory: Path):
        for path in directory.iterdir():
            if not path.is_dir():
                continue
            if (path / "config.json").exists():
                name = path.name
                category = _model_category(name, path)
                if category:
                    result[category].append((name, path))
            else:
                scan_dir(path)

    scan_dir(models_dir)
    return result


def get_available_models() -> dict:
    result = {"asr": [], "vad": [], "mention": []}
    seen = set()
    for models_dir in [USER_MODELS_DIR, HOMEBREW_MODELS_DIR, LOCAL_MODELS_DIR]:
        if models_dir.exists():
            found = find_models(models_dir)
            for category in ("asr", "vad", "mention"):
                for name, path in found[category]:
                    key = (category, name)
                    if key not in seen:
                        result[category].append((name, path))
                        seen.add(key)
    return result


def _model_category(model_name: str, model_path: Path) -> str | None:
    lower_name = model_name.lower()
    if "vad" in lower_name or "fsmn" in lower_name:
        return "vad"
    if "mention" in lower_name:
        return "mention"

    try:
        with open(model_path / "config.json", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    model_type = data.get("model_type") or data.get("thinker_config", {}).get("model_type")
    if model_type:
        for spec in MODEL_TYPES.values():
            if spec["server_type"] == model_type:
                return "asr"
    return None


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


def _download_known_model(model_name: str) -> Path | None:
    if model_name not in HF_REPO_MAP and model_name not in MODELSCOPE_REPO_MAP:
        return None
    from octoasr.cli.utils.download import ensure_model
    return ensure_model(model_name, is_vad=("vad" in model_name.lower() or "fsmn" in model_name.lower()))


def switch_engine(config: dict, engine_key: str) -> None:
    spec = MODEL_TYPES[engine_key]
    config["models"]["type"] = engine_key

    model_path = resolve_model_path(spec["default_model"])
    if not model_path:
        click.echo(info(f"Downloading {spec['label']} model..."))
        from octoasr.cli.utils.download import ensure_model
        model_path = ensure_model(spec["default_model"], is_vad=False)

    config["models"]["asr"] = str(model_path)
    save_config(config)


def _infer_engine_type(model_path: Path) -> str:
    """Infer the engine key (funasr / qwen3-asr) from a model's config.json.

    Maps the server-side model_type back to the MODEL_TYPES key. Falls back to
    the default engine when the config is missing or unrecognized.
    """
    config_file = model_path / "config.json"
    detected = None
    try:
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
        detected = data.get("model_type")
        if not detected:
            detected = data.get("thinker_config", {}).get("model_type")
    except Exception:
        pass

    if detected:
        for key, spec in MODEL_TYPES.items():
            if spec["server_type"] == detected:
                return key
    return DEFAULT_MODEL_TYPE


def switch_asr_model(config: dict, model_name: str, model_path: Path) -> None:
    """Switch to a specific ASR model, setting both its path and engine type."""
    config["models"]["type"] = _infer_engine_type(model_path)
    config["models"]["asr"] = str(model_path)
    save_config(config)


def restart_service_if_running() -> None:
    pid = get_pid()
    if not pid:
        return

    click.echo(info("Restarting service..."))
    if not stop_process(pid):
        click.echo(warning("Failed to stop service, please restart manually: octoasr restart"))
        return

    from octoasr.cli.commands.service import _start_daemon, get_configured_port

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
        click.echo(error("Not initialized, please run: octoasr start"))
        raise SystemExit(1)

    config = load_config()
    current_asr = Path(config.get("models", {}).get("asr", "")).name

    models = get_available_models()
    asr_models = models["asr"]

    if not asr_models:
        click.echo(error("No ASR models found. Run 'octoasr start' to download one."))
        raise SystemExit(1)

    options = [
        {"key": name, "label": name, "path": path}
        for name, path in asr_models
    ]

    chosen = interactive_select("Select ASR Model", options, current=current_asr)

    if chosen is None or chosen["key"] == current_asr:
        return

    switch_asr_model(config, chosen["key"], chosen["path"])
    click.echo(success(f"Switched ASR model: {chosen['key']}"))
    restart_service_if_running()


@model.command("info")
def model_info():
    """Show current model info"""

    if not config_exists():
        click.echo(error("Not initialized, please run: octoasr start"))
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
    if config["models"].get("mention"):
        click.echo(f"  Mention: {Path(config['models']['mention']).name}")
    else:
        click.echo(f"  Mention: disabled")
    print_footer()


@model.command("list")
def model_list():
    """List available models"""

    if not config_exists():
        click.echo(error("Not initialized, please run: octoasr start"))
        raise SystemExit(1)

    config = load_config()
    current_type = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
    current_asr = Path(config["models"]["asr"]).name
    current_vad = Path(config["models"]["vad"]).name if config["models"].get("vad") else None
    current_mention = Path(config["models"]["mention"]).name if config["models"].get("mention") else None

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

    if models["mention"]:
        click.echo("\n  Mention Models:")
        for name, path in models["mention"]:
            marker = "*" if name == current_mention else " "
            suffix = " (active)" if name == current_mention else ""
            click.echo(f"    {marker} {name}{suffix}")

    print_footer()


@model.command("use")
@click.argument("model_name")
@click.option("--type", "-t", "model_type", type=click.Choice(["asr", "vad", "mention"]), default=None)
def model_use(model_name: str, model_type: str):
    """Switch model

    MODEL_NAME: Model name or engine type (funasr / qwen3-asr)
    """

    if not config_exists():
        click.echo(error("Not initialized, please run: octoasr start"))
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
        for category in ("asr", "vad", "mention"):
            for name, path in models[category]:
                if name == model_name:
                    found_path = path
                    found_type = category
                    break
            if found_path:
                break
    else:
        for name, path in models[model_type]:
            if name == model_name:
                found_path = path
                break

    if not found_path:
        found_path = _download_known_model(model_name)
        if found_path:
            found_type = model_type
            if found_type is None:
                found_type = "vad" if "vad" in model_name.lower() or "fsmn" in model_name.lower() else "mention" if "mention" in model_name.lower() else "asr"
        else:
            click.echo(error(f"Model not found: {model_name}"))
            click.echo(info("Run 'octoasr model list' to see available models"))
            raise SystemExit(1)

    config = load_config()
    if found_type == "asr":
        switch_asr_model(config, model_name, found_path)
    else:
        config["models"][found_type] = str(found_path)
        if found_type == "mention":
            config.setdefault("migration", {})[
                MENTION_AUTO_UPGRADE_CONFIG_KEY
            ] = DEFAULT_MENTION_MODEL
        save_config(config)

    type_name = {"asr": "ASR", "vad": "VAD", "mention": "Mention"}[found_type]
    click.echo(success(f"Switched {type_name} model: {model_name}"))
    click.echo(warning("Restart required to take effect: octoasr restart"))
