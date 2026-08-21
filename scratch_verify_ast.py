import os
import sys
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fleed_whitelist"))
from crypto_engine import crypto_engine

ge_path = os.path.join(os.path.dirname(__file__), "goldeneagle.luau")
with open(ge_path, "r", encoding="utf-8", errors="ignore") as f:
    src = f.read()

obf = crypto_engine._obfuscate_with_prometheus_ast(src)

# Check for unescaped newlines inside table or invalid syntax
print(f"Obfuscated length: {len(obf)}")

# Look for broken patterns like _PR_C[...][...]
broken = re.findall(r'_PR_C\[0x[0-9a-f]+\]\s*\(', obf)
print(f"Found {len(broken)} function calls directly on string lookup: {broken[:5]}")

# Look for occurrences inside comments or multi-line strings
comment_broken = re.findall(r'--.*_PR_C\[', obf)
print(f"Occurrences in single line comments: {len(comment_broken)}")
