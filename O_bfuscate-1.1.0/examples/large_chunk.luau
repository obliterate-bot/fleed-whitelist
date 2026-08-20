-- Demonstrates automatic helper storage. Real projects need not set this manually.
local function protectedMessage(value)
    return `value={value}`
end

print(protectedMessage(42))
