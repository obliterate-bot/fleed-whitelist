--!strict
-- O_bfuscate 1.1 identity macro SDK. These helpers are no-ops before protection.

local function OBF_ENCSTR<T>(value: T): T
    return value
end

local function OBF_ENCNUM<T>(value: T): T
    return value
end

local function OBF_ENCFUNC<T>(fn: T, _keyId: string?): T
    return fn
end

local function OBF_VM<T>(fn: T): T
    return fn
end

local function OBF_LIGHT<T>(fn: T): T
    return fn
end

local function OBF_JIT<T>(fn: T): T
    return fn
end

local function OBF_JIT_MAX<T>(fn: T): T
    return fn
end

local function OBF_HOT<T>(fn: T): T
    return fn
end

local function OBF_NO_VM<T>(fn: T): T
    return fn
end

local function OBF_NO_UPVALUES<T>(fn: T): T
    return fn
end

-- Optional compatibility aliases for projects already using wYnFuscate macros.
local WYNF_OBFUSCATED = false
local function WYNF_JIT<T>(fn: T): T return fn end
local function WYNF_JIT_MAX<T>(fn: T): T return fn end
local function WYNF_INLINE<T>(fn: T): T return fn end
local function WYNF_NO_VIRTUALIZE<T>(fn: T): T return fn end

return {
    OBF_ENCSTR = OBF_ENCSTR,
    OBF_ENCNUM = OBF_ENCNUM,
    OBF_ENCFUNC = OBF_ENCFUNC,
    OBF_VM = OBF_VM,
    OBF_LIGHT = OBF_LIGHT,
    OBF_JIT = OBF_JIT,
    OBF_JIT_MAX = OBF_JIT_MAX,
    OBF_HOT = OBF_HOT,
    OBF_NO_VM = OBF_NO_VM,
    OBF_NO_UPVALUES = OBF_NO_UPVALUES,
    WYNF_OBFUSCATED = WYNF_OBFUSCATED,
    WYNF_JIT = WYNF_JIT,
    WYNF_JIT_MAX = WYNF_JIT_MAX,
    WYNF_INLINE = WYNF_INLINE,
    WYNF_NO_VIRTUALIZE = WYNF_NO_VIRTUALIZE,
}
