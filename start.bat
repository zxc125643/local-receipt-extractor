@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set CORE_GATEWAY_DATA_DIR=%USERPROFILE%\.core-gateway

echo ============================================
echo   Outlook Batch Manager 启动器
echo ============================================
echo.

REM Check if proxy pool has sources
if not exist "..\proxy_pool\sources\*.txt" (
    echo [WARN] proxy_pool/sources/ 目录没有代理源文件
)

echo [1/4] 启动后端 API 服务 ...
start "outlook-backend" /B "C:\Users\yiliu\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --log-level error
if %errorlevel% neq 0 (
    echo [ERROR] 后端启动失败
    pause
    exit /b 1
)
timeout /t 3 /nobreak >nul

echo [2/4] 前端开发服务器 ...
start "outlook-ui" /B cmd /c "npm run dev:ui 2>&1"
timeout /t 5 /nobreak >nul

echo [3/4] 验证服务状态 ...
curl -s http://127.0.0.1:8765/health >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] 后端 API: http://127.0.0.1:8765
    echo   [OK] 前端 UI:  http://127.0.0.1:5199
) else (
    echo   [FAIL] 后端服务未响应
)

echo.
echo [4/4] 打开浏览器 ...
start http://127.0.0.1:5199

echo.
echo ============================================
echo   服务已启动！
echo   后端 API:    http://127.0.0.1:8765
echo   前端 UI:     http://127.0.0.1:5173
echo   健康检查:    http://127.0.0.1:8765/health
echo ============================================
echo.
echo 按任意键停止所有服务 ...
pause >nul

echo 正在停止服务 ...
taskkill /f /im python.exe /t >nul 2>&1
taskkill /f /im node.exe /t >nul 2>&1
echo 已停止。
