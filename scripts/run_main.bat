@echo off
chcp 65001

:: 強制切換到腳本所在的目錄 (C:\google drive\github\XingyuBot\scripts)
cd /d "%~dp0"

:: 執行更新與同步
call "%~dp0\run_update.bat"
if errorlevel 1 exit /b 1
uv sync
if errorlevel 1 exit /b 1

:: 切換回專案根目錄執行主程式
cd ..
set APP_ENV=production
set PYTHONWARNINGS=ignore::DeprecationWarning
uv run python -W ignore -m main