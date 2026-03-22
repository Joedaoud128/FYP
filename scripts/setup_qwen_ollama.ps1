$ErrorActionPreference = 'Stop'

Write-Host "Checking ollama installation..."
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "Ollama is not installed. Install from https://ollama.com/download/windows"
    exit 1
}

Write-Host "Pulling model qwen3.5:0.8b-instruct-q4_K_M..."
ollama pull qwen3.5:0.8b-instruct-q4_K_M
if ($LASTEXITCODE -ne 0) {
    Write-Host "Model pull failed. Verify model tag availability and network access."
    exit $LASTEXITCODE
}

Write-Host "Model setup complete."
