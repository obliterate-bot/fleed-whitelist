Set WshShell = CreateObject("WScript.Shell")
' Run FleedGuard Whitelist Web Server silently
WshShell.Run "python fleed_whitelist/run_server.py", 0, False
' Run Cloudflare Tunnel silently (writes public URL to fleed_whitelist/public_url.txt)
WshShell.Run "cloudflared tunnel --url http://localhost:8000", 0, False
