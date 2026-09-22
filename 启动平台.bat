@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PATH=C:\ProgramData\Anaconda3\Library\bin;C:\ProgramData\Anaconda3\DLLs;%PATH%"
start "Crawler Platform API" /min ".venv\Scripts\python.exe" -X utf8 platform_main.py serve
start "Crawler Platform Worker" /min ".venv\Scripts\python.exe" -X utf8 platform_main.py worker
start "Crawler Platform Scheduler" /min ".venv\Scripts\python.exe" -X utf8 platform_main.py scheduler
echo 新平台已启动：http://127.0.0.1:8090
pause
