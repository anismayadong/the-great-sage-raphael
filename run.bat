@echo off
chcp 65001 >nul
title Great Sage Raphael
echo ===================================================
echo   Great Sage Raphael - Desktop Voice Assistant
echo ===================================================
echo.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
call .\venv\Scripts\activate.bat
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Error] Program exited with error code %ERRORLEVEL%
    pause
)
