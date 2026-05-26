#!/bin/bash
# test-local.sh - 一键本地 Homebrew 测试
# 使用方法: ./homebrew/test-local.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FORMULA="$PROJECT_DIR/homebrew/mano-asr-local.rb"
TAP_DIR="/opt/homebrew/Library/Taps/local/homebrew-mano-asr/Formula"

echo ""
echo "  mano-asr 本地 Homebrew 测试"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查 brew
if ! command -v brew &>/dev/null; then
    echo "  ✗ 未找到 Homebrew，请先安装"
    exit 1
fi

# 步骤 1: 构建 bottle
echo "  [1/4] 构建 Bottle..."
echo ""
bash "$PROJECT_DIR/homebrew/build-bottle.sh"
echo ""

# 步骤 2: 卸载旧版本（如果存在）
echo "  [2/4] 清理旧安装..."
if brew list mano-asr &>/dev/null; then
    echo "    卸载已有的 mano-asr..."
    mano-asr stop 2>/dev/null || true
    brew uninstall mano-asr 2>/dev/null || true
fi

# 步骤 3: 复制 formula 到 tap 并安装
echo "  [3/4] 安装 Formula..."
if [ ! -d "$TAP_DIR" ]; then
    echo "    创建本地 tap..."
    brew tap-new local/mano-asr 2>/dev/null || true
    mkdir -p "$TAP_DIR"
fi
cp "$FORMULA" "$TAP_DIR/mano-asr.rb"
HOMEBREW_NO_AUTO_UPDATE=1 brew install local/mano-asr/mano-asr

# 步骤 4: 验证
echo ""
echo "  [4/4] 验证安装..."
echo ""

PASS=0
FAIL=0

# 版本检查
VERSION_OUTPUT=$(mano-asr --version 2>&1 || true)
if echo "$VERSION_OUTPUT" | grep -q "0.1.1"; then
    echo "    ✓ mano-asr --version"
    PASS=$((PASS + 1))
else
    echo "    ✗ mano-asr --version (输出: $VERSION_OUTPUT)"
    FAIL=$((FAIL + 1))
fi

# doctor 检查
if mano-asr doctor &>/dev/null; then
    echo "    ✓ mano-asr doctor"
    PASS=$((PASS + 1))
else
    echo "    ! mano-asr doctor (部分检查未通过)"
    FAIL=$((FAIL + 1))
fi

# 帮助信息
HELP_OUTPUT=$(mano-asr help 2>&1 || true)
if echo "$HELP_OUTPUT" | grep -q "transcribe"; then
    echo "    ✓ mano-asr help"
    PASS=$((PASS + 1))
else
    echo "    ✗ mano-asr help"
    FAIL=$((FAIL + 1))
fi

# 检查模型目录（模型现在按需下载到 ~/.mano-asr/models/）
USER_MODELS_DIR="$HOME/.mano-asr/models"
if [ -d "$USER_MODELS_DIR" ]; then
    echo "    ✓ 用户模型目录存在: $USER_MODELS_DIR"
    PASS=$((PASS + 1))

    if [ -d "$USER_MODELS_DIR/mlx-community/Fun-ASR-Nano-2512-8bit" ]; then
        echo "    ✓ Fun-ASR-Nano-2512-8bit 模型（已下载）"
        PASS=$((PASS + 1))
    else
        echo "    ℹ Fun-ASR-Nano-2512-8bit 未下载（首次 mano-asr start 时自动下载）"
    fi

    if [ -d "$USER_MODELS_DIR/fsmn-vad-mlx" ]; then
        echo "    ✓ fsmn-vad-mlx 模型（已下载）"
        PASS=$((PASS + 1))
    else
        echo "    ℹ fsmn-vad-mlx 未下载（首次 mano-asr start 时自动下载）"
    fi
else
    echo "    ℹ 模型目录不存在（首次 mano-asr start 时自动创建并下载模型）"
fi

echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAIL -eq 0 ]; then
    echo "  ✓ 全部通过 ($PASS/$PASS)"
    echo ""
    echo "  可以继续测试:"
    echo "    mano-asr start          # 启动服务"
    echo "    mano-asr model list     # 查看模型"
    echo "    mano-asr status         # 查看状态"
    echo "    mano-asr stop           # 停止服务"
else
    echo "  ! 通过 $PASS / 失败 $FAIL"
fi
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
