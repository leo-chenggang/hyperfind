@echo off
REM HyperFind Windows 构建脚本
REM 前提: Python 3.9+ 已安装, 并执行 pip install -r requirements.txt
REM 用法: 在项目根目录运行 build_win.bat

echo === HyperFind Windows Build ===

REM 1. 清理
rmdir /s /q build dist 2>nul
echo [1/3] Cleaned

REM 2. PyInstaller
echo [2/3] Building...
python -m PyInstaller app.spec --clean --noconfirm

REM 3. 输出
echo [3/3] Done!
dir dist\HyperFind.exe
echo.
echo 将 dist\HyperFind.exe 发给朋友即可运行。
