@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set CORE_GATEWAY_DATA_DIR=%USERPROFILE%\.core-gateway

echo ============================================
echo   代理池重扫 + 重导入
echo ============================================
echo.

REM Step 1: Scan proxy_pool sources
echo [1/3] 扫描 proxy_pool/sources/ 中的代理文件 ...
cd /d "%~dp0..\..\proxy_pool"
C:\Users\yiliu\AppData\Local\Programs\Python\Python312\python.exe -c "from proxy_pool.pool import ProxyPool; ProxyPool().sync_from_sources(lambda d,t: print(f'  Progress: {d}/{t}', end='\r') if d%%500==0 else None)"
echo   [OK] proxy_pool 扫描完成

REM Step 2: Import into outlook-batch-manager DB
echo.
echo [2/3] 导入到 outlook-batch-manager 数据库 ...
cd /d "%~dp0.."
C:\Users\yiliu\AppData\Local\Programs\Python\Python312\python.exe scripts\import_proxies.py
echo   [OK] 导入完成

echo.
echo [3/3] 完成！
echo   代理池已更新，可重新启动服务开始注册。
pause
