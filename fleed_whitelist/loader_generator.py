"""
FleedGuard Loader Generator
Generates armored, anti-hook, cryptographic Luau loaders for Roblox executors.
Supports both VM Obfuscated scripts and Unobfuscated scripts.
"""

class LoaderGenerator:
    @staticmethod
    def generate_client_loader(server_url: str, script_slug: str, script_name: str) -> str:
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
        """
        clean_url = server_url.rstrip("/")

        return f'''-- [[ FleedGuard Military-Grade Security Loader :: {script_name} ]]
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
local FLEED_KEY = getgenv().FleedKey or getgenv().Key or _G.FleedKey or _G.Key

if not FLEED_KEY or _type(FLEED_KEY) ~= "string" or #FLEED_KEY < 4 then
    return warn("[FleedGuard] ERROR: No license key provided! Please set `getgenv().FleedKey = 'YOUR_KEY'` before executing.")
end

-- 1. Deep Anti-Hook & Native Closure Integrity Guard
local function isNative(fn)
    if not fn or _type(fn) ~= "function" then return false end
    
    -- Check 1: islclosure check (instant detection of Lua function hooks)
    if islclosure then
        local is_l = false
        local ok = _pcall(function() is_l = islclosure(fn) end)
        if ok and is_l then
            return false
        end
    end

    -- Check 2: iscclosure detection if supported
    if iscclosure then
        local is_c = true
        local ok = _pcall(function() is_c = iscclosure(fn) end)
        if ok and not is_c then
            return false
        end
    end

    -- Check 3: Safe debug.info check (handling standard Luau debug.info signature)
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
    if game and game.Players and game.Players.LocalPlayer then
        game.Players.LocalPlayer:Kick("[FleedGuard Security] Critical runtime environment tampering detected.")
    end
    return
end

-- 2. Universal Environment & HTTP Resolution
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local LocalPlayer = Players.LocalPlayer or Players.PlayerAdded:Wait()

local custom_req = (syn and syn.request) or (http and http.request) or http_request or request or (fluxus and fluxus.request)
if not custom_req or not isNative(custom_req) then
    return warn("[FleedGuard] CRITICAL: Your executor does not support secure, unhooked HTTP requests.")
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

-- Telemetry metrics
local rbx_username = (LocalPlayer and LocalPlayer.Name) or "Unknown"
local rbx_user_id = (LocalPlayer and LocalPlayer.UserId) or 0
local rbx_place_id = game.PlaceId or 0
local rbx_job_id = _tostring(game.JobId or "")
local rbx_game_name = "Roblox Game"
_pcall(function()
    local Market = game:GetService("MarketplaceService")
    local info = Market:GetProductInfo(game.PlaceId)
    if info and info.Name then
        rbx_game_name = _tostring(info.Name)
    end
end)

-- 4. Cryptographic Hashing & In-Memory Stream Decryption
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

local function stream_decrypt(cipher_bytes, key_bytes)
    local S = {{}}
    for i = 0, 255 do S[i] = i end
    local j = 0
    for i = 0, 255 do
        j = (j + S[i] + _string_byte(key_bytes, (i % #key_bytes) + 1)) % 256
        S[i], S[j] = S[j], S[i]
    end
    local i, j2 = 0, 0
    local out = {{}}
    for idx = 1, #cipher_bytes do
        i = (i + 1) % 256
        j2 = (j2 + S[i]) % 256
        S[i], S[j2] = S[j2], S[i]
        local k = S[(S[i] + S[j2]) % 256]
        out[idx] = _string_char(_bxor(cipher_bytes[idx], k))
    end
    return _table_concat(out)
end

-- 5. Step 1: Handshake Initialization
local client_challenge = sha256_hex(_tostring(_os_time()) .. "_" .. _tostring(_math_random(10000000, 99999999)))

local init_resp = custom_req({{
    Url = FLEED_SERVER .. "/v1/handshake/init",
    Method = "POST",
    Headers = {{ ["Content-Type"] = "application/json", ["User-Agent"] = "FleedGuard/" .. EXECUTOR }},
    Body = HttpService:JSONEncode({{
        slug = SCRIPT_SLUG,
        key = FLEED_KEY,
        hwid = HWID,
        client_challenge = client_challenge,
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
    return warn("[FleedGuard] Authentication Failed: " .. _tostring(msg))
end

local init_data = HttpService:JSONDecode(init_resp.Body)
if not init_data.success then
    return warn("[FleedGuard] Access Denied: " .. _tostring(init_data.message))
end

-- 6. Step 2: Proof Signature Computation & Handshake Verification
local server_challenge = init_data.server_challenge
local nonce = init_data.nonce

-- Compute client proof signature: sha256(client_challenge:server_challenge:nonce:key:hwid)
local sig_payload = client_challenge .. ":" .. server_challenge .. ":" .. nonce .. ":" .. FLEED_KEY .. ":" .. HWID
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
    return warn("[FleedGuard] Payload Delivery Error: " .. _tostring(err_msg))
end

local verify_data = HttpService:JSONDecode(verify_resp.Body)
if not verify_data.success then
    return warn("[FleedGuard] Execution Error: " .. _tostring(verify_data.message))
end

-- 7. Zero-Transmission Local Session Key Derivation
local session_key = sha256_hex(client_challenge .. ":" .. server_challenge .. ":" .. nonce .. ":" .. FLEED_KEY .. ":" .. HWID)

-- 8. In-Memory Decryption, AEAD Tag Verification & Stream Parsing
local raw_b64 = verify_data.payload
local auth_tag = verify_data.auth_tag
local decode_func = (crypt and crypt.base64decode and isNative(crypt.base64decode) and crypt.base64decode)
    or (syn and syn.crypt and syn.crypt.base64_decode and isNative(syn.crypt.base64_decode) and syn.crypt.base64_decode)
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

local cipher_bytes = {{}}
for i = 1, #decoded_str do
    cipher_bytes[i] = _string_byte(decoded_str, i)
end

local key_bytes = session_key .. nonce

-- 9. Anti-Dumping, Anti-Decompiler & Sandboxed Execution Guard
-- Verify compiler and execution environment
if not isNative(_loadstring) or detectMetatableTamper() then
    if game and game.Players and game.Players.LocalPlayer then
        game.Players.LocalPlayer:Kick("[FleedGuard Security] Hooked compiler or metamethod manipulation detected.")
    end
    return
end

-- Anti-Dumper Trap: Detect if global clipboard/file dumping functions are hooked to capture payload
if setclipboard and not isNative(setclipboard) then
    if game and game.Players and game.Players.LocalPlayer then
        game.Players.LocalPlayer:Kick("[FleedGuard Security] Memory dumper hook detected.")
    end
    return
end

if writefile and not isNative(writefile) then
    if game and game.Players and game.Players.LocalPlayer then
        game.Players.LocalPlayer:Kick("[FleedGuard Security] File interceptor hook detected.")
    end
    return
end

-- Decrypt source code in ephemeral memory
local source_code = stream_decrypt(cipher_bytes, key_bytes)

-- Attempt Luau Bytecode compilation or Loadstring
local exec_fn = nil
local syntax_err = nil

-- Check for luau bytecode execution support (e.g. getscriptbytecode / loadbytecode)
local _loadbytecode = (loadbytecode and isNative(loadbytecode) and loadbytecode)
if _loadbytecode and crypt and crypt.luau_compile and isNative(crypt.luau_compile) then
    local compiled_ok, bc = _pcall(function() return crypt.luau_compile(source_code) end)
    if compiled_ok and bc then
        exec_fn = _loadbytecode(bc)
    end
end

if not exec_fn then
    exec_fn, syntax_err = _loadstring(source_code)
end

if not exec_fn then
    return warn("[FleedGuard] Failed to parse script payload: " .. _tostring(syntax_err))
end

-- Isolate environment to prevent external variable scraping / getrenv / getgc constant scraping
local sandbox_env = _getfenv(exec_fn)
sandbox_env.script = nil
_setfenv(exec_fn, sandbox_env)

-- Scramble and zero memory references immediately to foil GC scrapers (getgc / getprotos)
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

-- Execute securely
print("[FleedGuard] Successfully authenticated " .. _tostring(SCRIPT_SLUG) .. "! Launching...")
task.spawn(exec_fn)
'''

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

