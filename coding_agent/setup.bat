@echo off
setlocal enabledelayedexpansion

echo.
echo ======================================================================
echo   ESIB AI Coding Agent - Setup
echo   FYP_26_21 ^| USJ Beirut ^| 2026
echo ======================================================================
echo.

set HAS_ERROR=0
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM ========================================================================
REM  STEP 0: Pre-flight checks
REM ========================================================================

echo [Step 0/6] Running pre-flight checks...
echo.

REM Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python not found!
    echo.
    echo     SOLUTION:
    echo     1. Install Python 3.10+ from: https://python.org
    echo     2. During installation, check "Add Python to PATH"
    echo     3. Restart this terminal and run setup.bat again
    echo.
    set HAS_ERROR=1
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [OK] Python %%v found
)

REM Docker installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo [X] Docker not found!
    echo.
    echo     SOLUTION:
    echo     1. Install Docker Desktop: https://www.docker.com/products/docker-desktop
    echo     2. Restart your computer
    echo     3. Start Docker Desktop
    echo     4. Run setup.bat again
    echo.
    set HAS_ERROR=1
) else (
    REM Docker running
    docker ps >nul 2>&1
    if errorlevel 1 (
        echo [X] Docker is installed but not running!
        echo.
        echo     SOLUTION:
        echo     1. Open Docker Desktop from the Start menu
        echo     2. Wait for "Docker Desktop is running"
        echo     3. Run setup.bat again
        echo.
        set HAS_ERROR=1
    ) else (
        for /f "tokens=3" %%v in ('docker --version') do echo [OK] Docker running ^(version %%v^)
    )
)

REM Ollama installed
where ollama >nul 2>&1
if errorlevel 1 (
    echo [X] Ollama not found!
    echo.
    echo     SOLUTION:
    echo     1. Download from: https://ollama.com/download
    echo     2. Run the installer
    echo     3. Ollama starts automatically after install
    echo     4. Run setup.bat again
    echo.
    set HAS_ERROR=1
) else (
    REM Ollama running
    curl.exe -s http://localhost:11434 >nul 2>&1
    if errorlevel 1 (
        echo [X] Ollama installed but not running on port 11434!
        echo.
        echo     SOLUTION:
        echo     1. Open a new CMD window and run: ollama serve
        echo     2. Keep that window open
        echo     3. Run setup.bat again in this window
        echo.
        set HAS_ERROR=1
    ) else (
        echo [OK] Ollama running on localhost:11434
    )
)

REM Disk space check
for /f "tokens=3" %%a in ('dir /-C "%SCRIPT_DIR%" 2^>nul ^| find "bytes free"') do set FREE_BYTES=%%a
if defined FREE_BYTES (
    set FREE_GB=!FREE_BYTES:~0,-9!
    if "!FREE_GB!"=="" set FREE_GB=0
    if !FREE_GB! LSS 8 (
        echo [!] Low disk space: ~!FREE_GB! GB free. Recommended: 8+ GB.
    ) else (
        echo [OK] Disk space: ~!FREE_GB! GB free
    )
)

if !HAS_ERROR! neq 0 (
    echo.
    echo [X] Pre-flight checks failed. Fix the issues above and run setup.bat again.
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] All prerequisites satisfied!
echo.

REM ========================================================================
REM  STEP 1: Virtual environment
REM ========================================================================

echo [Step 1/6] Creating virtual environment...
echo.

if exist ".venv\" (
    echo [!]  Virtual environment already exists -- skipping creation
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo [X] Failed to create virtual environment!
        echo     Check Python installation and available disk space.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created ^(.venv^)
)

echo.

REM ========================================================================
REM  STEP 2: Python dependencies
REM ========================================================================

echo [Step 2/6] Installing Python dependencies...
echo.

call .venv\Scripts\activate.bat

if not exist "requirements.txt" (
    echo [!]  requirements.txt not found -- creating minimal version
    echo pyyaml^>=6.0 > requirements.txt
)

python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

if errorlevel 1 (
    echo [X] Failed to install dependencies!
    echo     Check internet connection, then try:
    echo       python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo [OK] Dependencies installed
echo.

REM ========================================================================
REM  STEP 3: Ollama models
REM ========================================================================

echo [Step 3/6] Setting up AI models...
echo.
echo   Default model : qwen3:8b         (~5.0 GB^)
echo   Optional      : qwen2.5-coder:7b (~4.7 GB extra^)
echo.

REM Always pull the default model
curl.exe -s http://localhost:11434/api/tags | find "qwen3:8b" >nul 2>&1
if not errorlevel 1 (
    echo [OK] qwen3:8b already present
) else (
    echo       Pulling qwen3:8b (~5.0 GB^) -- this may take several minutes...
    ollama pull qwen3:8b
    if errorlevel 1 (
        echo [X] Failed to pull qwen3:8b!
        echo     Check internet connection and disk space (~5 GB^), then try:
        echo       ollama pull qwen3:8b
        pause
        exit /b 1
    )
    echo [OK] qwen3:8b downloaded
)

REM Ask about the fallback model
echo.
echo   Optional: Download qwen2.5-coder:7b ^(~4.7 GB^)?
echo   This is a code-specialised fallback model.
echo   You can always pull it later with:  ollama pull qwen2.5-coder:7b
echo.
set /p PULL_FALLBACK="  Download qwen2.5-coder:7b now? [y/N]: "

if /i "!PULL_FALLBACK!"=="y" (
    curl.exe -s http://localhost:11434/api/tags | find "qwen2.5-coder:7b" >nul 2>&1
    if not errorlevel 1 (
        echo [OK] qwen2.5-coder:7b already present
    ) else (
        echo       Pulling qwen2.5-coder:7b (~4.7 GB^)...
        ollama pull qwen2.5-coder:7b
        if errorlevel 1 (
            echo [!]  Failed to pull qwen2.5-coder:7b
            echo      Pull it later with:  ollama pull qwen2.5-coder:7b
        ) else (
            echo [OK] qwen2.5-coder:7b downloaded
        )
    )
) else (
    echo       Skipping qwen2.5-coder:7b.
    echo       Pull later with:  ollama pull qwen2.5-coder:7b
)

echo.

REM ========================================================================
REM  STEP 4: Docker sandbox image
REM ========================================================================

echo [Step 4/6] Building Docker sandbox image...
echo.

if not exist "docker\Dockerfile" (
    echo [X] Dockerfile not found at docker\Dockerfile!
    echo     Make sure you are running setup.bat from the project root ^(coding_agent/^).
    pause
    exit /b 1
)

docker images agent-sandbox -q | findstr . >nul 2>&1
if not errorlevel 1 (
    echo [OK] Docker image 'agent-sandbox' already exists
) else (
    echo       Building agent-sandbox image ^(first time may take ~1-2 min^)...
    docker build -t agent-sandbox -f docker\Dockerfile . --quiet
    if errorlevel 1 (
        echo       Retrying with verbose output...
        docker build -t agent-sandbox -f docker\Dockerfile .
        if errorlevel 1 (
            echo [X] Docker build failed!
            echo     Try:  docker system prune -a  then run setup.bat again.
            pause
            exit /b 1
        )
    )
    echo [OK] Docker image built successfully
)

echo.

REM ========================================================================
REM  STEP 5: Directories
REM ========================================================================

echo [Step 5/6] Creating required directories...
echo.

if not exist "logs"                          mkdir logs
if not exist "demos"                         mkdir demos
if not exist "src\generation\generated_code" mkdir src\generation\generated_code
if not exist "memory_store"                  mkdir memory_store
if not exist "docs"                          mkdir docs

echo [OK] Directories ready
echo.

REM ========================================================================
REM  STEP 6: Verification
REM ========================================================================

echo [Step 6/6] Running system verification...
echo.

if exist "pre_check.py" (
    python pre_check.py
    echo.
) else (
    echo [!]  pre_check.py not found -- skipping verification
    echo.
)

REM ========================================================================
REM  Done
REM ========================================================================

echo ======================================================================
echo   SETUP COMPLETE!
echo ======================================================================
echo.
echo   Next steps:
echo.
echo   1. Activate the virtual environment:
echo        run.bat
echo.
echo   2. Then generate code:
echo        python ESIB_AiCodingAgent.py --generate "Create a simple calculator"
echo.
echo   3. Or debug a script:
echo        python ESIB_AiCodingAgent.py --fix demos\03_broken_script.py
echo.
echo   4. Or run the demo:
echo        python ESIB_AiCodingAgent.py --demo
echo.
echo   For help:  python ESIB_AiCodingAgent.py --help
echo   For issues: see TROUBLESHOOTING.md
echo.
echo ======================================================================
echo.
pause