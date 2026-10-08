@echo off
cd /d "%~dp0"
echo Starting History Master backend...
call "%~dp0backend\run_server.bat"
