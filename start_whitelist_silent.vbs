Set WshShell = CreateObject("WScript.Shell")
' Run FleedGuard Whitelist Web Server silently
WshShell.Run "python fleed_whitelist/run_server.py", 0, False
' Run Cloudflare Tunnel via supervisor (automatically writes URL to fleed_whitelist/public_url.txt)
WshShell.Run "python fleed_whitelist/tunnel_service.py", 0, False

