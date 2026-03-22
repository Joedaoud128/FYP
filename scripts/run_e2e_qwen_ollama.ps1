$ErrorActionPreference = 'Stop'

Write-Host "Running optional real-model E2E demo..."
py -3 demo/e2e_qwen_ollama_demo.py
exit $LASTEXITCODE
