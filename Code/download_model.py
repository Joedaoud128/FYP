"""
Download Qwen2.5-Coder-7B-Instruct from Hugging Face Hub.

Quick-start:
    1. Get a free token at https://huggingface.co/settings/tokens  (Read access)
    2. Set the env var:   $env:HF_TOKEN = "hf_..."
    3. Run:  .\\qwen_env\\Scripts\\python.exe download_model.py

hf_transfer is used automatically when installed for much faster parallel downloads.
"""
import os
import sys

# Enable hf_transfer for parallel multi-connection downloads (up to 5x faster)
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")

try:
    import hf_transfer  # noqa: F401 — just importing enables it
except ImportError:
    pass

from huggingface_hub import snapshot_download

MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"

# Check for token
token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
if not token:
    print("[!] WARNING: No HF_TOKEN found.")
    print("    Unauthenticated downloads are heavily rate-limited by Hugging Face.")
    print("    For fast downloads:")
    print("      1. Get a free token at https://huggingface.co/settings/tokens")
    print("      2. Set $env:HF_TOKEN = 'hf_...' before running this script")
    print("    Continuing without token (may be very slow or fail)...\n")

print(f"[*] Downloading {MODEL_ID}")
print("[*] Model size: ~15 GB (safetensors weights only)")
print("[*] Please wait — this may take 5-20 minutes depending on your connection...\n")

cache_path = snapshot_download(
    repo_id=MODEL_ID,
    ignore_patterns=["*.gguf", "*.bin"],   # safetensors only
    token=token or None,
)

print(f"\n[+] Model downloaded successfully!")
print(f"    Cached at: {cache_path}")
print("\n[*] You can now run Phase3.py:")
print(f"    .\\qwen_env\\Scripts\\python.exe Phase3.py \"Your prompt here\"")
