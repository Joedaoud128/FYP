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

echo [1/6] Checking Docker...
docker --version >nul 2>&1
if errorlevel 1 (
    echo [X] Docker not found
    echo     Please install Docker Desktop from: https://www.docker.com/products/docker-desktop
    set HAS_ERROR=1
) else (
    docker ps >nul 2>&1
    if errorlevel 1 (
        echo [X] Docker is installed but not running
        echo     Please start Docker Desktop
        set HAS_ERROR=1
    ) else (
        for /f "tokens=3" %%v in ('docker --version') do echo [OK] Docker running ^(version %%v^)
    )
)

echo.
echo [2/6] Checking Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo [X] Ollama not found
    echo     Please install Ollama from: https://ollama.ai
    set HAS_ERROR=1
) else (
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [X] Ollama installed but not running on port 11434
        echo     Please start Ollama ^(should start automatically on Windows^)
        set HAS_ERROR=1
    ) else (
        echo [OK] Ollama running on localhost:11434
    )
)

echo.
echo [3/6] Checking AI Models...
if !HAS_ERROR! equ 0 (
    set MODELS_FOUND=0
    
    curl -s http://localhost:11434/api/tags | find "qwen2.5-coder:7b" >nul 2>&1
    if errorlevel 1 (
        echo [!] Model qwen2.5-coder:7b not found
        echo     Downloading now ^(5-10 minutes, ~4.7GB^)...
        echo.
        ollama pull qwen2.5-coder:7b
        if errorlevel 1 (
            echo [X] Model download failed
            set HAS_ERROR=1
        ) else (
            echo [OK] Model qwen2.5-coder:7b downloaded successfully
            set /a MODELS_FOUND+=1
        )
    ) else (
        echo [OK] Model qwen2.5-coder:7b found
        set /a MODELS_FOUND+=1
    )
    
    curl -s http://localhost:11434/api/tags | find "qwen3:8b" >nul 2>&1
    if errorlevel 1 (
        echo [!] Model qwen3:8b not found
        echo     Downloading now ^(5-10 minutes, ~5.0GB^)...
        echo.
        ollama pull qwen3:8b
        if errorlevel 1 (
            echo [!] Failed to download qwen3:8b ^(optional model^)
            echo     You can still use qwen2.5-coder:7b
        ) else (
            echo [OK] Model qwen3:8b downloaded successfully
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
echo [4/6] Getting Docker sandbox image...
if !HAS_ERROR! equ 0 (
    docker images mariasabbagh1/esib-ai-agent:latest -q | findstr . >nul 2>&1
    if not errorlevel 1 (
        echo [OK] Docker image already exists locally
    ) else (
        echo     Downloading pre-built image from Docker Hub...
        echo     ^(Faster than building - ~200MB download^)
        docker pull mariasabbagh1/esib-ai-agent:latest
        if errorlevel 1 (
            echo [!] Failed to pull from Docker Hub
            echo     Falling back to local build ^(1-2 minutes^)...
            docker build -t mariasabbagh1/esib-ai-agent:latest -f docker/Dockerfile . --quiet
            if errorlevel 1 (
                echo [X] Docker build failed
                echo     Try: docker build -t mariasabbagh1/esib-ai-agent:latest -f docker/Dockerfile .
                set HAS_ERROR=1
            ) else (
                echo [OK] Docker image built locally
            )
        ) else (
            echo [OK] Docker image downloaded
        )
    )
    
    if !HAS_ERROR! equ 0 (
        docker tag mariasabbagh1/esib-ai-agent:latest agent-sandbox
        echo [OK] Image tagged as 'agent-sandbox'
    )
)

echo.
echo [5/6] Installing Python dependencies...
if !HAS_ERROR! equ 0 (
    pip install -q -r requirements.txt
    if errorlevel 1 (
        echo [X] Failed to install dependencies
        set HAS_ERROR=1
    ) else (
        echo [OK] Python dependencies installed
    )
)

echo.
echo [6/6] Creating necessary directories...
if not exist generated_code mkdir generated_code
if not exist memory_store mkdir memory_store
if not exist logs mkdir logs
echo [OK] Directories created

echo.
echo ===============================================================

if !HAS_ERROR! equ 0 (
    echo.
    echo [OK] Setup Complete! Your system is ready.
    echo.
    echo Next steps:
    echo   1. Test the system:  run.bat check
    echo   2. Run a demo:       run.bat demo
    echo   3. Generate code:    run.bat generate "your prompt here"
    echo.
    echo Or use the direct entry point:
    echo   python ESIB_AiCodingAgent.py --generate "your prompt"
    echo   python ESIB_AiCodingAgent.py --generate "your prompt" --model qwen3:8b
    echo.
) else (
    echo.
    echo [X] Setup incomplete - please fix the errors above
    echo.
    echo Need help? Check docs\TROUBLESHOOTING.md
    exit /b 1
)
