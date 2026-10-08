@echo off
title History Master
cd /d "%~dp0"
echo ============================================
echo   History Master - starting...
echo ============================================

if not exist "frontend\dist" (
    echo Building frontend, please wait...
    pushd frontend
    call npm install
    call npm run build
    popd
)

start "HistoryMaster-Backend" "%~dp0backend\run_server.bat"

echo Waiting for the server to become ready (can take 1-2 minutes on first start)...
set /a tries=0
:waitloop
ping -n 6 127.0.0.1 > nul
set /a tries+=1
curl -s -m 3 http://localhost:8000/api/health > nul 2>&1
if errorlevel 1 (
    if %tries% lss 36 goto waitloop
    echo.
    echo WARNING: server not ready yet. It may still be loading - open
    echo http://localhost:8000 in a minute, or check the backend window.
    pause
    exit /b
)

start "" http://localhost:8000
echo.
echo   History Master is running:  http://localhost:8000
echo   API docs:                   http://localhost:8000/docs
echo   Login: admin/admin123  or  user/user123
echo   (Close the backend window to stop the server.)
echo.
pause
