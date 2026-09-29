<p align="center">
  <img src="octoasr-banner.svg" alt="OctoASR" width="800">
</p>

<h1 align="center">OctoASR User Guide</h1>

<p align="center">
  <a href="OctoASR-使用指南.md">中文</a> | <b>English</b>
</p>

---

OctoASR is a local speech-to-text service. It transcribes common audio formats and can also be used as an HTTP service from web, desktop, and backend applications.

This guide covers starting and stopping the service, transcribing audio, using context and @mentions, reading logs, switching models, and inspecting token usage.

## 1. Features at a glance

- Speech-to-text for `.wav`, `.mp3`, `.ogg`, `.webm`, `.m4a`, and `.flac` files.
- VAD-based segmentation for long recordings.
- Context and hotwords to improve recognition of names and technical terms.
- Smart, append-only, and edit-only text modes.
- @mention replacement and group-chat automatic mention decisions.
- HTTP API for application integration.
- Per-model input and output token usage in API responses.

## 2. Install and start

### Install with Homebrew

```bash
brew tap Mininglamp-AI/tap
brew install octoasr
octoasr start
```

The first start initializes the configuration and downloads the default models. The default service address is <http://127.0.0.1:8787>.

```bash
octoasr status
```

### Run from source

Use this option when developing OctoASR or managing local model paths yourself.

```bash
brew install ffmpeg
git clone https://github.com/Mininglamp-AI/OctoASR.git
cd OctoASR
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

After downloading the ASR and VAD models, start the server:

```bash
python3 server.py \
  --model-path models/Mininglamp-2718/OctoASR-1.7B-Instruct-1.0-MLX-8bit \
  --vad-model-path models/Mininglamp-2718/fsmn-vad-mlx \
  --host 127.0.0.1 \
  --port 8787 \
  --load-on-startup
```

When Hugging Face is inaccessible, a mirror can be configured for downloads:

```bash
HF_ENDPOINT=https://hf-mirror.com hf download <model-repository> --local-dir <local-directory>
```

## 3. Service management

```bash
octoasr start              # Start in the background
octoasr start --foreground # Run in the foreground and show logs
octoasr status             # Show status, port, and active model
octoasr stop               # Stop the background service
octoasr restart            # Restart the service
```

For a foreground service, press `Ctrl+C` to stop it. Use `octoasr stop` for a background service.

The default service listens only on `127.0.0.1`. To allow access from other devices on a trusted network:

```bash
octoasr start --host 0.0.0.0
```

Use appropriate firewall rules, authentication, and network controls before exposing a service beyond your own machine.

## 4. Transcribe audio

### Command line

```bash
octoasr transcribe recording.wav
octoasr transcribe meeting.m4a --hotwords "FastAPI,Kubernetes,OctoASR"
octoasr transcribe meeting.m4a --output meeting.txt
octoasr transcribe meeting.m4a --format json
```

When the background service is running, the command sends the audio to the local HTTP API. Otherwise, it loads the configured model directly.

### HTTP API

The transcription endpoint is `POST /v1/voice/transcribe` and accepts `multipart/form-data`.

```bash
curl -X POST http://127.0.0.1:8787/v1/voice/transcribe \
  -F "audio=@meeting.m4a" \
  -F "personal_context=FastAPI Kubernetes OctoASR" \
  -F "mode=smart"
```

Do not open this endpoint directly in a browser. Browsers issue a `GET` request from the address bar, while the endpoint accepts only `POST`, so it correctly returns `405 Method Not Allowed`.

### Python API

```python
from core.auto_model import AutoModel

model = AutoModel(
    model="models/Mininglamp-2718/OctoASR-1.7B-Instruct-1.0-MLX-8bit",
    vad_model="models/Mininglamp-2718/fsmn-vad-mlx",
)

text = model.generate(
    "meeting.m4a",
    task="transcribe",
    target_language="auto",
    merge_vad=True,
)
print(text)
```

## 5. API fields

### Request fields

| Field | Required | Description |
| --- | --- | --- |
| `audio` | Yes | The audio file to transcribe. |
| `personal_context` | No | Personal hotwords, product names, or specialized terms. |
| `chat_context` | No | Chat context used by the group-chat auto-mention decision. |
| `member_context` | No | Group member information used to identify mention targets. |
| `context_text` | No | Existing text for `append_only` or `edit_only` modes. |
| `mode` | No | `smart`, `append_only`, or `edit_only`. Defaults to `smart`. |
| `disable_auto_mention` | No | Set to `true` to skip automatic mentions for this request. |

The default limits are 30 MiB per file and 660 seconds per audio file. These limits can be changed through server configuration or startup arguments.

### Response fields and token usage

```json
{
  "status": 200,
  "text": "Let's meet at three this afternoon.",
  "mention": {
    "sentence_type": "other",
    "should_mention": false,
    "mention_probability": 0.05,
    "targets": []
  },
  "m": "octoasr",
  "engine": "mlx",
  "usage": {
    "asr": {
      "model": "OctoASR-1.7B-Instruct-1.0-MLX-8bit",
      "called": true,
      "input_tokens": 105,
      "output_tokens": 7
    },
    "mention": {
      "model": "OctoMention-2B-Instruct-1.2-MLX-8bit",
      "called": true,
      "input_tokens": 3277,
      "output_tokens": 23
    }
  }
}
```

- `text`: the final transcript. In a group-chat scenario it may include an automatic mention.
- `mention`: the result of the semantic mention decision. It can be `null` or contain a `skipped` reason when the feature does not apply.
- `usage.asr`: ASR model usage.
- `usage.mention`: Mention model usage.
- `input_tokens`: tokens supplied to the model for this request.
- `output_tokens`: tokens generated by the model.

`mention.should_mention: false` does not mean that the Mention model was not called. It means that the model decided an automatic mention is unnecessary. Check `usage.mention.called` to determine whether it actually ran.

When the Mention model is skipped, `called` is `false` and the usage may include a reason:

```json
{
  "called": false,
  "input_tokens": 0,
  "output_tokens": 0,
  "skipped": "not_group_chat"
}
```

| `skipped` value | Meaning |
| --- | --- |
| `not_group_chat` | The request is not a group-chat scenario. |
| `no_model` | No Mention model is configured. |
| `disabled_by_request` | Automatic mention was disabled for the request or service. |
| `model_unavailable` | The Mention model is temporarily unavailable. |
| `error` | Mention processing failed, but transcription still returns normally. |

## 6. @mention features

OctoASR has two @mention capabilities:

1. Name replacement: replaces `@nickname` in a transcript with a canonical name you define.
2. Automatic mention: in a group-chat context, the Mention model decides whether to prepend `@someone` to the result.

### Manage name replacements

```bash
octoasr start
octoasr mentions
```

The management page is <http://127.0.0.1:8787/mentions>. Add, edit, or remove nickname-to-canonical-name mappings, such as `小明` to `Xiaoming`. Changes apply to the next transcription without a restart.

To print the URL without opening a browser:

```bash
octoasr mentions --no-browser
```

User-defined mappings are stored in:

```text
~/.octoasr/mentions/user.json
```

### Disable automatic mentions

Disable it for one API request:

```bash
curl -X POST http://127.0.0.1:8787/v1/voice/transcribe \
  -F "audio=@meeting.m4a" \
  -F "disable_auto_mention=true"
```

Disable it when starting the service:

```bash
octoasr start --disable-auto-mention true
```

## 7. Logs and troubleshooting

The log file is located at:

```text
~/.octoasr/logs/octoasr.log
```

```bash
octoasr logs              # Show the last 50 lines
octoasr logs -f           # Follow the log; press Ctrl+C to stop following
octoasr logs --errors     # Show warnings and errors only
octoasr logs --stats      # Show statistics for the last 24 hours
```

`Transcribe OK` indicates that a request completed successfully. Its `elapsed_ms` value is the total request duration. To include transcript text in logs, restart in debug mode:

```bash
octoasr restart --debug
```

Token counts are returned in the `usage` object rather than printed in normal logs. Use JSON output from the CLI to see them:

```bash
octoasr transcribe meeting.m4a --format json
```

## 8. Model management

| Model type | Purpose |
| --- | --- |
| ASR | Converts audio to text. |
| VAD | Detects speech segments and helps with long recordings and silence. |
| Mention | Decides whether to automatically mention a group member. |

```bash
octoasr model info
octoasr model list
octoasr model use <model-name>
octoasr restart
```

You can also switch the ASR engine and its default model:

```bash
octoasr model use qwen3-asr
octoasr model use funasr
octoasr restart
```

Restart the service after switching a model. The model configuration file is:

```text
~/.octoasr/config.yaml
```

```bash
octoasr config show
```

## 9. Ports and network access

```bash
octoasr port       # Show the current port
octoasr port 9000  # Change the port
octoasr restart
```

After changing the port, update the API address accordingly, for example:

```text
http://127.0.0.1:9000/v1/voice/transcribe
```

## 10. Common questions

### The service cannot be reached

```bash
octoasr status
octoasr start
```

### The port is already in use

```bash
octoasr stop
octoasr port 9000
octoasr start
```

### A model or environment error occurs

```bash
octoasr doctor
octoasr logs --errors
```

### The transcription URL returns 405 in a browser

This is expected. `/v1/voice/transcribe` accepts audio uploads through `POST`, so use an application, `curl`, or a web client rather than the browser address bar.

### Does the Mention model run for every transcription?

No. The ASR model runs for each transcription. The Mention model runs only when it is configured, automatic mentions are enabled, and the request is recognized as a group-chat scenario. Check `usage.mention.called` and `usage.mention.skipped` in the response.

## 11. Quick command reference

```bash
octoasr start
octoasr status
octoasr transcribe recording.wav
octoasr transcribe recording.wav --format json
octoasr mentions
octoasr logs -f
octoasr logs --errors
octoasr model info
octoasr model list
octoasr port
octoasr restart
octoasr stop
```
