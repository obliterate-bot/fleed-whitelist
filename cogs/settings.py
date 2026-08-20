import discord
from discord.ext import commands
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="settings", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def settings(self, ctx):
        await send_group_help(ctx, self.settings, "settings")

    @settings.command(name="vcrole")
    @commands.has_permissions(administrator=True)
    async def settings_vcrole(self, ctx, role: discord.Role = None):
        r_id = role.id if role else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, vcrole_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET vcrole_id = ?", (ctx.guild.id, r_id, r_id))
        await ctx.send(embed=success_embed(f"voice channel role set to {role.name if role else 'none'}", ctx.author, role=role))

    @settings.command(name="embed")
    @commands.has_permissions(administrator=True)
    async def settings_embed(self, ctx, color: str = None):
        col = int(color.replace("#", ""), 16) if color else 0x2B2D31
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, embed_color) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET embed_color = ?", (ctx.guild.id, col, col))
        await ctx.send(embed=success_embed(f"default embed color updated to `{color or '#2b2d31'}`", ctx.author, color=col))

    @settings.command(name="rmuted")
    @commands.has_permissions(administrator=True)
    async def settings_rmuted(self, ctx, role: discord.Role = None):
        r_id = role.id if role else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, rmuted_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET rmuted_id = ?", (ctx.guild.id, r_id, r_id))
        await ctx.send(embed=success_embed(f"reaction mute role set to {role.name if role else 'none'}", ctx.author, role=role))

    @settings.command(name="imuted")
    @commands.has_permissions(administrator=True)
    async def settings_imuted(self, ctx, role: discord.Role = None):
        r_id = role.id if role else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, imuted_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET imuted_id = ?", (ctx.guild.id, r_id, r_id))
        await ctx.send(embed=success_embed(f"image mute role set to {role.name if role else 'none'}", ctx.author, role=role))

    @settings.command(name="jail")
    @commands.has_permissions(administrator=True)
    async def settings_jail(self, ctx, channel: discord.TextChannel = None):
        ch_id = channel.id if channel else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, jail_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET jail_id = ?", (ctx.guild.id, ch_id, ch_id))
        await ctx.send(embed=success_embed(f"jail channel set to {channel.mention if channel else 'none'}", ctx.author))

    @settings.command(name="dj")
    @commands.has_permissions(administrator=True)
    async def settings_dj(self, ctx, role: discord.Role = None):
        r_id = role.id if role else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, dj_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET dj_id = ?", (ctx.guild.id, r_id, r_id))
        await ctx.send(embed=success_embed(f"dj role set to {role.name if role else 'none'}", ctx.author, role=role))

    @settings.command(name="modlog")
    @commands.has_permissions(administrator=True)
    async def settings_modlog(self, ctx, channel: discord.TextChannel = None):
        ch_id = channel.id if channel else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, modlog_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET modlog_id = ?", (ctx.guild.id, ch_id, ch_id))
        await ctx.send(embed=success_embed(f"modlog channel set to {channel.mention if channel else 'none'}", ctx.author))

    @settings.command(name="baserole")
    @commands.has_permissions(administrator=True)
    async def settings_baserole(self, ctx, role: discord.Role = None):
        r_id = role.id if role else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, base_role_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET base_role_id = ?", (ctx.guild.id, r_id, r_id))
        await ctx.send(embed=success_embed(f"base role set to {role.name if role else 'none'}", ctx.author))

    @settings.command(name="tags")
    @commands.has_permissions(administrator=True)
    async def settings_tags(self, ctx, state: str = "on"):
        val = 1 if state.lower() in ["on", "true", "enable", "1"] else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, tags_enabled) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET tags_enabled = ?", (ctx.guild.id, val, val))
        await ctx.send(embed=success_embed(f"tags system set to {val == 1}", ctx.author))

    @settings.command(name="autoplay")
    @commands.has_permissions(administrator=True)
    async def settings_autoplay(self, ctx, state: str = "on"):
        val = 1 if state.lower() in ["on", "true", "enable", "1"] else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, autoplay) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET autoplay = ?", (ctx.guild.id, val, val))
        await ctx.send(embed=success_embed(f"music autoplay set to {val == 1}", ctx.author))

    @settings.command(name="247", aliases=["twentyfourseven", "24-7"])
    @commands.has_permissions(administrator=True)
    async def settings_247(self, ctx, destination: discord.VoiceChannel = None):
        enabled = 1
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, twentyfour_seven) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET twentyfour_seven = ?",
            (ctx.guild.id, enabled, enabled),
        )
        await ctx.send(embed=success_embed(f"24/7 mode set for {destination.name if destination else 'current voice'}", ctx.author))

    @settings.command(name="disablecustomfms")
    @commands.has_permissions(administrator=True)
    async def settings_disablecustomfms(self, ctx):
        row = await self.bot.db.fetchrow("SELECT disable_custom_fms FROM guild_settings WHERE guild_id = ?", (ctx.guild.id,))
        value = 0 if row and row["disable_custom_fms"] else 1
        await self.bot.db.execute(
            "INSERT INTO guild_settings (guild_id, disable_custom_fms) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET disable_custom_fms = ?",
            (ctx.guild.id, value, value),
        )
        await ctx.send(embed=success_embed(f"custom fm commands {'disabled' if value else 'enabled'}", ctx.author))

    @settings.command(name="resetcases")
    @commands.has_permissions(administrator=True)
    async def settings_resetcases(self, ctx):
        await self.bot.db.execute("DELETE FROM modhistory WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset all moderation cases for this server", ctx.author))

    # quote settings
    @settings.group(name="quote", aliases=["quotes"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def settings_quote(self, ctx):
        await send_group_help(ctx, ctx.command)

    @settings_quote.command(name="on", aliases=["enable"])
    async def settings_quote_on(self, ctx):
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, quote_enabled) VALUES (?, 1) ON CONFLICT(guild_id) DO UPDATE SET quote_enabled = 1", (ctx.guild.id,))
        await ctx.send(embed=success_embed("quote system enabled", ctx.author))

    @settings_quote.command(name="off", aliases=["disable"])
    async def settings_quote_off(self, ctx):
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, quote_enabled) VALUES (?, 0) ON CONFLICT(guild_id) DO UPDATE SET quote_enabled = 0", (ctx.guild.id,))
        await ctx.send(embed=success_embed("quote system disabled", ctx.author))

    @settings_quote.command(name="redirect")
    async def settings_quote_redirect(self, ctx, channel: discord.TextChannel = None):
        if not channel:
            await self.bot.db.execute("UPDATE guild_settings SET quote_redirect_channel = NULL WHERE guild_id = ?", (ctx.guild.id,))
            return await ctx.send(embed=success_embed("disabled quote redirection", ctx.author))
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, quote_redirect_channel) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET quote_redirect_channel = ?", (ctx.guild.id, channel.id, channel.id))
        await ctx.send(embed=success_embed(f"quote redirect channel set to {channel.mention}", ctx.author))

    # awards
    @settings.group(name="award", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def settings_award(self, ctx):
        await send_group_help(ctx, ctx.command)

    @settings_award.command(name="add")
    async def settings_award_add(self, ctx, role: discord.Role):
        await self.bot.db.execute("INSERT OR IGNORE INTO award_roles (guild_id, role_id) VALUES (?, ?)", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"added {role.name} to award roles", ctx.author, role=role))

    @settings_award.command(name="remove")
    async def settings_award_remove(self, ctx, role: discord.Role):
        await self.bot.db.execute("DELETE FROM award_roles WHERE guild_id = ? AND role_id = ?", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"removed {role.name} from award roles", ctx.author, role=role))

    @settings_award.command(name="list")
    async def settings_award_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT role_id FROM award_roles WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(title="award roles", description="\n".join(f"<@&{r['role_id']}>" for r in rows) or "none configured", author=ctx.author))

    # warn punishment
    @settings.group(name="warn", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def settings_warn(self, ctx):
        await send_group_help(ctx, ctx.command)

    @settings_warn.command(name="punishmentadd")
    async def settings_warn_punishment_add(self, ctx, threshold: int = 3, punishment_type: str = "timeout", duration: int = 60):
        await self.bot.db.execute("INSERT OR REPLACE INTO warn_punishments (guild_id, threshold, punishment_type, duration) VALUES (?, ?, ?, ?)", (ctx.guild.id, threshold, punishment_type.lower(), duration))
        await ctx.send(embed=success_embed(f"set punishment for {threshold} warns to `{punishment_type.lower()}`", ctx.author))

    @settings_warn.command(name="punishmentremove")
    async def settings_warn_punishment_remove(self, ctx, threshold: int):
        await self.bot.db.execute("DELETE FROM warn_punishments WHERE guild_id = ? AND threshold = ?", (ctx.guild.id, threshold))
        await ctx.send(embed=success_embed(f"removed punishment for {threshold} warns", ctx.author))

    @settings_warn.command(name="punishmentlist")
    async def settings_warn_punishment_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT threshold, punishment_type, duration FROM warn_punishments WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"{r['threshold']} warns -> `{r['punishment_type']}` ({r['duration']}s)" for r in rows]
        await ctx.send(embed=fleed_embed(title="warn punishment ladder", description="\n".join(lines) or "none configured", author=ctx.author))

    # staff
    @settings.group(name="staff", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def settings_staff(self, ctx):
        await send_group_help(ctx, ctx.command)

    @settings_staff.command(name="add")
    async def settings_staff_add(self, ctx, role: discord.Role):
        await self.bot.db.execute("INSERT OR IGNORE INTO staff_roles (guild_id, role_id) VALUES (?, ?)", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"added {role.name} to staff roles", ctx.author, role=role))

    @settings_staff.command(name="remove")
    async def settings_staff_remove(self, ctx, role: discord.Role):
        await self.bot.db.execute("DELETE FROM staff_roles WHERE guild_id = ? AND role_id = ?", (ctx.guild.id, role.id))
        await ctx.send(embed=success_embed(f"removed {role.name} from staff roles", ctx.author, role=role))

    @settings_staff.command(name="list")
    async def settings_staff_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT role_id FROM staff_roles WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(title="staff roles", description="\n".join(f"<@&{r['role_id']}>" for r in rows) or "none", author=ctx.author))

    # restrictions
    @settings.group(name="restrict", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def settings_restrict(self, ctx):
        await send_group_help(ctx, ctx.command)

    @settings_restrict.command(name="allow")
    async def settings_restrict_allow(self, ctx, command: str = None, role: discord.Role = None):
        if not command or not role:
            return await send_group_help(ctx, ctx.command.parent, "settings")
        await self.bot.db.execute("INSERT OR REPLACE INTO command_restrictions (guild_id, command_name, role_id, action_type) VALUES (?, ?, ?, 'allow')", (ctx.guild.id, command.lower(), role.id))
        await ctx.send(embed=success_embed(f"allowed `{command.lower()}` for {role.name}", ctx.author, role=role))

    @settings_restrict.command(name="deny")
    async def settings_restrict_deny(self, ctx, command: str = None, role: discord.Role = None):
        if not command or not role:
            return await send_group_help(ctx, ctx.command.parent, "settings")
        await self.bot.db.execute("INSERT OR REPLACE INTO command_restrictions (guild_id, command_name, role_id, action_type) VALUES (?, ?, ?, 'deny')", (ctx.guild.id, command.lower(), role.id))
        await ctx.send(embed=success_embed(f"denied `{command.lower()}` for {role.name}", ctx.author, role=role))

    @settings_restrict.command(name="remove")
    async def settings_restrict_remove(self, ctx, command: str = None, role: discord.Role = None):
        if not command or not role:
            return await send_group_help(ctx, ctx.command.parent, "settings")
        await self.bot.db.execute("DELETE FROM command_restrictions WHERE guild_id = ? AND command_name = ? AND role_id = ?", (ctx.guild.id, command.lower(), role.id))
        await ctx.send(embed=success_embed(f"removed restriction on `{command.lower()}` for {role.name}", ctx.author, role=role))

    @settings_restrict.command(name="reset")
    async def settings_restrict_reset(self, ctx, command: str = None):
        if command:
            await self.bot.db.execute("DELETE FROM command_restrictions WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, command.lower()))
        else:
            await self.bot.db.execute("DELETE FROM command_restrictions WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset command restrictions", ctx.author))

    @settings_restrict.command(name="list")
    async def settings_restrict_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT command_name, role_id, action_type FROM command_restrictions WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"`{r['command_name']}` → <@&{r['role_id']}> ({r['action_type']})" for r in rows]
        await ctx.send(embed=fleed_embed(title="command restrictions", description="\n".join(lines) or "none", author=ctx.author))

    # standalone restrict command
    @commands.hybrid_group(name="restrict", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def standalone_restrict(self, ctx):
        await send_group_help(ctx, ctx.command)

    @standalone_restrict.command(name="allow")
    async def standalone_restrict_allow(self, ctx, command: str, role: discord.Role):
        await self.bot.db.execute("INSERT OR REPLACE INTO command_restrictions (guild_id, command_name, role_id, action_type) VALUES (?, ?, ?, 'allow')", (ctx.guild.id, command.lower(), role.id))
        await ctx.send(embed=success_embed(f"allowed `{command.lower()}` for {role.name}", ctx.author))

    @standalone_restrict.command(name="deny")
    async def standalone_restrict_deny(self, ctx, command: str, role: discord.Role):
        await self.bot.db.execute("INSERT OR REPLACE INTO command_restrictions (guild_id, command_name, role_id, action_type) VALUES (?, ?, ?, 'deny')", (ctx.guild.id, command.lower(), role.id))
        await ctx.send(embed=success_embed(f"denied `{command.lower()}` for {role.name}", ctx.author))

    @standalone_restrict.command(name="remove", aliases=["delete", "del"])
    async def standalone_restrict_remove(self, ctx, command: str, role: discord.Role):
        await self.bot.db.execute("DELETE FROM command_restrictions WHERE guild_id = ? AND command_name = ? AND role_id = ?", (ctx.guild.id, command.lower(), role.id))
        await ctx.send(embed=success_embed(f"removed restriction on `{command.lower()}` for {role.name}", ctx.author))

    @standalone_restrict.command(name="reset", aliases=["clear"])
    async def standalone_restrict_reset(self, ctx, command: str = None):
        if command:
            await self.bot.db.execute("DELETE FROM command_restrictions WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, command.lower()))
            return await ctx.send(embed=success_embed(f"reset restrictions for `{command.lower()}`", ctx.author))
        await self.bot.db.execute("DELETE FROM command_restrictions WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset all command restrictions", ctx.author))

    @standalone_restrict.command(name="list", aliases=["ls", "show"])
    async def standalone_restrict_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT command_name, role_id, action_type FROM command_restrictions WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"`{r['command_name']}` -> <@&{r['role_id']}> ({r['action_type']})" for r in rows]
        await ctx.send(embed=fleed_embed(title="command restrictions", description="\n".join(lines) or "none", author=ctx.author))

    # disable / enable commands
    @commands.hybrid_group(name="disable", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def disable_group(self, ctx):
        await send_group_help(ctx, ctx.command)

    @disable_group.command(name="command")
    async def disable_command(self, ctx, name: str = None):
        if not name:
            return await ctx.send(embed=error_embed("provide command name", ctx.author))
        await self.bot.db.execute("INSERT OR IGNORE INTO disabled_commands (guild_id, command_name, target_id, target_type) VALUES (?, ?, 0, 'guild')", (ctx.guild.id, name.lower()))
        await ctx.send(embed=success_embed(f"disabled command `{name.lower()}` server-wide", ctx.author))

    @disable_group.command(name="channel")
    async def disable_channel(self, ctx, command: str, channel: discord.TextChannel):
        await self.bot.db.execute("INSERT OR IGNORE INTO disabled_commands (guild_id, command_name, target_id, target_type) VALUES (?, ?, ?, 'channel')", (ctx.guild.id, command.lower(), channel.id))
        await ctx.send(embed=success_embed(f"disabled command `{command.lower()}` in {channel.mention}", ctx.author))

    @disable_group.command(name="role")
    async def disable_role(self, ctx, command: str, role: discord.Role):
        await self.bot.db.execute("INSERT OR IGNORE INTO disabled_commands (guild_id, command_name, target_id, target_type) VALUES (?, ?, ?, 'role')", (ctx.guild.id, command.lower(), role.id))
        await ctx.send(embed=success_embed(f"disabled command `{command.lower()}` for {role.name}", ctx.author))

    @disable_group.command(name="reset")
    async def disable_reset(self, ctx, name: str = None):
        if name:
            await self.bot.db.execute("DELETE FROM disabled_commands WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, name.lower()))
            return await ctx.send(embed=success_embed(f"reset disabled state for `{name.lower()}`", ctx.author))
        await self.bot.db.execute("DELETE FROM disabled_commands WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset all disabled commands", ctx.author))

    @disable_group.command(name="list")
    async def disable_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT command_name, target_id, target_type FROM disabled_commands WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"`{r['command_name']}` ({r['target_type']}: {r['target_id']})" for r in rows]
        await ctx.send(embed=fleed_embed(title="disabled commands", description="\n".join(lines) or "none", author=ctx.author))

    @disable_group.group(name="whitelist", invoke_without_command=True)
    async def disable_whitelist(self, ctx):
        await send_group_help(ctx, ctx.command)

    @disable_whitelist.command(name="add")
    async def disable_whitelist_add(self, ctx, command: str, user_id: int):
        await self.bot.db.execute("INSERT OR IGNORE INTO disabled_command_whitelist (guild_id, command_name, user_id) VALUES (?, ?, ?)", (ctx.guild.id, command.lower(), user_id))
        await ctx.send(embed=success_embed(f"whitelisted user `{user_id}` for `{command.lower()}`", ctx.author))

    @disable_whitelist.command(name="remove")
    async def disable_whitelist_remove(self, ctx, command: str, user_id: int):
        await self.bot.db.execute("DELETE FROM disabled_command_whitelist WHERE guild_id = ? AND command_name = ? AND user_id = ?", (ctx.guild.id, command.lower(), user_id))
        await ctx.send(embed=success_embed(f"removed whitelist for `{user_id}` on `{command.lower()}`", ctx.author))

    @disable_whitelist.command(name="list")
    async def disable_whitelist_list(self, ctx, command: str = None):
        if command:
            rows = await self.bot.db.fetch("SELECT command_name, user_id FROM disabled_command_whitelist WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, command.lower()))
        else:
            rows = await self.bot.db.fetch("SELECT command_name, user_id FROM disabled_command_whitelist WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"`{r['command_name']}` → <@{r['user_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="disabled command whitelist", description="\n".join(lines) or "none", author=ctx.author))

    @commands.hybrid_command(name="enable")
    @commands.has_permissions(administrator=True)
    async def enable_command(self, ctx, command: str, target: str = None):
        await self.bot.db.execute("DELETE FROM disabled_commands WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, command.lower()))
        await ctx.send(embed=success_embed(f"re-enabled command `{command.lower()}`", ctx.author))

    @commands.hybrid_command(name="language", aliases=["lang"])
    async def language_cmd(self, ctx):
        await ctx.send(embed=fleed_embed(title="bot language", description="current language: english (en-us)", author=ctx.author))

    @commands.hybrid_command(name="snipeprotect", aliases=["snipe_protect"])
    @commands.has_permissions(administrator=True)
    async def snipeprotect(self, ctx, toggle: str = "on"):
        val = 1 if toggle.lower() in ["on", "true", "enable", "1"] else 0
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, snipe_protect) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET snipe_protect = ?", (ctx.guild.id, val, val))
        await ctx.send(embed=success_embed(f"snipe protection set to {val == 1}", ctx.author))

    def find_channel(self, guild: discord.Guild, query: str):
        if not query or not guild:
            return None
        clean_id = "".join(filter(str.isdigit, str(query)))
        if clean_id:
            ch = guild.get_channel(int(clean_id))
            if ch:
                return ch
        q_low = str(query).lower().strip().lstrip("#")
        for ch in guild.text_channels:
            if ch.name.lower() == q_low:
                return ch
        for ch in guild.text_channels:
            if ch.name.lower().startswith(q_low):
                return ch
        for ch in guild.text_channels:
            if q_low in ch.name.lower():
                return ch
        return None

    # commands channel management
    @commands.group(name="commands", aliases=["cmdschannel", "botchannels", "commandchannels"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def commands_group(self, ctx):
        await send_group_help(ctx, ctx.command, "settings")

    @commands_group.group(name="channel", aliases=["channels"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def commands_channel(self, ctx, *, channel: str = None):
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS command_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
        if channel is None:
            rows = await self.bot.db.fetch("SELECT channel_id FROM command_channels WHERE guild_id = ?", (ctx.guild.id,))
            if not rows:
                return await ctx.send(embed=warn_embed("no command channels set (commands can be used anywhere)", ctx.author))
            ch_list = [f"<#{r['channel_id']}>" for r in rows]
            return await ctx.send(embed=fleed_embed(title="allowed command channels", description="\n".join(ch_list), author=ctx.author))

        target = self.find_channel(ctx.guild, channel)
        if not target:
            return await ctx.send(embed=error_embed(f"could not find channel `{channel}`", ctx.author))

        await self.bot.db.execute("DELETE FROM command_channels WHERE guild_id = ?", (ctx.guild.id,))
        await self.bot.db.execute("INSERT INTO command_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"commands can now only be used in {target.mention}", ctx.author))

    @commands_channel.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def commands_channel_set(self, ctx, *, channel: str):
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS command_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
        target = self.find_channel(ctx.guild, channel)
        if not target:
            return await ctx.send(embed=error_embed(f"could not find channel `{channel}`", ctx.author))

        await self.bot.db.execute("DELETE FROM command_channels WHERE guild_id = ?", (ctx.guild.id,))
        await self.bot.db.execute("INSERT INTO command_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"commands can now only be used in {target.mention}", ctx.author))

    @commands_channel.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def commands_channel_add(self, ctx, *, channel: str):
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS command_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
        target = self.find_channel(ctx.guild, channel)
        if not target:
            return await ctx.send(embed=error_embed(f"could not find channel `{channel}`", ctx.author))

        await self.bot.db.execute("INSERT OR IGNORE INTO command_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"added {target.mention} to allowed command channels", ctx.author))

    @commands_channel.command(name="remove", aliases=["del", "rm"])
    @commands.has_permissions(manage_guild=True)
    async def commands_channel_remove(self, ctx, *, channel: str):
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS command_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
        target = self.find_channel(ctx.guild, channel)
        if not target:
            return await ctx.send(embed=error_embed(f"could not find channel `{channel}`", ctx.author))

        await self.bot.db.execute("DELETE FROM command_channels WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"removed {target.mention} from allowed command channels", ctx.author))

    @commands_channel.command(name="clear", aliases=["reset", "off", "disable"])
    @commands.has_permissions(manage_guild=True)
    async def commands_channel_clear(self, ctx):
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS command_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
        await self.bot.db.execute("DELETE FROM command_channels WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("cleared command channels — commands can now be used in any channel", ctx.author))

    @commands_channel.command(name="list", aliases=["show"])
    @commands.has_permissions(manage_guild=True)
    async def commands_channel_list(self, ctx):
        await self.bot.db.execute("CREATE TABLE IF NOT EXISTS command_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
        rows = await self.bot.db.fetch("SELECT channel_id FROM command_channels WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed("no command channels set (commands can be used anywhere)", ctx.author))
        ch_list = [f"<#{r['channel_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="allowed command channels", description="\n".join(ch_list), author=ctx.author))

    # top-level shortcuts
    @commands.command(name="commandchannel", aliases=["cmdchannel", "botchannel", "commandschannel"])
    @commands.has_permissions(manage_guild=True)
    async def commandchannel_direct(self, ctx, *, channel: str = None):
        await self.commands_channel(ctx, channel=channel)

async def setup(bot):
    await bot.add_cog(Settings(bot))
