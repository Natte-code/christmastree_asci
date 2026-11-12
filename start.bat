@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 christmas_tree.py %*
) else (
    python christmas_tree.py %*
)
if errorlevel 1 pause
