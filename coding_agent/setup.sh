@echo off
REM ========================================================================
REM  ESIB AI Coding Agent - Automated Setup Script (Windows)
REM  FYP_26_21 | 2026
REM ========================================================================

setlocal enabledelayedexpansion

echo ======================================================================
echo   ESIB AI Coding Agent - Setup
echo ======================================================================
echo.

REM ========================================================================
REM  STEP 0: Pre-flight Checks
REM ========================================================================

echo [Step 0/6] Running pre-flight checks...
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python not found!
    echo.
    echo SOLUTION:
    echo 1. Install Python 3.8 or higher from: https://python.org
    echo 2. During installation, check "Add Python to PATH"
    echo 3. Restart your terminal and run setup.bat again
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% found

REM Check Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo [X] Docker not found!
    echo.
    echo SOLUTION:
    echo 1. Install Docker Desktop from: https://docker.com/products/docker-desktop
    echo 2. Install and restart your computer
    echo 3. Start Docker Desktop
    echo 4. Run setup.bat again
    echo.
    echo Need help? See docs\TROUBLESHOOTING.md
    echo.
    pause
    exit /b 1
)
echo [OK] Docker installed

REM Check if Docker is running
docker ps >nul 2>&1
if errorlevel 1 (
    echo [X] Docker is not running!
    echo.
    echo SOLUTION:
    echo 1. Start Docker Desktop from the Start menu
    echo 2. Wait for "Docker Desktop is running" message
    echo 3. Run setup.bat again
    echo.
    echo Need help? See docs\TROUBLESHOOTING.md
    echo.
    pause
    exit /b 1
)
echo [OK] Docker is running

REM Check Ollama
where ollama >nul 2>&1
if errorlevel 1 (
    echo [X] Ollama not found!
    echo.
    echo SOLUTION:
    echo 1. Download Ollama from: https://ollama.com/download
    echo 2. Run the installer
    echo 3. Ollama will start automatically
    echo 4. Run setup.bat again
    echo.
    echo Need help? See docs\TROUBLESHOOTING.md
    echo.
    pause
    exit /b 1
)
echo [OK] Ollama installed

REM Check if Ollama is running
curl.exe -s http://localhost:11434 >nul 2>&1
if errorlevel 1 (
    echo [X] Ollama is not running on port 11434!
    echo.
    echo SOLUTION:
    echo 1. Open a new terminal window
    echo 2. Run: ollama serve
    echo 3. Keep that window open
    echo 4. Run setup.bat again in this window
    echo.
    echo Need help? See docs\TROUBLESHOOTING.md
    echo.
    pause
    exit /b 1
)
echo [OK] Ollama is running on port 11434

echo.
echo [OK] All prerequisites satisfied!
echo.

REM ========================================================================
REM  STEP 1: Create Virtual Environment
REM ========================================================================

echo [Step 1/6] Creating virtual environment...
echo.

if exist ".venv" (
    echo [!] Virtual environment already exists, skipping creation
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo [X] Failed to create virtual environment!
        echo.
        echo SOLUTION:
        echo 1. Ensure you have sufficient disk space
        echo 2. Check Python installation
        echo 3. Try: python -m pip install --upgrade pip
        echo.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

echo.

REM ========================================================================
REM  STEP 2: Install Dependencies
REM ========================================================================

echo [Step 2/6] Installing Python dependencies...
echo.

call .venv\Scripts\activate.bat

if not exist "requirements.txt" (
    echo [!] requirements.txt not found, creating minimal version...
    echo pyyaml^>=6.0 > requirements.txt
)

python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

if errorlevel 1 (
    echo [X] Failed to install dependencies!
    echo.
    echo SOLUTION:
    echo 1. Check your internet connection
    echo 2. Try: python -m pip install --upgrade pip
    echo 3. Try: python -m pip install -r requirements.txt
    echo.
    echo Need help? See docs\TROUBLESHOOTING.md
    echo.
    pause
    exit /b 1
)

echo [OK] Dependencies installed

echo.

REM ========================================================================
REM  STEP 3: Pull Ollama Models
REM ========================================================================

echo [Step 3/6] Pulling Ollama models (this may take a while)...
echo.

echo [!] Pulling primary model: qwen3:8b (~4.7GB download)...
ollama pull qwen3:8b
if errorlevel 1 (
    echo [X] Failed to pull qwen3:8b!
    echo.
    echo SOLUTION:
    echo 1. Check your internet connection
    echo 2. Ensure sufficient disk space (~5GB)
    echo 3. Try manually: ollama pull qwen3:8b
    echo.
    echo Continuing with fallback model...
    echo.
)

echo.
echo [!] Pulling fallback model: qwen2.5-coder:7b (~4.7GB download)...
ollama pull qwen2.5-coder:7b
if errorlevel 1 (
    echo [X] Failed to pull qwen2.5-coder:7b!
    echo.
    echo SOLUTION:
    echo 1. Check your internet connection
    echo 2. Ensure sufficient disk space (~5GB)
    echo 3. Try manually: ollama pull qwen2.5-coder:7b
    echo.
    echo Need help? See docs\TROUBLESHOOTING.md
    echo.
    pause
    exit /b 1
)

echo [OK] Models pulled successfully

echo.

REM ========================================================================
REM  STEP 4: Build Docker Image
REM ========================================================================

echo [Step 4/6] Building Docker sandbox image...
echo.

if not exist "docker\Dockerfile" (
    echo [X] Dockerfile not found at docker\Dockerfile!
    echo.
    echo SOLUTION:
    echo 1. Ensure you're in the correct directory (coding_agent/)
    echo 2. Check that docker\Dockerfile exists
    echo 3. Re-download the project if needed
    echo.
    pause
    exit /b 1
)

docker build -t agent-sandbox -f docker\Dockerfile .
if errorlevel 1 (
    echo [X] Failed to build Docker image!
    echo.
    echo SOLUTION:
    echo 1. Check Docker is running
    echo 2. Try: docker system prune -a
    echo 3. Try build again: docker build -t agent-sandbox -f docker\Dockerfile .
    echo.
    echo Need help? See docs\TROUBLESHOOTING.md
    echo.
    pause
    exit /b 1
)

echo [OK] Docker image built successfully

echo.

REM ========================================================================
REM  STEP 5: Create Required Directories
REM ========================================================================

echo [Step 5/6] Creating required directories...
echo.

if not exist "logs" mkdir logs
if not exist "demos" mkdir demos

REM Create directories within src folders (not at root)
if not exist "src\generation\generated_code" mkdir src\generation\generated_code
if not exist "src\orchestrator\memory_store" mkdir src\orchestrator\memory_store
if not exist "docs" mkdir docs

echo [OK] Directories created

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
    echo [!] pre_check.py not found, skipping verification
    echo.
)

REM ========================================================================
REM  Setup Complete
REM ========================================================================

echo ======================================================================
echo   SETUP COMPLETE!
echo ======================================================================
echo.
echo Next steps:
echo.
echo 1. Test generation mode:
echo    python ESIB_AiCodingAgent.py --generate "Create a simple calculator"
echo.
echo 2. Test debug mode:
echo    python ESIB_AiCodingAgent.py --fix demos\03_broken_script.py
echo.
echo 3. Use convenience wrapper:
echo    .\run.bat generate "Create a web scraper"
echo    .\run.bat fix script.py
echo.
echo For help:
echo    python ESIB_AiCodingAgent.py --help
echo    See docs\TROUBLESHOOTING.md for common issues
echo.
echo ======================================================================

pause