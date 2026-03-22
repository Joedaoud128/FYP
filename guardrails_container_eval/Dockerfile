FROM python:3.12-slim

# non-root user (good for evaluation)
RUN useradd -m agent
USER agent
WORKDIR /workspace

COPY --chown=agent:agent guardrails.py /workspace/guardrails.py
COPY --chown=agent:agent dangerous_payload.py /workspace/dangerous_payload.py
COPY --chown=agent:agent test_guardrails.py /workspace/test_guardrails.py

CMD ["python", "test_guardrails.py"]