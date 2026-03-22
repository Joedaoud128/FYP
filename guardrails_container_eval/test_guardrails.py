# test_guardrails.py
from guardrails import gate
from dangerous_payload import ATTEMPTS

for cmd in ATTEMPTS:
    decision = gate(cmd)
    print(f"{cmd}\n  -> {decision.reason}\n")

extra = [
    "python -m pip install yfinance",
    "python -m pip install yfinance --upgrade",
]

for cmd in extra:
    decision = gate(cmd)
    print(f"{cmd}\n  -> {decision.reason}\n")