#!/bin/bash
# HyperFind macOS 构建脚本
# 用法: bash build_mac.sh
set -e

cd "$(dirname "$0")"

echo "=== HyperFind macOS Build ==="

# 1. 清理旧构建
rm -rf build dist
echo "[1/4] Cleaned old builds"

# 2. 生成图标 (icns)
if [ -f assets/icon.png ]; then
    mkdir -p assets
    sips -s format icns assets/icon.png --out assets/icon.icns 2>/dev/null || true
    echo "[2/4] Icon prepared"
else
    echo "[2/4] No icon.png, skipping"
fi

# 3. PyInstaller 打包 (排除用户级冗余)
echo "[3/4] Building with PyInstaller..."
PYTHONNOUSERSITE=1 .venv/bin/pyinstaller app.spec --clean --noconfirm

# 4. 输出
echo "[4/4] Done!"
ls -lh dist/
echo ""
echo "App: dist/HyperFind.app"
