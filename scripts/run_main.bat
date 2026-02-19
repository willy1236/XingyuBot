@echo off
chcp 65001

:: 強制切換到腳本所在的目錄 (C:\google drive\github\XingyuBot\scripts)
cd /d "%~dp0"

:: 執行更新與同步
uv run python update.py
uv sync

:: 切換回專案根目錄執行主程式
cd ..
uv run python main.py