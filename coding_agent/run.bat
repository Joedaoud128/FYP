@echo off
REM ========================================================================
REM  ESIB AI Coding Agent - Windows Convenience Wrapper
REM  FYP_26_21 | 2026
REM ========================================================================

setlocal enabledelayedexpansion

REM Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please run setup.bat first:
    echo     .\setup.bat
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Parse command line arguments
set "COMMAND=%~1"

if "%COMMAND%"=="" (
    echo Usage: run.bat [command] [options]
    echo.
    echo Commands:
    echo   generate "prompt"     - Generate code from natural language
    echo   fix script.py         - Debug and fix a broken script
    echo   check                 - Run system health check
    echo   help                  - Show detailed help
    echo.
    echo Examples:
    echo   run.bat generate "Create a web scraper"
    echo   run.bat fix demos\03_broken_script.py
    echo   run.bat check
    echo.
    goto :eof
)

if /i "%COMMAND%"=="generate" (
    if "%~2"=="" (
        echo [ERROR] Please provide a prompt for code generation.
        echo Example: run.bat generate "Create a calculator"
        exit /b 1
    )
    echo.
    echo ======================================================================
    echo   GENERATION MODE
    echo ======================================================================
    echo.
    python ESIB_AiCodingAgent.py --generate %2 %3 %4 %5 %6 %7 %8 %9
    goto :eof
)

if /i "%COMMAND%"=="fix" (
    if "%~2"=="" (
        echo [ERROR] Please provide a script path to debug.
        echo Example: run.bat fix demos\03_broken_script.py
        exit /b 1
    )
    echo.
    echo ======================================================================
    echo   DEBUG MODE
    echo ======================================================================
    echo.
    python ESIB_AiCodingAgent.py --fix %2 %3 %4 %5 %6 %7 %8 %9
    goto :eof
)

if /i "%COMMAND%"=="check" (
    echo.
    echo ======================================================================
    echo   SYSTEM HEALTH CHECK
    echo ======================================================================
    echo.
    python pre_check.py
    goto :eof
)

if /i "%COMMAND%"=="help" (
    echo.
    echo ======================================================================
    echo   ESIB AI CODING AGENT - HELP
    echo ======================================================================
    echo.
    python ESIB_AiCodingAgent.py --help
    goto :eof
)

REM Unknown command - pass through to main script
python ESIB_AiCodingAgent.py %*
