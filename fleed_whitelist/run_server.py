import os
import sys
import secrets

# Ensure the project root is importable (so `fleed_whitelist.*` resolves).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_THIS_DIR, ".env")


def _load_env_file(path):
    """Minimal .env loader (no external dependency). Parses KEY=VALUE lines and
    only sets vars that are not already present in the real environment."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


def _ensure_local_secret():
    """For local hosting, persist a strong master secret to .env so issued tokens
    stay valid across restarts. Never overwrites an existing secret, and never
    runs in production (there you MUST provide FLEED_MASTER_SECRET yourself)."""
    if os.getenv("FLEED_ENV", "").lower() == "production":
        return
    cur = os.getenv("FLEED_MASTER_SECRET", "").strip()
    if cur and len(cur) >= 32:
        return
    secret = secrets.token_hex(32)
    os.environ["FLEED_MASTER_SECRET"] = secret
    try:
        with open(_ENV_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"\nFLEED_MASTER_SECRET={secret}\n")
        sys.stdout.write(f"  [+] Generated a persistent local master secret -> {_ENV_PATH}\n")
    except OSError:
        sys.stdout.write("  [!] Could not persist master secret; tokens will reset on restart.\n")


# Load .env BEFORE importing the app: crypto_engine reads FLEED_MASTER_SECRET at
# import time, so the environment must be fully prepared first.
_load_env_file(_ENV_PATH)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Local-dev conveniences: only fill in if the operator has not set them.
os.environ.setdefault("FLEED_SERVER_URL", f"http://127.0.0.1:{PORT}")
os.environ.setdefault(
    "FLEED_ALLOWED_ORIGINS",
    f"http://localhost:{PORT},http://127.0.0.1:{PORT}",
)
_ensure_local_secret()

import uvicorn  # noqa: E402  (imported after env prep on purpose)
from fleed_whitelist.server import app  # noqa: E402


def start_server(host: str = HOST, port: int = PORT):
    display_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    env = os.getenv("FLEED_ENV", "development") or "development"
    sys.stdout.write("============================================================\n")
    sys.stdout.write("  [+] FLEEDGUARD WHITELIST & 2FA SECURITY SERVER STARTING\n")
    sys.stdout.write(f"  [+] Binding:         {host}:{port}\n")
    sys.stdout.write(f"  [+] Local Dashboard: http://{display_host}:{port}\n")
    sys.stdout.write(f"  [+] API Docs:        http://{display_host}:{port}/docs\n")
    sys.stdout.write(f"  [+] Environment:     {env}\n")
    sys.stdout.write("============================================================\n")
    sys.stdout.flush()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
