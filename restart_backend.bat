@echo off
echo ==========================================
echo      Restarting PodDub (Backend Only)
echo ==========================================

echo 1. Stopping existing tts_server.py...
:: Use PowerShell to find and kill the specific python process running tts_server.py
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe' AND CommandLine LIKE '%tts_server.py%'\" | Stop-Process -Force"

:: Wait a moment
timeout /t 2 /nobreak >nul

echo.
echo 2. Starting new Backend Server...
start "PodDub Backend" cmd /k "cd server && python tts_server.py"

echo.
echo Done! Backend restarted in a new window.
echo You can close this window now.
pause
