@echo off
echo YouTube Downloader Launcher

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH. Please install Python to run this application.
    pause
    exit /b 1
)

REM Check if virtual environment exists, create if not
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Create downloads directory if it doesn't exist
if not exist downloads (
    echo Creating downloads directory...
    mkdir downloads
)

REM Run the application
echo Starting YouTube Downloader...
python app.py

REM Deactivate virtual environment on exit
call venv\Scripts\deactivate.bat

pause 