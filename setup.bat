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

REM Python — must be 3.10 or higher
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python not found!
    echo.
    echo     SOLUTION:
    echo     1. Install Python 3.10+ from: https://python.org/downloads
    echo     2. During installation, check "Add Python to PATH"
    echo     3. Restart this terminal and run setup.bat again
    echo.
    set HAS_ERROR=1
) else (
    REM Extract version string e.g. "3.9.7"
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v

    REM Extract major and minor version numbers
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        set PY_MAJOR=%%a
        set PY_MINOR=%%b
    )

    REM Check major == 3 and minor >= 10
    if !PY_MAJOR! neq 3 (
        echo [X] Python !PY_VER! found but Python 3.10+ is required!
        echo.
        echo     SOLUTION:
        echo     1. Install Python 3.10+ from: https://python.org/downloads
        echo     2. During installation, check "Add Python to PATH"
        echo     3. Restart this terminal and run setup.bat again
        echo.
        set HAS_ERROR=1
    ) else if !PY_MINOR! LSS 10 (
        echo [X] Python !PY_VER! found but Python 3.10+ is required!
        echo.
        echo     The project uses Python 3.10 type-hint syntax ^(str ^| None^)
        echo     which is not supported in older versions.
        echo.
        echo     SOLUTION:
        echo     1. Install Python 3.10+ from: https://python.org/downloads
        echo     2. During installation, check "Add Python to PATH"
        echo     3. Restart this terminal and run setup.bat again
        echo.
        set HAS_ERROR=1
    ) else (
        echo [OK] Python !PY_VER! found
    )
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

REM Detect which models are already present
set HAS_QWEN3=0
set HAS_CODER=0

ollama list 2>nul | find "qwen3:8b" >nul 2>&1
if not errorlevel 1 set HAS_QWEN3=1

ollama list 2>nul | find "qwen2.5-coder:7b" >nul 2>&1
if not errorlevel 1 set HAS_CODER=1

REM ---- Both already present -----------------------------------------------
if !HAS_QWEN3!==1 if !HAS_CODER!==1 (
    echo [OK] qwen3:8b already present
    echo [OK] qwen2.5-coder:7b already present
    goto :models_done
)

REM ---- Only qwen3:8b is present — ask about the coder model ---------------
if !HAS_QWEN3!==1 if !HAS_CODER!==0 (
    echo [OK] qwen3:8b already present
    echo.
    echo   Optional: Download qwen2.5-coder:7b ^(~4.7 GB^)?
    echo   This is a code-specialised companion model.
    echo   You can always pull it later with:  ollama pull qwen2.5-coder:7b
    echo.
    set /p PULL_CODER="  Download qwen2.5-coder:7b now? [y/N]: "
    if /i "!PULL_CODER!"=="y" (
        echo       Pulling qwen2.5-coder:7b ~(4.7 GB^)...
        ollama pull qwen2.5-coder:7b
        if errorlevel 1 (
            echo [!]  Failed to pull qwen2.5-coder:7b
            echo      Pull it later with:  ollama pull qwen2.5-coder:7b
        ) else (
            echo [OK] qwen2.5-coder:7b downloaded
        )
    ) else (
        echo       Skipping qwen2.5-coder:7b.
        echo       Pull later with:  ollama pull qwen2.5-coder:7b
    )
    goto :models_done
)

REM ---- Only qwen2.5-coder is present — ask about qwen3 -------------------
if !HAS_QWEN3!==0 if !HAS_CODER!==1 (
    echo [OK] qwen2.5-coder:7b already present
    echo.
    echo   Optional: Download qwen3:8b ^(~5.0 GB^)?
    echo   This is the default/recommended model for this agent.
    echo   You can always pull it later with:  ollama pull qwen3:8b
    echo.
    set /p PULL_QWEN3="  Download qwen3:8b now? [y/N]: "
    if /i "!PULL_QWEN3!"=="y" (
        echo       Pulling qwen3:8b ^(~5.0 GB^)...
        ollama pull qwen3:8b
        if errorlevel 1 (
            echo [!]  Failed to pull qwen3:8b
            echo      Pull it later with:  ollama pull qwen3:8b
        ) else (
            echo [OK] qwen3:8b downloaded
        )
    ) else (
        echo       Skipping qwen3:8b.
        echo       To use the agent you will need to pass:  --model qwen2.5-coder:7b
        echo       Pull qwen3:8b later with:  ollama pull qwen3:8b
    )
    goto :models_done
)

REM ---- Neither model present — pull qwen3 first, then ask about coder ----
echo       No models found. Pulling qwen3:8b ^(~5.0 GB^) -- this may take several minutes...
ollama pull qwen3:8b
if errorlevel 1 (
    echo [X] Failed to pull qwen3:8b!
    echo     Check internet connection and disk space ^(~5 GB^), then try:
    echo       ollama pull qwen3:8b
    pause
    exit /b 1
)
echo [OK] qwen3:8b downloaded
echo.
echo   Optional: Also download qwen2.5-coder:7b ^(~4.7 GB^)?
echo   This is a code-specialised companion model.
echo   You can always pull it later with:  ollama pull qwen2.5-coder:7b
echo.
set /p PULL_CODER2="  Download qwen2.5-coder:7b now? [y/N]: "
if /i "!PULL_CODER2!"=="y" (
    echo       Pulling qwen2.5-coder:7b ^(~4.7 GB^)...
    ollama pull qwen2.5-coder:7b
    if errorlevel 1 (
        echo [!]  Failed to pull qwen2.5-coder:7b
        echo      Pull it later with:  ollama pull qwen2.5-coder:7b
    ) else (
        echo [OK] qwen2.5-coder:7b downloaded
    )
) else (
    echo       Skipping qwen2.5-coder:7b.
    echo       Pull later with:  ollama pull qwen2.5-coder:7b
)

:models_done

echo.

REM ========================================================================
REM  STEP 4: Docker sandbox image (Pull from Hub with fallback to build)
REM ========================================================================

echo [Step 4/6] Setting up Docker sandbox image...
echo.

if not exist "docker\Dockerfile" (
    echo [X] Dockerfile not found at docker\Dockerfile!
    echo     Make sure you are running setup.bat from the project root ^(FYP/^).
    pause
    exit /b 1
)

REM Check if image already exists locally
docker images agent-sandbox -q | findstr . >nul 2>&1
if not errorlevel 1 (
    echo [OK] Docker image 'agent-sandbox' already exists locally
    goto :docker_done
)

REM Try to pull from Docker Hub first (faster, ~30 seconds)
echo       Attempting to pull from Docker Hub: mariasabbagh1/esib-ai-agent:latest
echo       This is faster than building locally (~30 seconds vs 2 minutes)
echo.
docker pull mariasabbagh1/esib-ai-agent:latest
if not errorlevel 1 (
    echo [OK] Docker image pulled successfully from Docker Hub
    REM Tag the pulled image as agent-sandbox for local compatibility
    docker tag mariasabbagh1/esib-ai-agent:latest agent-sandbox
    if errorlevel 1 (
        echo [!]  Warning: Failed to tag image as agent-sandbox
        echo      The image is available as mariasabbagh1/esib-ai-agent:latest
    ) else (
        echo [OK] Image tagged as agent-sandbox
    )
    goto :docker_done
)

REM If pull fails, fall back to local build
echo.
echo [!]  Failed to pull from Docker Hub. Falling back to local build...
echo       Building agent-sandbox image ^(this may take ~1-2 minutes^)...
echo.
docker build -t agent-sandbox -f docker\Dockerfile . --quiet
if errorlevel 1 (
    echo       Retrying with verbose output...
    docker build -t agent-sandbox -f docker\Dockerfile .
    if errorlevel 1 (
        echo [X] Docker build failed!
        echo     Possible solutions:
        echo     1. Check your internet connection (for pull attempt)
        echo     2. Run: docker system prune -a
        echo     3. Try setup.bat again
        echo.
        echo     Or pull manually later:
        echo       docker pull mariasabbagh1/esib-ai-agent:latest
        echo       docker tag mariasabbagh1/esib-ai-agent:latest agent-sandbox
        pause
        exit /b 1
    )
)
echo [OK] Docker image built successfully (local fallback)

:docker_done

echo.

REM ========================================================================
REM  STEP 5: Directories
REM ========================================================================

echo [Step 5/6] Creating required directories...
echo.

if not exist "logs"                                mkdir logs
if not exist "demos"                               mkdir demos
if not exist "src\generation\generated_code"       mkdir src\generation\generated_code
if not exist "src\orchestrator\memory_store"       mkdir src\orchestrator\memory_store
if not exist "docs"                                mkdir docs

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
REM  Done — launch run.bat to keep venv active
REM ========================================================================

echo ======================================================================
echo   SETUP COMPLETE!
echo ======================================================================
echo.
echo   Launching virtual environment shell...
echo.
echo   Once inside, you can run:
echo     python ESIB_AiCodingAgent.py --generate "Create a simple calculator"
echo     python ESIB_AiCodingAgent.py --fix demos\03_broken_script.py
echo     python ESIB_AiCodingAgent.py --demo
echo     python ESIB_AiCodingAgent.py --help
echo.
echo   For issues: see TROUBLESHOOTING.md
echo.
echo ======================================================================
echo.

REM Launch run.bat so the user lands in an activated shell automatically.
call "%SCRIPT_DIR%run.bat"