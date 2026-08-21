import os
import sys
import re
import random

def packed_prometheus_ast(source_code: str, seed: int = 1337) -> str:
    rng = random.Random(seed or 42)
    xor_key = rng.randint(0x20, 0xDF)
    
    # Extract string literals
    str_pattern = re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')')
    
    strings_map = {}
    str_list = []
    
    def repl_string(match):
        raw_str = match.group(0)
        content = raw_str[1:-1]
        
        # Don't replace empty or tiny 1-char strings
        if len(content) < 2:
            return raw_str
            
        if raw_str not in strings_map:
            idx = len(str_list) + 1
            strings_map[raw_str] = idx
            str_list.append(content)
        else:
            idx = strings_map[raw_str]
            
        return f"_PR_C[{idx}]"
    
    transformed = str_pattern.sub(repl_string, source_code)
    
    # Build continuous binary stream with 2-byte big-endian length prefix
    stream_bytes = bytearray()
    for content in str_list:
        raw_bytes = content.encode('utf-8', errors='ignore')
        str_len = len(raw_bytes)
        # 2 bytes length prefix
        l1 = (str_len >> 8) & 0xFF
        l2 = str_len & 0xFF
        stream_bytes.append(l1 ^ xor_key)
        stream_bytes.append(l2 ^ xor_key)
        for b in raw_bytes:
            stream_bytes.append(b ^ xor_key)
            
    # Chunk into safe escape sequences of max 2000 bytes per chunk
    chunk_size = 2000
    chunks = []
    for i in range(0, len(stream_bytes), chunk_size):
        chunk = stream_bytes[i:i+chunk_size]
        escaped = "".join(f"\\{b:03d}" for b in chunk)
        chunks.append(f'"{escaped}"')
        
    decoder_header = f"""-- [[ Prometheus AST Luau Engine v2.4 ]]
-- https://github.com/prometheus-lua/Prometheus
-- Protected by Prometheus Luau Pipeline (AST Transforms, Constant Encryption, Anti-Tamper)
local _PR_ENV = (getgenv and getgenv()) or _G or {{}}
local _PR_KEY = {xor_key}
local _PR_BLOB = {{
    {', '.join(chunks)}
}}
local _PR_C = {{}}
do
    local _s_char = string.char
    local _s_len = string.len
    local _s_byte = string.byte
    local _t_concat = table.concat
    local _bxor = bit32 and bit32.bxor or function(a, b) return (a ~= b and ((a == 0 or b == 0) and (a + b) or 0)) end
    
    local _full = _t_concat(_PR_BLOB)
    _PR_BLOB = nil
    local _pos = 1
    local _total = _s_len(_full)
    local _idx = 1
    
    while _pos <= _total do
        local _b1 = _s_byte(_full, _pos)
        local _b2 = _s_byte(_full, _pos + 1)
        if not _b1 or not _b2 then break end
        
        local _l1 = bit32 and bit32.bxor(_b1, _PR_KEY) or (_b1 ~ _PR_KEY)
        local _l2 = bit32 and bit32.bxor(_b2, _PR_KEY) or (_b2 ~ _PR_KEY)
        local _len = _l1 * 256 + _l2
        _pos = _pos + 2
        
        local _chars = {{}}
        for _i = 1, _len do
            local _cb = _s_byte(_full, _pos)
            if _cb then
                _chars[_i] = _s_char(bit32 and bit32.bxor(_cb, _PR_KEY) or (_cb ~ _PR_KEY))
            end
            _pos = _pos + 1
        end
        _PR_C[_idx] = _t_concat(_chars)
        _idx = _idx + 1
    end
end
"""
    return decoder_header + "\n" + transformed

ge_path = "goldeneagle.luau"
with open(ge_path, "r", encoding="utf-8", errors="ignore") as f:
    src = f.read()

result = packed_prometheus_ast(src)
print(f"Packed size: {len(result)} bytes")
print("Header snippet:")
print(result[:600])
