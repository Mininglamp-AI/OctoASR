<p align="center">
  <img src="octoasr-banner.svg" alt="OctoASR" width="800">
</p>

<h1 align="center">OctoASR 使用指南</h1>

<p align="center">
  <b>中文</b> | <a href="OctoASR-User-Guide.md">English</a>
</p>

---

OctoASR 是运行在本机的语音转文字服务，可识别常见音频文件，也可以作为 HTTP 服务接入网页、桌面应用或后端程序。

本指南面向日常使用者，介绍服务启动与关闭、音频转写、上下文和 @mention 功能、日志、模型切换及 Token 统计。

## 1. 功能概览

OctoASR 主要提供以下能力：

- 音频转文字：支持 `.wav`、`.mp3`、`.ogg`、`.webm`、`.m4a`、`.flac`。
- 长音频处理：可结合 VAD（语音活动检测）自动切分有语音的片段。
- 上下文纠正：可传入产品名、人名、专业词等内容，改善识别结果。
- 三种文本模式：智能转写、仅追加、仅编辑已有文本。
- @mention：将 `@昵称` 替换为规范名称；在群聊场景中，还可由 Mention 模型判断是否需要自动 @ 某位成员。
- HTTP API：方便接入网页、机器人和其他程序。
- Token 统计：接口返回 ASR 与 Mention 模型各自的输入、输出 Token 数。

## 2. 安装与首次启动

### 使用 Homebrew 安装

```bash
brew tap Mininglamp-AI/tap
brew install octoasr
```

首次启动服务时，会自动初始化配置并下载默认模型：

```bash
octoasr start
```

默认服务地址为：<http://127.0.0.1:8787>

可用下面的命令检查运行状态：

```bash
octoasr status
```

### 从源码运行

适用于需要修改代码、指定本地模型目录或手动管理运行环境的场景。

```bash
brew install ffmpeg
git clone https://github.com/Mininglamp-AI/OctoASR.git
cd OctoASR
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

下载 ASR 与 VAD 模型后，可直接启动：

```bash
python3 server.py \
  --model-path models/Mininglamp-2718/OctoASR-1.7B-Instruct-1.0-MLX-8bit \
  --vad-model-path models/Mininglamp-2718/fsmn-vad-mlx \
  --host 127.0.0.1 \
  --port 8787 \
  --load-on-startup
```

如果使用 Hugging Face 下载模型但网络访问受限，可配置镜像：

```bash
HF_ENDPOINT=https://hf-mirror.com hf download <模型仓库> --local-dir <本地目录>
```

## 3. 服务管理

常用命令如下：

```bash
octoasr start             # 后台启动服务
octoasr start --foreground # 前台启动，便于实时观察日志
octoasr status            # 查看服务、端口和当前模型
octoasr stop              # 停止后台服务
octoasr restart           # 重启服务
```

前台启动时，终端会持续输出日志；按 `Ctrl+C` 即可停止服务。后台启动的服务应通过 `octoasr stop` 停止。

默认服务只监听本机 `127.0.0.1`。如需让局域网中的其他设备访问，可在启动时指定监听地址，例如：

```bash
octoasr start --host 0.0.0.0
```

将服务暴露到局域网前，请结合实际网络环境配置防火墙、访问权限或接口鉴权。

## 4. 转写音频

### 命令行转写

最简单的用法：

```bash
octoasr transcribe recording.wav
```

传入热词或专业词：

```bash
octoasr transcribe meeting.m4a --hotwords "FastAPI,Kubernetes,OctoASR"
```

将结果保存为文件：

```bash
octoasr transcribe meeting.m4a --output meeting.txt
```

输出完整 JSON 结果：

```bash
octoasr transcribe meeting.m4a --format json
```

当后台服务已启动时，命令会通过本机 HTTP 服务转写；未启动时，命令会直接加载当前配置的模型进行识别。

### HTTP API 转写

转写接口为 `POST /v1/voice/transcribe`，请求格式为 `multipart/form-data`。

```bash
curl -X POST http://127.0.0.1:8787/v1/voice/transcribe \
  -F "audio=@meeting.m4a" \
  -F "personal_context=FastAPI Kubernetes OctoASR" \
  -F "mode=smart"
```

注意：此接口不支持浏览器直接打开。直接访问 `http://127.0.0.1:8787/v1/voice/transcribe` 会得到 `405 Method Not Allowed`，因为浏览器默认发出的是 `GET` 请求，而转写接口只接受 `POST`。

### Python 调用

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

## 5. 接口字段说明

### 请求字段

| 字段 | 是否必填 | 说明 |
| --- | --- | --- |
| `audio` | 是 | 要转写的音频文件。 |
| `personal_context` | 否 | 个人热词、产品名、专业词或希望纠正的词汇。 |
| `chat_context` | 否 | 聊天上下文，用于群聊自动 @ 判断。 |
| `member_context` | 否 | 群成员信息，用于识别可 @ 的对象。 |
| `context_text` | 否 | 已有文本，配合 `append_only` 或 `edit_only` 模式使用。 |
| `mode` | 否 | `smart`、`append_only` 或 `edit_only`，默认是 `smart`。 |
| `disable_auto_mention` | 否 | 传入 `true` 时，当前请求不执行自动 @ 判断。 |

默认限制为单个文件不超过 30 MiB、音频时长不超过 660 秒。实际限制可通过配置或服务启动参数调整。

### 返回字段

成功请求会返回类似下面的 JSON：

```json
{
  "status": 200,
  "text": "今天下午三点开会。",
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

其中：

- `text`：最终转写结果；在群聊场景中，可能已经补充了自动 @。
- `mention`：Mention 模型的判断结果；没有启用或不适用时可能为 `null`，或包含 `skipped` 原因。
- `usage.asr`：ASR 模型的 Token 统计。
- `usage.mention`：Mention 模型的 Token 统计。
- `input_tokens`：模型本次处理的输入 Token 数。
- `output_tokens`：模型本次生成的输出 Token 数。

`mention.should_mention` 为 `false` 并不代表 Mention 模型没有运行。它表示模型已判断当前语句不需要自动 @；是否真正调用过模型，应以 `usage.mention.called` 为准。

如果 Mention 模型未调用，`called` 会是 `false`，并可能有 `skipped` 字段，例如：

```json
{
  "called": false,
  "input_tokens": 0,
  "output_tokens": 0,
  "skipped": "not_group_chat"
}
```

常见的 `skipped` 值包括：

| 值 | 含义 |
| --- | --- |
| `not_group_chat` | 当前不是群聊场景。 |
| `no_model` | 未配置 Mention 模型。 |
| `disabled_by_request` | 当前请求或服务启动参数关闭了自动 @。 |
| `model_unavailable` | Mention 模型暂时不可用。 |
| `error` | Mention 判断出现异常，转写仍会继续返回。 |

## 6. @mention 功能

OctoASR 的 @mention 有两层能力：

1. 名称替换：把转写中的 `@昵称` 替换为你设置的标准名称。
2. 自动提及：在群聊上下文中，Mention 模型判断是否需要在结果前补充 `@某位成员`。

### 管理名称替换

先启动服务，再打开管理页面：

```bash
octoasr start
octoasr mentions
```

页面地址为：<http://127.0.0.1:8787/mentions>

在页面中可以新增、编辑和删除“昵称 -> 标准名称”映射，例如将 `小明` 映射为 `Xiaoming`。修改会在下一次转写中立即生效，无需重启服务。

只想显示页面链接、不自动打开浏览器时：

```bash
octoasr mentions --no-browser
```

用户自定义映射保存在：

```text
~/.octoasr/mentions/user.json
```

### 关闭自动 @

临时关闭某次 HTTP 请求的自动 @：

```bash
curl -X POST http://127.0.0.1:8787/v1/voice/transcribe \
  -F "audio=@meeting.m4a" \
  -F "disable_auto_mention=true"
```

启动整个服务时关闭：

```bash
octoasr start --disable-auto-mention true
```

## 7. 查看日志与排查问题

日志文件位于：

```text
~/.octoasr/logs/octoasr.log
```

常用查看方式：

```bash
octoasr logs              # 查看最近 50 行
octoasr logs -f           # 持续跟踪新日志，按 Ctrl+C 退出查看
octoasr logs --errors     # 只查看警告和错误
octoasr logs --stats      # 查看最近 24 小时的统计
```

当出现 `Transcribe OK` 时，表示一次转写请求已正常完成，其中的 `elapsed_ms` 是本次总耗时。若需要在日志中查看更完整的转写文本，可通过调试模式启动：

```bash
octoasr restart --debug
```

Token 使用量默认通过接口响应的 `usage` 字段查看，不会单独打印在普通日志中。命令行使用时可执行：

```bash
octoasr transcribe meeting.m4a --format json
```

## 8. 模型管理

OctoASR 通常会使用以下三类模型：

| 模型类型 | 作用 |
| --- | --- |
| ASR | 把音频识别为文字。 |
| VAD | 识别有效语音片段，帮助处理长音频和静音。 |
| Mention | 在群聊场景中判断是否需要自动 @ 某位成员。 |

查看当前模型配置：

```bash
octoasr model info
```

查看本机已识别到的模型：

```bash
octoasr model list
```

切换模型：

```bash
octoasr model use <模型名称>
octoasr restart
```

也可以按引擎切换 ASR 默认模型：

```bash
octoasr model use qwen3-asr
octoasr model use funasr
octoasr restart
```

切换模型后必须重启服务，新的模型才会生效。模型配置文件位于：

```text
~/.octoasr/config.yaml
```

查看完整配置：

```bash
octoasr config show
```

## 9. 端口与网络访问

查看当前端口：

```bash
octoasr port
```

更改端口：

```bash
octoasr port 9000
octoasr restart
```

更改端口后，接口地址也要同步更换，例如：

```text
http://127.0.0.1:9000/v1/voice/transcribe
```

## 10. 常见问题

### 服务无法连接

先确认服务是否运行：

```bash
octoasr status
```

如果未运行，执行：

```bash
octoasr start
```

### 端口已被占用

使用 `octoasr status` 确认当前服务状态；必要时停止旧服务，或修改端口后重启：

```bash
octoasr stop
octoasr port 9000
octoasr start
```

### 模型或运行环境异常

运行环境检查：

```bash
octoasr doctor
```

然后查看错误日志：

```bash
octoasr logs --errors
```

### 浏览器访问转写地址返回 405

这是正常现象。`/v1/voice/transcribe` 是上传音频的 POST 接口，应通过程序、`curl` 或网页前端提交音频文件调用，而不是在浏览器地址栏直接打开。

### Mention 模型会不会每次都调用

不会。ASR 模型会在每次转写时调用；Mention 模型只有在已配置、未关闭自动 @ 且请求被识别为群聊场景时才会调用。可通过返回结果的 `usage.mention.called` 和 `usage.mention.skipped` 确认。

## 11. 快速命令清单

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
