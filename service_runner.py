import subprocess
import sys
import time
import os
import datetime
import threading
import re

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable
LOG_FILE = os.path.join(BOT_DIR, "service.log")
URL_FILE = os.path.join(BOT_DIR, "fleed_whitelist", "public_url.txt")

def log(msg):
    ts = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{ts} {msg}\n"
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

def run_whitelist_server():
    """Runs the FastAPI Whitelist Backend in a persistent supervisor loop."""
    while True:
        try:
            log("[server] Starting FleedGuard Whitelist Web API on port 8000...")
            proc = subprocess.Popen(
                [PYTHON_EXE, "-u", "fleed_whitelist/run_server.py"],
                cwd=BOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            for line in iter(proc.stdout.readline, ''):
                if line:
                    log(f"[whitelist-api] {line.strip()}")
            proc.stdout.close()
            ret = proc.wait()
            log(f"[server] Whitelist API exited with code {ret}. Restarting in 2s...")
        except Exception as e:
            log(f"[server] Error: {e}")
        time.sleep(2)

def run_cloudflare_tunnel():
    """Runs Cloudflare Quick Tunnel for continuous 24/7 HTTPS global access."""
    while True:
        try:
            log("[tunnel] Launching Cloudflare 24/7 Public HTTPS Tunnel...")
            proc = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
                cwd=BOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            url_regex = re.compile(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com')
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    break
                match = url_regex.search(line)
                if match:
                    pub_url = match.group(0)
                    log(f"=======================================================")
                    log(f"  [+] FLEEDGUARD GLOBAL HTTPS DOMAIN ACTIVE:")
                    log(f"  --> {pub_url}")
                    log(f"  --> Dashboard: {pub_url}/dashboard")
                    log(f"=======================================================")
                    try:
                        with open(URL_FILE, "w", encoding="utf-8") as f:
                            f.write(pub_url)
                    except Exception:
                        pass
            proc.stdout.close()
            ret = proc.wait()
            log(f"[tunnel] Cloudflare tunnel stopped with code {ret}. Reconnecting in 3s...")
        except Exception as e:
            log(f"[tunnel] Error: {e}. Retrying in 5s...")
            time.sleep(5)
        time.sleep(3)

def run_discord_bot():
    """Runs SWISHBOT Discord Bot in a persistent supervisor loop."""
    while True:
        try:
            log("[bot] Starting SWISHBOT main.py...")
            proc = subprocess.Popen(
                [PYTHON_EXE, "-u", "main.py"],
                cwd=BOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            for line in iter(proc.stdout.readline, ''):
                if line:
                    log(f"[bot] {line.strip()}")
            proc.stdout.close()
            ret = proc.wait()
            if ret in (0, -1073741510, 3221225786, -1073740940, 3221226356, 1073807364):
                log(f"[bot] Stopped intentionally with code {ret}.")
                break
            log(f"[bot] Bot exited with code {ret}. Restarting in 3s...")
        except Exception as e:
            log(f"[bot] Error: {e}")
        time.sleep(3)

def main():
    log("========================================================")
    log("  [+] FLEEDGUARD 24/7 ALL-IN-ONE HOSTING SUPERVISOR")
    log("========================================================")

    # 1. Start Whitelist API Thread
    t_server = threading.Thread(target=run_whitelist_server, daemon=True)
    t_server.start()

    # 2. Start Cloudflare Tunnel Thread
    t_tunnel = threading.Thread(target=run_cloudflare_tunnel, daemon=True)
    t_tunnel.start()

    # Wait 2 seconds for server and tunnel initialization
    time.sleep(2)

    # 3. Run Discord Bot in main loop
    run_discord_bot()

if __name__ == "__main__":
    main()
