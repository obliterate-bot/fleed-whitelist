import discord
from discord.ext import commands
import datetime
import secrets
from utils import fleed_embed, success_embed, error_embed, warn_embed, find_role
from fleed_whitelist.database import db
from fleed_whitelist.loader_generator import loader_generator

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
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

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
                    role_assigned_text = f"\n🎉 Granted you the **{role.name}** role!"
                except Exception:
                    pass

        embed = success_embed(
            f"Successfully redeemed license for **{self.script_name}**!\n"
            f"🔑 **Key:** `{clean_key}`\n"
            f"👤 **Linked to:** {interaction.user.mention}{role_assigned_text}\n\n"
            f"You can now click **Get Script** to receive your loadstring.",
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

    @discord.ui.button(label="Redeem Key", emoji="🔑", style=discord.ButtonStyle.success, row=0, custom_id="fg_panel_redeem:default")
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

    @discord.ui.button(label="Get Script", emoji="📜", style=discord.ButtonStyle.primary, row=0, custom_id="fg_panel_script:default")
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
                embed=error_embed(f"You have not redeemed a valid license for `{slug}` yet!\nClick **Redeem Key** above to link your key.", interaction.user),
                ephemeral=True
            )

        pub_url = loader_generator.get_public_url()
        loadstring_snippet = f'getgenv().FleedKey = "{license_row["license_key"]}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{slug}"))()'
        
        embed = fleed_embed(
            interaction.user,
            title=f"📜 {license_row['script_name']} — Loadstring",
            description=f"Here is your personalized execution script with your linked key:\n\n"
                        f"```lua\n{loadstring_snippet}\n```\n"
                        f"🔒 **License Key:** `{license_row['license_key']}`\n"
                        f"⚡ **Status:** Active | **Executions:** {license_row['execution_count']}"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Get Role", emoji="👤", style=discord.ButtonStyle.primary, row=0, custom_id="fg_panel_role:default")
    async def role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]
        user_id_str = str(interaction.user.id)

        if not interaction.guild:
            return await interaction.response.send_message("This action can only be performed in a server.", ephemeral=True)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.id, s.name as script_name, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ? AND l.is_banned = 0
            """, (user_id_str, slug))
            row = await cursor.fetchone()

        if not row:
            return await interaction.response.send_message(
                embed=error_embed(f"No active license found linked to your Discord account for `{slug}`.", interaction.user),
                ephemeral=True
            )

        buyer_role_id = row["buyer_role_id"]
        if not buyer_role_id:
            return await interaction.response.send_message(
                embed=warn_embed("No buyer role has been configured for this script hub.", interaction.user),
                ephemeral=True
            )

        role = interaction.guild.get_role(buyer_role_id)
        if not role:
            return await interaction.response.send_message(
                embed=error_embed("The configured buyer role could not be found on this server.", interaction.user),
                ephemeral=True
            )

        if role in interaction.user.roles:
            return await interaction.response.send_message(
                embed=warn_embed(f"You already have the **{role.name}** role!", interaction.user),
                ephemeral=True
            )

        try:
            await interaction.user.add_roles(role, reason=f"FleedGuard Whitelist Role Claim ({slug})")
            await interaction.response.send_message(
                embed=success_embed(f"Granted you the **{role.name}** buyer role!", interaction.user),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Bot does not have permission to manage this role. Please ensure bot's role is higher.", interaction.user),
                ephemeral=True
            )

    @discord.ui.button(label="Reset HWID", emoji="⚙️", style=discord.ButtonStyle.success, row=0, custom_id="fg_panel_resethwid:default")
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
                    embed=error_embed(f"No active license found linked to your account for `{slug}`.", interaction.user),
                    ephemeral=True
                )

            if not license_row["hwid"]:
                return await interaction.response.send_message(
                    embed=warn_embed("Your license is currently unbound. You can launch immediately on any device.", interaction.user),
                    ephemeral=True
                )

            await conn.execute("UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?", (now_iso, license_row["id"]))
            await conn.commit()

        await interaction.response.send_message(
            embed=success_embed(f"HWID reset successfully for **{license_row['script_name']}**! You can now execute on your new device.", interaction.user),
            ephemeral=True
        )

    @discord.ui.button(label="Unlink Key", emoji="🔓", style=discord.ButtonStyle.danger, row=0, custom_id="fg_panel_unlink:default")
    async def unlink_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]
        user_id_str = str(interaction.user.id)

        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.id, s.name as script_name, s.buyer_role_id
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.discord_id = ? AND s.slug = ?
            """, (user_id_str, slug))
            license_row = await cursor.fetchone()

            if not license_row:
                return await interaction.response.send_message(
                    embed=error_embed(f"No license currently linked to your Discord account for `{slug}`.", interaction.user),
                    ephemeral=True
                )

            await conn.execute("UPDATE licenses SET discord_id = NULL WHERE id = ?", (license_row["id"],))
            await conn.commit()

        # Remove role if present
        if interaction.guild and license_row["buyer_role_id"]:
            role = interaction.guild.get_role(license_row["buyer_role_id"])
            if role and role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(role, reason=f"FleedGuard License Unlinked ({slug})")
                except Exception:
                    pass

        await interaction.response.send_message(
            embed=success_embed(f"Unlinked license key from your Discord account for **{license_row['script_name']}**.", interaction.user),
            ephemeral=True
        )

    @discord.ui.button(label="Get Stats", emoji="📊", style=discord.ButtonStyle.success, row=1, custom_id="fg_panel_stats:default")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        slug = button.custom_id.split(":", 1)[1]

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (slug,))
            script = await cursor.fetchone()
            if not script:
                return await interaction.response.send_message("Script not found.", ephemeral=True)

            c1 = await conn.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_banned = 0 THEN 1 ELSE 0 END) as active FROM licenses WHERE script_id = ?", (script["id"],))
            lic_data = await c1.fetchone()

            c2 = await conn.execute("SELECT COUNT(*) as execs FROM execution_logs WHERE script_id = ?", (script["id"],))
            exec_data = await c2.fetchone()

        mode = "🔒 Armored VM Mode" if script["is_obfuscated_mode"] else "📄 Unobfuscated Mode"
        ks_status = "🔴 KILLSWITCH ACTIVE" if script["killswitch_active"] else "🟢 Operational"

        embed = fleed_embed(
            interaction.user,
            title=f"📊 Project Analytics — {script['name']}",
            description=f"**Status:** {ks_status}\n"
                        f"**Protection:** {mode}\n"
                        f"**Version:** v{script['version']}\n"
                        f"**Total Buyers / Keys:** {lic_data['active'] or 0} active ({lic_data['total'] or 0} total)\n"
                        f"**Total Executions:** {exec_data['execs'] or 0}"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WhitelistCog(commands.Cog, name="whitelist"):
    """
    FleedGuard Roblox Whitelist & License Security Cog
    """
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Register persistent dynamic listener for control panels across restarts
        self.bot.add_view(WhitelistControlPanelView())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # Handle persistent button routing for dynamic custom_ids
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

    @commands.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    async def whitelist_group(self, ctx):
        embed = fleed_embed(
            ctx.author,
            title="🛡️ FleedGuard Whitelist Management",
            description="Manage script whitelists, license keys, and interactive buyer panels.\n\n"
                        "**Commands:**\n"
                        f"• `{ctx.prefix}wl panel <slug> [role]` — Spawn interactive buyer control panel\n"
                        f"• `{ctx.prefix}wl scripts` — List all registered scripts & hubs\n"
                        f"• `{ctx.prefix}wl genkey <slug> [days] [note]` — Generate a new license key\n"
                        f"• `{ctx.prefix}wl resethwid <key>` — Reset HWID binding for a key\n"
                        f"• `{ctx.prefix}wl ban <key> [reason]` — Ban a license key\n"
                        f"• `{ctx.prefix}wl unban <key>` — Unban a license key\n"
                        f"• `{ctx.prefix}wl killswitch <slug>` — Toggle script killswitch\n"
                        f"• `{ctx.prefix}wl info <key>` — Check license status & HWID\n"
                        f"• `{ctx.prefix}wl loadstring <slug>` — Get 1-liner loadstring\n"
                        f"• `{ctx.prefix}wl stats` — Platform analytics"
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="panel", aliases=["setup", "controlpanel"])
    async def panel_cmd(self, ctx, slug: str, *, role: str = None):
        """
        Spawns the exact buyer control panel with interactive buttons.
        """
        clean_slug = slug.strip().lower()

        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"Script `{clean_slug}` not found in FleedGuard!", ctx.author))

            buyer_role_id = script["buyer_role_id"] or 0
            if role:
                found_role = find_role(ctx.guild, role)
                if found_role:
                    buyer_role_id = found_role.id
                    await conn.execute("UPDATE scripts SET buyer_role_id = ?, guild_id = ? WHERE id = ?", (buyer_role_id, ctx.guild.id, script["id"]))
                    await conn.commit()

        now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        
        # Build the exact Embed match
        embed = discord.Embed(
            title=f"{script['name']} script hub",
            description=f"This control panel is for the project: **{script['name']}**\n"
                        f"If you're a buyer, click on the buttons below to redeem your key, get the script or get your role\n\n"
                        f"Sent by {ctx.author.name} • {now_str}",
            color=0x2B2D31
        )

        view = WhitelistControlPanelView(slug=clean_slug)
        await ctx.send(embed=embed, view=view)

    @whitelist_group.command(name="scripts")
    async def list_scripts_cmd(self, ctx):
        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT s.*, 
                       COUNT(l.id) as total_keys,
                       SUM(CASE WHEN l.is_banned = 0 THEN 1 ELSE 0 END) as active_keys
                FROM scripts s
                LEFT JOIN licenses l ON s.id = l.script_id
                GROUP BY s.id
                ORDER BY s.id DESC
            """)
            rows = await cursor.fetchall()

        if not rows:
            return await ctx.send(embed=warn_embed("No scripts found. Create one on the FleedGuard web dashboard!", ctx.author))

        embed = fleed_embed(ctx.author, title="📜 FleedGuard Managed Scripts")
        for s in rows:
            mode = "🔒 VM Protected" if s["is_obfuscated_mode"] else "📄 Unobfuscated"
            status = "🔴 KILLSWITCH ACTIVE" if s["killswitch_active"] else "🟢 Operational"
            embed.add_field(
                name=f"{s['name']} (`{s['slug']}`)",
                value=f"**Status:** {status} | **Mode:** {mode}\n"
                      f"**Active Keys:** {s['active_keys'] or 0} / {s['total_keys'] or 0}\n"
                      f"**Version:** v{s['version']}",
                inline=False
            )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="genkey", aliases=["createkey", "gen"])
    async def gen_key_cmd(self, ctx, slug: str, duration_days: int = 0, *, note: str = ""):
        clean_slug = slug.strip().lower()
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"Script `{clean_slug}` not found.", ctx.author))

            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_iso = now_utc.isoformat()
            expires_at = None
            if duration_days > 0:
                expires_at = (now_utc + datetime.timedelta(days=duration_days)).isoformat()

            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, note, expires_at, created_at, discord_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (script["id"], key, note or f"Generated via Discord by {ctx.author.name}", expires_at, now_iso, str(ctx.author.id)))
            await conn.commit()

        embed = success_embed(
            f"Successfully generated new license for **{script['name']}**!\n\n"
            f"🔑 **Key:** `{key}`\n"
            f"⏳ **Duration:** {f'{duration_days} Days' if duration_days > 0 else 'Lifetime'}\n"
            f"📝 **Note:** {note or 'None'}",
            ctx.author
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="resethwid", aliases=["reset"])
    async def reset_hwid_cmd(self, ctx, key: str):
        clean_key = key.strip().upper()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, hwid FROM licenses WHERE license_key = ?", (clean_key,))
            row = await cursor.fetchone()
            if not row:
                return await ctx.send(embed=error_embed("License key not found.", ctx.author))

            await conn.execute("""
                UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?
            """, (now_iso, row["id"]))
            await conn.commit()

        await ctx.send(embed=success_embed(f"HWID successfully reset for `{clean_key}`. User can now bind to a new device.", ctx.author))

    @whitelist_group.command(name="ban")
    async def ban_key_cmd(self, ctx, key: str, *, reason: str = "Banned by administrator"):
        clean_key = key.strip().upper()
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id FROM licenses WHERE license_key = ?", (clean_key,))
            if not await cursor.fetchone():
                return await ctx.send(embed=error_embed("License key not found.", ctx.author))

            await conn.execute("UPDATE licenses SET is_banned = 1, ban_reason = ? WHERE license_key = ?", (reason, clean_key))
            await conn.commit()

        await ctx.send(embed=success_embed(f"Banned license key `{clean_key}`. Reason: *{reason}*", ctx.author))

    @whitelist_group.command(name="unban")
    async def unban_key_cmd(self, ctx, key: str):
        clean_key = key.strip().upper()
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id FROM licenses WHERE license_key = ?", (clean_key,))
            if not await cursor.fetchone():
                return await ctx.send(embed=error_embed("License key not found.", ctx.author))

            await conn.execute("UPDATE licenses SET is_banned = 0, ban_reason = NULL WHERE license_key = ?", (clean_key,))
            await conn.commit()

        await ctx.send(embed=success_embed(f"Unbanned license key `{clean_key}`.", ctx.author))

    @whitelist_group.command(name="killswitch", aliases=["ks"])
    async def killswitch_cmd(self, ctx, slug: str):
        clean_slug = slug.strip().lower()
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name, killswitch_active FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"Script `{clean_slug}` not found.", ctx.author))

            new_status = 0 if script["killswitch_active"] else 1
            await conn.execute("UPDATE scripts SET killswitch_active = ? WHERE id = ?", (new_status, script["id"]))
            await conn.commit()

        status_text = "🔴 **ACTIVATED** (all executions blocked)" if new_status else "🟢 **DEACTIVATED** (normal operations resumed)"
        await ctx.send(embed=fleed_embed(ctx.author, title="⚡ Killswitch Toggled", description=f"Killswitch for **{script['name']}** is now {status_text}."))

    @whitelist_group.command(name="info")
    async def info_key_cmd(self, ctx, key: str):
        clean_key = key.strip().upper()
        async with db.get_db() as conn:
            cursor = await conn.execute("""
                SELECT l.*, s.name as script_name, s.slug as script_slug
                FROM licenses l
                JOIN scripts s ON l.script_id = s.id
                WHERE l.license_key = ?
            """, (clean_key,))
            row = await cursor.fetchone()

        if not row:
            return await ctx.send(embed=error_embed("License key not found.", ctx.author))

        status = "🔴 Banned" if row["is_banned"] else "🟢 Active"
        hwid_display = f"`{row['hwid'][:16]}...`" if row["hwid"] else "❌ *Unbound*"
        expires = row["expires_at"][:10] if row["expires_at"] else "⭐ *Lifetime*"

        embed = fleed_embed(
            ctx.author,
            title=f"🔑 License: {clean_key}",
            description=f"**Script:** {row['script_name']} (`{row['script_slug']}`)\n"
                        f"**Status:** {status}\n"
                        f"**HWID:** {hwid_display}\n"
                        f"**Executions:** {row['execution_count']} / {row['max_executions'] if row['max_executions'] != -1 else '∞'}\n"
                        f"**Expires:** {expires}\n"
                        f"**Note:** {row['note'] or 'None'}\n"
                        f"**Created:** {row['created_at'][:10]}"
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="loadstring", aliases=["loader"])
    async def loadstring_cmd(self, ctx, slug: str):
        clean_slug = slug.strip().lower()
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT name, slug FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"Script `{clean_slug}` not found.", ctx.author))

        pub_url = loader_generator.get_public_url()
        loadstr = f'loadstring(game:HttpGet("{pub_url}/v1/loader/{clean_slug}"))()'
        embed = fleed_embed(
            ctx.author,
            title=f"📜 Loadstring — {script['name']}",
            description=f"```lua\n{loadstr}\n```\n*Before executing, users must set their key:*\n```lua\ngetgenv().FleedKey = \"YOUR_KEY_HERE\"\n{loadstr}\n```"
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="stats")
    async def stats_cmd(self, ctx):
        async with db.get_db() as conn:
            c1 = await conn.execute("SELECT COUNT(*) as cnt FROM scripts")
            total_scripts = (await c1.fetchone())["cnt"]

            c2 = await conn.execute("SELECT COUNT(*) as cnt FROM licenses WHERE is_banned = 0")
            active_licenses = (await c2.fetchone())["cnt"]

            c3 = await conn.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status != 'SUCCESS' THEN 1 ELSE 0 END) as blocked FROM execution_logs")
            log_row = await c3.fetchone()
            total_execs = log_row["total"] or 0
            blocked_execs = log_row["blocked"] or 0

        embed = fleed_embed(
            ctx.author,
            title="📊 FleedGuard Global Security Stats",
            description=f"**Scripts Managed:** `{total_scripts}`\n"
                        f"**Active Licenses:** `{active_licenses}`\n"
                        f"**Total Handshakes:** `{total_execs}`\n"
                        f"**Blocked Tamper/Crack Attempts:** `{blocked_execs}`"
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WhitelistCog(bot))
