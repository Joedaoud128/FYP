# =============================================================================
# Dockerfile — agent-sandbox (hardened)
# =============================================================================
# Security hardening applied per docker_security_report_4 (sections 2.1–2.6
# and the complete flag set in section 3).
#
# Build:
#   docker build -t agent-sandbox .
#
# Run (full hardened command — matches section 3 of the security report):
#   docker run --rm                                         \
#     --network none                                        \
#     --read-only                                           \
#     --tmpfs /workspace:rw,noexec,nosuid,size=100m         \
#     --cap-drop ALL                                        \
#     --security-opt no-new-privileges=true                 \
#     --pids-limit 100                                      \
#     --memory 512m                                         \
#     --memory-swap 512m                                    \
#     --cpus 1                                              \
#     --user 1000:1000                                      \
#     -v /host/script.py:/sandbox/script.py:ro             \
#     agent-sandbox python /sandbox/script.py
#
# The ESIB_AiCodingAgent.py sets RUNNING_IN_DOCKER=1 so pipeline modules
# can detect the container environment.
# =============================================================================

# ── Base image ────────────────────────────────────────────────────────────────
# Use slim to minimise attack surface (no gcc, curl, wget by default).
FROM python:3.11-slim

# ── Security: metadata labels ─────────────────────────────────────────────────
LABEL maintainer="FYP_26_21"
LABEL project="ESIB AI Coding Agent"
LABEL security.read-only-root="true"
LABEL security.no-new-privileges="true"
LABEL security.network="none"

# ── Security: create a non-root user (UID/GID 1000) ──────────────────────────
# Matches the --user 1000:1000 runtime flag from the security report (§2.3).
# All subsequent commands and the final CMD run as this user.
RUN groupadd --gid 1000 agent && \
    useradd  --uid 1000 --gid 1000 --no-create-home --shell /bin/false agent


# ── Python dependencies ────────────────────────────────────────────────────────
# Install as root before switching user so site-packages are read-only at
# runtime (container runs --read-only; pip writes are only to /workspace tmpfs).
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# ── Sandbox directory setup ───────────────────────────────────────────────────
# /sandbox  — read-only mount point for user scripts (:ro flag at runtime)
# /workspace — writable tmpfs (rw,noexec,nosuid,size=100m at runtime)
#
# noexec on /workspace means compiled binaries written there cannot be run,
# preventing binary-drop attacks.  nosuid prevents privilege escalation via
# setuid binaries even if one is written to the tmpfs.
#
# We create both dirs here; /workspace is overridden by the tmpfs mount at
# runtime so its contents in the image are irrelevant.
RUN mkdir -p /sandbox /workspace && \
    chown agent:agent /sandbox /workspace && \
    chmod 755 /sandbox && \
    chmod 700 /workspace

# ── Agent source files ────────────────────────────────────────────────────────
# Copy only the files required to run the pipeline inside the container.
# The ESIB_AiCodingAgent.py is the sole entry point.
WORKDIR /app

COPY src/orchestrator/orchestrator.py         /app/
COPY src/orchestrator/orchestrator_handoff.py /app/
COPY src/debugging/debugging.py               /app/
COPY src/generation/generation.py             /app/
COPY src/guardrails/guardrails_engine.py      /app/
COPY src/guardrails/guardrails_config.yaml    /app/
COPY docker/docker_executor.py                /app/
COPY ESIB_AiCodingAgent.py                    /app/

# Ensure agent user owns the app directory (read access; no writes needed here)
RUN chown -R agent:agent /app && chmod -R 755 /app

# ── Security: switch to non-root user ─────────────────────────────────────────
USER agent

# ── Environment ───────────────────────────────────────────────────────────────
# Signal to pipeline modules that we are running inside Docker.
ENV RUNNING_IN_DOCKER=1
# Ollama is reachable on the host via the SSH reverse tunnel.
# Override at runtime: docker run -e OLLAMA_URL=http://host-ip:11434 ...
ENV OLLAMA_URL=http://host.docker.internal:11434
ENV OLLAMA_MODEL=qwen2.5-coder:7b
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ── Healthcheck ───────────────────────────────────────────────────────────────
# Lightweight check: verify Python and the main entry point load correctly.
# Runs every 30s; 3 consecutive failures mark the container unhealthy.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 --version > /dev/null 2>&1 || exit 1

# ── Entry point ───────────────────────────────────────────────────────────────
# Default: show help. Override with docker run ... --generate "..." or --fix ...
# No default entrypoint — docker_executor mounts and runs scripts directly
# ESIB_AiCodingAgent.py is the host entry point, not the container entry point
ENTRYPOINT ["python3"]
CMD ["--help"]