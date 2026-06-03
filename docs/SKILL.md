# mano-asr × OpenClaw 本地语音转写集成指南

> 在 Apple Silicon Mac 上，用 [mano-asr](https://github.com/Mininglamp-AI/mano-asr) 为 [OpenClaw](https://github.com/openclaw/openclaw) 提供完全离线、零成本的语音转文字能力。无需任何云端 API Key。

---

## 概述

| 项目 | 说明 |
|------|------|
| 功能 | 将语音/音频消息自动转写为文字，注入 OpenClaw 对话上下文 |
| 引擎 | Qwen3-ASR (1.7B-8bit) 或 Fun-ASR-Nano，基于 MLX 在 Apple Silicon 本地推理 |
| 隐私 | 音频不离开本机，完全离线处理 |
| 支持格式 | `.wav` `.mp3` `.ogg` `.webm` `.m4a` `.flac` |
| 支持语言 | 中文、英文（取决于所选模型） |
| 适用渠道 | 企业微信、Telegram、Discord、Signal、WebChat 等所有 OpenClaw 接入渠道 |

---

## 环境要求

- **硬件**: Apple Silicon Mac（M1/M2/M3/M4 系列）
- **系统**: macOS Monterey (12.0) 或更高
- **软件**:
  - [Homebrew](https://brew.sh) 已安装
  - [OpenClaw](https://github.com/openclaw/openclaw) 已安装且 Gateway 正在运行
  - `ffmpeg` （mano-asr 依赖，brew 会自动安装）

验证 OpenClaw 状态：

```bash
openclaw status
```

确认 Gateway 显示 `running`。

---

## 安装步骤

### 1. 添加 Tap 并安装 mano-asr

```bash
brew tap Mininglamp-AI/tap
brew install mano-asr
```

验证安装成功：

```bash
mano-asr --version
# 输出: mano-asr 0.1.4
```

### 2. 环境检查

```bash
mano-asr doctor
```

正常输出示例：

```
  Environment Check
  ───────────────────────────────────
  ✓ Python 3.13.x
  ✓ ffmpeg 7.x
  ✓ ffprobe (installed)
  ✓ MLX unknown
  ✓ Config file exists
  ✓ ASR model: Mano-ASR-0.8B-Instruct-1.0-MLX-8bit
  ───────────────────────────────────
```

### 3. 首次启动（自动下载模型）

```bash
mano-asr start
```

> ⏳ 首次启动会自动下载 ASR 模型（约 1 GB），请确保网络通畅。
> 模型存储路径：`~/.mano-asr/models/`

等待启动完成后确认状态：

```bash
mano-asr status
```

```
  mano-asr Service Status
  ───────────────────────────────────
  Status: running
  PID: xxxxx
  Port: 8787
  Uptime: 0h 1m
  ───────────────────────────────────
  Engine: qwen3-asr (Qwen3-ASR)
  ASR Model: Mano-ASR-0.8B-Instruct-1.0-MLX-8bit
  ───────────────────────────────────
```

### 4. 验证转写能力（可选）

用任意音频文件测试：

```bash
mano-asr transcribe --format text /path/to/test.wav
# 输出转写文本
```

---

## 配置 OpenClaw

### 编辑配置文件

打开 `~/.openclaw/openclaw.json`（或 `openclaw.json5`），找到 `"tools"` 字段，添加 `media.audio` 配置块：

### 最简配置（推荐）

```json
{
  "tools": {
    "media": {
      "audio": {
        "enabled": true,
        "models": [
          {
            "type": "cli",
            "command": "mano-asr",
            "args": ["transcribe", "--format", "text", "{{MediaPath}}"],
            "timeoutSeconds": 120
          }
        ]
      }
    }
  }
}
```

### 带热词和转写回显的完整配置

```json
{
  "tools": {
    "media": {
      "audio": {
        "enabled": true,
        "maxBytes": 31457280,
        "echoTranscript": true,
        "echoFormat": "📝 \"{transcript}\"",
        "models": [
          {
            "type": "cli",
            "command": "mano-asr",
            "args": [
              "transcribe",
              "--format", "text",
              "--hotwords", "OpenClaw,mano-asr,MLX",
              "{{MediaPath}}"
            ],
            "timeoutSeconds": 120
          }
        ]
      }
    }
  }
}
```

### 混合配置（本地优先 + 云端兜底）

如果你同时配置了云端 provider（如 OpenAI），可以让 mano-asr 优先，失败时回退到云端：

```json
{
  "tools": {
    "media": {
      "audio": {
        "enabled": true,
        "models": [
          {
            "type": "cli",
            "command": "mano-asr",
            "args": ["transcribe", "--format", "text", "{{MediaPath}}"],
            "timeoutSeconds": 120
          },
          {
            "provider": "openai",
            "model": "gpt-4o-mini-transcribe"
          }
        ]
      }
    }
  }
}
```

> OpenClaw 按顺序尝试 `models` 数组中的条目，第一个成功的就返回结果。

### 配置字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | boolean | 是否启用音频转写 |
| `maxBytes` | number | 最大文件大小（默认 20MB = 20971520） |
| `echoTranscript` | boolean | 转写后是否先将文本回显给用户确认（默认 false） |
| `echoFormat` | string | 回显格式，`{transcript}` 为占位符 |
| `models[].type` | string | `"cli"` 表示本地命令行工具 |
| `models[].command` | string | 可执行文件名或完整路径 |
| `models[].args` | string[] | 命令参数，`{{MediaPath}}` 由 OpenClaw 替换为实际音频路径 |
| `models[].timeoutSeconds` | number | 超时秒数（默认 60，长音频建议 120） |
| `--hotwords` | — | mano-asr 的热词参数，提升专有名词识别准确率 |

---

## 重启 & 验证

### 重启 OpenClaw Gateway

```bash
openclaw gateway restart
```

### 确认配置已加载

```bash
openclaw config get tools.media.audio
```

### 发送语音测试

通过任意已接入的渠道（企业微信、Telegram、WebChat 等）给 OpenClaw 发送一条语音消息。如果一切正常，AI 助手会基于转写后的文字内容进行回复。

---

## 工作原理

```
┌─────────────┐    ┌──────────────┐    ┌───────────────────┐    ┌──────────────┐
│  用户发送   │    │   OpenClaw   │    │    mano-asr       │    │   AI 模型    │
│  语音消息   │───▶│  接收音频文件 │───▶│  本地 MLX 转写    │───▶│   处理文本   │
└─────────────┘    └──────────────┘    └───────────────────┘    └──────────────┘
                                                │
                                                ▼
                                         纯文本 transcript
                                        注入 {{Transcript}}
```

**详细流程：**

1. 用户通过渠道发送语音/音频消息
2. OpenClaw Gateway 接收并下载音频文件到本地临时目录
3. 检查文件大小是否超过 `maxBytes` 限制
4. 按 `models` 数组顺序调用第一个可用的转写引擎
5. 执行 `mano-asr transcribe --format text <音频路径>`
6. mano-asr 在本地通过 MLX 完成推理，输出纯文本到 stdout
7. OpenClaw 捕获输出，设置 `{{Transcript}}` 模板变量
8. 将转写文本作为消息内容传递给 AI 模型处理
9. AI 模型基于文字内容生成回复

---

## 模型管理

### 查看可用模型

```bash
mano-asr model list
```

```
  Available Models
  ───────────────────────────────────
  Engine: qwen3-asr

  ASR Models:
    * Mano-ASR-0.8B-Instruct-1.0-MLX-8bit (active)
      Fun-ASR-Nano-2512-8bit
  ───────────────────────────────────
```

### 切换模型

```bash
mano-asr model use Fun-ASR-Nano-2512-8bit
mano-asr restart
```

| 模型 | 大小 | 特点 |
|------|------|------|
| Mano-ASR-0.8B-Instruct-1.0-MLX-8bit | ~1GB | 默认启动模型，兼顾速度和精度 |
| Fun-ASR-Nano-2512-8bit | ~500MB | 更轻量，速度更快 |

### 查看当前配置

```bash
mano-asr config show
```

---

## 服务管理

| 命令 | 说明 |
|------|------|
| `mano-asr start` | 启动服务（首次自动下载模型） |
| `mano-asr stop` | 停止服务 |
| `mano-asr restart` | 重启服务 |
| `mano-asr status` | 查看服务状态 |
| `mano-asr logs` | 查看服务日志 |
| `mano-asr doctor` | 环境检查 |

> **注意：** OpenClaw 使用的是 CLI 模式 (`mano-asr transcribe`)。即使后台服务未运行，CLI 也能工作（会临时加载模型）。但保持服务运行可以显著加速转写，因为模型已预加载在内存中。

---

## 高级配置

### 仅在私聊中启用（群聊禁用）

```json
{
  "tools": {
    "media": {
      "audio": {
        "enabled": true,
        "scope": {
          "default": "allow",
          "rules": [
            { "action": "deny", "match": { "chatType": "group" } }
          ]
        },
        "models": [
          {
            "type": "cli",
            "command": "mano-asr",
            "args": ["transcribe", "--format", "text", "{{MediaPath}}"],
            "timeoutSeconds": 120
          }
        ]
      }
    }
  }
}
```

### 指定 mano-asr 完整路径（PATH 找不到时）

```json
{
  "type": "cli",
  "command": "/opt/homebrew/bin/mano-asr",
  "args": ["transcribe", "--format", "text", "{{MediaPath}}"],
  "timeoutSeconds": 120
}
```

### 调整文件大小限制

```json
{
  "tools": {
    "media": {
      "audio": {
        "enabled": true,
        "maxBytes": 52428800,
        "models": [...]
      }
    }
  }
}
```

> 上例将限制设为 50MB。

---

## 故障排除

### 问题：语音消息没有被转写

检查清单：

```bash
# 1. 确认 mano-asr 可用
mano-asr --version

# 2. 确认环境正常
mano-asr doctor

# 3. 确认 OpenClaw 配置
openclaw config get tools.media.audio

# 4. 手动测试转写
mano-asr transcribe --format text /path/to/audio.wav

# 5. 查看 OpenClaw 日志（verbose 模式会显示转写调用）
openclaw gateway restart --verbose
```

### 问题：转写超时

- 增大 `timeoutSeconds`（默认 60，建议设为 120）
- 确保 mano-asr 服务在运行（预加载模型更快）：`mano-asr start`
- 检查音频时长是否过长（默认最大 660 秒）

### 问题：转写结果为空或乱码

- 确认音频文件格式正确（支持 wav/mp3/ogg/webm/m4a/flac）
- 确认 ffmpeg 已安装：`ffmpeg -version`
- 尝试切换模型：`mano-asr model use Mano-ASR-0.8B-Instruct-1.0-MLX-8bit`

### 问题：找不到 mano-asr 命令

```bash
# 确认安装位置
which mano-asr
# 通常为 /opt/homebrew/bin/mano-asr

# 如果不在 PATH 中，在配置里使用完整路径
# "command": "/opt/homebrew/bin/mano-asr"
```

---

## 更新与卸载

### 更新 mano-asr

```bash
brew upgrade mano-asr
mano-asr restart  # 如果服务在运行
```
