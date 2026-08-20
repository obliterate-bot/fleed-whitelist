import os
import json
import time
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status, Header
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import db
from .crypto_engine import crypto_engine
from .loader_generator import loader_generator

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

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
    yield

app = FastAPI(
    title="FleedGuard Whitelist & Security API",
    version="2.0.0",
    description="Enterprise-grade Roblox script whitelisting and protection service.",
    lifespan=lifespan
)

# CORS middleware for developer integrations & web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# Executor Handshake Models
class HandshakeInitRequest(BaseModel):
    slug: str
    key: str
    hwid: str
    client_challenge: str
    executor: Optional[str] = "Universal"

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
        "discord_id": user["discord_id"] if "discord_id" in user.keys() else None,
        "created_at": user["created_at"]
    }

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
    async with db.get_db() as conn:
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

# ----------------- License / Key Management API -----------------
@app.get("/api/scripts/{script_id}/licenses")
async def list_licenses(script_id: int, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.* FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.script_id = ? AND s.user_id = ?
            ORDER BY l.id DESC
        """, (script_id, user["id"]))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

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
            # Check if admin or create placeholder script
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
        # Verify script ownership
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
        for _ in range(max(1, min(req.count, 100))):
            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, note, max_executions, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (req.script_id, key, req.note, req.max_executions, expires_at, now_iso))
            generated_keys.append(key)

        await conn.commit()

    return {"success": True, "count": len(generated_keys), "keys": generated_keys}

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
    async with db.get_db() as conn:
        # Total scripts
        c1 = await conn.execute("SELECT COUNT(*) as cnt FROM scripts WHERE user_id = ?", (user["id"],))
        scripts_cnt = (await c1.fetchone())["cnt"]

        # Total licenses & active
        c2 = await conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN is_banned = 0 THEN 1 ELSE 0 END) as active
            FROM licenses WHERE script_id IN (SELECT id FROM scripts WHERE user_id = ?)
        """, (user["id"],))
        lic_row = await c2.fetchone()
        total_licenses = lic_row["total"] if lic_row else 0
        active_licenses = lic_row["active"] if lic_row and lic_row["active"] else 0

        # Total executions & blocked
        c3 = await conn.execute("""
            SELECT COUNT(*) as total_execs,
                   SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_execs,
                   SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) as blocked_execs
            FROM execution_logs WHERE script_id IN (SELECT id FROM scripts WHERE user_id = ?)
        """, (user["id"],))
        exec_row = await c3.fetchone()
        total_execs = exec_row["total_execs"] if exec_row else 0
        blocked_execs = exec_row["blocked_execs"] if exec_row and exec_row["blocked_execs"] else 0

        return {
            "total_scripts": scripts_cnt,
            "total_licenses": total_licenses,
            "active_licenses": active_licenses,
            "total_executions": total_execs,
            "blocked_attacks": blocked_execs
        }

@app.get("/api/logs")
async def get_logs(limit: int = 50, user: Dict = Depends(get_current_user)):
    async with db.get_db() as conn:
        cursor = await conn.execute("""
            SELECT l.*, s.name as script_name
            FROM execution_logs l
            JOIN scripts s ON l.script_id = s.id
            WHERE s.user_id = ?
            ORDER BY l.id DESC LIMIT ?
        """, (user["id"], limit))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

# ----------------- Roblox Executor Loader & Handshake API -----------------
@app.get("/v1/loader/{slug}", response_class=PlainTextResponse)
async def serve_raw_loader(slug: str, request: Request):
    """
    Returns the dynamic Luau loader for a specific script.
    """
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT name, slug FROM scripts WHERE slug = ?", (slug,))
        script = await cursor.fetchone()
        if not script:
            return "-- [FleedGuard] ERROR: Script not found or removed."

    base_url = str(request.base_url)
    if request.headers.get("X-Forwarded-Proto") and request.headers.get("X-Forwarded-Host"):
        base_url = f"{request.headers.get('X-Forwarded-Proto')}://{request.headers.get('X-Forwarded-Host')}"

    return loader_generator.generate_client_loader(base_url, script["slug"], script["name"])

@app.post("/v1/handshake/init")
async def handshake_init(req: HandshakeInitRequest, request: Request):
    """
    Step 1 of Handshake: Validates key, HWID binding, and creates dynamic challenge.
    """
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "127.0.0.1").split(",")[0].strip()
    norm_hwid = crypto_engine.normalize_hwid(req.hwid)
    now_iso = datetime.now(timezone.utc).isoformat()
    now_ts = int(time.time())

    async with db.get_db() as conn:
        # 1. Lookup script
        cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (req.slug,))
        script = await cursor.fetchone()
        if not script:
            return JSONResponse(status_code=404, content={"success": False, "message": "Script not found"})

        # Check Killswitch
        if script["killswitch_active"]:
            reason = script["killswitch_reason"] or "Script temporarily disabled by developer."
            await conn.execute("""
                INSERT INTO execution_logs (script_id, hwid, ip_address, executor_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, 'KILLSWITCH', ?, ?)
            """, (script["id"], norm_hwid, client_ip, req.executor, reason, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": f"KILLSWITCH ACTIVE: {reason}"})

        # 2. Lookup License Key (Case-insensitive & clean)
        clean_key = str(req.key).strip().upper()
        cursor = await conn.execute("SELECT * FROM licenses WHERE UPPER(license_key) = ? AND script_id = ?", (clean_key, script["id"]))
        license_row = await cursor.fetchone()
        if not license_row:
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_key, hwid, ip_address, executor_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, 'INVALID_KEY', 'Key does not exist for this script', ?)
            """, (script["id"], clean_key, norm_hwid, client_ip, req.executor, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "Invalid license key"})

        # Check Banned
        if license_row["is_banned"]:
            ban_msg = license_row["ban_reason"] or "License key has been banned."
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, 'BANNED', ?, ?)
            """, (script["id"], license_row["id"], req.key, norm_hwid, client_ip, req.executor, ban_msg, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": f"BANNED: {ban_msg}"})

        # Check Expiration
        if license_row["expires_at"]:
            exp_dt = datetime.fromisoformat(license_row["expires_at"])
            if datetime.now(timezone.utc) > exp_dt:
                await conn.execute("""
                    INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, status, details, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, 'EXPIRED', 'License expired', ?)
                """, (script["id"], license_row["id"], req.key, norm_hwid, client_ip, req.executor, now_iso))
                await conn.commit()
                return JSONResponse(status_code=403, content={"success": False, "message": "License key has expired"})

        # Check Max Executions
        if license_row["max_executions"] != -1 and license_row["execution_count"] >= license_row["max_executions"]:
            return JSONResponse(status_code=403, content={"success": False, "message": "Execution limit reached for this key"})

        # HWID Binding / Validation
        if not license_row["hwid"]:
            # Auto-bind HWID on first execution
            await conn.execute("""
                UPDATE licenses SET hwid = ?, ip_address = ? WHERE id = ?
            """, (norm_hwid, client_ip, license_row["id"]))
        elif license_row["hwid"] != norm_hwid:
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, executor_name, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, 'HWID_MISMATCH', 'HWID does not match bound device', ?)
            """, (script["id"], license_row["id"], req.key, norm_hwid, client_ip, req.executor, now_iso))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "HWID Mismatch! Please reset your HWID via dashboard or Discord bot."})

        # 3. Generate Handshake Challenge & Nonce
        challenge = crypto_engine.create_handshake_challenge(script["id"], req.key, req.client_challenge)
        
        await conn.execute("""
            INSERT OR REPLACE INTO active_nonces (nonce, script_id, license_key, client_challenge, server_challenge, session_key, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            challenge["nonce"],
            script["id"],
            req.key,
            req.client_challenge,
            challenge["server_challenge"],
            challenge["session_key"],
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
    Step 2 of Handshake: Verifies HMAC signature of client and delivers encrypted payload.
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

        if now_ts > nonce_row["expires_at"]:
            await conn.execute("DELETE FROM active_nonces WHERE nonce = ?", (req.nonce,))
            await conn.commit()
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

        # 3. Verify Client Signature with bound HWID
        bound_hwid = row["hwid"]
        is_valid_sig = crypto_engine.verify_client_signature(
            client_signature=req.signature,
            client_challenge=req.client_challenge,
            server_challenge=nonce_row["server_challenge"],
            nonce=req.nonce,
            license_key=row["license_key"],
            hwid=bound_hwid,
            raw_hwid=req.hwid
        )

        if not is_valid_sig:
            await conn.execute("""
                INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, status, details, timestamp)
                VALUES (?, ?, ?, ?, ?, 'TAMPER_DETECTED', 'Cryptographic signature mismatch / MITM attempt', ?)
            """, (row["script_id"], row["id"], row["license_key"], bound_hwid, client_ip, now_iso))
            await conn.execute("DELETE FROM active_nonces WHERE nonce = ?", (req.nonce,))
            await conn.commit()
            return JSONResponse(status_code=403, content={"success": False, "message": "Security Verification Failed: Tampered handshake"})

        # 4. Consume Nonce (Single use protection)
        await conn.execute("DELETE FROM active_nonces WHERE nonce = ?", (req.nonce,))

        # 5. Increment Execution Count & Record Success
        await conn.execute("""
            UPDATE licenses SET execution_count = execution_count + 1, last_executed_at = ? WHERE id = ?
        """, (now_iso, row["id"]))

        await conn.execute("""
            INSERT INTO execution_logs (script_id, license_id, license_key, hwid, ip_address, status, details, timestamp)
            VALUES (?, ?, ?, ?, ?, 'SUCCESS', 'Script decrypted and executed in-memory', ?)
        """, (row["script_id"], row["id"], row["license_key"], bound_hwid, client_ip, now_iso))
        await conn.commit()

        # 6. Encrypt Payload for in-memory VM unpacking
        raw_code = row["raw_source"]
        session_key = nonce_row["session_key"]
        encrypted_payload, auth_tag = crypto_engine.encrypt_payload(raw_code, session_key, req.nonce)

    return {
        "success": True,
        "payload": encrypted_payload,
        "session_key": session_key,
        "auth_tag": auth_tag,
        "is_obfuscated": bool(row["is_obfuscated_mode"])
    }
