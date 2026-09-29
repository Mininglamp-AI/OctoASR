<p align="center">
  <img src="octoasr-banner.svg" alt="OctoASR" width="800">
</p>

<h1 align="center">OctoASR GPU User Guide</h1>

<p align="center">
  <a href="使用手册.md">中文</a> | <b>English</b>
</p>

---

This guide covers the Docker-based OctoASR service on Linux hosts with NVIDIA GPUs. The service uses two Torch models: an ASR model for transcription and domain terminology, and a Mention model for context-aware `@mention` processing. It preserves OctoASR transcription fields, context parameters, mention management, model administration, logging, and audit workflows.

The default address is `http://127.0.0.1:18001`.

## 1. Features and endpoints

| Feature | Description | Entry point |
| --- | --- | --- |
| Audio transcription | Supports `.wav`, `.mp3`, `.ogg`, `.webm`, `.m4a`, and `.flac`, including mixed Chinese/English terminology. | `POST /v1/voice/transcribe` |
| Context correction | Existing text, chat, personal-term, and member context. | Transcription form fields |
| @Mention | Maps aliases to canonical names and uses conversation context for automatic mentions. | `/mentions`, `/v1/mentions` |
| Model management | Inspect, switch, and roll back ASR and Mention models. | `octoasr-gpu model …` |
| Operations | Start, stop, restart, inspect, diagnose, and review logs. | `octoasr-gpu …`, Docker Compose |
| Audit and tracing | Request IDs, request/result/error records, and optional audio retention. | `/health`, audit directory |

The service also exposes OpenAI-compatible `POST /v1/audio/transcriptions` and `POST /v1/chat/completions`. Use `/v1/voice/transcribe` when your integration needs the complete OctoASR response fields.

## 2. Prerequisites

The target host requires Linux, an NVIDIA GPU and driver, Docker Engine, Docker Compose v2, and NVIDIA Container Toolkit. The default build combination is Linux `x86_64`, CUDA 12.8, PyTorch 2.7.1, and cu128 wheels.

```bash
uname -m
docker --version
docker compose version
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

The final command must also list the GPU. On ARM64, choose mutually compatible `BASE_IMAGE`, `TORCH_VERSION`, and `TORCH_INDEX_URL` values.

Enter the GPU deployment project and confirm its required files:

```bash
PROJECT_DIR=/absolute/path/to/octoasrtorch
cd "$PROJECT_DIR"

for f in Dockerfile compose.yaml .env.example qwen3_asr_openai_server.py qwen3_asr_audit.py; do
  test -f "$f" || { echo "Missing deployment file: $f"; exit 1; }
done
```

## 3. Prepare the ASR and Mention models

Both models are complete Torch/Transformers checkpoints. Each model directory must contain `config.json`, weights, and its required processor/tokenizer files. Do not place models in the Docker build context.

```bash
ASR_MODEL_DIR=/srv/models/OctoASR-1.7B-Torch
MENTION_MODEL_DIR=/srv/models/OctoMention-2B-Torch

test -f "$ASR_MODEL_DIR/config.json" && echo 'ASR model is available'
test -f "$MENTION_MODEL_DIR/config.json" && echo 'Mention model is available'
```

The service mounts the models read-only at `/models/asr` and `/models/mention`. Container recreation does not modify the host model directories.

## 4. Configure `.env`

```bash
cp .env.example .env
```

Set at least the following values:

```dotenv
QWEN_ASR_IMAGE=octoasr-gpu:latest
BASE_IMAGE=nvidia/cuda:12.8.0-devel-ubuntu22.04
TORCH_VERSION=2.7.1
TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
QWEN_ASR_HOST_PORT=18001
QWEN_ASR_GPU=0

QWEN_ASR_MODEL_DIR=/srv/models/OctoASR-1.7B-Torch
OCTOASR_MENTION_MODEL_DIR=/srv/models/OctoMention-2B-Torch
OCTOASR_VAD_ENABLED=true
OCTOASR_AUTO_MENTION_ENABLED=true
OCTOASR_AUTH_TOKEN=

QWEN_ASR_AUDIT_HOST_DIR=./data/audit
QWEN_ASR_AUDIT_ENABLED=true
QWEN_ASR_AUDIT_SAVE_AUDIO=false
QWEN_ASR_LOG_MAX_SIZE=20m
QWEN_ASR_LOG_MAX_FILE=5
```

| Setting | Meaning |
| --- | --- |
| `QWEN_ASR_GPU` | Use one physical GPU index such as `0` on shared hosts, or `all` on dedicated hosts. A selected card appears as `cuda:0` in the container. |
| `QWEN_ASR_MODEL_DIR` | Absolute path to the ASR model. |
| `OCTOASR_MENTION_MODEL_DIR` | Absolute path to the Mention model. Leave it empty to disable semantic Mention inference while retaining user dictionary replacements. |
| `OCTOASR_VAD_ENABLED` | Enables automatic segmentation for long audio. |
| `OCTOASR_AUTO_MENTION_ENABLED` | Enables automatic @Mention by default; a request can override it. |
| `OCTOASR_AUTH_TOKEN` | Enables Bearer authentication when non-empty. Never commit this value. |
| `QWEN_ASR_AUDIT_SAVE_AUDIO` | Retains original audio in audit storage when true. Set according to your privacy policy. |

Validate the model paths, create protected audit storage, and render Compose configuration:

```bash
set -a
. ./.env
set +a
install -d -m 700 "$QWEN_ASR_AUDIT_HOST_DIR"
test -f "$QWEN_ASR_MODEL_DIR/config.json"
test -f "$OCTOASR_MENTION_MODEL_DIR/config.json"
docker compose config
```

## 5. Build, start, and verify

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --follow qwen3-asr-api
```

Initial startup loads the ASR and Mention models. After the container becomes `healthy`, check the service:

```bash
API_PORT=18001
curl -sS "http://127.0.0.1:${API_PORT}/health" | python3 -m json.tool
```

The response reports ASR/Mention model loading, GPU, and audit state:

```json
{
  "status": "ok",
  "asr_model_loaded": true,
  "mention_model_loaded": true,
  "gpu": "cuda:0",
  "audit": {"enabled": true, "writable": true}
}
```

Interactive API documentation is available at `http://127.0.0.1:18001/docs`.

## 6. Command-line operations

```bash
# Service and diagnostics
octoasr-gpu start
octoasr-gpu stop
octoasr-gpu restart
octoasr-gpu status
octoasr-gpu doctor
octoasr-gpu port
octoasr-gpu port 19001

# Transcription
octoasr-gpu transcribe meeting.wav
octoasr-gpu transcribe meeting.wav --format json --output meeting.json
octoasr-gpu transcribe meeting.wav --hotwords 'FastAPI,Kubernetes,Code Review'

# Models
octoasr-gpu model list
octoasr-gpu model info
octoasr-gpu model use OctoASR-1.7B-Torch --type asr
octoasr-gpu model use OctoMention-2B-Torch --type mention
octoasr-gpu model rollback

# Mention and logs
octoasr-gpu mentions
octoasr-gpu logs --follow
octoasr-gpu logs --errors
octoasr-gpu logs --stats --hours 24
```

Model switching validates the checkpoint, drains in-flight requests, loads the new model, and performs a health check. It retains the previous model on failure. Recreate the service after changing the GPU, port, model path, or audit configuration:

```bash
docker compose up -d --force-recreate
```

## 7. Transcription API

### `POST /v1/voice/transcribe`

The request uses `multipart/form-data`.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `audio` | file | Yes | `.wav`, `.mp3`, `.ogg`, `.webm`, `.m4a`, or `.flac`; default limit 30 MiB and 660 seconds. |
| `context_text` | string | No | Existing text; keeps the final 5,000 characters. |
| `chat_context` | string | No | Chat context; keeps the final 20,000 characters. |
| `personal_context` | string | No | Personal correction and hotword context; keeps the final 10,000 characters. |
| `member_context` | string | No | Member context; keeps the final 5,000 characters. |
| `mode` | string | No | `smart`, `append_only`, or `edit_only`; default `smart`. `edit_only` requires `context_text`. |
| `disable_auto_mention` | boolean | No | Disables automatic Mention for this request. |

```bash
TEST_AUDIO=/absolute/path/to/meeting.m4a
REQUEST_ID=meeting-20260929-001

curl -sS -X POST "http://127.0.0.1:${API_PORT}/v1/voice/transcribe" \
  -H "X-Request-ID: ${REQUEST_ID}" \
  -H "Authorization: Bearer ${OCTOASR_AUTH_TOKEN}" \
  -F audio=@"$TEST_AUDIO" \
  -F personal_context=$'## Terms\n- FastAPI\n- Kubernetes\n- Code Review' \
  -F chat_context='Discussing the GPU service release and model switching.' \
  -F member_context='小明=Xiaoming; 老王=Wang Wei' \
  -F mode=smart
```

The response follows the OctoASR schema:

```json
{
  "status": 200,
  "text": "@Xiaoming, please confirm the Kubernetes cluster Code Review result.",
  "mention": {"should_mention": true, "targets": [{"display_name": "Xiaoming"}]},
  "m": "OctoASR-1.7B-Torch",
  "engine": "torch-cuda",
  "usage": {
    "asr": {"model": "OctoASR-1.7B-Torch", "called": true, "input_tokens": 128, "output_tokens": 24},
    "mention": {"model": "OctoMention-2B-Torch", "called": true, "input_tokens": 78, "output_tokens": 12}
  }
}
```

`smart` and `append_only` join `context_text` with the new transcript. `edit_only` returns only the edited result. When Mention is disabled or unavailable, `usage.mention.skipped` explains why without failing transcription.

### Configuration and OpenAI compatibility

```bash
curl -sS "http://127.0.0.1:${API_PORT}/v1/voice/config" | python3 -m json.tool

curl -sS -X POST "http://127.0.0.1:${API_PORT}/v1/audio/transcriptions" \
  -H "Authorization: Bearer ${OCTOASR_AUTH_TOKEN}" \
  -F model=octoasr-gpu \
  -F language=Chinese \
  -F response_format=verbose_json \
  -F file=@"$TEST_AUDIO"
```

Use `/v1/voice/transcribe` when you need the full `mention`, `usage.asr`, and `usage.mention` fields.

## 8. Mention administration

Open `http://127.0.0.1:18001/mentions` to manage alias-to-canonical-name mappings. The API can also be used directly:

```bash
curl -sS "http://127.0.0.1:${API_PORT}/v1/mentions"

curl -sS -X POST "http://127.0.0.1:${API_PORT}/v1/mentions" \
  -H 'Content-Type: application/json' \
  -d '{"alias":"小明","name":"Xiaoming"}'
```

User dictionary substitutions take precedence over semantic inference. In group chats, the Mention model uses `chat_context` and `member_context` to decide whether an automatic mention is appropriate.

## 9. Logs, audit, and troubleshooting

Docker uses rotating `json-file` logs, with a default maximum of 20 MiB per file and five retained files.

```bash
docker compose logs --tail=200 qwen3-asr-api
docker compose logs --since=30m --timestamps --follow qwen3-asr-api
docker compose ps
docker compose exec qwen3-asr-api nvidia-smi
docker stats qwen3-asr-api
```

Every response returns `X-Request-ID`. Use it to inspect audit records:

```bash
set -a
. ./.env
set +a

find "$QWEN_ASR_AUDIT_HOST_DIR" -type f -printf '%TY-%Tm-%Td %TT %p\n' | sort
python3 -m json.tool "$QWEN_ASR_AUDIT_HOST_DIR/requests/${REQUEST_ID}.json"
python3 -m json.tool "$QWEN_ASR_AUDIT_HOST_DIR/results/${REQUEST_ID}.json"
python3 -m json.tool "$QWEN_ASR_AUDIT_HOST_DIR/errors/${REQUEST_ID}.json"
tail -n 50 "$QWEN_ASR_AUDIT_HOST_DIR/events.jsonl"
```

| Status | Action |
| --- | --- |
| `400` | Check audio type, size, duration, mode, and `context_text` for `edit_only`. |
| `401` | Check the `Authorization: Bearer <token>` header. |
| `422` | Check form and JSON field names. |
| `500` | Keep the request ID and inspect ASR/Mention logs, model mounts, and GPU memory. |
| `503` | Models are loading; retry after `/health` is healthy. |

## 10. Upgrade, rollback, and stop

```bash
set -a
. ./.env
set +a
docker tag "$QWEN_ASR_IMAGE" octoasr-gpu:rollback-YYYYMMDD
docker compose build
docker compose up -d --force-recreate
```

After an upgrade, verify health, transcription, Mention, and audit writing. To roll back, set this in `.env` and recreate the service:

```dotenv
QWEN_ASR_IMAGE=octoasr-gpu:rollback-YYYYMMDD
```

```bash
docker compose up -d --force-recreate
docker compose down  # stops the service while retaining host models and audit data
```

Do not use `docker system prune`, `docker container prune`, or `docker image prune -a` for service troubleshooting; those operations can affect unrelated workloads.

## 11. Security

- Put public deployments behind a TLS-enabled reverse proxy with authentication, request-size limits, and rate limiting.
- The audit directory can contain audio, transcripts, contexts, and member information. Restrict access and define a retention period.
- Never commit `.env`, tokens, internal paths, or GPU assignment details.
- Remote audio in Chat Completions is restricted to public HTTPS and remains subject to timeout, size, and redirect limits. Apply egress network controls in production.
