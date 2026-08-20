import discord
from discord.ext import commands
import datetime
import secrets
import aiohttp
from typing import Optional, Union
import config
from utils import fleed_embed, success_embed, error_embed, warn_embed, find_role, send_group_help
from fleed_whitelist.database import db
from fleed_whitelist.loader_generator import loader_generator

async def check_script_permission(ctx, slug: str = None) -> tuple[bool, Optional[str], Optional[dict]]:
    """
    Verifies that the Discord user is authorized to manage a specific script or platform.
    Checks:
    1. Bot Owners (universal bypass)
    2. Website Developer Account linked via `discord_id` (owns the script or is platform admin)
    3. Server Administrator if guild configured on script
    """
    author_id_str = str(ctx.author.id)

    # 1. Bot Owners
    if ctx.author.id == 539594512981295106 or ctx.author.id in getattr(config, "OWNER_IDS", []):
        return True, None, None
    bot_owners = getattr(ctx.bot, "owner_ids", set()) or set()
    if ctx.author.id in bot_owners or author_id_str in bot_owners:
        return True, None, None

    # 2. Lookup Website Linked Developer Account
    async with db.get_db() as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE discord_id = ? AND is_active = 1", (author_id_str,))
        user_row = await cursor.fetchone()

        if not user_row:
            return False, f"you are not linked to a website developer account. run `{ctx.prefix}whitelist link <api_key>` to link your website login.", None

        if user_row["role"] == "admin":
            return True, None, dict(user_row)

        if slug:
            clean_slug = slug.strip().lower()
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script_row = await cursor.fetchone()
            if not script_row:
                return False, f"script `{clean_slug}` does not exist.", dict(user_row)

            if script_row["user_id"] != user_row["id"]:
                return False, f"you do not own the script `{clean_slug}` on the website.", dict(user_row)

        return True, None, dict(user_row)

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

    @discord.ui.button(label="Redeem Key", style=discord.ButtonStyle.success, row=0, custom_id="fg_panel_redeem:default")
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

    @discord.ui.button(label="Get Script", style=discord.ButtonStyle.primary, row=0, custom_id="fg_panel_script:default")
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
            return await interaction.response.send_message(
                embed=error_embed(f"You have not redeemed a valid license for `{slug}` yet.\nClick Redeem Key above to link your key.", interaction.user),
                ephemeral=True
            )

        pub_url = loader_generator.get_public_url()
        loadstring_snippet = f'getgenv().FleedKey = "{license_row["license_key"]}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{slug}"))()'
        
        embed = fleed_embed(
            title=f"{license_row['script_name']} — Loadstring",
            description=f"Here is your personalized execution script with your linked key:\n\n"
                        f"```lua\n{loadstring_snippet}\n```\n"
                        f"License Key: `{license_row['license_key']}`\n"
                        f"Status: Active | Executions: {license_row['execution_count']}",
            author=interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Get Role", style=discord.ButtonStyle.primary, row=0, custom_id="fg_panel_role:default")
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

    @discord.ui.button(label="Reset HWID", style=discord.ButtonStyle.success, row=1, custom_id="fg_panel_resethwid:default")
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

    @discord.ui.button(label="Unlink Key", style=discord.ButtonStyle.danger, row=1, custom_id="fg_panel_unlink:default")
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

    @discord.ui.button(label="Get Stats", style=discord.ButtonStyle.success, row=1, custom_id="fg_panel_stats:default")
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

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.data or "custom_id" not in interaction.data:
            return
        custom_id = interaction.data["custom_id"]
        if not custom_id.startswith("fg_panel_"):
            return

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
    async def add_whitelist_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str, duration_days: int = 0, *, note: str = ""):
        """
        Whitelists a user directly by @mention or Discord ID.
        """
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        discord_id = str(target.id) if hasattr(target, "id") else str(target).strip("<@!>")
        
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))

            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_iso = now_utc.isoformat()
            expires_at = None
            if duration_days > 0:
                expires_at = (now_utc + datetime.timedelta(days=duration_days)).isoformat()

            user_note = note or f"whitelisted by {ctx.author.name}"
            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, discord_id, note, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (script["id"], key, discord_id, user_note, expires_at, now_iso))
            await conn.commit()

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
        loadstring_snippet = f'getgenv().FleedKey = "{key}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{clean_slug}"))()'

        embed = success_embed(
            f"whitelisted <@{discord_id}> for **{script['name']}**.\n\n"
            f"key: `{key}`\n"
            f"duration: {f'{duration_days} days' if duration_days > 0 else 'lifetime'}\n"
            f"note: {user_note}{role_text}\n\n"
            f"loadstring:\n```lua\n{loadstring_snippet}\n```",
            ctx.author
        )
        await ctx.send(embed=embed)

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

        embed = fleed_embed(title=f"whitelist profile — <@{discord_id}>", author=ctx.author)
        for r in rows:
            status = "banned" if r["is_banned"] else "active"
            hwid_val = f"`{r['hwid'][:16]}...`" if r["hwid"] else "unbound"
            expires = r["expires_at"][:10] if r["expires_at"] else "lifetime"
            embed.add_field(
                name=f"{r['script_name']} (`{r['script_slug']}`)",
                value=f"key: `{r['license_key']}`\n"
                      f"status: {status} | hwid: {hwid_val}\n"
                      f"executions: {r['execution_count']}\n"
                      f"expires: {expires}",
                inline=False
            )
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

        if not rows:
            return await ctx.send(embed=warn_embed(f"no redeemed keys found{' for `' + slug + '`' if slug else ''}.", ctx.author))

        pub_url = loader_generator.get_public_url()
        for r in rows:
            loadstr = f'getgenv().FleedKey = "{r["license_key"]}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{r["script_slug"]}"))()'
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

        now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        
        embed = discord.Embed(
            title=f"{script['name']} script hub",
            description=f"this control panel is for the project: **{script['name']}**\n"
                        f"if you're a buyer, click on the buttons below to redeem your key, get the script or get your role\n\n"
                        f"sent by {ctx.author.name} • {now_str}",
            color=0x2B2D31
        )

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

    @whitelist_group.command(name="genkey", aliases=["createkey", "gen"])
    async def gen_key_cmd(self, ctx, slug: str, duration_days: int = 0, *, note: str = ""):
        clean_slug = slug.strip().lower()
        ok, err_msg, _ = await check_script_permission(ctx, clean_slug)
        if not ok:
            return await ctx.send(embed=error_embed(err_msg, ctx.author))

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"script `{clean_slug}` not found.", ctx.author))

            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_iso = now_utc.isoformat()
            expires_at = None
            if duration_days > 0:
                expires_at = (now_utc + datetime.timedelta(days=duration_days)).isoformat()

            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, note, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (script["id"], key, note or f"generated by {ctx.author.name}", expires_at, now_iso))
            await conn.commit()

        embed = success_embed(
            f"generated license for **{script['name']}**.\n\n"
            f"key: `{key}`\n"
            f"duration: {f'{duration_days} days' if duration_days > 0 else 'lifetime'}\n"
            f"note: {note or 'none'}",
            ctx.author
        )
        await ctx.send(embed=embed)

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

async def setup(bot):
    await bot.add_cog(WhitelistCog(bot))
