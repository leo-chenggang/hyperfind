#!/bin/bash
# HyperFind macOS 构建脚本
# 用法: bash build_mac.sh
set -e

cd "$(dirname "$0")"

echo "=== HyperFind macOS Build ==="

# 1. 清理旧构建
rm -rf build dist
echo "[1/5] Cleaned old builds"

# 2. 生成图标 (icns)
if [ -f assets/icon.png ]; then
    mkdir -p assets
    sips -s format icns assets/icon.png --out assets/icon.icns 2>/dev/null || true
    echo "[2/5] Icon prepared"
else
    echo "[2/5] No icon.png, skipping"
fi

# 3. PyInstaller 打包 (排除用户级冗余)
echo "[3/5] Building with PyInstaller..."
PYTHONNOUSERSITE=1 .venv/bin/pyinstaller app.spec --clean --noconfirm

# 4. Ad-hoc codesign — 绕过 Gatekeeper 对每个 .so/.dylib 的逐个验证
echo "[4/5] Signing app bundle..."
codesign --force --deep --sign - dist/HyperFind.app 2>&1 || echo "  (codesign skipped — may already be signed)"

# 5. First-launch warmup — 预解压 + 预审核所有 native 库，消除首次启动挂起
echo "[5/5] First-launch warmup (pre-validating native libraries)..."
HP_BIN="dist/HyperFind.app/Contents/MacOS/HyperFind"
if [ -x "$HP_BIN" ]; then
    echo "  Running warmup with HYPERFIND_WARMUP=1 (max 120s)..."
    HYPERFIND_WARMUP=1 "$HP_BIN" &
    HP_PID=$!
    # 等待进程完成初始化或超时
    EXIT_CODE=0
    for i in $(seq 1 120); do
        if ! kill -0 $HP_PID 2>/dev/null; then
            wait $HP_PID 2>/dev/null && EXIT_CODE=$? || EXIT_CODE=$?
            echo "  Warmup completed in ${i}s (exit code: $EXIT_CODE)"
            break
        fi
        sleep 1
        if [ $((i % 10)) -eq 0 ]; then
            echo "  Warmup in progress... ${i}s"
        fi
    done
    # 超时则强制终止 + 清理 PyInstaller lock 文件
    if kill -0 $HP_PID 2>/dev/null; then
        echo "  Warmup timeout (120s) — killing process"
        kill $HP_PID 2>/dev/null || true
        sleep 2
        kill -9 $HP_PID 2>/dev/null || true
        # 清理残留的 PyInstaller lock 文件，避免死锁下次启动
        RUNTIME_DIR="$HOME/.hermes/hyperfind_runtime"
        rm -f "$RUNTIME_DIR/.pyilock" 2>/dev/null || true
    fi
else
    echo "  Binary not found, skipping warmup"
fi

echo ""
echo "=== Build Complete ==="
ls -lh dist/
echo ""
echo "App: dist/HyperFind.app"
echo "Size: $(du -sh dist/HyperFind.app | cut -f1)"
