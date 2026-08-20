import subprocess
import re
import time
import os
import sys
import threading

URL_FILE = os.path.join(os.path.dirname(__file__), "public_url.txt")

class CloudflareTunnel:
    def __init__(self, local_port: int = 8000):
        self.local_port = local_port
        self.process = None
        self.public_url = None
        self.is_running = False

    def start(self):
        """Starts cloudflared quick tunnel and extracts the HTTPS URL."""
        cmd = ["cloudflared", "tunnel", "--url", f"http://localhost:{self.local_port}"]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            self.is_running = True
            
            # Start background thread to capture URL
            thread = threading.Thread(target=self._monitor_output, daemon=True)
            thread.start()
            
            # Wait up to 15 seconds for URL detection
            for _ in range(30):
                if self.public_url:
                    break
                time.sleep(0.5)

            return self.public_url
        except Exception as e:
            print(f"[CloudflareTunnel] Failed to start cloudflared: {e}")
            return None

    def _monitor_output(self):
        url_regex = re.compile(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com')
        for line in iter(self.process.stdout.readline, ''):
            if not line:
                break
            match = url_regex.search(line)
            if match and not self.public_url:
                self.public_url = match.group(0)
                sys.stdout.write(f"\n=======================================================\n")
                sys.stdout.write(f"  [+] FLEEDGUARD PUBLIC HTTPS TUNNEL ONLINE:\n")
                sys.stdout.write(f"  --> {self.public_url}\n")
                sys.stdout.write(f"  --> Dashboard: {self.public_url}/dashboard\n")
                sys.stdout.write(f"=======================================================\n\n")
                sys.stdout.flush()
                with open(URL_FILE, "w", encoding="utf-8") as f:
                    f.write(self.public_url)

    def stop(self):
        if self.process:
            self.process.terminate()
            self.is_running = False

tunnel = CloudflareTunnel()

if __name__ == "__main__":
    url = tunnel.start()
    if url:
        print(f"[+] Tunnel online at: {url}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            tunnel.stop()
    else:
        print("[-] Could not capture tunnel URL.")
