@echo off
setlocal

:: Find a working Python (tries py launcher, then python, then common conda paths)
set PYTHON=

where py >nul 2>&1 && py -c "import sys" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%i in ('py -c "import sys; print(sys.executable)"') do set PYTHON=%%i
    goto :found
)

where python >nul 2>&1 && python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)"') do set PYTHON=%%i
    goto :found
)

for %%p in (
    "%USERPROFILE%\miniconda3\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) do (
    if exist %%p (
        set PYTHON=%%~p
        goto :found
    )
)

echo ERROR: Python not found. Install it from https://www.python.org/downloads/
echo        and check "Add Python to PATH" during installation.
pause
exit /b 1

:found
echo Using Python: %PYTHON%

:: Install / update dependencies
echo Checking dependencies...
"%PYTHON%" -m pip install -q -r requirements.txt

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
"%PYTHON%" app.py

pause
