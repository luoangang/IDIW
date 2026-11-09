@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing_python
if not exist "logs" mkdir "logs"
".venv\Scripts\python.exe" -X utf8 platform_main.py list packages >nul
if errorlevel 1 goto preflight_failed
start "Crawler Platform API" /min cmd.exe /d /c ""%CD%\.venv\Scripts\python.exe" -X utf8 "%CD%\platform_main.py" serve 1>>"%CD%\logs\api.log" 2>&1"
start "Crawler Platform Worker" /min cmd.exe /d /c ""%CD%\.venv\Scripts\python.exe" -X utf8 "%CD%\platform_main.py" worker 1>>"%CD%\logs\worker.log" 2>&1"
start "Crawler Platform Scheduler" /min cmd.exe /d /c ""%CD%\.venv\Scripts\python.exe" -X utf8 "%CD%\platform_main.py" scheduler 1>>"%CD%\logs\scheduler.log" 2>&1"
for /l %%i in (1,1,15) do (
    curl.exe --silent --fail http://127.0.0.1:8090/health/live >nul 2>&1
    if not errorlevel 1 goto ready
    timeout /t 1 /nobreak >nul
)
echo API did not start. Check logs\api.log.
pause
exit /b 1
:ready
echo Platform ready: http://127.0.0.1:8090/
pause
exit /b 0
:missing_python
echo Python environment missing: .venv\Scripts\python.exe
pause
exit /b 1
:preflight_failed
echo Platform preflight failed. Check Python and database settings.
pause
exit /b 1
