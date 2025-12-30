@echo off
echo ========================================================
echo       PodDub AI - Unified Start/Restart Script
echo ========================================================

echo.
echo [1/3] Cleaning up old processes...

:: 1. Force Kill Backend (tts_server.py)
echo    - Stopping Backend...
:: 1. Force Kill Backend (tts_server.py) - ROBUST PORT KILL
echo    - Stopping Backend (Port 8000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul & echo    - Killed PID %%a

:: Change to fallback if netstat fails (kill by name just in case)
taskkill /F /IM python.exe /FI "WINDOWTITLE eq PodDub Backend*" 2>nul

:: 2. Force Kill Frontend (Node/Vite on Port 3000)
echo    - Stopping Frontend (Port 3000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul & echo    - Killed PID %%a
taskkill /F /IM node.exe /FI "WINDOWTITLE eq PodDub Frontend*" 2>nul

:: Wait for cleanup
timeout /t 2 /nobreak >nul

echo.
echo [2/3] Starting Services...

:: 3. Start Backend
echo    - Launching Backend Server...
start "PodDub Backend" cmd /k "cd server && python tts_server.py"

:: 4. Start Frontend
echo    - Launching Frontend...
start "PodDub Frontend" cmd /k "npm run dev"

echo.
echo [3/3] Launching Browser...
timeout /t 3 /nobreak >nul
start http://localhost:3000

echo.
echo ========================================================
echo   Done! PodDub AI is running.
echo   - Backend: Port 8000
echo   - Frontend: Port 3000
echo ========================================================
pause
