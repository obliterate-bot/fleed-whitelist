// server.js
// High-Performance HTTP Server for O_bfuscate V2 Web Application

const http = require('http');
const fs = require('fs');
const path = require('path');
const { obfuscate, PRESETS } = require('./src/engine');

const PORT = process.env.PORT || 3000;
const PUBLIC_DIR = path.join(__dirname, 'public');

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

const SAMPLE_SCRIPTS = {
  raycast_aimbot: {
    title: 'Roblox Fast Raycast & Prediction Engine',
    code: `--!strict
-- High-Performance Roblox Raycasting & Target Prediction Engine
local Workspace = game:GetService("Workspace")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local LocalPlayer = Players.LocalPlayer
local Camera = Workspace.CurrentCamera

local PREDICTION_GRAVITY = 196.2
local BULLET_SPEED = 950.0

local function getTargetVelocity(targetPart: BasePart): Vector3
    return targetPart.AssemblyLinearVelocity
end

local function solveBallisticLead(origin: Vector3, targetPos: Vector3, targetVel: Vector3, bulletSpeed: number): Vector3
    local delta = targetPos - origin
    local distance = delta.Magnitude
    local timeToHit = distance / bulletSpeed
    local predictedPos = targetPos + (targetVel * timeToHit) + Vector3.new(0, 0.5 * PREDICTION_GRAVITY * (timeToHit ^ 2), 0)
    return predictedPos
end

local function scanNearestTarget(maxDistance: number): BasePart?
    local nearestDist = maxDistance
    local bestTarget: BasePart? = nil
    
    for _, player in ipairs(Players:GetPlayers()) do
        if player ~= LocalPlayer and player.Character then
            local root = player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
            local humanoid = player.Character:FindFirstChild("Humanoid") :: Humanoid?
            if root and humanoid and humanoid.Health > 0 then
                local dist = (root.Position - Camera.CFrame.Position).Magnitude
                if dist < nearestDist then
                    nearestDist = dist
                    bestTarget = root
                end
            end
        end
    end
    return bestTarget
end

return {
    solveLead = solveBallisticLead,
    scanTarget = scanNearestTarget
}`
  },
  buffer_crypto: {
    title: 'Zero-Allocation Native Buffer Data Stream',
    code: `--!native
--!optimize 2
-- Zero-Allocation High-Throughput Luau Buffer Packet Serializer
local packetBuffer = buffer.create(1024)
local writeOffset = 0

local function writeHeader(packetId: number, sequence: number)
    buffer.writeu8(packetBuffer, writeOffset, packetId)
    writeOffset += 1
    buffer.writeu16(packetBuffer, writeOffset, sequence)
    writeOffset += 2
end

local function writeFloatVector(x: number, y: number, z: number)
    buffer.writef32(packetBuffer, writeOffset, x)
    writeOffset += 4
    buffer.writef32(packetBuffer, writeOffset, y)
    writeOffset += 4
    buffer.writef32(packetBuffer, writeOffset, z)
    writeOffset += 4
end

local function finalizePacket(): string
    local result = buffer.readstring(packetBuffer, 0, writeOffset)
    writeOffset = 0
    return result
end

writeHeader(0x42, 1337)
writeFloatVector(12.5, -45.2, 108.9)
local payload = finalizePacket()
print("Serialized Buffer Payload Length:", #payload)`
  },
  remote_security: {
    title: 'RemoteEvent Anti-Exploit Handshake & Token Gate',
    code: `--!strict
-- Secure Network Handshake & Replay-Attack Prevention
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local HttpService = game:GetService("HttpService")

local Remote = Instance.new("RemoteFunction")
Remote.Name = "SecureHandshake"
Remote.Parent = ReplicatedStorage

local activeTokens = {}
local SALT = 0x5a3f

local function generateSessionToken(player: Player): string
    local seed = os.time() + player.UserId + SALT
    local token = HttpService:GenerateGUID(false)
    activeTokens[player.UserId] = {
        token = token,
        timestamp = os.clock(),
        nonce = seed
    }
    return token
end

local function verifyHandshake(player: Player, providedToken: string): boolean
    local session = activeTokens[player.UserId]
    if not session then return false end
    if os.clock() - session.timestamp > 30 then
        activeTokens[player.UserId] = nil
        return false
    end
    return session.token == providedToken
end

Remote.OnServerInvoke = function(player, action, token)
    if action == "REQUEST_TOKEN" then
        return generateSessionToken(player)
    elseif action == "VALIDATE" then
        return verifyHandshake(player, token)
    end
    return false
end`
  }
};

const server = http.createServer((req, res) => {
  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = parsedUrl.pathname;

  // Enable CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // API: Obfuscate
  if (pathname === '/api/obfuscate' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => {
      body += chunk;
      if (body.length > 5 * 1024 * 1024) { // 5MB limit
        res.writeHead(413, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Payload too large' }));
        req.destroy();
      }
    });

    req.on('end', () => {
      try {
        const payload = JSON.parse(body);
        const sourceCode = payload.code || '';
        const options = payload.options || {};

        if (!sourceCode.trim()) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Source code is required' }));
          return;
        }

        const result = obfuscate(sourceCode, options);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: true, ...result }));
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: false, error: err.message, stack: err.stack }));
      }
    });
    return;
  }

  // API: Get Samples & Presets
  if (pathname === '/api/info' && req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      presets: PRESETS,
      samples: SAMPLE_SCRIPTS,
      watermark: 'protected by O_bfuscate v2, created by Undix'
    }));
    return;
  }

  // Static file serving
  let filePath = path.join(PUBLIC_DIR, pathname === '/' ? 'index.html' : pathname);
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('Forbidden');
    return;
  }

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      filePath = path.join(PUBLIC_DIR, 'index.html');
    }

    const ext = path.extname(filePath);
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    fs.readFile(filePath, (readErr, content) => {
      if (readErr) {
        res.writeHead(500, { 'Content-Type': 'text/plain' });
        res.end('Internal Server Error');
      } else {
        res.writeHead(200, { 'Content-Type': contentType });
        res.end(content);
      }
    });
  });
});

server.listen(PORT, () => {
  console.log(`\x1b[36m=========================================================\x1b[0m`);
  console.log(`\x1b[1m\x1b[35m  O_bfuscate V2 Web Dashboard\x1b[0m`);
  console.log(`  \x1b[32mRunning at:\x1b[0m http://localhost:${PORT}`);
  console.log(`  \x1b[90mProtected by O_bfuscate v2, created by Undix\x1b[0m`);
  console.log(`\x1b[36m=========================================================\x1b[0m`);
});
