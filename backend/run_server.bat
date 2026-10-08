@echo off
REM History Master - backend server launcher (used by run_demo.bat / start_backend.bat)
cd /d "%~dp0"
title History Master - Backend
REM Embedding model is cached locally - skip the slow online check
set HF_HUB_OFFLINE=1
echo ============================================
echo   History Master backend starting...
echo   First start can take 1-2 minutes (AI model loading).
echo   Keep this window OPEN while using the app.
echo ============================================
"..\venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo.
echo The server exited. If there is an error above, read it and try again.
pause
