#!/bin/bash

echo "========================================================"
echo "  [+] FLEEDGUARD WHITELIST & DISCORD BOT RUNNER"
echo "========================================================"

# Graceful cleanup on SIGTERM / SIGINT
cleanup() {
    echo "  [-] Shutting down services..."
    if [ -n "$BOT_PID" ]; then
        kill -TERM "$BOT_PID" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup SIGTERM SIGINT SIGQUIT

# 1. Start Discord Bot in background if token exists
if [ -n "$DISCORD_TOKEN" ] && [ "$DISCORD_TOKEN" != "your_discord_bot_token_here" ]; then
    echo "  [+] Starting SWISHBOT Discord Bot in background..."
    python main.py &
    BOT_PID=$!
else
    echo "  [!] No DISCORD_TOKEN configured. Running Whitelist Web API only."
fi

# 2. Run Whitelist Web API in foreground attached to $PORT
echo "  [+] Starting FleedGuard Web Server on port ${PORT:-8000}..."
exec uvicorn fleed_whitelist.server:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"

