# coding=utf-8
"""Configuration management utilities"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from .constants import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_ASR_MODEL,
    DEFAULT_VAD_MODEL,
    DEFAULT_MENTION_MODEL,
    DEFAULT_MODEL_TYPE,
    USER_MODELS_DIR,
    HOMEBREW_MODELS_DIR,
    LOCAL_MODELS_DIR,
    model_namespace,
)


def get_models_dir() -> Path:
    if USER_MODELS_DIR.exists():
        return USER_MODELS_DIR
    if HOMEBREW_MODELS_DIR.exists():
        return HOMEBREW_MODELS_DIR
    return LOCAL_MODELS_DIR


def get_default_config() -> dict[str, Any]:
    models_dir = get_models_dir()
    asr_path = models_dir / model_namespace(DEFAULT_ASR_MODEL) / DEFAULT_ASR_MODEL
    if not asr_path.exists():
        asr_path = models_dir / "mlx-community" / DEFAULT_ASR_MODEL
    if not asr_path.exists():
        asr_path = models_dir / DEFAULT_ASR_MODEL
    vad_path = models_dir / DEFAULT_VAD_MODEL
    mention_path = models_dir / model_namespace(DEFAULT_MENTION_MODEL) / DEFAULT_MENTION_MODEL
    if not mention_path.exists():
        mention_path = models_dir / DEFAULT_MENTION_MODEL

    return {
        "models": {
            "type": DEFAULT_MODEL_TYPE,
            "asr": str(asr_path),
            "vad": str(vad_path) if vad_path.exists() else None,
            "mention": str(mention_path) if mention_path.exists() else None,
        },
        "server": {
            "host": DEFAULT_HOST,
            "port": DEFAULT_PORT,
            "load_on_startup": True,
        },
    }


def config_exists() -> bool:
    return CONFIG_FILE.exists()


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return get_default_config()

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config or get_default_config()


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def get_config_value(key: str, default: Any = None) -> Any:
    config = load_config()
    keys = key.split(".")
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
    return value if value is not None else default


def set_config_value(key: str, value: Any) -> None:
    config = load_config()
    keys = key.split(".")
    target = config
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value
    save_config(config)
