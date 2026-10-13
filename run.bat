@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3.13 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON=py -3.13"
    )
)

if not defined PYTHON (
    py -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON=py"
    )
)

if not defined PYTHON (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found. Install Python 3 and try again.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

%PYTHON% -c "import PySide6, kociemba" >nul 2>nul
if errorlevel 1 (
    echo Required packages are missing. Install them with:
    echo %PYTHON% -m pip install -r requirements.txt
    pause
    exit /b 1
)

%PYTHON% gui_3d.py
if errorlevel 1 pause
