@echo off
echo Starting PodDub AI...

:: 1. Start Backend Server (New Window)
echo Starting Python Backend Server...
start "PodDub Backend" cmd /k "cd server && python tts_server.py"

:: 2. Start Frontend Server (New Window)
echo Starting React Frontend...
:: Wait a second for backend to init
timeout /t 2 /nobreak >nul
start "PodDub Frontend" cmd /k "npm run dev"

echo.
echo ===================================================
echo   Servers launched in separate windows.
echo   Opening Browser at http://localhost:3000...
echo ===================================================
timeout /t 3 /nobreak >nul
start http://localhost:3000
echo.
pause
