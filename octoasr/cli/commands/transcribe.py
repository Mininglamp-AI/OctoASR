# coding=utf-8
"""octoasr transcribe - transcribe audio files"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import requests

from octoasr.cli.utils.config import load_config, config_exists
from octoasr.cli.utils.console import error
from octoasr.cli.utils.constants import DEFAULT_PORT, ALLOWED_EXTENSIONS, MODEL_TYPES, DEFAULT_MODEL_TYPE
from octoasr.cli.utils.process import get_pid


@click.command()
@click.argument("audio_file", type=click.Path(exists=True))
@click.option("-w", "--hotwords", default=None, help="Hotwords, comma-separated")
@click.option("-f", "--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.option("-o", "--output", "output_file", type=click.Path(), default=None, help="Output to file")
def transcribe(audio_file: str, hotwords: str, output_format: str, output_file: str):
    """Transcribe audio file

    AUDIO_FILE: Path to audio file
    """
    audio_path = Path(audio_file)

    if audio_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        click.echo(error(f"Unsupported audio format: {audio_path.suffix}"))
        click.echo(f"    Supported formats: {', '.join(ALLOWED_EXTENSIONS)}")
        raise SystemExit(1)

    pid = get_pid()
    if pid:
        result = _transcribe_via_api(audio_path, hotwords, output_format)
    else:
        result = _transcribe_directly(audio_path, hotwords, output_format)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result)
        click.echo(f"Result saved to: {output_file}")
    else:
        click.echo(result)


def _transcribe_via_api(audio_path: Path, hotwords: str, output_format: str) -> str:
    if not config_exists():
        port = DEFAULT_PORT
    else:
        config = load_config()
        port = config.get("server", {}).get("port", DEFAULT_PORT)

    url = f"http://127.0.0.1:{port}/v1/voice/transcribe"

    try:
        with open(audio_path, "rb") as f:
            files = {"audio": (audio_path.name, f, "audio/wav")}
            data = {}
            if hotwords:
                data["personal_context"] = hotwords

            response = requests.post(url, files=files, data=data, timeout=300)
            response.raise_for_status()

            result = response.json()
            if output_format == "json":
                return json.dumps(result, ensure_ascii=False, indent=2)
            return result.get("text", "")
    except requests.exceptions.ConnectionError:
        click.echo(error("Cannot connect to service, make sure it is running"))
        click.echo("    Run 'octoasr start' to start the service")
        raise SystemExit(1)
    except requests.exceptions.Timeout:
        click.echo(error("Request timed out"))
        raise SystemExit(1)
    except Exception as e:
        click.echo(error(f"Transcription failed: {e}"))
        raise SystemExit(1)


def _transcribe_directly(audio_path: Path, hotwords: str, output_format: str) -> str:
    if not config_exists():
        click.echo(error("Not initialized, please run: octoasr start"))
        raise SystemExit(1)

    config = load_config()

    from octoasr.cli.utils.constants import PROJECT_ROOT

    sys.path.insert(0, str(PROJECT_ROOT))

    from core.auto_model import AutoModel

    model_type_key = config.get("models", {}).get("type", DEFAULT_MODEL_TYPE)
    spec = MODEL_TYPES.get(model_type_key)
    server_type = spec["server_type"] if spec else "funasr"

    model = AutoModel(
        model=config["models"]["asr"],
        model_type=server_type,
        vad_model=config["models"].get("vad"),
    )

    hotword_list = []
    if hotwords:
        hotword_list = ["@"] + [w.strip() for w in hotwords.split(",") if w.strip()][:100]

    text = model.generate(
        audio_path,
        hotwords=hotword_list if hotword_list else None,
        task="translate",
        target_language="zh",
        merge_vad=True,
    )

    if output_format == "json":
        result = {
            "text": text,
            "model": Path(config["models"]["asr"]).name,
            "engine": model_type_key,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    return text
