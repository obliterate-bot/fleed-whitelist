@echo off
title FleedGuard 24/7 Whitelist & Bot Services
echo ========================================================
echo   🛡️ FLEEDGUARD WHITELIST & DISCORD BOT RUNNER
echo ========================================================
echo.
echo Starting FleedGuard Whitelist Web Server on http://localhost:8000 ...
start "FleedGuard Web API" cmd /k "python fleed_whitelist/run_server.py"

echo Starting SWISHBOT Discord Bot ...
start "Fleed Discord Bot" cmd /k "python main.py"

echo.
echo All services launched! Keep this window open or close it safely.
