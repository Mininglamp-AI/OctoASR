<p align="center">
  <img src="docs/mano-asr-banner.svg" alt="mano-asr" width="800">
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/MLX-Apple%20Silicon-000000?logo=apple&logoColor=white" alt="MLX"></a>
  <a href="https://github.com/Mininglamp-AI/mano-asr/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Mininglamp-AI/mano-asr?color=blue" alt="License"></a>
  <a href="https://github.com/Mininglamp-AI/mano-asr/stargazers"><img src="https://img.shields.io/github/stars/Mininglamp-AI/mano-asr?style=social" alt="Stars"></a>
  <a href="https://huggingface.co/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit"><img src="https://img.shields.io/badge/🤗-HuggingFace-yellow" alt="HuggingFace"></a>
  <a href="https://www.modelscope.cn/models/Mininglamp2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit"><img src="https://img.shields.io/badge/🪄-ModelScope%20CN-purple" alt="ModelScope CN"></a>
  <a href="https://www.modelscope.ai/models/Mininglamp2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit"><img src="https://img.shields.io/badge/🪄-ModelScope%20AI-purple" alt="ModelScope AI"></a>
</p>

<p align="center">
  <a href="docs/README_zh.md">中文</a> | <b>English</b>
</p>

---

## Introduction

**mano-asr** is a local speech recognition service for vertical domains, deeply optimized for Apple Silicon via [Cider](https://github.com/Mininglamp-AI/cider). Purpose-built for **internet / IT office** scenarios, it is closely adapted to high-frequency workplace use cases such as meeting notes, technical discussions, product reviews, and engineering dictation. Through targeted optimization on domain data, mano-asr accurately recognizes English terms, acronyms, and product names (e.g. `Kubernetes`, `FastAPI`, `PRD`, `Code Review`) as well as mixed Chinese-English speech, effectively addressing the term-misrecognition and code-switching segmentation issues common to general-purpose models — so transcripts come out clear, domain-aware, and accurate. The service runs fully locally, works out of the box, and keeps audio and transcript data on your machine.

Core capabilities:

- 🎯 **Vertical-domain optimization** — optimized on internet / IT office data; accurate on English terms, acronyms, product names, and mixed Chinese-English speech.
- 🍎 **Native Apple Silicon** — MLX-based local inference on M-series chips, further optimized with our in-house acceleration framework Cider.
- 🔒 **Fully local, privacy-first** — audio and transcripts never leave your machine.
- ✂️ **VAD segmentation** — optional FSMN VAD splits long audio and transcribes segment by segment.
- 🧩 **Pluggable engines** — supports Fun-ASR-Nano, Qwen3-ASR and more base models, switchable with one command.
- 🏷️ **@Mention replacement** — auto-fix nicknames and transliterated names in transcripts via a visual page. See [Mentions](docs/mentions/README.md).
- ⚡ **One-command start** — install via `brew install`, then `mano-asr start`.

---

<p align="center">
  <a href="#en-news">Changelog</a> ·
  <a href="#en-models">Models</a> ·
  <a href="#en-install">Installation</a> ·
  <a href="#en-examples">Usage</a> ·
  <a href="#en-api">API</a> ·
  <a href="#en-license">License</a> ·
  <a href="#en-acknowledgments">Acknowledgments</a> ·
</p>

---

<a id="en-news"></a>

## Changelog

See the full release history on the **[Releases](https://github.com/Mininglamp-AI/mano-asr/releases)** page.

- **2026-06-09** — Added @mention replacement with a visual management page (`mano-asr mentions`) for editing nickname → canonical-name mappings; spoken "艾特" is normalized to `@` before replacement. (v0.1.15 fixes packaging so the web page ships in the Homebrew build.)
- **2026-05-29** — Released the first ASR model for internet office scenarios, with written-style transcription output and accurate recognition of industry-specific terminology.
- **2026-05-26** — First release: FastAPI transcription service, FunASR-Nano engine, FSMN VAD, hotword extraction, session logging.

---

<a id="en-models"></a>

## Models

mano-asr uses a pluggable engine design and supports several mainstream ASR base models. Switch with a single command: `mano-asr model use <name>`.

| Model | Base model | Quant | Size | Languages | Links                                                                                                                                                                                                                                                                   |
| --- | --- | --- | --- | --- |-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Mano-ASR-0.8B** (default) | [Fun-ASR-Nano](https://github.com/FunAudioLLM/Fun-ASR) | 8bit | 0.8 GB | ZH / EN | [🤗](https://huggingface.co/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit) · [🤖](https://www.modelscope.cn/models/Mininglamp2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit) ·[🌟](https://www.modelscope.ai/models/Mininglamp2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit) |

> The model is downloaded automatically from HuggingFace or ModelScope (China mirror); the source is chosen by network environment on first run.

---

<a id="en-install"></a>

## Installation

### Option 1: Homebrew (recommended)

```bash
brew tap mano-asr/mano-asr
brew install mano-asr

# Start (first run auto-initializes + downloads the default model)
mano-asr start
mano-asr doctor   # environment check
```

### Option 2: From source

```bash
# 1. Dependency: ffmpeg (decodes non-WAV audio)
brew install ffmpeg

# 2. Clone + install
git clone https://github.com/Mininglamp-AI/mano-asr.git
cd mano-asr
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -e .

# 3. Download the model
hf download Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit \
  --local-dir models/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit

# Behind a China mirror:
# HF_ENDPOINT=https://hf-mirror.com hf download ...

# 4. Start the server
python3 server.py \
  --model-path models/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit \
  --vad-model-path models/fsmn-vad-mlx \
  --host 0.0.0.0 --port 8787 --load-on-startup
```

**Requirements:** macOS (Apple Silicon) · Python 3.10+ · `ffmpeg` / `ffprobe` on `PATH`.

---

<a id="en-examples"></a>

## Usage

The example below shows **audio translation**: transcribe speech and translate it into Chinese.

### CLI (recommended)

```bash
# On first run, the service auto-initializes and downloads the default model
mano-asr start

# Transcribe / translate an audio file
mano-asr transcribe assets/BAC009S0764W0129.wav

```

### Python API

```python
from core.auto_model import AutoModel

model = AutoModel(
    model="models/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit",
    vad_model="models/fsmn-vad-mlx",   # optional: auto-segment long audio
)

text = model.generate(
    "assets/BAC009S0764W0129.wav",
    task="translate",        # translation task
    target_language="zh",    # target language: Chinese
    merge_vad=True,
)
print(text)
# -> "甚至出现交易几乎停滞的情况"
```

### HTTP API

```bash
curl -X POST http://127.0.0.1:8787/v1/voice/transcribe \
  -F "audio=@assets/BAC009S0764W0129.wav" \
  -F "personal_context=## Terms\n- FastAPI\n- Kubernetes" \
  -F "mode=smart"
```

```json
{
  "status": 200,
  "text": "transcribed text",
  "m": "mano-asr",
  "engine": "mlx"
}
```

> Full API fields, limits and auth are documented under [API](#en-api).

### @Mention replacement

Auto-replace casual nicknames and transliterated names in transcripts with the canonical spelling you want (e.g. `@小明` → `@Xiaoming`). Manage entries on a visual web page — no JSON editing required:

```bash
mano-asr start        # Start the service (if not running)
mano-asr mentions     # Open the management page in your browser
```

> 📖 Full guide: [Mentions](docs/mentions/README.md)

---

<a id="en-api"></a>

## API

### `POST /v1/voice/transcribe`

Transcribe a single uploaded audio file. Request type: `multipart/form-data`.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `audio` | file | yes | Audio file. Supported: `.wav` `.mp3` `.ogg` `.webm` `.m4a` `.flac` |
| `context_text` | string | no | Existing text for append/edit modes; last 5000 chars kept |
| `chat_context` | string | no | Chat context; last 20000 chars kept |
| `personal_context` | string | no | Personal correction / hotword context; last 10000 chars kept |
| `member_context` | string | no | Member context; last 5000 chars kept |
| `mode` | string | no | `smart` / `append_only` / `edit_only`, default `smart` |

**Limits:** default max file `30 MiB`, max duration `660` s; `edit_only` requires `context_text`.

### `GET /v1/voice/config`

Returns current service limits and engine metadata.

```bash
curl http://127.0.0.1:8787/v1/voice/config
```

### Authentication

Disabled by default. If started with `--auth-token`, requests must carry `Authorization: Bearer <token>`.

```bash
python3 server.py --model-path <path> --auth-token "$MANO_ASR_TOKEN"
```

---

<a id="en-license"></a>

## License

Released under the [MIT License](LICENSE).

Copyright (c) 2026 MININGLAMP Technology.

---

<a id="en-acknowledgments"></a>

## Acknowledgments

mano-asr would not be possible without these excellent open-source projects:

- [**MLX**](https://github.com/ml-explore/mlx) & [**mlx-audio**](https://github.com/Blaizzy/mlx-audio) — Apple's machine-learning framework and audio toolkit, the foundation of mano-asr's local inference.
- [**FunASR / FunAudioLLM**](https://github.com/modelscope/FunASR) — source of Fun-ASR-Nano and FSMN-VAD, providing strong Chinese speech recognition.
- [**Qwen3**](https://github.com/QwenLM/Qwen3) — the base model behind the Qwen3-ASR engine.
- [**mlx-community**](https://huggingface.co/mlx-community) — high-quality MLX quantized models.
- [**ModelScope**](https://github.com/modelscope/modelscope) & [**Hugging Face**](https://huggingface.co/) — model hosting and distribution.
- [**FastAPI**](https://github.com/fastapi/fastapi) — high-performance web framework.

Thanks to everyone contributing to the open-source speech recognition community.
