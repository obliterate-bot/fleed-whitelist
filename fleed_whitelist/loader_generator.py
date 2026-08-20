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
        """
        # Ensure clean base URL
        clean_url = server_url.rstrip("/")

        return f'''-- [[ FleedGuard Client Security Loader :: {script_name} ]]
-- Protected by FleedGuard v2.0 - Cryptographic HWID & Integrity Engine
-- Generated: 2026-08-19

local FLEED_SERVER = "{clean_url}"
local SCRIPT_SLUG = "{script_slug}"
local FLEED_KEY = getgenv().FleedKey or getgenv().Key or _G.FleedKey or _G.Key

if not FLEED_KEY or type(FLEED_KEY) ~= "string" or #FLEED_KEY < 4 then
    return warn("[FleedGuard] ERROR: No license key provided! Please set `getgenv().FleedKey = 'YOUR_KEY'` before executing.")
end

-- 1. Universal Environment Resolution
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local LocalPlayer = Players.LocalPlayer or Players.PlayerAdded:Wait()

local custom_req = (syn and syn.request) or (http and http.request) or http_request or request or (fluxus and fluxus.request)
if not custom_req then
    return warn("[FleedGuard] CRITICAL: Your executor does not support secure HTTP requests.")
end

-- 2. Anti-Hook & Integrity Validation
local function checkEnvironment()
    if debug and debug.info then
        local src = debug.info(custom_req, "s")
        if src and src ~= "[C]" and not string.find(src, "builtin") then
            -- Request function is hooked by a cracker
            return false
        end
    end
    return true
end

if not checkEnvironment() then
    LocalPlayer:Kick("[FleedGuard Security] Tamper/Hook attempt detected in runtime environment.")
    return
end

-- 3. Hardware Fingerprint Acquisition
local function getHardwareID()
    local hwid = nil
    if gethwid then
        pcall(function() hwid = gethwid() end)
    end
    if not hwid and syn and syn.get_hwid then
        pcall(function() hwid = syn.get_hwid() end)
    end
    if not hwid and identifyexecutor then
        local name = identifyexecutor()
        local rbx_client = game:GetService("RbxAnalyticsService"):GetClientId()
        hwid = name .. "_" .. rbx_client
    end
    if not hwid then
        hwid = game:GetService("RbxAnalyticsService"):GetClientId()
    end
    return tostring(hwid or "UNKNOWN_HWID")
end

local HWID = getHardwareID()
local EXECUTOR = (identifyexecutor and identifyexecutor()) or (syn and "Synapse") or "Universal"

-- 3.5. Roblox Player & Place Telemetry
local rbx_username = (LocalPlayer and LocalPlayer.Name) or "Unknown"
local rbx_user_id = (LocalPlayer and LocalPlayer.UserId) or 0
local rbx_place_id = game.PlaceId or 0
local rbx_job_id = tostring(game.JobId or "")
local rbx_game_name = "Roblox Game"
pcall(function()
    local Market = game:GetService("MarketplaceService")
    local info = Market:GetProductInfo(game.PlaceId)
    if info and info.Name then
        rbx_game_name = tostring(info.Name)
    end
end)

-- 4. Fast Hash & Stream Decryption Helpers (In-Memory Luau Implementation)
local function sha256_hex(str)
    if crypt and crypt.hash then
        return crypt.hash(str, "sha256")
    elseif syn and syn.crypt and syn.crypt.hash then
        return syn.crypt.hash("sha256", str)
    end
    -- Fallback via bit32/bit or basic hashing if crypt lib unavailable
    local h = 0x811c9dc5
    for i = 1, #str do
        h = bit32.bxor(h, string.byte(str, i))
        h = bit32.band(h * 0x01000193, 0xFFFFFFFF)
    end
    return string.format("%08x", h)
end

local function stream_decrypt(cipher_bytes, key_bytes)
    local S = {{}}
    for i = 0, 255 do S[i] = i end
    local j = 0
    for i = 0, 255 do
        j = (j + S[i] + string.byte(key_bytes, (i % #key_bytes) + 1)) % 256
        S[i], S[j] = S[j], S[i]
    end
    local i, j2 = 0, 0
    local out = {{}}
    for idx = 1, #cipher_bytes do
        i = (i + 1) % 256
        j2 = (j2 + S[i]) % 256
        S[i], S[j2] = S[j2], S[i]
        local k = S[(S[i] + S[j2]) % 256]
        out[idx] = string.char(bit32.bxor(cipher_bytes[idx], k))
    end
    return table.concat(out)
end

-- 5. Step 1: Handshake Initialization
local client_challenge = sha256_hex(tostring(os.time()) .. "_" .. tostring(math.random(100000, 999999)))

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
    local err_data = pcall(function() return HttpService:JSONDecode(init_resp.Body) end)
    local msg = (type(err_data) == "table" and err_data.message) or init_resp.Body or "Connection error"
    return warn("[FleedGuard] Authentication Failed: " .. tostring(msg))
end

local init_data = HttpService:JSONDecode(init_resp.Body)
if not init_data.success then
    return warn("[FleedGuard] Access Denied: " .. tostring(init_data.message))
end

-- 6. Step 2: Challenge Verification & Payload Retrieval
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
    local err_msg = "Error " .. tostring(verify_resp.StatusCode)
    pcall(function()
        local decoded = HttpService:JSONDecode(verify_resp.Body)
        if decoded and decoded.message then
            err_msg = tostring(decoded.message)
        end
    end)
    return warn("[FleedGuard] Payload Delivery Error: " .. tostring(err_msg))
end

local verify_data = HttpService:JSONDecode(verify_resp.Body)
if not verify_data.success then
    return warn("[FleedGuard] Execution Error: " .. tostring(verify_data.message))
end

-- 7. In-Memory Decryption & Direct Execution
local raw_b64 = verify_data.payload
local session_key = verify_data.session_key or ""
local is_obfuscated = verify_data.is_obfuscated

local decode_func = (crypt and crypt.base64decode) or (syn and syn.crypt and syn.crypt.base64_decode)
local decoded_str = ""

if decode_func then
    decoded_str = decode_func(raw_b64)
else
    -- Base64 decode fallback
    local b = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    raw_b64 = string.gsub(raw_b64, '[^'..b..'=]', '')
    decoded_str = (raw_b64:gsub('=', ''):gsub('..', function(cc)
        local c = 0
        for i=1, 2 do
            c = c * 64 + (b:find(cc:sub(i, i)) - 1)
        end
        return string.char(bit32.rshift(c, 4), bit32.band(bit32.rshift(c, 2), 0xFF))
    end))
end

local cipher_bytes = {{}}
for i = 1, #decoded_str do
    cipher_bytes[i] = string.byte(decoded_str, i)
end

local key_bytes = session_key .. nonce
local source_code = stream_decrypt(cipher_bytes, key_bytes)

-- 8. Safe Execution without exposing raw string to global hooks
local exec_fn, syntax_err = loadstring(source_code)
if not exec_fn then
    return warn("[FleedGuard] Failed to parse script payload: " .. tostring(syntax_err))
end

-- Scramble memory reference
source_code = nil
verify_data = nil
cipher_bytes = nil

-- Execute securely
print("[FleedGuard] Successfully authenticated " .. tostring(SCRIPT_SLUG) .. "! Launching...")
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

