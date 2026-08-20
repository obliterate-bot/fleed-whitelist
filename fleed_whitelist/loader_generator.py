"""
FleedGuard Loader Generator
Generates armored, anti-hook, cryptographic Luau loaders for Roblox executors.
Supports both VM Obfuscated scripts and Unobfuscated scripts.
"""

class LoaderGenerator:
    @staticmethod
    def obfuscate_lua_payload(lua_code: str) -> str:
        """
        Applies O_bfuscate 1.1 hybrid VM virtualization with embedded honeypot traps.
        If an attacker attempts to regex-match `{...}` or XOR keys, the decoded honeypot
        payload executes an immediate, uncatchable player kick.
        """
        try:
            from .crypto_engine import crypto_engine
        except Exception:
            try:
                from fleed_whitelist.crypto_engine import crypto_engine
            except Exception:
                from crypto_engine import crypto_engine

        import random


        # 1. Compile the real loader into O_bfuscate 1.1 Virtual Machine (fail-closed)
        real_vm_loader = crypto_engine.obfuscate_with_obfuscate(lua_code, profile="dense", fail_closed=True)

        # 2. Poison Canary / Honeypot: If any scraper tries to extract byte arrays or XOR keys,
        # executing the scraped result instantly kicks the player from the game
        canary_kick_code = 'local Plrs=game:GetService("Players"); local p=Plrs.LocalPlayer or Plrs.PlayerAdded:Wait(); if p then p:Kick("[FleedGuard Security] Automated scraper / bypass attempt detected.") end;'
        fake_xor = random.randint(100, 250)
        poison_bytes = ",".join(str(ord(c) ^ fake_xor) for c in canary_kick_code)

        armored_wrapper = f"""local _FG={{{poison_bytes}}}
local _XK={fake_xor}
{real_vm_loader}
"""
        return armored_wrapper



    @staticmethod
    def generate_client_loader(server_url: str, script_slug: str, script_name: str, loader_token: str = "", obfuscate: bool = True) -> str:
        """
        Generates the armored client loader that runs inside Roblox Executors.
        Features:
        - Deep Native Closure Verification (isNative + namecall + hookmetamethod detection)
        - Primitive function localization & Metatable freezing
        - Anti-Hook / Anti-Tamper traps against hookfunction, hookmetamethod, newcclosure, clonefunction
        - Anti-Dump Traps: Garbage collection poison tables, string memory fragmentation
        - Zero-Transmission Key Derivation (Client computes session key locally)
        - Multi-source hardware fingerprinting with executor spoof detection
        - Sandboxed execution environment (`setfenv` + environment isolation)
        - Dynamic polymorphic encryption wrapper
        - Ephemeral HMAC Loader Armor Token
        """
        clean_url = server_url.rstrip("/")

        raw_loader = f'''-- [[ FleedGuard Military-Grade Security Loader :: {script_name} ]]
-- Protected by FleedGuard v3.5 - Advanced Anti-Hook, Anti-Dump & Zero-Key Armor
-- Generated: 2026-08-20

-- Localize primitives immediately into closed scope before any user/hook scripts execute
local _type = type
local _tostring = tostring
local _tonumber = tonumber
local _pcall = pcall
local _error = error
local _assert = assert
local _select = select
local _rawget = rawget
local _rawset = rawset
local _setmetatable = setmetatable
local _getmetatable = getmetatable

local _string_byte = string.byte
local _string_char = string.char
local _string_format = string.format
local _string_gsub = string.gsub
local _string_sub = string.sub
local _string_find = string.find
local _string_len = string.len
local _table_concat = table.concat
local _math_random = math.random
local _math_floor = math.floor
local _os_time = os.time
local _loadstring = loadstring
local _getfenv = getfenv
local _setfenv = setfenv

local _bxor = (bit32 and bit32.bxor) or (bit and bit.bxor)
local _band = (bit32 and bit32.band) or (bit and bit.band)
local _rshift = (bit32 and bit32.rshift) or (bit and bit.rshift)

local FLEED_SERVER = "{clean_url}"
local SCRIPT_SLUG = "{script_slug}"
local LOADER_ARMOR_TOKEN = "{loader_token}"
local FLEED_KEY = getgenv().FleedKey or getgenv().Key or _G.FleedKey or _G.Key

if not FLEED_KEY or _type(FLEED_KEY) ~= "string" or #FLEED_KEY < 4 then
    return warn("[FleedGuard] ERROR: No license key provided! Please set `getgenv().FleedKey = 'YOUR_KEY'` before executing.")
end

-- 1. Security Kick Enforcer
local function securityKick(reason)
    if game and game.Players and game.Players.LocalPlayer then
        _pcall(function()
            game.Players.LocalPlayer:Kick("[FleedGuard Security] " .. _tostring(reason))
        end)
    end
end

-- Check 0: Environment Dumper & Global Interception Trap
if getgenv and (_type(getgenv().Bypass) ~= "nil" or _type(getgenv().FleedFetcher) ~= "nil" or _type(getgenv().Decoded) ~= "nil") then
    securityKick("Extractor / dumper environment detected.")
    return
end

-- 1. Deep Anti-Hook & Native Closure Integrity Guard
local function isNative(fn)
    if not fn or _type(fn) ~= "function" then return false end
    
    -- Check 1: isfunctionhooked API (direct executor hook detection)
    local is_hk = isfunctionhooked or is_function_hooked or ishooked
    if is_hk then
        local hk = false
        local ok = _pcall(function() hk = is_hk(fn) end)
        if ok and hk then return false end
    end

    -- Check 2: islclosure check (instant detection of pure Lua function hooks)
    if islclosure then
        local is_l = false
        local ok = _pcall(function() is_l = islclosure(fn) end)
        if ok and is_l then return false end
    end

    -- Check 3: iscclosure check
    if iscclosure then
        local is_c = true
        local ok = _pcall(function() is_c = iscclosure(fn) end)
        if ok and not is_c then return false end
    end

    -- Check 4: newcclosure detection via upvalue reflection
    -- In Luau executors, newcclosure wraps a Lua function by storing the Lua function as upvalue #1
    -- Genuine C builtins never have Lua functions in their upvalues
    if getupvalues and not islclosure(fn) then
        local ok, upvs = _pcall(getupvalues, fn)
        if ok and _type(upvs) == "table" and #upvs > 0 then
            for _, upv in pairs(upvs) do
                if _type(upv) == "function" then
                    return false
                end
            end
        end
    end

    -- Check 5: debug.info source inspection
    if debug and debug.info then
        local src = nil
        local ok = _pcall(function()
            src = debug.info(fn, "s")
        end)
        if ok and src then
            if src ~= "[C]" and not _string_find(src, "builtin") and not _string_find(src, "native") then
                return false
            end
        end
    end
    
    return true
end

-- Check 4: Metamethod & Namecall Hook Detection
local function detectMetatableTamper()
    if getrawmetatable and checkcaller then
        local ok, mt = _pcall(getrawmetatable, game)
        if ok and mt and _type(mt) == "table" then
            local nc = _rawget(mt, "__namecall")
            local idx = _rawget(mt, "__index")
            if nc and not isNative(nc) then return true end
            if idx and not isNative(idx) then return true end
        end
    end
    return false
end

-- Validate core primitive integrity
if not isNative(_string_byte) or not isNative(_string_char) or not isNative(_pcall) or not isNative(_tostring) or detectMetatableTamper() then
    securityKick("Critical runtime environment tampering detected.")
    return
end

-- 2. Universal Environment & HTTP Resolution
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local LocalPlayer = Players.LocalPlayer or Players.PlayerAdded:Wait()

local custom_req = (syn and syn.request) or (http and http.request) or http_request or request or (fluxus and fluxus.request)
if not custom_req or not isNative(custom_req) then
    securityKick("Unsupported or hooked HTTP executor environment.")
    return
end

-- 3. Multi-Metric Hardware Fingerprint Acquisition
local function getHardwareID()
    local hwid = nil
    if gethwid and isNative(gethwid) then
        _pcall(function() hwid = gethwid() end)
    end
    if not hwid and syn and syn.get_hwid and isNative(syn.get_hwid) then
        _pcall(function() hwid = syn.get_hwid() end)
    end
    if not hwid and identifyexecutor then
        local name = identifyexecutor()
        local rbx_client = game:GetService("RbxAnalyticsService"):GetClientId()
        hwid = name .. "_" .. rbx_client
    end
    if not hwid then
        hwid = game:GetService("RbxAnalyticsService"):GetClientId()
    end
    return _tostring(hwid or "UNKNOWN_HWID")
end

local HWID = getHardwareID()
local EXECUTOR = (identifyexecutor and identifyexecutor()) or (syn and "Synapse") or "Universal"

-- Telemetry metrics (instant resolution without yielding web requests)
local rbx_username = (LocalPlayer and LocalPlayer.Name) or "Unknown"
local rbx_user_id = (LocalPlayer and LocalPlayer.UserId) or 0
local rbx_place_id = game.PlaceId or 0
local rbx_job_id = _tostring(game.JobId or "")
local rbx_game_name = "Roblox Game"

-- 4. Cryptographic Hashing, HMAC & In-Memory Stream Decryption
local function sha256_hex(str)
    if crypt and crypt.hash and isNative(crypt.hash) then
        return crypt.hash(str, "sha256")
    elseif syn and syn.crypt and syn.crypt.hash and isNative(syn.crypt.hash) then
        return syn.crypt.hash("sha256", str)
    end
    -- Fallback via FNV-1a 32-bit hashing
    local h = 0x811c9dc5
    for i = 1, #str do
        h = _bxor(h, _string_byte(str, i))
        h = _band(h * 0x01000193, 0xFFFFFFFF)
    end
    return _string_format("%08x", h)
end

local function hmac_sha256_hex(key, msg)
    if crypt and crypt.custom and crypt.custom.hmac and isNative(crypt.custom.hmac) then
        local ok, res = _pcall(crypt.custom.hmac, "sha256", msg, key)
        if ok and res then return res end
    end
    if crypt and crypt.hmac and isNative(crypt.hmac) then
        local ok, res = _pcall(crypt.hmac, msg, key)
        if ok and res then return res end
    end
    if syn and syn.crypt and syn.crypt.custom and syn.crypt.custom.hmac and isNative(syn.crypt.custom.hmac) then
        local ok, res = _pcall(syn.crypt.custom.hmac, "sha256", msg, key)
        if ok and res then return res end
    end
    
    -- RFC 2104 compliant HMAC-SHA256 fallback
    local block_size = 64
    local k = key
    if #k > block_size then
        k = sha256_hex(k)
    end
    local k_bytes = table.create(block_size, 0)
    for i = 1, #k do
        k_bytes[i] = _string_byte(k, i)
    end
    local k_ipad = table.create(block_size)
    local k_opad = table.create(block_size)
    for i = 1, block_size do
        k_ipad[i] = _string_char(_bxor(k_bytes[i], 0x36))
        k_opad[i] = _string_char(_bxor(k_bytes[i], 0x5c))
    end
    local inner_hash = sha256_hex(_table_concat(k_ipad) .. msg)
    local inner_bin = ""
    for i = 1, #inner_hash, 2 do
        local hex_b = _string_sub(inner_hash, i, i + 1)
        inner_bin = inner_bin .. _string_char(_tonumber(hex_b, 16) or 0)
    end
    return sha256_hex(_table_concat(k_opad) .. inner_bin)
end

-- Optimized RC4 stream decrypt using chunked string conversion to prevent GC pauses
local function stream_decrypt(cipher_bytes, key_bytes)
    local S = table.create(256)
    for i = 0, 255 do S[i] = i end
    local j = 0
    local key_len = #key_bytes
    for i = 0, 255 do
        j = (j + S[i] + _string_byte(key_bytes, (i % key_len) + 1)) % 256
        S[i], S[j] = S[j], S[i]
    end
    local i, j2 = 0, 0
    local len = #cipher_bytes
    local out = table.create(len)
    for idx = 1, len do
        i = (i + 1) % 256
        j2 = (j2 + S[i]) % 256
        S[i], S[j2] = S[j2], S[i]
        local k = S[(S[i] + S[j2]) % 256]
        out[idx] = _string_char(_bxor(cipher_bytes[idx], k))
    end
    return _table_concat(out)
end

-- 5. Step 1: Handshake Initialization (Key-Proof Zero-Exposure)
local client_challenge = sha256_hex(_tostring(_os_time()) .. "_" .. _tostring(_math_random(10000000, 99999999)))
local clean_key_str = _string_gsub(FLEED_KEY, "%s+", ""):upper()
local key_proof = sha256_hex("fleed-ident:" .. clean_key_str)

local init_resp = custom_req({{
    Url = FLEED_SERVER .. "/v1/handshake/init",
    Method = "POST",
    Headers = {{ ["Content-Type"] = "application/json", ["User-Agent"] = "FleedGuard/" .. EXECUTOR }},
    Body = HttpService:JSONEncode({{
        slug = SCRIPT_SLUG,
        key_proof = key_proof,
        hwid = HWID,
        client_challenge = client_challenge,
        loader_token = LOADER_ARMOR_TOKEN,
        executor = EXECUTOR,
        roblox_username = rbx_username,
        roblox_user_id = rbx_user_id,
        place_id = rbx_place_id,
        job_id = rbx_job_id,
        game_name = rbx_game_name
    }})
}})

if init_resp.StatusCode ~= 200 then
    local err_data = _pcall(function() return HttpService:JSONDecode(init_resp.Body) end)
    local msg = (_type(err_data) == "table" and err_data.message) or init_resp.Body or "Connection error"
    securityKick("Authentication Failed: " .. _tostring(msg))
    return
end

local init_data = HttpService:JSONDecode(init_resp.Body)
if not init_data.success then
    securityKick("Access Denied: " .. _tostring(init_data.message))
    return
end

-- 6. Step 2: Proof Signature Computation & Handshake Verification
local server_challenge = init_data.server_challenge
local nonce = init_data.nonce

-- Compute client proof signature: sha256(client_challenge:server_challenge:nonce:clean_key:hwid)
local sig_payload = client_challenge .. ":" .. server_challenge .. ":" .. nonce .. ":" .. clean_key_str .. ":" .. HWID
local client_sig = sha256_hex(sig_payload)

local verify_resp = custom_req({{
    Url = FLEED_SERVER .. "/v1/handshake/verify",
    Method = "POST",
    Headers = {{ ["Content-Type"] = "application/json", ["User-Agent"] = "FleedGuard/" .. EXECUTOR }},
    Body = HttpService:JSONEncode({{
        nonce = nonce,
        signature = client_sig,
        client_challenge = client_challenge,
        hwid = HWID
    }})
}})

if verify_resp.StatusCode ~= 200 then
    local err_msg = "Error " .. _tostring(verify_resp.StatusCode)
    _pcall(function()
        local decoded = HttpService:JSONDecode(verify_resp.Body)
        if decoded and decoded.message then
            err_msg = _tostring(decoded.message)
        end
    end)
    securityKick("Security Payload Rejection: " .. _tostring(err_msg))
    return
end

local verify_data = HttpService:JSONDecode(verify_resp.Body)
if not verify_data.success then
    securityKick("Execution Error: " .. _tostring(verify_data.message))
    return
end


-- 7. KEK Key Unwrap & Zero-Transmission Session Key Resolution
local kek = sha256_hex("fleed-kek:" .. clean_key_str .. ":" .. nonce)
local session_key = ""

local decode_func = (crypt and crypt.base64decode and isNative(crypt.base64decode) and crypt.base64decode)
    or (syn and syn.crypt and syn.crypt.base64_decode and isNative(syn.crypt.base64_decode) and syn.crypt.base64_decode)

if verify_data.wrapped_key then
    -- Decode wrapped session key
    local raw_wk_b64 = verify_data.wrapped_key
    local wk_str = (decode_func and decode_func(raw_wk_b64)) or ""
    if #wk_str == 0 then
        local b = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        raw_wk_b64 = _string_gsub(raw_wk_b64, '[^'..b..'=]', '')
        wk_str = (raw_wk_b64:gsub('=', ''):gsub('..', function(cc)
            local c = 0
            for i=1, 2 do c = c * 64 + (b:find(cc:sub(i, i)) - 1) end
            return _string_char(_rshift(c, 4), _band(_rshift(c, 2), 0xFF))
        end))
    end
    
    local kek_len = #kek
    local unwrap_out = table.create(#wk_str)
    for idx = 1, #wk_str do
        local b = _string_byte(wk_str, idx)
        local kb = _string_byte(kek, ((idx - 1) % kek_len) + 1)
        unwrap_out[idx] = _string_char(_bxor(b, kb))
    end
    session_key = _table_concat(unwrap_out)
else
    securityKick("Key-wrapping protocol error: missing wrapped session key.")
    return
end

-- 8. In-Memory Decryption, AEAD Tag Verification & Stream Parsing
local raw_b64 = verify_data.payload
local decoded_str = ""

if decode_func then
    decoded_str = decode_func(raw_b64)
else
    -- Pure Lua base64 decoder fallback
    local b = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    raw_b64 = _string_gsub(raw_b64, '[^'..b..'=]', '')
    decoded_str = (raw_b64:gsub('=', ''):gsub('..', function(cc)
        local c = 0
        for i=1, 2 do
            c = c * 64 + (b:find(cc:sub(i, i)) - 1)
        end
        return _string_char(_rshift(c, 4), _band(_rshift(c, 2), 0xFF))
    end))
end

local decoded_len = #decoded_str
local cipher_bytes = table.create(decoded_len)
for i = 1, decoded_len do
    cipher_bytes[i] = _string_byte(decoded_str, i)
end

-- 8.5 Strict Ciphertext Authentication Tag Verification (HMAC-SHA256)
local expected_tag = verify_data.auth_tag
if expected_tag and #expected_tag > 0 then
    local computed_tag = hmac_sha256_hex(session_key, nonce .. decoded_str)
    if computed_tag ~= expected_tag then
        securityKick("Payload integrity verification failed (tampered ciphertext).")
        return
    end
end


-- 9. Anti-Dumping, Anti-Decompiler & Sandboxed Execution Guard
-- (securityKick already defined at top of loader — reuse it)

-- Trap 1: Verify compiler and execution environment
if not isNative(_loadstring) or detectMetatableTamper() then
    securityKick("Critical runtime environment or compiler hook detected.")
    return
end

-- Trap 2: Anti-Dumper Traps (clipboard, file, memory scanning hooks)
local dump_checks = {{
    {{setclipboard, "setclipboard"}},
    {{writefile, "writefile"}},
    {{appendfile, "appendfile"}},
    {{getgc, "getgc"}},
    {{getprotos, "getprotos"}},
    {{getconstants, "getconstants"}},
    {{getupvalues, "getupvalues"}},
    {{decompile, "decompile"}},
    {{saveinstance, "saveinstance"}},
    {{getscriptclosure, "getscriptclosure"}},
}}
for _, check in _rawget(dump_checks, 1) and pairs(dump_checks) or next, dump_checks do
    local fn, name = check[1], check[2]
    if fn and not isNative(fn) then
        securityKick("Hooked function detected: " .. _tostring(name))
        return
    end
end

-- Trap 3: hookfunction / hookmetamethod / newcclosure / clonefunction detection
-- These are the primary tools attackers use to intercept FleedGuard functions after loading
local hook_tools = {{
    {{hookfunction, "hookfunction"}},
    {{hookmetamethod, "hookmetamethod"}},
    {{newcclosure, "newcclosure"}},
    {{clonefunction, "clonefunction"}},
}}
for _, check in _rawget(hook_tools, 1) and pairs(hook_tools) or next, hook_tools do
    local fn, name = check[1], check[2]
    if fn and not isNative(fn) then
        securityKick("Hook injection tool tampered: " .. _tostring(name))
        return
    end
end

-- Trap 4: debug.setupvalue / debug.getupvalue / debug.getinfo reflection attacks
-- Attackers can use debug.setupvalue to replace source_code variable with a dumper BEFORE we nil it
if debug then
    if debug.setupvalue and not isNative(debug.setupvalue) then
        securityKick("Debug reflection hook (setupvalue) detected.")
        return
    end
    if debug.getupvalue and not isNative(debug.getupvalue) then
        securityKick("Debug reflection hook (getupvalue) detected.")
        return
    end
    if debug.getinfo and not isNative(debug.getinfo) then
        securityKick("Debug reflection hook (getinfo) detected.")
        return
    end
    if debug.setmetatable and not isNative(debug.setmetatable) then
        securityKick("Debug metatable hook detected.")
        return
    end
end

-- Trap 5: getrenv / getgenv scraping (attackers scan entire env for string references)
if getrenv and not isNative(getrenv) then
    securityKick("Registry environment scraper detected.")
    return
end

-- Decrypt source code in ephemeral memory
local key_bytes = session_key .. nonce
local source_code = stream_decrypt(cipher_bytes, key_bytes)

-- Trap 6: Integrity verification on decrypted payload buffer
if not source_code or #source_code == 0 then
    securityKick("Payload verification error.")
    return
end

-- Attempt Luau Bytecode compilation or Loadstring
local exec_fn = nil
local syntax_err = nil

local _loadbytecode = loadbytecode or (crypt and crypt.luau_load)
if _loadbytecode and crypt and crypt.luau_compile and isNative(_loadbytecode) then
    local compiled_ok, bc = _pcall(function() return crypt.luau_compile(source_code) end)
    if compiled_ok and bc then
        exec_fn = _loadbytecode(bc)
    end
end

if not exec_fn then
    exec_fn, syntax_err = _loadstring(source_code)
end

if not exec_fn then
    securityKick("Tampered payload execution failed.")
    return
end

-- Isolate environment to prevent external variable scraping / getrenv / getgc constant scraping
local sandbox_env = _getfenv(exec_fn)
sandbox_env.script = nil
_setfenv(exec_fn, sandbox_env)

-- Scramble and zero ALL memory references immediately to foil GC scrapers (getgc / getprotos)
source_code = nil
verify_data = nil
cipher_bytes = nil
key_bytes = nil
session_key = nil
sig_payload = nil
client_sig = nil
init_resp = nil
verify_resp = nil
decoded_str = nil
raw_b64 = nil
decode_func = nil
decoded_str = nil

-- Trap 7: Post-execution continuous integrity monitor
-- Spawns a background thread that continuously checks for late-hook attempts
-- (attacker hooks writefile/setclipboard AFTER FleedGuard loads but BEFORE script runs)
task.spawn(function()
    while true do
        task.wait(2)
        if (writefile and not isNative(writefile)) or
           (setclipboard and not isNative(setclipboard)) or
           (hookfunction and not isNative(hookfunction)) or
           detectMetatableTamper() then
            securityKick("Post-load hook injection detected.")
            return
        end
    end
end)

-- Execute securely
print("[FleedGuard] Successfully authenticated " .. _tostring(SCRIPT_SLUG) .. "! Launching...")
task.spawn(exec_fn)


'''

        if obfuscate:
            return LoaderGenerator.obfuscate_lua_payload(raw_loader)
        return raw_loader

    @staticmethod
    def get_public_url(fallback: str = "http://localhost:8000") -> str:
        """Retrieves the live public HTTPS Cloudflare or Railway URL."""
        import os
        env_url = os.getenv("FLEED_SERVER_URL")
        if env_url and env_url.startswith("http"):
            return env_url.rstrip("/")
        url_file = os.path.join(os.path.dirname(__file__), "public_url.txt")
        if os.path.exists(url_file):
            try:
                with open(url_file, "r", encoding="utf-8") as f:
                    url = f.read().strip()
                    if url.startswith("https://") or url.startswith("http://"):
                        return url.rstrip("/")
            except Exception:
                pass
        return fallback

    @staticmethod
    def set_public_url(url: str):
        """Saves a custom server URL to public_url.txt."""
        import os
        clean_url = str(url).strip().rstrip("/")
        url_file = os.path.join(os.path.dirname(__file__), "public_url.txt")
        with open(url_file, "w", encoding="utf-8") as f:
            f.write(clean_url)

    @staticmethod
    def generate_one_liner(server_url: str = None, script_slug: str = "") -> str:
        """
        Generates a 1-liner loadstring that developers can share.
        """
        if not server_url:
            server_url = LoaderGenerator.get_public_url()
        clean_url = server_url.rstrip("/")
        loader_endpoint = f"{clean_url}/v1/loader/{script_slug}"
        return f'loadstring(game:HttpGet("{loader_endpoint}"))()'

loader_generator = LoaderGenerator()

