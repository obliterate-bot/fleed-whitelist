# Hosting FleedGuard locally

This backend runs entirely on your own machine. No cloud account required.

## 1. Install dependencies

```bash
cd fleed_whitelist        # the folder containing run_server.py
python -m pip install -r requirements.txt
```

## 2. (Optional) configure

Copy the example env file and tweak if you want. This step is optional for local
dev — sensible defaults are applied automatically.

```bash
cp .env.example .env
```

- Leave `FLEED_MASTER_SECRET` blank for local dev; a strong one is generated and
  saved back into `.env` on first run, so your tokens stay valid across restarts.
- Set `FLEED_SERVER_URL` to the address the **machine running Roblox** will use
  to reach this server (see below).

## 3. Run

```bash
python run_server.py
# or, from the project root:
python -m fleed_whitelist.run_server
```

You'll see:

```
  [+] Local Dashboard: http://127.0.0.1:8000
  [+] API Docs:        http://127.0.0.1:8000/docs
```

Open the dashboard, create a script + license key, then copy the one-liner loader.

## Reaching the server from Roblox

The loader talks to whatever URL you fetched it from, so fetch it from a URL the
game's machine can actually reach:

| Setup | Use this base URL |
|-------|-------------------|
| Executor on the **same PC** as the server | `http://127.0.0.1:8000` |
| Executor on **another device on your LAN** | `http://<server-LAN-IP>:8000` (run with `HOST=0.0.0.0`, allow the port through your firewall) |
| Need a **public HTTPS** URL | put a tunnel (e.g. Cloudflare Tunnel / ngrok) in front and set `FLEED_SERVER_URL` to the tunnel URL |

> Most executors allow HTTP requests to localhost / LAN IPs. If yours blocks
> plain HTTP, use a tunnel that provides HTTPS.

## Environment variables

See `.env.example` for the full list (`FLEED_MASTER_SECRET`, `FLEED_ENV`,
`FLEED_SERVER_URL`, `HOST`, `PORT`, `FLEED_ALLOWED_ORIGINS`, `FLEED_WHITELIST_DB`).

## Going to production

Set `FLEED_ENV=production` and provide your own strong `FLEED_MASTER_SECRET`
(>= 32 chars). In production the server refuses to start without one, on purpose.
