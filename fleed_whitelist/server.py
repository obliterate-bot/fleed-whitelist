import os
import json
import time
import secrets
import asyncio
import base64
import urllib.request
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status, Header, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import db
from .crypto_engine import crypto_engine
from .loader_generator import loader_generator
from .feature_analyzer import feature_analyzer

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
UPLOADS_AVATAR_DIR = os.path.join(STATIC_DIR, "uploads", "avatars")

SERVER_START_TIME = time.time()

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(UPLOADS_AVATAR_DIR, exist_ok=True)

# Modern FastAPI Lifespan Handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    # Create default demo/admin account if empty
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT COUNT(*) as cnt FROM users")
        row = await cursor.fetchone()
        if row and row["cnt"] == 0:
            pw_hash, salt = crypto_engine.hash_password("FleedAdmin2026!")
            api_key = f"fg_live_{secrets.token_hex(20)}"
            now_iso = datetime.now(timezone.utc).isoformat()
            await conn.execute("""
                INSERT INTO users (username, email, password_hash, salt, api_key, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("admin", "admin@fleed.bot", pw_hash, salt, api_key, "admin", now_iso))
            await conn.commit()

        # Auto-heal past executions where place_id > 0 and game_name was 'Roblox Game'
        try:
            cur_places = await conn.execute("SELECT DISTINCT place_id FROM execution_logs WHERE (game_name = 'Roblox Game' OR game_name = 'Unknown' OR game_name IS NULL OR game_name = 'Roblox Experience') AND place_id > 0")
            place_rows = await cur_places.fetchall()
            for pr in place_rows:
                pid = pr["place_id"]
                if pid:
                    asyncio.create_task(background_resolve_and_update_place(pid))
        except Exception:
            pass
    yield

app = FastAPI(
    title="FleedGuard Whitelist & Security API",
    version="2.0.0",
    description="Enterprise-grade Roblox script whitelisting and protection service.",
    lifespan=lifespan
)

# CORS middleware for the web dashboard only.
# SECURITY: allow_origins=["*"] together with allow_credentials=True is both
# invalid per the CORS spec and unsafe (it would let any website make
# authenticated requests with the user's cookies). The executor handshake API is
# server-to-server (no browser origin), so it needs no CORS. We restrict browser
# origins to the dashboard host(s) configured via FLEED_ALLOWED_ORIGINS.
_allowed_origins = [
    o.strip()
    for o in os.getenv("FLEED_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,  # empty list = no cross-origin browser access
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ----------------- Dependency: Auth Verification -----------------
async def get_current_user(request: Request) -> Dict:
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif "fleed_token" in request.cookies:
        token = request.cookies.get("fleed_token")

    if not token:
        # Check for direct API key in header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            async with db.get_db() as conn:
                cursor = await conn.execute("SELECT * FROM users WHERE api_key = ? AND is_active = 1", (api_key,))
                user = await cursor.fetchone()
                if user:
                    return dict(user)

        raise HTTPException(status_code=401, detail="Authentication required")

    payload = crypto_engine.verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (payload["sub"],))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return dict(user)

# ----------------- Pydantic Request Models -----------------
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str
    two_factor_code: Optional[str] = None

class Enable2FARequest(BaseModel):
    code: str

class ScriptCreateRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = ""
    version: Optional[str] = "1.0.0"
    raw_source: str
    is_obfuscated_mode: int = 1 # 1=Protected, 0=Unobfuscated
    discord_webhook: Optional[str] = ""

class ScriptUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    raw_source: Optional[str] = None
    is_obfuscated_mode: Optional[int] = None
    killswitch_active: Optional[int] = None
    killswitch_reason: Optional[str] = None
    discord_webhook: Optional[str] = None

class LicenseBulkCreateRequest(BaseModel):
    script_id: int
    count: int = 1
    duration_days: Optional[int] = None # None = lifetime
    max_executions: int = -1 # -1 = infinite
    note: Optional[str] = ""

class LicenseUpdateRequest(BaseModel):
    note: Optional[str] = None
    is_banned: Optional[int] = None
    ban_reason: Optional[str] = None
    expires_at: Optional[str] = None

class LicenseImportItem(BaseModel):
    license_key: str
    note: Optional[str] = ""
    discord_id: Optional[str] = None
    duration_days: Optional[int] = None
    max_executions: Optional[int] = -1

class LicenseBulkImportRequest(BaseModel):
    script_id: int
    keys: List[LicenseImportItem]

class LicenseBulkActionRequest(BaseModel):
    action: str # 'copy', 'resethwid', 'ban', 'unban', 'delete', 'extend'
    license_ids: List[int]
    extend_days: Optional[int] = 30
    ban_reason: Optional[str] = "Bulk banned by administrator"

class LicenseExtendRequest(BaseModel):
    days: int = 30 # 0 for lifetime

class BlacklistAddRequest(BaseModel):
    target_type: str # 'HWID' or 'IP'
    target_value: str
    reason: Optional[str] = "Manual security ban"

class SimulateHandshakeRequest(BaseModel):
    slug: str
    key: str
    hwid: Optional[str] = "SIMULATOR_HWID_ABC123"

class StaffManagerAddRequest(BaseModel):
    discord_user_id: str
    script_slug: Optional[str] = "all"
    is_role: Optional[int] = 0
    quota_limit: Optional[int] = -1
    note: Optional[str] = ""

class RemoteKickRequest(BaseModel):
    target_type: str = "KEY" # KEY, HWID, USER_ID, USERNAME
    target_value: str
    reason: Optional[str] = "Terminated by developer"

class PublicRedeemRequest(BaseModel):
    license_key: str
    discord_id: Optional[str] = None

class PublicResetHwidRequest(BaseModel):
    license_key: str
    discord_id: str

class AnnouncementCreateRequest(BaseModel):
    message: str
    banner_type: Optional[str] = "INFO" # 'INFO', 'UPDATE', 'WARNING', 'MAINTENANCE'
    is_active: Optional[int] = 1

class FeatureFlagCreateRequest(BaseModel):
    flag_name: str
    display_name: Optional[str] = None
    category: Optional[str] = "General Utilities"
    flag_type: Optional[str] = "BOOLEAN" # 'BOOLEAN', 'STRING', 'NUMBER', 'JSON'
    flag_value: str = "true"
    is_enabled: Optional[int] = 1
    source_type: Optional[str] = "Manual"
    line_number: Optional[int] = 0

class FeatureFlagToggleAllRequest(BaseModel):
    action: str = "enable" # "enable" or "disable"
    category: Optional[str] = None

class RemoteExecRequest(BaseModel):
    script_slug: Optional[str] = None
    target_type: str = "ALL" # "ALL", "KEY", "PLAYER", "SESSION"
    target_value: Optional[str] = None
    luau_code: str
    description: Optional[str] = "Live Remote Console Exec"
    ttl_seconds: Optional[int] = 300

class ScriptVersionCreateRequest(BaseModel):
    version_tag: str
    changelog: Optional[str] = ""
    raw_source: str

class DiscordWebhookCreateRequest(BaseModel):
    script_id: Optional[int] = None
    event_type: str = "WHITELIST_ADDED" # 'WHITELIST_ADDED', 'THREAT_DETECTED', 'HWID_RESET', 'EXECUTION_SPIKE'
    webhook_url: str
    is_enabled: Optional[int] = 1

class TestWebhookRequest(BaseModel):
    webhook_url: Optional[str] = None

class WatermarkLookupRequest(BaseModel):
    watermark_or_source: str

class BanLeakerRequest(BaseModel):
    license_id: int
    reason: Optional[str] = "Banned via Forensic Watermark Trace"

class KickPlayerRequest(BaseModel):
    target_type: Optional[str] = None
    target_value: Optional[str] = None
    license_key: Optional[str] = None
    hwid: Optional[str] = None
    roblox_user_id: Optional[int] = None
    roblox_username: Optional[str] = None
    reason: Optional[str] = "Terminated by developer"

class BroadcastSendRequest(BaseModel):
    target_type: Optional[str] = "GLOBAL" # 'GLOBAL', 'SCRIPT', 'KEY', 'USERNAME'
    target_value: Optional[str] = ""
    script_id: Optional[int] = None
    title: Optional[str] = "FleedGuard Announcement"
    message: str
    banner_type: Optional[str] = "INFO" # 'INFO', 'UPDATE', 'WARNING', 'MAINTENANCE', 'EMERGENCY'
    duration: Optional[int] = 10
    play_sound: Optional[int] = 1
    expires_minutes: Optional[int] = 60




async def send_discord_security_alert(webhook_url: str, title: str, description: str, fields: List[Dict], color: int = 0xEF4444):
    """Sends a rich, non-blocking Discord security alert embed."""
    if not webhook_url or not str(webhook_url).startswith("https://discord.com/api/webhooks/"):
        return
    try:
        embed = {
            "title": f"FleedGuard Security Alert: {title}",
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {"text": "FleedGuard Automated Anomaly Defense • 2026"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json={"embeds": [embed]}, timeout=aiohttp.ClientTimeout(total=4))
    except Exception:
        pass

async def check_and_enforce_anomalies(conn, script: Dict, license_row: Dict, roblox_username: Optional[str], roblox_user_id: Optional[int], client_ip: str, executor: str, place_id: Optional[int], job_id: Optional[str], game_name: Optional[str]) -> Optional[str]:
    """
    Evaluates multi-account and multi-IP sprawl in rolling windows.
    Returns error message if anomaly triggered and key auto-banned; otherwise None.
    """
    clean_key = license_row["license_key"].upper()
    now_iso = datetime.now(timezone.utc).isoformat()
    uid = int(roblox_user_id or 0)
    
    # 1. Multi-Account Sprawl Check (rolling 24h)
    if uid > 0:
        cursor = await conn.execute("""
            SELECT COUNT(DISTINCT roblox_user_id) as distinct_users,
                   GROUP_CONCAT(DISTINCT roblox_username) as usernames
            FROM execution_logs
            WHERE UPPER(license_key) = ?
              AND roblox_user_id > 0
              AND roblox_user_id != ?
              AND timestamp >= datetime('now', '-24 hours')
        """, (clean_key, uid))
        user_stats = await cursor.fetchone()
        prior_users = user_stats["distinct_users"] if user_stats else 0
        if prior_users >= 2:  # current + 2 prior = 3 distinct accounts
            all_users = (user_stats["usernames"] or "") + f", {roblox_username or uid}"
            ban_reason = f"Automated Leak Shield: Key shared across {prior_users + 1} distinct Roblox accounts ({all_users.strip(', ')})"
            await conn.execute("UPDATE licenses SET is_banned = 1, ban_reason = ? WHERE id = ?", (ban_reason, license_row["id"]))
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'LEAK_AUTO_BANNED', ?, ?)
            """, (script["id"], license_row["id"], clean_key, license_row["hwid"], client_ip, executor, roblox_username, uid, place_id, job_id, game_name, ban_reason, now_iso))
            await conn.commit()
            
            # Send Discord Alert Webhook
            webhook_url = script["discord_webhook"] if "discord_webhook" in script.keys() else None
            if webhook_url:
                fields = [
                    {"name": "License Key", "value": f"`{clean_key}`", "inline": True},
                    {"name": "Script Hub", "value": f"{script['name']} (`{script['slug']}`)", "inline": True},
                    {"name": "Trigger Reason", "value": "Multi-Account Distribution (>2 accounts in 24h)", "inline": False},
                    {"name": "Roblox Accounts Detected", "value": f"```{all_users.strip(', ')}```", "inline": False},
                    {"name": "Latest IP", "value": f"`{client_ip}`", "inline": True},
                    {"name": "Action Taken", "value": "**Key Automatically Banned & Revoked**", "inline": False}
                ]
                await send_discord_security_alert(webhook_url, "Script Leak Detected (Auto-Banned)", f"License key `{clean_key}` has been automatically banned due to multi-user distribution.", fields, 0xEF4444)
            
            return f"Security Violation: License revoked. Multi-account key sharing detected."

    # 2. Multi-IP Sprawl Check (rolling 2h)
    cursor = await conn.execute("""
        SELECT COUNT(DISTINCT ip_address) as distinct_ips,
               GROUP_CONCAT(DISTINCT ip_address) as ips
        FROM execution_logs
        WHERE UPPER(license_key) = ?
          AND ip_address != ?
          AND timestamp >= datetime('now', '-2 hours')
    """, (clean_key, client_ip))
    ip_stats = await cursor.fetchone()
    prior_ips = ip_stats["distinct_ips"] if ip_stats else 0
    if prior_ips >= 3:  # current + 3 prior = 4 distinct IPs in 2 hours
        all_ips = (ip_stats["ips"] or "") + f", {client_ip}"
        ban_reason = f"Automated Leak Shield: Key accessed from {prior_ips + 1} distinct IPs in 2h ({all_ips.strip(', ')})"
        await conn.execute("UPDATE licenses SET is_banned = 1, ban_reason = ? WHERE id = ?", (ban_reason, license_row["id"]))
        await conn.execute("""
            INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'LEAK_AUTO_BANNED', ?, ?)
        """, (script["id"], license_row["id"], clean_key, license_row["hwid"], client_ip, executor, roblox_username, uid, place_id, job_id, game_name, ban_reason, now_iso))
        await conn.commit()

        webhook_url = script["discord_webhook"] if "discord_webhook" in script.keys() else None
        if webhook_url:
            fields = [
                {"name": "License Key", "value": f"`{clean_key}`", "inline": True},
                {"name": "Script Hub", "value": f"{script['name']} (`{script['slug']}`)", "inline": True},
                {"name": "Trigger Reason", "value": "Multi-IP Proxy Sprawl (>3 IPs in 2h)", "inline": False},
                {"name": "IPs Detected", "value": f"`{all_ips.strip(', ')}`", "inline": False},
                {"name": "Action Taken", "value": "**Key Automatically Banned & Revoked**", "inline": False}
            ]
            await send_discord_security_alert(webhook_url, "IP Sprawl / Proxy Leak Detected (Auto-Banned)", f"License key `{clean_key}` has been automatically banned.", fields, 0xEF4444)

        return f"Security Violation: License revoked. IP sprawl / proxy distribution detected."

    return None

# Executor Handshake Models
class HandshakeInitRequest(BaseModel):
    slug: str
    key: str
    hwid: str
    client_challenge: str
    loader_token: Optional[str] = None
    executor: Optional[str] = "Universal"
    roblox_username: Optional[str] = None
    roblox_user_id: Optional[int] = None
    place_id: Optional[int] = None
    job_id: Optional[str] = None
    game_name: Optional[str] = None


class HandshakeVerifyRequest(BaseModel):
    nonce: str
    signature: str
    client_challenge: str
    hwid: Optional[str] = None

# ----------------- Frontend HTML Routes -----------------
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>FleedGuard Whitelist Service Online</h1>"

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    dash_file = os.path.join(TEMPLATES_DIR, "dashboard.html")
    if os.path.exists(dash_file):
        with open(dash_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>FleedGuard Dashboard Loading...</h1>"

@app.get("/getkey/{slug}", response_class=HTMLResponse)
async def serve_getkey(slug: str):
    getkey_file = os.path.join(TEMPLATES_DIR, "getkey.html")
    if os.path.exists(getkey_file):
        with open(getkey_file, "r", encoding="utf-8") as f:
            return f.read()
    return f"<h1>Get Key for {slug}</h1>"

# ----------------- User Auth & 2FA API -----------------
@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    if len(req.username) < 3 or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Username must be at least 3 chars, password at least 6")

    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM users WHERE username = ? OR email = ?", (req.username, req.email))
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Username or email already exists")

        pw_hash, salt = crypto_engine.hash_password(req.password)
        api_key = f"fg_live_{secrets.token_hex(20)}"
        now_iso = datetime.now(timezone.utc).isoformat()

        cursor = await conn.execute("""
            INSERT INTO users (username, email, password_hash, salt, api_key, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (req.username, req.email, pw_hash, salt, api_key, "developer", now_iso))
        await conn.commit()
        user_id = cursor.lastrowid

    token = crypto_engine.create_session_token(user_id, req.username, "developer")
    response = JSONResponse(content={"success": True, "token": token, "user": {"id": user_id, "username": req.username}})
    response.set_cookie(key="fleed_token", value=token, httponly=True, max_age=86400 * 30, samesite="lax")
    return response

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (req.username,))
        user = await cursor.fetchone()
        if not user:
            raise HTTPException(status_code=400, detail="Invalid username or password")

        if not crypto_engine.verify_password(req.password, user["password_hash"], user["salt"]):
            raise HTTPException(status_code=400, detail="Invalid username or password")

        # 2FA Check
        if user["two_factor_enabled"]:
            if not req.two_factor_code:
                return JSONResponse(content={"requires_2fa": True, "message": "2FA code required"})
            
            # Check TOTP code or Backup code
            totp_valid = crypto_engine.verify_totp(user["totp_secret"], req.two_factor_code)
            backup_valid = False
            backup_codes = json.loads(user["backup_codes"] or "[]")

            if not totp_valid and req.two_factor_code.upper() in backup_codes:
                backup_valid = True
                backup_codes.remove(req.two_factor_code.upper())
                await conn.execute("UPDATE users SET backup_codes = ? WHERE id = ?", (json.dumps(backup_codes), user["id"]))
                await conn.commit()

            if not totp_valid and not backup_valid:
                raise HTTPException(status_code=400, detail="Invalid 2FA code or backup code")

        now_iso = datetime.now(timezone.utc).isoformat()
        await conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso, user["id"]))
        await conn.commit()

    token = crypto_engine.create_session_token(user["id"], user["username"], user["role"])
    response = JSONResponse(content={
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "two_factor_enabled": bool(user["two_factor_enabled"]),
            "api_key": user["api_key"]
        }
    })
    response.set_cookie(key="fleed_token", value=token, httponly=True, max_age=86400 * 30, samesite="lax")
    return response

@app.post("/api/auth/logout")
async def logout():
    response = JSONResponse(content={"success": True})
    response.delete_cookie("fleed_token")
    return response

@app.get("/api/auth/me")
async def get_me(user: Dict = Depends(get_current_user)):
    api_key = user.get("api_key")
    if not api_key:
        api_key = f"fg_live_{secrets.token_hex(20)}"
        async with db.get_db() as conn:
            await conn.execute("UPDATE users SET api_key = ? WHERE id = ?", (api_key, user["id"]))
            await conn.commit()
        user["api_key"] = api_key

    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "two_factor_enabled": bool(user["two_factor_enabled"]),
        "api_key": api_key,
        "avatar_url": user.get("avatar_url"),
        "discord_id": user["discord_id"] if "discord_id" in user.keys() else None,
        "created_at": user["created_at"]
    }

class UpdateAvatarRequest(BaseModel):
    avatar_url: Optional[str] = None
    roblox_username: Optional[str] = None
    roblox_user_id: Optional[int] = None
    discord_id: Optional[str] = None

@app.post("/api/auth/update_avatar")
async def update_avatar(req: UpdateAvatarRequest, user: Dict = Depends(get_current_user)):
    resolved_avatar = req.avatar_url.strip() if req.avatar_url else None

    # 1. Resolve Roblox username / user ID if provided
    if req.roblox_user_id and req.roblox_user_id > 0:
        resolved_avatar = f"/api/roblox/avatar/{req.roblox_user_id}"
    elif req.roblox_username:
        clean_user = req.roblox_username.strip()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://users.roblox.com/v1/usernames/users", json={"usernames": [clean_user], "excludeBannedUsers": False}, timeout=aiohttp.ClientTimeout(total=4)) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data.get("data") and len(data["data"]) > 0:
                            rbx_id = data["data"][0]["id"]
                            resolved_avatar = f"/api/roblox/avatar/{rbx_id}"
        except Exception:
            pass

    # 2. Resolve Discord ID if provided
    if req.discord_id:
        clean_disc = str(req.discord_id).strip("<@!>")
        try:
            user_info = await get_discord_user_cached(clean_disc)
            if user_info and user_info.get("avatar_url"):
                resolved_avatar = user_info["avatar_url"]
        except Exception:
            pass

    async with db.get_db() as conn:
        await conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (resolved_avatar, user["id"]))
        await conn.commit()

    return {"success": True, "avatar_url": resolved_avatar, "message": "Avatar updated successfully!"}

@app.post("/api/auth/upload_avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: Dict = Depends(get_current_user)
):
    """Allows uploading a custom avatar image directly from the user's PC."""
    allowed_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    filename = file.filename or "avatar.png"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Invalid image format. Supported formats: PNG, JPG, JPEG, WebP, GIF.")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image file too large (Max 5MB).")

    # Generate unique secure filename
    safe_filename = f"avatar_{user['id']}_{int(time.time())}_{secrets.token_hex(4)}{ext}"
    target_path = os.path.join(UPLOADS_AVATAR_DIR, safe_filename)
    with open(target_path, "wb") as f:
        f.write(content)

    avatar_url = f"/static/uploads/avatars/{safe_filename}"

    # Update user in database
    async with db.get_db() as conn:
        await conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, user["id"]))
        await conn.commit()

    return {"success": True, "avatar_url": avatar_url, "message": "Avatar uploaded and updated successfully!"}

class Base64AvatarUploadRequest(BaseModel):
    image_data: str # "data:image/png;base64,iVBOR..."

@app.post("/api/auth/upload_avatar_base64")
async def upload_avatar_base64(req: Base64AvatarUploadRequest, user: Dict = Depends(get_current_user)):
    """Allows uploading a custom avatar image via base64 data URL."""
    raw = req.image_data.strip()
    if not raw.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Invalid image payload. Must be a valid image data URL.")

    try:
        header, b64_str = raw.split(",", 1)
        mime = header.split(";")[0].split(":")[1].lower()
        ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
        ext = ext_map.get(mime, ".png")
        file_bytes = base64.b64decode(b64_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decode image data.")

    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image file too large (Max 5MB).")

    safe_filename = f"avatar_{user['id']}_{int(time.time())}_{secrets.token_hex(4)}{ext}"
    target_path = os.path.join(UPLOADS_AVATAR_DIR, safe_filename)
    with open(target_path, "wb") as f:
        f.write(file_bytes)

    avatar_url = f"/static/uploads/avatars/{safe_filename}"

    async with db.get_db() as conn:
        await conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, user["id"]))
        await conn.commit()

    return {"success": True, "avatar_url": avatar_url, "message": "Avatar uploaded and updated successfully!"}

@app.post("/api/auth/regenerate_api_key")
async def regenerate_api_key(user: Dict = Depends(get_current_user)):
    new_api_key = f"fg_live_{secrets.token_hex(20)}"
    async with db.get_db() as conn:
        await conn.execute("UPDATE users SET api_key = ? WHERE id = ?", (new_api_key, user["id"]))
        await conn.commit()
    return {"success": True, "api_key": new_api_key}

class BindDiscordRequest(BaseModel):
    discord_id: str

@app.post("/api/auth/bind_discord")
async def bind_discord(req: BindDiscordRequest, user: Dict = Depends(get_current_user)):
    clean_id = str(req.discord_id).strip("<@!>")
    async with db.get_db() as conn:
        await conn.execute("UPDATE users SET discord_id = ? WHERE id = ?", (clean_id, user["id"]))
        await conn.commit()
    return {"success": True, "message": f"Linked Discord ID {clean_id} to user {user['username']}"}

# ----------------- 2FA Configuration Endpoints -----------------
@app.post("/api/auth/2fa/setup")
async def setup_2fa(user: Dict = Depends(get_current_user)):
    totp_secret = crypto_engine.generate_totp_secret()
    totp_uri = crypto_engine.get_totp_uri(totp_secret, user["username"])
    qr_data_uri = crypto_engine.generate_qr_data_uri(totp_uri)
    backup_codes = crypto_engine.generate_backup_codes()

    async with db.get_db() as conn:
        await conn.execute("""
            UPDATE users SET totp_secret = ?, backup_codes = ? WHERE id = ?
        """, (totp_secret, json.dumps(backup_codes), user["id"]))
        await conn.commit()

    return {
        "secret": totp_secret,
        "qr_code": qr_data_uri,
        "backup_codes": backup_codes
    }

@app.post("/api/auth/2fa/verify")
async def verify_and_enable_2fa(req: Enable2FARequest, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT totp_secret, backup_codes FROM users WHERE id = ?", (user["id"],))
        db_user = await cursor.fetchone()
        if not db_user or not db_user["totp_secret"]:
            raise HTTPException(status_code=400, detail="2FA setup not initiated")

        if not crypto_engine.verify_totp(db_user["totp_secret"], req.code):
            raise HTTPException(status_code=400, detail="Invalid 6-digit TOTP verification code")

        await conn.execute("UPDATE users SET two_factor_enabled = 1 WHERE id = ?", (user["id"],))
        await conn.commit()

    return {"success": True, "message": "2FA successfully enabled"}

@app.post("/api/auth/2fa/disable")
async def disable_2fa(req: Enable2FARequest, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT totp_secret FROM users WHERE id = ?", (user["id"],))
        db_user = await cursor.fetchone()
        if not db_user or not db_user["totp_secret"]:
            raise HTTPException(status_code=400, detail="2FA is not active")

        if not crypto_engine.verify_totp(db_user["totp_secret"], req.code):
            raise HTTPException(status_code=400, detail="Invalid 6-digit TOTP code")

        await conn.execute("UPDATE users SET two_factor_enabled = 0, totp_secret = NULL, backup_codes = NULL WHERE id = ?", (user["id"],))
        await conn.commit()

    return {"success": True, "message": "2FA disabled"}

# ----------------- Script Management API -----------------
@app.get("/api/scripts")
async def list_scripts(user: Dict = Depends(get_current_user)):
    is_admin = user.get("role") == "admin"
    async with db.get_db() as conn:
        if is_admin:
            cursor = await conn.execute("""
                SELECT s.*, 
                       COUNT(l.id) as total_licenses,
                       SUM(CASE WHEN l.is_banned = 0 THEN 1 ELSE 0 END) as active_licenses
                FROM scripts s
                LEFT JOIN licenses l ON s.id = l.script_id
                GROUP BY s.id
                ORDER BY s.id DESC
            """)
        else:
            cursor = await conn.execute("""
                SELECT s.*, 
                       COUNT(l.id) as total_licenses,
                       SUM(CASE WHEN l.is_banned = 0 THEN 1 ELSE 0 END) as active_licenses
                FROM scripts s
                LEFT JOIN licenses l ON s.id = l.script_id
                WHERE s.user_id = ?
                GROUP BY s.id
                ORDER BY s.id DESC
            """, (user["id"],))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

@app.post("/api/scripts")
async def create_script(req: ScriptCreateRequest, user: Dict = Depends(get_current_user)):
    clean_slug = req.slug.strip().lower().replace(" ", "_")
    now_iso = datetime.now(timezone.utc).isoformat()

    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ?", (clean_slug,))
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Script slug already exists")

        cursor = await conn.execute("""
            INSERT INTO scripts (user_id, name, slug, description, version, raw_source, is_obfuscated_mode, discord_webhook, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user["id"], req.name, clean_slug, req.description, req.version, req.raw_source, req.is_obfuscated_mode, req.discord_webhook, now_iso, now_iso))
        await conn.commit()
        script_id = cursor.lastrowid

    return {"success": True, "id": script_id, "slug": clean_slug}

@app.get("/api/scripts/{script_id}")
async def get_script(script_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM scripts WHERE id = ? AND user_id = ?", (script_id, user["id"]))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Script not found")
        return dict(row)

@app.patch("/api/scripts/{script_id}")
async def update_script(script_id: int, req: ScriptUpdateRequest, user: Dict = Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []

    if req.name is not None: fields.append("name = ?"); values.append(req.name)
    if req.description is not None: fields.append("description = ?"); values.append(req.description)
    if req.version is not None: fields.append("version = ?"); values.append(req.version)
    if req.raw_source is not None: fields.append("raw_source = ?"); values.append(req.raw_source)
    if req.is_obfuscated_mode is not None: fields.append("is_obfuscated_mode = ?"); values.append(req.is_obfuscated_mode)
    if req.killswitch_active is not None: fields.append("killswitch_active = ?"); values.append(req.killswitch_active)
    if req.killswitch_reason is not None: fields.append("killswitch_reason = ?"); values.append(req.killswitch_reason)
    if req.discord_webhook is not None: fields.append("discord_webhook = ?"); values.append(req.discord_webhook)

    if not fields:
        return {"success": True}

    fields.append("updated_at = ?")
    values.append(now_iso)
    values.extend([script_id, user["id"]])

    query = f"UPDATE scripts SET {', '.join(fields)} WHERE id = ? AND user_id = ?"

    async with db.get_db() as conn:
        await conn.execute(query, tuple(values))
        await conn.commit()

    return {"success": True}

@app.delete("/api/scripts/{script_id}")
async def delete_script(script_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM scripts WHERE id = ? AND user_id = ?", (script_id, user["id"]))
        await conn.commit()
    return {"success": True}

@app.post("/api/scripts/{script_id}/test-webhook")
async def test_script_webhook(script_id: int, req: TestWebhookRequest, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM scripts WHERE id = ? AND user_id = ?", (script_id, user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        webhook_url = req.webhook_url or script["discord_webhook"]
        if not webhook_url or not str(webhook_url).startswith("https://discord.com/api/webhooks/"):
            raise HTTPException(status_code=400, detail="No valid Discord webhook URL provided.")

        fields = [
            {"name": "Script Hub", "value": f"{script['name']} (`{script['slug']}`)", "inline": True},
            {"name": "Status", "value": "Webhook Connection Active & Verified", "inline": True},
            {"name": "Security VM", "value": "O_bfuscate 1.1 Virtualization Ready", "inline": True},
            {"name": "Timestamp", "value": f"<t:{int(time.time())}:R>", "inline": True}
        ]
        await send_discord_security_alert(
            webhook_url=webhook_url,
            title="FleedGuard Webhook Diagnostic Test",
            description="This is an automated verification test dispatched from your FleedGuard Enterprise Console.",
            fields=fields,
            color=0xFACC15
        )

    return {"success": True, "message": "Test security alert sent to Discord webhook!"}

# ----------------- Discord User Resolver API -----------------
_discord_user_cache: Dict[str, Dict] = {}

async def resolve_discord_user(user_id: str) -> Dict:
    clean_id = str(user_id).strip("<@!> ")
    if not clean_id or not clean_id.isdigit():
        return {"id": user_id, "username": user_id, "display_name": user_id, "avatar_url": None}

    if clean_id in _discord_user_cache:
        return _discord_user_cache[clean_id]

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        res = {"id": clean_id, "username": f"User {clean_id[-4:]}", "display_name": f"User {clean_id[-4:]}", "avatar_url": None}
        _discord_user_cache[clean_id] = res
        return res

    try:
        url = f"https://discord.com/api/v10/users/{clean_id}"
        headers = {"Authorization": f"Bot {token}", "User-Agent": "FleedGuardBot/1.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    username = data.get("username")
                    global_name = data.get("global_name") or username
                    avatar_hash = data.get("avatar")
                    avatar_url = f"https://cdn.discordapp.com/avatars/{clean_id}/{avatar_hash}.png?size=64" if avatar_hash else "https://cdn.discordapp.com/embed/avatars/0.png"
                    res = {
                        "id": clean_id,
                        "username": username,
                        "display_name": global_name,
                        "avatar_url": avatar_url
                    }
                    _discord_user_cache[clean_id] = res
                    return res
    except Exception:
        pass

    res = {"id": clean_id, "username": f"User {clean_id[-4:]}", "display_name": f"User {clean_id[-4:]}", "avatar_url": None}
    _discord_user_cache[clean_id] = res
    return res

@app.get("/api/discord/user/{user_id}")
async def get_discord_user_info(user_id: str):
    """Fetches Discord username, avatar, and display name for user ID."""
    return await resolve_discord_user(user_id)

# ----------------- License / Key Management API -----------------
@app.get("/api/scripts/{script_id}/licenses")
async def list_licenses(script_id: int, user: Dict = Depends(get_current_user)):
    is_admin = user.get("role") == "admin"
    async with db.get_db() as conn:
        if is_admin:
            cursor = await conn.execute("""
                SELECT l.* FROM licenses l
                WHERE l.script_id = ?
                ORDER BY l.id DESC
            """, (script_id,))
        else:
            cursor = await conn.execute("""
                SELECT l.* FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.script_id = ? AND s.user_id = ?
                ORDER BY l.id DESC
            """, (script_id, user["id"]))
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            raw_disc = d.get("discord_id")
            if raw_disc:
                clean_disc = str(raw_disc).strip("<@!> ")
                if clean_disc in _discord_user_cache:
                    u = _discord_user_cache[clean_disc]
                    d["discord_username"] = u.get("username")
                    d["discord_display_name"] = u.get("display_name")
                    d["discord_avatar"] = u.get("avatar_url")
            result.append(d)
        return result

@app.get("/api/licenses/{license_id}/history")
async def get_license_history(license_id: int, user: Dict = Depends(get_current_user)):
    """Deep forensic inspection for a single license key."""
    is_admin = user.get("role") == "admin"
    async with db.get_db() as conn:
        if is_admin:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.slug as script_slug
                FROM licenses l
                LEFT JOIN scripts s ON l.script_id = s.id
                WHERE l.id = ?
            """, (license_id,))
        else:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.slug as script_slug
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.id = ? AND s.user_id = ?
            """, (license_id, user["id"]))
        lic = await cursor.fetchone()
        if not lic:
            raise HTTPException(status_code=404, detail="License not found")

        clean_key = lic["license_key"]

        c_logs = await conn.execute("""
            SELECT * FROM execution_logs
            WHERE license_id = ? OR UPPER(license_key) = UPPER(?)
            ORDER BY id DESC LIMIT 50
        """, (license_id, clean_key))
        logs = [dict(r) for r in await c_logs.fetchall()]

        c_users = await conn.execute("""
            SELECT roblox_username, roblox_user_id, MAX(timestamp) as last_seen, COUNT(*) as exec_count
            FROM execution_logs
            WHERE (license_id = ? OR UPPER(license_key) = UPPER(?)) AND roblox_user_id > 0
            GROUP BY roblox_username, roblox_user_id
            ORDER BY exec_count DESC LIMIT 20
        """, (license_id, clean_key))
        users = [dict(r) for r in await c_users.fetchall()]

        c_ips = await conn.execute("""
            SELECT ip_address, MAX(timestamp) as last_seen, COUNT(*) as exec_count
            FROM execution_logs
            WHERE (license_id = ? OR UPPER(license_key) = UPPER(?)) AND ip_address IS NOT NULL AND ip_address != ''
            GROUP BY ip_address
            ORDER BY exec_count DESC LIMIT 20
        """, (license_id, clean_key))
        ips = [dict(r) for r in await c_ips.fetchall()]

        c_games = await conn.execute("""
            SELECT game_name, place_id, COUNT(*) as exec_count
            FROM execution_logs
            WHERE (license_id = ? OR UPPER(license_key) = UPPER(?)) AND place_id > 0
            GROUP BY game_name, place_id
            ORDER BY exec_count DESC LIMIT 10
        """, (license_id, clean_key))
        games = [dict(r) for r in await c_games.fetchall()]

        return {
            "license": dict(lic),
            "logs": logs,
            "roblox_users": users,
            "ip_addresses": ips,
            "games": games
        }

class LicenseCreateDirectRequest(BaseModel):
    slug: str
    license_key: str
    discord_id: Optional[str] = None
    note: Optional[str] = None
    expires_at: Optional[str] = None

@app.post("/api/licenses/create")
async def create_single_license(req: LicenseCreateDirectRequest, user: Dict = Depends(get_current_user)):
    clean_slug = req.slug.strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (clean_slug, user["id"]))
        script = await cursor.fetchone()
        if not script:
            cursor2 = await conn.execute("SELECT id FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor2.fetchone()
            if not script:
                raise HTTPException(status_code=404, detail=f"Script '{clean_slug}' not found")

        clean_key = str(req.license_key).strip().upper()
        clean_discord_id = str(req.discord_id).strip("<@!>") if req.discord_id else None

        await conn.execute("""
            INSERT INTO licenses (script_id, license_key, discord_id, note, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(license_key) DO UPDATE SET discord_id = excluded.discord_id, note = excluded.note
        """, (script["id"], clean_key, clean_discord_id, req.note, req.expires_at, now_iso))
        await conn.commit()

    return {"success": True, "license_key": clean_key}

@app.post("/api/licenses/bulk")
async def create_bulk_licenses(req: LicenseBulkCreateRequest, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT slug FROM scripts WHERE id = ? AND user_id = ?", (req.script_id, user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()
        expires_at = None
        if req.duration_days and req.duration_days > 0:
            expires_at = (now_utc + timedelta(days=req.duration_days)).isoformat()

        generated_keys = []
        for _ in range(max(1, min(req.count, 200))):
            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, note, max_executions, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (req.script_id, key, req.note, req.max_executions, expires_at, now_iso))
            generated_keys.append(key)

        await conn.commit()

    return {"success": True, "count": len(generated_keys), "keys": generated_keys}

@app.post("/api/licenses/import")
async def import_licenses(req: LicenseBulkImportRequest, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE id = ? AND user_id = ?", (req.script_id, user["id"]))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Script not found")

        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()
        imported = 0
        skipped = 0

        for item in req.keys:
            clean_key = str(item.license_key).strip().upper()
            if not clean_key:
                skipped += 1
                continue

            expires_at = None
            if item.duration_days and item.duration_days > 0:
                expires_at = (now_utc + timedelta(days=item.duration_days)).isoformat()

            clean_disc = str(item.discord_id).strip("<@!>") if item.discord_id else None

            try:
                await conn.execute("""
                    INSERT INTO licenses (script_id, license_key, note, discord_id, max_executions, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(license_key) DO UPDATE SET note = excluded.note, discord_id = excluded.discord_id
                """, (req.script_id, clean_key, item.note, clean_disc, item.max_executions or -1, expires_at, now_iso))
                imported += 1
            except Exception:
                skipped += 1

        await conn.commit()

    return {"success": True, "imported": imported, "skipped": skipped}

@app.post("/api/licenses/bulk-action")
async def bulk_license_action(req: LicenseBulkActionRequest, user: Dict = Depends(get_current_user)):
    if not req.license_ids:
        return {"success": True, "affected": 0}

    now_iso = datetime.now(timezone.utc).isoformat()

    async with db.get_db() as conn:
        placeholders = ",".join("?" * len(req.license_ids))
        cursor = await conn.execute(f"""
            SELECT l.id, l.license_key, l.expires_at FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.id IN ({placeholders}) AND s.user_id = ?
        """, (*req.license_ids, user["id"]))
        valid_rows = await cursor.fetchall()
        valid_ids = [r["id"] for r in valid_rows]

        if not valid_ids:
            return {"success": True, "affected": 0}

        valid_placeholders = ",".join("?" * len(valid_ids))

        if req.action == "resethwid":
            await conn.execute(f"""
                UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ?
                WHERE id IN ({valid_placeholders})
            """, (now_iso, *valid_ids))
        elif req.action == "ban":
            await conn.execute(f"""
                UPDATE licenses SET is_banned = 1, ban_reason = ?
                WHERE id IN ({valid_placeholders})
            """, (req.ban_reason or "Bulk Banned by Admin", *valid_ids))
        elif req.action == "unban":
            await conn.execute(f"""
                UPDATE licenses SET is_banned = 0, ban_reason = NULL
                WHERE id IN ({valid_placeholders})
            """, (*valid_ids,))
        elif req.action == "delete":
            await conn.execute(f"""
                DELETE FROM licenses WHERE id IN ({valid_placeholders})
            """, (*valid_ids,))
        elif req.action == "extend":
            days = req.extend_days or 30
            for r in valid_rows:
                base_dt = datetime.now(timezone.utc)
                if r["expires_at"]:
                    try:
                        cur_exp = datetime.fromisoformat(r["expires_at"])
                        if cur_exp > base_dt:
                            base_dt = cur_exp
                    except Exception:
                        pass
                new_exp = (base_dt + timedelta(days=days)).isoformat()
                await conn.execute("UPDATE licenses SET expires_at = ? WHERE id = ?", (new_exp, r["id"]))

        await conn.commit()

    return {"success": True, "affected": len(valid_ids)}

@app.post("/api/licenses/{license_id}/extend")
async def extend_single_license(license_id: int, req: LicenseExtendRequest, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.id, l.expires_at FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.id = ? AND s.user_id = ?
        """, (license_id, user["id"]))
        lic = await cursor.fetchone()
        if not lic:
            raise HTTPException(status_code=404, detail="License not found")

        if req.days <= 0:
            # Lifetime
            new_exp = None
        else:
            base_dt = datetime.now(timezone.utc)
            if lic["expires_at"]:
                try:
                    cur_exp = datetime.fromisoformat(lic["expires_at"])
                    if cur_exp > base_dt:
                        base_dt = cur_exp
                except Exception:
                    pass
            new_exp = (base_dt + timedelta(days=req.days)).isoformat()

        await conn.execute("UPDATE licenses SET expires_at = ? WHERE id = ?", (new_exp, license_id))
        await conn.commit()

    return {"success": True, "expires_at": new_exp}

@app.post("/api/licenses/{license_id}/resethwid")
async def reset_license_hwid(license_id: int, user: Dict = Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.id FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.id = ? AND s.user_id = ?
        """, (license_id, user["id"]))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="License not found")

        await conn.execute("""
            UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?
        """, (now_iso, license_id))
        await conn.commit()

    return {"success": True, "message": "HWID reset successfully"}

@app.patch("/api/licenses/{license_id}")
async def update_license(license_id: int, req: LicenseUpdateRequest, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.id FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.id = ? AND s.user_id = ?
        """, (license_id, user["id"]))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="License not found")

        fields = []
        values = []
        if req.note is not None: fields.append("note = ?"); values.append(req.note)
        if req.is_banned is not None: fields.append("is_banned = ?"); values.append(req.is_banned)
        if req.ban_reason is not None: fields.append("ban_reason = ?"); values.append(req.ban_reason)
        if req.expires_at is not None: fields.append("expires_at = ?"); values.append(req.expires_at)

        if fields:
            values.append(license_id)
            await conn.execute(f"UPDATE licenses SET {', '.join(fields)} WHERE id = ?", tuple(values))
            await conn.commit()

    return {"success": True}

@app.delete("/api/licenses/{license_id}")
async def delete_license(license_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        await conn.execute("""
            DELETE FROM licenses WHERE id = ? AND script_id IN (SELECT id FROM scripts WHERE user_id = ?)
        """, (license_id, user["id"]))
        await conn.commit()
    return {"success": True}

# ----------------- Analytics & Execution Logs API -----------------
@app.get("/api/stats")
async def get_dashboard_stats(user: Dict = Depends(get_current_user)):
    is_admin = user.get("role") == "admin"
    async with db.get_db() as conn:
        # Total scripts
        if is_admin:
            c1 = await conn.execute("SELECT COUNT(*) as cnt FROM scripts")
        else:
            c1 = await conn.execute("SELECT COUNT(*) as cnt FROM scripts WHERE user_id = ?", (user["id"],))
        scripts_cnt = (await c1.fetchone())["cnt"]

        # Total licenses & breakdown
        if is_admin:
            c2 = await conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN is_banned = 0 AND (expires_at IS NULL OR datetime(expires_at) > datetime('now')) THEN 1 ELSE 0 END) as active,
                       SUM(CASE WHEN is_banned = 1 THEN 1 ELSE 0 END) as banned,
                       SUM(CASE WHEN is_banned = 0 AND expires_at IS NOT NULL AND datetime(expires_at) <= datetime('now') THEN 1 ELSE 0 END) as expired,
                       SUM(CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END) as lifetime,
                       SUM(CASE WHEN hwid IS NOT NULL AND hwid != '' THEN 1 ELSE 0 END) as bound_hwids
                FROM licenses
            """)
        else:
            c2 = await conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN is_banned = 0 AND (expires_at IS NULL OR datetime(expires_at) > datetime('now')) THEN 1 ELSE 0 END) as active,
                       SUM(CASE WHEN is_banned = 1 THEN 1 ELSE 0 END) as banned,
                       SUM(CASE WHEN is_banned = 0 AND expires_at IS NOT NULL AND datetime(expires_at) <= datetime('now') THEN 1 ELSE 0 END) as expired,
                       SUM(CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END) as lifetime,
                       SUM(CASE WHEN hwid IS NOT NULL AND hwid != '' THEN 1 ELSE 0 END) as bound_hwids
                FROM licenses WHERE script_id IN (SELECT id FROM scripts WHERE user_id = ?)
            """, (user["id"],))
        lic_row = await c2.fetchone()
        total_licenses = lic_row["total"] if lic_row else 0
        active_licenses = lic_row["active"] if lic_row and lic_row["active"] else 0
        banned_licenses = lic_row["banned"] if lic_row and lic_row["banned"] else 0
        expired_licenses = lic_row["expired"] if lic_row and lic_row["expired"] else 0
        lifetime_licenses = lic_row["lifetime"] if lic_row and lic_row["lifetime"] else 0
        bound_hwids = lic_row["bound_hwids"] if lic_row and lic_row["bound_hwids"] else 0

        # Total executions & blocked
        if is_admin:
            c3 = await conn.execute("""
                SELECT COUNT(*) as total_execs,
                       SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_execs,
                       SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) as blocked_execs,
                       COUNT(DISTINCT CASE WHEN roblox_user_id > 0 THEN roblox_user_id ELSE NULL END) as unique_players
                FROM execution_logs
            """)
        else:
            c3 = await conn.execute("""
                SELECT COUNT(*) as total_execs,
                       SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_execs,
                       SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) as blocked_execs,
                       COUNT(DISTINCT CASE WHEN roblox_user_id > 0 THEN roblox_user_id ELSE NULL END) as unique_players
                FROM execution_logs WHERE script_id IN (SELECT id FROM scripts WHERE user_id = ?)
            """, (user["id"],))
        exec_row = await c3.fetchone()
        total_execs = exec_row["total_execs"] if exec_row else 0
        success_execs = exec_row["success_execs"] if exec_row and exec_row["success_execs"] else 0
        blocked_execs = exec_row["blocked_execs"] if exec_row and exec_row["blocked_execs"] else 0
        unique_players = exec_row["unique_players"] if exec_row and exec_row["unique_players"] else 0

        # Active sessions in last 15 min
        if is_admin:
            c4 = await conn.execute("""
                SELECT COUNT(*) as cnt FROM execution_logs
                WHERE timestamp >= datetime('now', '-15 minutes')
            """)
        else:
            c4 = await conn.execute("""
                SELECT COUNT(*) as cnt FROM execution_logs
                WHERE script_id IN (SELECT id FROM scripts WHERE user_id = ?)
                  AND timestamp >= datetime('now', '-15 minutes')
            """, (user["id"],))
        active_15m = (await c4.fetchone())["cnt"]

        # Hourly activity (last 24 hours)
        if is_admin:
            c5 = await conn.execute("""
                SELECT strftime('%H:00', timestamp) as hr,
                       SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_cnt,
                       SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) as blocked_cnt,
                       COUNT(*) as total_cnt
                FROM execution_logs
                WHERE timestamp >= datetime('now', '-24 hours')
                GROUP BY strftime('%Y-%m-%d %H', timestamp)
                ORDER BY timestamp ASC
            """)
        else:
            c5 = await conn.execute("""
                SELECT strftime('%H:00', timestamp) as hr,
                       SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_cnt,
                       SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) as blocked_cnt,
                       COUNT(*) as total_cnt
                FROM execution_logs
                WHERE script_id IN (SELECT id FROM scripts WHERE user_id = ?)
                  AND timestamp >= datetime('now', '-24 hours')
                GROUP BY strftime('%Y-%m-%d %H', timestamp)
                ORDER BY timestamp ASC
            """, (user["id"],))
        hourly_rows = await c5.fetchall()
        hourly_activity = [{"hour": r["hr"], "success": r["success_cnt"] or 0, "blocked": r["blocked_cnt"] or 0, "total": r["total_cnt"]} for r in hourly_rows]

        # Top Executors
        if is_admin:
            c6 = await conn.execute("""
                SELECT COALESCE(NULLIF(executor_name, ''), 'Universal') as exec_name, COUNT(*) as cnt
                FROM execution_logs
                GROUP BY exec_name
                ORDER BY cnt DESC
                LIMIT 5
            """)
        else:
            c6 = await conn.execute("""
                SELECT COALESCE(NULLIF(executor_name, ''), 'Universal') as exec_name, COUNT(*) as cnt
                FROM execution_logs
                WHERE script_id IN (SELECT id FROM scripts WHERE user_id = ?)
                GROUP BY exec_name
                ORDER BY cnt DESC
                LIMIT 5
            """, (user["id"],))
        top_executors_rows = await c6.fetchall()
        top_executors = [{"name": r["exec_name"], "count": r["cnt"]} for r in top_executors_rows]

        # Top Games / Experiences
        if is_admin:
            c7 = await conn.execute("""
                SELECT game_name,
                       place_id,
                       COUNT(*) as cnt
                FROM execution_logs
                WHERE status = 'SUCCESS' OR place_id > 0
                GROUP BY place_id, game_name
                ORDER BY cnt DESC
                LIMIT 15
            """)
        else:
            c7 = await conn.execute("""
                SELECT game_name,
                       place_id,
                       COUNT(*) as cnt
                FROM execution_logs
                WHERE script_id IN (SELECT id FROM scripts WHERE user_id = ?) AND (status = 'SUCCESS' OR place_id > 0)
                GROUP BY place_id, game_name
                ORDER BY cnt DESC
                LIMIT 15
            """, (user["id"],))
        top_games_rows = await c7.fetchall()
        top_games_dict = {}
        for r in top_games_rows:
            place_id = r["place_id"] or 0
            cur_name = r["game_name"]
            if (not cur_name or cur_name in ("Roblox Game", "Unknown", "Roblox Experience")) and place_id > 0:
                resolved_name = await resolve_roblox_game_name(place_id, cur_name)
                if resolved_name != cur_name and not resolved_name.startswith("Place #"):
                    try:
                        await conn.execute("UPDATE execution_logs SET game_name = ? WHERE place_id = ? AND (game_name = 'Roblox Game' OR game_name = 'Unknown' OR game_name IS NULL)", (resolved_name, place_id))
                        await conn.execute("UPDATE live_sessions SET game_name = ? WHERE place_id = ? AND (game_name = 'Roblox Game' OR game_name = 'Unknown' OR game_name IS NULL)", (resolved_name, place_id))
                    except Exception:
                        pass
                cur_name = resolved_name
            elif not cur_name:
                cur_name = f"Place #{place_id}" if place_id > 0 else "Roblox Experience"

            key = (cur_name, place_id)
            top_games_dict[key] = top_games_dict.get(key, 0) + r["cnt"]

        top_games = [{"name": k[0], "place_id": k[1], "count": v} for k, v in sorted(top_games_dict.items(), key=lambda x: x[1], reverse=True)[:5]]
        await conn.commit()

        return {
            "total_scripts": scripts_cnt,
            "total_licenses": total_licenses,
            "active_licenses": active_licenses,
            "banned_licenses": banned_licenses,
            "expired_licenses": expired_licenses,
            "lifetime_licenses": lifetime_licenses,
            "bound_hwids": bound_hwids,
            "total_executions": total_execs,
            "success_executions": success_execs,
            "blocked_attacks": blocked_execs,
            "unique_players": unique_players,
            "active_sessions_15m": active_15m,
            "hourly_activity": hourly_activity,
            "top_executors": top_executors,
            "top_games": top_games
        }

@app.get("/api/logs")
async def get_logs(limit: int = 100, status_filter: Optional[str] = None, user: Dict = Depends(get_current_user)):
    is_admin = user.get("role") == "admin"
    async with db.get_db() as conn:
        if is_admin:
            if status_filter == "blocked":
                cursor = await conn.execute("""
                    SELECT l.*, s.name as script_name
                    FROM execution_logs l
                    LEFT JOIN scripts s ON l.script_id = s.id
                    WHERE l.status != 'SUCCESS'
                    ORDER BY l.id DESC LIMIT ?
                """, (limit,))
            elif status_filter:
                cursor = await conn.execute("""
                    SELECT l.*, s.name as script_name
                    FROM execution_logs l
                    LEFT JOIN scripts s ON l.script_id = s.id
                    WHERE l.status = ?
                    ORDER BY l.id DESC LIMIT ?
                """, (status_filter, limit))
            else:
                cursor = await conn.execute("""
                    SELECT l.*, s.name as script_name
                    FROM execution_logs l
                    LEFT JOIN scripts s ON l.script_id = s.id
                    ORDER BY l.id DESC LIMIT ?
                """, (limit,))
        else:
            if status_filter == "blocked":
                cursor = await conn.execute("""
                    SELECT l.*, s.name as script_name
                    FROM execution_logs l
                    JOIN scripts s ON l.script_id = s.id
                    WHERE s.user_id = ? AND l.status != 'SUCCESS'
                    ORDER BY l.id DESC LIMIT ?
                """, (user["id"], limit))
            elif status_filter:
                cursor = await conn.execute("""
                    SELECT l.*, s.name as script_name
                    FROM execution_logs l
                    JOIN scripts s ON l.script_id = s.id
                    WHERE s.user_id = ? AND l.status = ?
                    ORDER BY l.id DESC LIMIT ?
                """, (user["id"], status_filter, limit))
            else:
                cursor = await conn.execute("""
                    SELECT l.*, s.name as script_name
                    FROM execution_logs l
                    JOIN scripts s ON l.script_id = s.id
                    WHERE s.user_id = ?
                    ORDER BY l.id DESC LIMIT ?
                """, (user["id"], limit))
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            pid = d.get("place_id") or 0
            if (not d.get("game_name") or d.get("game_name") in ("Roblox Game", "Unknown", "Roblox Experience")) and pid > 0:
                if pid in game_name_cache:
                    d["game_name"] = game_name_cache[pid]
                else:
                    d["game_name"] = f"Place #{pid}"
            result.append(d)
        return result

# Cache avatar headshots in memory to avoid repeated requests to Roblox API
avatar_cache: Dict[int, str] = {}

DEFAULT_AVATAR_SVG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2371717a'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z'/%3E%3C/svg%3E"

@app.get("/api/roblox/avatar/{user_id}")
async def get_roblox_avatar(user_id: int):
    """Fetches high-res Roblox user headshot and redirects directly to CDN."""
    if user_id <= 0:
        return RedirectResponse(url=DEFAULT_AVATAR_SVG, status_code=302)
        
    if user_id in avatar_cache:
        return RedirectResponse(url=avatar_cache[user_id], status_code=302)

    try:
        url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png&isCircular=true"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("data") and len(data["data"]) > 0:
                    img_url = data["data"][0].get("imageUrl")
                    if img_url:
                        avatar_cache[user_id] = img_url
                        return RedirectResponse(url=img_url, status_code=302)
    except Exception:
        pass

    return RedirectResponse(url=DEFAULT_AVATAR_SVG, status_code=302)

# Cache resolved game titles in memory
game_name_cache: Dict[int, str] = {}

async def resolve_roblox_game_name(place_id: int, fallback: Optional[str] = None) -> str:
    """Fetches the official Roblox game title given a place_id via Roblox Universe API."""
    if not place_id or place_id <= 0:
        return fallback if (fallback and fallback not in ("Roblox Game", "Unknown", "Roblox Experience")) else "Roblox Experience"
    if place_id in game_name_cache:
        return game_name_cache[place_id]

    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            # 1. Fetch Universe ID from place ID
            u_url = f"https://apis.roblox.com/universes/v1/places/{place_id}/universe"
            async with session.get(u_url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as r:
                if r.status == 200:
                    data = await r.json()
                    uid = data.get("universeId")
                    if uid:
                        # 2. Fetch Game Details
                        g_url = f"https://games.roblox.com/v1/games?universeIds={uid}"
                        async with session.get(g_url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as gr:
                            if gr.status == 200:
                                gdata = await gr.json()
                                if gdata.get("data") and len(gdata["data"]) > 0:
                                    name = gdata["data"][0].get("name")
                                    if name:
                                        clean_name = str(name).strip()
                                        game_name_cache[place_id] = clean_name
                                        return clean_name
    except Exception:
        pass

    return fallback if (fallback and fallback not in ("Roblox Game", "Unknown", "Roblox Experience")) else f"Place #{place_id}"

async def background_resolve_and_update_place(place_id: int):
    """Background worker to resolve place names and update database records."""
    try:
        resolved = await resolve_roblox_game_name(place_id)
        if resolved and not resolved.startswith("Place #") and resolved not in ("Roblox Game", "Unknown", "Roblox Experience"):
            async with db.get_db() as conn:
                await conn.execute("UPDATE execution_logs SET game_name = ? WHERE place_id = ? AND (game_name = 'Roblox Game' OR game_name = 'Unknown' OR game_name IS NULL OR game_name = 'Roblox Experience')", (resolved, place_id))
                await conn.execute("UPDATE live_sessions SET game_name = ? WHERE place_id = ? AND (game_name = 'Roblox Game' OR game_name = 'Unknown' OR game_name IS NULL OR game_name = 'Roblox Experience')", (resolved, place_id))
                await conn.commit()
    except Exception:
        pass




# ----------------- Rate Limiting & Anti-Brute Force Engine -----------------
handshake_rate_limit: Dict[str, List[float]] = {}

def check_rate_limit(key: str, max_requests: int = 30, window_sec: int = 60) -> bool:
    """Sliding-window rate limiter. Returns True if allowed, False if exceeded."""
    now = time.time()
    timestamps = handshake_rate_limit.setdefault(key, [])
    # Filter out entries older than window
    timestamps = [t for t in timestamps if now - t < window_sec]
    handshake_rate_limit[key] = timestamps
    if len(timestamps) >= max_requests:
        return False
    timestamps.append(now)
    return True

# ----------------- Roblox Executor Loader & Handshake API -----------------
@app.get("/v1/loader/{slug}", response_class=PlainTextResponse)
async def serve_raw_loader(slug: str, request: Request, key: Optional[str] = None):
    """
    Returns the dynamic armored Luau loader for a specific script with ephemeral HMAC loader token.
    Protected by strict license key validation, O_bfuscate VM virtualization, rate limiting, and scraper detection.
    """
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()
    
    # Rate Limiting on Loader requests
    if not check_rate_limit(f"loader_ip:{client_ip}", max_requests=40, window_sec=60):
        return PlainTextResponse('error("[FleedGuard Security] Rate limit exceeded. Please wait a moment.")', status_code=429)

    # Scraper & Automated Extractor Trap
    ua = (request.headers.get("User-Agent") or "").lower()
    blocked_agents = [
        "python-requests", "curl", "wget", "postmanruntime", "aiohttp",
        "go-http-client", "scrapy", "node-fetch", "axios", "http.client",
        "urllib", "insomnia", "httpie", "libwww-perl", "apache-httpclient"
    ]
    if any(b in ua for b in blocked_agents):
        return PlainTextResponse('local p=game:GetService("Players").LocalPlayer; if p then p:Kick("[FleedGuard Security] Automated scraper / bypass attempt detected.") end', status_code=403)

    clean_slug = slug.strip().lower()
    clean_key = (key or request.headers.get("X-License-Key") or "").strip().upper()

    if not clean_key:
        # Refuse to send the loader if no key is attached
        return PlainTextResponse('local p=game:GetService("Players").LocalPlayer; if p then p:Kick("[FleedGuard Security] Access Denied: Valid license key required.") end', status_code=403)

    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.*, s.name as script_name, s.slug as script_slug, s.killswitch_active, s.killswitch_reason
            FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE UPPER(l.license_key) = ? AND LOWER(s.slug) = ?
        """, (clean_key, clean_slug))
        license_row = await cursor.fetchone()
        
        if not license_row:
            return PlainTextResponse('local p=game:GetService("Players").LocalPlayer; if p then p:Kick("[FleedGuard Security] Access Denied: Invalid license key.") end', status_code=403)

        if license_row["is_banned"]:
            return PlainTextResponse('local p=game:GetService("Players").LocalPlayer; if p then p:Kick("[FleedGuard Security] Access Denied: License key has been banned.") end', status_code=403)

        if license_row["killswitch_active"]:
            return PlainTextResponse('local p=game:GetService("Players").LocalPlayer; if p then p:Kick("[FleedGuard Security] Access Denied: Script is temporarily offline.") end', status_code=403)

        if license_row["expires_at"]:
            try:
                exp_dt = datetime.fromisoformat(license_row["expires_at"])
                if datetime.now(timezone.utc) > exp_dt:
                    return PlainTextResponse('local p=game:GetService("Players").LocalPlayer; if p then p:Kick("[FleedGuard Security] Access Denied: License key has expired.") end', status_code=403)
            except Exception:
                pass

        script_name = license_row["script_name"]
        script_slug = license_row["script_slug"]

    base_url = str(request.base_url).rstrip("/")
    if request.headers.get("X-Forwarded-Proto") and request.headers.get("X-Forwarded-Host"):
        base_url = f"{request.headers.get('X-Forwarded-Proto')}://{request.headers.get('X-Forwarded-Host')}".rstrip("/")

    # Generate ephemeral HMAC loader armor token bound to slug and short time window
    loader_token = crypto_engine.generate_loader_token(script_slug)
    armored_loader = loader_generator.generate_client_loader(base_url, script_slug, script_name, loader_token=loader_token, obfuscate=True, key=clean_key)
    return PlainTextResponse(armored_loader, media_type="text/plain")

@app.post("/v1/handshake/init")
async def handshake_init(req: HandshakeInitRequest, request: Request):
    """
    Step 1 of Handshake: Validates key, HWID binding, applies rate limits, and detects bypass fetchers.
    """
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()
    
    # Apply Rate Limiting per IP and per Key
    if not check_rate_limit(f"ip:{client_ip}", max_requests=40, window_sec=60):
        return JSONResponse(status_code=429, content={"success": False, "message": "Too many requests. Please slow down."})

    clean_key = str(req.key).strip().upper()
    if not check_rate_limit(f"key:{clean_key}", max_requests=25, window_sec=60):
        return JSONResponse(status_code=429, content={"success": False, "message": "Too many handshake attempts for this key."})

    norm_hwid = crypto_engine.normalize_hwid(req.hwid)
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = int(time.time())

    # Resolve real game name if place_id is provided and game_name is generic/empty
    if req.place_id and req.place_id > 0:
        if not req.game_name or req.game_name in ("Roblox Game", "Unknown", "Roblox Experience"):
            req.game_name = await resolve_roblox_game_name(req.place_id, req.game_name)

    async with db.get_db() as conn:
        # 1. Lookup script
        cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (req.slug,))
        script = await cursor.fetchone()
        if not script:
            return JSONResponse(status_code=404, content={"success": False, "message": "Script not found"})

        # Bypass Check 1: Check Loader Armor Token if provided (defeats bot extractors)
        if req.loader_token:
            is_token_valid = crypto_engine.verify_loader_token(req.loader_token, script["slug"])
            if not is_token_valid:
                # Log telemetry event but allow valid key-holders to solve the cryptographic challenge
                try:
                    await conn.execute("""
                        INSERT INTO execution_logs (script_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TELEMETRY_WARN', 'Loader armor token drifted or mismatched', ?)
                    """, (script["id"], clean_key, norm_hwid, client_ip, req.executor, req.roblox_username or "Unknown", req.roblox_user_id or 0, req.place_id or 0, req.job_id or "", req.game_name or "Unknown", now_iso))
                    await conn.commit()
                except Exception:
                    pass

        # Bypass Check 2: Detect spoofed or bot telemetry
        raw_hwid_lower = str(req.hwid or "").lower()
        raw_user_lower = str(req.roblox_username or "").lower()
        if any(term in raw_hwid_lower for term in ["fetcher", "dump", "intercept", "spoof", "test_hwid"]) or \
           any(term in raw_user_lower for term in ["fetcher", "dumper", "interceptor", "cracker"]):
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'BYPASS_ATTEMPT', 'Malicious extractor or dumper telemetry signature detected', ?)
            """, (script["id"], clean_key, norm_hwid, client_ip, req.executor, req.roblox_username or "Unknown", req.roblox_user_id or 0, req.place_id or 0, req.job_id or "", req.game_name or "Unknown", now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "Security Violation: Extraction attempt detected and logged."})

        # Check Global Blacklist (HWID or IP)
        cursor_bl = await conn.execute("SELECT reason FROM blacklists WHERE target_value IN (?, ?)", (norm_hwid, client_ip))
        bl_row = await cursor_bl.fetchone()
        if bl_row:
            bl_reason = bl_row["reason"] or "Globally blacklisted device/IP."
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'BLACKLISTED', ?, ?)
            """, (script["id"], clean_key, norm_hwid, client_ip, req.executor, req.roblox_username or "Unknown", req.roblox_user_id or 0, req.place_id or 0, req.job_id or "", req.game_name or "Unknown", bl_reason, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": f"Access Denied: {bl_reason}"})

        # Check Killswitch
        if script["killswitch_active"]:
            reason = script["killswitch_reason"] or "Script temporarily disabled by developer."
            await conn.execute("""
                INSERT INTO execution_logs (script_id, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'KILLSWITCH', ?, ?)
            """, (script["id"], norm_hwid, client_ip, req.executor, req.roblox_username, req.roblox_user_id, req.place_id, req.job_id, req.game_name, reason, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": f"KILLSWITCH ACTIVE: {reason}"})

        # 2. Lookup License Key
        cursor = await conn.execute("SELECT * FROM licenses WHERE UPPER(license_key) = ? AND script_id = ?", (clean_key, script["id"]))
        license_row = await cursor.fetchone()

        if not license_row:
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'INVALID_KEY', 'Key does not exist for this script', ?)
            """, (script["id"], clean_key, norm_hwid, client_ip, req.executor, req.roblox_username, req.roblox_user_id, req.place_id, req.job_id, req.game_name, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "Invalid license key"})

        # Check Banned
        if license_row["is_banned"]:
            ban_msg = license_row["ban_reason"] or "License key has been banned."
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'BANNED', ?, ?)
            """, (script["id"], license_row["id"], req.key, norm_hwid, client_ip, req.executor, req.roblox_username, req.roblox_user_id, req.place_id, req.job_id, req.game_name, ban_msg, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": f"BANNED: {ban_msg}"})

        # Check Expiration
        if license_row["expires_at"]:
            exp_dt = datetime.fromisoformat(license_row["expires_at"])
            if datetime.now(timezone.utc) > exp_dt:
                await conn.execute("""
                    INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'EXPIRED', 'License expired', ?)
                """, (script["id"], license_row["id"], req.key, norm_hwid, client_ip, req.executor, req.roblox_username, req.roblox_user_id, req.place_id, req.job_id, req.game_name, now_iso))
                await conn.commit()
                return JSONResponse(status_code=403, content={"success": False, "message": "License key has expired"})

        # Check Max Executions
        if license_row["max_executions"] != -1 and license_row["execution_count"] >= license_row["max_executions"]:
            return JSONResponse(status_code=403, content={"success": False, "message": "Execution limit reached for this key"})

        # Check Multi-Account / Multi-IP Anomaly Leak Shield
        anomaly_err = await check_and_enforce_anomalies(
            conn=conn,
            script=script,
            license_row=license_row,
            roblox_username=req.roblox_username,
            roblox_user_id=req.roblox_user_id,
            client_ip=client_ip,
            executor=req.executor or "Universal",
            place_id=req.place_id,
            job_id=req.job_id,
            game_name=req.game_name
        )
        if anomaly_err:
            return JSONResponse(status_code=403, content={"success": False, "message": anomaly_err})

        # HWID Binding / Validation
        if not license_row["hwid"]:
            # Auto-bind HWID on first execution
            await conn.execute("""
                UPDATE licenses SET hwid = ?, ip_address = ? WHERE id = ?
            """, (norm_hwid, client_ip, license_row["id"]))
            bound_hwid = norm_hwid
        elif license_row["hwid"] != norm_hwid:
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'HWID_MISMATCH', 'HWID does not match bound device', ?)
            """, (script["id"], license_row["id"], req.key, norm_hwid, client_ip, req.executor, req.roblox_username, req.roblox_user_id, req.place_id, req.job_id, req.game_name, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "HWID Mismatch! Please reset your HWID via dashboard or Discord bot."})
        else:
            bound_hwid = license_row["hwid"]

        # 3. Generate Handshake Challenge & Nonce with zero-transmission session key
        challenge = crypto_engine.create_handshake_challenge(
            script_id=script["id"],
            license_key=req.key,
            client_challenge=req.client_challenge,
            hwid=req.hwid
        )
        
        await conn.execute("""
            INSERT OR REPLACE INTO active_nonces (nonce, script_id, license_key, client_challenge, server_challenge, session_key, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            challenge["nonce"],
            script["id"],
            req.key,
            req.client_challenge,
            challenge["server_challenge"],
            challenge["session_key"],
            req.executor,
            req.roblox_username,
            req.roblox_user_id,
            req.place_id,
            req.job_id,
            req.game_name,
            challenge["expires_at"],
            now_ts
        ))
        await conn.commit()

    return {
        "success": True,
        "nonce": challenge["nonce"],
        "server_challenge": challenge["server_challenge"]
    }

@app.post("/v1/handshake/verify")
async def handshake_verify(req: HandshakeVerifyRequest, request: Request):
    """
    Step 2 of Handshake: Verifies cryptographic HMAC signature of client and delivers encrypted payload.
    The session decryption key is NEVER sent over the network.
    """
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = int(time.time())

    async with db.get_db() as conn:
        # 1. Lookup Nonce
        cursor = await conn.execute("SELECT * FROM active_nonces WHERE nonce = ?", (req.nonce,))
        nonce_row = await cursor.fetchone()
        if not nonce_row:
            return JSONResponse(status_code=400, content={"success": False, "message": "Invalid or expired session nonce"})

        # Single-use: delete nonce immediately
        await conn.execute("DELETE FROM active_nonces WHERE nonce = ?", (req.nonce,))
        await conn.commit()

        if now_ts > nonce_row["expires_at"]:
            return JSONResponse(status_code=400, content={"success": False, "message": "Session challenge expired"})

        # 2. Lookup License & Script
        cursor = await conn.execute("""
            SELECT l.*, s.raw_source, s.is_obfuscated_mode, s.name as script_name
            FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE UPPER(l.license_key) = UPPER(?) AND s.id = ?
        """, (nonce_row["license_key"], nonce_row["script_id"]))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"success": False, "message": "Authorization context lost"})

        # 2b. Re-validate license state at delivery time (init and verify are
        # separate requests; a key could be banned/expired between them).
        if row["is_banned"]:
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'BANNED', 'Key banned before payload delivery', ?)
            """, (row["script_id"], row["id"], row["license_key"], row["hwid"], client_ip, nonce_row["executor_name"], nonce_row["roblox_username"], nonce_row["roblox_user_id"], nonce_row["place_id"], nonce_row["job_id"], nonce_row["game_name"], now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "License key has been banned."})

        if row["expires_at"]:
            try:
                _exp_dt = datetime.fromisoformat(row["expires_at"])
                if datetime.now(timezone.utc) > _exp_dt:
                    return JSONResponse(status_code=403, content={"success": False, "message": "License key has expired"})
            except Exception:
                # Unparseable expiry -> fail closed.
                return JSONResponse(status_code=403, content={"success": False, "message": "License expiry invalid"})

        # 3. Verify Client Signature with bound HWID
        bound_hwid = row["hwid"]

        # STRICT HWID GATE: the raw HWID presented now MUST normalize to the exact
        # HWID bound to this license. This is the authoritative device check --
        # it lives here on the server, never on the client. No first-bind bypass
        # is possible because init already bound the HWID before issuing a nonce.
        if not bound_hwid or crypto_engine.normalize_hwid(req.hwid or "") != bound_hwid:
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'HWID_MISMATCH', 'HWID at verify does not match bound device', ?)
            """, (row["script_id"], row["id"], row["license_key"], bound_hwid, client_ip, nonce_row["executor_name"], nonce_row["roblox_username"], nonce_row["roblox_user_id"], nonce_row["place_id"], nonce_row["job_id"], nonce_row["game_name"], now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "HWID Mismatch! Please reset your HWID via dashboard or Discord bot."})

        is_valid_sig, matching_hwid = crypto_engine.verify_client_signature(
            client_signature=req.signature,
            client_challenge=req.client_challenge,
            server_challenge=nonce_row["server_challenge"],
            nonce=req.nonce,
            license_key=row["license_key"],
            hwid=bound_hwid,
            raw_hwid=req.hwid
        )

        exec_name = nonce_row["executor_name"] or "Universal"
        rbx_user = nonce_row["roblox_username"]
        rbx_uid = nonce_row["roblox_user_id"]
        place_id = nonce_row["place_id"]
        job_id = nonce_row["job_id"]
        game_name = nonce_row["game_name"]

        if not is_valid_sig:
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TAMPER_DETECTED', 'Cryptographic signature mismatch / MITM attempt', ?)
            """, (row["script_id"], row["id"], row["license_key"], bound_hwid, client_ip, exec_name, rbx_user, rbx_uid, place_id, job_id, game_name, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "Security Verification Failed: Tampered handshake"})

        # Mint the forensic watermark + short-lived execution token for the FUSED
        # in-payload guard. Both are derived from the server-only MASTER_SECRET,
        # so the client can neither forge them nor read who a build belongs to.
        watermark = crypto_engine.generate_watermark(row["license_key"], bound_hwid)
        exec_token = crypto_engine.generate_exec_token(row["license_key"], bound_hwid)

        # 4. Increment Execution Count & Record Success
        await conn.execute("""
            UPDATE licenses SET execution_count = execution_count + 1, last_executed_at = ? WHERE id = ?
        """, (now_iso, row["id"]))

        await conn.execute("""
            INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, watermark, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUCCESS', ?, ?, ?)
        """, (row["script_id"], row["id"], row["license_key"], bound_hwid, client_ip, exec_name, rbx_user, rbx_uid, place_id, job_id, game_name, f"Script delivered in-memory | watermark={watermark}", watermark, now_iso))
        await conn.commit()

        # 5. Encrypt Payload for in-memory VM unpacking using matching HWID representation
        raw_code = row["raw_source"]

        # Fetch and inject real-time dynamic feature flags for this script
        try:
            flags_cur = await conn.execute("SELECT flag_name, flag_type, flag_value, is_enabled FROM script_feature_flags WHERE script_id = ?", (row["script_id"],))
            flag_rows = await flags_cur.fetchall()
            flags_lua = []
            for f in flag_rows:
                fname = f["flag_name"]
                ftype = f["flag_type"]
                fval = f["flag_value"]
                is_en = bool(f["is_enabled"])
                if not is_en:
                    flags_lua.append(f'["{fname}"] = false')
                elif ftype == "NUMBER":
                    clean_n = fval if fval.replace(".", "", 1).isdigit() else "0"
                    flags_lua.append(f'["{fname}"] = {clean_n}')
                elif ftype == "BOOLEAN":
                    flags_lua.append(f'["{fname}"] = {"true" if fval.lower() == "true" else "false"}')
                else:
                    escaped_s = fval.replace('"', '\\"')
                    flags_lua.append(f'["{fname}"] = "{escaped_s}"')
            if flags_lua:
                flags_header = f'pcall(function() local g = getgenv and getgenv(); if g then g.__FLEED_FLAGS = {{ {", ".join(flags_lua)} }} end end);\n'
                raw_code = flags_header + raw_code
        except Exception:
            pass

        # FUSE the whitelist re-check + watermark INTO the script body, then
        # virtualize the whole thing together (below). Because the guard lives in
        # the same obfuscated blob, it cannot be stripped without breaking the
        # script, and a dumped/redistributed copy fails the runtime heartbeat.
        base_url = str(request.base_url).rstrip("/")
        if request.headers.get("X-Forwarded-Host"):
            base_url = f"{request.headers.get('X-Forwarded-Proto', 'https')}://{request.headers.get('X-Forwarded-Host')}"
        guard = crypto_engine.build_fused_guard(base_url, exec_token, watermark)
        raw_code = guard + "\n" + raw_code

        # If script is in protected mode (mode 1 or 2), apply O_bfuscate 1.1 VM virtualization.
        # FAIL CLOSED: if virtualization fails we must NOT ship raw source. A valid
        # key-holder can always read whatever the client executes, so the only
        # source protection we can guarantee is that the delivered payload is
        # virtualized bytecode, never readable source. If that guarantee cannot be
        # met, refuse to deliver.
        if row["is_obfuscated_mode"] in (1, 2):
            try:
                raw_code = crypto_engine.obfuscate_with_obfuscate(raw_code, profile="dense", fail_closed=True)
            except Exception as _obf_err:
                await conn.execute("""
                    INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, roblox_username, roblox_user_id, place_id, job_id, game_name, status, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DELIVERY_BLOCKED', 'Protected-mode obfuscation failed; refused to ship raw source', ?)
                """, (row["script_id"], row["id"], row["license_key"], bound_hwid, client_ip, exec_name, rbx_user, rbx_uid, place_id, job_id, game_name, now_iso))
                await conn.commit()
                return JSONResponse(status_code=503, content={"success": False, "message": "Protected payload temporarily unavailable. Contact the developer."})

        effective_hwid = matching_hwid or req.hwid or bound_hwid
        session_key = crypto_engine.derive_session_key(
            client_challenge=req.client_challenge,
            server_challenge=nonce_row["server_challenge"],
            nonce=req.nonce,
            license_key=row["license_key"],
            hwid=effective_hwid
        )
        encrypted_payload, auth_tag = crypto_engine.encrypt_payload(raw_code, session_key, req.nonce)

        # Track in real-time live_sessions presence table
        try:
            await conn.execute("""
                INSERT INTO live_sessions (script_id, license_key, hwid, roblox_username, roblox_user_id, game_name, place_id, job_id, executor_name, ip_address, started_at, last_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(license_key, hwid) DO UPDATE SET
                    last_heartbeat = excluded.last_heartbeat,
                    roblox_username = excluded.roblox_username,
                    roblox_user_id = excluded.roblox_user_id,
                    game_name = excluded.game_name,
                    place_id = excluded.place_id,
                    job_id = excluded.job_id,
                    executor_name = excluded.executor_name,
                    ip_address = excluded.ip_address,
                    is_kicked = 0
            """, (row["script_id"], row["license_key"], bound_hwid, rbx_user, rbx_uid, game_name, place_id, job_id, exec_name, client_ip, now_iso, now_iso))
            await conn.commit()
        except Exception:
            pass

    # Note: session_key is NEVER returned to the client
    return {
        "success": True,
        "payload": encrypted_payload,
        "auth_tag": auth_tag,
        "is_obfuscated": bool(row["is_obfuscated_mode"])
    }


class SessionHeartbeatRequest(BaseModel):
    exec_token: str
    hwid: Optional[str] = None
    wm: Optional[str] = None


@app.post("/v1/session/heartbeat")
async def session_heartbeat(req: SessionHeartbeatRequest, request: Request):
    """
    Runtime re-validation for the FUSED in-payload whitelist guard.

    This is the authoritative check and it lives on the server -- the client
    cannot forge a passing response. It is stateless: it validates the
    server-signed execution token (proving a real handshake issued it for this
    key + device moments ago), re-checks the presented HWID against the token,
    and live-checks ban/expiry so a banned or expired key dies mid-session.
    """
    ok, claims = crypto_engine.verify_exec_token(req.exec_token or "")
    if not ok or not claims:
        return JSONResponse(status_code=403, content={"success": False, "message": "Invalid or expired session token"})

    # The device running now must match the HWID the token was minted for.
    if req.hwid and claims.get("hwid"):
        presented = crypto_engine.normalize_hwid(req.hwid)
        if claims["hwid"] not in (presented, req.hwid):
            return JSONResponse(status_code=403, content={"success": False, "message": "Device mismatch"})

    # Live kill-switch: re-check license state so bans/expiry apply immediately.
    async with db.get_db() as conn:
        cursor = await conn.execute(
            "SELECT is_banned, expires_at FROM licenses WHERE UPPER(license_key) = UPPER(?)",
            (claims["key"],),
        )
        lic = await cursor.fetchone()
    if not lic:
        return JSONResponse(status_code=403, content={"success": False, "message": "Unknown license"})
    if lic["is_banned"]:
        return JSONResponse(status_code=403, content={"success": False, "message": "License banned"})
    if lic["expires_at"]:
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(lic["expires_at"]):
                return JSONResponse(status_code=403, content={"success": False, "message": "License expired"})
        except Exception:
            return JSONResponse(status_code=403, content={"success": False, "message": "License expiry invalid"})

    # Live in-game kick check: if admin issued a kick for this key or HWID within the last 60s, terminate game session immediately
    async with db.get_db() as conn:
        now_iso = datetime.now(timezone.utc).isoformat()
        k_cur = await conn.execute("""
            SELECT id, reason FROM session_kicks 
            WHERE (is_consumed IS NULL OR is_consumed = 0)
              AND created_at >= datetime('now', '-60 seconds')
              AND (
                  (target_type = 'KEY' AND UPPER(target_value) = UPPER(?))
                  OR (target_type = 'HWID' AND UPPER(target_value) = UPPER(?))
              )
            ORDER BY id DESC LIMIT 1
        """, (claims["key"], presented))
        kick_row = await k_cur.fetchone()
        if kick_row:
            try:
                # Mark this kick as consumed immediately so future joins are NOT blocked
                await conn.execute("UPDATE session_kicks SET is_consumed = 1, consumed_at = ? WHERE id = ?", (now_iso, kick_row["id"]))
                await conn.execute("UPDATE live_sessions SET is_kicked = 1 WHERE UPPER(license_key) = UPPER(?)", (claims["key"],))
                await conn.commit()
            except Exception:
                pass
            return JSONResponse(status_code=403, content={
                "success": False, 
                "action": "kick", 
                "kick_reason": kick_row["reason"] or "FleedGuard: You have been kicked from the game by the administrator."
            })


        # Update real-time heartbeat timestamp
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            await conn.execute("""
                UPDATE live_sessions 
                SET last_heartbeat = ? 
                WHERE UPPER(license_key) = UPPER(?) AND hwid = ?
            """, (now_iso, claims["key"], presented))
            await conn.commit()
        except Exception:
            pass

        # Check for active live broadcasts to dispatch to this player client
        broadcast_payload = None
        try:
            b_cur = await conn.execute("""
                SELECT b.id, b.title, b.message, b.banner_type, b.duration, b.play_sound
                FROM live_broadcasts b
                WHERE (b.expires_at IS NULL OR b.expires_at > ?)
                  AND (
                      b.target_type = 'GLOBAL'
                      OR (b.target_type = 'KEY' AND UPPER(b.target_value) = UPPER(?))
                      OR (b.target_type = 'HWID' AND UPPER(b.target_value) = UPPER(?))
                      OR (b.target_type = 'USERNAME' AND LOWER(b.target_value) = (SELECT LOWER(roblox_username) FROM live_sessions WHERE UPPER(license_key) = UPPER(?) LIMIT 1))
                      OR (b.target_type = 'SCRIPT' AND (b.script_id = (SELECT script_id FROM live_sessions WHERE UPPER(license_key) = UPPER(?) LIMIT 1) OR LOWER(b.target_value) = (SELECT LOWER(s.slug) FROM live_sessions ls JOIN scripts s ON ls.script_id = s.id WHERE UPPER(ls.license_key) = UPPER(?) LIMIT 1)))
                  )
                ORDER BY b.id DESC LIMIT 1
            """, (now_iso, claims["key"], presented, claims["key"], claims["key"], claims["key"]))
            b_row = await b_cur.fetchone()
            if b_row:
                broadcast_payload = {
                    "id": b_row["id"],
                    "title": b_row["title"] or "FleedGuard Broadcast",
                    "message": b_row["message"],
                    "banner_type": b_row["banner_type"] or "INFO",
                    "duration": b_row["duration"] or 10,
                    "play_sound": bool(b_row["play_sound"])
                }
        except Exception:
            pass

        # Check for active dynamic feature flags for this script to dispatch real-time flag changes
        flags_dict = {}
        try:
            f_cur = await conn.execute("""
                SELECT flag_name, flag_type, flag_value, is_enabled
                FROM script_feature_flags
                WHERE script_id = (SELECT script_id FROM live_sessions WHERE UPPER(license_key) = UPPER(?) LIMIT 1)
            """, (claims["key"],))
            f_rows = await f_cur.fetchall()
            for f in f_rows:
                fname = f["flag_name"]
                ftype = f["flag_type"]
                fval = f["flag_value"]
                is_en = bool(f["is_enabled"])
                if not is_en:
                    flags_dict[fname] = False
                elif ftype == "NUMBER":
                    try:
                        flags_dict[fname] = float(fval) if "." in fval else int(fval)
                    except Exception:
                        flags_dict[fname] = 0
                elif ftype == "BOOLEAN":
                    flags_dict[fname] = (fval.lower() == "true")
                else:
                    flags_dict[fname] = fval
        except Exception:
            pass

        # Check for pending live remote Luau execution payloads targeting this session/player/hub
        remote_luau_payloads = []
        try:
            p_cur = await conn.execute("""
                SELECT script_id, roblox_username, roblox_user_id, session_id
                FROM live_sessions
                WHERE UPPER(license_key) = UPPER(?)
                ORDER BY last_heartbeat DESC LIMIT 1
            """, (claims["key"],))
            p_row = await p_cur.fetchone()

            script_id_val = p_row["script_id"] if p_row else None
            r_user = (p_row["roblox_username"] or "") if p_row else ""
            r_uid = str(p_row["roblox_user_id"] or "") if p_row else ""
            s_id = (p_row["session_id"] or "") if p_row else ""
            now_iso = datetime.utcnow().isoformat()

            exec_cur = await conn.execute("""
                SELECT id, script_id, target_type, target_value, luau_code
                FROM remote_luau_queue
                WHERE status = 'PENDING'
                  AND (expires_at IS NULL OR expires_at > ?)
                  AND (
                       (target_type = 'ALL' AND (script_id IS NULL OR script_id = ?))
                    OR (target_type = 'KEY' AND UPPER(target_value) = UPPER(?))
                    OR (target_type = 'PLAYER' AND (LOWER(target_value) = LOWER(?) OR target_value = ?))
                    OR (target_type = 'SESSION' AND target_value = ?)
                  )
                ORDER BY id ASC
                LIMIT 5
            """, (now_iso, script_id_val, claims["key"], r_user, r_uid, s_id))
            exec_rows = await exec_cur.fetchall()

            for er in exec_rows:
                remote_luau_payloads.append({
                    "id": er["id"],
                    "code": er["luau_code"]
                })
                # If targeted specifically to a single target, mark EXECUTED
                if er["target_type"] in ('KEY', 'PLAYER', 'SESSION'):
                    await conn.execute("""
                        UPDATE remote_luau_queue
                        SET status = 'EXECUTED', execution_count = execution_count + 1
                        WHERE id = ?
                    """, (er["id"],))
                else:
                    await conn.execute("""
                        UPDATE remote_luau_queue
                        SET execution_count = execution_count + 1
                        WHERE id = ?
                    """, (er["id"],))
            if exec_rows:
                await conn.commit()
        except Exception as e:
            logger.error(f"Error dispatching remote luau payloads: {e}")

    # Roll the execution token so the fused guard's background re-check keeps
    # validating without needing a long-lived token. Short TTL + rolling means a
    # stolen token is useless within seconds while legit sessions refresh
    # seamlessly in the background (never blocking the game).
    new_token = crypto_engine.generate_exec_token(claims["key"], claims["hwid"])
    return {
        "success": True,
        "token": new_token,
        "broadcast": broadcast_payload,
        "flags": flags_dict,
        "remote_luau": remote_luau_payloads
    }



# ----------------- Leak Intelligence & Forensic Attribution API -----------------

@app.post("/api/audit/lookup-watermark")
async def lookup_watermark(req: WatermarkLookupRequest, user: Dict = Depends(get_current_user)):
    """
    Forensic Watermark Decoder & Attribution Tool.
    Takes a watermark hash string or a raw dumped .lua script and traces it back to the original buyer.
    """
    raw_input = req.watermark_or_source.strip()
    if not raw_input:
        raise HTTPException(status_code=400, detail="Watermark hash or script snippet required")

    # Extract watermark hash (20 hex chars or WM: pattern)
    extracted_wm = None
    import re
    wm_match = re.search(r'_FGWM\s*=\s*["\']([a-f0-9]{16,64})["\']', raw_input, re.IGNORECASE)
    if wm_match:
        extracted_wm = wm_match.group(1)
    else:
        hex_match = re.search(r'[a-f0-9]{16,40}', raw_input, re.IGNORECASE)
        if hex_match:
            extracted_wm = hex_match.group(0)
        else:
            extracted_wm = raw_input[:20]

    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.*, s.name as script_name, s.slug as script_slug,
                   e.timestamp as first_delivered, e.details, e.ip_address as deliver_ip,
                   e.watermark
            FROM execution_logs e
            JOIN licenses l ON e.license_id = l.id
            JOIN scripts s ON l.script_id = s.id
            WHERE s.user_id = ?
              AND (e.watermark = ? OR e.details LIKE ? OR UPPER(l.license_key) = UPPER(?))
            ORDER BY e.id DESC LIMIT 1
        """, (user["id"], extracted_wm, f"%watermark={extracted_wm}%", extracted_wm))
        found = await cursor.fetchone()

        if not found:
            return {
                "success": True,
                "found": False,
                "searched_watermark": extracted_wm,
                "message": "No matching license found for this watermark in your execution records."
            }

        # Gather distinct accounts & IPs that executed this license
        c2 = await conn.execute("""
            SELECT DISTINCT roblox_username, roblox_user_id
            FROM execution_logs
            WHERE license_id = ? AND roblox_user_id > 0
            LIMIT 50
        """, (found["id"],))
        accounts = [dict(r) for r in await c2.fetchall()]

        c3 = await conn.execute("""
            SELECT DISTINCT ip_address FROM execution_logs WHERE license_id = ? LIMIT 50
        """, (found["id"],))
        ips = [r["ip_address"] for r in await c3.fetchall() if r["ip_address"]]

        return {
            "success": True,
            "found": True,
            "searched_watermark": extracted_wm,
            "license": {
                "id": found["id"],
                "license_key": found["license_key"],
                "discord_id": found["discord_id"],
                "note": found["note"],
                "is_banned": bool(found["is_banned"]),
                "ban_reason": found["ban_reason"],
                "hwid": found["hwid"],
                "execution_count": found["execution_count"],
                "created_at": found["created_at"],
                "last_executed_at": found["last_executed_at"]
            },
            "script": {
                "name": found["script_name"],
                "slug": found["script_slug"]
            },
            "attribution": {
                "roblox_accounts": accounts,
                "ip_addresses": ips,
                "delivery_timestamp": found["first_delivered"]
            }
        }


@app.get("/api/audit/anomalies")
async def get_active_anomalies(user: Dict = Depends(get_current_user)):
    """
    Returns keys showing elevated multi-account sharing (>1 Roblox user)
    or multi-IP sprawl in the past 48 hours for developer investigation.
    """
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.id, l.license_key, l.note, l.is_banned, l.ban_reason, l.created_at,
                   s.name as script_name, s.slug as script_slug,
                   COUNT(DISTINCT e.roblox_user_id) as distinct_users,
                   GROUP_CONCAT(DISTINCT e.roblox_username) as user_list,
                   COUNT(DISTINCT e.ip_address) as distinct_ips,
                   MAX(e.timestamp) as last_seen
            FROM execution_logs e
            JOIN licenses l ON e.license_id = l.id
            JOIN scripts s ON l.script_id = s.id
            WHERE s.user_id = ?
              AND e.timestamp >= datetime('now', '-48 hours')
            GROUP BY l.id
            HAVING distinct_users > 1 OR distinct_ips > 2
            ORDER BY distinct_users DESC, distinct_ips DESC
            LIMIT 50
        """, (user["id"],))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


@app.post("/api/audit/ban-leaker")
async def ban_leaker(req: BanLeakerRequest, user: Dict = Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.id, l.license_key, s.name as script_name, s.discord_webhook
            FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.id = ? AND s.user_id = ?
        """, (req.license_id, user["id"]))
        license_row = await cursor.fetchone()
        if not license_row:
            raise HTTPException(status_code=404, detail="License not found")

        ban_reason = req.reason or "Banned via Forensic Watermark Trace"
        await conn.execute("UPDATE licenses SET is_banned = 1, ban_reason = ? WHERE id = ?", (ban_reason, req.license_id))
        await conn.execute("""
            INSERT INTO execution_logs (script_id, license_id, license_key, status, details, timestamp)
            VALUES ((SELECT script_id FROM licenses WHERE id = ?), ?, ?, 'BANNED', ?, ?)
        """, (req.license_id, req.license_id, license_row["license_key"], ban_reason, now_iso))
        await conn.commit()

        if license_row["discord_webhook"]:
            fields = [
                {"name": "License Key", "value": f"`{license_row['license_key']}`", "inline": True},
                {"name": "Script", "value": license_row["script_name"], "inline": True},
                {"name": "Reason", "value": ban_reason, "inline": False},
                {"name": "Action Taken", "value": "**Manually Banned via Developer Console**", "inline": False}
            ]
            await send_discord_security_alert(license_row["discord_webhook"], "License Banned (Forensic Trace)", f"License `{license_row['license_key']}` was revoked.", fields, 0xEF4444)

    return {"success": True, "message": f"License {license_row['license_key']} banned successfully."}


# ----------------- Global Blacklist (HWID & IP) Management -----------------

@app.get("/api/blacklist")
async def get_blacklists(user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM blacklists WHERE user_id = ? ORDER BY id DESC", (user["id"],))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

@app.post("/api/blacklist/add")
async def add_blacklist(req: BlacklistAddRequest, user: Dict = Depends(get_current_user)):
    val = req.target_value.strip()
    if not val:
        raise HTTPException(status_code=400, detail="Target value required")
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        await conn.execute("""
            INSERT INTO blacklists (user_id, target_type, target_value, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user["id"], req.target_type.upper(), val, req.reason or "Manual security ban", now_iso))
        await conn.commit()
    return {"success": True, "message": f"{req.target_type.upper()} {val} blacklisted"}

@app.delete("/api/blacklist/{item_id}")
async def remove_blacklist(item_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM blacklists WHERE id = ? AND user_id = ?", (item_id, user["id"]))
        await conn.commit()
    return {"success": True}


# ----------------- System Health & Diagnostics API -----------------

@app.get("/api/system/health")
async def get_system_health(user: Dict = Depends(get_current_user)):
    uptime_sec = int(time.time() - SERVER_START_TIME)
    days = uptime_sec // 86400
    hours = (uptime_sec % 86400) // 3600
    minutes = (uptime_sec % 3600) // 60
    seconds = uptime_sec % 60
    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days > 0 else f"{hours}h {minutes}m {seconds}s"

    db_path = db.db_path
    db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    if db_size_bytes > 1024 * 1024:
        db_size_str = f"{(db_size_bytes / (1024 * 1024)):.2f} MB"
    elif db_size_bytes > 1024:
        db_size_str = f"{(db_size_bytes / 1024):.1f} KB"
    else:
        db_size_str = f"{db_size_bytes} B"

    public_url = None
    url_file = os.path.join(os.path.dirname(__file__), "public_url.txt")
    if os.path.exists(url_file):
        try:
            with open(url_file, "r", encoding="utf-8") as f:
                public_url = f.read().strip()
        except Exception:
            pass

    async with db.get_db() as conn:
        c1 = await conn.execute("SELECT COUNT(*) as cnt FROM active_nonces")
        active_nonces = (await c1.fetchone())["cnt"]
        c2 = await conn.execute("SELECT COUNT(*) as cnt FROM execution_logs")
        total_logs = (await c2.fetchone())["cnt"]
        c3 = await conn.execute("SELECT COUNT(*) as cnt FROM blacklists WHERE user_id = ?", (user["id"],))
        blacklist_cnt = (await c3.fetchone())["cnt"]

    return {
        "uptime": uptime_str,
        "uptime_seconds": uptime_sec,
        "database_size": db_size_str,
        "database_size_bytes": db_size_bytes,
        "active_nonces": active_nonces,
        "total_logs": total_logs,
        "blacklisted_items": blacklist_cnt,
        "public_tunnel_url": public_url,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "wal_mode": "WAL Enabled",
        "crypto_version": "AES-256-GCM + HMAC-SHA256"
    }

@app.get("/api/system/backup")
async def download_db_backup(user: Dict = Depends(get_current_user)):
    db_path = db.db_path
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Database file not found")
    filename = f"fleedguard_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    return FileResponse(path=db_path, filename=filename, media_type="application/x-sqlite3")


# ----------------- Developer Diagnostic & Handshake Simulator Tool -----------------

@app.post("/api/tools/simulate-handshake")
async def simulate_handshake(req: SimulateHandshakeRequest, user: Dict = Depends(get_current_user)):
    """
    Diagnostic tool for testing handshake logic without a live Roblox client.
    """
    clean_slug = req.slug.strip().lower()
    clean_key = req.key.strip().upper()
    norm_hwid = crypto_engine.normalize_hwid(req.hwid or "SIMULATOR_HWID")

    async with db.get_db() as conn:
        cur = await conn.execute("SELECT * FROM scripts WHERE slug = ? AND user_id = ?", (clean_slug, user["id"]))
        script = await cur.fetchone()
        if not script:
            return {"valid": False, "reason": f"Script hub '{clean_slug}' not found under your account"}

        cur = await conn.execute("SELECT * FROM licenses WHERE script_id = ? AND UPPER(license_key) = UPPER(?)", (script["id"], clean_key))
        lic = await cur.fetchone()
        if not lic:
            return {"valid": False, "reason": f"License key '{clean_key}' does not exist for this hub"}

        if lic["is_banned"]:
            return {"valid": False, "reason": f"License key is BANNED (Reason: {lic['ban_reason'] or 'Terms violation'})"}

        if lic["expires_at"]:
            try:
                exp = datetime.fromisoformat(lic["expires_at"])
                if datetime.now(timezone.utc) > exp:
                    return {"valid": False, "reason": f"License key EXPIRED on {lic['expires_at']}"}
            except Exception:
                pass

        hwid_status = "Unbound (Will bind to first device)"
        if lic["hwid"]:
            if lic["hwid"] == norm_hwid:
                hwid_status = "Matches bound device HWID"
            else:
                hwid_status = f"HWID Mismatch (Bound: {lic['hwid'][:12]}... Presented: {norm_hwid[:12]}...)"

        return {
            "valid": True,
            "script_name": script["name"],
            "script_slug": script["slug"],
            "protection_mode": script["is_obfuscated_mode"],
            "license_key": lic["license_key"],
            "note": lic["note"],
            "discord_id": lic["discord_id"],
            "hwid_status": hwid_status,
            "execution_count": lic["execution_count"],
            "expires_at": lic["expires_at"] or "Lifetime"
        }


# ----------------- In-Game Remote Player Kicking API -----------------

@app.post("/api/sessions/kick")
async def kick_player_session(req: KickPlayerRequest, user: Dict = Depends(get_current_user)):
    """
    Remotely terminates and kicks a player from their active Roblox game session.
    """
    reason = req.reason.strip() if req.reason else "Kicked by FleedGuard Administrator"
    targets_added = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    async with db.get_db() as conn:
        if req.license_key:
            await conn.execute("""
                INSERT INTO session_kicks (user_id, target_type, target_value, reason, kicked_by, created_at)
                VALUES (?, 'KEY', ?, ?, ?, ?)
            """, (user["id"], req.license_key.strip(), reason, user["username"], now_iso))
            targets_added += 1

        if req.hwid:
            await conn.execute("""
                INSERT INTO session_kicks (user_id, target_type, target_value, reason, kicked_by, created_at)
                VALUES (?, 'HWID', ?, ?, ?, ?)
            """, (user["id"], req.hwid.strip(), reason, user["username"], now_iso))
            targets_added += 1

        if req.roblox_user_id:
            await conn.execute("""
                INSERT INTO session_kicks (user_id, target_type, target_value, reason, kicked_by, created_at)
                VALUES (?, 'USER_ID', ?, ?, ?, ?)
            """, (user["id"], str(req.roblox_user_id), reason, user["username"], now_iso))
            targets_added += 1

        if req.roblox_username:
            await conn.execute("""
                INSERT INTO session_kicks (user_id, target_type, target_value, reason, kicked_by, created_at)
                VALUES (?, 'USERNAME', ?, ?, ?, ?)
            """, (user["id"], req.roblox_username.strip(), reason, user["username"], now_iso))
            targets_added += 1

        # Lookup script_id and license_id if key provided
        script_id = None
        license_id = None
        if req.license_key:
            l_cur = await conn.execute("SELECT id, script_id FROM licenses WHERE UPPER(license_key) = UPPER(?)", (req.license_key.strip(),))
            l_row = await l_cur.fetchone()
            if l_row:
                license_id = l_row["id"]
                script_id = l_row["script_id"]

        # Also update live_sessions to mark as kicked immediately
        try:
            if req.license_key:
                await conn.execute("UPDATE live_sessions SET is_kicked = 1, kick_reason = ?, kicked_at = ?, kicked_by = ? WHERE UPPER(license_key) = UPPER(?)", (reason, now_iso, user["username"], req.license_key.strip()))
            if req.hwid:
                await conn.execute("UPDATE live_sessions SET is_kicked = 1, kick_reason = ?, kicked_at = ?, kicked_by = ? WHERE hwid = ?", (reason, now_iso, user["username"], req.hwid.strip()))
            if req.roblox_user_id:
                await conn.execute("UPDATE live_sessions SET is_kicked = 1, kick_reason = ?, kicked_at = ?, kicked_by = ? WHERE roblox_user_id = ?", (reason, now_iso, user["username"], req.roblox_user_id))
            if req.roblox_username:
                await conn.execute("UPDATE live_sessions SET is_kicked = 1, kick_reason = ?, kicked_at = ?, kicked_by = ? WHERE LOWER(roblox_username) = LOWER(?)", (reason, now_iso, user["username"], req.roblox_username.strip()))
        except Exception:
            pass

        # Also log to execution_logs as SESSION_KICKED
        await conn.execute("""
            INSERT INTO execution_logs (script_id, license_id, license_key, roblox_username, roblox_user_id, status, details, hwid, timestamp)
            VALUES (?, ?, ?, ?, ?, 'SESSION_KICKED', ?, ?, ?)
        """, (script_id, license_id, req.license_key or "N/A", req.roblox_username or "Unknown", req.roblox_user_id or 0, f"Remote Kick: {reason}", req.hwid or "", now_iso))

        await conn.commit()

    return {"success": True, "message": f"Kick command issued for player/session ({reason})"}


@app.get("/api/sessions")
@app.get("/api/sessions/active")
async def get_active_sessions(show_all: bool = False, user: Dict = Depends(get_current_user)):
    """
    Returns strictly live and idle in-game sessions with real-time heartbeat pulse.
    Filters out players who have disconnected / left the game.
    """
    now = datetime.now(timezone.utc)
    is_admin = user.get("role") == "admin"
    # Heartbeat threshold: 2.5 minutes maximum for active/idle in-game presence
    cutoff = (now - timedelta(seconds=150)).isoformat()

    async with db.get_db() as conn:
        if is_admin:
            cursor = await conn.execute("""
                SELECT l.id, l.license_key, l.hwid, l.roblox_username, l.roblox_user_id, l.game_name, l.place_id, 
                       l.job_id, l.executor_name, l.ip_address, l.started_at, l.last_heartbeat, l.is_kicked, l.kick_reason,
                       s.name as script_name, s.slug as script_slug
                FROM live_sessions l
                LEFT JOIN scripts s ON l.script_id = s.id
                WHERE l.last_heartbeat >= ? OR l.is_kicked = 1
                ORDER BY l.last_heartbeat DESC
                LIMIT 50
            """, (cutoff,))
        else:
            cursor = await conn.execute("""
                SELECT l.id, l.license_key, l.hwid, l.roblox_username, l.roblox_user_id, l.game_name, l.place_id, 
                       l.job_id, l.executor_name, l.ip_address, l.started_at, l.last_heartbeat, l.is_kicked, l.kick_reason,
                       s.name as script_name, s.slug as script_slug
                FROM live_sessions l
                JOIN scripts s ON l.script_id = s.id
                WHERE s.user_id = ? AND (l.last_heartbeat >= ? OR l.is_kicked = 1)
                ORDER BY l.last_heartbeat DESC
                LIMIT 50
            """, (user["id"], cutoff))
        rows = await cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        try:
            hb_dt = datetime.fromisoformat(d["last_heartbeat"])
            secs_ago = max(0, int((now - hb_dt).total_seconds()))
        except Exception:
            secs_ago = 999

        if d.get("is_kicked"):
            presence_state = "kicked"
            presence_label = "KICKED"
        elif secs_ago <= 35:
            presence_state = "online"
            presence_label = "ONLINE"
        elif secs_ago <= 120:
            presence_state = "idle"
            presence_label = "IDLE / IN-GAME"
        else:
            presence_state = "offline"
            presence_label = "LEFT GAME"

        # Strictly exclude players who have left the game unless show_all is requested
        if not show_all and presence_state == "offline":
            continue

        d["seconds_ago"] = secs_ago
        d["presence_state"] = presence_state
        d["presence_label"] = presence_label

        pid = d.get("place_id") or 0
        if (not d.get("game_name") or d.get("game_name") in ("Roblox Game", "Unknown", "Roblox Experience")) and pid > 0:
            if pid in game_name_cache:
                d["game_name"] = game_name_cache[pid]
            else:
                d["game_name"] = f"Place #{pid}"

        results.append(d)

    return results


@app.get("/api/kicks")
async def get_kicked_sessions(limit: int = 50, user: Dict = Depends(get_current_user)):
    """
    Returns all detected in-game kick events, disconnect reasons, and enforcement actions.
    """
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.id, l.script_id, l.license_id, l.license_key, l.hwid, l.ip_address,
                   l.executor_name, l.roblox_username, l.roblox_user_id, l.place_id, l.job_id,
                   l.game_name, l.status, l.details, l.timestamp,
                   s.name as script_name, s.slug as script_slug
            FROM execution_logs l
            LEFT JOIN scripts s ON l.script_id = s.id
            WHERE (l.status IN ('SESSION_KICKED', 'BANNED', 'BLACKLISTED', 'KILLSWITCH', 'BYPASS_ATTEMPT') 
                   OR l.details LIKE '%Kick%' 
                   OR l.details LIKE '%banned%' 
                   OR l.details LIKE '%revoked%'
                   OR l.details LIKE '%validation failed%')
              AND (s.user_id = ? OR s.user_id IS NULL)
            ORDER BY l.id DESC
            LIMIT ?
        """, (user["id"], limit))
        rows = await cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        details = d.get("details") or ""
        status = d.get("status") or "SESSION_KICKED"
        
        if "Remote Kick:" in details:
            kick_reason = details.replace("Remote Kick:", "").strip()
            source = "Admin Web Dashboard"
            icon = "fa-bolt"
            badge_class = "badge-danger"
        elif status == "BANNED" or "banned" in details.lower():
            kick_reason = details or "License key has been banned by developer"
            source = "License Revocation"
            icon = "fa-ban"
            badge_class = "badge-danger"
        elif status == "BLACKLISTED":
            kick_reason = details or "HWID / IP Blacklist Enforcement"
            source = "Global Blacklist"
            icon = "fa-shield-halved"
            badge_class = "badge-danger"
        elif status == "BYPASS_ATTEMPT":
            kick_reason = details or "Bypass / Memory Tamper Trap"
            source = "Anti-Tamper Shield"
            icon = "fa-triangle-exclamation"
            badge_class = "badge-gold"
        elif status == "KILLSWITCH":
            kick_reason = details or "Global Emergency Killswitch"
            source = "Developer Killswitch"
            icon = "fa-power-off"
            badge_class = "badge-danger"
        else:
            kick_reason = details or "Session validation failed"
            source = "Heartbeat & Fused Security Guard"
            icon = "fa-circle-xmark"
            badge_class = "badge-danger"

        pid = d.get("place_id") or 0
        if (not d.get("game_name") or d.get("game_name") in ("Roblox Game", "Unknown", "Roblox Experience")) and pid > 0:
            if pid in game_name_cache:
                d["game_name"] = game_name_cache[pid]
            else:
                d["game_name"] = f"Place #{pid}"

        d["kick_reason"] = kick_reason
        d["source"] = source
        d["icon"] = icon
        d["badge_class"] = badge_class
        
        uid = d.get("roblox_user_id") or 0
        d["avatar_url"] = f"/api/roblox/avatar/{uid}" if uid > 0 else None

        results.append(d)

    return results


# =========================================================================
# LIVE COMMUNITY CHAT WEBSOCKET & REST API
# =========================================================================

class ChatConnectionManager:
    def __init__(self):
        self.active_connections: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket, user_info: Dict):
        await websocket.accept()
        self.active_connections[websocket] = user_info
        await self.broadcast_presence()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast_presence(self):
        online_users = []
        seen_ids = set()
        for u in self.active_connections.values():
            uid = u.get("id")
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                online_users.append({
                    "id": u.get("id"),
                    "username": u.get("username", "Anonymous"),
                    "avatar_url": u.get("avatar_url"),
                    "role": u.get("role", "developer")
                })
        payload = {
            "type": "presence",
            "online_count": max(1, len(seen_ids)),
            "users": online_users
        }
        await self.broadcast(payload)

    async def broadcast(self, message: dict):
        disconnected = []
        for ws in list(self.active_connections.keys()):
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

chat_manager = ChatConnectionManager()

@app.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket, token: Optional[str] = None):
    if not token and "fleed_token" in websocket.cookies:
        token = websocket.cookies.get("fleed_token")

    user = None
    if token:
        payload = crypto_engine.verify_session_token(token)
        if payload and "sub" in payload:
            async with db.get_db() as conn:
                cursor = await conn.execute("SELECT id, username, email, role, avatar_url FROM users WHERE id = ?", (payload["sub"],))
                u_row = await cursor.fetchone()
                if u_row:
                    user = dict(u_row)

    if not user:
        guest_tag = secrets.token_hex(2)
        user = {"id": 0, "username": f"Guest_{guest_tag}", "role": "buyer", "avatar_url": None}

    await chat_manager.connect(websocket, user)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")
            if msg_type == "message":
                text = (data.get("message") or "").strip()
                channel = data.get("channel", "general")[:32]
                if text and len(text) <= 1000:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    async with db.get_db() as conn:
                        cursor = await conn.execute("""
                            INSERT INTO chat_messages (user_id, username, avatar_url, role, message, channel, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (user.get("id"), user.get("username"), user.get("avatar_url"), user.get("role", "developer"), text, channel, now_iso))
                        await conn.commit()
                        msg_id = cursor.lastrowid

                    broadcast_payload = {
                        "type": "message",
                        "id": msg_id,
                        "user_id": user.get("id"),
                        "username": user.get("username"),
                        "avatar_url": user.get("avatar_url"),
                        "role": user.get("role", "developer"),
                        "message": text,
                        "channel": channel,
                        "created_at": now_iso
                    }
                    await chat_manager.broadcast(broadcast_payload)
            elif msg_type == "typing":
                await chat_manager.broadcast({
                    "type": "typing",
                    "username": user.get("username")
                })
    except WebSocketDisconnect:
        chat_manager.disconnect(websocket)
        await chat_manager.broadcast_presence()
    except Exception:
        chat_manager.disconnect(websocket)
        await chat_manager.broadcast_presence()

@app.get("/api/chat/messages")
async def get_chat_messages(channel: str = "general", limit: int = 50, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT id, user_id, username, avatar_url, role, message, channel, created_at
            FROM chat_messages
            WHERE channel = ? AND is_deleted = 0
            ORDER BY id DESC LIMIT ?
        """, (channel, min(limit, 100)))
        rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]

@app.delete("/api/chat/messages/{message_id}")
async def delete_chat_message(message_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        if user.get("role") == "admin":
            await conn.execute("UPDATE chat_messages SET is_deleted = 1 WHERE id = ?", (message_id,))
        else:
            await conn.execute("UPDATE chat_messages SET is_deleted = 1 WHERE id = ? AND user_id = ?", (message_id, user["id"]))
        await conn.commit()
    return {"success": True}


# =========================================================================
# STAFF & RESELLER MANAGERS API
# =========================================================================

@app.get("/api/staff/managers")
async def get_staff_managers(user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT m.*, s.name as script_name
            FROM whitelist_managers m
            LEFT JOIN scripts s ON m.script_slug = s.slug
            ORDER BY m.id DESC
        """)
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]

@app.post("/api/staff/managers")
async def add_staff_manager(req: StaffManagerAddRequest, user: Dict = Depends(get_current_user)):
    clean_id = req.discord_user_id.strip("<@!&>").strip()
    clean_slug = (req.script_slug or "all").strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    async with db.get_db() as conn:
        await conn.execute("""
            INSERT INTO whitelist_managers (discord_user_id, is_role, script_slug, quota_limit, note, granted_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_user_id, script_slug, is_role, guild_id) DO UPDATE SET
                quota_limit = excluded.quota_limit,
                note = excluded.note
        """, (clean_id, req.is_role or 0, clean_slug, req.quota_limit or -1, req.note, user["username"], now_iso))
        await conn.commit()

    return {"success": True, "message": f"Successfully granted manager access to ID {clean_id} for {clean_slug}."}

@app.delete("/api/staff/managers/{manager_id}")
async def revoke_staff_manager(manager_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM whitelist_managers WHERE id = ?", (manager_id,))
        await conn.commit()
    return {"success": True, "message": "Manager access revoked."}


# =========================================================================
# LIVE REMOTE KICK & SESSION DISCONNECT API
# =========================================================================

@app.post("/api/sessions/kick")
async def execute_remote_kick(req: RemoteKickRequest, user: Dict = Depends(get_current_user)):
    clean_val = req.target_value.strip()
    target_type = req.target_type.upper()
    now_iso = datetime.now(timezone.utc).isoformat()
    reason = req.reason or "Terminated by developer"

    async with db.get_db() as conn:
        await conn.execute("""
            INSERT INTO session_kicks (user_id, target_type, target_value, reason, kicked_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user["id"], target_type, clean_val, reason, user["username"], now_iso))

        if target_type == "KEY":
            await conn.execute("UPDATE live_sessions SET is_kicked = 1, kick_reason = ?, kicked_at = ?, kicked_by = ? WHERE UPPER(license_key) = UPPER(?)", (reason, now_iso, user["username"], clean_val))
        elif target_type == "HWID":
            await conn.execute("UPDATE live_sessions SET is_kicked = 1, kick_reason = ?, kicked_at = ?, kicked_by = ? WHERE hwid = ?", (reason, now_iso, user["username"], clean_val))
        elif target_type == "USERNAME":
            await conn.execute("UPDATE live_sessions SET is_kicked = 1, kick_reason = ?, kicked_at = ?, kicked_by = ? WHERE roblox_username = ?", (reason, now_iso, user["username"], clean_val))

        await conn.commit()

    return {"success": True, "message": f"Issued instant remote kick for {target_type}: '{clean_val}'."}


# =========================================================================
# ROBLOX EXECUTOR TELEMETRY & ANALYTICS API
# =========================================================================

@app.get("/api/telemetry/executors")
async def get_executor_telemetry(user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT executor_name, COUNT(*) as count,
                   SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
                   SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) as fail_count
            FROM execution_logs
            WHERE executor_name IS NOT NULL AND executor_name != '' AND executor_name != 'Unknown'
            GROUP BY executor_name
            ORDER BY count DESC
            LIMIT 12
        """)
        rows = await cursor.fetchall()

    total_execs = sum(r["count"] for r in rows) or 1
    data = []
    for r in rows:
        d = dict(r)
        d["percentage"] = round((d["count"] / total_execs) * 100, 1)
        data.append(d)

    return {"total": total_execs, "executors": data}

@app.get("/api/telemetry/overview")
async def get_telemetry_overview(user: Dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    day_7_ago = (now - timedelta(days=7)).isoformat()

    async with db.get_db() as conn:
        # Total counts
        cur1 = await conn.execute("SELECT COUNT(*) as total_logs FROM execution_logs")
        total_logs = (await cur1.fetchone())["total_logs"]

        cur2 = await conn.execute("SELECT COUNT(*) as total_success FROM execution_logs WHERE status = 'SUCCESS'")
        total_success = (await cur2.fetchone())["total_success"]

        cur3 = await conn.execute("SELECT COUNT(*) as total_threats FROM execution_logs WHERE status IN ('BYPASS_ATTEMPT', 'TAMPER_DETECTED', 'BLACKLISTED')")
        total_threats = (await cur3.fetchone())["total_threats"]

        # Daily volume last 7 days
        cur4 = await conn.execute("""
            SELECT substr(timestamp, 1, 10) as day, COUNT(*) as count
            FROM execution_logs
            WHERE timestamp >= ?
            GROUP BY day
            ORDER BY day ASC
        """, (day_7_ago,))
        daily_rows = [dict(r) for r in await cur4.fetchall()]

    return {
        "total_logs": total_logs,
        "total_success": total_success,
        "total_threats": total_threats,
        "success_rate": round((total_success / (total_logs or 1)) * 100, 1),
        "daily_volume": daily_rows
    }


# =========================================================================
# PUBLIC BUYER PORTAL & REDEMPTION API
# =========================================================================

@app.get("/redeem", response_class=HTMLResponse)
async def public_redeem_page():
    template_path = os.path.join(TEMPLATES_DIR, "redeem.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>FleedGuard Key Redemption Portal</h1>")

@app.post("/api/public/redeem")
async def public_redeem_key(req: PublicRedeemRequest):
    clean_key = req.license_key.strip().upper()
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.*, s.name as script_name, s.slug as script_slug, s.description as script_desc
            FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE UPPER(l.license_key) = ?
        """, (clean_key,))
        lic = await cursor.fetchone()
        if not lic:
            raise HTTPException(status_code=404, detail="Invalid license key. Please verify your key and try again.")

        if lic["is_banned"]:
            raise HTTPException(status_code=403, detail=f"This license has been banned: {lic['ban_reason'] or 'Violation of terms'}")

        if req.discord_id and not lic["discord_id"]:
            clean_disc = req.discord_id.strip("<@!>")
            await conn.execute("UPDATE licenses SET discord_id = ? WHERE id = ?", (clean_disc, lic["id"]))
            await conn.commit()

    pub_url = loader_generator.get_public_url()
    loadstr = f'getgenv().FleedKey = "{lic["license_key"]}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{lic["script_slug"]}?key={lic["license_key"]}"))()'

    return {
        "status": "valid",
        "script_name": lic["script_name"],
        "script_slug": lic["script_slug"],
        "script_desc": lic["script_desc"] or "",
        "license_key": lic["license_key"],
        "discord_id": lic["discord_id"] or req.discord_id,
        "is_hwid_bound": bool(lic["hwid"]),
        "expires_at": lic["expires_at"] or "Lifetime",
        "execution_count": lic["execution_count"],
        "loadstring": loadstr
    }

@app.post("/api/public/resethwid")
async def public_reset_hwid(req: PublicResetHwidRequest):
    clean_key = req.license_key.strip().upper()
    clean_disc = req.discord_id.strip("<@!>")
    now_iso = datetime.now(timezone.utc).isoformat()

    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT * FROM licenses 
            WHERE UPPER(license_key) = ? AND discord_id = ? AND is_banned = 0
        """, (clean_key, clean_disc))
        lic = await cursor.fetchone()
        if not lic:
            raise HTTPException(status_code=400, detail="Matching license not found for this Discord ID.")

        await conn.execute("UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?", (now_iso, lic["id"]))
        await conn.commit()

    return {"success": True, "message": "HWID successfully reset! You can now execute on your new device."}


# =========================================================================
# IN-GAME ANNOUNCEMENTS & MAINTENANCE BANNERS API
# =========================================================================

@app.get("/api/scripts/{slug}/announcements")
async def get_script_announcements(slug: str, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        cur2 = await conn.execute("SELECT * FROM script_announcements WHERE script_id = ? ORDER BY id DESC", (script["id"],))
        rows = await cur2.fetchall()
    return [dict(r) for r in rows]

@app.post("/api/scripts/{slug}/announcements")
async def create_script_announcement(slug: str, req: AnnouncementCreateRequest, user: Dict = Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        # Deactivate older announcements if this is active
        if req.is_active:
            await conn.execute("UPDATE script_announcements SET is_active = 0 WHERE script_id = ?", (script["id"],))

        await conn.execute("""
            INSERT INTO script_announcements (script_id, message, banner_type, is_active, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (script["id"], req.message.strip(), req.banner_type or "INFO", req.is_active or 1, now_iso))
        await conn.commit()

    return {"success": True, "message": "In-game announcement updated successfully!"}

@app.delete("/api/scripts/{slug}/announcements/{ann_id}")
async def delete_script_announcement(slug: str, ann_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM script_announcements WHERE id = ?", (ann_id,))
        await conn.commit()
    return {"success": True, "message": "Announcement deleted."}


# =========================================================================
# LIVE IN-GAME BROADCASTS API (DIRECT TO CLIENT SCREENS)
# =========================================================================

@app.get("/api/broadcasts")
async def get_live_broadcasts(user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT b.*, s.name as script_name, s.slug as script_slug
            FROM live_broadcasts b
            LEFT JOIN scripts s ON b.script_id = s.id
            ORDER BY b.id DESC
            LIMIT 50
        """)
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]

@app.post("/api/broadcasts")
async def send_live_broadcast(req: BroadcastSendRequest, user: Dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expires_mins = max(1, min(req.expires_minutes or 60, 1440))
    expires_at = (now + timedelta(minutes=expires_mins)).isoformat()

    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Broadcast message cannot be empty.")

    target_type = (req.target_type or "GLOBAL").upper()
    target_value = (req.target_value or "").strip()

    async with db.get_db() as conn:
        # Count currently active target clients for immediate feedback
        cur_count = await conn.execute("SELECT COUNT(*) as active_cnt FROM live_sessions WHERE last_heartbeat >= datetime('now', '-2 minutes') AND is_kicked = 0")
        active_cnt = (await cur_count.fetchone())["active_cnt"]

        await conn.execute("""
            INSERT INTO live_broadcasts (user_id, script_id, target_type, target_value, title, message, banner_type, duration, play_sound, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user["id"], req.script_id, target_type, target_value, req.title or "FleedGuard Announcement", msg, req.banner_type or "INFO", req.duration or 10, req.play_sound if req.play_sound is not None else 1, now_iso, expires_at))
        await conn.commit()

    return {
        "success": True,
        "message": f"Broadcast sent! Dispatching to {active_cnt} active player client(s).",
        "active_clients": active_cnt
    }

@app.delete("/api/broadcasts/{broadcast_id}")
async def delete_live_broadcast(broadcast_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM live_broadcasts WHERE id = ?", (broadcast_id,))
        await conn.commit()
    return {"success": True, "message": "Broadcast removed from active queue."}



# =========================================================================
# REMOTE DYNAMIC FEATURE FLAGS API (AST SCAN & REAL-TIME GLOBAL TOGGLES)
# =========================================================================

@app.get("/api/scripts/{slug}/flags")
async def get_script_feature_flags(slug: str, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        cur2 = await conn.execute("""
            SELECT id, script_id, flag_name, display_name, category, flag_type, flag_value, is_enabled, source_type, line_number, updated_at
            FROM script_feature_flags 
            WHERE script_id = ? 
            ORDER BY category ASC, flag_name ASC
        """, (script["id"],))
        rows = await cur2.fetchall()
    return [dict(r) for r in rows]

@app.post("/api/scripts/{slug}/flags/auto-scan")
async def auto_scan_script_feature_flags(slug: str, user: Dict = Depends(get_current_user)):
    """
    Analyzes the Lua / Luau source code of the script using AST / pattern scanner,
    detects all toggleable features, UI components, routines, and configuration variables,
    and synchronizes them into the remote feature flags database.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id, raw_source FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        raw_source = script["raw_source"] or ""
        discovered = feature_analyzer.scan_script(raw_source)

        inserted_or_updated = 0
        for feat in discovered:
            await conn.execute("""
                INSERT INTO script_feature_flags (
                    script_id, flag_name, display_name, category, flag_type, flag_value, is_enabled, source_type, line_number, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(script_id, flag_name) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, script_feature_flags.display_name),
                    category = COALESCE(excluded.category, script_feature_flags.category),
                    source_type = excluded.source_type,
                    line_number = excluded.line_number
            """, (
                script["id"], 
                feat["flag_name"], 
                feat["display_name"], 
                feat["category"], 
                feat["flag_type"], 
                feat["default_value"], 
                feat["source_type"], 
                feat["line_number"], 
                now_iso
            ))
            inserted_or_updated += 1

        await conn.commit()

        # Return updated list of flags
        cur2 = await conn.execute("""
            SELECT id, script_id, flag_name, display_name, category, flag_type, flag_value, is_enabled, source_type, line_number, updated_at
            FROM script_feature_flags 
            WHERE script_id = ? 
            ORDER BY category ASC, flag_name ASC
        """, (script["id"],))
        rows = await cur2.fetchall()

    return {
        "success": True, 
        "discovered_count": len(discovered), 
        "message": f"Successfully analyzed script! Discovered {len(discovered)} toggleable features across {len(set(f['category'] for f in discovered))} categories.",
        "flags": [dict(r) for r in rows]
    }

@app.patch("/api/scripts/{slug}/flags/{flag_id}/toggle")
async def toggle_single_feature_flag(slug: str, flag_id: int, user: Dict = Depends(get_current_user)):
    """
    Instantly toggles a feature flag ON/OFF globally with 1-click.
    Active connected in-game Roblox players sync the updated state within seconds!
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT f.id, f.flag_name, f.display_name, f.is_enabled, s.slug
            FROM script_feature_flags f
            JOIN scripts s ON f.script_id = s.id
            WHERE f.id = ? AND s.slug = ? AND s.user_id = ?
        """, (flag_id, slug.lower(), user["id"]))
        flag = await cursor.fetchone()
        if not flag:
            raise HTTPException(status_code=404, detail="Feature flag not found.")

        new_status = 0 if flag["is_enabled"] else 1
        await conn.execute("UPDATE script_feature_flags SET is_enabled = ?, updated_at = ? WHERE id = ?", (new_status, now_iso, flag_id))
        await conn.commit()

    label = flag["display_name"] or flag["flag_name"]
    state_str = "ENABLED" if new_status == 1 else "DISABLED"
    return {
        "success": True,
        "is_enabled": new_status,
        "message": f"Feature '{label}' is now globally {state_str} for all connected players."
    }

@app.post("/api/scripts/{slug}/flags/toggle-all")
async def toggle_all_feature_flags(slug: str, req: FeatureFlagToggleAllRequest, user: Dict = Depends(get_current_user)):
    """
    Globally enables or disables all feature flags in a script hub or specific category with 1-click killswitch.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    new_val = 1 if req.action.lower() == "enable" else 0

    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        if req.category and req.category != "all":
            await conn.execute("""
                UPDATE script_feature_flags 
                SET is_enabled = ?, updated_at = ? 
                WHERE script_id = ? AND category = ?
            """, (new_val, now_iso, script["id"], req.category))
        else:
            await conn.execute("""
                UPDATE script_feature_flags 
                SET is_enabled = ?, updated_at = ? 
                WHERE script_id = ?
            """, (new_val, now_iso, script["id"]))

        await conn.commit()

    action_label = "enabled" if new_val == 1 else "disabled (Killswitch Active)"
    scope = f"in category '{req.category}'" if (req.category and req.category != 'all') else "globally"
    return {"success": True, "message": f"All feature flags {action_label} {scope}."}

@app.post("/api/scripts/{slug}/flags")
async def set_script_feature_flag(slug: str, req: FeatureFlagCreateRequest, user: Dict = Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        clean_name = feature_analyzer.clean_flag_name(req.flag_name)
        display = req.display_name or req.flag_name
        category = req.category or feature_analyzer.categorize_feature(display)

        await conn.execute("""
            INSERT INTO script_feature_flags (script_id, flag_name, display_name, category, flag_type, flag_value, is_enabled, source_type, line_number, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(script_id, flag_name) DO UPDATE SET
                display_name = excluded.display_name,
                category = excluded.category,
                flag_type = excluded.flag_type,
                flag_value = excluded.flag_value,
                is_enabled = excluded.is_enabled,
                updated_at = excluded.updated_at
        """, (script["id"], clean_name, display, category, req.flag_type or "BOOLEAN", req.flag_value.strip(), req.is_enabled if req.is_enabled is not None else 1, req.source_type or "Manual", req.line_number or 0, now_iso))
        await conn.commit()

    return {"success": True, "message": f"Feature flag '{clean_name}' saved."}

@app.delete("/api/scripts/{slug}/flags/{flag_id}")
async def delete_script_feature_flag(slug: str, flag_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM script_feature_flags WHERE id = ?", (flag_id,))
        await conn.commit()
    return {"success": True, "message": "Feature flag removed."}


# =========================================================================
# SCRIPT VERSION HISTORY & 1-CLICK ROLLBACK API
# =========================================================================

@app.get("/api/scripts/{slug}/versions")
async def get_script_versions(slug: str, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        cur2 = await conn.execute("SELECT id, script_id, version_tag, changelog, created_by, created_at FROM script_versions WHERE script_id = ? ORDER BY id DESC", (script["id"],))
        rows = await cur2.fetchall()
    return [dict(r) for r in rows]

@app.post("/api/scripts/{slug}/versions")
async def create_script_version(slug: str, req: ScriptVersionCreateRequest, user: Dict = Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        # Save snapshot
        await conn.execute("""
            INSERT INTO script_versions (script_id, version_tag, changelog, raw_source, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (script["id"], req.version_tag.strip(), req.changelog or "", req.raw_source, user["username"], now_iso))

        # Update active script source
        await conn.execute("""
            UPDATE scripts SET raw_source = ?, version = ?, updated_at = ? WHERE id = ?
        """, (req.raw_source, req.version_tag.strip(), now_iso, script["id"]))
        await conn.commit()

    return {"success": True, "message": f"Published version {req.version_tag} successfully!"}

@app.post("/api/scripts/{slug}/rollback/{version_id}")
async def rollback_script_version(slug: str, version_id: int, user: Dict = Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND user_id = ?", (slug.lower(), user["id"]))
        script = await cursor.fetchone()
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")

        cur_v = await conn.execute("SELECT raw_source, version_tag FROM script_versions WHERE id = ? AND script_id = ?", (version_id, script["id"]))
        ver = await cur_v.fetchone()
        if not ver:
            raise HTTPException(status_code=404, detail="Version snapshot not found")

        await conn.execute("""
            UPDATE scripts SET raw_source = ?, version = ?, updated_at = ? WHERE id = ?
        """, (ver["raw_source"], ver["version_tag"], now_iso, script["id"]))
        await conn.commit()

    return {"success": True, "message": f"Successfully rolled back to version {ver['version_tag']}!"}


# =========================================================================
# DISCORD WEBHOOKS CONFIGURATION API
# =========================================================================

@app.get("/api/webhooks")
async def get_discord_webhooks(user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT w.*, s.name as script_name, s.slug as script_slug
            FROM discord_webhooks w
            LEFT JOIN scripts s ON w.script_id = s.id
            WHERE w.user_id = ?
            ORDER BY w.id DESC
        """, (user["id"],))
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]

@app.post("/api/webhooks")
async def create_discord_webhook(req: DiscordWebhookCreateRequest, user: Dict = Depends(get_current_user)):
    now_iso = datetime.now(timezone.utc).isoformat()
    async with db.get_db() as conn:
        await conn.execute("""
            INSERT INTO discord_webhooks (user_id, script_id, event_type, webhook_url, is_enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user["id"], req.script_id, req.event_type.upper(), req.webhook_url.strip(), req.is_enabled or 1, now_iso))
        await conn.commit()
    return {"success": True, "message": "Webhook created successfully."}

@app.post("/api/webhooks/test")
async def test_discord_webhook(req: TestWebhookRequest, user: Dict = Depends(get_current_user)):
    url = req.webhook_url
    if not url:
        raise HTTPException(status_code=400, detail="Webhook URL required")
    await send_discord_security_alert(
        webhook_url=url,
        title="Webhook Test Event",
        description=f"This is a test notification from the FleedGuard Console sent by **{user['username']}**.",
        fields=[
            {"name": "Status", "value": "Operational", "inline": True},
            {"name": "Service", "value": "FleedGuard v2.2 Enterprise", "inline": True}
        ],
        color=0xFACC15
    )
    return {"success": True, "message": "Test webhook dispatched!"}

@app.delete("/api/webhooks/{webhook_id}")
async def delete_discord_webhook(webhook_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM discord_webhooks WHERE id = ? AND user_id = ?", (webhook_id, user["id"]))
        await conn.commit()
    return {"success": True, "message": "Webhook removed."}


# ----------------- Live Remote Luau Execution Console API -----------------

@app.post("/api/remote-exec")
async def dispatch_remote_exec(req: RemoteExecRequest, user: Dict = Depends(get_current_user)):
    """
    Queue a custom Luau payload to be dispatched to live client session(s).
    """
    code = req.luau_code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Luau code payload cannot be empty.")

    ttype = req.target_type.upper()
    if ttype not in ('ALL', 'KEY', 'PLAYER', 'SESSION'):
        raise HTTPException(status_code=400, detail="Invalid target type. Must be ALL, KEY, PLAYER, or SESSION.")

    script_id = None
    async with db.get_db() as conn:
        if req.script_slug and req.script_slug != 'all':
            s_cur = await conn.execute("SELECT id FROM scripts WHERE slug = ? AND (user_id = ? OR ? = 1)",
                                      (req.script_slug, user["id"], user.get("is_admin", 0)))
            s_row = await s_cur.fetchone()
            if s_row:
                script_id = s_row["id"]

        now_dt = datetime.utcnow()
        now_iso = now_dt.isoformat()
        ttl = max(30, min(req.ttl_seconds or 300, 86400))
        expires_at = (now_dt + timedelta(seconds=ttl)).isoformat()

        cur = await conn.execute("""
            INSERT INTO remote_luau_queue (user_id, script_id, target_type, target_value, luau_code, description, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
        """, (user["id"], script_id, ttype, req.target_value, code, req.description or "Live Remote Console Exec", now_iso, expires_at))
        await conn.commit()
        queue_id = cur.lastrowid

    target_display = f"{ttype}:{req.target_value}" if req.target_value else ttype
    logger.info(f"Admin {user['username']} queued Remote Luau Exec #{queue_id} for target [{target_display}]")

    return {
        "success": True,
        "id": queue_id,
        "target": target_display,
        "message": f"Luau payload queued successfully for [{target_display}]. Dispatched to client via protected heartbeat!"
    }


@app.get("/api/remote-exec/queue")
async def get_remote_exec_queue(user: Dict = Depends(get_current_user)):
    """
    Fetch pending and recently executed remote Luau dispatch items.
    """
    async with db.get_db() as conn:
        cur = await conn.execute("""
            SELECT q.id, q.user_id, q.script_id, q.target_type, q.target_value, 
                   q.luau_code, q.description, q.status, q.execution_count, 
                   q.created_at, q.expires_at, s.name as script_name, s.slug as script_slug,
                   u.username as creator_name
            FROM remote_luau_queue q
            LEFT JOIN scripts s ON q.script_id = s.id
            LEFT JOIN users u ON q.user_id = u.id
            ORDER BY q.id DESC
            LIMIT 50
        """)
        rows = await cur.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "target_type": r["target_type"],
                "target_value": r["target_value"],
                "luau_code": r["luau_code"],
                "description": r["description"],
                "status": r["status"],
                "execution_count": r["execution_count"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "script_name": r["script_name"] or "Global (All Scripts)",
                "script_slug": r["script_slug"] or "all",
                "creator_name": r["creator_name"] or "Administrator"
            })
        return results


@app.delete("/api/remote-exec/{exec_id}")
async def delete_remote_exec_item(exec_id: int, user: Dict = Depends(get_current_user)):
    """
    Cancel or delete a queued remote Luau execution item.
    """
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM remote_luau_queue WHERE id = ?", (exec_id,))
        await conn.commit()
    return {"success": True, "message": f"Remote Luau task #{exec_id} removed."}


@app.post("/api/remote-exec/clear")
async def clear_remote_exec_history(user: Dict = Depends(get_current_user)):
    """
    Clear executed and expired remote execution history.
    """
    async with db.get_db() as conn:
        await conn.execute("DELETE FROM remote_luau_queue WHERE status != 'PENDING'")
        await conn.commit()
    return {"success": True, "message": "Remote Luau execution history cleared."}






