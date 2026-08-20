import discord
from discord.ext import commands
from utils import fleed_embed, success_embed, error_embed, send_group_help, warn_embed, find_role

class Auto(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def find_role(self, guild: discord.Guild, query: str):
        return find_role(guild, query)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.guild or member.bot:
            return
        rows = await self.bot.db.fetch("SELECT role_id FROM autoroles WHERE guild_id = ?", (member.guild.id,))
        if not rows:
            return
        roles_to_add = []
        for r in rows:
            role = member.guild.get_role(r["role_id"])
            if role and role not in member.roles and role < member.guild.me.top_role:
                roles_to_add.append(role)
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="fleed autoroles")
            except Exception:
                pass

    # autorole
    @commands.hybrid_group(name="autorole", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx):
        await send_group_help(ctx, ctx.command, "auto")

    @autorole.command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def autorole_add(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"role `{role}` not found", ctx.author))
        await self.bot.db.execute("INSERT OR IGNORE INTO autoroles (guild_id, role_id) VALUES (?, ?)", (ctx.guild.id, target_role.id))
        await ctx.send(embed=success_embed(f"added autorole {target_role.mention}", ctx.author, role=target_role))

    @autorole.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def autorole_remove(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"role `{role}` not found", ctx.author))
        await self.bot.db.execute("DELETE FROM autoroles WHERE guild_id = ? AND role_id = ?", (ctx.guild.id, target_role.id))
        await ctx.send(embed=success_embed(f"removed autorole {target_role.mention}", ctx.author, role=target_role))

    @autorole.command(name="list")
    @commands.has_permissions(manage_roles=True)
    async def autorole_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT role_id FROM autoroles WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no autoroles configured", author=ctx.author))
        roles = [f"<@&{r['role_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="autoroles", description="\n".join(roles), author=ctx.author))

    @autorole.command(name="clear")
    @commands.has_permissions(manage_roles=True)
    async def autorole_clear(self, ctx):
        await self.bot.db.execute("DELETE FROM autoroles WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("cleared all autoroles", ctx.author))

    # badge
    @commands.hybrid_group(name="badge", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def badge(self, ctx):
        await send_group_help(ctx, ctx.command)

    @badge.group(name="role", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def badge_role(self, ctx):
        await send_group_help(ctx, ctx.command)

    @badge_role.command(name="add")
    async def badge_role_add(self, ctx, role: discord.Role):
        await self.bot.db.execute("INSERT OR IGNORE INTO badge_roles (guild_id, role_id) VALUES (?, ?)", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"added badge role {role.mention}", ctx.author, role=role))

    @badge_role.command(name="remove", aliases=["delete"])
    async def badge_role_remove(self, ctx, role: discord.Role):
        await self.bot.db.execute("DELETE FROM badge_roles WHERE guild_id = ? AND role_id = ?", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"removed badge role {role.mention}", ctx.author, role=role))

    @badge_role.command(name="list", aliases=["show"])
    async def badge_role_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT role_id FROM badge_roles WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no badge roles set", author=ctx.author))
        roles = [f"<@&{r['role_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="badge award roles", description="\n".join(roles), author=ctx.author))

    @badge.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def badge_enable(self, ctx, enabled: str):
        val = 1 if enabled.lower() in ["true", "yes", "on", "enable", "1"] else 0
        await self.bot.db.execute("INSERT INTO badge_config (guild_id, enabled) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET enabled = ?", (ctx.guild.id, val, val))
        await ctx.send(embed=success_embed(f"badge awards set to {enabled.lower()}", ctx.author))

    @badge.command(name="message")
    @commands.has_permissions(manage_guild=True)
    async def badge_message(self, ctx, *, message: str = None):
        await self.bot.db.execute("INSERT INTO badge_config (guild_id, message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET message = ?", (ctx.guild.id, message, message))
        await ctx.send(embed=success_embed("badge thank you message updated", ctx.author))

    @badge.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def badge_channel(self, ctx, channel: discord.TextChannel = None):
        ch_id = channel.id if channel else 0
        await self.bot.db.execute("INSERT INTO badge_config (guild_id, award_channel) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET award_channel = ?", (ctx.guild.id, ch_id, ch_id))
        await ctx.send(embed=success_embed("badge award channel updated", ctx.author))

    @badge.command(name="award")
    @commands.has_permissions(manage_guild=True)
    async def badge_award(self, ctx, sub: str = None, channel: discord.TextChannel = None):
        if sub == "channel":
            ch_id = channel.id if channel else 0
            await self.bot.db.execute("INSERT INTO badge_config (guild_id, award_channel) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET award_channel = ?", (ctx.guild.id, ch_id, ch_id))
            return await ctx.send(embed=success_embed("badge award channel set", ctx.author))
        await send_group_help(ctx, ctx.command, "auto")

    @badge.command(name="config")
    @commands.has_permissions(manage_guild=True)
    async def badge_config(self, ctx):
        row = await self.bot.db.fetchrow("SELECT * FROM badge_config WHERE guild_id = ?", (ctx.guild.id,))
        enabled = "enabled" if row and row["enabled"] else "disabled"
        ch = f"<#{row['award_channel']}>" if row and row["award_channel"] else "none"
        msg = row["message"] if row and row["message"] else "default"
        await ctx.send(embed=fleed_embed(title="badge config", description=f"status: {enabled}\nchannel: {ch}\nmessage: {msg}", author=ctx.author))

    @badge.group(name="view", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def badge_view(self, ctx):
        await send_group_help(ctx, ctx.command)

    @badge_view.command(name="message")
    async def badge_view_message(self, ctx):
        row = await self.bot.db.fetchrow("SELECT message FROM badge_config WHERE guild_id = ?", (ctx.guild.id,))
        msg = row["message"] if row and row["message"] else "no custom message set"
        await ctx.send(embed=fleed_embed(title="rendered badge message", description=msg, author=ctx.author))

    @badge_view.command(name="substring")
    async def badge_view_substring(self, ctx):
        row = await self.bot.db.fetchrow("SELECT message FROM badge_config WHERE guild_id = ?", (ctx.guild.id,))
        msg = row["message"] if row and row["message"] else "none"
        await ctx.send(embed=fleed_embed(title="raw badge message script", description=f"```\n{msg}\n```", author=ctx.author))

    # tracking
    @commands.group(name="tracking", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def tracking(self, ctx):
        await send_group_help(ctx, ctx.command)

    @tracking.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def tracking_add(self, ctx, channel: discord.TextChannel):
        await self.bot.db.execute("INSERT OR IGNORE INTO tracking_channels (guild_id, channel_id, track_type) VALUES (?, ?, 'all')", (ctx.guild.id, channel.id))
        await ctx.send(embed=success_embed(f"added tracking channel {channel.mention}", ctx.author))

    @tracking.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def tracking_remove(self, ctx, channel: discord.TextChannel = None):
        if channel:
            await self.bot.db.execute("DELETE FROM tracking_channels WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, channel.id))
            return await ctx.send(embed=success_embed(f"removed tracking channel {channel.mention}", ctx.author))
        await self.bot.db.execute("DELETE FROM tracking_channels WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("removed all tracking channels", ctx.author))

    @tracking.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def tracking_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT channel_id, track_type FROM tracking_channels WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no tracking channels configured", author=ctx.author))
        channels = [f"<#{r['channel_id']}> ({r['track_type']})" for r in rows]
        await ctx.send(embed=fleed_embed(title="tracking channels", description="\n".join(channels), author=ctx.author))

    @tracking.command(name="username")
    @commands.has_permissions(manage_guild=True)
    async def tracking_username(self, ctx, sub: str, channel: discord.TextChannel):
        if sub == "channel":
            await self.bot.db.execute("INSERT OR REPLACE INTO tracking_channels (guild_id, channel_id, track_type) VALUES (?, ?, 'username')", (ctx.guild.id, channel.id))
            return await ctx.send(embed=success_embed(f"set username changes tracking channel to {channel.mention}", ctx.author))
        await send_group_help(ctx, ctx.command, "auto")

    # vanity
    @commands.hybrid_group(name="vanity", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def vanity(self, ctx):
        await send_group_help(ctx, ctx.command)

    @vanity.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def vanity_set(self, ctx, vanity: str = None):
        await self.bot.db.execute("INSERT INTO vanity_config (guild_id, vanity) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET vanity = ?", (ctx.guild.id, vanity, vanity))
        await ctx.send(embed=success_embed(f"vanity to detect set to {vanity}", ctx.author))

    @vanity.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def vanity_channel(self, ctx, channel: discord.TextChannel = None):
        ch_id = channel.id if channel else 0
        await self.bot.db.execute("INSERT INTO vanity_config (guild_id, award_channel) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET award_channel = ?", (ctx.guild.id, ch_id, ch_id))
        await ctx.send(embed=success_embed("vanity award channel updated", ctx.author))

    @vanity.command(name="award")
    @commands.has_permissions(manage_guild=True)
    async def vanity_award(self, ctx, sub: str = None, channel: discord.TextChannel = None):
        if sub == "channel":
            ch_id = channel.id if channel else 0
            await self.bot.db.execute("INSERT INTO vanity_config (guild_id, award_channel) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET award_channel = ?", (ctx.guild.id, ch_id, ch_id))
            return await ctx.send(embed=success_embed("vanity award channel set", ctx.author))
        await send_group_help(ctx, ctx.command, "auto")

    @vanity.command(name="strict")
    @commands.has_permissions(manage_guild=True)
    async def vanity_strict(self, ctx, setting: str = None):
        val = 1 if setting and setting.lower() in ["true", "on", "1", "yes"] else 0
        await self.bot.db.execute("INSERT INTO vanity_config (guild_id, strict) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET strict = ?", (ctx.guild.id, val, val))
        await ctx.send(embed=success_embed(f"vanity strict mode set to {val == 1}", ctx.author))

    @vanity.command(name="message")
    @commands.has_permissions(manage_guild=True)
    async def vanity_message(self, ctx, *, message: str = None):
        await self.bot.db.execute("INSERT INTO vanity_config (guild_id, message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET message = ?", (ctx.guild.id, message, message))
        await ctx.send(embed=success_embed("vanity message updated", ctx.author))

    @vanity.command(name="config")
    @commands.has_permissions(manage_guild=True)
    async def vanity_config(self, ctx):
        row = await self.bot.db.fetchrow("SELECT * FROM vanity_config WHERE guild_id = ?", (ctx.guild.id,))
        vanity = row["vanity"] if row and row["vanity"] else "none"
        ch = f"<#{row['award_channel']}>" if row and row["award_channel"] else "none"
        strict = "enabled" if row and row["strict"] else "disabled"
        msg = row["message"] if row and row["message"] else "default"
        await ctx.send(embed=fleed_embed(title="vanity config", description=f"vanity: {vanity}\nchannel: {ch}\nstrict: {strict}\nmessage: {msg}", author=ctx.author))

    @vanity.group(name="role", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def vanity_role(self, ctx):
        await send_group_help(ctx, ctx.command)

    @vanity_role.command(name="add")
    async def vanity_role_add(self, ctx, role: discord.Role):
        await self.bot.db.execute("INSERT OR IGNORE INTO vanity_roles (guild_id, role_id) VALUES (?, ?)", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"added vanity role {role.name}", ctx.author))

    @vanity_role.command(name="remove", aliases=["delete"])
    async def vanity_role_remove(self, ctx, role: discord.Role):
        await self.bot.db.execute("DELETE FROM vanity_roles WHERE guild_id = ? AND role_id = ?", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"removed vanity role {role.name}", ctx.author))

    @vanity_role.command(name="list", aliases=["show"])
    async def vanity_role_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT role_id FROM vanity_roles WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no vanity award roles set", author=ctx.author))
        roles = [f"<@&{r['role_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="vanity roles", description="\n".join(roles), author=ctx.author))

    @vanity.group(name="view", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def vanity_view(self, ctx):
        await send_group_help(ctx, ctx.command)

    @vanity_view.command(name="message")
    async def vanity_view_message(self, ctx):
        row = await self.bot.db.fetchrow("SELECT message FROM vanity_config WHERE guild_id = ?", (ctx.guild.id,))
        msg = row["message"] if row and row["message"] else "none"
        await ctx.send(embed=fleed_embed(title="rendered vanity message", description=msg, author=ctx.author))

    @vanity_view.command(name="substring")
    async def vanity_view_substring(self, ctx):
        row = await self.bot.db.fetchrow("SELECT message FROM vanity_config WHERE guild_id = ?", (ctx.guild.id,))
        msg = row["message"] if row and row["message"] else "none"
        await ctx.send(embed=fleed_embed(title="raw vanity message script", description=f"```\n{msg}\n```", author=ctx.author))

    # pingonjoin
    @commands.group(name="pingonjoin", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin(self, ctx):
        await send_group_help(ctx, ctx.command)

    @pingonjoin.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_enable(self, ctx, channel: discord.TextChannel, threshold: int = 0):
        await self.bot.db.execute("INSERT INTO pingonjoin (guild_id, channel_id, threshold) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?, threshold = ?", (ctx.guild.id, channel.id, threshold, channel.id, threshold))
        await ctx.send(embed=success_embed(f"ping on join enabled in {channel.mention}", ctx.author))

    @pingonjoin.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_disable(self, ctx):
        await self.bot.db.execute("DELETE FROM pingonjoin WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("ping on join disabled", ctx.author))

    @pingonjoin.command(name="info")
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_info(self, ctx):
        row = await self.bot.db.fetchrow("SELECT * FROM pingonjoin WHERE guild_id = ?", (ctx.guild.id,))
        if not row:
            return await ctx.send(embed=fleed_embed(description="ping on join not configured", author=ctx.author))
        await ctx.send(embed=fleed_embed(title="ping on join config", description=f"channel: <#{row['channel_id']}>\nthreshold: {row['threshold']}\nmessage: {row['message'] or 'default'}", author=ctx.author))

    @pingonjoin.command(name="message", aliases=["msg"])
    @commands.has_permissions(manage_guild=True)
    async def pingonjoin_message(self, ctx, *, message: str):
        await self.bot.db.execute("INSERT INTO pingonjoin (guild_id, message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET message = ?", (ctx.guild.id, message, message))
        await ctx.send(embed=success_embed("ping on join message template updated", ctx.author))

    # autoreact
    @commands.group(name="autoreact", invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def autoreact(self, ctx):
        await send_group_help(ctx, ctx.command)

    @autoreact.command(name="add")
    @commands.has_permissions(manage_messages=True)
    async def autoreact_add(self, ctx, keyword: str, reaction: str):
        await self.bot.db.execute("INSERT OR REPLACE INTO autoreactions (guild_id, keyword, reaction) VALUES (?, ?, ?)", (ctx.guild.id, keyword.lower(), reaction))
        await ctx.send(embed=success_embed(f"added autoreact `{keyword.lower()}` -> `{reaction}`", ctx.author))

    @autoreact.command(name="remove")
    @commands.has_permissions(manage_messages=True)
    async def autoreact_remove(self, ctx, keyword: str):
        await self.bot.db.execute("DELETE FROM autoreactions WHERE guild_id = ? AND keyword = ?", (ctx.guild.id, keyword.lower()))
        await ctx.send(embed=success_embed(f"removed autoreact for `{keyword.lower()}`", ctx.author))

    @autoreact.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def autoreact_clear(self, ctx):
        await self.bot.db.execute("DELETE FROM autoreactions WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("cleared all autoreactions", ctx.author))

    @autoreact.command(name="list")
    @commands.has_permissions(manage_messages=True)
    async def autoreact_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT keyword, reaction FROM autoreactions WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no autoreactions configured", author=ctx.author))
        lines = [f"`{r['keyword']}` -> {r['reaction']}" for r in rows]
        await ctx.send(embed=fleed_embed(title="autoreactions", description="\n".join(lines), author=ctx.author))

    # autoresponder
    @commands.hybrid_group(name="autoresponder", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def autoresponder(self, ctx):
        await send_group_help(ctx, ctx.command)

    @autoresponder.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_add(self, ctx, *, content: str):
        parts = content.split(",", 1)
        if len(parts) < 2:
            return await ctx.send(embed=error_embed("format: autoresponder add <trigger>, <response>", ctx.author))
        trigger, response = parts[0].strip().lower(), parts[1].strip()
        await self.bot.db.execute("INSERT OR REPLACE INTO autoresponders (guild_id, trigger, response) VALUES (?, ?, ?)", (ctx.guild.id, trigger, response))
        await ctx.send(embed=success_embed(f"created autoresponder for `{trigger}`", ctx.author))

    @autoresponder.command(name="update")
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_update(self, ctx, *, args: str):
        parts = args.split(",", 1)
        if len(parts) < 2:
            return await ctx.send(embed=error_embed("format: autoresponder update <trigger>, <new_response>", ctx.author))
        trigger, response = parts[0].strip().lower(), parts[1].strip()
        await self.bot.db.execute("UPDATE autoresponders SET response = ? WHERE guild_id = ? AND trigger = ?", (response, ctx.guild.id, trigger))
        await ctx.send(embed=success_embed(f"updated reply for `{trigger}`", ctx.author))

    @autoresponder.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_remove(self, ctx, *, trigger: str):
        await self.bot.db.execute("DELETE FROM autoresponders WHERE guild_id = ? AND trigger = ?", (ctx.guild.id, trigger.lower()))
        await ctx.send(embed=success_embed(f"removed autoresponder for `{trigger.lower()}`", ctx.author))

    @autoresponder.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_clear(self, ctx):
        await self.bot.db.execute("DELETE FROM autoresponders WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("cleared all autoresponders", ctx.author))

    @autoresponder.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_reset(self, ctx):
        await self.autoresponder_clear(ctx)

    @autoresponder.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT trigger, response FROM autoresponders WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no autoresponders configured", author=ctx.author))
        lines = [f"`{r['trigger']}` -> {r['response'][:50]}" for r in rows]
        await ctx.send(embed=fleed_embed(title="autoresponders", description="\n".join(lines), author=ctx.author))

    @autoresponder.group(name="role", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def autoresponder_role(self, ctx):
        await send_group_help(ctx, ctx.command)

    @autoresponder_role.command(name="add")
    async def autoresponder_role_add(self, ctx, trigger: str, role: discord.Role):
        await self.bot.db.execute("INSERT OR REPLACE INTO autoresponder_roles (guild_id, trigger, role_id, action_type) VALUES (?, ?, ?, 'add')", (ctx.guild.id, trigger.lower(), role.id))
        await ctx.send(embed=success_embed(f"added role {role.mention} to trigger `{trigger.lower()}`", ctx.author, role=role))

    @autoresponder_role.command(name="remove")
    async def autoresponder_role_remove(self, ctx, trigger: str, role: discord.Role):
        await self.bot.db.execute("DELETE FROM autoresponder_roles WHERE guild_id = ? AND trigger = ? AND role_id = ?", (ctx.guild.id, trigger.lower(), role.id))
        await ctx.send(embed=success_embed(f"removed role {role.mention} from trigger `{trigger.lower()}`", ctx.author, role=role))

async def setup(bot):
    await bot.add_cog(Auto(bot))
