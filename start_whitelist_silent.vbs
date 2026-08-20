Set WshShell = CreateObject("WScript.Shell")
' Run FleedGuard Whitelist Web Server in background silently
WshShell.Run "python fleed_whitelist/run_server.py", 0, False
