# coding=utf-8
"""Constants"""

from pathlib import Path

VERSION = "0.1.7"

DEFAULT_PORT = 8787

CONFIG_DIR = Path.home() / ".mano-asr"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
PID_FILE = CONFIG_DIR / "mano-asr.pid"
LOG_DIR = CONFIG_DIR / "logs"
LOG_FILE = LOG_DIR / "mano-asr.log"

HOMEBREW_PREFIX = Path("/opt/homebrew/share/mano-asr")
HOMEBREW_MODELS_DIR = HOMEBREW_PREFIX / "models"

USER_MODELS_DIR = CONFIG_DIR / "models"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LOCAL_MODELS_DIR = PROJECT_ROOT / "models"

DEFAULT_ASR_MODEL = "Mano-ASR-0.8B-Instruct-1.0-MLX-8bit"
DEFAULT_VAD_MODEL = "fsmn-vad-mlx"
DEFAULT_MODEL_TYPE = "funasr"

MODEL_TYPES = {
    "funasr": {
        "label": "Mano-ASR",
        "server_type": "funasr",
        "default_model": "Mano-ASR-0.8B-Instruct-1.0-MLX-8bit",
    },
    "qwen3-asr": {
        "label": "Qwen3-ASR",
        "server_type": "qwen3_asr",
        "default_model": "Qwen3-ASR-1.7B-8bit",
    },
}

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac"}

HF_REPO_MAP = {
    "Mano-ASR-0.8B-Instruct-1.0-MLX-8bit": "Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit",
    "Fun-ASR-Nano-2512-8bit": "mlx-community/Fun-ASR-Nano-2512-8bit",
    "Qwen3-ASR-1.7B-8bit": "mlx-community/Qwen3-ASR-1.7B-8bit",
    "fsmn-vad-mlx": "Mininglamp-2718/fsmn-vad-mlx",
}

MODELSCOPE_REPO_MAP = {
    "Mano-ASR-0.8B-Instruct-1.0-MLX-8bit": "Mininglamp2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit",
    "Fun-ASR-Nano-2512-8bit": "luosir001/Fun-ASR-Nano-2512-8bit",
    "Qwen3-ASR-1.7B-8bit": "luosir001/Qwen3-ASR-1_7B-8bit",
    "fsmn-vad-mlx": "Mininglamp2718/fsmn-vad-mlx",
}

GITHUB_RELEASE_BASE_URL = "https://github.com/Mininglamp-AI/mano-asr/releases/download"

GITHUB_REPO = "Mininglamp-AI/mano-asr"
UPDATE_CACHE_FILE = CONFIG_DIR / "update_check.json"
CHECK_INTERVAL = 86400


def model_namespace(model_name: str) -> str:
    """Local sub-directory (HF org) a non-VAD model is stored under.

    Derived from the HuggingFace repo id, e.g.
    "Mininglamp-2718/Mano-ASR-..." -> "Mininglamp-2718".
    Falls back to "mlx-community" for unknown models so legacy layouts
    keep working.
    """
    repo_id = HF_REPO_MAP.get(model_name, "")
    if "/" in repo_id:
        return repo_id.split("/", 1)[0]
    return "mlx-community"
