# FleedGuard — 24/7 Hosting & Deployment Guide

This guide outlines the best, most reliable ways to host the **FleedGuard Whitelist API**, **Web Dashboard**, and **SWISHBOT** 24/7 with HTTPS and custom domain support.

---

## 🏆 Recommended Hosting Options

| Method | Cost | Best For | SSL / HTTPS | Uptime |
| :--- | :--- | :--- | :--- | :--- |
| **1. Railway / Render / Fly.io** | Free / $5/mo | Simplest 1-click cloud deploy from GitHub | ✅ Automatic | 99.99% |
| **2. Linux VPS (Docker Compose)** | $3–$5/mo | Complete control, maximum speed & privacy | ✅ Automatic via Certbot | 99.99% |
| **3. Windows Host + Cloudflare Tunnel** | 100% Free | Running on your own PC or Windows VPS | ✅ Cloudflare SSL | 24/7 as long as PC is on |

---

## Option 1: Deploying to Railway or Render (Easiest Cloud Deploy)

### Deploying via GitHub to Railway (Recommended)
1. Push this repository to GitHub.
2. Go to [Railway.app](https://railway.app) and click **New Project** → **Deploy from GitHub repo**.
3. Railway will detect the `Procfile` and `Dockerfile`.
4. In **Variables**, add:
   * `DISCORD_TOKEN`: Your Discord Bot Token
   * `PORT`: `8000`
   * `FLEED_MASTER_SECRET`: Any 32-character random string
5. Under **Settings** → **Networking**, click **Generate Domain** (or attach your custom domain like `auth.fleed.bot`).
6. Your whitelist API is now live 24/7 on `https://your-project.up.railway.app`!

---

## Option 2: Deploying to a Linux VPS via Docker (Hetzner / DigitalOcean / Linode)

1. Connect to your VPS via SSH:
   ```bash
   ssh root@your_vps_ip
   ```
2. Clone your repo or copy the project files to the VPS:
   ```bash
   git clone <your_repo_url> fleed
   cd fleed
   ```
3. Create your `.env` file:
   ```bash
   nano .env
   ```
   Add your `DISCORD_TOKEN` and secrets.
4. Start everything in the background using Docker Compose:
   ```bash
   docker compose up -d --build
   ```
5. Check status:
   ```bash
   docker compose ps
   docker compose logs -f
   ```

---

## Option 3: Free 24/7 Cloudflare Tunnel (Zero-Port-Forwarding)

If you are running the server on your Windows PC or a Windows VPS and want a **free, public `https://...` URL** with DDoS protection:

1. Download [cloudflared for Windows](https://github.com/cloudflare/cloudflared/releases/latest).
2. Open terminal and run:
   ```powershell
   cloudflared tunnel --url http://localhost:8000
   ```
3. Cloudflare will give you a free secure HTTPS URL (e.g. `https://random-words.trycloudflare.com` or your own connected domain).
4. Any Roblox executor in the world can now connect to your whitelist over encrypted HTTPS!

---

## 🚀 Running Locally on Windows

* **To run all services with live console windows:**
  Double-click `start_all_services.bat`
* **To run the Whitelist server silently in the background:**
  Double-click `start_whitelist_silent.vbs`
