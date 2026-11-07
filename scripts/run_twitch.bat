@echo off
chcp 65001

:: Twitch bot 的啟動腳本；git 更新由 run_main.bat 負責，這裡只做 uv sync
cd /d "%~dp0"
uv sync
if errorlevel 1 exit /b 1

cd ..
set APP_ENV=production
set PYTHONWARNINGS=ignore::DeprecationWarning
uv run python -W ignore -m twitch_main