// tests/e2e.test.js
const assert = require('assert');
const { obfuscate, PRESETS } = require('../src/engine');

function test(name, fn) {
  try {
    fn();
    console.log(`  \x1b[32m✓\x1b[0m ${name}`);
  } catch (err) {
    console.error(`  \x1b[31m✗\x1b[0m ${name}`);
    console.error(err);
    process.exitCode = 1;
  }
}

console.log('\x1b[1m\x1b[36mRunning End-to-End Obfuscator Tests...\x1b[0m');

const SAMPLE_ROBLOX_SCRIPT = `
--!strict
-- High-Performance Roblox Camera & Physics Controller
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local LocalPlayer = Players.LocalPlayer

local function calculateTrajectory(origin: Vector3, velocity: Vector3, gravity: number, t: number): Vector3
    local pos = origin + (velocity * t) + Vector3.new(0, -0.5 * gravity * t^2, 0)
    return pos
end

local function onHeartbeat(deltaTime: number)
    local char = LocalPlayer.Character
    if not char then return end
    
    local hrp = char:FindFirstChild("HumanoidRootPart")
    if hrp then
        local currentSpeed = hrp.AssemblyLinearVelocity.Magnitude
        if currentSpeed > 50 then
            print("Speed threshold exceeded: " .. tostring(currentSpeed))
        end
    end
end

RunService.Heartbeat:Connect(onHeartbeat)
`;

test('Obfuscates with max-performance preset', () => {
  const result = obfuscate(SAMPLE_ROBLOX_SCRIPT, { preset: 'max-performance' });
  assert(result.code.includes('protected by O_bfuscate v2, created by Undix'));
  assert(result.code.includes('--!native'));
  assert(result.code.includes('--!optimize 2'));
  assert(result.stats.securityRating >= 80);
  assert.strictEqual(result.stats.performanceRating, '100% (Zero Overhead)');
});

test('Obfuscates with balanced preset', () => {
  const result = obfuscate(SAMPLE_ROBLOX_SCRIPT, { preset: 'balanced' });
  assert(result.code.includes('protected by O_bfuscate v2, created by Undix'));
  assert(result.stats.securityRating >= 90);
});

test('Obfuscates with ultra-secure preset', () => {
  const result = obfuscate(SAMPLE_ROBLOX_SCRIPT, { preset: 'ultra-secure' });
  assert(result.code.includes('protected by O_bfuscate v2, created by Undix'));
  assert.strictEqual(result.stats.securityRating, 100);
});
