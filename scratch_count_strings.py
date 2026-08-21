import os
import re

ge_path = "goldeneagle.luau"
with open(ge_path, "r", encoding="utf-8", errors="ignore") as f:
    s = f.read()

str_pattern = re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')')
matches = str_pattern.findall(s)
print(f"Total string matches in goldeneagle: {len(matches)}")
unique_strings = set(matches)
print(f"Unique strings: {len(unique_strings)}")
