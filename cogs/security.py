import discord
from discord.ext import commands
import re
import time
import asyncio
from collections import defaultdict
from utils import fleed_embed, success_embed, error_embed, CommandGroupPaginatorView, send_group_help

import config

# ==================== PERMISSION CHECK DECORATORS ====================

def _is_owner_check(ctx_or_bot, user_id: int) -> bool:
    if not user_id:
        return False
    if user_id == 539594512981295106 or user_id in getattr(config, "OWNER_IDS", []):
        return True
    bot = getattr(ctx_or_bot, "bot", ctx_or_bot)
    owner_ids = getattr(bot, "owner_ids", set()) or set()
    return user_id in owner_ids or str(user_id) in owner_ids

def is_antinuke_authorized():
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id or _is_owner_check(ctx, ctx.author.id):
            return True
        row = await ctx.bot.db.fetchrow(
            "SELECT is_admin FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ? AND is_admin = 1",
            (ctx.guild.id, ctx.author.id)
        )
        if row is not None:
            return True
        await ctx.send(embed=error_embed("only the server owner or an antinuke admin can manage antinuke", ctx.author))
        return False
    return commands.check(predicate)

def is_server_owner_only():
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id or _is_owner_check(ctx, ctx.author.id):
            return True
        await ctx.send(embed=error_embed("only the server owner can manage antinuke admins and core settings", ctx.author))
        return False
    return commands.check(predicate)

def is_admin_or_owner():
    async def predicate(ctx):
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator or _is_owner_check(ctx, ctx.author.id):
            return True
        await ctx.send(embed=error_embed("you must have the `administrator` permission to execute this command", ctx.author))
        return False
    return commands.check(predicate)

class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # sliding rate limiter tracking: guild_id -> user_id -> action -> list[timestamps]
        self.rate_limits = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        self.join_history = defaultdict(list)
        self.panicked_guilds = set()

    async def is_whitelisted(self, guild: discord.Guild, user_id: int) -> bool:
        if user_id == guild.owner_id or user_id == self.bot.user.id or _is_owner_check(self.bot, user_id):
            return True
        row = await self.bot.db.fetchrow(
            "SELECT user_id FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?",
            (guild.id, user_id)
        )
        return row is not None

    async def punish_user(self, guild: discord.Guild, member: discord.Member, reason: str, action: str = "ban"):
        try:
            if action == "ban":
                await guild.ban(member, reason=f"fleed security: {reason.lower()}")
            elif action == "kick":
                await member.kick(reason=f"fleed security: {reason.lower()}")
            elif action == "strip":
                # remove all roles lower than bot's top role
                removable_roles = [r for r in member.roles if r.name != "@everyone" and r < guild.me.top_role]
                if removable_roles:
                    await member.remove_roles(*removable_roles, reason=f"fleed security: {reason.lower()}")
            from utils import send_modlog
            await send_modlog(self.bot, guild, action, guild.me, member, f"antinuke: {reason.lower()}")
        except Exception:
            pass

    def check_rate_limit(self, guild_id: int, user_id: int, action: str, limit: int, window: int = 10) -> bool:
        now = time.time()
        timestamps = self.rate_limits[guild_id][user_id][action]
        # filter out old timestamps
        timestamps = [t for t in timestamps if now - t <= window]
        timestamps.append(now)
        self.rate_limits[guild_id][user_id][action] = timestamps
        return len(timestamps) > limit

    # ==================== LIVE ANTINUKE LISTENERS ====================

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        cfg = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild.id,))
        if not cfg or not cfg["enabled"]:
            return

        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            user = entry.user
            if user and not await self.is_whitelisted(guild, user.id):
                limit = cfg["channel_limit"] or 3
                if self.check_rate_limit(guild.id, user.id, "channel_delete", limit):
                    member = guild.get_member(user.id)
                    if member:
                        await self.punish_user(guild, member, "antinuke: mass channel deletion", "ban")
                    # recover channel
                    try:
                        if isinstance(channel, discord.TextChannel):
                            await guild.create_text_channel(name=channel.name, category=channel.category, topic=channel.topic)
                        elif isinstance(channel, discord.VoiceChannel):
                            await guild.create_voice_channel(name=channel.name, category=channel.category)
                    except Exception:
                        pass
            break

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        cfg = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild.id,))
        if not cfg or not cfg["enabled"]:
            return

        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
            user = entry.user
            if user and not await self.is_whitelisted(guild, user.id):
                limit = cfg["channel_limit"] or 3
                if self.check_rate_limit(guild.id, user.id, "channel_create", limit):
                    member = guild.get_member(user.id)
                    if member:
                        await self.punish_user(guild, member, "antinuke: mass channel creation spam", "ban")
                    try:
                        await channel.delete(reason="fleed security: unauthorized channel create")
                    except Exception:
                        pass
            break

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        cfg = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild.id,))
        if not cfg or not cfg["enabled"]:
            return

        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            user = entry.user
            if user and not await self.is_whitelisted(guild, user.id):
                limit = cfg["role_limit"] or 3
                if self.check_rate_limit(guild.id, user.id, "role_delete", limit):
                    member = guild.get_member(user.id)
                    if member:
                        await self.punish_user(guild, member, "antinuke: mass role deletion", "ban")
                    # recover role
                    try:
                        await guild.create_role(name=role.name, color=role.color, permissions=role.permissions, hoist=role.hoist, mentionable=role.mentionable)
                    except Exception:
                        pass
            break

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        guild = after.guild
        cfg = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild.id,))
        if not cfg or not cfg["enabled"]:
            return

        # check if dangerous permissions were added
        dangerous_perms = ["administrator", "ban_members", "kick_members", "manage_guild", "manage_roles", "manage_channels"]
        added_dangerous = False
        for perm in dangerous_perms:
            if not getattr(before.permissions, perm) and getattr(after.permissions, perm):
                added_dangerous = True
                break

        if added_dangerous:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                user = entry.user
                if user and not await self.is_whitelisted(guild, user.id):
                    member = guild.get_member(user.id)
                    if member:
                        await self.punish_user(guild, member, "antinuke: unauthorized dangerous permission grant", "strip")
                    try:
                        await after.edit(permissions=before.permissions, reason="fleed security: reverted unauthorized perms")
                    except Exception:
                        pass
                break

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        cfg = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild.id,))
        if not cfg or not cfg["enabled"]:
            return

        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            mod = entry.user
            if mod and not await self.is_whitelisted(guild, mod.id):
                limit = cfg["ban_limit"] or 3
                if self.check_rate_limit(guild.id, mod.id, "member_ban", limit):
                    member = guild.get_member(mod.id)
                    if member:
                        await self.punish_user(guild, member, "antinuke: mass ban threshold reached", "ban")
                    try:
                        await guild.unban(user, reason="fleed security: restored banned member")
                    except Exception:
                        pass
            break

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        cfg = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild.id,))
        if not cfg or not cfg["enabled"]:
            return

        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            mod = entry.user
            if mod and not await self.is_whitelisted(guild, mod.id):
                limit = cfg["kick_limit"] or 3
                if self.check_rate_limit(guild.id, mod.id, "member_kick", limit):
                    mod_member = guild.get_member(mod.id)
                    if mod_member:
                        await self.punish_user(guild, mod_member, "antinuke: mass kick threshold reached", "ban")
            break

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        cfg = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild.id,))
        if not cfg or not cfg["enabled"]:
            return

        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
            user = entry.user
            if user and not await self.is_whitelisted(guild, user.id):
                member = guild.get_member(user.id)
                if member:
                    await self.punish_user(guild, member, "antinuke: unauthorized webhook created", "strip")
                # delete webhook
                try:
                    hooks = await channel.webhooks()
                    for h in hooks:
                        if h.user and h.user.id == user.id:
                            await h.delete(reason="fleed security: unauthorized webhook")
                except Exception:
                    pass
            break

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        cfg = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (after.guild.id if hasattr(after, 'guild') else after.id,))
        if not cfg or not cfg["enabled"]:
            return

        async for entry in after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
            user = entry.user
            if user and not await self.is_whitelisted(after, user.id):
                member = after.get_member(user.id)
                if member:
                    await self.punish_user(after, member, "antinuke: unauthorized guild settings update", "strip")
                # revert name if changed
                if before.name != after.name:
                    try:
                        await after.edit(name=before.name, reason="fleed security: reverted server name")
                    except Exception:
                        pass
            break

    # ==================== LIVE ANTIRAID LISTENERS ====================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cfg = await self.bot.db.fetchrow("SELECT * FROM antiraid_config WHERE guild_id = ?", (guild.id,))
        if not cfg or not cfg["enabled"]:
            return

        now = time.time()

        # 1. Anti-Bot / Unauthorized Bot Add Check
        if member.bot:
            nuke_cfg = await self.bot.db.fetchrow("SELECT botadd FROM antinuke_config WHERE guild_id = ?", (guild.id,))
            antibot_active = (nuke_cfg and nuke_cfg["botadd"]) or cfg["unverifiedbots"]
            if antibot_active:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.bot_add):
                    inviter = entry.user
                    if inviter:
                        # check if inviter is whitelisted
                        if not await self.is_whitelisted(guild, inviter.id):
                            # unauthorized bot addition
                            inviter_mem = guild.get_member(inviter.id)
                            if inviter_mem:
                                await self.punish_user(guild, inviter_mem, "antiraid: rogue bot invitation", "strip")
                            await member.ban(reason="fleed antiraid: unauthorized bot addition blocked")
                            return
                        # check if unverified bot is blocked
                        if cfg["unverifiedbots"] and not member.public_flags.verified_bot:
                            if not await self.is_whitelisted(guild, member.id):
                                await member.kick(reason="fleed antiraid: unverified bot blocked")
                                return
                    break

        # 2. Account Age Check (e.g. accounts < 3 days old)
        if cfg["age"]:
            age_days = (now - member.created_at.timestamp()) / 86400
            if age_days < 3:
                try:
                    await member.kick(reason=f"antiraid: account age too young ({int(age_days * 24)}h old)")
                    return
                except Exception:
                    pass

        # 3. Default Avatar Filter Check
        if cfg["avatar"] and member.avatar is None:
            try:
                await member.kick(reason="antiraid: default avatar not permitted during raid protection")
                return
            except Exception:
                pass

        # 4. Username Pattern Matching
        patterns = await self.bot.db.fetch("SELECT pattern FROM antiraid_patterns WHERE guild_id = ?", (guild.id,))
        for p in patterns:
            if re.search(p["pattern"], member.name.lower()):
                try:
                    await member.ban(reason=f"antiraid: username pattern match '{p['pattern']}'")
                    return
                except Exception:
                    pass

        # 5. Mass Join Raid Burst Detection
        if cfg["massjoin"]:
            history = self.join_history[guild.id]
            history = [t for t in history if now - t <= 10]
            history.append(now)
            self.join_history[guild.id] = history
            if len(history) > 5:
                # trigger emergency lockdown
                try:
                    await guild.default_role.edit(permissions=discord.Permissions(send_messages=False, connect=False), reason="fleed antiraid: automatic massjoin lockdown")
                    await member.kick(reason="antiraid: massjoin raid spike detected")
                except Exception:
                    pass

    # ==================== LIVE FILTER & MESSAGE LISTENERS ====================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        # 1. Mass Mention Check
        if len(message.mentions) >= 5:
            if not await self.is_whitelisted(message.guild, message.author.id):
                try:
                    await message.delete()
                    await self.punish_user(message.guild, message.author, "antiraid: mass mention burst", "kick")
                    return
                except Exception:
                    pass

        # 2. Invite Link Filter Check
        invite_pattern = r"(discord\.(gg|io|me|li)|discordapp\.com\/invite|discord\.com\/invite)\/[a-zA-Z0-9]+"
        if re.search(invite_pattern, message.content.lower()):
            if not await self.is_whitelisted(message.guild, message.author.id):
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}: discord invite links are not permitted here", delete_after=5)
                    return
                except Exception:
                    pass

        # 3. Word Filter Check
        words = await self.bot.db.fetch("SELECT word FROM filter_words WHERE guild_id = ? AND is_whitelist = 0", (message.guild.id,))
        for w in words:
            if w["word"] in message.content.lower():
                if not await self.is_whitelisted(message.guild, message.author.id):
                    try:
                        await message.delete()
                        await message.channel.send(f"{message.author.mention}: that message contains blacklisted content", delete_after=5)
                        return
                    except Exception:
                        pass

    # ==================== ANTINUKE COMMAND SUITE ====================

    @commands.hybrid_group(name="antinuke", invoke_without_command=True)
    @is_antinuke_authorized()
    async def antinuke(self, ctx):
        cmd_list = [self.antinuke] + list(self.antinuke.walk_commands())
        view = CommandGroupPaginatorView(ctx.author.id, cmd_list, prefix=ctx.prefix or ",", module_name="security")
        embed = view.get_embed(ctx.author)
        await ctx.send(embed=embed, view=view)

    @antinuke.command(name="enable", aliases=["on"])
    @is_antinuke_authorized()
    async def antinuke_enable(self, ctx):
        await self.bot.db.execute(
            "INSERT INTO antinuke_config (guild_id, enabled) VALUES (?, 1) ON CONFLICT(guild_id) DO UPDATE SET enabled = 1",
            (ctx.guild.id,)
        )
        await ctx.send(embed=success_embed("antinuke protection enabled", ctx.author))

    @antinuke.command(name="disable", aliases=["off"])
    @is_antinuke_authorized()
    async def antinuke_disable(self, ctx):
        await self.bot.db.execute(
            "INSERT INTO antinuke_config (guild_id, enabled) VALUES (?, 0) ON CONFLICT(guild_id) DO UPDATE SET enabled = 0",
            (ctx.guild.id,)
        )
        await ctx.send(embed=success_embed("antinuke protection disabled", ctx.author))

    @antinuke.command(name="state", aliases=["config", "settings", "status"])
    @is_antinuke_authorized()
    async def antinuke_state(self, ctx):
        row = await self.bot.db.fetchrow("SELECT * FROM antinuke_config WHERE guild_id = ?", (ctx.guild.id,))
        status = "enabled" if row and row["enabled"] else "disabled"
        desc = (
            f"status: **{status}**\n"
            f"channel limit: **{row['channel_limit'] if row else 3}/10s**\n"
            f"role limit: **{row['role_limit'] if row else 3}/10s**\n"
            f"ban limit: **{row['ban_limit'] if row else 3}/10s**\n"
            f"kick limit: **{row['kick_limit'] if row else 3}/10s**\n"
            f"webhook limit: **{row['webhook_limit'] if row else 3}/10s**\n"
            f"vanity / botadd / guild update: **protected**"
        )
        await ctx.send(embed=fleed_embed(title="antinuke configuration", description=desc, author=ctx.author))

    @antinuke.command(name="panic", aliases=["emergency"])
    @is_antinuke_authorized()
    async def antinuke_panic(self, ctx):
        self.panicked_guilds.add(ctx.guild.id)
        # remove dangerous permissions from all non-whitelisted roles
        for role in ctx.guild.roles:
            if role < ctx.guild.me.top_role and role.name != "@everyone":
                try:
                    if role.permissions.administrator or role.permissions.manage_guild or role.permissions.ban_members:
                        await role.edit(permissions=discord.Permissions.none(), reason="fleed antinuke: emergency panic mode")
                except Exception:
                    pass
        await ctx.send(embed=fleed_embed(title="panic mode activated", description="stripped all administrative permissions from roles and enabled emergency lock", author=ctx.author))

    @antinuke.command(name="unpanic", aliases=["recover"])
    @is_antinuke_authorized()
    async def antinuke_unpanic(self, ctx):
        self.panicked_guilds.discard(ctx.guild.id)
        await ctx.send(embed=success_embed("deactivated panic mode", ctx.author))

    @antinuke.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    @is_antinuke_authorized()
    async def antinuke_whitelist_grp(self, ctx):
        await send_group_help(ctx, ctx.command)

    @antinuke_whitelist_grp.command(name="add")
    @is_antinuke_authorized()
    async def antinuke_whitelist_add(self, ctx, target: discord.User):
        await self.bot.db.execute("INSERT OR REPLACE INTO antinuke_whitelist (guild_id, user_id, is_admin) VALUES (?, ?, 0)", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"whitelisted {target.mention} in antinuke", ctx.author))

    @antinuke_whitelist_grp.command(name="remove", aliases=["del"])
    @is_antinuke_authorized()
    async def antinuke_whitelist_remove(self, ctx, target: discord.User):
        await self.bot.db.execute("DELETE FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"removed {target.mention} from antinuke whitelist", ctx.author))

    @antinuke_whitelist_grp.command(name="list")
    @is_antinuke_authorized()
    async def antinuke_whitelist_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id, is_admin FROM antinuke_whitelist WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"<@{r['user_id']}> ({'admin' if r['is_admin'] else 'whitelisted'})" for r in rows]
        await ctx.send(embed=fleed_embed(title="antinuke whitelist", description="\n".join(lines) or "no whitelisted users", author=ctx.author))

    @antinuke.group(name="admin", invoke_without_command=True)
    @is_server_owner_only()
    async def antinuke_admin_grp(self, ctx):
        await send_group_help(ctx, ctx.command)

    @antinuke_admin_grp.command(name="add")
    @is_server_owner_only()
    async def antinuke_admin_add(self, ctx, member: discord.Member):
        await self.bot.db.execute("INSERT OR REPLACE INTO antinuke_whitelist (guild_id, user_id, is_admin) VALUES (?, ?, 1)", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"added {member.mention} as antinuke admin", ctx.author))

    @antinuke_admin_grp.command(name="remove", aliases=["del"])
    @is_server_owner_only()
    async def antinuke_admin_remove(self, ctx, member: discord.Member):
        await self.bot.db.execute("DELETE FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"removed {member.mention} from antinuke admins", ctx.author))

    @antinuke_admin_grp.command(name="list")
    @is_server_owner_only()
    async def antinuke_admin_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id FROM antinuke_whitelist WHERE guild_id = ? AND is_admin = 1", (ctx.guild.id,))
        lines = [f"<@{r['user_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="antinuke admins", description="\n".join(lines) or "no admins", author=ctx.author))

    @antinuke.command(name="threshold")
    @is_antinuke_authorized()
    async def antinuke_threshold(self, ctx, module: str, limit: int):
        valid = ["channel", "role", "ban", "kick", "webhook", "emoji", "sticker"]
        if module.lower() not in valid:
            return await ctx.send(embed=error_embed(f"invalid module: `{module.lower()}` (choose: {', '.join(valid)})", ctx.author))
        col = f"{module.lower()}_limit"
        await self.bot.db.execute(
            f"INSERT INTO antinuke_config (guild_id, {col}) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET {col} = ?",
            (ctx.guild.id, limit, limit)
        )
        await ctx.send(embed=success_embed(f"set antinuke `{module.lower()}` threshold to `{limit}/10s`", ctx.author))

    # ==================== ANTIRAID COMMAND SUITE ====================

    @commands.hybrid_group(name="antiraid", invoke_without_command=True)
    @is_admin_or_owner()
    async def antiraid(self, ctx):
        cmd_list = [self.antiraid] + list(self.antiraid.walk_commands())
        view = CommandGroupPaginatorView(ctx.author.id, cmd_list, prefix=ctx.prefix or ",", module_name="security")
        embed = view.get_embed(ctx.author)
        await ctx.send(embed=embed, view=view)

    @antiraid.command(name="enable", aliases=["on"])
    @is_admin_or_owner()
    async def antiraid_enable(self, ctx):
        await self.bot.db.execute(
            "INSERT INTO antiraid_config (guild_id, enabled, massjoin, massmention, avatar, age, unverifiedbots) VALUES (?, 1, 1, 1, 1, 1, 1) ON CONFLICT(guild_id) DO UPDATE SET enabled = 1, massjoin = 1, massmention = 1, avatar = 1, age = 1, unverifiedbots = 1",
            (ctx.guild.id,)
        )
        await ctx.send(embed=success_embed("enabled full antiraid protection suite", ctx.author))

    @antiraid.command(name="disable", aliases=["off"])
    @is_admin_or_owner()
    async def antiraid_disable(self, ctx):
        await self.bot.db.execute(
            "INSERT INTO antiraid_config (guild_id, enabled) VALUES (?, 0) ON CONFLICT(guild_id) DO UPDATE SET enabled = 0",
            (ctx.guild.id,)
        )
        await ctx.send(embed=success_embed("disabled antiraid protection", ctx.author))

    @antiraid.command(name="state", aliases=["config", "settings", "status"])
    @is_admin_or_owner()
    async def antiraid_state(self, ctx):
        row = await self.bot.db.fetchrow("SELECT * FROM antiraid_config WHERE guild_id = ?", (ctx.guild.id,))
        desc = (
            f"system: **{'enabled' if row and row['enabled'] else 'disabled'}**\n"
            f"massjoin protection: **{'on' if row and row['massjoin'] else 'off'}**\n"
            f"massmention filter: **{'on' if row and row['massmention'] else 'off'}**\n"
            f"default avatar block: **{'on' if row and row['avatar'] else 'off'}**\n"
            f"account age filter: **{'on (<3 days)' if row and row['age'] else 'off'}**\n"
            f"unverified bots filter: **{'on' if row and row['unverifiedbots'] else 'off'}**"
        )
        await ctx.send(embed=fleed_embed(title="antiraid status", description=desc, author=ctx.author))

    @antiraid.command(name="massjoin")
    @is_admin_or_owner()
    async def antiraid_massjoin(self, ctx, status: str):
        val = 1 if status.lower() in ["on", "enable", "true", "1"] else 0
        await self.bot.db.execute("UPDATE antiraid_config SET massjoin = ? WHERE guild_id = ?", (val, ctx.guild.id))
        await ctx.send(embed=success_embed(f"antiraid massjoin protection set to `{status.lower()}`", ctx.author))

    @antiraid.command(name="massmention")
    @is_admin_or_owner()
    async def antiraid_massmention(self, ctx, status: str):
        val = 1 if status.lower() in ["on", "enable", "true", "1"] else 0
        await self.bot.db.execute("UPDATE antiraid_config SET massmention = ? WHERE guild_id = ?", (val, ctx.guild.id))
        await ctx.send(embed=success_embed(f"antiraid massmention filter set to `{status.lower()}`", ctx.author))

    @antiraid.command(name="avatar")
    @is_admin_or_owner()
    async def antiraid_avatar(self, ctx, status: str):
        val = 1 if status.lower() in ["on", "enable", "true", "1"] else 0
        await self.bot.db.execute("UPDATE antiraid_config SET avatar = ? WHERE guild_id = ?", (val, ctx.guild.id))
        await ctx.send(embed=success_embed(f"antiraid default avatar filter set to `{status.lower()}`", ctx.author))

    @antiraid.command(name="age")
    @is_admin_or_owner()
    async def antiraid_age(self, ctx, status: str):
        val = 1 if status.lower() in ["on", "enable", "true", "1"] else 0
        await self.bot.db.execute("UPDATE antiraid_config SET age = ? WHERE guild_id = ?", (val, ctx.guild.id))
        await ctx.send(embed=success_embed(f"antiraid account age filter set to `{status.lower()}`", ctx.author))

    @antiraid.command(name="unverifiedbots")
    @is_admin_or_owner()
    async def antiraid_unverifiedbots(self, ctx, status: str):
        val = 1 if status.lower() in ["on", "enable", "true", "1"] else 0
        await self.bot.db.execute("UPDATE antiraid_config SET unverifiedbots = ? WHERE guild_id = ?", (val, ctx.guild.id))
        await ctx.send(embed=success_embed(f"antiraid unverified bots filter set to `{status.lower()}`", ctx.author))

    @antiraid.group(name="bots", aliases=["antibot", "bot"], invoke_without_command=True)
    @is_admin_or_owner()
    async def antiraid_bots_grp(self, ctx):
        await send_group_help(ctx, ctx.command)

    @antiraid_bots_grp.command(name="toggle")
    @is_admin_or_owner()
    async def antiraid_bots_toggle(self, ctx, status: str):
        val = 1 if status.lower() in ["on", "enable", "true", "1"] else 0
        await self.bot.db.execute(
            "INSERT INTO antinuke_config (guild_id, botadd) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET botadd = ?",
            (ctx.guild.id, val, val)
        )
        await ctx.send(embed=success_embed(f"anti-bot protection set to `{status.lower()}`", ctx.author))

    @antiraid_bots_grp.command(name="unverified")
    @is_admin_or_owner()
    async def antiraid_bots_unverified(self, ctx, status: str):
        await self.antiraid_unverifiedbots(ctx, status=status)

    @antiraid_bots_grp.command(name="whitelist", aliases=["wl"])
    @is_admin_or_owner()
    async def antiraid_bots_wl_add(self, ctx, bot_id: int):
        await self.bot.db.execute("INSERT OR REPLACE INTO antinuke_whitelist (guild_id, user_id, is_admin) VALUES (?, ?, 0)", (ctx.guild.id, bot_id))
        await ctx.send(embed=success_embed(f"whitelisted bot `{bot_id}` from antibot filters", ctx.author))

    @antiraid_bots_grp.command(name="unwhitelist", aliases=["unwl"])
    @is_admin_or_owner()
    async def antiraid_bots_wl_remove(self, ctx, bot_id: int):
        await self.bot.db.execute("DELETE FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, bot_id))
        await ctx.send(embed=success_embed(f"removed bot `{bot_id}` from antibot whitelist", ctx.author))

    @antiraid_bots_grp.command(name="whitelisted", aliases=["wllist"])
    @is_admin_or_owner()
    async def antiraid_bots_wl_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id FROM antinuke_whitelist WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"`{r['user_id']}`" for r in rows]
        await ctx.send(embed=fleed_embed(title="antibot whitelisted bots", description=", ".join(lines) or "none", author=ctx.author))


    @antiraid.group(name="username", invoke_without_command=True)
    @is_admin_or_owner()
    async def antiraid_username_grp(self, ctx):
        await send_group_help(ctx, ctx.command)

    @antiraid_username_grp.command(name="add")
    @is_admin_or_owner()
    async def antiraid_username_add(self, ctx, pattern: str):
        await self.bot.db.execute("INSERT OR REPLACE INTO antiraid_patterns (guild_id, pattern) VALUES (?, ?)", (ctx.guild.id, pattern.lower()))
        await ctx.send(embed=success_embed(f"added username raid pattern `{pattern.lower()}`", ctx.author))

    @antiraid_username_grp.command(name="remove", aliases=["del"])
    @is_admin_or_owner()
    async def antiraid_username_remove(self, ctx, pattern: str):
        await self.bot.db.execute("DELETE FROM antiraid_patterns WHERE guild_id = ? AND pattern = ?", (ctx.guild.id, pattern.lower()))
        await ctx.send(embed=success_embed(f"removed username raid pattern `{pattern.lower()}`", ctx.author))

    @antiraid_username_grp.command(name="list")
    @is_admin_or_owner()
    async def antiraid_username_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT pattern FROM antiraid_patterns WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"`{r['pattern']}`" for r in rows]
        await ctx.send(embed=fleed_embed(title="username raid patterns", description=", ".join(lines) or "none", author=ctx.author))

    # ==================== FILTERS & STRIKES ====================

    @commands.hybrid_group(name="filter", invoke_without_command=True)
    @is_admin_or_owner()
    async def filter_cmd(self, ctx):
        cmd_list = [self.filter_cmd] + list(self.filter_cmd.walk_commands())
        view = CommandGroupPaginatorView(ctx.author.id, cmd_list, prefix=ctx.prefix or ",", module_name="security")
        embed = view.get_embed(ctx.author)
        await ctx.send(embed=embed, view=view)

    @filter_cmd.command(name="add")
    @is_admin_or_owner()
    async def filter_add(self, ctx, *, word: str):
        await self.bot.db.execute("INSERT OR IGNORE INTO filter_words (guild_id, word, is_whitelist) VALUES (?, ?, 0)", (ctx.guild.id, word.lower()))
        await ctx.send(embed=success_embed(f"added `{word.lower()}` to word filter", ctx.author))

    @filter_cmd.command(name="remove", aliases=["delete", "del"])
    @is_admin_or_owner()
    async def filter_remove(self, ctx, *, word: str):
        await self.bot.db.execute("DELETE FROM filter_words WHERE guild_id = ? AND word = ? AND is_whitelist = 0", (ctx.guild.id, word.lower()))
        await ctx.send(embed=success_embed(f"removed `{word.lower()}` from word filter", ctx.author))

    @filter_cmd.command(name="list")
    @is_admin_or_owner()
    async def filter_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT word FROM filter_words WHERE guild_id = ? AND is_whitelist = 0", (ctx.guild.id,))
        lines = [f"`{r['word']}`" for r in rows]
        await ctx.send(embed=fleed_embed(title="filtered words", description=", ".join(lines) or "none", author=ctx.author))

    @filter_cmd.command(name="reset", aliases=["clear"])
    @is_admin_or_owner()
    async def filter_reset(self, ctx):
        await self.bot.db.execute("DELETE FROM filter_words WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("cleared all filtered words", ctx.author))

    @filter_cmd.group(name="regex", invoke_without_command=True)
    @is_admin_or_owner()
    async def filter_regex_grp(self, ctx):
        await send_group_help(ctx, ctx.command)

    @filter_regex_grp.command(name="add")
    @is_admin_or_owner()
    async def filter_regex_add(self, ctx, name: str, pattern: str):
        await self.bot.db.execute("INSERT OR REPLACE INTO filter_regex (guild_id, name, pattern) VALUES (?, ?, ?)", (ctx.guild.id, name.lower(), pattern))
        await ctx.send(embed=success_embed(f"added regex rule `{name.lower()}`", ctx.author))

    @filter_regex_grp.command(name="remove", aliases=["del"])
    @is_admin_or_owner()
    async def filter_regex_remove(self, ctx, name: str):
        await self.bot.db.execute("DELETE FROM filter_regex WHERE guild_id = ? AND name = ?", (ctx.guild.id, name.lower()))
        await ctx.send(embed=success_embed(f"removed regex rule `{name.lower()}`", ctx.author))

    @filter_regex_grp.command(name="list")
    @is_admin_or_owner()
    async def filter_regex_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT name, pattern FROM filter_regex WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"`{r['name']}`: `{r['pattern']}`" for r in rows]
        await ctx.send(embed=fleed_embed(title="regex filter rules", description="\n".join(lines) or "none", author=ctx.author))

    # ==================== FAKEPERMISSIONS & INCIDENTS ====================

    @commands.hybrid_group(name="fakepermissions", aliases=["fakeperms"], invoke_without_command=True)
    @is_admin_or_owner()
    async def fakepermissions(self, ctx):
        await send_group_help(ctx, ctx.command)

    @fakepermissions.command(name="add")
    @is_admin_or_owner()
    async def fakepermissions_add(self, ctx, role: discord.Role, *, permissions: str):
        requested = {item.strip().lower().replace(" ", "_") for item in permissions.split(",") if item.strip()}
        valid = {name for name, _ in discord.Permissions.all()}
        unknown = sorted(requested - valid)
        if unknown:
            return await ctx.send(embed=error_embed(f"unknown permissions: {', '.join(unknown)}", ctx.author))
        await self.bot.db.execute("INSERT OR REPLACE INTO fake_permissions (guild_id, role_id, permissions) VALUES (?, ?, ?)", (ctx.guild.id, role.id, ",".join(sorted(requested))))
        await ctx.send(embed=success_embed(f"granted bot-command permission overrides `{', '.join(sorted(requested))}` to {role.name}", ctx.author))

    @fakepermissions.command(name="remove")
    @is_admin_or_owner()
    async def fakepermissions_remove(self, ctx, role: discord.Role):
        await self.bot.db.execute("DELETE FROM fake_permissions WHERE guild_id = ? AND role_id = ?", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"removed fake permissions from {role.name}", ctx.author))

    @fakepermissions.command(name="list")
    @is_admin_or_owner()
    async def fakepermissions_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT role_id, permissions FROM fake_permissions WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"<@&{r['role_id']}> — `{r['permissions']}`" for r in rows]
        await ctx.send(embed=fleed_embed(title="bot-command permission overrides", description="\n".join(lines) or "none configured", author=ctx.author))

    @commands.hybrid_group(name="incidents", invoke_without_command=True)
    @is_admin_or_owner()
    async def incidents(self, ctx):
        await send_group_help(ctx, ctx.command)

    @incidents.command(name="list")
    @is_admin_or_owner()
    async def incidents_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT incident_type, actor_id, details, created_at FROM security_incidents WHERE guild_id = ? ORDER BY created_at DESC LIMIT 25", (ctx.guild.id,))
        lines = [f"<t:{r['created_at']}:R> **{r['incident_type']}** by <@{r['actor_id']}> — {r['details'][:100]}" for r in rows]
        await ctx.send(embed=fleed_embed(title="recent security incidents", description="\n".join(lines) or "none recorded", author=ctx.author))

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        monitored = {
            discord.AuditLogAction.ban, discord.AuditLogAction.kick,
            discord.AuditLogAction.role_create, discord.AuditLogAction.role_delete,
            discord.AuditLogAction.channel_create, discord.AuditLogAction.channel_delete,
            discord.AuditLogAction.bot_add, discord.AuditLogAction.webhook_create,
        }
        if entry.action not in monitored or not entry.guild:
            return
        actor_id = entry.user.id if entry.user else 0
        target = getattr(entry.target, "name", None) or getattr(entry.target, "id", "unknown")
        await self.bot.db.execute(
            "INSERT INTO security_incidents (guild_id, incident_type, actor_id, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (entry.guild.id, str(entry.action).split(".")[-1], actor_id, f"target: {target}", int(time.time())),
        )

    @commands.group(name="regex", invoke_without_command=True)
    @is_admin_or_owner()
    async def direct_regex_group(self, ctx):
        await self.filter_regex_list(ctx)

    @direct_regex_group.command(name="add")
    @is_admin_or_owner()
    async def direct_regex_add(self, ctx, name: str, pattern: str):
        await self.filter_regex_add(ctx, name, pattern)

    @direct_regex_group.command(name="remove", aliases=["del"])
    @is_admin_or_owner()
    async def direct_regex_remove(self, ctx, name: str):
        await self.filter_regex_remove(ctx, name)

    @direct_regex_group.command(name="list")
    @is_admin_or_owner()
    async def direct_regex_list(self, ctx):
        await self.filter_regex_list(ctx)

async def setup(bot):
    await bot.add_cog(Security(bot))
