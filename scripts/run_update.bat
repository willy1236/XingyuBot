@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"

set "CURRENT_BRANCH="
for /f %%I in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CURRENT_BRANCH=%%I"

if not defined CURRENT_BRANCH (
	echo [Update Module] Unable to determine current branch
	exit /b 1
)

if /i "%CURRENT_BRANCH%"=="HEAD" (
	echo [Update Module] Detached HEAD state, abort update
	exit /b 1
)

set "HAS_LOCAL_CHANGES="
for /f "delims=" %%I in ('git status --porcelain 2^>nul') do set "HAS_LOCAL_CHANGES=1"

if defined HAS_LOCAL_CHANGES (
	echo [Update Module] Working tree has local changes, abort update
	exit /b 1
)

echo [Update Module] Current branch: %CURRENT_BRANCH%
git fetch origin
if errorlevel 1 exit /b 1

git pull --ff-only origin %CURRENT_BRANCH%
if errorlevel 1 exit /b 1

echo [Update Module] Update successful
echo [Update Module] Close after 3 seconds...
timeout /t 3 /nobreak >nul