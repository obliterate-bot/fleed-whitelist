@echo off
title FleedGuard Whitelist & Cloudflare Tunnel
echo =============================================================
echo   🛡️ FLEEDGUARD WHITELIST API ^& CLOUDFLARE PUBLIC TUNNEL
echo =============================================================
echo.
echo 1. Starting Whitelist Web Server on http://localhost:8000 ...
start "FleedGuard Web API" cmd /k "python fleed_whitelist/run_server.py"

timeout /t 2 /nobreak >nul

echo 2. Starting Cloudflare Public HTTPS Tunnel ...
start "FleedGuard Public Tunnel" cmd /k "cloudflared tunnel --url http://localhost:8000"

echo.
echo [✓] Whitelist API and Cloudflare Tunnel launched!
echo Look at the 'FleedGuard Public Tunnel' window for your public HTTPS URL.
pause
