@echo off
chcp 65001 >nul
title 停止 Auto WeChat
echo 正在停止 Auto WeChat 服务（端口 8000）...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
if exist "data\server.pid" del /q "data\server.pid"
echo 已停止。
timeout /t 2 >nul
