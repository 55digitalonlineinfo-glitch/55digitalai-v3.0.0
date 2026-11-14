@echo off
REM One-command setup for Windows — creates .venv, installs dependencies into it,
REM then runs the wizard.
REM Usage: setup.bat  (double-click, or run from a terminal)
REM
REM NOTE: the slash commands in .claude/commands/ invoke ".venv/bin/python3" with a
REM Unix-style path, so they expect to run under WSL or Git Bash, not cmd.exe/PowerShell
REM directly (Claude Code's Bash tool needs one of those on Windows anyway). This script
REM creates a native Windows .venv (so setup_wizard.py works fine from cmd.exe here), then
REM adds .venv/bin/python3 as a shim pointing back at it — see make_windows_bin_shim.py —
REM so the exact same slash commands that work on Mac also work unchanged from Git Bash/WSL.

cd /d "%~dp0"

if not exist .venv (
    echo Creating .venv...
    python -m venv .venv
    if errorlevel 1 (
        python3 -m venv .venv
    )
)

echo Installing dependencies into .venv...
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\python.exe -m pip install -r requirements.txt

echo Setting up Git Bash / WSL compatibility shims...
.venv\Scripts\python.exe scripts\make_windows_bin_shim.py

echo.
.venv\Scripts\python.exe scripts\setup_wizard.py

pause
