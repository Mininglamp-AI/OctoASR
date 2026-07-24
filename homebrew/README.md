# Homebrew 打包指南

## 本地测试

### 一键测试

```bash
chmod +x homebrew/test-local.sh
./homebrew/test-local.sh
```

这会自动执行：构建 bottle → 安装 Formula → 验证安装。

### 手动测试

1. 构建 bottle:

```bash
chmod +x homebrew/build-bottle.sh
./homebrew/build-bottle.sh
```

2. 安装本地 Formula:

```bash
brew install --formula homebrew/octoasr-local.rb
```

3. 验证:

```bash
octoasr --version
octoasr doctor
octoasr model list
octoasr start
octoasr status
octoasr stop
```

4. 卸载:

```bash
octoasr stop
brew uninstall octoasr
rm -rf ~/.octoasr
```

## 发布流程

### 1. 构建发布包

```bash
chmod +x homebrew/build-release.sh
./homebrew/build-release.sh
```

生成文件（`build/release-v0.1.0/`）：
- `mano-asr-0.1.0.tar.gz` - 源代码
- `Mano-ASR-0.8B-Instruct-1.0-MLX-8bit.tar.gz` - Mano-ASR 模型（默认）
- `Qwen3-ASR-1_7B-8bit.tar.gz` - Qwen3 ASR 模型
- `fsmn-vad-mlx.tar.gz` - VAD 模型
- `SHA256SUMS.txt` - 校验和

### 2. 创建 GitHub Release

```bash
git tag v0.1.0
git push origin v0.1.0

gh release create v0.1.0 \
  build/release-v0.1.0/mano-asr-0.1.0.tar.gz \
  build/release-v0.1.0/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit.tar.gz \
  build/release-v0.1.0/Qwen3-ASR-1_7B-8bit.tar.gz \
  build/release-v0.1.0/fsmn-vad-mlx.tar.gz \
  --title "octoasr v0.1.0" \
  --notes "首次发布"
```

### 3. 设置 Homebrew Tap

```bash
# 创建 Tap 仓库: octoasr/homebrew-octoasr
mkdir -p Formula
cp homebrew/octoasr.rb Formula/
# 更新 Formula 中的 SHA256 值（参考 SHA256SUMS.txt）
git add . && git commit -m "Add octoasr v0.1.0" && git push
```

### 4. 用户安装

```bash
brew tap octoasr/octoasr
brew install octoasr
```

## 包含的模型

| 模型 | 大小 | 用途 |
|------|------|------|
| Mano-ASR-0.8B-Instruct-1.0-MLX-8bit | ~0.8GB | 默认引擎 |
| Qwen3-ASR-1_7B-8bit | ~2.2GB | Qwen3-ASR 引擎 |
| fsmn-vad-mlx | ~2MB | VAD 语音活动检测 |

## 文件说明

| 文件 | 用途 |
|------|------|
| `octoasr.rb` | 发布用 Formula（GitHub Release URL） |
| `octoasr-local.rb` | 本地测试用 Formula（file:// URL） |
| `build-bottle.sh` | 构建预编译 Bottle |
| `build-release.sh` | 构建发布包（源码 + 模型 tar.gz） |
| `test-local.sh` | 一键本地测试 |
