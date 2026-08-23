@echo off
REM Pulls the latest code, keeps the virtual environment's dependencies current, and
REM launches AgentOverlay. Safe to double-click or re-run any time -- each step is a
REM no-op if there's nothing new.

cd /d "%~dp0"

git pull
if errorlevel 1 (
    echo.
    echo git pull failed -- check your network connection or run "git status" to see
    echo if you have local changes blocking it.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo Dependency install failed -- see the error above.
    pause
    exit /b 1
)

cd src
python -m agent_overlay
