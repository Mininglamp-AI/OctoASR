#!/bin/bash
# build-release.sh - 构建 mano-asr 发布包（含全部模型）
# 使用方法: ./homebrew/build-release.sh

set -e

VERSION="0.1.9"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
RELEASE_DIR="$BUILD_DIR/release-v$VERSION"

echo ""
echo "  mano-asr 发布构建 v$VERSION"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 清理构建目录
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# 1. 打包源代码
echo "  [1/5] 打包源代码..."
cd "$PROJECT_ROOT"
git archive --format=tar.gz --prefix=mano-asr-$VERSION/ -o "$RELEASE_DIR/mano-asr-$VERSION.tar.gz" HEAD 2>/dev/null || \
    tar --exclude='.git' --exclude='build' --exclude='*.pyc' --exclude='__pycache__' \
        --exclude='models/mlx-community.zip' --exclude='models/Qwen3-ASR-1_7B-8bit.zip' \
        --exclude='.idea' --exclude='.DS_Store' \
        -czf "$RELEASE_DIR/mano-asr-$VERSION.tar.gz" -C "$PROJECT_ROOT/.." "$(basename $PROJECT_ROOT)"

SOURCE_SHA256=$(shasum -a 256 "$RELEASE_DIR/mano-asr-$VERSION.tar.gz" | cut -d' ' -f1)
echo "    ✓ mano-asr-$VERSION.tar.gz (SHA256: ${SOURCE_SHA256:0:16}...)"

# 2. 打包 ASR 模型 - Mano-ASR
echo "  [2/5] 打包 Mano-ASR-0.8B-Instruct-1.0-MLX-8bit..."
ASR_MODEL_DIR="$PROJECT_ROOT/models/Mininglamp-2718/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit"
if [ -d "$ASR_MODEL_DIR" ]; then
    tar -czf "$RELEASE_DIR/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit.tar.gz" -C "$PROJECT_ROOT/models/Mininglamp-2718" "Mano-ASR-0.8B-Instruct-1.0-MLX-8bit"
    ASR_SHA256=$(shasum -a 256 "$RELEASE_DIR/Mano-ASR-0.8B-Instruct-1.0-MLX-8bit.tar.gz" | cut -d' ' -f1)
    echo "    ✓ SHA256: ${ASR_SHA256:0:16}..."
else
    echo "    ✗ 目录不存在: $ASR_MODEL_DIR"
    ASR_SHA256="MISSING"
fi

# 3. 打包 ASR 模型 - Qwen3-ASR
echo "  [3/5] 打包 Qwen3-ASR-1_7B-8bit..."
QWEN3_MODEL_DIR="$PROJECT_ROOT/models/mlx-community/Qwen3-ASR-1_7B-8bit"
if [ -d "$QWEN3_MODEL_DIR" ]; then
    tar -czf "$RELEASE_DIR/Qwen3-ASR-1_7B-8bit.tar.gz" -C "$PROJECT_ROOT/models/mlx-community" "Qwen3-ASR-1_7B-8bit"
    QWEN3_SHA256=$(shasum -a 256 "$RELEASE_DIR/Qwen3-ASR-1_7B-8bit.tar.gz" | cut -d' ' -f1)
    echo "    ✓ SHA256: ${QWEN3_SHA256:0:16}..."
else
    echo "    ✗ 目录不存在: $QWEN3_MODEL_DIR"
    QWEN3_SHA256="MISSING"
fi

# 4. 打包 VAD 模型
echo "  [4/5] 打包 fsmn-vad-mlx..."
VAD_MODEL_DIR="$PROJECT_ROOT/models/fsmn-vad-mlx"
if [ -d "$VAD_MODEL_DIR" ]; then
    tar -czf "$RELEASE_DIR/fsmn-vad-mlx.tar.gz" -C "$PROJECT_ROOT/models" "fsmn-vad-mlx"
    VAD_SHA256=$(shasum -a 256 "$RELEASE_DIR/fsmn-vad-mlx.tar.gz" | cut -d' ' -f1)
    echo "    ✓ SHA256: ${VAD_SHA256:0:16}..."
else
    echo "    ✗ 目录不存在: $VAD_MODEL_DIR"
    VAD_SHA256="MISSING"
fi

# 5. 生成 SHA256 摘要文件
echo "  [5/5] 生成摘要..."
cat > "$RELEASE_DIR/SHA256SUMS.txt" << EOF
# mano-asr v$VERSION SHA256 Checksums

Source:
  $SOURCE_SHA256  mano-asr-$VERSION.tar.gz

Models:
  $ASR_SHA256  Mano-ASR-0.8B-Instruct-1.0-MLX-8bit.tar.gz
  $QWEN3_SHA256  Qwen3-ASR-1_7B-8bit.tar.gz
  $VAD_SHA256  fsmn-vad-mlx.tar.gz
EOF

echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ 构建完成"
echo ""
echo "  发布文件: $RELEASE_DIR"
ls -lh "$RELEASE_DIR"/*.tar.gz 2>/dev/null | awk '{print "    " $NF " (" $5 ")"}'
echo ""
echo "  下一步:"
echo "    1. 创建 GitHub Release v$VERSION"
echo "    2. 上传 $RELEASE_DIR 中的 .tar.gz 文件"
echo "    3. 更新 Homebrew Tap Formula 中的 SHA256"
echo ""
