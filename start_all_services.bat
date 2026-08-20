@echo off
title FleedGuard 24/7 Whitelist & Bot Services
echo ========================================================
echo   🛡️ FLEEDGUARD WHITELIST, CLOUDFLARE TUNNEL & BOT RUNNER
echo ========================================================
echo.
echo 1. Starting FleedGuard Whitelist Web Server on http://localhost:8000 ...
start "FleedGuard Web API" cmd /k "python fleed_whitelist/run_server.py"

timeout /t 2 /nobreak >nul

echo 2. Starting Cloudflare Public HTTPS Tunnel ...
start "FleedGuard Public Tunnel" cmd /k "cloudflared tunnel --url http://localhost:8000"

echo 3. Starting SWISHBOT Discord Bot ...
start "Fleed Discord Bot" cmd /k "python main.py"

echo.
echo [✓] All 3 services launched successfully!
echo Check the 'FleedGuard Public Tunnel' window for your live HTTPS URL.
pause
