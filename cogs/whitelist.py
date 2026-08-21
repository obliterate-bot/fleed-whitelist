import discord
from discord.ext import commands
import datetime
import secrets
import aiohttp
import re
import io
from PIL import Image
from typing import Optional, Union
import config
from utils import fleed_embed, success_embed, error_embed, warn_embed, find_role, send_group_help
from fleed_whitelist.database import db
from fleed_whitelist.loader_generator import loader_generator

# FontAwesome / VoiceMaster Application Emojis
VM_APP_EMOJIS = {
    "lock": "<:vm_lock:1539043578247127093>",
    "unlock": "<:vm_unlock:1539043580897787934>",
    "ghost": "<:vm_ghost:1539043585176109067>",
    "reveal": "<:vm_reveal:1539043590116868146>",
    "rename": "<:vm_rename:1539043592692170813>",
    "claim": "<:vm_claim:1539043595414278314>",
    "increase": "<:vm_plus:1539043598123667517>",
    "decrease": "<:vm_minus:1539043601118396436>",
    "delete": "<:vm_delete:1539043604054409287>",
    "info": "<:vm_info:1539043607057666148>",
    "yes": "<:yes:1539039322693435433>",
    "no": "<:no:1539038121088385175>",
}

FA_ICONS = {
    "plus": discord.PartialEmoji.from_str("<:vm_plus:1539043598123667517>"),
    "info": discord.PartialEmoji.from_str("<:vm_info:1539043607057666148>"),
    "claim": discord.PartialEmoji.from_str("<:vm_claim:1539043595414278314>"),
    "lock": discord.PartialEmoji.from_str("<:vm_lock:1539043578247127093>"),
    "unlock": discord.PartialEmoji.from_str("<:vm_unlock:1539043580897787934>"),
    "rename": discord.PartialEmoji.from_str("<:vm_rename:1539043592692170813>"),
    "delete": discord.PartialEmoji.from_str("<:vm_delete:1539043604054409287>"),
    "yes": discord.PartialEmoji.from_str("<:yes:1539039322693435433>"),
    "no": discord.PartialEmoji.from_str("<:no:1539038121088385175>"),
    "reveal": discord.PartialEmoji.from_str("<:vm_reveal:1539043590116868146>"),
}

async def get_server_icon_color(guild: Optional[discord.Guild]) -> int:
    if not guild or not guild.icon:
        return 0xFEE75C
    try:
        icon_bytes = await guild.icon.read()
        im = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
        im = im.resize((32, 32))
        colors = im.getcolors(32 * 32)
        if not colors:
            return 0xFEE75C
        best_color = None
        best_score = -1
        for count, (r, g, b, a) in colors:
            if a < 128:
                continue
            delta = max(r, g, b) - min(r, g, b)
            if 30 < (r + g + b) // 3 < 240:
                score = count * (delta + 1)
                if score > best_score:
                    best_score = score
                    best_color = (r, g, b)
        if best_color:
            return (best_color[0] << 16) + (best_color[1] << 8) + best_color[2]
    except Exception:
        pass
    return 0xFEE75C

async def create_staff_panel_embed(guild: Optional[discord.Guild], bot: commands.Bot, slug: str = "all") -> discord.Embed:
    icon_url = guild.icon.url if guild and guild.icon else (bot.user.display_avatar.url if bot and bot.user else None)
    color = await get_server_icon_color(guild) if guild else 0xFEE75C
    
    e_plus = VM_APP_EMOJIS["increase"]
    e_info = VM_APP_EMOJIS["info"]
    e_key = VM_APP_EMOJIS["claim"]
    e_lock = VM_APP_EMOJIS["lock"]
    e_guide = VM_APP_EMOJIS["rename"]

    scope_title = f"{slug.upper()}" if slug != "all" else "GLOBAL"
    clean_slug = slug.strip().lower() if slug and slug != "all" else None
    guild_id_str = str(guild.id) if guild else None

    manager_mentions = []
    recent_buyer_lines = []

    async with db.get_db() as conn:
        mgr_query = "SELECT * FROM whitelist_managers WHERE (guild_id = ? OR guild_id IS NULL)"
        params = [guild_id_str]
        if clean_slug:
            mgr_query += " AND (script_slug = ? OR script_slug = 'all')"
            params.append(clean_slug)
        mgr_query += " ORDER BY id ASC LIMIT 15"
        cursor = await conn.execute(mgr_query, tuple(params))
        mgr_rows = await cursor.fetchall()

        for m in mgr_rows:
            target_id = m["discord_user_id"]
            if m["is_role"]:
                manager_mentions.append(f"<@&{target_id}> (Role)")
            else:
                manager_mentions.append(f"<@{target_id}>")

        lic_query = """
            SELECT l.*, s.name as script_name
            FROM licenses l
            JOIN scripts s ON l.script_id = s.id
        """
        lic_params = []
        if clean_slug:
            lic_query += " WHERE s.slug = ?"
            lic_params.append(clean_slug)
        lic_query += " ORDER BY l.id DESC LIMIT 6"
        cursor = await conn.execute(lic_query, tuple(lic_params))
        recent_lics = await cursor.fetchall()

        for lic in recent_lics:
            user_tag = f"<@{lic['discord_id']}>" if lic["discord_id"] else "`Unlinked Key`"
            hwid_tag = "Bound" if lic["hwid"] else "Unbound"
            status_tag = "BANNED" if lic["is_banned"] else "Active"
            recent_buyer_lines.append(f"• {user_tag} — **{lic['script_name']}** (`{status_tag}` • `{hwid_tag}`)")

    managers_text = ", ".join(manager_mentions) if manager_mentions else "None assigned yet (use `Grant Manager` button)"
    buyers_text = "\n".join(recent_buyer_lines) if recent_buyer_lines else "No active buyers found"

    desc = (
        f"Manage script whitelists and buyers for **{scope_title}** using the buttons below.\n\n"
        "**Button Usage**\n"
        f"{e_plus} — `Whitelist Member` — Whitelist buyer & auto-DM loadstring\n"
        f"{e_info} — `Manage / Reset Buyer` — Reset HWID, toggle ban, resend key\n"
        f"{e_key} — `Generate Key` — Create an unlinked license key\n"
        f"{e_lock} — `Grant Manager Access` — Delegate staff whitelist permissions\n"
        f"{e_guide} — `Commands Guide` — View all commands and syntax\n\n"
        f"**👑 Authorized Whitelist Managers:**\n{managers_text}\n\n"
        f"**👥 Recent Whitelisted Buyers:**\n{buyers_text}"
    )

    embed = discord.Embed(
        title=f"Whitelist Interface — {scope_title}",
        description=desc,
        color=color
    )
    if guild and icon_url:
        embed.set_author(name=guild.name, icon_url=icon_url)
        embed.set_thumbnail(url=icon_url)
    elif bot.user:
        embed.set_author(name=bot.user.name)

    return embed

async def create_buyer_panel_embed(guild: Optional[discord.Guild], bot: commands.Bot, script_name: str, slug: str) -> discord.Embed:
    icon_url = guild.icon.url if guild and guild.icon else (bot.user.display_avatar.url if bot and bot.user else None)
    color = await get_server_icon_color(guild) if guild else 0xFEE75C

    e_claim = VM_APP_EMOJIS["claim"]
    e_info = VM_APP_EMOJIS["info"]
    e_plus = VM_APP_EMOJIS["increase"]
    e_unlock = VM_APP_EMOJIS["unlock"]
    e_delete = VM_APP_EMOJIS["delete"]
    e_stats = VM_APP_EMOJIS["reveal"]

    desc = (
        f"Manage your license and script access by using the buttons below.\n\n"
        "**Button Usage**\n"
        f"{e_claim} — `Redeem Key`\n"
        f"{e_info} — `Get Script`\n"
        f"{e_plus} — `Get Role`\n"
        f"{e_unlock} — `Reset HWID`\n"
        f"{e_delete} — `Unlink Key`\n"
        f"{e_stats} — `Get Stats`"
    )

    embed = discord.Embed(
        title=f"{script_name} Interface",
        description=desc,
        color=color
    )
    if guild and icon_url:
        embed.set_author(name=guild.name, icon_url=icon_url)
        embed.set_thumbnail(url=icon_url)
    elif bot.user:
        embed.set_author(name=bot.user.name)

    return embed

def parse_whitelist_duration(time_str: Optional[str]) -> tuple[Optional[str], str]:
    """
    Parses flexible duration inputs:
    '10m', '2h', '7d', '30d', '1w', '1mo', '365d', 'lifetime', '0', 'permanent', 'none', None
    Returns: (expires_at_iso, human_label)
    """
    if not time_str:
        return None, "lifetime"
    s = str(time_str).strip().lower()
    if s in ["0", "lifetime", "perm", "permanent", "infinite", "none", "-1", "forever", "null"]:
        return None, "lifetime"

    now_utc = datetime.datetime.now(datetime.timezone.utc)

    # If it's a plain integer, treat as days
    if s.isdigit():
        days = int(s)
        if days <= 0:
            return None, "lifetime"
        exp = now_utc + datetime.timedelta(days=days)
        return exp.isoformat(), f"{days} days"

    # Parse units (m=minutes, h=hours, d=days, w=weeks, mo=months, y=years)
    units = {
        's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
        'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
        'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
        'd': 86400, 'day': 86400, 'days': 86400,
        'w': 604800, 'week': 604800, 'weeks': 604800,
        'mo': 2592000, 'month': 2592000, 'months': 2592000,
        'y': 31536000, 'yr': 31536000, 'year': 31536000, 'years': 31536000
    }
    matches = re.findall(r'(\d+)\s*([a-zA-Z]+)', s)
    if matches:
        total_seconds = 0
        for val, unit in matches:
            if unit in units:
                total_seconds += int(val) * units[unit]
        if total_seconds > 0:
            exp = now_utc + datetime.timedelta(seconds=total_seconds)
            return exp.isoformat(), s

    return None, "lifetime"

async def get_cloud_api_key(slug: str = None) -> Optional[str]:
    """
    Finds the active Railway cloud API key for syncing.
    Checks:
    1. Owner of the script with this slug
    2. Admin account (role = 'admin')
    3. Any active developer account with a valid api_key
    """
    async with db.get_db() as conn:
        if slug:
            cursor = await conn.execute("""
                SELECT u.api_key FROM users u
                JOIN scripts s ON s.user_id = u.id
                WHERE s.slug = ? AND u.api_key IS NOT NULL AND u.is_active = 1
            """, (slug.strip().lower(),))
            row = await cursor.fetchone()
            if row and row["api_key"]:
                return row["api_key"]

        # Fallback: Admin or linked developer account
        cursor = await conn.execute("SELECT api_key FROM users WHERE (role = 'admin' OR discord_id IS NOT NULL) AND api_key IS NOT NULL AND is_active = 1 ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        if row and row["api_key"]:
            return row["api_key"]

        # Ultimate fallback: Any account with an API key
        cursor = await conn.execute("SELECT api_key FROM users WHERE api_key IS NOT NULL AND is_active = 1 ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        return row["api_key"] if row else None

async def is_script_owner_or_admin(ctx, slug: str = None) -> tuple[bool, Optional[str], Optional[dict]]:
    """
    Strict permission check: only bot owners, platform admins, or the website creator of the script.
    Managers CANNOT grant access to other managers (prevents privilege escalation).
    """
    author_id_str = str(ctx.author.id)
    clean_slug = slug.strip().lower() if slug else None

    # 1. Bot Owners
    is_owner = False
    if ctx.author.id == 539594512981295106 or ctx.author.id in getattr(config, "OWNER_IDS", []):
        is_owner = True
    bot_owners = getattr(ctx.bot, "owner_ids", set()) or set()
    if ctx.author.id in bot_owners or author_id_str in bot_owners:
        is_owner = True

    if is_owner:
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ? AND is_active = 1", (author_id_str,))
            user_row = await cursor.fetchone()
            if not user_row and clean_slug:
                cursor = await conn.execute("""
                    SELECT u.* FROM users u
                    JOIN scripts s ON s.user_id = u.id
                    WHERE s.slug = ? AND u.is_active = 1
                """, (clean_slug,))
                user_row = await cursor.fetchone()
        return True, None, dict(user_row) if user_row else None

    # 2. Website Developer Account (Owner or Admin)
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ? AND is_active = 1", (author_id_str,))
        user_row = await cursor.fetchone()

        if not user_row:
            return False, f"you must be linked to a website developer account to manage permissions. run `{ctx.prefix}whitelist link <api_key>`.", None

        if user_row["role"] == "admin":
            return True, None, dict(user_row)

        if clean_slug and clean_slug != "all":
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script_row = await cursor.fetchone()
            if not script_row:
                return False, f"script `{clean_slug}` does not exist.", dict(user_row)

            if script_row["user_id"] != user_row["id"]:
                return False, f"only the creator of `{clean_slug}` can delegate manager permissions for this script.", dict(user_row)

        return True, None, dict(user_row)


async def check_script_permission(ctx, slug: str = None) -> tuple[bool, Optional[str], Optional[dict]]:
    """
    Verifies that the Discord user is authorized to manage a specific script or platform.
    Checks:
    1. Bot Owners (universal bypass)
    2. Website Developer Account linked via `discord_id` (owns the script or is platform admin)
    3. Delegated Whitelist Managers in `whitelist_managers` table (User ID or Role ID)
    """
    author_id_str = str(ctx.author.id)
    clean_slug = slug.strip().lower() if slug else None
    guild_id_str = str(ctx.guild.id) if ctx.guild else None

    # 1. Bot Owners — still try to find their linked account for API key sync
    is_owner = False
    if ctx.author.id == 539594512981295106 or ctx.author.id in getattr(config, "OWNER_IDS", []):
        is_owner = True
    bot_owners = getattr(ctx.bot, "owner_ids", set()) or set()
    if ctx.author.id in bot_owners or author_id_str in bot_owners:
        is_owner = True

    if is_owner:
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ? AND is_active = 1", (author_id_str,))
            user_row = await cursor.fetchone()
            if not user_row and clean_slug:
                cursor = await conn.execute("""
                    SELECT u.* FROM users u
                    JOIN scripts s ON s.user_id = u.id
                    WHERE s.slug = ? AND u.is_active = 1
                """, (clean_slug,))
                user_row = await cursor.fetchone()
        return True, None, dict(user_row) if user_row else None

    async with db.get_db() as conn:
        # 2. Check direct Website Linked Developer Account
        cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ? AND is_active = 1", (author_id_str,))
        user_row = await cursor.fetchone()

        if user_row:
            if user_row["role"] == "admin":
                return True, None, dict(user_row)

            if clean_slug:
                cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
                script_row = await cursor.fetchone()
                if script_row and script_row["user_id"] == user_row["id"]:
                    return True, None, dict(user_row)
            else:
                return True, None, dict(user_row)

        # 3. Check Delegated Whitelist Manager permissions (User ID or Role ID)
        # A) Check direct user delegation
        cursor = await conn.execute("""
            SELECT * FROM whitelist_managers 
            WHERE discord_user_id = ? AND is_role = 0
              AND (script_slug = ? OR script_slug = 'all')
              AND (guild_id = ? OR guild_id IS NULL)
        """, (author_id_str, clean_slug or 'all', guild_id_str))
        mgr_row = await cursor.fetchone()

        # B) Check role delegation if in a guild
        if not mgr_row and ctx.guild and hasattr(ctx.author, "roles"):
            role_ids = [str(r.id) for r in ctx.author.roles]
            if role_ids:
                placeholders = ",".join(["?"] * len(role_ids))
                params = [clean_slug or 'all', guild_id_str] + role_ids
                cursor = await conn.execute(f"""
                    SELECT * FROM whitelist_managers
                    WHERE is_role = 1
                      AND (script_slug = ? OR script_slug = 'all')
                      AND (guild_id = ? OR guild_id IS NULL)
                      AND discord_user_id IN ({placeholders})
                """, tuple(params))
                mgr_row = await cursor.fetchone()

        if mgr_row:
            # Authorized manager! Retrieve script owner account for API key sync
            owner_user_row = None
            if clean_slug:
                cursor = await conn.execute("""
                    SELECT u.* FROM users u
                    JOIN scripts s ON s.user_id = u.id
                    WHERE s.slug = ? AND u.is_active = 1
                """, (clean_slug,))
                owner_user_row = await cursor.fetchone()
            if not owner_user_row:
                cursor = await conn.execute("SELECT * FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1")
                owner_user_row = await cursor.fetchone()

            return True, None, dict(owner_user_row) if owner_user_row else None

        if not user_row:
            return False, f"you do not have permission to manage whitelists. ask the owner to grant you access via `{ctx.prefix}whitelist manager add @{ctx.author.name}`.", None

        return False, f"you do not own or have manager access for `{clean_slug}`.", dict(user_row)

class RedeemKeyModal(discord.ui.Modal, title="Redeem License Key"):
    def __init__(self, slug: str, script_name: str, script_id: int, buyer_role_id: int = 0):
        super().__init__()
        self.slug = slug
        self.script_name = script_name
        self.script_id = script_id
        self.buyer_role_id = buyer_role_id

        self.key_input = discord.ui.TextInput(
            label="License Key",
            placeholder="FLEED-XXXX-XXXX-XXXX",
            min_length=10,
            max_length=64,
            required=True
        )
        self.add_item(self.key_input)

    async def on_submit(self, interaction: discord.Interaction):
        clean_key = self.key_input.value.strip().upper()
        user_id_str = str(interaction.user.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM licenses WHERE license_key = ? AND script_id = ?", (clean_key, self.script_id))
            license_row = await cursor.fetchone()

            if not license_row:
                return await interaction.response.send_message(
                    embed=error_embed("Invalid license key for this script hub.", interaction.user),
                    ephemeral=True
                )

            if license_row["is_banned"]:
                reason = license_row["ban_reason"] or "License has been suspended."
                return await interaction.response.send_message(
                    embed=error_embed(f"This license is banned: {reason}", interaction.user),
                    ephemeral=True
                )

            if license_row["expires_at"]:
                exp_dt = datetime.datetime.fromisoformat(license_row["expires_at"])
                if datetime.datetime.now(datetime.timezone.utc) > exp_dt:
                    return await interaction.response.send_message(
                        embed=error_embed("This license key has expired.", interaction.user),
                        ephemeral=True
                    )

            if license_row["discord_id"] and license_row["discord_id"] != user_id_str:
                return await interaction.response.send_message(
                    embed=error_embed("This key is already redeemed by another Discord account!", interaction.user),
                    ephemeral=True
                )

            # Bind key to Discord account
            await conn.execute("UPDATE licenses SET discord_id = ? WHERE id = ?", (user_id_str, license_row["id"]))
            await conn.commit()

        # Handle Role Assignment
        role_assigned_text = ""
        if self.buyer_role_id and interaction.guild:
            role = interaction.guild.get_role(self.buyer_role_id)
            if role and interaction.guild.me.guild_permissions.manage_roles and interaction.guild.me.top_role > role:
                try:
                    await interaction.user.add_roles(role, reason=f"FleedGuard Whitelist Key Redemption ({self.slug})")
                    role_assigned_text = f"\nGranted you the **{role.name}** role."
                except Exception:
                    pass

        embed = success_embed(
            f"Successfully redeemed license for **{self.script_name}**.\n"
            f"Key: `{clean_key}`\n"
            f"Linked to: {interaction.user.mention}{role_assigned_text}\n\n"
            f"You can now click Get Script to receive your loadstring.",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WhitelistControlPanelView(discord.ui.View):
    def __init__(self, slug: str = None):
        super().__init__(timeout=None)
        self.slug = slug

        if slug:
            self.redeem_btn.custom_id = f"fg_panel_redeem:{slug}"
            self.script_btn.custom_id = f"fg_panel_script:{slug}"
            self.role_btn.custom_id = f"fg_panel_role:{slug}"
            self.resethwid_btn.custom_id = f"fg_panel_resethwid:{slug}"
            self.unlink_btn.custom_id = f"fg_panel_unlink:{slug}"
            self.stats_btn.custom_id = f"fg_panel_stats:{slug}"

    @discord.ui.button(custom_id="fg_panel_redeem:default", style=discord.ButtonStyle.secondary, row=0, emoji=FA_ICONS["claim"])
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name, slug, buyer_role_id FROM scripts WHERE slug = ?", (slug,))
            script = await cursor.fetchone()
            if not script:
                return await interaction.response.send_message("Script hub not found.", ephemeral=True)

        modal = RedeemKeyModal(
            slug=script["slug"],
            script_name=script["name"],
            script_id=script["id"],
            buyer_role_id=script["buyer_role_id"] or 0
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(custom_id="fg_panel_script:default", style=discord.ButtonStyle.secondary, row=0, emoji=FA_ICONS["info"])
    async def script_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]
        user_id_str = str(interaction.user.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.slug as script_slug
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ? AND l.is_banned = 0
            """, (user_id_str, slug))
            license_row = await cursor.fetchone()

        if not license_row:
            # Check if user already holds the configured buyer role
            async with db.get_db() as conn:
                cursor = await conn.execute("SELECT id, name, slug, buyer_role_id FROM scripts WHERE slug = ?", (slug,))
                script = await cursor.fetchone()

            has_buyer_role = False
            if script and script["buyer_role_id"] and interaction.guild:
                role = interaction.guild.get_role(script["buyer_role_id"])
                if role and role in interaction.user.roles:
                    has_buyer_role = True

            if has_buyer_role:
                # Auto-generate key for existing buyer role holder
                key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                async with db.get_db() as conn:
                    await conn.execute("""
                        INSERT INTO licenses (script_id, license_key, discord_id, note, created_at)
                        VALUES (?, ?, ?, 'Auto-whitelisted via Buyer Role', ?)
                    """, (script["id"], key, user_id_str, now_iso))
                    await conn.commit()

                # Sync to Railway cloud
                pub_url = loader_generator.get_public_url()
                if pub_url and pub_url.startswith("http"):
                    api_key = await get_cloud_api_key(slug)
                    if api_key:
                        try:
                            async with aiohttp.ClientSession() as session:
                                await session.post(
                                    f"{pub_url}/api/licenses/create",
                                    headers={"X-API-Key": api_key},
                                    json={
                                        "slug": slug,
                                        "license_key": key,
                                        "discord_id": user_id_str,
                                        "note": "Auto-whitelisted via Buyer Role",
                                        "expires_at": None
                                    },
                                    timeout=aiohttp.ClientTimeout(total=5)
                                )
                        except Exception:
                            pass

                license_row = {"script_name": script["name"], "license_key": key, "execution_count": 0}
            else:
                return await interaction.response.send_message(
                    embed=error_embed(f"You have not redeemed a valid license for `{slug}` yet.\nClick Redeem Key above to link your key.", interaction.user),
                    ephemeral=True
                )

        pub_url = loader_generator.get_public_url()

        # Always ensure the key exists on Railway cloud (catches pre-sync keys)
        if pub_url and pub_url.startswith("http"):
            api_key = await get_cloud_api_key(slug)
            if api_key:
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            f"{pub_url}/api/licenses/create",
                            headers={"X-API-Key": api_key},
                            json={
                                "slug": slug,
                                "license_key": license_row["license_key"],
                                "discord_id": user_id_str,
                                "note": "synced via Get Script",
                                "expires_at": None
                            },
                            timeout=aiohttp.ClientTimeout(total=5)
                        )
                except Exception:
                    pass

        loadstring_snippet = f'getgenv().FleedKey = "{license_row["license_key"]}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{slug}?key={license_row["license_key"]}"))()'
        
        embed = fleed_embed(
            title=f"{license_row['script_name']} — Loadstring",
            description=f"Here is your personalized execution script with your linked key:\n\n"
                        f"```lua\n{loadstring_snippet}\n```\n"
                        f"License Key: `{license_row['license_key']}`\n"
                        f"Status: Active | Executions: {license_row['execution_count']}",
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(custom_id="fg_panel_role:default", style=discord.ButtonStyle.secondary, row=0, emoji=FA_ICONS["plus"])
    async def role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]
        user_id_str = str(interaction.user.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ? AND l.is_banned = 0
            """, (user_id_str, slug))
            license_row = await cursor.fetchone()

        if not license_row:
            return await interaction.response.send_message(
                embed=error_embed(f"You do not have an active redeemed key for `{slug}`.", interaction.user),
                ephemeral=True
            )

        buyer_role_id = license_row["buyer_role_id"]
        if not buyer_role_id or not interaction.guild:
            return await interaction.response.send_message(
                embed=warn_embed("No buyer role has been configured for this script on this server.", interaction.user),
                ephemeral=True
            )

        role = interaction.guild.get_role(buyer_role_id)
        if not role:
            return await interaction.response.send_message(
                embed=error_embed("Configured buyer role no longer exists.", interaction.user),
                ephemeral=True
            )

        if role in interaction.user.roles:
            return await interaction.response.send_message(
                embed=fleed_embed(title="Role Already Assigned", description=f"You already have the {role.mention} role.", author=interaction.user),
                ephemeral=True
            )

        try:
            await interaction.user.add_roles(role, reason=f"FleedGuard Claim Role: {slug}")
            await interaction.response.send_message(
                embed=success_embed(f"Successfully granted you the {role.mention} role.", interaction.user),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("I do not have permission to assign that role. Please ensure my role is placed higher than the buyer role.", interaction.user),
                ephemeral=True
            )

    @discord.ui.button(custom_id="fg_panel_resethwid:default", style=discord.ButtonStyle.secondary, row=1, emoji=FA_ICONS["unlock"])
    async def resethwid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]
        user_id_str = str(interaction.user.id)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ? AND l.is_banned = 0
            """, (user_id_str, slug))
            license_row = await cursor.fetchone()

            if not license_row:
                return await interaction.response.send_message(
                    embed=error_embed(f"No active license found for `{slug}` on your account.", interaction.user),
                    ephemeral=True
                )

            await conn.execute("""
                UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?
            """, (now_iso, license_row["id"]))
            await conn.commit()

        embed = success_embed(
            f"Successfully reset your Hardware ID for **{license_row['script_name']}**.\n"
            f"Key: `{license_row['license_key']}`\n\n"
            f"You can now execute the script on a new device.",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(custom_id="fg_panel_unlink:default", style=discord.ButtonStyle.secondary, row=1, emoji=FA_ICONS["delete"])
    async def unlink_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]
        user_id_str = str(interaction.user.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ?
            """, (user_id_str, slug))
            license_row = await cursor.fetchone()

            if not license_row:
                return await interaction.response.send_message(
                    embed=error_embed(f"No license linked to your account for `{slug}`.", interaction.user),
                    ephemeral=True
                )

            await conn.execute("UPDATE licenses SET discord_id = NULL WHERE id = ?", (license_row["id"],))
            await conn.commit()

        if license_row["buyer_role_id"] and interaction.guild:
            role = interaction.guild.get_role(license_row["buyer_role_id"])
            if role and role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(role, reason=f"FleedGuard Unlink Key: {slug}")
                except Exception:
                    pass

        embed = success_embed(
            f"Successfully unlinked your Discord account from **{license_row['script_name']}**.\n"
            f"Your key `{license_row['license_key']}` is now free to be re-redeemed.",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(custom_id="fg_panel_stats:default", style=discord.ButtonStyle.secondary, row=1, emoji=FA_ICONS["reveal"])
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (slug,))
            script = await cursor.fetchone()
            if not script:
                return await interaction.response.send_message("Script hub not found.", ephemeral=True)

            c1 = await conn.execute("""
                SELECT COUNT(*) as total, SUM(CASE WHEN is_banned = 0 THEN 1 ELSE 0 END) as active
                FROM licenses WHERE script_id = ?
            """, (script["id"],))
            lic_data = await c1.fetchone()

            c2 = await conn.execute("SELECT COUNT(*) as execs FROM execution_logs WHERE script_id = ?", (script["id"],))
            exec_data = await c2.fetchone()

        status_str = "Inactive (Killswitch)" if script["killswitch_active"] else "Active"
        embed = fleed_embed(
            title=f"{script['name']} — Statistics",
            description=f"Status: {status_str}\n"
                        f"Version: v{script['version']}\n"
                        f"Active Buyers: {lic_data['active'] or 0} / {lic_data['total'] or 0}\n"
                        f"Total Executions: {exec_data['execs'] or 0}",
            author=interaction.user
        )
# ------------------- Staff Whitelist Dropdown Components & Interactive Views -------------------

async def check_user_is_manager(user: Union[discord.Member, discord.User], guild: Optional[discord.Guild], slug: str = None) -> tuple[bool, Optional[str], Optional[dict]]:
    """
    Verifies if an interacting user has whitelist manager permissions for an interaction.
    """
    user_id_str = str(user.id)
    clean_slug = slug.strip().lower() if slug and slug != "all" else None
    guild_id_str = str(guild.id) if guild else None

    # 1. Bot Owners
    if user.id == 539594512981295106 or user.id in getattr(config, "OWNER_IDS", []):
        return True, None, None

    # 2. Server Administrator or Server Owner
    if guild and isinstance(user, discord.Member):
        if user.guild_permissions.administrator or user.id == guild.owner_id:
            return True, None, None

    async with db.get_db() as conn:
        # 3. Direct Website Linked Developer Account
        cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ? AND is_active = 1", (user_id_str,))
        user_row = await cursor.fetchone()
        if user_row:
            if user_row["role"] == "admin":
                return True, None, dict(user_row)
            if clean_slug:
                cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
                script_row = await cursor.fetchone()
                if script_row and script_row["user_id"] == user_row["id"]:
                    return True, None, dict(user_row)
            else:
                return True, None, dict(user_row)

        # 4. Whitelist Managers Table (User ID)
        cursor = await conn.execute("""
            SELECT * FROM whitelist_managers 
            WHERE discord_user_id = ? AND is_role = 0
              AND (script_slug = ? OR script_slug = 'all')
              AND (guild_id = ? OR guild_id IS NULL)
        """, (user_id_str, clean_slug or 'all', guild_id_str))
        if await cursor.fetchone():
            return True, None, None

        # 5. Whitelist Managers Table (Role ID)
        if guild and isinstance(user, discord.Member) and hasattr(user, "roles"):
            role_ids = [str(r.id) for r in user.roles]
            if role_ids:
                placeholders = ",".join(["?"] * len(role_ids))
                params = [clean_slug or 'all', guild_id_str] + role_ids
                cursor = await conn.execute(f"""
                    SELECT * FROM whitelist_managers
                    WHERE is_role = 1
                      AND (script_slug = ? OR script_slug = 'all')
                      AND (guild_id = ? OR guild_id IS NULL)
                      AND discord_user_id IN ({placeholders})
                """, tuple(params))
                if await cursor.fetchone():
                    return True, None, None

    return False, "you do not have whitelist manager permissions for this script.", None

async def is_script_owner_or_admin_interaction(user: Union[discord.Member, discord.User], guild: Optional[discord.Guild], slug: str = None) -> tuple[bool, Optional[str], Optional[dict]]:
    user_id_str = str(user.id)
    clean_slug = slug.strip().lower() if slug and slug != "all" else None

    if user.id == 539594512981295106 or user.id in getattr(config, "OWNER_IDS", []):
        return True, None, None

    if guild and isinstance(user, discord.Member):
        if user.guild_permissions.administrator or user.id == guild.owner_id:
            return True, None, None

    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ? AND is_active = 1", (user_id_str,))
        user_row = await cursor.fetchone()
        if not user_row:
            return False, "you must be linked to a website developer account to manage permissions.", None
        if user_row["role"] == "admin":
            return True, None, dict(user_row)
        if clean_slug:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script_row = await cursor.fetchone()
            if script_row and script_row["user_id"] == user_row["id"]:
                return True, None, dict(user_row)
        return True, None, dict(user_row)

# ------------------- Dropdown Menus -------------------

class BuyerUserSelect(discord.ui.UserSelect):
    def __init__(self, placeholder: str = "👤 Select buyer from server members...", row: int = 0):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, row=row)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_user = self.values[0]
        await interaction.response.defer()

class ManagerRoleSelect(discord.ui.RoleSelect):
    def __init__(self, placeholder: str = "🛡️ Select staff / reseller role...", row: int = 1):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, row=row)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_role = self.values[0]
        await interaction.response.defer()

class ScriptSelect(discord.ui.Select):
    def __init__(self, scripts: list, default_slug: str = None, include_all: bool = False, row: int = 1):
        options = []
        if include_all:
            options.append(discord.SelectOption(
                label="All Scripts (Global)",
                value="all",
                description="Apply permission across every script hub",
                emoji="🌐",
                default=(default_slug == "all" or default_slug is None)
            ))

        for s in scripts[:24]:
            is_default = (s["slug"] == default_slug) and not include_all
            options.append(discord.SelectOption(
                label=s["name"][:100],
                value=s["slug"],
                description=f"Slug: {s['slug']} • v{s['version']}"[:100],
                emoji="📜",
                default=is_default
            ))

        if not options:
            options.append(discord.SelectOption(label="No scripts available", value="none"))

        super().__init__(placeholder="📜 Select script hub...", min_values=1, max_values=1, options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_slug = self.values[0]
        await interaction.response.defer()

class DurationSelect(discord.ui.Select):
    def __init__(self, row: int = 2):
        options = [
            discord.SelectOption(label="Lifetime (Permanent)", value="lifetime", description="Never expires", emoji="♾️", default=True),
            discord.SelectOption(label="30 Days (1 Month)", value="30d", description="Expires after 30 days", emoji="📅"),
            discord.SelectOption(label="14 Days (2 Weeks)", value="14d", description="Expires after 14 days", emoji="🗓️"),
            discord.SelectOption(label="7 Days (1 Week)", value="7d", description="Expires after 7 days", emoji="⏱️"),
            discord.SelectOption(label="3 Days", value="3d", description="Expires after 3 days", emoji="⏳"),
            discord.SelectOption(label="1 Day (24 Hours)", value="1d", description="Expires after 24 hours", emoji="🕒"),
            discord.SelectOption(label="1 Hour (Trial)", value="1h", description="Expires after 1 hour", emoji="⚡"),
        ]
        super().__init__(placeholder="⏳ Select duration...", min_values=1, max_values=1, options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_duration = self.values[0]
        await interaction.response.defer()

class BuyerSelectDropdown(discord.ui.Select):
    def __init__(self, licenses: list, guild: Optional[discord.Guild] = None, bot: Optional[commands.Bot] = None, row: int = 0):
        options = []
        for lic in licenses[:25]:
            user_label = "Unlinked Key"
            if lic["discord_id"]:
                user_id_int = int(lic["discord_id"]) if str(lic["discord_id"]).isdigit() else None
                member = guild.get_member(user_id_int) if (guild and user_id_int) else None
                if not member and bot and user_id_int:
                    member = bot.get_user(user_id_int)
                
                if member:
                    user_label = f"@{member.name}"
                    if member.display_name and member.display_name != member.name:
                        user_label = f"{member.display_name} (@{member.name})"
                else:
                    user_label = f"User: {lic['discord_id']}"

            script_label = lic["script_name"][:16]
            key_preview = lic["license_key"][:14]
            hwid_label = "Bound" if lic["hwid"] else "Unbound"
            status_label = "BANNED" if lic["is_banned"] else "Active"
            
            options.append(discord.SelectOption(
                label=f"{user_label} — {script_label}"[:100],
                value=str(lic["id"]),
                description=f"Key: {key_preview}... • HWID: {hwid_label} • {status_label}"[:100],
                emoji=FA_ICONS["info"] if not lic["is_banned"] else FA_ICONS["lock"]
            ))

        if not options:
            options.append(discord.SelectOption(label="No buyer licenses found", value="none"))

        super().__init__(placeholder="🔍 Select buyer to inspect or reset...", min_values=1, max_values=1, options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        selected_id = self.values[0]
        if selected_id == "none":
            return await interaction.response.defer()

        self.view.selected_license_id = int(selected_id)
        await self.view.update_buyer_display(interaction)

# ------------------- Interactive Sub-Views -------------------

class StaffInteractiveWhitelistView(discord.ui.View):
    def __init__(self, scripts: list, default_slug: str, author: Union[discord.Member, discord.User]):
        super().__init__(timeout=180)
        self.author = author
        self.selected_user = None
        self.selected_slug = default_slug
        self.selected_duration = "lifetime"

        self.add_item(BuyerUserSelect(row=0))
        self.add_item(ScriptSelect(scripts=scripts, default_slug=default_slug, include_all=False, row=1))
        self.add_item(DurationSelect(row=2))

    @discord.ui.button(label="confirm", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["yes"], row=3)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_user:
            return await interaction.response.send_message(embed=error_embed("please select a buyer from the user dropdown first.", interaction.user), ephemeral=True)

        clean_slug = self.selected_slug.strip().lower()
        is_allowed, err, _ = await check_user_is_manager(interaction.user, interaction.guild, clean_slug)
        if not is_allowed:
            return await interaction.response.send_message(embed=error_embed(err or "you do not have permission to whitelist buyers for this script.", interaction.user), ephemeral=True)

        target_member = self.selected_user
        discord_id = str(target_member.id)
        expires_at, duration_label = parse_whitelist_duration(self.selected_duration)
        user_note = f"whitelisted via dropdown panel by {interaction.user.name}"

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await interaction.response.send_message(embed=error_embed(f"script `{clean_slug}` does not exist.", interaction.user), ephemeral=True)

            cursor = await conn.execute("SELECT * FROM licenses WHERE discord_id = ? AND script_id = ?", (discord_id, script["id"]))
            existing = await cursor.fetchone()
            if existing:
                return await interaction.response.send_message(
                    embed=warn_embed(f"<@{discord_id}> is already whitelisted for **{script['name']}**.\nkey: `{existing['license_key']}`", interaction.user),
                    ephemeral=True
                )

            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, discord_id, note, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (script["id"], key, discord_id, user_note, expires_at, now_iso))
            await conn.commit()

        pub_url = loader_generator.get_public_url()
        if pub_url and pub_url.startswith("http"):
            api_key = await get_cloud_api_key(clean_slug)
            if api_key:
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            f"{pub_url}/api/licenses/create",
                            headers={"X-API-Key": api_key},
                            json={
                                "slug": clean_slug,
                                "license_key": key,
                                "discord_id": discord_id,
                                "note": user_note,
                                "expires_at": expires_at
                            },
                            timeout=aiohttp.ClientTimeout(total=5)
                        )
                except Exception:
                    pass

        role_text = ""
        if script["buyer_role_id"] and interaction.guild and isinstance(target_member, discord.Member):
            role = interaction.guild.get_role(script["buyer_role_id"])
            if role and interaction.guild.me.guild_permissions.manage_roles and interaction.guild.me.top_role > role:
                try:
                    await target_member.add_roles(role, reason=f"whitelisted: {script['name']}")
                    role_text = f"\ngranted role: {role.mention}"
                except Exception:
                    pass

        loadstring_snippet = f'getgenv().FleedKey = "{key}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{clean_slug}?key={key}"))()'
        dm_embed = fleed_embed(
            title=f"{script['name']} — license & loadstring",
            description=f"you have been whitelisted for **{script['name']}**.\n\n"
                        f"**key:** `{key}`\n"
                        f"**duration:** {duration_label}\n"
                        f"**note:** {user_note}\n\n"
                        f"**loadstring:**\n```lua\n{loadstring_snippet}\n```\n"
                        f"execute this loadstring inside your roblox executor.",
            author=interaction.user
        )
        dm_delivered = False
        try:
            await target_member.send(embed=dm_embed)
            dm_delivered = True
        except Exception:
            dm_delivered = False

        status_msg = "sent license key directly to their dms." if dm_delivered else "could not dm the user (dms closed)."
        embed = success_embed(
            f"successfully whitelisted {target_member.mention} for **{script['name']}** ({duration_label}).\n"
            f"**key:** `{key}`{role_text}\n"
            f"{status_msg}",
            interaction.user
        )

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["no"], row=3)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=fleed_embed(title="whitelist cancelled", description="action was cancelled.", author=interaction.user), view=self)

class StaffInteractiveBuyerManagerView(discord.ui.View):
    def __init__(self, licenses: list, author: Union[discord.Member, discord.User], guild: Optional[discord.Guild], bot: Optional[commands.Bot] = None):
        super().__init__(timeout=180)
        self.author = author
        self.guild = guild
        self.bot = bot
        self.selected_license_id = None
        self.add_item(BuyerSelectDropdown(licenses=licenses, guild=guild, bot=bot, row=0))

    async def update_buyer_display(self, interaction: discord.Interaction):
        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.slug as script_slug, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.id = ?
            """, (self.selected_license_id,))
            lic = await cursor.fetchone()

        if not lic:
            return await interaction.response.send_message(embed=error_embed("license not found.", interaction.user), ephemeral=True)

        status = "BANNED" if lic["is_banned"] else "Active"
        hwid_val = f"`{lic['hwid'][:16]}...`" if lic["hwid"] else "`unbound`"
        expires = f"`{lic['expires_at'][:10]}`" if lic["expires_at"] else "`lifetime`"
        user_mention = f"<@{lic['discord_id']}>" if lic["discord_id"] else "`Unlinked (Unredeemed)`"

        embed = fleed_embed(
            title=f"buyer profile — {lic['script_name']}",
            description=f"**buyer:** {user_mention}\n"
                        f"**key:** `{lic['license_key']}`\n"
                        f"**script:** **{lic['script_name']}** (`{lic['script_slug']}`)\n"
                        f"**status:** `{status}`\n"
                        f"**hwid:** {hwid_val}\n"
                        f"**executions:** `{lic['execution_count']}`\n"
                        f"**expires:** {expires}\n"
                        f"**note:** `{lic['note'] or 'none'}`\n\n"
                        f"use the action buttons below to manage this buyer.",
            author=interaction.user
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="reset hwid", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["unlock"], row=1)
    async def reset_hwid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_license_id:
            return await interaction.response.send_message(embed=error_embed("please select a buyer from the dropdown first.", interaction.user), ephemeral=True)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        async with db.get_db() as conn:
            await conn.execute("UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?", (now_iso, self.selected_license_id))
            await conn.commit()

        await self.update_buyer_display(interaction)
        await interaction.followup.send(embed=success_embed("successfully reset hardware ID for this buyer.", interaction.user), ephemeral=True)

    @discord.ui.button(label="resend dm", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["info"], row=1)
    async def resend_dm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_license_id:
            return await interaction.response.send_message(embed=error_embed("please select a buyer from the dropdown first.", interaction.user), ephemeral=True)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.slug as script_slug
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.id = ?
            """, (self.selected_license_id,))
            lic = await cursor.fetchone()

        if not lic or not lic["discord_id"]:
            return await interaction.response.send_message(embed=error_embed("no linked discord user found for this license.", interaction.user), ephemeral=True)

        target_member = interaction.guild.get_member(int(lic["discord_id"])) if (interaction.guild and lic["discord_id"].isdigit()) else None
        if not target_member and lic["discord_id"].isdigit():
            try:
                target_member = await interaction.client.fetch_user(int(lic["discord_id"]))
            except Exception:
                pass

        if not target_member:
            return await interaction.response.send_message(embed=error_embed("could not locate the buyer's discord account.", interaction.user), ephemeral=True)

        pub_url = loader_generator.get_public_url()
        loadstring_snippet = f'getgenv().FleedKey = "{lic["license_key"]}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{lic["script_slug"]}?key={lic["license_key"]}"))()'
        dm_embed = fleed_embed(
            title=f"{lic['script_name']} — license & loadstring",
            description=f"here is your key and loadstring for **{lic['script_name']}**:\n\n"
                        f"**key:** `{lic['license_key']}`\n\n"
                        f"**loadstring:**\n```lua\n{loadstring_snippet}\n```\n"
                        f"execute this loadstring inside your roblox executor.",
            author=interaction.user
        )
        try:
            await target_member.send(embed=dm_embed)
            await interaction.response.send_message(embed=success_embed(f"resent key and loadstring to {target_member.mention}'s DMs.", interaction.user), ephemeral=True)
        except Exception:
            await interaction.response.send_message(embed=warn_embed(f"could not deliver to {target_member.mention}'s DMs (DMs are closed).", interaction.user), ephemeral=True)

    @discord.ui.button(label="toggle ban", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["lock"], row=1)
    async def toggle_ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_license_id:
            return await interaction.response.send_message(embed=error_embed("please select a buyer from the dropdown first.", interaction.user), ephemeral=True)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT is_banned FROM licenses WHERE id = ?", (self.selected_license_id,))
            lic = await cursor.fetchone()
            if not lic:
                return await interaction.response.send_message(embed=error_embed("license not found.", interaction.user), ephemeral=True)

            new_status = 0 if lic["is_banned"] else 1
            reason = "manually banned by staff" if new_status else None
            await conn.execute("UPDATE licenses SET is_banned = ?, ban_reason = ? WHERE id = ?", (new_status, reason, self.selected_license_id))
            await conn.commit()

        await self.update_buyer_display(interaction)
        status_text = "banned" if new_status else "unbanned"
        await interaction.followup.send(embed=success_embed(f"license is now {status_text}.", interaction.user), ephemeral=True)

    @discord.ui.button(label="revoke", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["delete"], row=1)
    async def revoke_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_license_id:
            return await interaction.response.send_message(embed=error_embed("please select a buyer from the dropdown first.", interaction.user), ephemeral=True)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.id = ?
            """, (self.selected_license_id,))
            lic = await cursor.fetchone()

            if not lic:
                return await interaction.response.send_message(embed=error_embed("license not found.", interaction.user), ephemeral=True)

            await conn.execute("DELETE FROM licenses WHERE id = ?", (self.selected_license_id,))
            await conn.commit()

        if lic["buyer_role_id"] and interaction.guild and lic["discord_id"]:
            role = interaction.guild.get_role(lic["buyer_role_id"])
            target_member = interaction.guild.get_member(int(lic["discord_id"])) if lic["discord_id"].isdigit() else None
            if role and target_member and role in target_member.roles:
                try:
                    await target_member.remove_roles(role, reason=f"whitelist revoked: {lic['script_name']}")
                except Exception:
                    pass

        embed = success_embed(f"permanently revoked whitelist access for `{lic['license_key']}`.", interaction.user)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

class StaffInteractiveGenKeyView(discord.ui.View):
    def __init__(self, scripts: list, default_slug: str, author: Union[discord.Member, discord.User]):
        super().__init__(timeout=180)
        self.author = author
        self.selected_slug = default_slug
        self.selected_duration = "lifetime"

        self.add_item(ScriptSelect(scripts=scripts, default_slug=default_slug, include_all=False, row=0))
        self.add_item(DurationSelect(row=1))

    @discord.ui.button(label="generate", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["claim"], row=2)
    async def generate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        clean_slug = self.selected_slug.strip().lower()
        is_allowed, err, _ = await check_user_is_manager(interaction.user, interaction.guild, clean_slug)
        if not is_allowed:
            return await interaction.response.send_message(embed=error_embed(err or "you do not have permission to generate keys for this script.", interaction.user), ephemeral=True)

        expires_at, duration_label = parse_whitelist_duration(self.selected_duration)
        user_note = f"generated via dropdown panel by {interaction.user.name}"

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await interaction.response.send_message(embed=error_embed(f"script `{clean_slug}` does not exist.", interaction.user), ephemeral=True)

            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, discord_id, note, expires_at, created_at)
                VALUES (?, ?, NULL, ?, ?, ?)
            """, (script["id"], key, user_note, expires_at, now_iso))
            await conn.commit()

        pub_url = loader_generator.get_public_url()
        if pub_url and pub_url.startswith("http"):
            api_key = await get_cloud_api_key(clean_slug)
            if api_key:
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            f"{pub_url}/api/licenses/create",
                            headers={"X-API-Key": api_key},
                            json={
                                "slug": clean_slug,
                                "license_key": key,
                                "discord_id": None,
                                "note": user_note,
                                "expires_at": expires_at
                            },
                            timeout=aiohttp.ClientTimeout(total=5)
                        )
                except Exception:
                    pass

        embed = success_embed(
            f"generated unlinked license key for **{script['name']}** ({duration_label}).\n\n"
            f"**key:** `{key}`\n"
            f"**duration:** {duration_label}\n"
            f"**note:** {user_note}\n\n"
            f"buyers can redeem this via `,redeem {key}` or by clicking **Redeem Key** on the buyer control panel.",
            interaction.user
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["no"], row=2)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=fleed_embed(title="key generation cancelled", description="action was cancelled.", author=interaction.user), view=self)

class StaffInteractiveGrantManagerView(discord.ui.View):
    def __init__(self, scripts: list, default_slug: str, author: Union[discord.Member, discord.User], guild: Optional[discord.Guild]):
        super().__init__(timeout=180)
        self.author = author
        self.guild = guild
        self.selected_user = None
        self.selected_role = None
        self.selected_slug = default_slug

        self.add_item(BuyerUserSelect(placeholder="👤 Select user to grant manager access...", row=0))
        self.add_item(ManagerRoleSelect(placeholder="🛡️ Or select role to grant manager access...", row=1))
        self.add_item(ScriptSelect(scripts=scripts, default_slug=default_slug, include_all=True, row=2))

    @discord.ui.button(label="grant user", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["claim"], row=3)
    async def grant_user_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_user:
            return await interaction.response.send_message(embed=error_embed("please select a user from the user dropdown first.", interaction.user), ephemeral=True)

        clean_slug = self.selected_slug.strip().lower()
        ok, err_msg, _ = await is_script_owner_or_admin_interaction(interaction.user, interaction.guild, clean_slug if clean_slug != "all" else None)
        if not ok:
            return await interaction.response.send_message(embed=error_embed(err_msg or "only script owners or platform admins can grant manager access.", interaction.user), ephemeral=True)

        target_member = self.selected_user
        discord_id = str(target_member.id)
        guild_id_str = str(interaction.guild.id) if interaction.guild else None
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        async with db.get_db() as conn:
            script_name = "All Scripts (Global)"
            if clean_slug != "all":
                cursor = await conn.execute("SELECT name FROM scripts WHERE slug = ?", (clean_slug,))
                s_row = await cursor.fetchone()
                if not s_row:
                    return await interaction.response.send_message(embed=error_embed(f"script `{clean_slug}` not found.", interaction.user), ephemeral=True)
                script_name = s_row["name"]

            await conn.execute("""
                INSERT INTO whitelist_managers (discord_user_id, is_role, script_slug, guild_id, granted_by, created_at)
                VALUES (?, 0, ?, ?, ?, ?)
                ON CONFLICT(discord_user_id, script_slug, is_role, guild_id) DO UPDATE SET
                    granted_by = excluded.granted_by,
                    created_at = excluded.created_at
            """, (discord_id, clean_slug, guild_id_str, str(interaction.user.id), now_iso))
            await conn.commit()

        # Auto-update permissions on staff channels
        if interaction.guild:
            for ch in interaction.guild.text_channels:
                if ch.name in ["whitelist-staff", "staff-whitelist", "wl-staff"] or (ch.topic and "Private Whitelist Staff Hub" in ch.topic):
                    try:
                        await ch.set_permissions(target_member, overwrite=discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, view_channel=True))
                    except Exception:
                        pass

        # DM new manager
        try:
            dm_embed = fleed_embed(
                title="whitelist manager access granted",
                description=f"you have been granted whitelist management access for **{script_name}** (`{clean_slug}`).\n\n"
                            f"**granted by:** {interaction.user.mention} (`{interaction.user.name}`)\n\n"
                            f"you can now whitelist users and generate license keys directly in discord.",
                author=interaction.user
            )
            await target_member.send(embed=dm_embed)
        except Exception:
            pass

        embed = success_embed(
            f"granted whitelist manager access to {target_member.mention} for **{script_name}** (`{clean_slug}`).\n"
            f"they have also been granted access to the private staff whitelist chat.",
            interaction.user
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="grant role", style=discord.ButtonStyle.secondary, emoji=FA_ICONS["lock"], row=3)
    async def grant_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_role:
            return await interaction.response.send_message(embed=error_embed("please select a role from the role dropdown first.", interaction.user), ephemeral=True)

        clean_slug = self.selected_slug.strip().lower()
        ok, err_msg, _ = await is_script_owner_or_admin_interaction(interaction.user, interaction.guild, clean_slug if clean_slug != "all" else None)
        if not ok:
            return await interaction.response.send_message(embed=error_embed(err_msg or "only script owners or platform admins can grant manager access.", interaction.user), ephemeral=True)

        role = self.selected_role
        guild_id_str = str(interaction.guild.id) if interaction.guild else None
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        async with db.get_db() as conn:
            script_name = "All Scripts (Global)"
            if clean_slug != "all":
                cursor = await conn.execute("SELECT name FROM scripts WHERE slug = ?", (clean_slug,))
                s_row = await cursor.fetchone()
                if not s_row:
                    return await interaction.response.send_message(embed=error_embed(f"script `{clean_slug}` not found.", interaction.user), ephemeral=True)
                script_name = s_row["name"]

            await conn.execute("""
                INSERT INTO whitelist_managers (discord_user_id, is_role, script_slug, guild_id, granted_by, created_at)
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(discord_user_id, script_slug, is_role, guild_id) DO UPDATE SET
                    granted_by = excluded.granted_by,
                    created_at = excluded.created_at
            """, (str(role.id), clean_slug, guild_id_str, str(interaction.user.id), now_iso))
            await conn.commit()

        # Auto-update permissions on staff channels
        if interaction.guild:
            for ch in interaction.guild.text_channels:
                if ch.name in ["whitelist-staff", "staff-whitelist", "wl-staff"] or (ch.topic and "Private Whitelist Staff Hub" in ch.topic):
                    try:
                        await ch.set_permissions(role, overwrite=discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, view_channel=True))
                    except Exception:
                        pass

        embed = success_embed(
            f"granted whitelist manager access to role {role.mention} for **{script_name}** (`{clean_slug}`).\n"
            f"all members with this role now have access to the staff whitelist chat.",
            interaction.user
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

# ------------------- Main Persistent Staff Control Panel -------------------

class StaffWhitelistPanelView(discord.ui.View):
    def __init__(self, slug: str = "all"):
        super().__init__(timeout=None)
        self.slug = slug
        self.add_btn.custom_id = f"fg_staff_add:{slug}"
        self.manage_btn.custom_id = f"fg_staff_manage:{slug}"
        self.genkey_btn.custom_id = f"fg_staff_genkey:{slug}"
        self.grant_btn.custom_id = f"fg_staff_grant:{slug}"
        self.guide_btn.custom_id = f"fg_staff_guide:{slug}"

    @discord.ui.button(label="Whitelist", custom_id="fg_staff_add:default", style=discord.ButtonStyle.secondary, row=0, emoji=FA_ICONS["plus"])
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1] if ":" in button.custom_id else "all"
        is_allowed, err, _ = await check_user_is_manager(interaction.user, interaction.guild, slug if slug != "all" else None)
        if not is_allowed:
            return await interaction.response.send_message(embed=error_embed(err or "you do not have whitelist manager permissions.", interaction.user), ephemeral=True)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name, slug, version FROM scripts ORDER BY id DESC")
            scripts = await cursor.fetchall()

        if not scripts:
            return await interaction.response.send_message(embed=error_embed("no scripts found in database. create a script on the website first.", interaction.user), ephemeral=True)

        view = StaffInteractiveWhitelistView(scripts=scripts, default_slug=slug if slug != "all" else scripts[0]["slug"], author=interaction.user)
        embed = fleed_embed(
            title="whitelist member — dropdown selector",
            description="select the member, script hub, and duration from the dropdown menus below, then click **confirm**.",
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Manage Buyers", custom_id="fg_staff_manage:default", style=discord.ButtonStyle.secondary, row=0, emoji=FA_ICONS["info"])
    async def manage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1] if ":" in button.custom_id else "all"
        is_allowed, err, _ = await check_user_is_manager(interaction.user, interaction.guild, slug if slug != "all" else None)
        if not is_allowed:
            return await interaction.response.send_message(embed=error_embed(err or "you do not have whitelist manager permissions.", interaction.user), ephemeral=True)

        async with db.get_db() as conn:
            query = """
                SELECT l.*, s.name as script_name, s.slug as script_slug
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
            """
            params = []
            if slug and slug != "all":
                query += " WHERE s.slug = ?"
                params.append(slug.lower())
            query += " ORDER BY l.id DESC LIMIT 25"
            cursor = await conn.execute(query, tuple(params))
            licenses = await cursor.fetchall()

        if not licenses:
            return await interaction.response.send_message(embed=warn_embed("no active buyer licenses found in database.", interaction.user), ephemeral=True)

        view = StaffInteractiveBuyerManagerView(licenses=licenses, author=interaction.user, guild=interaction.guild, bot=interaction.client)
        embed = fleed_embed(
            title="manage buyers & hwids — dropdown selector",
            description="select any buyer from the dropdown menu below to view their profile, reset their HWID, resend their key, or revoke access.",
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Gen Key", custom_id="fg_staff_genkey:default", style=discord.ButtonStyle.secondary, row=0, emoji=FA_ICONS["claim"])
    async def genkey_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1] if ":" in button.custom_id else "all"
        is_allowed, err, _ = await check_user_is_manager(interaction.user, interaction.guild, slug if slug != "all" else None)
        if not is_allowed:
            return await interaction.response.send_message(embed=error_embed(err or "you do not have whitelist manager permissions.", interaction.user), ephemeral=True)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name, slug, version FROM scripts ORDER BY id DESC")
            scripts = await cursor.fetchall()

        if not scripts:
            return await interaction.response.send_message(embed=error_embed("no scripts found in database.", interaction.user), ephemeral=True)

        view = StaffInteractiveGenKeyView(scripts=scripts, default_slug=slug if slug != "all" else scripts[0]["slug"], author=interaction.user)
        embed = fleed_embed(
            title="generate buyer key — dropdown selector",
            description="select the script hub and duration from the dropdown menus below, then click **generate**.",
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Grant Manager", custom_id="fg_staff_grant:default", style=discord.ButtonStyle.secondary, row=0, emoji=FA_ICONS["lock"])
    async def grant_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1] if ":" in button.custom_id else "all"
        ok, err, _ = await is_script_owner_or_admin_interaction(interaction.user, interaction.guild, slug if slug != "all" else None)
        if not ok:
            return await interaction.response.send_message(embed=error_embed(err or "only the script owner or platform admin can grant manager access.", interaction.user), ephemeral=True)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name, slug, version FROM scripts ORDER BY id DESC")
            scripts = await cursor.fetchall()

        view = StaffInteractiveGrantManagerView(scripts=scripts, default_slug=slug if slug != "all" else "all", author=interaction.user, guild=interaction.guild)
        embed = fleed_embed(
            title="grant whitelist manager access — dropdown selector",
            description="select a user or role from the dropdowns below to delegate whitelist management permissions.",
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Guide", custom_id="fg_staff_guide:default", style=discord.ButtonStyle.secondary, row=0, emoji=FA_ICONS["rename"])
    async def guide_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        guide_text = (
            "### Whitelist Manager Commands Guide\n\n"
            "**Key Management:**\n"
            "• `,whitelist add <@user> <slug> [duration] [note]` — Whitelist user & DM them loadstring\n"
            "• `,whitelist genkey <slug> [duration] [note]` — Generate unlinked buyer key\n"
            "• `,whitelist remove <@user> <slug>` — Revoke user whitelist & role\n"
            "• `,whitelist check <@user>` — View user licenses, HWIDs & executions\n"
            "• `,whitelist force-resethwid <@user> <slug>` — Force-reset a user's HWID\n"
            "• `,whitelist bulkadd <slug> [duration]` — Auto-whitelist everyone with buyer role\n\n"
            "**Access Delegation (Owners Only):**\n"
            "• `,whitelist manager add <@user> [slug/all]` — Grant whitelist permissions to a user\n"
            "• `,whitelist manager remove <@user> [slug/all]` — Revoke whitelist permissions\n"
            "• `,whitelist manager role <@Role> [slug/all]` — Grant permissions to an entire staff role\n"
            "• `,whitelist manager unrole <@Role> [slug/all]` — Revoke role permissions\n"
            "• `,whitelist manager list [slug]` — View authorized managers\n\n"
            "**Channel Setup:**\n"
            "• `,whitelist setupchannel [name]` — Creates this private whitelist staff channel"
        )
        embed = fleed_embed(title="staff command documentation", description=guide_text, author=interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WhitelistCog(commands.Cog, name="whitelist"):
    """
    FleedGuard Roblox Whitelist & License Security Cog
    Integrated directly with website developer accounts.
    """
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(WhitelistControlPanelView())
        self.bot.add_view(StaffWhitelistPanelView())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.data or "custom_id" not in interaction.data:
            return
        custom_id = interaction.data["custom_id"]

        # Buyer Control Panel Buttons
        if custom_id.startswith("fg_panel_"):
            parts = custom_id.split(":", 1)
            action = parts[0]
            slug = parts[1] if len(parts) > 1 else ""

            view = WhitelistControlPanelView(slug=slug)
            if action == "fg_panel_redeem":
                await view.redeem_btn.callback(interaction)
            elif action == "fg_panel_script":
                await view.script_btn.callback(interaction)
            elif action == "fg_panel_role":
                await view.role_btn.callback(interaction)
            elif action == "fg_panel_resethwid":
                await view.resethwid_btn.callback(interaction)
            elif action == "fg_panel_unlink":
                await view.unlink_btn.callback(interaction)
            elif action == "fg_panel_stats":
                await view.stats_btn.callback(interaction)

        # Staff Whitelist Panel Buttons
        elif custom_id.startswith("fg_staff_"):
            parts = custom_id.split(":", 1)
            action = parts[0]
            slug = parts[1] if len(parts) > 1 else "all"

            view = StaffWhitelistPanelView(slug=slug)
            if action == "fg_staff_add":
                await view.add_btn.callback(interaction)
            elif action == "fg_staff_manage":
                await view.manage_btn.callback(interaction)
            elif action == "fg_staff_genkey":
                await view.genkey_btn.callback(interaction)
            elif action == "fg_staff_grant":
                await view.grant_btn.callback(interaction)
            elif action == "fg_staff_guide":
                await view.guide_btn.callback(interaction)

    # ------------------- Luarmor Core Whitelist Commands -------------------

    @commands.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    async def whitelist_group(self, ctx):
        """Displays interactive paginated help menu for whitelist commands."""
        await send_group_help(ctx, ctx.command, "whitelist")

    @whitelist_group.command(name="seturl", aliases=["url"])
    async def set_url_cmd(self, ctx, url: str):
        """
        Configures the backend live public API URL (e.g. Railway app URL).
        """
        clean_url = url.strip().rstrip("/")
        if not clean_url.startswith("http"):
            return await ctx.send(embed=error_embed("URL must start with http:// or https://", ctx.author))

        loader_generator.set_public_url(clean_url)
        await ctx.send(embed=success_embed(f"configured backend public url to `{clean_url}`.", ctx.author))

    @whitelist_group.command(name="link", aliases=["bind", "connect"])
    async def link_account_cmd(self, ctx, *, api_key: str):
        """
        Links your Discord account to your website developer login using your API key.
        """
        try:
            if ctx.guild:
                await ctx.message.delete()
        except Exception:
            pass

        clean_key = api_key.strip().strip("'\"`").replace("Bearer ", "").strip()
        author_id_str = str(ctx.author.id)

        user_row = None
        # 1. Try local database
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE api_key = ? AND is_active = 1", (clean_key,))
            row = await cursor.fetchone()
            if row:
                await conn.execute("UPDATE users SET discord_id = ? WHERE id = ?", (author_id_str, row["id"]))
                await conn.commit()
                user_row = dict(row)

        # 2. If not found locally, query live backend servers via HTTP
        if not user_row:
            urls_to_try = [
                loader_generator.get_public_url(),
                "http://localhost:8000",
                "http://127.0.0.1:8000"
            ]
            async with aiohttp.ClientSession() as session:
                for base_url in urls_to_try:
                    if not base_url:
                        continue
                    try:
                        async with session.get(f"{base_url}/api/auth/me", headers={"X-API-Key": clean_key}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                # Bind on server
                                try:
                                    await session.post(f"{base_url}/api/auth/bind_discord", headers={"X-API-Key": clean_key}, json={"discord_id": author_id_str}, timeout=aiohttp.ClientTimeout(total=5))
                                except Exception:
                                    pass

                                # Sync to local DB
                                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                                async with db.get_db() as conn:
                                    await conn.execute("""
                                        INSERT INTO users (username, email, password_hash, salt, api_key, role, is_active, discord_id, created_at)
                                        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                                        ON CONFLICT(username) DO UPDATE SET api_key = excluded.api_key, discord_id = excluded.discord_id
                                    """, (data["username"], data.get("email", ""), "remote_synced", "remote_salt", clean_key, data.get("role", "developer"), author_id_str, now_iso))
                                    await conn.commit()
                                user_row = data
                                break
                    except Exception:
                        pass

        if not user_row:
            return await ctx.send(embed=error_embed("invalid developer api key. verify your api key on the website settings tab.", ctx.author))

        embed = success_embed(
            f"successfully linked discord to website developer **{user_row['username']}**.\n"
            f"you can now manage your script whitelists directly in discord.",
            ctx.author
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="unlink", aliases=["disconnect"])
    async def unlink_account_cmd(self, ctx):
        """
        Unlinks your Discord account from the website login.
        """
        author_id_str = str(ctx.author.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ?", (author_id_str,))
            user_row = await cursor.fetchone()

            if not user_row:
                return await ctx.send(embed=error_embed("you do not have a linked website account.", ctx.author))

            await conn.execute("UPDATE users SET discord_id = NULL WHERE id = ?", (user_row["id"],))
            await conn.commit()

        await ctx.send(embed=success_embed(f"unlinked discord from website developer **{user_row['username']}**.", ctx.author))

    @whitelist_group.command(name="me", aliases=["profile", "dev"])
    async def dev_profile_cmd(self, ctx):
        """
        Displays your linked website developer account and owned scripts.
        """
        author_id_str = str(ctx.author.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ?", (author_id_str,))
            user_row = await cursor.fetchone()

            if not user_row:
                return await ctx.send(embed=warn_embed(f"you are not linked to a website account. run `{ctx.prefix}whitelist link <api_key>`.", ctx.author))

            c_scripts = await conn.execute("SELECT * FROM scripts WHERE user_id = ?", (user_row["id"],))
            scripts = await c_scripts.fetchall()

            c_keys = await conn.execute("""
                SELECT COUNT(l.id) as total_keys
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE s.user_id = ? AND l.is_banned = 0
            """, (user_row["id"],))
            key_data = await c_keys.fetchone()

        embed = fleed_embed(title=f"developer profile — {user_row['username']}", author=ctx.author)
        script_list = ", ".join([f"`{s['slug']}`" for s in scripts]) if scripts else "none"
        embed.add_field(name="Website User", value=f"**{user_row['username']}** (`{user_row['role']}`)", inline=True)
        embed.add_field(name="Active Keys", value=str(key_data["total_keys"] or 0), inline=True)
        embed.add_field(name="Managed Scripts", value=script_list, inline=False)
        await ctx.send(embed=embed)

    @whitelist_group.command(name="add", aliases=["user", "create"])
    async def add_whitelist_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str, duration: str = "0", *, note: str = ""):
        """
        Whitelists a user directly by @mention or Discord ID.
        Duration supports '10m', '1h', '7d', '30d', 'lifetime', etc.
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, user_row = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        discord_id = str(target.id) if hasattr(target, "id") else str(target).strip("<@!>")
        expires_at, duration_label = parse_whitelist_duration(duration)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))

            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            user_note = note or f"whitelisted by {ctx.author.name}"
            
            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, discord_id, note, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (script["id"], key, discord_id, user_note, expires_at, now_iso))
            await conn.commit()

        # Also sync to live Railway Cloud Backend if developer is linked with API key
        if user_row and user_row.get("api_key"):
            pub_url = loader_generator.get_public_url()
            if pub_url and pub_url.startswith("http"):
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            f"{pub_url}/api/licenses/create",
                            headers={"X-API-Key": user_row["api_key"]},
                            json={
                                "slug": clean_slug,
                                "license_key": key,
                                "discord_id": discord_id,
                                "note": user_note,
                                "expires_at": expires_at
                            },
                            timeout=aiohttp.ClientTimeout(total=5)
                        )
                except Exception:
                    pass

        role_text = ""
        if script["buyer_role_id"] and ctx.guild:
            role = ctx.guild.get_role(script["buyer_role_id"])
            target_member = ctx.guild.get_member(int(discord_id)) if discord_id.isdigit() else None
            if role and target_member and ctx.guild.me.guild_permissions.manage_roles and ctx.guild.me.top_role > role:
                try:
                    await target_member.add_roles(role, reason=f"whitelist: {script['name']}")
                    role_text = f"\nassigned role {role.mention}."
                except Exception:
                    pass

        pub_url = loader_generator.get_public_url()
        loadstring_snippet = f'getgenv().FleedKey = "{key}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{clean_slug}?key={key}"))()'

        # Build DM embed
        dm_embed = fleed_embed(
            title=f"{script['name']} — License & Loadstring",
            description=f"You have been whitelisted for **{script['name']}**.\n\n"
                        f"**Key:** `{key}`\n"
                        f"**Duration:** {duration_label}\n"
                        f"**Note:** {user_note}\n\n"
                        f"**Loadstring:**\n```lua\n{loadstring_snippet}\n```\n"
                        f"Execute this loadstring inside your Roblox executor.",
            author=ctx.author
        )

        dm_delivered = False
        target_obj = None
        if isinstance(target, (discord.Member, discord.User)):
            target_obj = target
        elif discord_id.isdigit() and ctx.guild:
            target_obj = ctx.guild.get_member(int(discord_id)) or await ctx.bot.fetch_user(int(discord_id))

        if target_obj:
            try:
                await target_obj.send(embed=dm_embed)
                dm_delivered = True
            except Exception:
                dm_delivered = False

        # If whitelisting someone else, also send a receipt copy to the developer's DMs
        if target_obj and target_obj.id != ctx.author.id:
            try:
                await ctx.author.send(embed=dm_embed)
            except Exception:
                pass

        if dm_delivered:
            embed = success_embed(
                f"whitelisted <@{discord_id}> for **{script['name']}** ({duration_label}).{role_text}\n"
                f"sent their license key and loadstring directly to their dms.",
                ctx.author
            )
        else:
            embed = warn_embed(
                f"whitelisted <@{discord_id}> for **{script['name']}** ({duration_label}).{role_text}\n"
                f"could not deliver to their dms (dms are closed). they can click **Get Script** on the control panel or open their dms.",
                ctx.author
            )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="genkey", aliases=["gen", "generate", "createkey"])
    async def gen_key_cmd(self, ctx, slug: str, duration: str = "0", *, note: str = ""):
        """
        Generates an unlinked license key for buyers to redeem.
        Duration supports '10m', '1h', '7d', '30d', 'lifetime', etc.
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, user_row = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        expires_at, duration_label = parse_whitelist_duration(duration)

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))

            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            user_note = note or f"generated by {ctx.author.name}"
            
            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, discord_id, note, expires_at, created_at)
                VALUES (?, ?, NULL, ?, ?, ?)
            """, (script["id"], key, user_note, expires_at, now_iso))
            await conn.commit()

        # Also sync to live Railway Cloud Backend if developer is linked with API key
        if user_row and user_row.get("api_key"):
            pub_url = loader_generator.get_public_url()
            if pub_url and pub_url.startswith("http"):
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            f"{pub_url}/api/licenses/create",
                            headers={"X-API-Key": user_row["api_key"]},
                            json={
                                "slug": clean_slug,
                                "license_key": key,
                                "discord_id": None,
                                "note": user_note,
                                "expires_at": expires_at
                            },
                            timeout=aiohttp.ClientTimeout(total=5)
                        )
                except Exception:
                    pass

        dm_embed = fleed_embed(
            title=f"{script['name']} — Generated License Key",
            description=f"**Key:** `{key}`\n"
                        f"**Duration:** {duration_label}\n"
                        f"**Note:** {user_note}\n\n"
                        f"Buyers can redeem this key via `{ctx.prefix}redeem {key}` or by clicking **Redeem Key** on the control panel.",
            author=ctx.author
        )

        try:
            await ctx.author.send(embed=dm_embed)
            await ctx.send(embed=success_embed(f"generated license key for **{script['name']}** ({duration_label}). sent to your dms.", ctx.author))
        except discord.Forbidden:
            await ctx.send(embed=dm_embed)

    @whitelist_group.command(name="bulkadd", aliases=["masswhitelist", "bulkwhitelist"])
    async def bulk_add_cmd(self, ctx, slug: str, duration: str = "lifetime"):
        """
        Whitelists every member who has the buyer role for a script.
        Skips anyone who already has a key. DMs each person their key.
        Usage: ,whitelist bulkadd <slug> [duration]
        """
        ok, err, user_row = await check_script_permission(ctx, slug)
        if not ok:
            return await ctx.send(embed=error_embed(err, ctx.author))

        clean_slug = slug.strip().lower()
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()

        if not script:
            return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))

        if not script["buyer_role_id"] or not ctx.guild:
            return await ctx.send(embed=error_embed(f"no buyer role configured for `{clean_slug}`. set one with `,whitelist setrole {clean_slug} @Role`.", ctx.author))

        role = ctx.guild.get_role(script["buyer_role_id"])
        if not role:
            return await ctx.send(embed=error_embed(f"buyer role not found in this server.", ctx.author))

        # Parse duration
        dur_map = {"lifetime": 0, "0": 0, "1d": 1, "3d": 3, "7d": 7, "14d": 14, "30d": 30, "90d": 90, "365d": 365}
        days = dur_map.get(duration.lower(), None)
        if days is None:
            try:
                days = int(duration)
            except ValueError:
                return await ctx.send(embed=error_embed(f"invalid duration `{duration}`. use `lifetime`, `7d`, `30d`, etc.", ctx.author))

        expires_at = None
        if days > 0:
            expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)).isoformat()
        duration_label = "lifetime" if days == 0 else f"{days}d"

        # Gather members with the role
        members_with_role = [m for m in role.members if not m.bot]
        if not members_with_role:
            return await ctx.send(embed=warn_embed(f"no members found with {role.mention}.", ctx.author))

        status_msg = await ctx.send(embed=fleed_embed(
            title="Bulk Whitelist — Processing",
            description=f"found **{len(members_with_role)}** members with {role.mention}.\nprocessing...",
            author=ctx.author
        ))

        added = 0
        skipped = 0
        dm_sent = 0
        dm_failed = 0
        pub_url = loader_generator.get_public_url()

        for member in members_with_role:
            user_id_str = str(member.id)

            # Check if they already have a key
            async with db.get_db() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM licenses WHERE discord_id = ? AND script_id = ? AND is_banned = 0",
                    (user_id_str, script["id"])
                )
                existing = await cursor.fetchone()

            if existing:
                skipped += 1
                continue

            # Generate key
            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            async with db.get_db() as conn:
                await conn.execute("""
                    INSERT INTO licenses (script_id, license_key, discord_id, note, created_at, expires_at)
                    VALUES (?, ?, ?, 'Bulk whitelisted via buyer role', ?, ?)
                """, (script["id"], key, user_id_str, now_iso, expires_at))
                await conn.commit()

            # Sync to Railway
            if pub_url and pub_url.startswith("http") and user_row and user_row.get("api_key"):
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(
                            f"{pub_url}/api/licenses/create",
                            headers={"X-API-Key": user_row["api_key"]},
                            json={
                                "slug": clean_slug,
                                "license_key": key,
                                "discord_id": user_id_str,
                                "note": "Bulk whitelisted via buyer role",
                                "expires_at": expires_at
                            },
                            timeout=aiohttp.ClientTimeout(total=5)
                        )
                except Exception:
                    pass

            added += 1

            # DM the user
            loadstring_snippet = f'getgenv().FleedKey = "{key}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{clean_slug}?key={key}"))()'
            dm_embed = fleed_embed(
                title=f"{script['name']} — License & Loadstring",
                description=f"You have been whitelisted for **{script['name']}**.\n\n"
                            f"**Key:** `{key}`\n"
                            f"**Duration:** {duration_label}\n\n"
                            f"**Loadstring:**\n```lua\n{loadstring_snippet}\n```\n"
                            f"Execute this loadstring inside your Roblox executor.",
                author=ctx.author
            )
            try:
                await member.send(embed=dm_embed)
                dm_sent += 1
            except Exception:
                dm_failed += 1

        result_embed = fleed_embed(
            title="Bulk Whitelist — Complete",
            description=f"**Script:** {script['name']}\n"
                        f"**Duration:** {duration_label}\n\n"
                        f"✅ **Added:** {added}\n"
                        f"⏭️ **Skipped (already had key):** {skipped}\n"
                        f"📬 **DMs sent:** {dm_sent}\n"
                        f"🚫 **DMs failed (closed):** {dm_failed}",
            author=ctx.author
        )
        await status_msg.edit(embed=result_embed)

    @whitelist_group.command(name="remove", aliases=["unwhitelist", "del", "delete"])
    async def remove_whitelist_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str):
        """
        Removes a user's whitelist access for a script and revokes buyer role.
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        discord_id = str(target.id) if hasattr(target, "id") else str(target).strip("<@!>")

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ?
            """, (discord_id, clean_slug))
            license_row = await cursor.fetchone()

            if not license_row:
                return await ctx.send(embed=error_embed(f"no active whitelist found for <@{discord_id}> on `{clean_slug}`.", ctx.author))

            await conn.execute("DELETE FROM licenses WHERE id = ?", (license_row["id"],))
            await conn.commit()

        if license_row["buyer_role_id"] and ctx.guild:
            role = ctx.guild.get_role(license_row["buyer_role_id"])
            target_member = ctx.guild.get_member(int(discord_id)) if discord_id.isdigit() else None
            if role and target_member and role in target_member.roles:
                try:
                    await target_member.remove_roles(role, reason=f"unwhitelist: {license_row['script_name']}")
                except Exception:
                    pass

        embed = success_embed(f"removed whitelist access for <@{discord_id}> on **{license_row['script_name']}**.", ctx.author)
        await ctx.send(embed=embed)

    @whitelist_group.command(name="check", aliases=["userinfo", "lookup"])
    async def check_user_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: Optional[str] = None):
        """
        Checks whitelist details, keys, HWIDs, and executions for a Discord user.
        """
        ok, err_msg, _ = await check_script_permission(ctx, slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        discord_id = str(target.id) if hasattr(target, "id") else str(target).strip("<@!>")

        query = """
            SELECT l.*, s.name as script_name, s.slug as script_slug
            FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.discord_id = ?
        """
        params = [discord_id]
        if slug:
            query += " AND s.slug = ?"
            params.append(slug.strip().lower())

        async with db.get_db() as conn:
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()

        if not rows:
            return await ctx.send(embed=warn_embed(f"no whitelisted keys found for <@{discord_id}>.", ctx.author))

        lines = [f"**target:** <@{discord_id}>\n"]
        for r in rows:
            status = "banned" if r["is_banned"] else "active"
            hwid_val = f"`{r['hwid'][:16]}...`" if r["hwid"] else "`unbound`"
            expires = f"`{r['expires_at'][:10]}`" if r["expires_at"] else "`lifetime`"
            lines.append(
                f"**{r['script_name']}** (`{r['script_slug']}`)\n"
                f"↳ **key:** `{r['license_key']}`\n"
                f"↳ **status:** `{status}` • **hwid:** {hwid_val} • **execs:** `{r['execution_count']}` • **expires:** {expires}"
            )
        embed = fleed_embed(title="whitelist profile", description="\n\n".join(lines), author=ctx.author)
        await ctx.send(embed=embed)

    @whitelist_group.command(name="force-resethwid", aliases=["freset", "adminreset"])
    async def force_resethwid_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str):
        """
        Manager command to force reset a user's HWID.
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        discord_id = str(target.id) if hasattr(target, "id") else str(target).strip("<@!>")
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ?
            """, (discord_id, clean_slug))
            license_row = await cursor.fetchone()

            if not license_row:
                return await ctx.send(embed=error_embed(f"no license found for <@{discord_id}> on `{clean_slug}`.", ctx.author))

            await conn.execute("UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?", (now_iso, license_row["id"]))
            await conn.commit()

        embed = success_embed(f"force reset hwid for <@{discord_id}> on **{license_row['script_name']}**.", ctx.author)
        await ctx.send(embed=embed)

    @whitelist_group.command(name="transfer", aliases=["transferkey"])
    async def transfer_key_cmd(self, ctx, old_target: Union[discord.Member, discord.User, str], new_target: Union[discord.Member, discord.User, str], slug: str):
        """
        Transfers a license key from one Discord account to another.
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        old_id = str(old_target.id) if hasattr(old_target, "id") else str(old_target).strip("<@!>")
        new_id = str(new_target.id) if hasattr(new_target, "id") else str(new_target).strip("<@!>")

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ?
            """, (old_id, clean_slug))
            license_row = await cursor.fetchone()

            if not license_row:
                return await ctx.send(embed=error_embed(f"no license found for <@{old_id}> on `{clean_slug}`.", ctx.author))

            await conn.execute("UPDATE licenses SET discord_id = ?, hwid = NULL WHERE id = ?", (new_id, license_row["id"]))
            await conn.commit()

        if license_row["buyer_role_id"] and ctx.guild:
            role = ctx.guild.get_role(license_row["buyer_role_id"])
            if role:
                old_mem = ctx.guild.get_member(int(old_id)) if old_id.isdigit() else None
                new_mem = ctx.guild.get_member(int(new_id)) if new_id.isdigit() else None
                try:
                    if old_mem and role in old_mem.roles:
                        await old_mem.remove_roles(role, reason="license transferred")
                    if new_mem:
                        await new_mem.add_roles(role, reason="license transferred")
                except Exception:
                    pass

        embed = success_embed(
            f"transferred **{license_row['script_name']}** key from <@{old_id}> to <@{new_id}>.\n"
            f"hwid has been reset for the new user.",
            ctx.author
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="setrole", aliases=["role", "buyerrole"])
    async def set_role_cmd(self, ctx, slug: str, role: discord.Role):
        """
        Sets the Discord Buyer role for a project.
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))

            await conn.execute("UPDATE scripts SET buyer_role_id = ?, guild_id = ? WHERE id = ?", (role.id, ctx.guild.id, script["id"]))
            await conn.commit()

        await ctx.send(embed=success_embed(f"set buyer role for **{script['name']}** to {role.mention}.", ctx.author))

    # ------------------- End-User Self-Service Commands -------------------

    @commands.command(name="redeem", aliases=["claimkey"])
    async def redeem_cmd(self, ctx, key: str):
        """
        Redeems a license key directly in chat.
        """
        clean_key = key.strip().upper()
        user_id_str = str(ctx.author.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.slug as script_slug, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.license_key = ?
            """, (clean_key,))
            row = await cursor.fetchone()

            if not row:
                return await ctx.send(embed=error_embed("invalid license key.", ctx.author))

            if row["is_banned"]:
                return await ctx.send(embed=error_embed("this license key is banned.", ctx.author))

            if row["discord_id"] and row["discord_id"] != user_id_str:
                return await ctx.send(embed=error_embed("this key is already redeemed by another user.", ctx.author))

            await conn.execute("UPDATE licenses SET discord_id = ? WHERE id = ?", (user_id_str, row["id"]))
            await conn.commit()

        role_text = ""
        if row["buyer_role_id"] and ctx.guild:
            role = ctx.guild.get_role(row["buyer_role_id"])
            if role and ctx.guild.me.guild_permissions.manage_roles and ctx.guild.me.top_role > role:
                try:
                    await ctx.author.add_roles(role, reason=f"redeemed key for {row['script_name']}")
                    role_text = f"\ngranted role {role.mention}."
                except Exception:
                    pass

        embed = success_embed(
            f"redeemed key for **{row['script_name']}**.{role_text}\n"
            f"use `{ctx.prefix}script {row['script_slug']}` to get your loadstring.",
            ctx.author
        )
        await ctx.send(embed=embed)

    @commands.command(name="getscript", aliases=["script", "loadstring"])
    async def get_script_cmd(self, ctx, slug: Optional[str] = None):
        """
        Retrieves the personalized loadstring for a buyer.
        """
        user_id_str = str(ctx.author.id)
        query = """
            SELECT l.*, s.name as script_name, s.slug as script_slug
            FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.discord_id = ? AND l.is_banned = 0
        """
        params = [user_id_str]
        if slug:
            query += " AND s.slug = ?"
            params.append(slug.strip().lower())

        async with db.get_db() as conn:
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()

        if not rows and slug:
            clean_slug = slug.strip().lower()
            async with db.get_db() as conn:
                cursor = await conn.execute("SELECT id, name, slug, buyer_role_id FROM scripts WHERE slug = ?", (clean_slug,))
                script = await cursor.fetchone()

            if script and script["buyer_role_id"] and ctx.guild:
                role = ctx.guild.get_role(script["buyer_role_id"])
                if role and role in ctx.author.roles:
                    key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    async with db.get_db() as conn:
                        await conn.execute("""
                            INSERT INTO licenses (script_id, license_key, discord_id, note, created_at)
                            VALUES (?, ?, ?, 'Auto-whitelisted via Buyer Role', ?)
                        """, (script["id"], key, user_id_str, now_iso))
                        await conn.commit()

                    # Sync to Railway cloud
                    pub_url = loader_generator.get_public_url()
                    if pub_url and pub_url.startswith("http"):
                        api_key = await get_cloud_api_key(clean_slug)
                        if api_key:
                            try:
                                async with aiohttp.ClientSession() as session:
                                    await session.post(
                                        f"{pub_url}/api/licenses/create",
                                        headers={"X-API-Key": api_key},
                                        json={
                                            "slug": clean_slug,
                                            "license_key": key,
                                            "discord_id": user_id_str,
                                            "note": "Auto-whitelisted via Buyer Role",
                                            "expires_at": None
                                        },
                                        timeout=aiohttp.ClientTimeout(total=5)
                                    )
                            except Exception:
                                pass

                    rows = [{"script_name": script["name"], "script_slug": script["slug"], "license_key": key}]

        if not rows:
            return await ctx.send(embed=warn_embed(f"no redeemed keys found{' for `' + slug + '`' if slug else ''}.", ctx.author))

        pub_url = loader_generator.get_public_url()
        for r in rows:
            if pub_url and pub_url.startswith("http"):
                api_key = await get_cloud_api_key(r.get("script_slug"))
                if api_key:
                    try:
                        async with aiohttp.ClientSession() as session:
                            await session.post(
                                f"{pub_url}/api/licenses/create",
                                headers={"X-API-Key": api_key},
                                json={
                                    "slug": r.get("script_slug"),
                                    "license_key": r["license_key"],
                                    "discord_id": user_id_str,
                                    "note": "synced via getscript",
                                    "expires_at": None
                                },
                                timeout=aiohttp.ClientTimeout(total=5)
                            )
                    except Exception:
                        pass

            loadstr = f'getgenv().FleedKey = "{r["license_key"]}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{r["script_slug"]}?key={r["license_key"]}"))()'
            embed = fleed_embed(
                title=f"{r['script_name']} — loadstring",
                description=f"```lua\n{loadstr}\n```\nkey: `{r['license_key']}`",
                author=ctx.author
            )
            try:
                await ctx.author.send(embed=embed)
                await ctx.send(embed=success_embed(f"sent **{r['script_name']}** loadstring to your dms.", ctx.author))
            except discord.Forbidden:
                await ctx.send(embed=embed)

    @commands.command(name="getrole", aliases=["claimrole"])
    async def get_role_cmd(self, ctx, slug: str):
        """
        Claims your configured buyer role if you have a redeemed key.
        """
        clean_slug = slug.strip().lower()
        user_id_str = str(ctx.author.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ? AND l.is_banned = 0
            """, (user_id_str, clean_slug))
            row = await cursor.fetchone()

        if not row:
            return await ctx.send(embed=error_embed(f"no active redeemed key found for `{clean_slug}`.", ctx.author))

        if not row["buyer_role_id"] or not ctx.guild:
            return await ctx.send(embed=warn_embed("no buyer role configured for this script.", ctx.author))

        role = ctx.guild.get_role(row["buyer_role_id"])
        if not role:
            return await ctx.send(embed=error_embed("buyer role not found.", ctx.author))

        try:
            await ctx.author.add_roles(role, reason=f"claimed role: {row['script_name']}")
            await ctx.send(embed=success_embed(f"granted role {role.mention}.", ctx.author))
        except discord.Forbidden:
            await ctx.send(embed=error_embed("i do not have permission to assign that role.", ctx.author))

    @commands.command(name="resethwid", aliases=["userresethwid"])
    async def user_resethwid_cmd(self, ctx, slug: Optional[str] = None):
        """
        Resets your own HWID binding so you can play on a new PC.
        """
        user_id_str = str(ctx.author.id)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        query = """
            SELECT l.*, s.name as script_name
            FROM licenses l
            JOIN scripts s ON l.script_id = s.id
            WHERE l.discord_id = ? AND l.is_banned = 0
        """
        params = [user_id_str]
        if slug:
            query += " AND s.slug = ?"
            params.append(slug.strip().lower())

        async with db.get_db() as conn:
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()

            if not rows:
                return await ctx.send(embed=error_embed(f"no active license found on your account{' for ' + slug if slug else ''}.", ctx.author))

            for r in rows:
                await conn.execute("UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?", (now_iso, r["id"]))
            await conn.commit()

        await ctx.send(embed=success_embed(f"reset hwid for **{len(rows)}** script(s). you can now execute on your new device.", ctx.author))

    # ------------------- Additional Admin Utilities -------------------

    @whitelist_group.command(name="panel", aliases=["setup", "controlpanel"])
    async def panel_cmd(self, ctx, slug: str, *, role: str = None):
        """
        Spawns the buyer control panel.
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))

            buyer_role_id = script["buyer_role_id"] or 0
            if role:
                found_role = find_role(ctx.guild, role)
                if found_role:
                    buyer_role_id = found_role.id
                    await conn.execute("UPDATE scripts SET buyer_role_id = ?, guild_id = ? WHERE id = ?", (buyer_role_id, ctx.guild.id, script["id"]))
                    await conn.commit()

        embed = await create_buyer_panel_embed(ctx.guild, self.bot, script["name"], clean_slug)
        view = WhitelistControlPanelView(slug=clean_slug)
        await ctx.send(embed=embed, view=view)

    @whitelist_group.command(name="scripts")
    async def list_scripts_cmd(self, ctx):
        ok, err_msg, user_row = await check_script_permission(ctx, None)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        async with db.get_db() as conn:
            if user_row and user_row.get("role") != "admin":
                query = """
                    SELECT s.*, 
                           COUNT(l.id) as total_keys,
                           SUM(CASE WHEN l.is_banned = 0 THEN 1 ELSE 0 END) as active_keys
                    FROM scripts s
                    LEFT JOIN licenses l ON s.id = l.script_id
                    WHERE s.user_id = ?
                    GROUP BY s.id
                    ORDER BY s.id DESC
                """
                cursor = await conn.execute(query, (user_row["id"],))
            else:
                query = """
                    SELECT s.*, 
                           COUNT(l.id) as total_keys,
                           SUM(CASE WHEN l.is_banned = 0 THEN 1 ELSE 0 END) as active_keys
                    FROM scripts s
                    LEFT JOIN licenses l ON s.id = l.script_id
                    GROUP BY s.id
                    ORDER BY s.id DESC
                """
                cursor = await conn.execute(query)
            rows = await cursor.fetchall()

        if not rows:
            return await ctx.send(embed=warn_embed("no scripts found.", ctx.author))

        embed = fleed_embed(title="fleed managed scripts", author=ctx.author)
        for s in rows:
            mode = "vm protected" if s["is_obfuscated_mode"] else "unobfuscated"
            status = "killswitch active" if s["killswitch_active"] else "operational"
            embed.add_field(
                name=f"{s['name']} (`{s['slug']}`)",
                value=f"status: {status} | mode: {mode}\n"
                      f"active keys: {s['active_keys'] or 0} / {s['total_keys'] or 0}\n"
                      f"version: v{s['version']}",
                inline=False
            )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="mode", aliases=["setmode", "protection"])
    async def mode_cmd(self, ctx, slug: str, mode: str):
        """
        Toggles protection mode for a script: 'raw' / 'unobfuscated' (0) or 'vm' / 'obfuscated' (2).
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, user_row = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        clean_mode = mode.strip().lower()
        if clean_mode in ["0", "raw", "unobfuscated", "none", "off"]:
            mode_val = 0
            mode_name = "Unobfuscated Mode (Raw Script + Server Whitelist)"
        elif clean_mode in ["1", "stream", "armor"]:
            mode_val = 1
            mode_name = "Stream Armor"
        elif clean_mode in ["2", "vm", "obfuscated", "on", "dense"]:
            mode_val = 2
            mode_name = "O_bfuscate 1.1 VM Protected"
        else:
            return await ctx.send(embed=error_embed("invalid mode. choose `raw` (unobfuscated) or `vm` (protected).", ctx.author))

        # Update local DB and remote API if applicable
        async with db.get_db() as conn:
            await conn.execute("UPDATE scripts SET is_obfuscated_mode = ? WHERE slug = ?", (mode_val, clean_slug))
            await conn.commit()

        # Update remote backend API if configured
        pub_url = loader_generator.get_public_url()
        api_key = (user_row and user_row.get("api_key")) or await get_cloud_api_key(clean_slug)
        if pub_url and pub_url.startswith("http") and api_key:
            try:
                async with aiohttp.ClientSession() as session:
                    # Get script id
                    async with session.get(f"{pub_url}/api/scripts", headers={"X-API-Key": api_key}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            scripts = await resp.json()
                            for s in scripts:
                                if s["slug"].strip().lower() == clean_slug:
                                    await session.patch(
                                        f"{pub_url}/api/scripts/{s['id']}",
                                        headers={"X-API-Key": api_key},
                                        json={"is_obfuscated_mode": mode_val},
                                        timeout=aiohttp.ClientTimeout(total=5)
                                    )
                                    break
            except Exception:
                pass

        await ctx.send(embed=success_embed(f"updated protection mode for **`{clean_slug}`** to **{mode_name}**.", ctx.author))

    @whitelist_group.command(name="ban")
    async def ban_key_cmd(self, ctx, target: str, *, reason: str = "banned by administrator"):
        ok, err_msg, user_row = await check_script_permission(ctx, None)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        clean_target = target.strip().strip("<@!>")
        async with db.get_db() as conn:
            if clean_target.startswith("FLEED-"):
                cursor = await conn.execute("SELECT id, script_id FROM licenses WHERE license_key = ?", (clean_target.upper(),))
                lic_row = await cursor.fetchone()
                if not lic_row:
                    return await ctx.send(embed=error_embed("license key not found.", ctx.author))
                
                # Verify script ownership if developer
                if user_row and user_row.get("role") != "admin":
                    cursor = await conn.execute("SELECT user_id FROM scripts WHERE id = ?", (lic_row["script_id"],))
                    s_row = await cursor.fetchone()
                    if not s_row or s_row["user_id"] != user_row["id"]:
                        return await ctx.send(embed=error_embed("you do not own the script associated with this key.", ctx.author))

                await conn.execute("UPDATE licenses SET is_banned = 1, ban_reason = ? WHERE license_key = ?", (reason, clean_target.upper()))
            else:
                cursor = await conn.execute("SELECT id FROM licenses WHERE discord_id = ?", (clean_target,))
                if not await cursor.fetchone():
                    return await ctx.send(embed=error_embed(f"no licenses found for user <@{clean_target}>.", ctx.author))
                await conn.execute("UPDATE licenses SET is_banned = 1, ban_reason = ? WHERE discord_id = ?", (reason, clean_target))
            await conn.commit()

        await ctx.send(embed=success_embed(f"banned `{clean_target}`. reason: *{reason}*", ctx.author))

    @whitelist_group.command(name="unban")
    async def unban_key_cmd(self, ctx, target: str):
        ok, err_msg, _ = await check_script_permission(ctx, None)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        clean_target = target.strip().strip("<@!>")
        async with db.get_db() as conn:
            if clean_target.startswith("FLEED-"):
                await conn.execute("UPDATE licenses SET is_banned = 0, ban_reason = NULL WHERE license_key = ?", (clean_target.upper(),))
            else:
                await conn.execute("UPDATE licenses SET is_banned = 0, ban_reason = NULL WHERE discord_id = ?", (clean_target,))
            await conn.commit()

        await ctx.send(embed=success_embed(f"unbanned `{clean_target}`.", ctx.author))

    @whitelist_group.command(name="killswitch", aliases=["ks"])
    async def killswitch_cmd(self, ctx, slug: str):
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name, killswitch_active FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))

            new_status = 0 if script["killswitch_active"] else 1
            await conn.execute("UPDATE scripts SET killswitch_active = ? WHERE id = ?", (new_status, script["id"]))
            await conn.commit()

        status_text = "activated (executions blocked)" if new_status else "deactivated (operational)"
        await ctx.send(embed=fleed_embed(title="killswitch toggled", description=f"killswitch for **{script['name']}** is now {status_text}.", author=ctx.author))

    @whitelist_group.command(name="stats")
    async def stats_cmd(self, ctx):
        ok, err_msg, user_row = await check_script_permission(ctx, None)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        async with db.get_db() as conn:
            if user_row and user_row.get("role") != "admin":
                c1 = await conn.execute("SELECT COUNT(*) as cnt FROM scripts WHERE user_id = ?", (user_row["id"],))
                total_scripts = (await c1.fetchone())["cnt"]

                c2 = await conn.execute("""
                    SELECT COUNT(l.id) as cnt 
                    FROM licenses l
                    JOIN scripts s ON l.script_id = s.id
                    WHERE s.user_id = ? AND l.is_banned = 0
                """, (user_row["id"],))
                active_licenses = (await c2.fetchone())["cnt"]

                c3 = await conn.execute("""
                    SELECT COUNT(e.id) as total, SUM(CASE WHEN e.status != 'SUCCESS' THEN 1 ELSE 0 END) as blocked
                    FROM execution_logs e
                    JOIN scripts s ON e.script_id = s.id
                    WHERE s.user_id = ?
                """, (user_row["id"],))
                log_row = await c3.fetchone()
            else:
                c1 = await conn.execute("SELECT COUNT(*) as cnt FROM scripts")
                total_scripts = (await c1.fetchone())["cnt"]

                c2 = await conn.execute("SELECT COUNT(*) as cnt FROM licenses WHERE is_banned = 0")
                active_licenses = (await c2.fetchone())["cnt"]

                c3 = await conn.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) as blocked FROM execution_logs")
                log_row = await c3.fetchone()

            total_execs = log_row["total"] or 0
            blocked_execs = log_row["blocked"] or 0

        embed = fleed_embed(
            title="fleed security stats",
            description=f"scripts: `{total_scripts}`\n"
                        f"active licenses: `{active_licenses}`\n"
                        f"total handshakes: `{total_execs}`\n"
                        f"blocked attacks: `{blocked_execs}`",
            author=ctx.author
        )
        await ctx.send(embed=embed)

    # ------------------- Delegated Whitelist Manager Commands -------------------

    @whitelist_group.group(name="manager", aliases=["managers", "mgr", "access", "subadmin"], invoke_without_command=True)
    async def manager_group(self, ctx):
        """
        Manage delegated whitelist permissions (giving other users/roles access to whitelist people).
        """
        embed = fleed_embed(
            title="Whitelist Manager Access Control",
            description="Delegate whitelist permissions to trusted Discord users or staff roles.\n\n"
                        f"**Commands:**\n"
                        f"• `{ctx.prefix}whitelist manager add <@user> [slug/all]` — Grant user whitelist permissions\n"
                        f"• `{ctx.prefix}whitelist manager remove <@user> [slug/all]` — Revoke user whitelist permissions\n"
                        f"• `{ctx.prefix}whitelist manager role <@role> [slug/all]` — Grant an entire staff/reseller role permissions\n"
                        f"• `{ctx.prefix}whitelist manager unrole <@role> [slug/all]` — Revoke role permissions\n"
                        f"• `{ctx.prefix}whitelist manager list [slug]` — List all authorized managers\n\n"
                        f"**Shortcuts:**\n"
                        f"• `{ctx.prefix}whitelist grant <@user> [slug]`\n"
                        f"• `{ctx.prefix}whitelist revoke <@user> [slug]`",
            author=ctx.author
        )
        await ctx.send(embed=embed)

    @manager_group.command(name="add", aliases=["give", "grant", "user"])
    async def manager_add_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str = "all"):
        """
        Grants a Discord user permission to whitelist people for a script (or all scripts).
        Usage: ,whitelist manager add @user [slug/all]
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await is_script_owner_or_admin(ctx, clean_slug if clean_slug != "all" else None)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        discord_id = str(target.id) if hasattr(target, "id") else str(target).strip("<@!>")
        guild_id_str = str(ctx.guild.id) if ctx.guild else None
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        async with db.get_db() as conn:
            # Validate script if not 'all'
            script_name = "All Scripts"
            if clean_slug != "all":
                cursor = await conn.execute("SELECT name FROM scripts WHERE slug = ?", (clean_slug,))
                s_row = await cursor.fetchone()
                if not s_row:
                    return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))
                script_name = s_row["name"]

            await conn.execute("""
                INSERT INTO whitelist_managers (discord_user_id, is_role, script_slug, guild_id, granted_by, created_at)
                VALUES (?, 0, ?, ?, ?, ?)
                ON CONFLICT(discord_user_id, script_slug, is_role, guild_id) DO UPDATE SET
                    granted_by = excluded.granted_by,
                    created_at = excluded.created_at
            """, (discord_id, clean_slug, guild_id_str, str(ctx.author.id), now_iso))
            await conn.commit()

        # Auto-update permissions on existing staff whitelist channels in this server
        if ctx.guild and discord_id.isdigit():
            member_obj = ctx.guild.get_member(int(discord_id))
            if member_obj:
                for ch in ctx.guild.text_channels:
                    if ch.name in ["whitelist-staff", "staff-whitelist", "wl-staff"] or (ch.topic and "Private Whitelist Staff Hub" in ch.topic):
                        try:
                            await ch.set_permissions(member_obj, overwrite=discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, view_channel=True))
                        except Exception:
                            pass

        # DM notification to the authorized manager
        target_obj = ctx.guild.get_member(int(discord_id)) if (ctx.guild and discord_id.isdigit()) else None
        if not target_obj and discord_id.isdigit():
            try:
                target_obj = await ctx.bot.fetch_user(int(discord_id))
            except Exception:
                target_obj = None

        if target_obj:
            try:
                dm_embed = fleed_embed(
                    title="Whitelist Manager Access Granted",
                    description=f"You have been granted whitelist management access for **{script_name}** (`{clean_slug}`).\n\n"
                                f"**Granted By:** {ctx.author.mention} (`{ctx.author.name}`)\n\n"
                                f"**You can now use:**\n"
                                f"• `{ctx.prefix}whitelist add <@user> {clean_slug if clean_slug != 'all' else '<slug>'} [duration]`\n"
                                f"• `{ctx.prefix}whitelist genkey {clean_slug if clean_slug != 'all' else '<slug>'} [duration]`\n"
                                f"• `{ctx.prefix}whitelist remove <@user> {clean_slug if clean_slug != 'all' else '<slug>'}`\n"
                                f"• `{ctx.prefix}whitelist check <@user>`",
                    author=ctx.author
                )
                await target_obj.send(embed=dm_embed)
            except Exception:
                pass

        embed = success_embed(
            f"successfully granted whitelist manager access to <@{discord_id}> for **{script_name}** (`{clean_slug}`).\n"
            f"they can now whitelist users and generate license keys.",
            ctx.author
        )
        await ctx.send(embed=embed)

    @manager_group.command(name="remove", aliases=["revoke", "del", "delete"])
    async def manager_remove_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str = "all"):
        """
        Revokes a Discord user's whitelist management access.
        Usage: ,whitelist manager remove @user [slug/all]
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await is_script_owner_or_admin(ctx, clean_slug if clean_slug != "all" else None)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        discord_id = str(target.id) if hasattr(target, "id") else str(target).strip("<@!>")

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT * FROM whitelist_managers 
                WHERE discord_user_id = ? AND is_role = 0 AND (script_slug = ? OR ? = 'all')
            """, (discord_id, clean_slug, clean_slug))
            rows = await cursor.fetchall()

            if not rows:
                return await ctx.send(embed=error_embed(f"<@{discord_id}> does not have manager access for `{clean_slug}`.", ctx.author))

            if clean_slug == "all":
                await conn.execute("DELETE FROM whitelist_managers WHERE discord_user_id = ? AND is_role = 0", (discord_id,))
            else:
                await conn.execute("DELETE FROM whitelist_managers WHERE discord_user_id = ? AND is_role = 0 AND script_slug = ?", (discord_id, clean_slug))
            await conn.commit()

        await ctx.send(embed=success_embed(f"revoked whitelist manager access from <@{discord_id}> for `{clean_slug}`.", ctx.author))

    @manager_group.command(name="role", aliases=["addrole", "grantrole", "giverole"])
    async def manager_role_cmd(self, ctx, role: discord.Role, slug: str = "all"):
        """
        Grants an entire Discord role whitelist management access.
        Usage: ,whitelist manager role @StaffRole [slug/all]
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await is_script_owner_or_admin(ctx, clean_slug if clean_slug != "all" else None)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        guild_id_str = str(ctx.guild.id) if ctx.guild else None
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        async with db.get_db() as conn:
            script_name = "All Scripts"
            if clean_slug != "all":
                cursor = await conn.execute("SELECT name FROM scripts WHERE slug = ?", (clean_slug,))
                s_row = await cursor.fetchone()
                if not s_row:
                    return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))
                script_name = s_row["name"]

            await conn.execute("""
                INSERT INTO whitelist_managers (discord_user_id, is_role, script_slug, guild_id, granted_by, created_at)
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(discord_user_id, script_slug, is_role, guild_id) DO UPDATE SET
                    granted_by = excluded.granted_by,
                    created_at = excluded.created_at
            """, (str(role.id), clean_slug, guild_id_str, str(ctx.author.id), now_iso))
            await conn.commit()

        # Auto-update permissions on existing staff whitelist channels in this server
        if ctx.guild:
            for ch in ctx.guild.text_channels:
                if ch.name in ["whitelist-staff", "staff-whitelist", "wl-staff"] or (ch.topic and "Private Whitelist Staff Hub" in ch.topic):
                    try:
                        await ch.set_permissions(role, overwrite=discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, view_channel=True))
                    except Exception:
                        pass

        embed = success_embed(
            f"successfully granted whitelist manager access to role {role.mention} for **{script_name}** (`{clean_slug}`).\n"
            f"all members with this role can now whitelist users and generate license keys.",
            ctx.author
        )
        await ctx.send(embed=embed)

    @manager_group.command(name="unrole", aliases=["removerole", "revokerole", "delrole"])
    async def manager_unrole_cmd(self, ctx, role: discord.Role, slug: str = "all"):
        """
        Revokes a Discord role's whitelist management access.
        Usage: ,whitelist manager unrole @StaffRole [slug/all]
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await is_script_owner_or_admin(ctx, clean_slug if clean_slug != "all" else None)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        async with db.get_db() as conn:
            if clean_slug == "all":
                await conn.execute("DELETE FROM whitelist_managers WHERE discord_user_id = ? AND is_role = 1", (str(role.id),))
            else:
                await conn.execute("DELETE FROM whitelist_managers WHERE discord_user_id = ? AND is_role = 1 AND script_slug = ?", (str(role.id), clean_slug))
            await conn.commit()

        await ctx.send(embed=success_embed(f"revoked whitelist manager access from role {role.mention} for `{clean_slug}`.", ctx.author))

    @manager_group.command(name="list", aliases=["show", "all"])
    async def manager_list_cmd(self, ctx, slug: Optional[str] = None):
        """
        Lists all authorized whitelist managers and manager roles.
        Usage: ,whitelist manager list [slug]
        """
        ok, err_msg, _ = await check_script_permission(ctx, slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        query = "SELECT * FROM whitelist_managers"
        params = []
        if slug:
            query += " WHERE script_slug = ? OR script_slug = 'all'"
            params.append(slug.strip().lower())
        query += " ORDER BY id DESC LIMIT 30"

        async with db.get_db() as conn:
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()

        if not rows:
            return await ctx.send(embed=warn_embed("no delegated whitelist managers configured yet.", ctx.author))

        lines = []
        for i, r in enumerate(rows, start=1):
            is_role = r["is_role"] == 1
            target_mention = f"<@&{r['discord_user_id']}>" if is_role else f"<@{r['discord_user_id']}>"
            tag_type = "role" if is_role else "user"
            scope_str = f"`{r['script_slug']}`" if r["script_slug"] != "all" else "`all scripts (global)`"
            granted_by_str = f"<@{r['granted_by']}>" if r["granted_by"] else "owner"
            created_str = r["created_at"][:10] if r["created_at"] else "—"

            lines.append(
                f"**{i}.** {target_mention} (`{tag_type}`)\n"
                f"↳ **scope:** {scope_str} • **granted by:** {granted_by_str} • **date:** `{created_str}`"
            )

        embed = fleed_embed(
            title="authorized whitelist managers",
            description="\n\n".join(lines),
            author=ctx.author
        )
        await ctx.send(embed=embed)

    # Top-level direct shortcuts
    @whitelist_group.command(name="grant", aliases=["grantaccess", "giveaccess"])
    async def grant_shortcut_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str = "all"):
        """Shortcut to grant a user whitelist permissions."""
        await self.manager_add_cmd(ctx, target, slug)

    @whitelist_group.command(name="revoke", aliases=["revokeaccess"])
    async def revoke_shortcut_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str = "all"):
        """Shortcut to revoke a user's whitelist permissions."""
        await self.manager_remove_cmd(ctx, target, slug)

    @whitelist_group.command(name="setupchannel", aliases=["staffchat", "staffchannel", "setstaffchannel", "setupstaff"])
    async def setup_staff_channel_cmd(self, ctx, channel_name: str = "whitelist-staff", slug: str = "all"):
        """
        Creates or configures a private whitelist staff chat that only authorized managers and admins can see.
        Usage: ,whitelist setupchannel [channel_name] [slug]
        """
        if not ctx.guild:
            return await ctx.send(embed=error_embed("this command can only be used inside a discord server.", ctx.author))

        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await is_script_owner_or_admin(ctx, clean_slug if clean_slug != "all" else None)
        if not ok and not ctx.author.guild_permissions.administrator and ctx.author.id != ctx.guild.owner_id:
            return await ctx.send(embed=error_embed(err_msg or "only server administrators or script owners can setup staff channels.", ctx.author))

        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", channel_name.strip().lower()) or "whitelist-staff"

        # Build Permission Overwrites
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(
                read_messages=False,
                send_messages=False,
                view_channel=False
            ),
            ctx.guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                manage_channels=True,
                manage_permissions=True,
                view_channel=True
            ),
            ctx.author: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                view_channel=True
            )
        }

        # Query all authorized managers from database
        guild_id_str = str(ctx.guild.id)
        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT * FROM whitelist_managers 
                WHERE (guild_id = ? OR guild_id IS NULL)
                  AND (script_slug = ? OR script_slug = 'all')
            """, (guild_id_str, clean_slug))
            mgr_rows = await cursor.fetchall()

        # Add manager roles & users to overwrites
        for m in mgr_rows:
            target_id = m["discord_user_id"]
            if m["is_role"] == 1:
                role = ctx.guild.get_role(int(target_id)) if target_id.isdigit() else None
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, view_channel=True)
            else:
                member = ctx.guild.get_member(int(target_id)) if target_id.isdigit() else None
                if member:
                    overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True, view_channel=True)

        # Check if existing channel exists
        existing_channel = discord.utils.get(ctx.guild.text_channels, name=clean_name)
        if existing_channel:
            channel = existing_channel
            try:
                for target, overwrite in overwrites.items():
                    await channel.set_permissions(target, overwrite=overwrite)
            except Exception:
                pass
        else:
            try:
                channel = await ctx.guild.create_text_channel(
                    name=clean_name,
                    overwrites=overwrites,
                    topic="🔒 Private Whitelist Staff Hub — Authorized Managers & Admins Only",
                    reason="FleedGuard Whitelist Staff Chat Setup"
                )
            except discord.Forbidden:
                return await ctx.send(embed=error_embed("i do not have permission to create channels in this server.", ctx.author))

        # Send interactive staff panel inside the private channel
        panel_embed = await create_staff_panel_embed(ctx.guild, self.bot, clean_slug)
        view = StaffWhitelistPanelView(slug=clean_slug)
        panel_msg = await channel.send(embed=panel_embed, view=view)
        try:
            await panel_msg.pin()
        except Exception:
            pass

    @whitelist_group.command(name="broadcast", aliases=["ingamebroadcast", "notifyplayers"])
    async def broadcast_cmd(self, ctx, *, message: str):
        """
        Broadcasts an instant on-screen notification and audio chime to all active players running your script in Roblox.
        Usage: ,whitelist broadcast <message>
        """
        clean_msg = message.strip()
        if not clean_msg:
            return await ctx.send(embed=error_embed("please provide a broadcast message to send to active players.", ctx.author))

        # Check permission: developer or admin
        ok, err_msg, _ = await check_script_permission(ctx, None)
        if not ok and ctx.author.id not in config.OWNER_IDS:
            return await ctx.send(embed=error_embed("you do not have permission to send global in-game broadcasts.", ctx.author))

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=60)).isoformat()

        async with db.get_db() as conn:
            # Count currently active sessions
            cur = await conn.execute("SELECT COUNT(*) as active_cnt FROM live_sessions WHERE last_heartbeat >= datetime('now', '-2 minutes') AND is_kicked = 0")
            row = await cur.fetchone()
            active_cnt = row["active_cnt"] if row else 0

            await conn.execute("""
                INSERT INTO live_broadcasts (script_id, target_type, target_value, title, message, banner_type, duration, play_sound, created_at, expires_at)
                VALUES (NULL, 'GLOBAL', '', 'FleedGuard Announcement', ?, 'UPDATE', 10, 1, ?, ?)
            """, (clean_msg, now_iso, expires_at))
            await conn.commit()

        embed = success_embed(
            f"**📢 In-Game Broadcast Dispatched!**\n\n"
            f"**Message:** `{clean_msg}`\n"
            f"**Target:** 🌐 All Active Players (Global)\n"
            f"**Delivering to:** `{active_cnt}` live connected Roblox client(s)\n"
            f"**Sound:** 🔊 Audio Chime Enabled",
            ctx.author
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="announce", aliases=["hubannounce"])
    async def announce_cmd(self, ctx, slug: str, *, message: str):
        """
        Broadcasts an in-game message specifically to players running a specific Script Hub.
        Usage: ,whitelist announce <slug> <message>
        """
        clean_slug = slug.strip().lower()
        clean_msg = message.strip()

        ok, err_msg, script = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=60)).isoformat()

        async with db.get_db() as conn:
            cur = await conn.execute("""
                SELECT COUNT(*) as active_cnt 
                FROM live_sessions ls
                JOIN scripts s ON ls.script_id = s.id
                WHERE LOWER(s.slug) = ? AND ls.last_heartbeat >= datetime('now', '-2 minutes') AND ls.is_kicked = 0
            """, (clean_slug,))
            row = await cur.fetchone()
            active_cnt = row["active_cnt"] if row else 0

            await conn.execute("""
                INSERT INTO live_broadcasts (script_id, target_type, target_value, title, message, banner_type, duration, play_sound, created_at, expires_at)
                VALUES (?, 'SCRIPT', ?, 'FleedGuard Update', ?, 'UPDATE', 10, 1, ?, ?)
            """, (script["id"], clean_slug, clean_msg, now_iso, expires_at))
            await conn.commit()

        embed = success_embed(
            f"**📢 Script In-Game Broadcast Dispatched!**\n\n"
            f"**Script Hub:** `{clean_slug}`\n"
            f"**Message:** `{clean_msg}`\n"
            f"**Delivering to:** `{active_cnt}` live `{clean_slug}` player client(s)",
            ctx.author
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WhitelistCog(bot))

