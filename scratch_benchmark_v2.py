import os
import sys
import subprocess
import time
import shutil

base_dir = os.path.dirname(os.path.abspath(__file__))
obf_v2_cli = os.path.join(base_dir, "o_bfuscate_v2", "bin", "obfuscate.js")
node_bin = shutil.which("node") or "node"

ge_path = os.path.join(base_dir, "goldeneagle.luau")
out_path = os.path.join(base_dir, "goldeneagle.test.out.luau")

t0 = time.time()
cmd = [node_bin, obf_v2_cli, ge_path, "--preset", "ultra-secure", "-o", out_path]
proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=os.path.join(base_dir, "o_bfuscate_v2"))
t1 = time.time()

print(f"Status: {proc.returncode}")
print(f"Elapsed: {t1 - t0:.2f}s")
print(f"Stdout:\n{proc.stdout}")
if os.path.exists(out_path):
    print(f"Output file size: {os.path.getsize(out_path)} bytes")
    os.unlink(out_path)
