#!/bin/bash
# build-bottle.sh - 构建预编译 Bottle（不含模型，首次运行自动下载）
# 使用方法: ./homebrew/build-bottle.sh

set -e

VERSION="0.1.1"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/build/bottle"

# 检测 Python
PYTHON=""
for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "  ✗ 未找到 Python 3，请安装 Python 3.10+"
    exit 1
fi
PYTHON_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

# 检测 macOS bottle tag
MACOS_TAG="arm64_$(sw_vers -productVersion | cut -d. -f1 | xargs -I{} python3 -c "
names={15:'sequoia',14:'sonoma',13:'ventura',12:'monterey',11:'big_sur'}
print(names.get({},f'macos{}'))
")"
# fallback: 用 brew 检测
if echo "$MACOS_TAG" | grep -q "macos"; then
    MACOS_TAG="arm64_$(brew ruby -e 'puts MacOS.version.to_sym' 2>/dev/null || echo 'sonoma')"
fi
BOTTLE_NAME="mano-asr--${VERSION}.${MACOS_TAG}.bottle.tar.gz"

echo ""
echo "  mano-asr Bottle 构建 v$VERSION"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Python:     $PYTHON ($PYTHON_VERSION)"
echo "  macOS tag:  $MACOS_TAG"
echo ""

# 清理
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/mano-asr/$VERSION"

INSTALL_DIR="$BUILD_DIR/mano-asr/$VERSION"

# 1. 创建虚拟环境并安装依赖
echo "  [1/6] 创建虚拟环境..."
"$PYTHON" -m venv "$INSTALL_DIR/libexec"

echo "  [2/6] 安装依赖..."
"$INSTALL_DIR/libexec/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/libexec/bin/pip" install "$PROJECT_DIR" -q

# 2. 复制核心代码（server.py, core/, utils/）
echo "  [3/6] 复制核心代码..."
SITE_PACKAGES="$INSTALL_DIR/libexec/lib/python${PYTHON_VERSION}/site-packages"
cp -r "$PROJECT_DIR/core" "$SITE_PACKAGES/"
cp -r "$PROJECT_DIR/utils" "$SITE_PACKAGES/"
cp "$PROJECT_DIR/server.py" "$SITE_PACKAGES/"

# 3. 创建启动脚本
echo "  [4/6] 创建启动脚本..."
mkdir -p "$INSTALL_DIR/bin"
cat > "$INSTALL_DIR/bin/mano-asr" << 'SCRIPT'
#!/bin/bash
SCRIPT_PATH="$0"
if [ -L "$0" ]; then
    SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || readlink "$0")"
fi
CELLAR_DIR="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
PYTHON_VERSION=$(ls "$CELLAR_DIR/libexec/lib/" | grep python | head -1)
exec "$CELLAR_DIR/libexec/bin/$PYTHON_VERSION" -m manoasr.cli.main "$@"
SCRIPT
chmod +x "$INSTALL_DIR/bin/mano-asr"

# 4. 创建 INSTALL_RECEIPT.json
echo "  [5/6] 创建元数据..."
cat > "$INSTALL_DIR/INSTALL_RECEIPT.json" << EOF
{
  "homebrew_version": "4.0.0",
  "used_options": [],
  "unused_options": [],
  "built_as_bottle": true,
  "poured_from_bottle": true,
  "installed_as_dependency": false,
  "installed_on_request": true,
  "time": $(date +%s),
  "source": {
    "spec": "stable",
    "versions": {
      "stable": "$VERSION"
    }
  }
}
EOF

# 5. 清理 bottle 中的无用文件
find "$BUILD_DIR" -name ".DS_Store" -delete 2>/dev/null
find "$BUILD_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# 6. 打包 Bottle
echo "  [6/6] 打包 Bottle..."
cd "$BUILD_DIR"
tar -czf "$BOTTLE_NAME" mano-asr

BOTTLE_SHA256=$(shasum -a 256 "$BOTTLE_NAME" | cut -d' ' -f1)

# 移动到 release 目录
mkdir -p "$PROJECT_DIR/build/release-v$VERSION"
FINAL_BOTTLE_NAME="mano-asr-$VERSION.${MACOS_TAG}.bottle.tar.gz"
mv "$BOTTLE_NAME" "$PROJECT_DIR/build/release-v$VERSION/$FINAL_BOTTLE_NAME"

# 清理临时 bottle 目录
rm -rf "$BUILD_DIR"

BOTTLE_SIZE=$(ls -lh "$PROJECT_DIR/build/release-v$VERSION/$FINAL_BOTTLE_NAME" | awk '{print $5}')

echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ Bottle 构建完成"
echo ""
echo "  文件:   build/release-v$VERSION/$FINAL_BOTTLE_NAME"
echo "  大小:   $BOTTLE_SIZE"
echo "  SHA256: $BOTTLE_SHA256"

# 自动更新 mano-asr-local.rb 中的 sha256 和路径
LOCAL_FORMULA="$PROJECT_DIR/homebrew/mano-asr-local.rb"
if [ -f "$LOCAL_FORMULA" ]; then
    sed -i '' "s|root_url \"file://.*\"|root_url \"file://$PROJECT_DIR/build/release-v$VERSION\"|" "$LOCAL_FORMULA"
    # 尝试替换已有的 tag 行；如果不存在则在 root_url 后追加
    if grep -q "$MACOS_TAG" "$LOCAL_FORMULA"; then
        sed -i '' "s/sha256 cellar: :any_skip_relocation, $MACOS_TAG: \".*\"/sha256 cellar: :any_skip_relocation, $MACOS_TAG: \"$BOTTLE_SHA256\"/" "$LOCAL_FORMULA"
    else
        sed -i '' "/root_url/a\\
    sha256 cellar: :any_skip_relocation, $MACOS_TAG: \"$BOTTLE_SHA256\"
" "$LOCAL_FORMULA"
    fi
    echo ""
    echo "  ✓ mano-asr-local.rb 已自动更新"
fi

echo ""
echo "  本地测试:"
echo "    brew install --formula $LOCAL_FORMULA"
echo "    mano-asr --version"
echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
