import discord
from discord.ext import commands
from discord import app_commands
import datetime
import secrets
from typing import Optional, Union
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
                embed=fleed_embed(interaction.user, title="Role Already Assigned", description=f"You already have the {role.mention} role!"),
                ephemeral=True
            )

        try:
            await interaction.user.add_roles(role, reason=f"FleedGuard Claim Role: {slug}")
            await interaction.response.send_message(
                embed=success_embed(f"Successfully granted you the {role.mention} role!", interaction.user),
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("I don't have permission to assign that role. Please ensure my role is placed higher than the buyer role.", interaction.user),
                ephemeral=True
            )

    @discord.ui.button(label="Reset HWID", emoji="⚙️", style=discord.ButtonStyle.success, row=1, custom_id="fg_panel_resethwid:default")
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

            # Reset HWID in DB
            await conn.execute("""
                UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?
            """, (now_iso, license_row["id"]))
            await conn.commit()

        embed = success_embed(
            f"Successfully reset your Hardware ID for **{license_row['script_name']}**!\n"
            f"🔑 **Key:** `{license_row['license_key']}`\n\n"
            f"You can now execute the script on a new device or PC.",
            interaction.user
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Unlink Key", emoji="🔓", style=discord.ButtonStyle.danger, row=1, custom_id="fg_panel_unlink:default")
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

            # Unlink Discord ID
            await conn.execute("UPDATE licenses SET discord_id = NULL WHERE id = ?", (license_row["id"],))
            await conn.commit()

        # Remove Buyer Role
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

    @discord.ui.button(label="Get Stats", emoji="📊", style=discord.ButtonStyle.success, row=1, custom_id="fg_panel_stats:default")
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

        status_str = "🔴 Inactive (Killswitch)" if script["killswitch_active"] else "🟢 Active & Running"
        embed = fleed_embed(
            interaction.user,
            title=f"📊 {script['name']} — Live Statistics",
            description=f"**Status:** {status_str}\n"
                        f"**Version:** v{script['version']}\n"
                        f"**Total Buyers / Keys:** {lic_data['active'] or 0} active ({lic_data['total'] or 0} total)\n"
                        f"**Total Executions:** {exec_data['execs'] or 0}"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WhitelistCog(commands.Cog, name="whitelist"):
    """
    FleedGuard Roblox Whitelist & License Security Cog
    Full parity with Luarmor / PandAuth Discord bot functionality.
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

    # ------------------- Luarmor Core Whitelist Commands -------------------

    @commands.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    async def whitelist_group(self, ctx):
        """Displays help menu for Whitelist management commands."""
        embed = fleed_embed(
            ctx.author,
            title="🛡️ FleedGuard Whitelist Management (Luarmor Parity)",
            description="Manage script whitelists, buyers, HWID resets, and control panels.\n\n"
                        "**Manager Commands:**\n"
                        f"• `{ctx.prefix}whitelist add <@user/id> <slug> [days] [note]` — Whitelist a buyer directly\n"
                        f"• `{ctx.prefix}whitelist remove <@user/id> <slug>` — Remove buyer access\n"
                        f"• `{ctx.prefix}whitelist check <@user/id> [slug]` — Check buyer status & HWID\n"
                        f"• `{ctx.prefix}whitelist force-resethwid <@user/id> [slug]` — Force reset user HWID\n"
                        f"• `{ctx.prefix}whitelist transfer <@old_user> <@new_user> <slug>` — Transfer key ownership\n"
                        f"• `{ctx.prefix}whitelist setrole <slug> <@role>` — Configure buyer role\n"
                        f"• `{ctx.prefix}whitelist genkey <slug> [days] [note]` — Create unlinked license key\n"
                        f"• `{ctx.prefix}whitelist ban <key/@user> [reason]` — Ban a key or user\n"
                        f"• `{ctx.prefix}whitelist unban <key/@user>` — Unban a key or user\n"
                        f"• `{ctx.prefix}whitelist killswitch <slug>` — Toggle script killswitch\n"
                        f"• `{ctx.prefix}whitelist panel <slug> [role]` — Spawn interactive buyer control panel\n\n"
                        "**Buyer Self-Service Commands:**\n"
                        f"• `{ctx.prefix}redeem <key>` — Redeem a license key\n"
                        f"• `{ctx.prefix}getscript [slug]` — Receive your loadstring with key\n"
                        f"• `{ctx.prefix}getrole [slug]` — Claim your Discord buyer role\n"
                        f"• `{ctx.prefix}resethwid [slug]` — Reset your HWID for new device"
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="add", aliases=["user", "create"])
    async def add_whitelist_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str, duration_days: int = 0, *, note: str = ""):
        """
        Whitelists a user directly by @mention or Discord ID (Luarmor /whitelist command).
        Generates a key, binds it directly to their Discord ID, and grants the buyer role!
        """
        clean_slug = slug.strip().lower()
        discord_id = str(target.id) if hasattr(target, "id") else str(target).strip("<@!>")
        
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT * FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"Script hub `{clean_slug}` not found.", ctx.author))

            # Generate unique key
            key = f"FLEED-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_iso = now_utc.isoformat()
            expires_at = None
            if duration_days > 0:
                expires_at = (now_utc + datetime.timedelta(days=duration_days)).isoformat()

            user_note = note or f"Whitelisted via Discord by {ctx.author.name}"
            await conn.execute("""
                INSERT INTO licenses (script_id, license_key, discord_id, note, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (script["id"], key, discord_id, user_note, expires_at, now_iso))
            await conn.commit()

        # Handle Role Assignment if member is in guild
        role_text = ""
        if script["buyer_role_id"] and ctx.guild:
            role = ctx.guild.get_role(script["buyer_role_id"])
            target_member = ctx.guild.get_member(int(discord_id)) if discord_id.isdigit() else None
            if role and target_member and ctx.guild.me.guild_permissions.manage_roles and ctx.guild.me.top_role > role:
                try:
                    await target_member.add_roles(role, reason=f"FleedGuard Direct Whitelist: {script['name']}")
                    role_text = f"\n🎉 Assigned role {role.mention} to user."
                except Exception:
                    pass

        pub_url = loader_generator.get_public_url()
        loadstring_snippet = f'getgenv().FleedKey = "{key}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{clean_slug}"))()'

        embed = success_embed(
            f"Successfully whitelisted <@{discord_id}> for **{script['name']}**!\n\n"
            f"🔑 **Key:** `{key}`\n"
            f"⏳ **Duration:** {f'{duration_days} Days' if duration_days > 0 else 'Lifetime'}\n"
            f"📝 **Note:** {user_note}{role_text}\n\n"
            f"**Execution Loadstring:**\n```lua\n{loadstring_snippet}\n```",
            ctx.author
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="remove", aliases=["unwhitelist", "del", "delete"])
    async def remove_whitelist_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str):
        """
        Removes a user's whitelist access for a script and revokes buyer role.
        """
        clean_slug = slug.strip().lower()
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
                return await ctx.send(embed=error_embed(f"No active whitelist found for <@{discord_id}> on `{clean_slug}`.", ctx.author))

            # Delete or ban license
            await conn.execute("DELETE FROM licenses WHERE id = ?", (license_row["id"],))
            await conn.commit()

        # Remove Role if in guild
        if license_row["buyer_role_id"] and ctx.guild:
            role = ctx.guild.get_role(license_row["buyer_role_id"])
            target_member = ctx.guild.get_member(int(discord_id)) if discord_id.isdigit() else None
            if role and target_member and role in target_member.roles:
                try:
                    await target_member.remove_roles(role, reason=f"FleedGuard Unwhitelist: {license_row['script_name']}")
                except Exception:
                    pass

        embed = success_embed(f"Removed whitelist access for <@{discord_id}> on **{license_row['script_name']}**.", ctx.author)
        await ctx.send(embed=embed)

    @whitelist_group.command(name="check", aliases=["userinfo", "lookup"])
    async def check_user_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: Optional[str] = None):
        """
        Checks whitelist details, keys, HWIDs, and executions for a Discord user.
        """
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
            return await ctx.send(embed=warn_embed(f"No whitelisted keys found for <@{discord_id}>.", ctx.author))

        embed = fleed_embed(ctx.author, title=f"👤 Whitelist Profile — <@{discord_id}>")
        for r in rows:
            status = "🔴 Banned" if r["is_banned"] else "🟢 Active"
            hwid_val = f"`{r['hwid'][:16]}...`" if r["hwid"] else "❌ *Unbound*"
            expires = r["expires_at"][:10] if r["expires_at"] else "⭐ *Lifetime*"
            embed.add_field(
                name=f"{r['script_name']} (`{r['script_slug']}`)",
                value=f"🔑 **Key:** `{r['license_key']}`\n"
                      f"⚡ **Status:** {status} | **HWID:** {hwid_val}\n"
                      f"📈 **Executions:** {r['execution_count']}\n"
                      f"⏳ **Expires:** {expires}",
                inline=False
            )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="force-resethwid", aliases=["freset", "adminreset"])
    async def force_resethwid_cmd(self, ctx, target: Union[discord.Member, discord.User, str], slug: str):
        """
        Manager command to force reset a user's HWID (Luarmor /force-resethwid).
        """
        clean_slug = slug.strip().lower()
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
                return await ctx.send(embed=error_embed(f"No license found for <@{discord_id}> on `{clean_slug}`.", ctx.author))

            await conn.execute("UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?", (now_iso, license_row["id"]))
            await conn.commit()

        embed = success_embed(f"Forcefully reset HWID for <@{discord_id}> on **{license_row['script_name']}**.", ctx.author)
        await ctx.send(embed=embed)

    @whitelist_group.command(name="transfer", aliases=["transferkey"])
    async def transfer_key_cmd(self, ctx, old_target: Union[discord.Member, discord.User, str], new_target: Union[discord.Member, discord.User, str], slug: str):
        """
        Transfers a license key from one Discord account to another.
        """
        clean_slug = slug.strip().lower()
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
                return await ctx.send(embed=error_embed(f"No license found for <@{old_id}> on `{clean_slug}`.", ctx.author))

            # Update owner and wipe HWID
            await conn.execute("UPDATE licenses SET discord_id = ?, hwid = NULL WHERE id = ?", (new_id, license_row["id"]))
            await conn.commit()

        # Update Roles
        if license_row["buyer_role_id"] and ctx.guild:
            role = ctx.guild.get_role(license_row["buyer_role_id"])
            if role:
                old_mem = ctx.guild.get_member(int(old_id)) if old_id.isdigit() else None
                new_mem = ctx.guild.get_member(int(new_id)) if new_id.isdigit() else None
                try:
                    if old_mem and role in old_mem.roles:
                        await old_mem.remove_roles(role, reason="License transferred")
                    if new_mem:
                        await new_mem.add_roles(role, reason="License transferred")
                except Exception:
                    pass

        embed = success_embed(
            f"Successfully transferred **{license_row['script_name']}** key from <@{old_id}> to <@{new_id}>!\n"
            f"HWID has been automatically reset for the new user.",
            ctx.author
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="setrole", aliases=["role", "buyerrole"])
    async def set_role_cmd(self, ctx, slug: str, role: discord.Role):
        """
        Sets the Discord Buyer role for a project.
        """
        clean_slug = slug.strip().lower()
        async with db.get_db() as conn:
            cursor = await conn.execute("SELECT id, name FROM scripts WHERE slug = ?", (clean_slug,))
            script = await cursor.fetchone()
            if not script:
                return await ctx.send(embed=error_embed(f"Script `{clean_slug}` not found.", ctx.author))

            await conn.execute("UPDATE scripts SET buyer_role_id = ?, guild_id = ? WHERE id = ?", (role.id, ctx.guild.id, script["id"]))
            await conn.commit()

        await ctx.send(embed=success_embed(f"Set buyer role for **{script['name']}** to {role.mention}.", ctx.author))

    # ------------------- End-User Self-Service Commands -------------------

    @commands.command(name="redeem", aliases=["claimkey", "claim"])
    async def redeem_cmd(self, ctx, key: str):
        """
        Redeems a license key directly in chat (Luarmor /redeem).
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
                return await ctx.send(embed=error_embed("Invalid license key.", ctx.author))

            if row["is_banned"]:
                return await ctx.send(embed=error_embed("This license key is banned.", ctx.author))

            if row["discord_id"] and row["discord_id"] != user_id_str:
                return await ctx.send(embed=error_embed("This key is already redeemed by another user!", ctx.author))

            await conn.execute("UPDATE licenses SET discord_id = ? WHERE id = ?", (user_id_str, row["id"]))
            await conn.commit()

        # Grant Role
        role_text = ""
        if row["buyer_role_id"] and ctx.guild:
            role = ctx.guild.get_role(row["buyer_role_id"])
            if role and ctx.guild.me.guild_permissions.manage_roles and ctx.guild.me.top_role > role:
                try:
                    await ctx.author.add_roles(role, reason=f"Redeemed key for {row['script_name']}")
                    role_text = f"\n🎉 Granted you the {role.mention} role!"
                except Exception:
                    pass

        embed = success_embed(
            f"Successfully redeemed key for **{row['script_name']}**!{role_text}\n"
            f"Use `{ctx.prefix}script {row['script_slug']}` to get your loadstring.",
            ctx.author
        )
        await ctx.send(embed=embed)

    @commands.command(name="getscript", aliases=["script", "loadstring"])
    async def get_script_cmd(self, ctx, slug: Optional[str] = None):
        """
        Retrieves the personalized loadstring for a buyer (Luarmor /script).
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
            return await ctx.send(embed=warn_embed(f"You don't have any redeemed keys{' for `' + slug + '`' if slug else ''}.", ctx.author))

        pub_url = loader_generator.get_public_url()
        for r in rows:
            loadstr = f'getgenv().FleedKey = "{r["license_key"]}"\nloadstring(game:HttpGet("{pub_url}/v1/loader/{r["script_slug"]}"))()'
            embed = fleed_embed(
                ctx.author,
                title=f"📜 {r['script_name']} — Loadstring",
                description=f"```lua\n{loadstr}\n```\n🔑 **Key:** `{r['license_key']}`"
            )
            # Try DMing the script for privacy
            try:
                await ctx.author.send(embed=embed)
                await ctx.send(embed=success_embed(f"Sent your **{r['script_name']}** loadstring to your DMs! 📩", ctx.author))
            except discord.Forbidden:
                await ctx.send(embed=embed)

    @commands.command(name="getrole", aliases=["claimrole"])
    async def get_role_cmd(self, ctx, slug: str):
        """
        Claims your configured buyer role if you have a redeemed key (Luarmor /getrole).
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
            return await ctx.send(embed=error_embed(f"You don't have an active redeemed key for `{clean_slug}`.", ctx.author))

        if not row["buyer_role_id"] or not ctx.guild:
            return await ctx.send(embed=warn_embed("No buyer role has been configured for this script.", ctx.author))

        role = ctx.guild.get_role(row["buyer_role_id"])
        if not role:
            return await ctx.send(embed=error_embed("Configured buyer role was not found.", ctx.author))

        try:
            await ctx.author.add_roles(role, reason=f"Claimed buyer role for {row['script_name']}")
            await ctx.send(embed=success_embed(f"Granted you the {role.mention} role!", ctx.author))
        except discord.Forbidden:
            await ctx.send(embed=error_embed("I don't have permission to assign that role.", ctx.author))

    @commands.command(name="resethwid", aliases=["userresethwid"])
    async def user_resethwid_cmd(self, ctx, slug: Optional[str] = None):
        """
        Resets your own HWID binding so you can play on a new PC (Luarmor /resethwid).
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
                return await ctx.send(embed=error_embed(f"No active license found on your account{' for ' + slug if slug else ''}.", ctx.author))

            for r in rows:
                await conn.execute("UPDATE licenses SET hwid = NULL, ip_address = NULL, last_reset_at = ? WHERE id = ?", (now_iso, r["id"]))
            await conn.commit()

        await ctx.send(embed=success_embed(f"Successfully reset HWID for **{len(rows)}** script(s). You can now execute on your new device!", ctx.author))

    # ------------------- Additional Admin Utilities -------------------

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
                INSERT INTO licenses (script_id, license_key, note, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (script["id"], key, note or f"Generated via Discord by {ctx.author.name}", expires_at, now_iso))
            await conn.commit()

        embed = success_embed(
            f"Successfully generated new license for **{script['name']}**!\n\n"
            f"🔑 **Key:** `{key}`\n"
            f"⏳ **Duration:** {f'{duration_days} Days' if duration_days > 0 else 'Lifetime'}\n"
            f"📝 **Note:** {note or 'None'}",
            ctx.author
        )
        await ctx.send(embed=embed)

    @whitelist_group.command(name="ban")
    async def ban_key_cmd(self, ctx, target: str, *, reason: str = "Banned by administrator"):
        clean_target = target.strip().strip("<@!>")
        async with db.get_db() as conn:
            if clean_target.startswith("FLEED-"):
                cursor = await conn.execute("SELECT id FROM licenses WHERE license_key = ?", (clean_target.upper(),))
                if not await cursor.fetchone():
                    return await ctx.send(embed=error_embed("License key not found.", ctx.author))
                await conn.execute("UPDATE licenses SET is_banned = 1, ban_reason = ? WHERE license_key = ?", (reason, clean_target.upper()))
            else:
                cursor = await conn.execute("SELECT id FROM licenses WHERE discord_id = ?", (clean_target,))
                if not await cursor.fetchone():
                    return await ctx.send(embed=error_embed(f"No licenses found for user <@{clean_target}>.", ctx.author))
                await conn.execute("UPDATE licenses SET is_banned = 1, ban_reason = ? WHERE discord_id = ?", (reason, clean_target))
            await conn.commit()

        await ctx.send(embed=success_embed(f"Banned `{clean_target}`. Reason: *{reason}*", ctx.author))

    @whitelist_group.command(name="unban")
    async def unban_key_cmd(self, ctx, target: str):
        clean_target = target.strip().strip("<@!>")
        async with db.get_db() as conn:
            if clean_target.startswith("FLEED-"):
                await conn.execute("UPDATE licenses SET is_banned = 0, ban_reason = NULL WHERE license_key = ?", (clean_target.upper(),))
            else:
                await conn.execute("UPDATE licenses SET is_banned = 0, ban_reason = NULL WHERE discord_id = ?", (clean_target,))
            await conn.commit()

        await ctx.send(embed=success_embed(f"Unbanned `{clean_target}`.", ctx.author))

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
