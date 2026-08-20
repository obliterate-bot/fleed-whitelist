import os
import aiosqlite
import hashlib
import secrets
from datetime import datetime, timezone
from contextlib import asynccontextmanager

DATABASE_PATH = os.getenv("FLEED_WHITELIST_DB", os.path.join(os.path.dirname(os.path.dirname(__file__)), "fleed_whitelist.db"))

class WhitelistDB:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        # Ensure parent directory exists for persistent cloud volumes
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception:
                pass

    @asynccontextmanager
    async def get_db(self):
        parent_dir = os.path.dirname(self.db_path)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception:
                pass
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA foreign_keys=ON;")
            yield conn

    async def init(self):
        async with self.get_db() as conn:
            # 1. Users Table (with 2FA support)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    totp_secret TEXT,
                    two_factor_enabled INTEGER DEFAULT 0,
                    backup_codes TEXT,
                    api_key TEXT UNIQUE NOT NULL,
                    role TEXT DEFAULT 'developer',
                    is_active INTEGER DEFAULT 1,
                    discord_id TEXT,
                    avatar_url TEXT,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                )
            """)

            # Migrations for users table
            for col, col_type in [
                ("discord_id", "TEXT"),
                ("avatar_url", "TEXT")
            ]:
                try:
                    await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

            # 2. Scripts / Hubs Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    description TEXT,
                    version TEXT DEFAULT '1.0.0',
                    raw_source TEXT NOT NULL,
                    is_obfuscated_mode INTEGER DEFAULT 1, -- 1=Protected/VM, 0=Unobfuscated
                    killswitch_active INTEGER DEFAULT 0,
                    killswitch_reason TEXT,
                    custom_headers TEXT,
                    discord_webhook TEXT,
                    buyer_role_id INTEGER DEFAULT 0,
                    guild_id INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # Migrations for existing scripts table
            try:
                await conn.execute("ALTER TABLE scripts ADD COLUMN buyer_role_id INTEGER DEFAULT 0;")
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE scripts ADD COLUMN guild_id INTEGER DEFAULT 0;")
            except Exception:
                pass

            # 3. Licenses / Keys Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id INTEGER NOT NULL,
                    license_key TEXT UNIQUE NOT NULL,
                    note TEXT,
                    discord_id TEXT,
                    hwid TEXT,
                    ip_address TEXT,
                    max_executions INTEGER DEFAULT -1, -- -1 for infinite
                    execution_count INTEGER DEFAULT 0,
                    expires_at TEXT, -- NULL for lifetime, or ISO timestamp
                    is_banned INTEGER DEFAULT 0,
                    ban_reason TEXT,
                    hwid_resets_remaining INTEGER DEFAULT 3,
                    last_reset_at TEXT,
                    created_at TEXT NOT NULL,
                    last_executed_at TEXT,
                    FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
                )
            """)

            # 4. Execution Logs Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id INTEGER,
                    license_id INTEGER,
                    license_key TEXT,
                    hwid TEXT,
                    ip_address TEXT,
                    executor_name TEXT,
                    roblox_username TEXT,
                    roblox_user_id INTEGER,
                    place_id INTEGER,
                    job_id TEXT,
                    game_name TEXT,
                    status TEXT NOT NULL, -- 'SUCCESS', 'HWID_MISMATCH', 'EXPIRED', 'BANNED', 'TAMPER_DETECTED', 'KILLSWITCH'
                    details TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE SET NULL,
                    FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE SET NULL
                )
            """)

            # Migrations for execution_logs table
            for col, col_type in [
                ("roblox_username", "TEXT"),
                ("roblox_user_id", "INTEGER"),
                ("place_id", "INTEGER"),
                ("job_id", "TEXT"),
                ("game_name", "TEXT"),
                ("watermark", "TEXT")
            ]:
                try:
                    await conn.execute(f"ALTER TABLE execution_logs ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

            # 5. Handshake Nonces Table (Ephemeral Time-based Anti-Replay)
            await conn.execute("DROP TABLE IF EXISTS active_nonces;")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS active_nonces (
                    nonce TEXT PRIMARY KEY,
                    script_id INTEGER NOT NULL,
                    license_key TEXT NOT NULL,
                    client_challenge TEXT NOT NULL,
                    server_challenge TEXT NOT NULL,
                    session_key TEXT,
                    executor_name TEXT,
                    roblox_username TEXT,
                    roblox_user_id INTEGER,
                    place_id INTEGER,
                    job_id TEXT,
                    game_name TEXT,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)

            for col, col_type in [
                ("executor_name", "TEXT"),
                ("roblox_username", "TEXT"),
                ("roblox_user_id", "INTEGER"),
                ("place_id", "INTEGER"),
                ("job_id", "TEXT"),
                ("game_name", "TEXT")
            ]:
                try:
                    await conn.execute(f"ALTER TABLE active_nonces ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

            # 6. Global Blacklists (HWIDs and IPs)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS blacklists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL, -- 'HWID' or 'IP'
                    target_value TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # 7. In-Game Session Kicks Queue
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS session_kicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL, -- 'KEY', 'HWID', 'USER_ID', 'USERNAME'
                    target_value TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    kicked_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # 8. Real-Time In-Game Live Presence & Heartbeats
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS live_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id INTEGER,
                    license_key TEXT NOT NULL,
                    hwid TEXT NOT NULL,
                    roblox_username TEXT,
                    roblox_user_id INTEGER,
                    game_name TEXT,
                    place_id INTEGER,
                    job_id TEXT,
                    executor_name TEXT,
                    ip_address TEXT,
                    started_at TEXT NOT NULL,
                    last_heartbeat TEXT NOT NULL,
                    is_kicked INTEGER DEFAULT 0,
                    kick_reason TEXT,
                    kicked_at TEXT,
                    kicked_by TEXT,
                    UNIQUE(license_key, hwid) ON CONFLICT REPLACE
                )
            """)

            # Migrations for live_sessions & session_kicks
            for col, col_type in [
                ("kick_reason", "TEXT"),
                ("kicked_at", "TEXT"),
                ("kicked_by", "TEXT")
            ]:
                try:
                    await conn.execute(f"ALTER TABLE live_sessions ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

            for col, col_type in [
                ("script_id", "INTEGER"),
                ("roblox_username", "TEXT"),
                ("roblox_user_id", "INTEGER"),
                ("place_id", "INTEGER"),
                ("game_name", "TEXT")
            ]:
                try:
                    await conn.execute(f"ALTER TABLE session_kicks ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

            # 9. Delegated Whitelist Managers & Sub-Admins
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS whitelist_managers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_user_id TEXT NOT NULL,
                    is_role INTEGER DEFAULT 0,
                    script_slug TEXT DEFAULT 'all',
                    guild_id TEXT,
                    granted_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(discord_user_id, script_slug, is_role, guild_id) ON CONFLICT REPLACE
                )
            """)

            # Indices for ultra-fast lookup
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_licenses_key ON licenses(license_key);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_licenses_script ON licenses(script_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_scripts_slug ON scripts(slug);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON execution_logs(timestamp);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_watermark ON execution_logs(watermark);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_key_time ON execution_logs(license_key, timestamp);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_status_time ON execution_logs(status, timestamp);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_blacklists_val ON blacklists(target_value);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_kicks_val ON session_kicks(target_value);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_live_hb ON live_sessions(last_heartbeat);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_wl_mgr_user ON whitelist_managers(discord_user_id, script_slug);")
            await conn.commit()

db = WhitelistDB()
