@echo off
setlocal

:: Create virtual environment if it doesn't exist
if not exist ".venv\Scripts\activate.bat" (
    echo Setting up virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Python not found. Install it from https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

:: Install / update dependencies
echo Checking dependencies...
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt

:: Check credentials file exists
if not exist "credentials.json" (
    echo.
    echo ERROR: credentials.json not found.
    echo See README.md for instructions on how to get it.
    echo.
    pause
    exit /b 1
)

:: Launch app
echo Starting Clemailer...
python app.py

pause
