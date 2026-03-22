Understood. Let’s do this your way: use your folder and try GPU, with zero ambiguity.

## 1) Hard reset all Ollama processes
Run in PowerShell:
```powershell
taskkill /IM ollama.exe /F
```

## 2) Point Ollama to your folder (current session)
```powershell
$env:OLLAMA_MODELS="C:\Users\raymo\OneDrive\Desktop\UNIVERSITY\year 5\Sem 2\FYP\phase4\models"
$env:OLLAMA_VULKAN="1"
$env:OLLAMA_DEBUG="INFO"
```

## 3) Verify the folder actually has usable manifests
```powershell
Test-Path "$env:OLLAMA_MODELS\manifests"
(Get-ChildItem "$env:OLLAMA_MODELS\manifests" -Recurse -File | Measure-Object).Count
```

- If count is `0`: that folder has blobs only (or no valid manifests), and `ollama list` will stay empty.
- If count is `>0`: Ollama should be able to list models from that folder.

## 4) Start Ollama server in this same terminal
```powershell
ollama serve
```

Keep it open.

## 5) In a second PowerShell, set same env vars again
```powershell
$env:OLLAMA_MODELS="C:\Users\raymo\OneDrive\Desktop\UNIVERSITY\year 5\Sem 2\FYP\phase4\models"
$env:OLLAMA_HOST="127.0.0.1:11434"
ollama list
```

## 6) If list is still empty, populate that exact folder
```powershell
$env:OLLAMA_MODELS="C:\Users\raymo\OneDrive\Desktop\UNIVERSITY\year 5\Sem 2\FYP\phase4\models"
ollama pull qwen2.5-coder:7b
ollama list
```

This guarantees the manifests are created in that folder.

## 7) Run the model
```powershell
ollama run qwen2.5-coder:7b
```

## 8) Check GPU vs CPU
```powershell
ollama ps
```
Also inspect `ollama serve` logs for device detection.

---

Blunt truth:
- If `ollama list` is empty after Step 3 shows no manifests, your folder is not a complete runnable Ollama model registry.
- If `ollama ps` still shows CPU after `OLLAMA_VULKAN=1`, your Radeon/driver/backend combo is not being accepted by Ollama on Windows right now. The model can still run, but on CPU.