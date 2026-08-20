#!/bin/bash
set -e

echo "========================================================"
echo "  [+] FLEEDGUARD WHITELIST & DISCORD BOT RUNNER"
echo "========================================================"

# Start Whitelist Web API in background
uvicorn fleed_whitelist.server:app --host 0.0.0.0 --port ${PORT:-8000} &
SERVER_PID=$!

# Wait for server initialization
sleep 2

# Start Discord Bot if DISCORD_TOKEN is present
if [ -n "$DISCORD_TOKEN" ] && [ "$DISCORD_TOKEN" != "your_discord_bot_token_here" ]; then
    echo "  [+] Starting SWISHBOT Discord Bot..."
    python main.py &
    BOT_PID=$!
    wait -n || wait
else
    echo "  [!] No DISCORD_TOKEN found. Running Whitelist Web API only."
    wait $SERVER_PID
fi
