<p align="center">
  <img src="mano-asr-banner.svg" alt="mano-asr" width="800">
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/FastAPI-server-009688?logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="#"><img src="https://img.shields.io/badge/MLX-Apple%20Silicon-000000?logo=apple&logoColor=white" alt="MLX"></a>
  <a href="https://github.com/Mininglamp-AI/mano-asr/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Mininglamp-AI/mano-asr?color=blue" alt="License"></a>
  <a href="https://github.com/Mininglamp-AI/mano-asr/stargazers"><img src="https://img.shields.io/github/stars/Mininglamp-AI/mano-asr?style=social" alt="Stars"></a>
</p>

<p align="center">
  <b>中文</b> | <a href="../README.md">English</a>
</p>

---

## 简介

**mano-asr** 是一款面向 **垂直领域** 的本地语音识别（ASR）服务，基于 [MLX](https://github.com/ml-explore/mlx) 为 Apple Silicon 深度优化，开箱即用、完全本地运行、数据不出本机。

mano-asr 在 **互联网 / IT 办公** 场景下做了专门打磨——会议纪要、技术讨论、产品评审、研发口播等场景中高频出现的英文术语、缩写、产品名、专有名词（如 `FastAPI`、`Kubernetes`、`PRD`、`Code Review`、`埋点`、`回滚` 等）进行了针对性的微调，把识别准确率拉到可用级别。

核心能力：

- 🎯 **垂直领域优化** — 针对互联网、IT 办公场景的术语和中英混说做了专项调优。
- 🍎 **Apple Silicon 原生** — 基于 MLX 对 M 系列芯片本地推理，并在此基础上使用自研加速框架 Cider 进行进一步优化。
- 🔒 **完全本地、隐私优先** — 音频与转写结果均不离开本机。
- ✂️ **VAD 智能分段** — 可选 FSMN VAD，对长音频自动切分后逐段转写。
- 🧩 **多引擎可插拔** — 支持 Fun-ASR-Nano、Qwen3-ASR 等多种基座模型，一行命令切换。
- ⚡ **一行命令启动** — `brew install` 安装，`mano-asr start` 即可用。

---

<p align="center">
  <a href="#news">更新动态</a> ·
  <a href="#models">适配模型</a> ·
  <a href="#install">安装</a> ·
  <a href="#examples">使用示例</a> ·
  <a href="#api">API 参考</a> ·
  <a href="#license">License</a> ·
  <a href="#acknowledgments">Acknowledgments</a> ·
</p>

---

<a id="news"></a>

## 更新动态

完整的版本更新记录见 **[Releases](https://github.com/Mininglamp-AI/mano-asr/releases)** 页面。

- **2026-05-29** — 发布首个面向互联网办公场景的 ASR 模型,支持书面化转录输出,精准识别行业专业术语。
- **2026-05-26** — 首次发布:FastAPI 转写服务、FunASR-Nano 引擎、FSMN VAD、热词提取、会话日志。

---

<a id="models"></a>

## 适配模型

mano-asr 采用可插拔的引擎设计，支持多种主流 ASR 基座模型。可通过 `mano-asr model use <name>` 一行命令切换：

| 模型 | 基座模型 | 量化 | 大小 | 语言 | 访问网站 |
| --- | --- | --- | --- | --- | --- |
| **Mano-ASR-0.8B-Instruct-1.0-MLX-8bit**（默认） | [Fun-ASR-Nano](https://github.com/FunAudioLLM/Fun-ASR) | 8bit | 0.8 GB | 中 / 英 | [🤗](https://huggingface.co/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit) · [🤖](https://www.modelscope.cn/models/Mininglamp2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit) |

> 模型支持从 HuggingFace 或 ModelScope（国内镜像）自动下载，首次启动会按网络环境自动选源。

---

<a id="install"></a>

## 安装

### 方式一：Homebrew（推荐）

```bash
brew tap mano-asr/mano-asr
brew install mano-asr

# 启动（首次运行自动初始化 + 下载默认模型）
mano-asr start
mano-asr doctor   # 环境自检
```

### 方式二：源码安装

```bash
# 1. 依赖：ffmpeg（解码非 WAV 音频）
brew install ffmpeg

# 2. 克隆 + 安装
git clone https://github.com/Mininglamp-AI/mano-asr.git
cd mano-asr
python3 -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -e .

# 3. 下载模型
hf download Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit \
  --local-dir models/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit

# 国内用户使用镜像：
# HF_ENDPOINT=https://hf-mirror.com hf download ...

# 4. 启动服务
python3 server.py \
  --model-path models/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit \
  --vad-model-path models/fsmn-vad-mlx \
  --host 0.0.0.0 --port 8787 --load-on-startup
```

**运行要求：** macOS (Apple Silicon) · Python 3.10+ · `ffmpeg` / `ffprobe` 在 `PATH` 中。

---

<a id="examples"></a>

## 使用示例

下面以一段**音频翻译**为例：将一段语音转写并翻译为中文。

### 命令行（推荐）

```bash
# 安装后首次启动会自动初始化并下载默认模型
mano-asr start

# 转写 / 翻译一段音频
mano-asr transcribe assets/BAC009S0764W0129.wav

```

### Python API

```python
from core.auto_model import AutoModel

model = AutoModel(
    model="models/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit",
    vad_model="models/fsmn-vad-mlx",   # 可选：长音频自动分段
)

text = model.generate(
    "assets/BAC009S0764W0129.wav",
    task="translate",        # 翻译任务
    target_language="zh",    # 目标语言：中文
    merge_vad=True,
)
print(text)
# -> "甚至出现交易几乎停滞的情况"
```

### HTTP API

```bash
curl -X POST http://127.0.0.1:8787/v1/voice/transcribe \
  -F "audio=@assets/BAC009S0764W0129.wav" \
  -F "personal_context=## 术语\n- FastAPI\n- Kubernetes" \
  -F "mode=smart"
```

```json
{
  "status": 200,
  "text": "转写文本",
  "m": "mano-asr",
  "engine": "mlx"
}
```

> 完整 API 字段、限制与鉴权说明见下方 [API 参考](#api)。

---

<a id="api"></a>

## API 参考

### `POST /v1/voice/transcribe`

转写单个上传音频文件。请求类型 `multipart/form-data`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `audio` | file | 是 | 音频文件，支持 `.wav` `.mp3` `.ogg` `.webm` `.m4a` `.flac` |
| `context_text` | string | 否 | 已有文本，用于 append/edit 模式，保留最后 5000 字符 |
| `chat_context` | string | 否 | 聊天上下文，保留最后 20000 字符 |
| `personal_context` | string | 否 | 个人纠错 / 热词上下文，保留最后 10000 字符 |
| `member_context` | string | 否 | 成员上下文，保留最后 5000 字符 |
| `mode` | string | 否 | `smart` / `append_only` / `edit_only`，默认 `smart` |

**限制：** 默认最大文件 `30 MiB`，最大时长 `660` 秒；`edit_only` 模式需提供 `context_text`。

### `GET /v1/voice/config`

返回当前服务限制与引擎元数据。

```bash
curl http://127.0.0.1:8787/v1/voice/config
```

### 鉴权

默认关闭。若以 `--auth-token` 启动，请求需携带 `Authorization: Bearer <token>`。

```bash
python3 server.py --model-path <path> --auth-token "$MANO_ASR_TOKEN"
```

---

<a id="license"></a>

## License

本项目基于 [MIT License](../LICENSE) 开源。

Copyright (c) 2026 MININGLAMP Technology.

---

<a id="acknowledgments"></a>

## Acknowledgments

mano-asr 的实现离不开以下优秀的开源项目，在此一并致谢：

- [**MLX**](https://github.com/ml-explore/mlx) & [**mlx-audio**](https://github.com/Blaizzy/mlx-audio) — Apple 的机器学习框架及音频工具链，是 mano-asr 本地推理的基础。
- [**FunASR / FunAudioLLM**](https://github.com/modelscope/FunASR) — Fun-ASR-Nano 与 FSMN-VAD 的来源，提供了强大的中文语音识别能力。
- [**Qwen3**](https://github.com/QwenLM/Qwen3) — 通义千问团队，Qwen3-ASR 引擎的基座模型。
- [**mlx-community**](https://huggingface.co/mlx-community) — 提供了高质量的 MLX 量化模型。
- [**ModelScope**](https://github.com/modelscope/modelscope) & [**Hugging Face**](https://huggingface.co/) — 模型托管与分发。
- [**FastAPI**](https://github.com/fastapi/fastapi) — 高性能 Web 服务框架。

感谢所有为开源语音识别社区做出贡献的开发者。
