import os
import sys

# Add path to fleed_whitelist
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fleed_whitelist"))
from crypto_engine import crypto_engine

ge_path = os.path.join(os.path.dirname(__file__), "goldeneagle.luau")
if os.path.exists(ge_path):
    with open(ge_path, "r", encoding="utf-8", errors="ignore") as f:
        src = f.read()
    
    print(f"Read {len(src)} bytes from {ge_path}")
    obf = crypto_engine._obfuscate_with_prometheus_ast(src[:5000])
    print(f"Obfuscated {len(obf)} bytes")
    print(obf[:800])
