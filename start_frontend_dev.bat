@echo off
cd /d "%~dp0frontend"
echo ============================================
echo   KnowBot frontend (dev mode) on port 5173
echo   Backend must be running on port 8000!
echo ============================================
npm run dev
pause
