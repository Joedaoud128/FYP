@echo off
REM ========================================================================
REM  ESIB AI Coding Agent - Virtual Environment Activator
REM  FYP_26_21 | 2026
REM  
REM  This script activates the virtual environment and keeps the prompt open.
REM  After activation, run Python commands directly.
REM ========================================================================

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Check if virtual environment exists
if not exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please run setup.bat first: .\setup.bat
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

echo.
echo ======================================================================
echo   Virtual Environment Activated!
echo ======================================================================
echo.
echo Now you can run:
echo   python ESIB_AiCodingAgent.py --generate "your prompt"
echo   python ESIB_AiCodingAgent.py --fix script.py
echo   python ESIB_AiCodingAgent.py --demo
echo   python ESIB_AiCodingAgent.py --help
echo.
echo Examples:
echo   python ESIB_AiCodingAgent.py --generate "Create a simple calculator"
echo   python ESIB_AiCodingAgent.py --fix demos\03_broken_script.py
echo.
echo ======================================================================
echo.

REM Keep the command prompt open with venv activated
cmd /k