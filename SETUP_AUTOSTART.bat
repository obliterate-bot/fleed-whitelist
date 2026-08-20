@echo off
title FleedGuard 24/7 Auto-Start Setup
echo =============================================================
echo   🛡️ FLEEDGUARD 24/7 ZERO-EFFORT HOSTING SETUP
echo =============================================================
echo.
echo Installing background 24/7 supervisor to Windows Startup...

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_VBS=%STARTUP_FOLDER%\FleedGuard_Supervisor.vbs"
set "PROJECT_DIR=%~dp0"

(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.CurrentDirectory = "%PROJECT_DIR:~0,-1%"
echo WshShell.Run "python service_runner.py", 0, False
) > "%SHORTCUT_VBS%"

echo.
echo [✓] SUCCESS! FleedGuard is now configured to run 24/7 automatically.
echo Whenever your PC turns on, the Whitelist API, Cloudflare HTTPS Tunnel,
echo and Discord Bot will launch silently in the background.
echo.
echo Launching services right now...
wscript "%SHORTCUT_VBS%"
echo [✓] Services are now running live in the background!
pause
