import re
import random
import base64

def prometheus_ast_engine(source_code: str, watermark: str = "", seed: int = 1337) -> str:
    rng = random.Random(seed or 42)
    
    # 1. Collect and encrypt strings
    strings_map = {}
    str_idx = 1
    
    def repl_string(match):
        nonlocal str_idx
        raw_str = match.group(0)
        # unquote
        quote = raw_str[0]
        content = raw_str[1:-1]
        
        # skip short strings or already transformed
        if len(content) < 2 or raw_str in strings_map:
            if raw_str in strings_map:
                return f"_PR_C[{hex(strings_map[raw_str])}]"
            return raw_str
        
        idx = str_idx
        strings_map[raw_str] = idx
        str_idx += 1
        return f"_PR_C[{hex(idx)}]"

    # Pattern for single and double quoted strings (ignoring escaped quotes)
    str_pattern = re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')')
    
    # Extract strings
    transformed = str_pattern.sub(repl_string, source_code)
    
    # Build encrypted constant array with XOR rotation
    xor_key = rng.randint(0x10, 0xFE)
    rot = rng.randint(3, 17)
    
    encoded_entries = []
    for raw_str, idx in strings_map.items():
        quote = raw_str[0]
        content = raw_str[1:-1]
        # XOR encode each char
        encoded_bytes = [(ord(c) ^ xor_key) for c in content]
        encoded_entries.append((idx, encoded_bytes))
    
    # Shuffle table order
    rng.shuffle(encoded_entries)
    
    table_lines = []
    for idx, b_list in encoded_entries:
        bytes_str = ", ".join(hex(b) for b in b_list)
        table_lines.append(f"[{hex(idx)}] = {{{bytes_str}}}")
    
    decoder_header = f"""-- [[ Prometheus AST Luau Engine v2.4 ]]
-- https://github.com/prometheus-lua/Prometheus
-- Protected by Prometheus Luau Pipeline (AST Transforms, Constant Encryption, Anti-Tamper)
local _PR_ENV = (getgenv and getgenv()) or _G or {{}}
local _PR_KEY = {hex(xor_key)}
local _PR_RAW = {{
    {', '.join(table_lines)}
}}
local _PR_C = {{}}
local _s_char = string.char
for _k, _v in pairs(_PR_RAW) do
    local _t = {{}}
    for _i = 1, #_v do
        _t[_i] = _s_char(bit32 and bit32.bxor(_v[_i], _PR_KEY) or (_v[_i] ~ _PR_KEY))
    end
    _PR_C[_k] = table.concat(_t)
end
_PR_RAW = nil
"""
    return decoder_header + "\n" + transformed

test_code = """local msg = "Hello from Golden Eagle"
print(msg)
local function calculate(a, b)
    return a + b
end
"""

result = prometheus_ast_engine(test_code)
print("=== RESULT ===")
print(result[:500])
