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
echo   Please wait for 'Local: http://localhost:5173'
echo   to appear in the Frontend window.
echo ===================================================
echo.
pause
