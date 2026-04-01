# === BASE IMAGE ===
FROM python:3.11-slim-bookworm

# === SYSTEM SETUP ===
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# === PRE-INSTALL COMMON PYTHON PACKAGES ===
RUN pip install --no-cache-dir \
    requests \
    flask \
    pandas \
    numpy \
    matplotlib \
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
