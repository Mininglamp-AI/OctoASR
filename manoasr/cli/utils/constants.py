# coding=utf-8
"""常量定义"""

from pathlib import Path

VERSION = "0.1.0"

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

DEFAULT_ASR_MODEL = "Fun-ASR-Nano-2512-8bit"
DEFAULT_VAD_MODEL = "fsmn-vad-mlx"
DEFAULT_MODEL_TYPE = "funasr"

MODEL_TYPES = {
    "funasr": {
        "label": "FunASR Nano",
        "server_type": "funasr",
        "default_model": "Fun-ASR-Nano-2512-8bit",
    },
    "qwen3-asr": {
        "label": "Qwen3-ASR",
        "server_type": "qwen3_asr",
        "default_model": "Qwen3-ASR-1_7B-8bit",
    },
}

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac"}

HF_REPO_MAP = {
    "Fun-ASR-Nano-2512-8bit": "mlx-community/Fun-ASR-Nano-2512-8bit",
    "Qwen3-ASR-1_7B-8bit": "mlx-community/Qwen3-ASR-1_7B-8bit",
    "fsmn-vad-mlx": "mano-asr/fsmn-vad-mlx",
}

MODELSCOPE_REPO_MAP = {
    "Fun-ASR-Nano-2512-8bit": "luosir001/Fun-ASR-Nano-2512-8bit",
    "Qwen3-ASR-1_7B-8bit": "luosir001/Qwen3-ASR-1_7B-8bit",
    "fsmn-vad-mlx": "PLACEHOLDER_MODELSCOPE_REPO_ID",
}

GITHUB_RELEASE_BASE_URL = "https://github.com/Mininglamp-AI/mano-asr/releases/download"

GITHUB_REPO = "Mininglamp-AI/mano-asr"
UPDATE_CACHE_FILE = CONFIG_DIR / "update_check.json"
CHECK_INTERVAL = 86400
