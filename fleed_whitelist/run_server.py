import uvicorn
import os
import sys

# Ensure current project directory is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fleed_whitelist.server import app

def start_server(host: str = "0.0.0.0", port: int = 8000):
    sys.stdout.write("============================================================\n")
    sys.stdout.write("  [+] FLEEDGUARD WHITELIST & 2FA SECURITY SERVER STARTING\n")
    sys.stdout.write(f"  [+] Local Dashboard: http://localhost:{port}\n")
    sys.stdout.write(f"  [+] API Docs:        http://localhost:{port}/docs\n")
    sys.stdout.write("============================================================\n")
    sys.stdout.flush()
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    start_server(port=port)
