# coding=utf-8
"""Update checker - detect new CLI versions and model updates"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

import click

from .constants import (
    UPDATE_CACHE_FILE,
    CHECK_INTERVAL,
    GITHUB_REPO,
    HF_REPO_MAP,
    MODELSCOPE_REPO_MAP,
    VERSION,
)
from .console import warning, info, divider

_CHECK_TIMEOUT = 3


def _load_cache() -> dict:
    try:
        return json.loads(UPDATE_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    try:
        UPDATE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_CACHE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _should_check(cache: dict) -> bool:
    last_ts = cache.get("last_check_ts", 0)
    return (time.time() - last_ts) >= CHECK_INTERVAL


def _compare_versions(current: str, latest: str) -> bool:
    try:
        cur = tuple(int(x) for x in current.split("."))
        lat = tuple(int(x) for x in latest.split("."))
        return lat > cur
    except (ValueError, AttributeError):
        return False


def _fetch_latest_cli_version() -> Optional[str]:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", f"mano-asr/{VERSION}")
    try:
        resp = urlopen(req, timeout=_CHECK_TIMEOUT)
        data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        return tag.lstrip("v") if tag else None
    except Exception:
        return None


def _fetch_model_sha_hf(repo_id: str) -> Optional[str]:
    url = f"https://huggingface.co/api/models/{repo_id}"
    req = Request(url)
    req.add_header("User-Agent", f"mano-asr/{VERSION}")
    try:
        resp = urlopen(req, timeout=_CHECK_TIMEOUT)
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("sha")
    except Exception:
        return None


def _fetch_model_sha_modelscope(repo_id: str) -> Optional[str]:
    url = (
        f"https://www.modelscope.cn/api/v1/models/{repo_id}"
        f"/repo/files?Revision=master"
    )
    req = Request(url)
    req.add_header("User-Agent", f"mano-asr/{VERSION}")
    try:
        resp = urlopen(req, timeout=_CHECK_TIMEOUT)
        data = json.loads(resp.read().decode("utf-8"))
        files = data.get("Data", {}).get("Files", [])
        # Files share the repo's latest commit hash in "Revision".
        for f in files:
            rev = f.get("Revision")
            if rev:
                return rev
    except Exception:
        pass
    return None


def _fetch_model_sha(repo_id: str, source: str = "hf") -> Optional[str]:
    if source == "modelscope":
        return _fetch_model_sha_modelscope(repo_id)
    return _fetch_model_sha_hf(repo_id)


def _get_installed_model_names() -> list[str]:
    from .download import find_model_in_dirs

    installed = []
    for model_name in HF_REPO_MAP:
        is_vad = "vad" in model_name.lower() or "fsmn" in model_name.lower()
        if find_model_in_dirs(model_name, is_vad=is_vad):
            installed.append(model_name)
    return installed


def record_model_sha(model_name: str, repo_id: str, source: str = "hf") -> None:
    try:
        sha = _fetch_model_sha(repo_id, source)
        if not sha:
            return
        cache = _load_cache()
        models = cache.setdefault("models", {})
        models[model_name] = {
            "repo": repo_id,
            "source": source,
            "known_sha": sha,
        }
        _save_cache(cache)
    except Exception:
        pass


def check_and_notify() -> None:
    try:
        _do_check_and_notify()
    except Exception:
        pass


def _do_check_and_notify() -> None:
    cache = _load_cache()

    needs_remote = _should_check(cache)

    if needs_remote:
        latest_ver = _fetch_latest_cli_version()
        if latest_ver:
            cache["cli"] = {
                "latest_version": latest_ver,
                "current_version": VERSION,
            }

        installed = _get_installed_model_names()
        models_cache = cache.setdefault("models", {})
        for model_name in installed:
            entry = models_cache.get(model_name, {})
            # Prefer the source the model was actually downloaded from; this is
            # recorded at download time. Fall back to HF for models that were
            # already present before source tracking existed.
            source = entry.get("source", "hf")
            repo_id = entry.get("repo")
            if not repo_id:
                if source == "modelscope":
                    repo_id = MODELSCOPE_REPO_MAP.get(model_name)
                else:
                    repo_id = HF_REPO_MAP.get(model_name)
            if not repo_id:
                continue
            remote_sha = _fetch_model_sha(repo_id, source)
            if remote_sha:
                entry = models_cache.setdefault(
                    model_name,
                    {"repo": repo_id, "source": source, "known_sha": remote_sha},
                )
                entry["remote_sha"] = remote_sha

        cache["last_check_ts"] = time.time()
        _save_cache(cache)

    messages: list[str] = []

    cli_info = cache.get("cli", {})
    latest = cli_info.get("latest_version")
    if latest and _compare_versions(VERSION, latest):
        messages.append(warning(f"New version available: mano-asr {latest} (current: {VERSION})"))
        messages.append(info("Update: brew upgrade mano-asr"))

    models_cache = cache.get("models", {})
    updated_models = []
    for model_name, entry in models_cache.items():
        known = entry.get("known_sha")
        remote = entry.get("remote_sha")
        if known and remote and known != remote:
            updated_models.append(model_name)

    if updated_models:
        names = ", ".join(updated_models)
        messages.append(warning(f"Model update available: {names}"))
        messages.append(info("Re-download: mano-asr stop && mano-asr start"))

    if messages:
        click.echo(f"\n  {divider()}")
        for msg in messages:
            click.echo(msg)
        click.echo(f"  {divider()}")
