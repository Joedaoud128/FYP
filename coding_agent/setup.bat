@echo off
setlocal enabledelayedexpansion

echo ===============================================================
echo.
echo          ESIB AI Coding Agent - Setup and Validation
echo               FYP 26/21 - USJ Beirut
echo.
echo ===============================================================
echo.

set HAS_ERROR=0
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo [1/8] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python not found
    echo     Please install Python 3.8 or higher from https://python.org
    echo     Make sure to check "Add Python to PATH" during installation
    set HAS_ERROR=1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [OK] Python %%v found
)

echo.
echo [2/8] Checking Docker...
docker --version >nul 2>&1
if errorlevel 1 (
    echo [X] Docker not found
    echo     Please install Docker Desktop from: https://www.docker.com/products/docker-desktop
    echo     Windows 10/11 Pro, Enterprise, or Education required
    set HAS_ERROR=1
) else (
    docker ps >nul 2>&1
    if errorlevel 1 (
        echo [X] Docker is installed but not running
        echo     Please start Docker Desktop from the Start menu
        echo     Wait for "Docker Desktop is running" message
        set HAS_ERROR=1
    ) else (
        for /f "tokens=3" %%v in ('docker --version') do echo [OK] Docker running ^(version %%v^)
    )
)

echo.
echo [3/8] Checking Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo [X] Ollama not found
    echo     Please install Ollama from: https://ollama.com/download
    set HAS_ERROR=1
) else (
    curl.exe -s http://localhost:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [X] Ollama installed but not running on port 11434
        echo     Please start Ollama from the Start menu
        echo     Or run: ollama serve
        set HAS_ERROR=1
    ) else (
        echo [OK] Ollama running on localhost:11434
    )
)

echo.
echo [4/8] Checking Disk Space...
for /f "tokens=3" %%a in ('dir /-C C:\ 2^>nul ^| find "bytes free"') do set FREE_SPACE=%%a
set FREE_SPACE_GB=!FREE_SPACE:~0,-3!
if !FREE_SPACE_GB! LSS 10 (
    echo [WARN] Low disk space: !FREE_SPACE_GB! GB free
    echo     Recommended: 10+ GB free for models and logs
) else (
    echo [OK] Disk space: !FREE_SPACE_GB! GB free
)

echo.
echo [5/8] Creating Virtual Environment...
if exist ".venv\" (
    echo [OK] Virtual environment already exists
) else (
    echo     Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [X] Failed to create virtual environment
        set HAS_ERROR=1
    ) else (
        echo [OK] Virtual environment created
    )
)

echo.
echo [6/8] Installing Python dependencies...
if !HAS_ERROR! equ 0 (
    echo     Activating virtual environment...
    call .venv\Scripts\activate.bat
    
    echo     Upgrading pip...
    python -m pip install --upgrade pip >nul 2>&1
    
    echo     Installing requirements from requirements.txt...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [X] Failed to install dependencies
        echo     Trying with --no-cache-dir...
        pip install --no-cache-dir -r requirements.txt
        if errorlevel 1 (
            set HAS_ERROR=1
        ) else (
            echo [OK] Dependencies installed with --no-cache-dir
        )
    ) else (
        echo [OK] Dependencies installed successfully
    )
)

echo.
echo [7/8] Checking AI Models...
if !HAS_ERROR! equ 0 (
    set MODELS_FOUND=0
    
    echo     Checking for qwen2.5-coder:7b...
    curl.exe -s http://localhost:11434/api/tags | find "qwen2.5-coder:7b" >nul 2>&1
    if errorlevel 1 (
        echo [!] Model qwen2.5-coder:7b not found
        echo     Downloading now ^(5-10 minutes, ~4.7GB^)...
        echo     This may fail on slow connections - retrying up to 3 times...
        echo.
        set RETRY_COUNT=0
        :retry_model1
        ollama pull qwen2.5-coder:7b
        if errorlevel 1 (
            set /a RETRY_COUNT+=1
            if !RETRY_COUNT! LSS 3 (
                echo     Retry !RETRY_COUNT!/3 in 10 seconds...
                timeout /t 10 /nobreak >nul
                goto retry_model1
            ) else (
                echo [X] Failed to download qwen2.5-coder:7b after 3 attempts
                set HAS_ERROR=1
            )
        ) else (
            echo [OK] Model qwen2.5-coder:7b downloaded
            set /a MODELS_FOUND+=1
        )
    ) else (
        echo [OK] Model qwen2.5-coder:7b found
        set /a MODELS_FOUND+=1
    )
    
    echo     Checking for qwen3:8b...
    curl.exe -s http://localhost:11434/api/tags | find "qwen3:8b" >nul 2>&1
    if errorlevel 1 (
        echo [!] Model qwen3:8b not found ^(optional^)
        echo     Downloading now ^(5-10 minutes, ~5.0GB^)...
        echo     This may fail on slow connections - retrying up to 3 times...
        echo.
        set RETRY_COUNT=0
        :retry_model2
        ollama pull qwen3:8b
        if errorlevel 1 (
            set /a RETRY_COUNT+=1
            if !RETRY_COUNT! LSS 3 (
                echo     Retry !RETRY_COUNT!/3 in 10 seconds...
                timeout /t 10 /nobreak >nul
                goto retry_model2
            ) else (
                echo [!] Failed to download qwen3:8b ^(optional model^)
                echo     You can still use qwen2.5-coder:7b
            )
        ) else (
            echo [OK] Model qwen3:8b downloaded
            set /a MODELS_FOUND+=1
        )
    ) else (
        echo [OK] Model qwen3:8b found
        set /a MODELS_FOUND+=1
    )
    
    if !MODELS_FOUND! equ 0 (
        echo [X] No models available
        set HAS_ERROR=1
    ) else if !MODELS_FOUND! equ 1 (
        echo [!] Only one model available ^(limited model selection^)
    ) else (
        echo [OK] Both models available
    )
)

echo.
echo [8/8] Setting up Docker sandbox image...
if !HAS_ERROR! equ 0 (
    REM Check if image already exists locally
    docker images agent-sandbox -q | findstr . >nul 2>&1
    if not errorlevel 1 (
        echo [OK] Docker image already exists
    ) else (
        REM Try to pull from Docker Hub first
        echo     Attempting to pull pre-built image from Docker Hub...
        echo     ^(Faster - ~200MB download^)
        docker pull mariasabbagh1/esib-ai-agent:latest
        if errorlevel 1 (
            echo [!] Failed to pull from Docker Hub
            echo     Falling back to local build ^(1-2 minutes^)...
            docker build -t agent-sandbox -f docker\Dockerfile . --quiet
            if errorlevel 1 (
                echo [X] Docker build failed
                echo     Trying with verbose output...
                docker build -t agent-sandbox -f docker\Dockerfile .
                if errorlevel 1 (
                    set HAS_ERROR=1
                ) else (
                    echo [OK] Docker image built with verbose output
                )
            ) else (
                echo [OK] Docker image built locally
            )
        ) else (
            REM Tag the pulled image as agent-sandbox for local use
            docker tag mariasabbagh1/esib-ai-agent:latest agent-sandbox
            echo [OK] Docker image pulled from Docker Hub and tagged
        )
    )
)

echo.
echo ===============================================================

if !HAS_ERROR! equ 0 (
    echo.
    echo [OK] Setup Complete! Your system is ready.
    echo.
    echo Next steps:
    echo   1. Activate the virtual environment:
    echo        .venv\Scripts\activate
    echo.
    echo   2. Test the system:  run.bat check
    echo   3. Run a demo:       run.bat demo
    echo   4. Generate code:    run.bat generate "your prompt here"
    echo.
    echo Or use the direct entry point:
    echo   python ESIB_AiCodingAgent.py --generate "your prompt"
    echo.
) else (
    echo.
    echo [X] Setup incomplete - please fix the errors above
    echo.
    echo Troubleshooting:
    echo   - Ensure Docker Desktop is running
    echo   - Ensure Ollama is running (check system tray)
    echo   - Check internet connection for model downloads
    echo   - See TROUBLESHOOTING.md for more help
    pause
    exit /b 1
)