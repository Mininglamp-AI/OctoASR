# coding=utf-8
"""Model download and discovery utilities."""

from __future__ import annotations

import tarfile
import tempfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request

import click

from .constants import (
    USER_MODELS_DIR,
    HOMEBREW_MODELS_DIR,
    LOCAL_MODELS_DIR,
    HF_REPO_MAP,
    MODELSCOPE_REPO_MAP,
    GITHUB_RELEASE_BASE_URL,
    MODEL_TYPES,
    DEFAULT_VAD_MODEL,
    VERSION,
    model_namespace,
)
from .console import success, error, info, warning


def _detect_preferred_source() -> str:
    """Detect network environment, returns 'hf' or 'modelscope'."""
    import os
    import socket

    if os.environ.get("HF_ENDPOINT"):
        return "hf"

    try:
        socket.create_connection(("huggingface.co", 443), timeout=3)
        return "hf"
    except (socket.timeout, OSError):
        return "modelscope"


def _is_model_complete(model_dir: Path) -> bool:
    if not model_dir.exists() or not (model_dir / "config.json").exists():
        return False
    has_weights = (
        any(model_dir.glob("*.safetensors"))
        or any(model_dir.glob("*.npz"))
        or any(model_dir.glob("*.mvn"))
    )
    if not has_weights:
        return False
    temp_dir = model_dir / "._____temp"
    if temp_dir.exists() and any(temp_dir.iterdir()):
        return False
    return True


def find_model_in_dirs(model_name: str, is_vad: bool = False) -> Optional[Path]:
    search_dirs = [USER_MODELS_DIR, HOMEBREW_MODELS_DIR, LOCAL_MODELS_DIR]
    for models_dir in search_dirs:
        if not models_dir.exists():
            continue
        if not is_vad:
            # The model's own namespace (HF org), e.g. Mininglamp-2718/ or mlx-community/.
            candidate = models_dir / model_namespace(model_name) / model_name
            if _is_model_complete(candidate):
                return candidate
            # Legacy layout: everything used to live under mlx-community/.
            candidate = models_dir / "mlx-community" / model_name
            if _is_model_complete(candidate):
                return candidate
        candidate = models_dir / model_name
        if _is_model_complete(candidate):
            return candidate
    return None


def download_from_hf(model_name: str, target_dir: Path) -> Path:
    repo_id = HF_REPO_MAP.get(model_name)
    if not repo_id:
        raise ValueError(f"No HuggingFace repo ID configured for model: {model_name}")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise RuntimeError(
            "huggingface_hub is required for model download. "
            "Install with: pip install huggingface_hub"
        )

    is_vad = "vad" in model_name.lower() or "fsmn" in model_name.lower()
    if is_vad:
        local_dir = target_dir / model_name
    else:
        local_dir = target_dir / model_namespace(model_name) / model_name

    local_dir.parent.mkdir(parents=True, exist_ok=True)

    click.echo(f"    Source: HuggingFace Hub ({repo_id})")

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        allow_patterns=["*.json", "*.safetensors", "*.py", "*.model",
                        "*.tiktoken", "*.txt", "*.yaml", "*.npz", "*.mvn"],
    )

    if not _is_model_complete(local_dir):
        raise RuntimeError(f"Download incomplete: model weights not found in {local_dir}")

    from .update_checker import record_model_sha
    record_model_sha(model_name, repo_id, source="hf")

    return local_dir


def _get_modelscope_total_size(repo_id: str) -> int:
    try:
        from modelscope.hub.api import HubApi
        api = HubApi()
        files = api.get_model_files(repo_id)
        return sum(f.get("Size", 0) for f in files)
    except Exception:
        return 0


def _monitor_download(local_dir: Path, total_size: int, done_event):
    import time
    while not done_event.is_set():
        if local_dir.exists():
            current = sum(
                f.stat().st_size for f in local_dir.rglob("*") if f.is_file()
            )
            mb_done = current / (1024 * 1024)
            if total_size > 0:
                mb_total = total_size / (1024 * 1024)
                pct = min(current * 100 // total_size, 100)
                click.echo(
                    f"\r    Downloading: {mb_done:.0f}/{mb_total:.0f} MB ({pct}%)",
                    nl=False,
                )
            else:
                click.echo(f"\r    Downloading: {mb_done:.0f} MB", nl=False)
        done_event.wait(2)
    click.echo()


def download_from_modelscope(model_name: str, target_dir: Path) -> Path:
    repo_id = MODELSCOPE_REPO_MAP.get(model_name)
    if not repo_id:
        raise ValueError(f"No ModelScope repo ID configured for model: {model_name}")

    try:
        from modelscope import snapshot_download
    except ImportError:
        raise RuntimeError(
            "modelscope is required for ModelScope download. "
            "Install with: pip install modelscope"
        )

    is_vad = "vad" in model_name.lower() or "fsmn" in model_name.lower()
    if is_vad:
        local_dir = target_dir / model_name
    else:
        local_dir = target_dir / model_namespace(model_name) / model_name

    local_dir.parent.mkdir(parents=True, exist_ok=True)

    click.echo(f"    Source: ModelScope ({repo_id})")

    import logging
    import os
    import threading

    total_size = _get_modelscope_total_size(repo_id)
    done_event = threading.Event()
    monitor_thread = threading.Thread(
        target=_monitor_download,
        args=(local_dir, total_size, done_event),
        daemon=True,
    )
    monitor_thread.start()

    prev_level = logging.getLogger("modelscope").level
    logging.getLogger("modelscope").setLevel(logging.WARNING)

    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    orig_stderr_fd = os.dup(2)
    os.dup2(devnull_fd, 2)
    try:
        snapshot_download(repo_id, local_dir=str(local_dir))
    finally:
        os.dup2(orig_stderr_fd, 2)
        os.close(devnull_fd)
        os.close(orig_stderr_fd)
        done_event.set()
        monitor_thread.join(timeout=3)
        logging.getLogger("modelscope").setLevel(prev_level)

    if not _is_model_complete(local_dir):
        import shutil
        temp_dir = local_dir / "._____temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Download incomplete: model weights not found in {local_dir}")

    from .update_checker import record_model_sha
    record_model_sha(model_name, repo_id, source="modelscope")

    return local_dir


def download_from_github(model_name: str, target_dir: Path) -> Path:
    url = f"{GITHUB_RELEASE_BASE_URL}/v{VERSION}/{model_name}.tar.gz"

    is_vad = "vad" in model_name.lower() or "fsmn" in model_name.lower()

    click.echo(f"    Source: GitHub Releases")

    fd, tmp_path = tempfile.mkstemp(suffix=".tar.gz")
    tmp_file = Path(tmp_path)
    try:
        req = Request(url)
        req.add_header("User-Agent", f"mano-asr/{VERSION}")
        response = urlopen(req, timeout=30)

        total = response.headers.get("Content-Length")
        total = int(total) if total else None

        with open(fd, "wb") as f:
            downloaded = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    mb_done = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    click.echo(
                        f"\r    Downloading: {mb_done:.0f}/{mb_total:.0f} MB ({pct}%)",
                        nl=False,
                    )
            click.echo()

        target_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(str(tmp_file), "r:gz") as tar:
            tar.extractall(path=str(target_dir), filter="data")

        if is_vad:
            model_path = target_dir / model_name
        else:
            model_path = target_dir / model_namespace(model_name) / model_name
            if not model_path.exists():
                model_path = target_dir / "mlx-community" / model_name
            if not model_path.exists():
                model_path = target_dir / model_name

        if not model_path.exists() or not (model_path / "config.json").exists():
            raise RuntimeError(f"Extraction completed but model not found at {model_path}")

        return model_path
    except Exception:
        tmp_file.unlink(missing_ok=True)
        raise


def ensure_model(model_name: str, is_vad: bool = False) -> Path:
    existing = find_model_in_dirs(model_name, is_vad=is_vad)
    if existing:
        return existing

    model_type_label = "VAD" if is_vad else "ASR"
    click.echo(info(f"Downloading {model_type_label} model: {model_name} ..."))

    USER_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    preferred = _detect_preferred_source()
    if preferred == "hf":
        sources = [
            ("HuggingFace", download_from_hf),
            ("ModelScope", download_from_modelscope),
        ]
    else:
        sources = [
            ("ModelScope", download_from_modelscope),
            ("HuggingFace", download_from_hf),
        ]
    sources.append(("GitHub Releases", download_from_github))

    for i, (name, download_fn) in enumerate(sources):
        try:
            return download_fn(model_name, USER_MODELS_DIR)
        except Exception as exc:
            click.echo(warning(f"    {name} download failed: {exc}"))
            if i < len(sources) - 1:
                next_name = sources[i + 1][0]
                click.echo(info(f"    Trying {next_name} fallback..."))

    repo_id = HF_REPO_MAP.get(model_name, model_name)
    ms_repo_id = MODELSCOPE_REPO_MAP.get(model_name)
    if is_vad:
        target = f"~/.mano-asr/models/{model_name}/"
    else:
        target = f"~/.mano-asr/models/{model_namespace(model_name)}/{model_name}/"

    click.echo(error(f"Could not download model: {model_name}"))
    click.echo()
    click.echo(f"    Manual download:")
    click.echo(f"      HuggingFace: https://huggingface.co/{repo_id}")
    if ms_repo_id:
        click.echo(f"      ModelScope:  modelscope download --model {ms_repo_id} --local_dir {target}")
    click.echo(f"      Place in: {target}")
    click.echo(f"      Then run: mano-asr start")
    raise SystemExit(1)


def ensure_default_models(model_type_key: str) -> tuple[Path, Optional[Path]]:
    spec = MODEL_TYPES.get(model_type_key)
    if not spec:
        raise ValueError(f"Unknown model type: {model_type_key}")

    asr_model_name = spec["default_model"]
    asr_path = ensure_model(asr_model_name, is_vad=False)

    vad_path = None
    try:
        vad_path = ensure_model(DEFAULT_VAD_MODEL, is_vad=True)
    except SystemExit:
        click.echo(warning("VAD model not available, continuing without VAD"))

    return asr_path, vad_path
