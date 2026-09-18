@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 项目运行环境不存在，请先安装依赖。
  pause
  exit /b 1
)
set "PATH=C:\ProgramData\Anaconda3\Library\bin;C:\ProgramData\Anaconda3\DLLs;%PATH%"
echo 正在启动情报采集控制台...
echo 浏览器地址：http://127.0.0.1:8080
".venv\Scripts\python.exe" -X utf8 main.py --panel
pause
