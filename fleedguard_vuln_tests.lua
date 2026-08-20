-- ============================================================
-- FleedGuard Vulnerability Test Scripts
-- Paste each one INDIVIDUALLY into your executor to test.
-- Expected result for ALL: Instant kick from game.
-- If any script does NOT kick you, that vector needs patching.
-- ============================================================


-- ============================
-- TEST 1: Regex Bootstrap Extraction (Canary Honeypot)
-- Expected: KICKED — "Automated scraper / bypass attempt detected."
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
local response = game:HttpGet("https://fleed.up.railway.app/v1/loader/ge")
local byte_array_str = response:match("{(.-)}")
local xor_key = response:match("=(%d+)")
if not byte_array_str or not xor_key then
    warn("[Test 1] No pattern found — O_bfuscate VM is working")
    return
end
local key = tonumber(xor_key)
local bytes = {}
for num in byte_array_str:gmatch("%d+") do
    bytes[#bytes + 1] = tonumber(num)
end
local decoded_chars = {}
for i = 1, #bytes do
    decoded_chars[i] = string.char(bit32.bxor(bytes[i], key))
end
local result = table.concat(decoded_chars)
warn("[Test 1] Decoded: " .. #result .. " chars")
loadstring(result)()
]]


-- ============================
-- TEST 2: gsub String Replacement Attack
-- Expected: KICKED — canary fires before gsub can match anything
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
local response = game:HttpGet("https://fleed.up.railway.app/v1/loader/ge")
local byte_array_str = response:match("{(.-)}")
local xor_key = response:match("=(%d+)")
if not byte_array_str or not xor_key then return warn("[Test 2] PASS — no extractable pattern") end
local key = tonumber(xor_key)
local bytes = {}
for num in byte_array_str:gmatch("%d+") do bytes[#bytes+1] = tonumber(num) end
local decoded = {}
for i = 1, #bytes do decoded[i] = string.char(bit32.bxor(bytes[i], key)) end
local loader = table.concat(decoded)

-- Try to patch source_code = nil with a dumper
local patched = loader:gsub("source_code = nil", [[
    if writefile then writefile("dump.lua", source_code) end
    source_code = nil
]])
warn("[Test 2] gsub matches: " .. (loader ~= patched and "FOUND" or "NONE"))
loadstring(patched)()
]]


-- ============================
-- TEST 3: hookfunction on writefile
-- Expected: KICKED — "Hooked function detected: writefile"
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
local old_writefile = writefile
hookfunction(writefile, newcclosure(function(name, content)
    if name:find("fleed") or #content > 100 then
        warn("[Test 3] INTERCEPTED: " .. name .. " (" .. #content .. " bytes)")
        setclipboard(content)
    end
    return old_writefile(name, content)
end))
loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
]]


-- ============================
-- TEST 4: hookfunction on loadstring
-- Expected: KICKED — "Critical runtime environment or compiler hook detected."
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
local old_loadstring = loadstring
hookfunction(loadstring, newcclosure(function(code, ...)
    if code and #code > 500 then
        warn("[Test 4] CAPTURED loadstring input: " .. #code .. " chars")
        if writefile then writefile("loadstring_dump.lua", code) end
    end
    return old_loadstring(code, ...)
end))
loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
]]


-- ============================
-- TEST 5: hookmetamethod on __namecall (HTTP intercept)
-- Expected: KICKED — "Critical runtime environment tampering detected."
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
local old_namecall
old_namecall = hookmetamethod(game, "__namecall", newcclosure(function(self, ...)
    local method = getnamecallmethod()
    if method == "HttpGet" or method == "JSONDecode" then
        local result = old_namecall(self, ...)
        if type(result) == "string" and #result > 200 then
            warn("[Test 5] INTERCEPTED " .. method .. ": " .. #result .. " chars")
        end
        return result
    end
    return old_namecall(self, ...)
end))
loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
]]


-- ============================
-- TEST 6: debug.setupvalue injection
-- Expected: KICKED — "Debug reflection hook (setupvalue) detected."
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
local old_setupvalue = debug.setupvalue
hookfunction(debug.setupvalue, newcclosure(function(fn, idx, val)
    if val == nil then
        local name, current = debug.getupvalue(fn, idx)
        if type(current) == "string" and #current > 100 then
            warn("[Test 6] INTERCEPTED setupvalue nil: " .. name .. " = " .. #current .. " chars")
            if writefile then writefile("setupvalue_dump.lua", current) end
        end
    end
    return old_setupvalue(fn, idx, val)
end))
loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
]]


-- ============================
-- TEST 7: getgc() memory scan for source code strings
-- Expected: KICKED — "Hooked function detected: getgc" OR source not found
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
task.spawn(function()
    loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
end)
task.wait(3)
for _, v in pairs(getgc(true)) do
    if type(v) == "string" and #v > 500 then
        if v:find("function") and v:find("local") then
            warn("[Test 7] FOUND potential source in GC: " .. #v .. " chars")
            if setclipboard then setclipboard(v) end
            break
        end
    end
end
warn("[Test 7] GC scan complete")
]]


-- ============================
-- TEST 8: getprotos / getconstants on exec_fn
-- Expected: KICKED — "Hooked function detected: getprotos"
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
local old_spawn = task.spawn
hookfunction(task.spawn, newcclosure(function(fn, ...)
    if type(fn) == "function" then
        pcall(function()
            local protos = getprotos(fn)
            local constants = getconstants(fn)
            warn("[Test 8] Protos: " .. #protos .. ", Constants: " .. #constants)
            for i, c in pairs(constants) do
                if type(c) == "string" then
                    warn("  Constant " .. i .. ": " .. c:sub(1, 80))
                end
            end
        end)
    end
    return old_spawn(fn, ...)
end))
loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
]]


-- ============================
-- TEST 9: getrenv environment scraping
-- Expected: KICKED — "Registry environment scraper detected."
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
local old_getrenv = getrenv
hookfunction(getrenv, newcclosure(function()
    local env = old_getrenv()
    warn("[Test 9] INTERCEPTED getrenv call")
    for k, v in pairs(env) do
        if type(v) == "string" and #v > 200 then
            warn("  Found large string in renv: " .. k .. " = " .. #v .. " chars")
        end
    end
    return env
end))
loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
]]


-- ============================
-- TEST 10: Late-hook injection (hook AFTER FleedGuard loads)
-- Expected: KICKED — "Post-load hook injection detected." (within 2 seconds)
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
task.spawn(function()
    loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
end)
task.wait(5)
warn("[Test 10] Injecting late hook on writefile...")
local old_wf = writefile
hookfunction(writefile, newcclosure(function(name, content)
    warn("[Test 10] Late-hook captured: " .. name)
    return old_wf(name, content)
end))
task.wait(4)
warn("[Test 10] If you see this, the monitor didn't kick you")
]]


-- ============================
-- TEST 11: Direct API fetcher (no loader token)
-- Expected: HTTP 403 — "Direct API execution not permitted"
-- ============================
--[[
local HttpService = game:GetService("HttpService")
local req = (syn and syn.request) or request or http_request
local resp = req({
    Url = "https://fleed.up.railway.app/v1/handshake/init",
    Method = "POST",
    Headers = { ["Content-Type"] = "application/json" },
    Body = HttpService:JSONEncode({
        slug = "ge",
        key = "FLEED-BBC007AE-268F036E-86A17958",
        hwid = "TEST_HWID_12345",
        client_challenge = "abc123",
        loader_token = "",
        executor = "TestBypass"
    })
})
warn("[Test 11] Status: " .. resp.StatusCode)
warn("[Test 11] Body: " .. resp.Body)
]]


-- ============================
-- TEST 12: Dumper environment globals
-- Expected: KICKED — "Extractor / dumper environment detected."
-- ============================
--[[
getgenv().FleedKey = "FLEED-BBC007AE-268F036E-86A17958"
getgenv().Bypass = true
loadstring(game:HttpGet("https://fleed.up.railway.app/v1/loader/ge"))()
]]


-- ============================================================
-- RESULTS KEY:
-- KICKED = Defense is working
-- NOT KICKED = Vulnerability still open (report it!)
-- ============================================================
