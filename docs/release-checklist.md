# OctoASR 线上发布检查清单

## 已完成

- [x] `utils/__init__.py` 加入 git 跟踪（修复 daemon 启动 ModuleNotFoundError）
- [x] `pyproject.toml` 添加 `python-multipart` 依赖（修复 FastAPI 文件上传报错）
- [x] ModelScope 下载进度条清理（OS 级 stderr 重定向）
- [x] 模型完整性检查（`_is_model_complete`：验证 safetensors 文件 + 无残留 temp）
- [x] 自动探测网络环境选择下载源（`_detect_preferred_source`）
- [x] `homebrew/octoasr.rb` 添加 `arm64_tahoe` (macOS 26) bottle 标签
- [x] `.gitignore` 排除 `homebrew/octoasr-local.rb`（防止本地测试路径泄露）

## 占位符（发布前必须替换）

> **以下占位符在代码中用 `PLACEHOLDER_*` 标记，发布前必须替换为真实值，否则功能不可用。**

### 1. Homebrew Formula SHA256

**文件：** `homebrew/octoasr.rb`

| 占位符 | 说明 | 何时可获取 |
|--------|------|-----------|
| `PLACEHOLDER_SOURCE_SHA256` | 源码包 tar.gz 的 SHA256 | 在发布平台创建 Release 上传源码后，`shasum -a 256` 计算 |
| `PLACEHOLDER_BOTTLE_SHA256`（×3） | 各 macOS 版本 bottle 的 SHA256 | 运行 `build-bottle.sh` 后自动输出，或 `build-release.sh` 计算 |

**替换方式：**
```bash
# build-bottle.sh 输出示例：
#   SHA256: 4dbc8306f0400aeee289b1633782c8bee14befd7f7e7575d031a145aa3a27516
# 将该值填入对应的 arm64_tahoe / arm64_sequoia / arm64_sonoma 行

# 或用 build-release.sh 一键生成所有 SHA256
./homebrew/build-release.sh
```

### 2. VAD 模型 ModelScope 仓库 ID

**文件：** `octoasr/cli/utils/constants.py`

```python
MODELSCOPE_REPO_MAP = {
    ...
    "fsmn-vad-mlx": "PLACEHOLDER_MODELSCOPE_REPO_ID",  # <-- 替换
}
```

**影响：** 中国大陆用户（HuggingFace 不可达）将无法自动下载 VAD 模型，导致 VAD 功能不可用。

**操作步骤：**
1. 将 `fsmn-vad-mlx` 模型上传到 ModelScope
2. 获取仓库 ID（格式：`用户名/fsmn-vad-mlx`）
3. 替换 `PLACEHOLDER_MODELSCOPE_REPO_ID` 为真实仓库 ID

## 待确认

### 发布平台选择

**当前状态：** `homebrew/octoasr.rb` 和 `constants.py` 中的地址指向 `github.com/octoasr/octoasr`，但 git remote 是 `code.mlamp.cn`。

**需要决定：**
- Homebrew bottle 和源码包托管在哪里？（GitHub Release / code.mlamp.cn / 其他）
- 确定后需要修改以下文件：
  - `homebrew/octoasr.rb` — `homepage`、`url`、`root_url`
  - `octoasr/cli/utils/constants.py` — `GITHUB_RELEASE_BASE_URL`

### scripts/ 和 exp/ 含硬编码个人路径

`scripts/eval/` 和 `exp/infer/` 中的脚本包含大量 `/Users/mlamp/...` 硬编码路径，且已被 git 跟踪。如果推送到线上，他人可见。

**建议：** 发布前将这些目录加入 `.gitignore` 并从 git 中移除，或将路径改为相对路径/环境变量。

**如果用 GitHub：**
1. 创建 `github.com/octoasr/octoasr` 仓库
2. 创建 Release `v0.1.0`
3. 上传 bottle 和模型包作为 Release Asset
4. 用真实 SHA256 替换上述占位符
5. 创建 Homebrew Tap 仓库（如 `github.com/octoasr/homebrew-tap`）

**如果用 code.mlamp.cn：**
1. 修改 formula 和 constants.py 中所有 URL
2. 确保 code.mlamp.cn 支持 Releases / 文件下载

## 发布步骤概览

```bash
# 1. 替换所有 PLACEHOLDER（见上方）

# 2. 构建 bottle
./homebrew/build-bottle.sh

# 3. 打包 release（源码 + 模型）
./homebrew/build-release.sh

# 4. 在发布平台创建 Release v0.1.0
#    上传 build/release-v0.1.0/ 下所有 .tar.gz

# 5. 用 SHA256 更新 homebrew/octoasr.rb

# 6. 创建 Homebrew Tap 仓库
#    将 octoasr.rb 放入 Formula/ 目录

# 7. 用户安装命令：
#    brew tap octoasr/tap
#    brew install octoasr
```
