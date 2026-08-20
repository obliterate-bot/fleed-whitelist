import os
import aiosqlite
import config

class Database:
    def __init__(self, db_path=config.DATABASE_PATH):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            
            # settings & prefixes
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    prefix TEXT,
                    embed_color INTEGER,
                    vcrole_id INTEGER,
                    muted_id INTEGER,
                    rmuted_id INTEGER,
                    imuted_id INTEGER,
                    jail_id INTEGER,
                    dj_id INTEGER,
                    modlog_id INTEGER,
                    base_role_id INTEGER,
                    tags_enabled INTEGER DEFAULT 1,
                    quote_enabled INTEGER DEFAULT 1,
                    quote_redirect_channel INTEGER DEFAULT 0,
                    autoplay INTEGER DEFAULT 0,
                    twentyfour_seven INTEGER DEFAULT 0,
                    disable_custom_fms INTEGER DEFAULT 0,
                    snipe_protect INTEGER DEFAULT 0
                )
            """)
            
            # migrations for existing tables
            try:
                await db.execute("ALTER TABLE guild_settings ADD COLUMN muted_id INTEGER;")
            except Exception:
                pass
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    prefix TEXT,
                    timezone TEXT,
                    afk_message TEXT,
                    afk_time INTEGER DEFAULT 0,
                    lastfm_username TEXT,
                    lastfm_color TEXT,
                    lastfm_custom_cmd TEXT
                )
            """)

            # auto modules
            await db.execute("""
                CREATE TABLE IF NOT EXISTS command_channels (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    PRIMARY KEY (guild_id, channel_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS autoroles (
                    guild_id INTEGER,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS badge_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    award_channel INTEGER DEFAULT 0,
                    message TEXT
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS badge_roles (
                    guild_id INTEGER,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS vanity_config (
                    guild_id INTEGER PRIMARY KEY,
                    vanity TEXT,
                    award_channel INTEGER DEFAULT 0,
                    strict INTEGER DEFAULT 0,
                    message TEXT
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS vanity_roles (
                    guild_id INTEGER,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tracking_channels (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    track_type TEXT DEFAULT 'all',
                    PRIMARY KEY (guild_id, channel_id, track_type)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS pingonjoin (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    threshold INTEGER DEFAULT 0,
                    message TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS autoreactions (
                    guild_id INTEGER,
                    keyword TEXT,
                    reaction TEXT,
                    PRIMARY KEY (guild_id, keyword)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS autoresponders (
                    guild_id INTEGER,
                    trigger TEXT,
                    response TEXT,
                    PRIMARY KEY (guild_id, trigger)
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS autoresponder_roles (
                    guild_id INTEGER,
                    trigger TEXT,
                    role_id INTEGER,
                    action_type TEXT,
                    PRIMARY KEY (guild_id, trigger, role_id, action_type)
                )
            """)

            # developer & blacklist & premium
            await db.execute("""
                CREATE TABLE IF NOT EXISTS blacklists (
                    target_id INTEGER PRIMARY KEY,
                    target_type TEXT,
                    reason TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS premium (
                    target_id INTEGER PRIMARY KEY,
                    target_type TEXT,
                    expires_at INTEGER DEFAULT 0
                )
            """)

            # economy
            await db.execute("""
                CREATE TABLE IF NOT EXISTS economy (
                    guild_id INTEGER,
                    user_id INTEGER,
                    wallet INTEGER DEFAULT 0,
                    bank INTEGER DEFAULT 0,
                    job TEXT,
                    daily_cooldown INTEGER DEFAULT 0,
                    work_cooldown INTEGER DEFAULT 0,
                    crime_cooldown INTEGER DEFAULT 0,
                    rob_cooldown INTEGER DEFAULT 0,
                    last_open INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            try:
                await db.execute("ALTER TABLE economy ADD COLUMN last_open INTEGER DEFAULT 0")
            except Exception:
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS economy_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    mode TEXT DEFAULT 'guild',
                    preset TEXT DEFAULT 'default'
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS economy_shop (
                    guild_id INTEGER,
                    name TEXT,
                    price INTEGER,
                    role_id INTEGER DEFAULT 0,
                    description TEXT,
                    PRIMARY KEY (guild_id, name)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS economy_jobs (
                    guild_id INTEGER,
                    name TEXT,
                    min_payout INTEGER,
                    max_payout INTEGER,
                    description TEXT,
                    PRIMARY KEY (guild_id, name)
                )
            """)

            # fun & gangs & birthdays & uwulock
            await db.execute("""
                CREATE TABLE IF NOT EXISTS gangs (
                    guild_id INTEGER,
                    gang_name TEXT,
                    owner_id INTEGER,
                    banner_url TEXT,
                    PRIMARY KEY (guild_id, gang_name)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS gang_members (
                    guild_id INTEGER,
                    gang_name TEXT,
                    user_id INTEGER,
                    is_admin INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS diary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    content TEXT,
                    created_at INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS uwulock (
                    guild_id INTEGER,
                    user_id INTEGER,
                    protected INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS birthdays (
                    guild_id INTEGER,
                    user_id INTEGER,
                    month INTEGER,
                    day INTEGER,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS birthday_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    role_id INTEGER,
                    locked INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS vape (
                    guild_id INTEGER PRIMARY KEY,
                    holder_id INTEGER,
                    flavor TEXT DEFAULT 'mint',
                    hits INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS blunt (
                    guild_id INTEGER PRIMARY KEY,
                    sparked INTEGER DEFAULT 0,
                    taps INTEGER DEFAULT 0
                )
            """)

            # levels
            await db.execute("""
                CREATE TABLE IF NOT EXISTS levels (
                    guild_id INTEGER,
                    user_id INTEGER,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS level_config (
                    guild_id INTEGER PRIMARY KEY,
                    rate REAL DEFAULT 1.0,
                    stack_roles INTEGER DEFAULT 0,
                    message TEXT,
                    channel_id INTEGER
                )
            """)
            try:
                await db.execute("ALTER TABLE level_config ADD COLUMN channel_id INTEGER")
            except Exception:
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS level_roles (
                    guild_id INTEGER,
                    rank INTEGER,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, rank)
                )
            """)

            # logs
            await db.execute("""
                CREATE TABLE IF NOT EXISTS logs_config (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    event_type TEXT,
                    color INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, channel_id, event_type)
                )
            """)

            # tickets
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    guild_id INTEGER,
                    channel_id INTEGER PRIMARY KEY,
                    opener_id INTEGER,
                    claimed_by INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'open',
                    created_at INTEGER
                )
            """)

            # moderation
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    timestamp INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS warn_punishments (
                    guild_id INTEGER,
                    threshold INTEGER,
                    punishment_type TEXT,
                    duration INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, threshold)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS strikes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    timestamp INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS strike_punishments (
                    guild_id INTEGER,
                    threshold INTEGER,
                    punishment_type TEXT,
                    duration INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, threshold)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS modhistory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    moderator_id INTEGER,
                    action TEXT,
                    reason TEXT,
                    timestamp INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS forced_nicknames (
                    guild_id INTEGER,
                    user_id INTEGER,
                    nickname TEXT,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS lockdown_ignored (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    PRIMARY KEY (guild_id, channel_id)
                )
            """)

            # security & antinuke & antiraid & filters
            await db.execute("""
                CREATE TABLE IF NOT EXISTS antinuke_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    ban_limit INTEGER DEFAULT 3,
                    kick_limit INTEGER DEFAULT 3,
                    role_limit INTEGER DEFAULT 3,
                    channel_limit INTEGER DEFAULT 3,
                    webhook_limit INTEGER DEFAULT 3,
                    emoji_limit INTEGER DEFAULT 3,
                    sticker_limit INTEGER DEFAULT 3,
                    botadd INTEGER DEFAULT 1,
                    vanity INTEGER DEFAULT 1,
                    guildupdate INTEGER DEFAULT 1,
                    integration INTEGER DEFAULT 1
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS antinuke_whitelist (
                    guild_id INTEGER,
                    user_id INTEGER,
                    is_admin INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS antiraid_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    massjoin INTEGER DEFAULT 0,
                    massmention INTEGER DEFAULT 0,
                    avatar INTEGER DEFAULT 0,
                    age INTEGER DEFAULT 0,
                    unverifiedbots INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS antiraid_patterns (
                    guild_id INTEGER,
                    pattern TEXT PRIMARY KEY
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS filter_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    strikes_enabled INTEGER DEFAULT 0,
                    strikes_cap INTEGER DEFAULT 5,
                    strikes_decay INTEGER DEFAULT 24
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS filter_words (
                    guild_id INTEGER,
                    word TEXT,
                    is_whitelist INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, word, is_whitelist)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS filter_regex (
                    guild_id INTEGER,
                    name TEXT,
                    pattern TEXT,
                    PRIMARY KEY (guild_id, name)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS filter_exempts (
                    guild_id INTEGER,
                    role_id INTEGER,
                    filter_type TEXT,
                    PRIMARY KEY (guild_id, role_id, filter_type)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS strikes (
                    guild_id INTEGER,
                    user_id INTEGER,
                    strikes INTEGER DEFAULT 0,
                    last_strike INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            # server features
            await db.execute("""
                CREATE TABLE IF NOT EXISTS welcome_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    message TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS leave_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    message TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS booster_roles (
                    guild_id INTEGER,
                    user_id INTEGER,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS booster_shares (
                    guild_id INTEGER,
                    owner_id INTEGER,
                    user_id INTEGER,
                    PRIMARY KEY (guild_id, owner_id, user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS booster_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    base_role INTEGER DEFAULT 0,
                    limit_count INTEGER DEFAULT 249,
                    max_shares INTEGER DEFAULT 5,
                    hoist INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS starboards (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    emoji TEXT,
                    threshold INTEGER DEFAULT 3,
                    color INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, emoji)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS invoke_messages (
                    guild_id INTEGER,
                    command_name TEXT,
                    msg_type TEXT,
                    message TEXT,
                    PRIMARY KEY (guild_id, command_name, msg_type)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS sticky_messages (
                    guild_id INTEGER,
                    channel_id INTEGER PRIMARY KEY,
                    content TEXT,
                    last_message_id INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS button_roles (
                    guild_id INTEGER,
                    message_id INTEGER,
                    channel_id INTEGER,
                    role_id INTEGER,
                    style TEXT DEFAULT 'secondary',
                    emoji TEXT,
                    label TEXT,
                    PRIMARY KEY (guild_id, message_id, role_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS reaction_roles (
                    guild_id INTEGER,
                    message_id INTEGER,
                    channel_id INTEGER,
                    role_id INTEGER,
                    emoji TEXT,
                    PRIMARY KEY (guild_id, message_id, emoji)
                )
            """)

            # voicemaster
            await db.execute("""
                CREATE TABLE IF NOT EXISTS voicemaster_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    category_id INTEGER,
                    interface_id INTEGER DEFAULT 0,
                    default_name TEXT DEFAULT "{user}'s channel",
                    default_bitrate INTEGER DEFAULT 64000,
                    default_role INTEGER DEFAULT 0,
                    joinrole INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS voicemaster_channels (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    owner_id INTEGER
                )
            """)

            # tickets - old schema removed, see updated schema below

            # snipes
            await db.execute("""
                CREATE TABLE IF NOT EXISTS name_history (
                    user_id INTEGER,
                    old_name TEXT,
                    timestamp INTEGER
                )
            """)

            # restrictions & disables
            await db.execute("""
                CREATE TABLE IF NOT EXISTS disabled_commands (
                    guild_id INTEGER,
                    command_name TEXT,
                    target_id INTEGER,
                    target_type TEXT,
                    PRIMARY KEY (guild_id, command_name, target_id, target_type)
                )
            """)

            # command access and server feature state.  These tables replace
            # older command handlers that acknowledged changes without saving
            # or enforcing them.
            await db.execute("""
                CREATE TABLE IF NOT EXISTS command_restrictions (
                    guild_id INTEGER,
                    command_name TEXT,
                    role_id INTEGER,
                    action_type TEXT CHECK(action_type IN ('allow', 'deny')),
                    PRIMARY KEY (guild_id, command_name, role_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    user_id INTEGER,
                    task TEXT NOT NULL,
                    remind_at INTEGER NOT NULL,
                    kind TEXT DEFAULT 'reminder'
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bump_reminders (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    next_bump INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS disabled_command_whitelist (
                    guild_id INTEGER,
                    command_name TEXT,
                    user_id INTEGER,
                    PRIMARY KEY (guild_id, command_name, user_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS award_roles (
                    guild_id INTEGER,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS staff_roles (
                    guild_id INTEGER,
                    role_id INTEGER,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pagination_pages (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER,
                    page_number INTEGER,
                    content TEXT NOT NULL,
                    current_page INTEGER DEFAULT 1,
                    PRIMARY KEY (guild_id, message_id, page_number)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS confessions_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER DEFAULT 0,
                    upvote TEXT DEFAULT '⬆️',
                    downvote TEXT DEFAULT '⬇️'
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS confession_entries (
                    guild_id INTEGER,
                    confession_number INTEGER,
                    author_id INTEGER,
                    message_id INTEGER DEFAULT 0,
                    created_at INTEGER,
                    PRIMARY KEY (guild_id, confession_number)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS confession_muted (
                    guild_id INTEGER,
                    user_id INTEGER,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS confession_blacklist (
                    guild_id INTEGER,
                    word TEXT,
                    PRIMARY KEY (guild_id, word)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_counters (
                    guild_id INTEGER,
                    channel_id INTEGER PRIMARY KEY,
                    metric TEXT NOT NULL,
                    channel_kind TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS booster_filters (
                    guild_id INTEGER,
                    word TEXT,
                    PRIMARY KEY (guild_id, word)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS autopfp_config (
                    guild_id INTEGER,
                    channel_id INTEGER PRIMARY KEY,
                    interval_minutes INTEGER DEFAULT 60,
                    last_posted INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS custom_aliases (
                    guild_id INTEGER,
                    shortcut TEXT,
                    command_text TEXT NOT NULL,
                    PRIMARY KEY (guild_id, shortcut)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS starboard_ignored (
                    guild_id INTEGER,
                    channel_id INTEGER,
                    PRIMARY KEY (guild_id, channel_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS starboard_posts (
                    guild_id INTEGER,
                    source_message_id INTEGER,
                    board_message_id INTEGER,
                    emoji TEXT,
                    PRIMARY KEY (guild_id, source_message_id, emoji)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_backups (
                    guild_id INTEGER,
                    backup_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    snapshot_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS boost_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER DEFAULT 0,
                    message TEXT DEFAULT 'thank you {user} for boosting {guild.name}!'
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS role_snapshots (
                    guild_id INTEGER,
                    user_id INTEGER,
                    role_ids TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS deny_permissions (
                    guild_id INTEGER,
                    permission_name TEXT,
                    PRIMARY KEY (guild_id, permission_name)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS protected_members (
                    guild_id INTEGER,
                    user_id INTEGER,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS fake_permissions (
                    guild_id INTEGER,
                    role_id INTEGER,
                    permissions TEXT NOT NULL,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS security_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    incident_type TEXT,
                    actor_id INTEGER DEFAULT 0,
                    details TEXT,
                    created_at INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS lastfm_friends (
                    user_id INTEGER,
                    friend_id INTEGER,
                    PRIMARY KEY (user_id, friend_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS lastfm_preferences (
                    user_id INTEGER PRIMARY KEY,
                    embed_mode TEXT,
                    upvote TEXT,
                    downvote TEXT
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS voicemaster_config (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    category_id INTEGER,
                    interface_id INTEGER,
                    default_name TEXT DEFAULT '{user}''s channel',
                    default_bitrate INTEGER DEFAULT 64000,
                    default_role INTEGER DEFAULT 0,
                    default_region TEXT DEFAULT 'us-east',
                    joinrole INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS voicemaster_channels (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER,
                    owner_id INTEGER,
                    locked INTEGER DEFAULT 0,
                    hidden INTEGER DEFAULT 0
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS jailed_users (
                    guild_id INTEGER,
                    user_id INTEGER,
                    roles TEXT,
                    jailed_at INTEGER,
                    expires_at INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            # drop old ticket tables if schema is outdated, then recreate
            try:
                async with db.execute("PRAGMA table_info(ticket_config)") as cursor:
                    cols = [row[1] async for row in cursor]
                if cols and "support_role_ids" not in cols:
                    await db.execute("DROP TABLE IF EXISTS ticket_config")
                    await db.execute("DROP TABLE IF EXISTS tickets")
            except Exception:
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_config (
                    guild_id INTEGER PRIMARY KEY,
                    category_id INTEGER,
                    closed_category_id INTEGER,
                    transcript_channel_id INTEGER,
                    support_role_ids TEXT DEFAULT '',
                    ticket_counter INTEGER DEFAULT 0,
                    panel_title TEXT DEFAULT 'support tickets',
                    panel_desc TEXT DEFAULT 'select a category below or click a button to open a private support ticket.',
                    panel_color INTEGER DEFAULT 2829617
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER UNIQUE,
                    opener_id INTEGER,
                    ticket_num INTEGER DEFAULT 1,
                    category TEXT DEFAULT 'general',
                    topic TEXT DEFAULT 'no topic provided',
                    claimed_by INTEGER,
                    status TEXT DEFAULT 'open',
                    created_at INTEGER,
                    closed_at INTEGER,
                    closed_by INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    message_id INTEGER UNIQUE,
                    host_id INTEGER,
                    prize TEXT,
                    description TEXT DEFAULT '',
                    winner_count INTEGER DEFAULT 1,
                    required_role_id INTEGER DEFAULT 0,
                    ends_at INTEGER,
                    ended INTEGER DEFAULT 0,
                    winners TEXT DEFAULT '',
                    entries TEXT DEFAULT '',
                    created_at INTEGER
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS ai_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    channel_id INTEGER DEFAULT 0,
                    model TEXT DEFAULT 'auto/fast',
                    system_prompt TEXT DEFAULT '',
                    respond_on_mention INTEGER DEFAULT 1,
                    respond_on_reply INTEGER DEFAULT 1,
                    respond_in_tickets INTEGER DEFAULT 0,
                    ping_staff_in_tickets INTEGER DEFAULT 0,
                    max_tokens INTEGER DEFAULT 500
                )
            """)

            # Migration: check for new columns in ai_config
            try:
                async with db.execute("PRAGMA table_info(ai_config)") as cursor:
                    ai_cols = [row[1] async for row in cursor]
                if "respond_in_tickets" not in ai_cols:
                    await db.execute("ALTER TABLE ai_config ADD COLUMN respond_in_tickets INTEGER DEFAULT 0")
                if "ping_staff_in_tickets" not in ai_cols:
                    await db.execute("ALTER TABLE ai_config ADD COLUMN ping_staff_in_tickets INTEGER DEFAULT 0")
            except Exception:
                pass

            await db.commit()

    async def execute(self, query: str, parameters: tuple = ()):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, parameters)
            await db.commit()

    async def fetchrow(self, query: str, parameters: tuple = ()):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, parameters) as cursor:
                return await cursor.fetchone()

    async def fetch(self, query: str, parameters: tuple = ()):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, parameters) as cursor:
                return await cursor.fetchall()
