import os
import sys
import subprocess
import tempfile
import shutil

base_dir = os.path.dirname(os.path.abspath(__file__))
obf_v2_cli = os.path.join(base_dir, "o_bfuscate_v2", "bin", "obfuscate.js")
node_bin = shutil.which("node") or "node"

print(f"Node binary: {node_bin}")
print(f"O_bfuscate v2 CLI exists: {os.path.exists(obf_v2_cli)}")

test_code = """--!native
local Player = game:GetService("Players").LocalPlayer
local Character = Player.Character or Player.CharacterAdded:Wait()
print("Golden Eagle Hub Loaded for " .. Player.Name)
"""

with tempfile.NamedTemporaryFile(suffix=".luau", delete=False, mode="w", encoding="utf-8") as in_f:
    in_f.write(test_code)
    in_path = in_f.name

out_path = in_path + ".obf.luau"

cmd = [node_bin, obf_v2_cli, in_path, "--preset", "ultra-secure", "-o", out_path]
proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=os.path.join(base_dir, "o_bfuscate_v2"))
print(f"Return code: {proc.returncode}")
print(f"Stdout:\n{proc.stdout}")

if os.path.exists(out_path):
    with open(out_path, "r", encoding="utf-8") as f:
        res = f.read()
    print("=== OBFUSCATED OUTPUT (ULTRA SECURE) ===")
    print(res[:600])

for p in [in_path, out_path]:
    if os.path.exists(p): os.unlink(p)
