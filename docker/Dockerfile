# === BASE IMAGE ===
FROM python:3.11-slim-bookworm

# NOTE: numpy, pandas, matplotlib excluded due to VM bandwidth constraints.
# These are installed on-demand via execute_with_packages() when needed.
RUN pip install --no-cache-dir \
    --timeout 120 \
    requests \
    flask \
    beautifulsoup4 \
    python-dotenv \
    pytest

# === CREATE NON-ROOT USER ===
RUN useradd --create-home --shell /bin/bash sandbox

# === WORKSPACE DIRECTORY ===
RUN mkdir -p /workspace && chown sandbox:sandbox /workspace
WORKDIR /workspace

# === SWITCH TO NON-ROOT USER ===
USER sandbox

# === DEFAULT COMMAND ===
CMD ["python3"]