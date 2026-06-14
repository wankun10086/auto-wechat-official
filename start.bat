@echo off
chcp 65001 >nul
title Auto WeChat - 公众号自动化发布系统
echo.
echo  ╔══════════════════════════════════════╗
echo  ║   Auto WeChat - 公众号自动化发布系统   ║
echo  ╚══════════════════════════════════════╝
echo.
echo  正在启动服务...
echo.

cd /d "%~dp0"

:: 检查依赖
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo  [!] 正在安装依赖...
    pip install -r requirements.txt
)

:: 检查前端构建
if not exist "web\frontend\dist\index.html" (
    echo  [!] 正在构建前端...
    cd web\frontend
    call npm install
    call npm run build
    cd /d "%~dp0"
)

:: 启动服务
echo.
echo  ✓ 服务启动成功！
echo  ✓ 浏览器打开: http://localhost:8000
echo.
echo  按 Ctrl+C 停止服务
echo.

python -m web.server 8000

pause
