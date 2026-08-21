import os
import sys
import subprocess
import shutil

base_dir = os.path.dirname(os.path.abspath(__file__))
prom_cli = os.path.join(base_dir, "Prometheus", "cli.lua")

print(f"Base dir: {base_dir}")
print(f"Prom cli exists: {os.path.exists(prom_cli)}")

lua_bin = None
for candidate in ["luajit", "lua5.1", "lua", "luajit.exe", "lua.exe", "/usr/bin/luajit", "/usr/bin/lua5.1", "/usr/bin/lua"]:
    if shutil.which(candidate) or (os.path.isabs(candidate) and os.path.exists(candidate)):
        lua_bin = candidate
        break

print(f"Detected lua_bin: {lua_bin}")
