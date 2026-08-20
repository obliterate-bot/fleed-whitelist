import discord
from discord.ext import commands, tasks
import asyncio
import time
import re
import json
import random
import datetime
import aiohttp
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help, send_modlog, find_role, send_paginated_embed
import config

def _is_owner_exempt(ctx):
    if not ctx or not ctx.author:
        return False
    if ctx.author.id == getattr(ctx.guild, "owner_id", None):
        return True
    if ctx.author.id == 539594512981295106 or ctx.author.id in getattr(config, "OWNER_IDS", []):
        return True
    bot_owners = getattr(ctx.bot, "owner_ids", set()) or set()
    return ctx.author.id in bot_owners or str(ctx.author.id) in bot_owners

def parse_duration(time_str: str):
    if not time_str:
        return None
    time_str = time_str.strip().lower()
    units = {
        's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
        'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
        'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
        'd': 86400, 'day': 86400, 'days': 86400,
        'w': 604800, 'week': 604800, 'weeks': 604800,
        'mo': 2592000, 'month': 2592000, 'months': 2592000
    }
    matches = re.findall(r'(\d+)\s*([a-zA-Z]+)', time_str)
    if not matches:
        if time_str.isdigit():
            return int(time_str) * 60
        return None
    total_seconds = 0
    for val, unit in matches:
        if unit in units:
            total_seconds += int(val) * units[unit]
        else:
            return None
    return total_seconds

def format_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "expired"
    parts = []
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


class MassRoleConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("this confirmation is not for you", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="confirm", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mass_role_cancellations = {}
        self.check_jail_expirations.start()

    def cog_unload(self):
        self.check_jail_expirations.cancel()

    async def confirm_mass_role(self, ctx, prompt: str) -> bool:
        view = MassRoleConfirmView(ctx.author.id)
        message = await ctx.send(embed=warn_embed(prompt, ctx.author), view=view)
        await view.wait()
        if view.value is not True:
            try:
                await message.edit(embed=warn_embed("mass role operation cancelled", ctx.author), view=None)
            except Exception:
                pass
            return False
        return True

    async def run_mass_role_update(self, ctx, target_role: discord.Role, members: list, add: bool, target_label: str):
        if target_role.is_default() or target_role.managed:
            return await ctx.send(embed=error_embed("that role cannot be managed manually", ctx.author))
        if target_role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to my highest role", ctx.author))
        if target_role >= ctx.author.top_role and not _is_owner_exempt(ctx):
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to your highest role", ctx.author))

        candidates = [
            member for member in members
            if (target_role not in member.roles if add else target_role in member.roles)
        ]
        action_word = "add" if add else "remove"
        direction = "to" if add else "from"
        if not candidates:
            return await ctx.send(embed=warn_embed(f"no members need {target_role.mention} {action_word}ed", ctx.author))
        if not await self.confirm_mass_role(
            ctx,
            f"{action_word} {target_role.mention} {direction} **{len(candidates)}** {target_label}?",
        ):
            return

        cancel_event = asyncio.Event()
        old_event = self.mass_role_cancellations.get(ctx.guild.id)
        if old_event:
            old_event.set()
        self.mass_role_cancellations[ctx.guild.id] = cancel_event

        progress = await ctx.send(
            embed=fleed_embed(
                title="mass role operation",
                description=f"starting: **0/{len(candidates)}** members updated",
                author=ctx.author,
            )
        )
        changed = 0
        failed = 0
        cancelled = False
        try:
            for index, member in enumerate(candidates, start=1):
                if cancel_event.is_set():
                    cancelled = True
                    break
                try:
                    if add:
                        await member.add_roles(target_role, reason=f"mass role add by {ctx.author} ({ctx.author.id})")
                    else:
                        await member.remove_roles(target_role, reason=f"mass role remove by {ctx.author} ({ctx.author.id})")
                    changed += 1
                except (discord.Forbidden, discord.HTTPException):
                    failed += 1
                if index % 25 == 0 and index < len(candidates):
                    try:
                        await progress.edit(
                            embed=fleed_embed(
                                title="mass role operation",
                                description=f"working: **{index}/{len(candidates)}** checked, **{changed}** updated, **{failed}** failed",
                                author=ctx.author,
                            )
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(0.25)
        finally:
            if self.mass_role_cancellations.get(ctx.guild.id) is cancel_event:
                self.mass_role_cancellations.pop(ctx.guild.id, None)

        status = "cancelled" if cancelled else "completed"
        await progress.edit(
            embed=success_embed(
                f"mass role operation {status}: **{changed}** updated, **{failed}** failed, **{len(candidates) - changed - failed}** skipped",
                ctx.author,
                role=target_role,
            )
        )

    @tasks.loop(seconds=5)
    async def check_jail_expirations(self):
        try:
            now = int(time.time())
            rows = await self.bot.db.fetch("SELECT guild_id, user_id, roles, reason FROM jailed_users WHERE expires_at > 0 AND expires_at <= ?", (now,))
            for row in rows:
                guild = self.bot.get_guild(row["guild_id"])
                if not guild:
                    continue
                member = guild.get_member(row["user_id"])
                if member:
                    jail_role = discord.utils.get(guild.roles, name="jailed")
                    if jail_role and jail_role in member.roles:
                        try:
                            await member.remove_roles(jail_role, reason="jail sentence expired")
                        except Exception:
                            pass
                    
                    # Restore previous roles
                    saved_roles = json.loads(row["roles"]) if row["roles"] else []
                    roles_to_add = [guild.get_role(rid) for rid in saved_roles if guild.get_role(rid) and guild.get_role(rid) < guild.me.top_role]
                    if roles_to_add:
                        try:
                            await member.add_roles(*roles_to_add, reason="jail sentence expired")
                        except Exception:
                            pass

                await self.bot.db.execute("DELETE FROM jailed_users WHERE guild_id = ? AND user_id = ?", (row["guild_id"], row["user_id"]))
                await send_modlog(self.bot, guild, "unjail", self.bot.user, member or row["user_id"], "jail sentence expired")
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        row = await self.bot.db.fetchrow("SELECT roles FROM jailed_users WHERE guild_id = ? AND user_id = ?", (member.guild.id, member.id))
        if row:
            jail_role = await self.get_or_create_jail_role(member.guild)
            if jail_role:
                try:
                    await member.add_roles(jail_role, reason="anti-jail evasion: re-applying jail role")
                except Exception:
                    pass


    # punishments & kicks & bans
    @commands.hybrid_command(name="kick", aliases=["boot", "k"])
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        try:
            await member.kick(reason=reason)
            await send_modlog(self.bot, ctx.guild, "kick", ctx.author, member, reason)
            await ctx.send(embed=success_embed(f"kicked {member.display_name.lower()} — {reason.lower()}", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to kick: {e}", ctx.author))

    @commands.hybrid_command(name="ban", aliases=["deport", "b"])
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user: discord.User, *, reason: str = "No reason provided"):
        try:
            await ctx.guild.ban(user, reason=reason)
            await send_modlog(self.bot, ctx.guild, "ban", ctx.author, user, reason)
            await ctx.send(embed=success_embed(f"banned {user.display_name.lower()} — {reason.lower()}", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to ban: {e}", ctx.author))

    @commands.hybrid_command(name="hardban", aliases=["hb"])
    @commands.has_permissions(ban_members=True)
    async def hardban(self, ctx, target: discord.User, history: int = 7, *, reason: str = "hardban"):
        try:
            await ctx.guild.ban(target, delete_message_days=history, reason=reason)
            await send_modlog(self.bot, ctx.guild, "hardban", ctx.author, target, reason)
            await ctx.send(embed=success_embed(f"hardbanned {target.display_name.lower()}", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to hardban: {e}", ctx.author))

    @commands.hybrid_command(name="softban")
    @commands.has_permissions(ban_members=True)
    async def softban(self, ctx, user: discord.Member, *, reason: str = "softban"):
        try:
            await ctx.guild.ban(user, delete_message_days=7, reason=reason)
            await ctx.guild.unban(user, reason="softban unban")
            await send_modlog(self.bot, ctx.guild, "softban", ctx.author, user, reason)
            await ctx.send(embed=success_embed(f"softbanned {user.display_name.lower()}", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to softban: {e}", ctx.author))

    @commands.hybrid_group(name="unban", invoke_without_command=True)
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user: discord.User, *, reason: str = "unban"):
        try:
            await ctx.guild.unban(user, reason=reason)
            await send_modlog(self.bot, ctx.guild, "unban", ctx.author, user, reason)
            await ctx.send(embed=success_embed(f"unbanned {user.display_name.lower()}", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to unban: {e}", ctx.author))

    @unban.command(name="all")
    @commands.has_permissions(administrator=True)
    async def unban_all(self, ctx):
        bans = [entry async for entry in ctx.guild.bans()]
        for b in bans:
            try:
                await ctx.guild.unban(b.user)
            except Exception:
                pass
        await ctx.send(embed=success_embed(f"unbanned all {len(bans)} users", ctx.author))

    # warnings
    @commands.hybrid_group(name="warn", invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        now = int(time.time())
        await self.bot.db.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)", (ctx.guild.id, member.id, ctx.author.id, reason, now))
        await send_modlog(self.bot, ctx.guild, "warn", ctx.author, member, reason)
        await ctx.send(embed=success_embed(f"warned {member.display_name.lower()} — {reason.lower()}", ctx.author))

    @warn.command(name="list", aliases=["ls"])
    async def warn_list(self, ctx, member: discord.Member):
        rows = await self.bot.db.fetch("SELECT id, reason, timestamp FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        if not rows:
            return await ctx.send(embed=warn_embed(description=f"no warnings for {member.mention}", author=member))
        lines = [f"`#{r['id']}` — {r['reason']}" for r in rows]
        await ctx.send(embed=fleed_embed(title=f"warnings for {member.display_name.lower()}", description="\n".join(lines), author=member))

    @warn.command(name="remove")
    @commands.has_permissions(manage_messages=True)
    async def warn_remove(self, ctx, member: discord.Member, warning_id: int):
        await self.bot.db.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ? AND id = ?", (ctx.guild.id, member.id, warning_id))
        await ctx.send(embed=success_embed(f"removed warning #{warning_id} from {member.mention}", ctx.author))

    @warn.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def warn_clear(self, ctx, member: discord.Member):
        await self.bot.db.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"cleared all warnings for {member.mention}", ctx.author))

    @commands.command(name="warnings")
    async def warnings_alias(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        await self.warn_list(ctx, target)

    # strikes
    @commands.hybrid_group(name="strike", invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def strike(self, ctx, member: discord.Member = None, *, reason: str = "no reason provided"):
        if member is None:
            return await send_group_help(ctx, ctx.command)

        if member.id == ctx.author.id:
            return await ctx.send(embed=error_embed("you cannot strike yourself", ctx.author))
        if member.id == ctx.guild.owner_id:
            return await ctx.send(embed=error_embed("you cannot strike the server owner", ctx.author))
        if member.top_role >= ctx.author.top_role and not _is_owner_exempt(ctx):
            return await ctx.send(embed=error_embed("you cannot strike someone with a higher or equal role", ctx.author))
        if member.bot:
            return await ctx.send(embed=error_embed("you cannot strike a bot", ctx.author))

        now = int(time.time())
        await self.bot.db.execute(
            "INSERT INTO strikes (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, member.id, ctx.author.id, reason, now)
        )
        await self.bot.db.execute(
            "INSERT INTO modhistory (guild_id, user_id, moderator_id, action, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (ctx.guild.id, member.id, ctx.author.id, "strike", reason, now)
        )

        strike_rows = await self.bot.db.fetch("SELECT id FROM strikes WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        total_strikes = len(strike_rows)

        punishment_msg = ""
        punishment_row = await self.bot.db.fetchrow(
            "SELECT punishment_type, duration FROM strike_punishments WHERE guild_id = ? AND threshold = ?",
            (ctx.guild.id, total_strikes)
        )

        action_type = None
        action_dur = 0
        if punishment_row:
            action_type = punishment_row["punishment_type"].lower()
            action_dur = punishment_row["duration"]
        elif total_strikes == 3:
            action_type = "timeout"
            action_dur = 3600
        elif total_strikes >= 5:
            action_type = "kick"

        if action_type:
            try:
                if action_type == "timeout":
                    dur_secs = action_dur if action_dur > 0 else 3600
                    await member.timeout(discord.utils.utcnow() + discord.utils.timedelta(seconds=dur_secs), reason=f"auto-strike threshold ({total_strikes} strikes)")
                    punishment_msg = f"\napplied **{format_remaining(dur_secs)} timeout** (threshold reached)"
                    await send_modlog(self.bot, ctx.guild, "timeout", self.bot.user, member, f"auto-strike threshold reached ({total_strikes} strikes)")
                elif action_type == "kick":
                    await member.kick(reason=f"auto-strike threshold ({total_strikes} strikes)")
                    punishment_msg = f"\n**kicked** from server (threshold reached)"
                    await send_modlog(self.bot, ctx.guild, "kick", self.bot.user, member, f"auto-strike threshold reached ({total_strikes} strikes)")
                elif action_type == "ban":
                    await ctx.guild.ban(member, reason=f"auto-strike threshold ({total_strikes} strikes)")
                    punishment_msg = f"\n**banned** from server (threshold reached)"
                    await send_modlog(self.bot, ctx.guild, "ban", self.bot.user, member, f"auto-strike threshold reached ({total_strikes} strikes)")
                elif action_type == "jail":
                    jail_role = await self.get_or_create_jail_role(ctx.guild)
                    if jail_role:
                        await member.add_roles(jail_role, reason=f"auto-strike threshold ({total_strikes} strikes)")
                        punishment_msg = f"\n**jailed** (threshold reached)"
                        await send_modlog(self.bot, ctx.guild, "jail", self.bot.user, member, f"auto-strike threshold reached ({total_strikes} strikes)")
            except Exception as e:
                punishment_msg = f"\n*(failed to execute auto-{action_type}: {e})*"

        try:
            dm_embed = warn_embed(
                f"you received a strike in **{ctx.guild.name}**\n"
                f"**reason:** {reason}\n"
                f"**total strikes:** {total_strikes}" + (f"\n**action taken:** {action_type}" if action_type else ""),
                member
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass

        await send_modlog(self.bot, ctx.guild, "strike", ctx.author, member, f"{reason} (strike #{total_strikes})")
        await ctx.send(embed=success_embed(f"struck {member.mention} — {reason.lower()} *(strike #{total_strikes})*{punishment_msg}", ctx.author))

    @strike.command(name="add")
    @commands.has_permissions(manage_messages=True)
    async def strike_add(self, ctx, member: discord.Member, *, reason: str = "no reason provided"):
        await self.strike(ctx, member=member, reason=reason)

    @strike.command(name="list", aliases=["ls"])
    async def strike_list(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        rows = await self.bot.db.fetch("SELECT id, moderator_id, reason, timestamp FROM strikes WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, target.id))
        if not rows:
            return await ctx.send(embed=warn_embed(description=f"no strikes recorded for {target.mention}", author=ctx.author))
        lines = []
        for r in rows:
            mod = ctx.guild.get_member(r["moderator_id"])
            mod_name = mod.display_name.lower() if mod else f"`{r['moderator_id']}`"
            lines.append(f"`#{r['id']}` — {r['reason']} *(by {mod_name})*")
        await ctx.send(embed=fleed_embed(title=f"strikes for {target.display_name.lower()} ({len(rows)})", description="\n".join(lines), author=target))

    @strike.command(name="remove", aliases=["del", "rm"])
    @commands.has_permissions(manage_messages=True)
    async def strike_remove(self, ctx, member: discord.Member, strike_id: int):
        row = await self.bot.db.fetchrow("SELECT id FROM strikes WHERE guild_id = ? AND user_id = ? AND id = ?", (ctx.guild.id, member.id, strike_id))
        if not row:
            return await ctx.send(embed=error_embed(f"strike `#{strike_id}` not found for {member.mention}", ctx.author))
        await self.bot.db.execute("DELETE FROM strikes WHERE guild_id = ? AND user_id = ? AND id = ?", (ctx.guild.id, member.id, strike_id))
        await ctx.send(embed=success_embed(f"removed strike `#{strike_id}` from {member.mention}", ctx.author))

    @strike.command(name="clear", aliases=["reset"])
    @commands.has_permissions(manage_messages=True)
    async def strike_clear(self, ctx, member: discord.Member):
        await self.bot.db.execute("DELETE FROM strikes WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"cleared all strikes for {member.mention}", ctx.author))

    @strike.group(name="punishment", aliases=["punishments", "config"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def strike_punishment_group(self, ctx):
        rows = await self.bot.db.fetch("SELECT threshold, punishment_type, duration FROM strike_punishments WHERE guild_id = ? ORDER BY threshold ASC", (ctx.guild.id,))
        if not rows:
            desc = (
                "no custom punishments configured. using defaults:\n"
                "`3 strikes` — **1 hour timeout**\n"
                "`5 strikes` — **kick**\n\n"
                "to configure:\n"
                "`,strike punishment set <threshold> <timeout/kick/ban/jail> [duration]`\n"
                "`,strike punishment remove <threshold>`"
            )
            return await ctx.send(embed=fleed_embed(title="strike punishments", description=desc, author=ctx.author))
        lines = []
        for r in rows:
            dur_str = f" ({format_remaining(r['duration'])})" if r['duration'] > 0 else ""
            lines.append(f"`{r['threshold']} strikes` — **{r['punishment_type'].lower()}**{dur_str}")
        await ctx.send(embed=fleed_embed(title="strike punishments", description="\n".join(lines), author=ctx.author))

    @strike_punishment_group.command(name="set", aliases=["add"])
    @commands.has_permissions(administrator=True)
    async def strike_punishment_set(self, ctx, threshold: int, punishment_type: str, *, duration: str = None):
        punishment_type = punishment_type.lower()
        if punishment_type not in ["timeout", "mute", "kick", "ban", "jail"]:
            return await ctx.send(embed=error_embed("punishment type must be one of: `timeout`, `kick`, `ban`, `jail`", ctx.author))

        dur_secs = 0
        if duration:
            dur_secs = parse_duration(duration) or 0

        await self.bot.db.execute(
            "INSERT OR REPLACE INTO strike_punishments (guild_id, threshold, punishment_type, duration) VALUES (?, ?, ?, ?)",
            (ctx.guild.id, threshold, punishment_type, dur_secs)
        )
        dur_disp = f" for `{format_remaining(dur_secs)}`" if dur_secs > 0 else ""
        await ctx.send(embed=success_embed(f"set punishment for `{threshold}` strikes to **{punishment_type}**{dur_disp}", ctx.author))

    @strike_punishment_group.command(name="remove", aliases=["delete", "del", "rm"])
    @commands.has_permissions(administrator=True)
    async def strike_punishment_remove(self, ctx, threshold: int):
        await self.bot.db.execute("DELETE FROM strike_punishments WHERE guild_id = ? AND threshold = ?", (ctx.guild.id, threshold))
        await ctx.send(embed=success_embed(f"removed punishment rule for `{threshold}` strikes", ctx.author))

    @commands.command(name="strikes")
    async def strikes_alias(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        await self.strike_list(ctx, target)

    # timeouts & jail & mutes
    @commands.hybrid_group(name="timeout", invoke_without_command=True)
    @commands.has_permissions(moderate_members=True)
    async def timeout_cmd(self, ctx, member: discord.Member, duration: int = 60, *, reason: str = "No reason provided"):
        try:
            await member.timeout(discord.utils.utcnow() + discord.utils.timedelta(seconds=duration), reason=reason)
            await send_modlog(self.bot, ctx.guild, "timeout", ctx.author, member, f"{reason} ({duration}s)")
            await ctx.send(embed=success_embed(f"timed out {member.display_name.lower()} for {duration}s", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to timeout: {e}", ctx.author))

    @timeout_cmd.command(name="list", aliases=["ls"])
    async def timeout_list(self, ctx):
        timed_out = [m.mention for m in ctx.guild.members if m.timed_out_until]
        await ctx.send(embed=fleed_embed(title="timed out members", description="\n".join(timed_out) or "no timed out members", author=ctx.author))

    @commands.command(name="untimeout")
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason: str = "untimeout"):
        try:
            await member.timeout(None, reason=reason)
            await send_modlog(self.bot, ctx.guild, "untimeout", ctx.author, member, reason)
            await ctx.send(embed=success_embed(f"removed timeout for {member.display_name.lower()}", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to untimeout: {e}", ctx.author))

    @commands.command(name="untimeout_all")
    @commands.has_permissions(administrator=True)
    async def untimeout_all(self, ctx):
        for m in ctx.guild.members:
            if m.timed_out_until:
                try:
                    await m.timeout(None)
                except Exception:
                    pass
        await ctx.send(embed=success_embed("removed all active timeouts", ctx.author))

    async def get_or_create_jail_role(self, guild: discord.Guild):
        jail_role = discord.utils.get(guild.roles, name="jailed")
        if not jail_role:
            try:
                jail_role = await guild.create_role(name="jailed", color=discord.Color(0x2B2D31), permissions=discord.Permissions.none(), reason="fleed jail setup")
            except Exception:
                pass
        return jail_role

    @commands.hybrid_group(name="jail", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def jail(self, ctx, member: discord.Member, *, args: str = None):
        if member.id == ctx.author.id:
            return await ctx.send(embed=error_embed("you cannot jail yourself", ctx.author))
        if member.id == ctx.guild.owner_id:
            return await ctx.send(embed=error_embed("you cannot jail the server owner", ctx.author))
        if member.top_role >= ctx.author.top_role and not _is_owner_exempt(ctx):
            return await ctx.send(embed=error_embed("you cannot jail someone with a higher or equal role", ctx.author))

        # Check if already jailed
        existing = await self.bot.db.fetchrow("SELECT * FROM jailed_users WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        if existing:
            return await ctx.send(embed=warn_embed(f"{member.mention} is already in jail", ctx.author))

        # Parse duration and reason
        duration_seconds = 0
        reason = "no reason provided"
        if args:
            parts = args.split()
            dur = parse_duration(parts[0])
            if dur is not None:
                duration_seconds = dur
                reason = " ".join(parts[1:]) if len(parts) > 1 else "no reason provided"
            else:
                reason = args

        jail_role = await self.get_or_create_jail_role(ctx.guild)
        if not jail_role:
            return await ctx.send(embed=error_embed("failed to find or create the `jailed` role", ctx.author))

        # Backup roles before removing
        roles_to_save = [r.id for r in member.roles if r != ctx.guild.default_role and not r.managed and r < ctx.guild.me.top_role]
        roles_to_remove = [r for r in member.roles if r != ctx.guild.default_role and not r.managed and r < ctx.guild.me.top_role]

        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=f"jailed by {ctx.author}: {reason}")
            except Exception:
                pass

        try:
            await member.add_roles(jail_role, reason=f"jailed by {ctx.author}: {reason}")
        except Exception as e:
            return await ctx.send(embed=error_embed(f"failed to add jailed role: {e}", ctx.author))

        now = int(time.time())
        expires_at = now + duration_seconds if duration_seconds > 0 else 0
        roles_json = json.dumps(roles_to_save)

        await self.bot.db.execute(
            "INSERT OR REPLACE INTO jailed_users (guild_id, user_id, roles, jailed_at, expires_at, moderator_id, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ctx.guild.id, member.id, roles_json, now, expires_at, ctx.author.id, reason)
        )

        time_str = f" for `{format_remaining(duration_seconds)}`" if duration_seconds > 0 else " (indefinite)"
        await send_modlog(self.bot, ctx.guild, "jail", ctx.author, member, f"{reason}{time_str}")
        await ctx.send(embed=success_embed(f"jailed {member.mention}{time_str} — {reason.lower()}", ctx.author))

    @jail.command(name="list", aliases=["ls"])
    async def jail_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT * FROM jailed_users WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=fleed_embed(title="jailed members", description="none currently jailed", author=ctx.author))

        now = int(time.time())
        lines = []
        for r in rows:
            m = ctx.guild.get_member(r["user_id"])
            m_str = m.mention if m else f"`{r['user_id']}`"
            if r["expires_at"] > 0:
                rem = r["expires_at"] - now
                time_disp = f"`{format_remaining(rem)} remaining`" if rem > 0 else "`sentence expired`"
            else:
                time_disp = "`indefinite`"
            lines.append(f"{m_str} — {r['reason']} ({time_disp})")

        embed = fleed_embed(title=f"jailed members ({len(rows)})", description="\n".join(lines), author=ctx.author)
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="unjail", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def unjail(self, ctx, member: discord.Member):
        row = await self.bot.db.fetchrow("SELECT * FROM jailed_users WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        jail_role = discord.utils.get(ctx.guild.roles, name="jailed")

        if jail_role and jail_role in member.roles:
            try:
                await member.remove_roles(jail_role, reason=f"unjailed by {ctx.author}")
            except Exception:
                pass

        if row:
            saved_roles = json.loads(row["roles"]) if row["roles"] else []
            roles_to_add = [ctx.guild.get_role(rid) for rid in saved_roles if ctx.guild.get_role(rid) and ctx.guild.get_role(rid) < ctx.guild.me.top_role]
            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason=f"restoring roles on unjail by {ctx.author}")
                except Exception:
                    pass
            await self.bot.db.execute("DELETE FROM jailed_users WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
            await send_modlog(self.bot, ctx.guild, "unjail", ctx.author, member, "unjailed")
            await ctx.send(embed=success_embed(f"unjailed {member.mention} and restored {len(roles_to_add)} roles", ctx.author))
        else:
            await send_modlog(self.bot, ctx.guild, "unjail", ctx.author, member, "unjailed")
            await ctx.send(embed=success_embed(f"unjailed {member.mention}", ctx.author))

    @unjail.command(name="all")
    @commands.has_permissions(administrator=True)
    async def unjail_all(self, ctx):
        rows = await self.bot.db.fetch("SELECT * FROM jailed_users WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed("no members are currently jailed", ctx.author))

        jail_role = discord.utils.get(ctx.guild.roles, name="jailed")
        count = 0
        for r in rows:
            member = ctx.guild.get_member(r["user_id"])
            if member:
                if jail_role and jail_role in member.roles:
                    try:
                        await member.remove_roles(jail_role, reason="unjail all")
                    except Exception:
                        pass
                saved_roles = json.loads(r["roles"]) if r["roles"] else []
                roles_to_add = [ctx.guild.get_role(rid) for rid in saved_roles if ctx.guild.get_role(rid) and ctx.guild.get_role(rid) < ctx.guild.me.top_role]
                if roles_to_add:
                    try:
                        await member.add_roles(*roles_to_add, reason="unjail all: restoring roles")
                    except Exception:
                        pass
                count += 1

        await self.bot.db.execute("DELETE FROM jailed_users WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed(f"unjailed {count} members and cleared jail records", ctx.author))

    @commands.hybrid_group(name="imute", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def imute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        imute_role = discord.utils.get(ctx.guild.roles, name="imuted")
        if imute_role:
            try:
                await member.add_roles(imute_role, reason=reason)
            except Exception:
                pass
        await send_modlog(self.bot, ctx.guild, "imute", ctx.author, member, reason)
        await ctx.send(embed=success_embed(f"image muted {member.display_name.lower()}", ctx.author))

    @imute.command(name="list", aliases=["ls"])
    async def imute_list(self, ctx):
        role = discord.utils.get(ctx.guild.roles, name="imuted")
        members = [m.mention for m in (role.members if role else [])]
        await ctx.send(embed=fleed_embed(title="image muted members", description="\n".join(members) or "no image muted members", author=ctx.author))

    @commands.command(name="iunmute")
    @commands.has_permissions(manage_roles=True)
    async def iunmute(self, ctx, member: discord.Member, *, reason: str = "iunmute"):
        imute_role = discord.utils.get(ctx.guild.roles, name="imuted")
        if imute_role:
            try:
                await member.remove_roles(imute_role, reason=reason)
            except Exception:
                pass
        await send_modlog(self.bot, ctx.guild, "iunmute", ctx.author, member, reason)
        await ctx.send(embed=success_embed(f"unmuted images for {member.display_name.lower()}", ctx.author))

    @commands.hybrid_group(name="rmute", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def rmute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        rmute_role = discord.utils.get(ctx.guild.roles, name="rmuted")
        if rmute_role:
            try:
                await member.add_roles(rmute_role, reason=reason)
            except Exception:
                pass
        await send_modlog(self.bot, ctx.guild, "rmute", ctx.author, member, reason)
        await ctx.send(embed=success_embed(f"reaction muted {member.display_name.lower()}", ctx.author))

    @rmute.command(name="list", aliases=["ls"])
    async def rmute_list(self, ctx):
        role = discord.utils.get(ctx.guild.roles, name="rmuted")
        members = [m.mention for m in (role.members if role else [])]
        await ctx.send(embed=fleed_embed(title="reaction muted members", description="\n".join(members) or "no reaction muted members", author=ctx.author))

    @commands.command(name="runmute")
    @commands.has_permissions(manage_roles=True)
    async def runmute(self, ctx, member: discord.Member, *, reason: str = "runmute"):
        rmute_role = discord.utils.get(ctx.guild.roles, name="rmuted")
        if rmute_role:
            try:
                await member.remove_roles(rmute_role, reason=reason)
            except Exception:
                pass
        await send_modlog(self.bot, ctx.guild, "runmute", ctx.author, member, reason)
        await ctx.send(embed=success_embed(f"unmuted reactions for {member.display_name.lower()}", ctx.author))

    def find_role(self, guild: discord.Guild, query: str):
        return find_role(guild, query)

    # roles & mass role
    @commands.hybrid_group(name="role", aliases=["r"], invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def role_group(self, ctx, member: discord.Member = None, *, role: str = None):
        if member is None or role is None:
            return await send_group_help(ctx, ctx.command)

        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))

        if target_role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to my highest role", ctx.author))
        if target_role >= ctx.author.top_role and not _is_owner_exempt(ctx):
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to your highest role", ctx.author))

        try:
            if target_role in member.roles:
                await member.remove_roles(target_role, reason=f"role toggled by {ctx.author}")
                await ctx.send(embed=success_embed(f"removed {target_role.mention} from {member.display_name.lower()}", ctx.author, role=target_role))
            else:
                await member.add_roles(target_role, reason=f"role toggled by {ctx.author}")
                await ctx.send(embed=success_embed(f"added {target_role.mention} to {member.display_name.lower()}", ctx.author, role=target_role))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to update role: {e}", ctx.author))

    @role_group.command(name="add", aliases=["grant"])
    @commands.has_permissions(manage_roles=True)
    async def role_add(self, ctx, member: discord.Member, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))

        if target_role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to my highest role", ctx.author))
        if target_role >= ctx.author.top_role and not _is_owner_exempt(ctx):
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to your highest role", ctx.author))

        try:
            await member.add_roles(target_role, reason=f"role added by {ctx.author}")
            await ctx.send(embed=success_embed(f"added {target_role.mention} to {member.display_name.lower()}", ctx.author, role=target_role))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to add role: {e}", ctx.author))

    @role_group.command(name="remove", aliases=["rm"])
    @commands.has_permissions(manage_roles=True)
    async def role_remove(self, ctx, member: discord.Member, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))

        if target_role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to my highest role", ctx.author))
        if target_role >= ctx.author.top_role and not _is_owner_exempt(ctx):
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to your highest role", ctx.author))

        try:
            await member.remove_roles(target_role, reason=f"role removed by {ctx.author}")
            await ctx.send(embed=success_embed(f"removed {target_role.mention} from {member.display_name.lower()}", ctx.author, role=target_role))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to remove role: {e}", ctx.author))

    @role_group.command(name="create", aliases=["make"])
    @commands.has_permissions(manage_roles=True)
    async def role_create(self, ctx, color: str = None, hoist: bool = False, *, name: str):
        col = int(color.replace("#", ""), 16) if color and color.startswith("#") else 0
        r = await ctx.guild.create_role(name=name, color=discord.Color(col), hoist=hoist)
        await ctx.send(embed=success_embed(f"created role {r.mention}", ctx.author, role=r))

    @role_group.command(name="delete", aliases=["del"])
    @commands.has_permissions(manage_roles=True)
    async def role_delete(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        if target_role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed(f"role {target_role.mention} is higher than or equal to my highest role", ctx.author))
        saved_role = target_role
        await target_role.delete()
        await ctx.send(embed=success_embed(f"deleted role `{saved_role.name.lower()}`", ctx.author, role=saved_role))

    @role_group.command(name="rename", aliases=["name"])
    @commands.has_permissions(manage_roles=True)
    async def role_rename(self, ctx, role: str, *, name: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await target_role.edit(name=name)
        await ctx.send(embed=success_embed(f"renamed role to `{name.lower()}`", ctx.author, role=target_role))

    @role_group.command(name="color", aliases=["colour"])
    @commands.has_permissions(manage_roles=True)
    async def role_color(self, ctx, role: str, color: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        col = int(color.replace("#", ""), 16)
        await target_role.edit(color=discord.Color(col))
        await ctx.send(embed=success_embed(f"changed role color to `{color.lower()}`", ctx.author, role=target_role))

    @role_group.command(name="hoist")
    @commands.has_permissions(manage_roles=True)
    async def role_hoist(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await target_role.edit(hoist=not target_role.hoist)
        await ctx.send(embed=success_embed(f"toggled role hoist to {target_role.hoist}", ctx.author, role=target_role))

    @role_group.command(name="mentionable")
    @commands.has_permissions(manage_roles=True)
    async def role_mentionable(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await target_role.edit(mentionable=not target_role.mentionable)
        await ctx.send(embed=success_embed(f"toggled mentionable to {target_role.mentionable}", ctx.author, role=target_role))

    @role_group.command(name="icon")
    @commands.has_permissions(manage_roles=True)
    async def role_icon(self, ctx, role: str, icon_url: str = None):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        if target_role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed("that role is above my highest role", ctx.author))
        source_url = icon_url
        if not source_url and ctx.message.attachments:
            source_url = ctx.message.attachments[0].url
        try:
            if source_url and source_url.lower() not in {"none", "remove", "reset"}:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                    async with session.get(source_url) as response:
                        if response.status != 200:
                            raise RuntimeError(f"image returned HTTP {response.status}")
                        icon_bytes = await response.read()
                if len(icon_bytes) > 256 * 1024:
                    return await ctx.send(embed=error_embed("role icon must be smaller than 256 KB", ctx.author))
                await target_role.edit(display_icon=icon_bytes, reason=f"role icon changed by {ctx.author}")
            else:
                await target_role.edit(display_icon=None, reason=f"role icon removed by {ctx.author}")
            await ctx.send(embed=success_embed(f"updated role icon for {target_role.name.lower()}", ctx.author, role=target_role))
        except Exception as exc:
            await ctx.send(embed=error_embed(f"could not update role icon: {str(exc)[:250]}", ctx.author))

    @role_group.command(name="restore", aliases=["re"])
    @commands.has_permissions(manage_roles=True)
    async def role_restore(self, ctx, member: discord.Member):
        row = await self.bot.db.fetchrow("SELECT role_ids FROM role_snapshots WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        if not row:
            return await ctx.send(embed=warn_embed(f"no saved role snapshot exists for {member.mention}", ctx.author))
        role_ids = json.loads(row["role_ids"] or "[]")
        roles = [ctx.guild.get_role(int(role_id)) for role_id in role_ids]
        roles = [role for role in roles if role and not role.managed and role < ctx.guild.me.top_role and role not in member.roles]
        if roles:
            await member.add_roles(*roles, reason=f"roles restored by {ctx.author}")
        await self.bot.db.execute("DELETE FROM role_snapshots WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"restored {len(roles)} previous roles for {member.mention}", ctx.author))

    @role_group.command(name="cancel", aliases=["stop"])
    @commands.has_permissions(manage_roles=True)
    async def role_cancel(self, ctx):
        event = self.mass_role_cancellations.get(ctx.guild.id)
        if not event:
            return await ctx.send(embed=warn_embed("there is no active mass role operation", ctx.author))
        event.set()
        await ctx.send(embed=success_embed("cancelling the active mass role operation", ctx.author))

    @role_group.group(name="all", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_all(self, ctx, *, role: str = None):
        """add a role to every member, or show complete usage when no role is provided"""
        if not role:
            return await send_group_help(ctx, ctx.command, "moderation")
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, list(ctx.guild.members), True, "server members")

    @role_all.command(name="add", aliases=["give", "grant"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_all_add(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, list(ctx.guild.members), True, "server members")

    @role_all.command(name="remove", aliases=["rm"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_all_remove(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, list(ctx.guild.members), False, "server members")

    @role_group.group(name="bots", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_bots(self, ctx, *, role: str = None):
        if not role:
            return await send_group_help(ctx, ctx.command, "moderation")
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, [m for m in ctx.guild.members if m.bot], True, "bots")

    @role_bots.command(name="add", aliases=["give", "grant"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_bots_add(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, [m for m in ctx.guild.members if m.bot], True, "bots")

    @role_bots.command(name="remove", aliases=["rm"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_bots_remove(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, [m for m in ctx.guild.members if m.bot], False, "bots")

    @role_group.group(name="humans", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_humans(self, ctx, *, role: str = None):
        if not role:
            return await send_group_help(ctx, ctx.command, "moderation")
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, [m for m in ctx.guild.members if not m.bot], True, "human members")

    @role_humans.command(name="add", aliases=["give", "grant"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_humans_add(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, [m for m in ctx.guild.members if not m.bot], True, "human members")

    @role_humans.command(name="remove", aliases=["rm"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_humans_remove(self, ctx, *, role: str):
        target_role = self.find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_role, [m for m in ctx.guild.members if not m.bot], False, "human members")

    @role_group.group(name="has", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_has(self, ctx, source_role: str = None, *, target_role: str = None):
        if not source_role or not target_role:
            return await send_group_help(ctx, ctx.command, "moderation")
        source = self.find_role(ctx.guild, source_role)
        target = self.find_role(ctx.guild, target_role)
        if not source:
            return await ctx.send(embed=error_embed(f"could not find role `{source_role}`", ctx.author))
        if not target:
            return await ctx.send(embed=error_embed(f"could not find role `{target_role}`", ctx.author))
        await self.run_mass_role_update(ctx, target, list(source.members), True, f"members with {source.mention}")

    @role_has.command(name="remove", aliases=["rm"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_has_remove(self, ctx, role: str, remove_role: str):
        target_role = self.find_role(ctx.guild, role)
        target_remove = self.find_role(ctx.guild, remove_role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"could not find role `{role}`", ctx.author))
        if not target_remove:
            return await ctx.send(embed=error_embed(f"could not find role `{remove_role}`", ctx.author))
        await self.run_mass_role_update(ctx, target_remove, list(target_role.members), False, f"members with {target_role.mention}")
    @commands.command(name="roles")
    async def roles_list(self, ctx):
        roles = [r for r in reversed(ctx.guild.roles) if not r.is_default()]
        if not roles:
            return await ctx.send(embed=warn_embed("no custom roles in server", ctx.author))
        entries = [f"`{idx:02}` {r.mention} (`{r.id}`)" for idx, r in enumerate(roles, start=1)]
        await send_paginated_embed(ctx, f"server roles ({len(roles)})", entries, per_page=15, item_name="roles")

    # strip & staffstrip
    @commands.command(name="strip")
    @commands.has_permissions(manage_roles=True)
    async def strip(self, ctx, member: discord.Member, *, reason: str = "stripped"):
        dangerous_perms = ["administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members", "kick_members"]
        to_remove = [r for r in member.roles[1:] if any(getattr(r.permissions, p, False) for p in dangerous_perms)]
        try:
            await self.bot.db.execute(
                "INSERT OR REPLACE INTO role_snapshots (guild_id, user_id, role_ids, created_at) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, member.id, json.dumps([r.id for r in to_remove]), int(time.time())),
            )
            await member.remove_roles(*to_remove)
            await ctx.send(embed=success_embed(f"stripped {len(to_remove)} dangerous roles from {member.display_name.lower()}", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to strip roles: {e}", ctx.author))

    @commands.command(name="staffstrip", aliases=["stripstaff"])
    @commands.has_permissions(administrator=True)
    async def staffstrip(self, ctx, member: discord.Member, *, reason: str = "staffstrip"):
        await self.strip(ctx, member, reason=reason)

    # purges
    @commands.hybrid_group(name="purge", invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int = 10):
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(embed=success_embed(f"purged {len(deleted) - 1} messages", ctx.author), delete_after=3)

    @purge.command(name="bots", aliases=["bot"])
    @commands.has_permissions(manage_messages=True)
    async def purge_bots(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.bot)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} bot messages", ctx.author), delete_after=3)

    @purge.command(name="humans", aliases=["human"])
    @commands.has_permissions(manage_messages=True)
    async def purge_humans(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: not m.author.bot)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} human messages", ctx.author), delete_after=3)

    @purge.command(name="system", aliases=["sys"])
    @commands.has_permissions(manage_messages=True)
    async def purge_system(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.is_system())
        await ctx.send(embed=success_embed(f"purged {len(deleted)} system messages", ctx.author), delete_after=3)

    @purge.command(name="embeds", aliases=["embed"])
    @commands.has_permissions(manage_messages=True)
    async def purge_embeds(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: len(m.embeds) > 0)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} embed messages", ctx.author), delete_after=3)

    @purge.command(name="files", aliases=["file"])
    @commands.has_permissions(manage_messages=True)
    async def purge_files(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: len(m.attachments) > 0)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} files", ctx.author), delete_after=3)

    @purge.command(name="images", aliases=["image"])
    @commands.has_permissions(manage_messages=True)
    async def purge_images(self, ctx, amount: int = 50):
        await self.purge_files(ctx, amount)

    @purge.command(name="links", aliases=["link"])
    @commands.has_permissions(manage_messages=True)
    async def purge_links(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: "http://" in m.content or "https://" in m.content)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} link messages", ctx.author), delete_after=3)

    @purge.command(name="invites", aliases=["invite", "inv"])
    @commands.has_permissions(manage_messages=True)
    async def purge_invites(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: "discord.gg/" in m.content or "discord.com/invite/" in m.content)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} invite messages", ctx.author), delete_after=3)

    @purge.command(name="mentions", aliases=["mention"])
    @commands.has_permissions(manage_messages=True)
    async def purge_mentions(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: len(m.mentions) > 0 or len(m.role_mentions) > 0)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} mention messages", ctx.author), delete_after=3)

    @purge.command(name="emojis", aliases=["emotes", "emoji", "emote"])
    @commands.has_permissions(manage_messages=True)
    async def purge_emojis(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: "<:" in m.content or "<a:" in m.content)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} emoji messages", ctx.author), delete_after=3)

    @purge.command(name="reactions", aliases=["reaction", "react"])
    @commands.has_permissions(manage_messages=True)
    async def purge_reactions(self, ctx, amount: int = 50):
        async for m in ctx.channel.history(limit=amount):
            try:
                await m.clear_reactions()
            except Exception:
                pass
        await ctx.send(embed=success_embed(f"cleared reactions on last {amount} messages", ctx.author), delete_after=3)

    @purge.command(name="stickers", aliases=["sticker"])
    @commands.has_permissions(manage_messages=True)
    async def purge_stickers(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: len(m.stickers) > 0)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} sticker messages", ctx.author), delete_after=3)

    @purge.command(name="webhooks", aliases=["webhook"])
    @commands.has_permissions(manage_messages=True)
    async def purge_webhooks(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.webhook_id is not None)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} webhook messages", ctx.author), delete_after=3)

    @purge.command(name="voice", aliases=["vm"])
    @commands.has_permissions(manage_messages=True)
    async def purge_voice(self, ctx, amount: int = 50):
        voice_types = {"call", "stage_start", "stage_end", "stage_speaker", "voice_hangout_invite"}
        deleted = await ctx.channel.purge(limit=max(1, min(amount, 1000)), check=lambda m: getattr(m.type, "name", str(m.type)) in voice_types)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} voice or stage status messages", ctx.author), delete_after=3)

    @purge.command(name="contains", aliases=["contain"])
    @commands.has_permissions(manage_messages=True)
    async def purge_contains(self, ctx, substring: str, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: substring.lower() in m.content.lower())
        await ctx.send(embed=success_embed(f"purged {len(deleted)} messages containing `{substring.lower()}`", ctx.author), delete_after=3)

    @purge.command(name="startswith", aliases=["prefix", "start", "sw"])
    @commands.has_permissions(manage_messages=True)
    async def purge_startswith(self, ctx, substring: str, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.content.lower().startswith(substring.lower()))
        await ctx.send(embed=success_embed(f"purged {len(deleted)} messages starting with `{substring.lower()}`", ctx.author), delete_after=3)

    @purge.command(name="endswith", aliases=["suffix", "end", "ew"])
    @commands.has_permissions(manage_messages=True)
    async def purge_endswith(self, ctx, substring: str, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.content.lower().endswith(substring.lower()))
        await ctx.send(embed=success_embed(f"purged {len(deleted)} messages ending with `{substring.lower()}`", ctx.author), delete_after=3)

    @purge.command(name="except", aliases=["besides", "schizo"])
    @commands.has_permissions(manage_messages=True)
    async def purge_except(self, ctx, member: discord.Member, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.id != member.id)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} messages except from {member.mention}", ctx.author), delete_after=3)

    @purge.command(name="between")
    @commands.has_permissions(manage_messages=True)
    async def purge_between(self, ctx, start: int, finish: int):
        first = await ctx.channel.fetch_message(start)
        second = await ctx.channel.fetch_message(finish)
        before, after = (first, second) if first.created_at > second.created_at else (second, first)
        deleted = await ctx.channel.purge(limit=1000, before=before, after=after)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} messages between {start} and {finish}", ctx.author), delete_after=3)

    @purge.command(name="before")
    @commands.has_permissions(manage_messages=True)
    async def purge_before(self, ctx, message_id: int):
        msg = await ctx.channel.fetch_message(message_id)
        deleted = await ctx.channel.purge(limit=50, before=msg)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} messages before {message_id}", ctx.author), delete_after=3)

    @purge.command(name="after", aliases=["upto", "up"])
    @commands.has_permissions(manage_messages=True)
    async def purge_after(self, ctx, message_id: int):
        msg = await ctx.channel.fetch_message(message_id)
        deleted = await ctx.channel.purge(limit=50, after=msg)
        await ctx.send(embed=success_embed(f"purged {len(deleted)} messages after {message_id}", ctx.author), delete_after=3)

    @commands.command(name="selfpurge", aliases=["sp"])
    async def selfpurge(self, ctx, amount: int = 10):
        deleted = await ctx.channel.purge(limit=amount + 1, check=lambda m: m.author.id == ctx.author.id)
        await ctx.send(embed=success_embed(f"purged {len(deleted) - 1} of your messages", ctx.author), delete_after=3)

    @commands.command(name="cleanup", aliases=["bc"])
    @commands.has_permissions(manage_messages=True)
    async def cleanup(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.bot or m.content.startswith(","))
        await ctx.send(embed=success_embed(f"cleaned up {len(deleted)} command and bot messages", ctx.author), delete_after=3)

    # channel management & lockdown
    @commands.hybrid_group(name="channel", aliases=["ch"], invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def channel_group(self, ctx):
        await send_group_help(ctx, ctx.command, "moderation")

    @channel_group.command(name="rename", aliases=["name"])
    @commands.has_permissions(manage_channels=True)
    async def channel_rename(self, ctx, channel: discord.abc.GuildChannel, *, new_name: str):
        old_name = channel.name
        await channel.edit(name=new_name[:100], reason=f"channel rename by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"renamed {channel.mention} to `{new_name[:100]}`", ctx.author))

    @channel_group.command(name="create", aliases=["make", "new"])
    @commands.has_permissions(manage_channels=True)
    async def channel_create(self, ctx, channel_type: str = "text", *, name: str):
        c_type = channel_type.lower()
        if c_type in ["voice", "vc"]:
            ch = await ctx.guild.create_voice_channel(name=name[:100], reason=f"created by {ctx.author}")
        elif c_type in ["category", "cat"]:
            ch = await ctx.guild.create_category(name=name[:100], reason=f"created by {ctx.author}")
        else:
            ch = await ctx.guild.create_text_channel(name=name[:100], reason=f"created by {ctx.author}")
        await ctx.send(embed=success_embed(f"created {ch.mention}", ctx.author))

    @channel_group.command(name="delete", aliases=["del", "remove"])
    @commands.has_permissions(manage_channels=True)
    async def channel_delete(self, ctx, channel: discord.abc.GuildChannel = None):
        target = channel or ctx.channel
        name_saved = target.name
        await target.delete(reason=f"deleted by {ctx.author} ({ctx.author.id})")
        if target.id != ctx.channel.id:
            await ctx.send(embed=success_embed(f"deleted channel `{name_saved}`", ctx.author))

    @commands.command(name="nsfw", aliases=["naughty", "sfw"])
    @commands.has_permissions(manage_channels=True)
    async def nsfw(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await ch.edit(nsfw=not ch.is_nsfw())
        await ctx.send(embed=success_embed(f"toggled nsfw for {ch.mention} to {ch.is_nsfw()}", ctx.author))

    @commands.group(name="topic", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def topic(self, ctx, channel: discord.TextChannel, *, topic_text: str):
        await channel.edit(topic=topic_text)
        await ctx.send(embed=success_embed(f"set topic for {channel.mention}", ctx.author))

    @topic.command(name="remove", aliases=["delete", "del", "rm"])
    @commands.has_permissions(manage_channels=True)
    async def topic_remove(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await ch.edit(topic=None)
        await ctx.send(embed=success_embed(f"removed topic for {ch.mention}", ctx.author))

    @commands.hybrid_group(name="slowmode", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await ch.edit(slowmode_delay=seconds)
        await ctx.send(embed=success_embed(f"set slowmode for {ch.mention} to {seconds}s", ctx.author))

    @slowmode.command(name="disable", aliases=["off", "remove"])
    @commands.has_permissions(manage_channels=True)
    async def slowmode_disable(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await ch.edit(slowmode_delay=0)
        await ctx.send(embed=success_embed(f"disabled slowmode for {ch.mention}", ctx.author))

    @commands.command(name="hide", aliases=["private", "priv"])
    @commands.has_permissions(manage_channels=True)
    async def hide(self, ctx, channel: discord.TextChannel = None, target: discord.Role = None, *, reason: str = "hidden"):
        ch = channel or ctx.channel
        tgt = target or ctx.guild.default_role
        await ch.set_permissions(tgt, view_channel=False)
        await ctx.send(embed=success_embed(f"hid {ch.mention} from {tgt.name.lower()}", ctx.author))

    @commands.command(name="reveal", aliases=["unhide", "public"])
    @commands.has_permissions(manage_channels=True)
    async def reveal(self, ctx, channel: discord.TextChannel = None, target: discord.Role = None, *, reason: str = "revealed"):
        ch = channel or ctx.channel
        tgt = target or ctx.guild.default_role
        await ch.set_permissions(tgt, view_channel=True)
        await ctx.send(embed=success_embed(f"revealed {ch.mention} to {tgt.name.lower()}", ctx.author))

    @commands.hybrid_group(name="lockdown", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def lockdown(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await ch.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send(embed=success_embed(f"locked down {ch.mention}", ctx.author))

    @lockdown.command(name="all")
    @commands.has_permissions(administrator=True)
    async def lockdown_all(self, ctx, *, reason: str = "server lockdown"):
        ignored_rows = await self.bot.db.fetch("SELECT channel_id FROM lockdown_ignored WHERE guild_id = ?", (ctx.guild.id,))
        ignored = {row["channel_id"] for row in ignored_rows}
        for ch in ctx.guild.text_channels:
            if ch.id in ignored:
                continue
            try:
                await ch.set_permissions(ctx.guild.default_role, send_messages=False)
            except Exception:
                pass
        await ctx.send(embed=success_embed("locked down all channels", ctx.author))

    @lockdown.command(name="role")
    @commands.has_permissions(manage_roles=True)
    async def lockdown_role(self, ctx, role: discord.Role):
        await ctx.channel.set_permissions(role, send_messages=False, reason=f"role lockdown by {ctx.author}")
        await ctx.send(embed=success_embed(f"locked {role.name} from sending in {ctx.channel.mention}", ctx.author, role=role))

    @lockdown.group(name="ignore", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def lockdown_ignore(self, ctx):
        await send_group_help(ctx, ctx.command)

    @lockdown_ignore.command(name="add")
    async def lockdown_ignore_add(self, ctx, channel: discord.TextChannel):
        await self.bot.db.execute("INSERT OR IGNORE INTO lockdown_ignored (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, channel.id))
        await ctx.send(embed=success_embed(f"ignored {channel.mention} during server-wide lockdowns", ctx.author))

    @lockdown_ignore.command(name="list", aliases=["ls"])
    async def lockdown_ignore_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT channel_id FROM lockdown_ignored WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(title="lockdown ignored channels", description="\n".join(f"<#{r['channel_id']}>" for r in rows) or "none", author=ctx.author))

    @lockdown_ignore.command(name="remove", aliases=["delete", "del", "rm"])
    async def lockdown_ignore_remove(self, ctx, channel: discord.TextChannel):
        await self.bot.db.execute("DELETE FROM lockdown_ignored WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, channel.id))
        await ctx.send(embed=success_embed(f"removed {channel.mention} from lockdown ignore", ctx.author))

    @commands.command(name="unlockdown")
    @commands.has_permissions(manage_channels=True)
    async def unlockdown(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await ch.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send(embed=success_embed(f"unlocked {ch.mention}", ctx.author))

    @commands.command(name="unlockdown_all")
    @commands.has_permissions(administrator=True)
    async def unlockdown_all(self, ctx, *, reason: str = "unlockdown all"):
        ignored_rows = await self.bot.db.fetch("SELECT channel_id FROM lockdown_ignored WHERE guild_id = ?", (ctx.guild.id,))
        ignored = {row["channel_id"] for row in ignored_rows}
        for ch in ctx.guild.text_channels:
            if ch.id in ignored:
                continue
            try:
                await ch.set_permissions(ctx.guild.default_role, send_messages=True)
            except Exception:
                pass
        await ctx.send(embed=success_embed("unlocked all channels", ctx.author))

    # denyperm
    @commands.group(name="denyperm", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def denyperm(self, ctx):
        await send_group_help(ctx, ctx.command)

    @denyperm.command(name="add")
    async def denyperm_add(self, ctx, permission: str):
        permission = permission.lower().strip()
        valid = {name for name, _ in discord.Permissions.all()}
        if permission not in valid:
            return await ctx.send(embed=error_embed(f"unknown Discord permission `{permission}`", ctx.author))
        await self.bot.db.execute("INSERT OR IGNORE INTO deny_permissions (guild_id, permission_name) VALUES (?, ?)", (ctx.guild.id, permission))
        await ctx.send(embed=success_embed(f"added `{permission.lower()}` to denied permissions list", ctx.author))

    @denyperm.command(name="remove")
    async def denyperm_remove(self, ctx, permission: str):
        await self.bot.db.execute("DELETE FROM deny_permissions WHERE guild_id = ? AND permission_name = ?", (ctx.guild.id, permission.lower().strip()))
        await ctx.send(embed=success_embed(f"removed `{permission.lower()}` from denied list", ctx.author))

    @denyperm.command(name="clear")
    async def denyperm_clear(self, ctx):
        await self.bot.db.execute("DELETE FROM deny_permissions WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("cleared denied permissions list", ctx.author))

    @denyperm.command(name="available", aliases=["list"])
    async def denyperm_available(self, ctx):
        rows = await self.bot.db.fetch("SELECT permission_name FROM deny_permissions WHERE guild_id = ?", (ctx.guild.id,))
        configured = ", ".join(f"`{r['permission_name']}`" for r in rows) or "none"
        common = "administrator, ban_members, kick_members, manage_roles, manage_channels, manage_messages"
        await ctx.send(embed=fleed_embed(title="denied permissions", description=f"configured: {configured}\n\ncommon options: {common}", author=ctx.author))

    # nicknames & force nicknames
    @commands.hybrid_group(name="nickname", invoke_without_command=True)
    @commands.has_permissions(manage_nicknames=True)
    async def nickname_cmd(self, ctx, member: discord.Member, *, nickname: str):
        await member.edit(nick=nickname)
        await ctx.send(embed=success_embed(f"changed nickname for {member.mention} to `{nickname.lower()}`", ctx.author))

    @nickname_cmd.command(name="remove", aliases=["reset", "rm"])
    @commands.has_permissions(manage_nicknames=True)
    async def nickname_remove(self, ctx, member: discord.Member):
        await member.edit(nick=None)
        await ctx.send(embed=success_embed(f"reset nickname for {member.mention}", ctx.author))

    @nickname_cmd.group(name="force", invoke_without_command=True)
    @commands.has_permissions(manage_nicknames=True)
    async def nickname_force(self, ctx, member: discord.Member, *, nickname: str = None):
        if not nickname:
            return await send_group_help(ctx, ctx.command, "moderation")
        await self.bot.db.execute("INSERT OR REPLACE INTO forced_nicknames (guild_id, user_id, nickname) VALUES (?, ?, ?)", (ctx.guild.id, member.id, nickname.lower()))
        await member.edit(nick=nickname)
        await ctx.send(embed=success_embed(f"forced nickname `{nickname.lower()}` on {member.mention}", ctx.author))

    @nickname_force.command(name="cancel", aliases=["stop"])
    async def nickname_force_cancel(self, ctx, member: discord.Member):
        await self.bot.db.execute("DELETE FROM forced_nicknames WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"cancelled forced nickname for {member.mention}", ctx.author))

    @commands.command(name="fn")
    @commands.has_permissions(manage_nicknames=True)
    async def fn_alias(self, ctx, member: discord.Member, *, nickname: str = None):
        if not nickname:
            return await self.nickname_force_cancel(ctx, member)
        await self.nickname_force(ctx, member, nickname=nickname)

    @commands.command(name="picperms", aliases=["pic", "pictureperms", "picture"])
    @commands.has_permissions(manage_channels=True)
    async def picperms(self, ctx, member: discord.Member, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        curr = ch.permissions_for(member).attach_files
        await ch.set_permissions(member, attach_files=not curr, embed_links=not curr)
        await ctx.send(embed=success_embed(f"toggled picture permissions for {member.mention} in {ch.mention} to {not curr}", ctx.author))

    @commands.command(name="history")
    async def history_cmd(self, ctx, user: discord.User):
        rows = await self.bot.db.fetch("SELECT action, reason, timestamp FROM modhistory WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, user.id))
        if not rows:
            return await ctx.send(embed=warn_embed(description=f"no moderation history for {user.display_name.lower()}", author=ctx.author))
        lines = [f"`{r['action']}` — {r['reason']}" for r in rows]
        await ctx.send(embed=fleed_embed(title=f"history for {user.display_name.lower()}", description="\n".join(lines), author=ctx.author))

    @commands.command(name="modhistory")
    async def modhistory_cmd(self, ctx, moderator: discord.Member):
        rows = await self.bot.db.fetch("SELECT action, user_id, reason FROM modhistory WHERE guild_id = ? AND moderator_id = ?", (ctx.guild.id, moderator.id))
        if not rows:
            return await ctx.send(embed=warn_embed(description=f"no actions logged for {moderator.display_name.lower()}", author=ctx.author))
        lines = [f"`{r['action']}` on <@{r['user_id']}> — {r['reason']}" for r in rows]
        await ctx.send(embed=fleed_embed(title=f"moderator history: {moderator.display_name.lower()}", description="\n".join(lines), author=moderator))

    @commands.command(name="audit")
    @commands.has_permissions(view_audit_log=True)
    async def audit_cmd(self, ctx, limit: int = 5):
        entries = [entry async for entry in ctx.guild.audit_logs(limit=limit)]
        lines = [f"{str(e.user).lower()} -> {e.action.name.lower()} on {e.target}" for e in entries]
        await ctx.send(embed=fleed_embed(title="recent audit logs", description="\n".join(lines) or "no entries", author=ctx.author))

    @commands.hybrid_group(name="setup", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def setup_group(self, ctx):
        await self.setup_full(ctx)

    @setup_group.command(name="full", aliases=["server", "all"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def setup_full(self, ctx, force: str = None):
        guild = ctx.guild

        # Check if server is already set up
        is_force = force and force.lower() in ("force", "--force", "-f")
        if not is_force:
            key_roles = [r for r in guild.roles if r.name.lower() in ("admin", "moderator", "member", "jailed", "muted")]
            cat_info = discord.utils.get(guild.categories, name="information")
            if len(key_roles) >= 3 or cat_info:
                return await ctx.send(embed=warn_embed("the server is already set up", ctx.author))

        msg = await ctx.send(embed=fleed_embed(description="setting up server infrastructure... please wait", author=ctx.author))

        # ==========================================
        # 1. ROLES HIERARCHY SETUP
        # ==========================================
        roles_spec = [
            ("owner", discord.Color(0xF1C40F), True, discord.Permissions.none()),
            ("executive", discord.Color(0xE67E22), True, discord.Permissions.none()),
            ("admin", discord.Color(0xE74C3C), True, discord.Permissions(administrator=True)),
            ("moderator", discord.Color(0x3498DB), True, discord.Permissions(manage_messages=True, kick_members=True, ban_members=True, moderate_members=True)),
            ("booster", discord.Color(0xF47FFF), True, discord.Permissions.none()),
            ("vip", discord.Color(0x9B59B6), True, discord.Permissions.none()),
            ("pic perms", discord.Color(0xB9BBBE), False, discord.Permissions.none()),
            ("member", discord.Color(0x95A5A6), True, discord.Permissions.none()),
            ("bots", discord.Color(0x7289DA), True, discord.Permissions.none()),
            ("birthday", discord.Color(0xFF70A6), False, discord.Permissions.none()),
            ("muted", discord.Color(0x4F545C), False, discord.Permissions.none()),
            ("jailed", discord.Color(0x2B2D31), False, discord.Permissions.none()),
            ("imuted", discord.Color(0x4F545C), False, discord.Permissions.none()),
            ("rmuted", discord.Color(0x4F545C), False, discord.Permissions.none()),
        ]

        created_roles = {}
        for r_name, r_color, r_hoist, r_perms in roles_spec:
            role = discord.utils.get(guild.roles, name=r_name)
            if not role:
                try:
                    role = await guild.create_role(
                        name=r_name,
                        color=r_color,
                        hoist=r_hoist,
                        permissions=r_perms,
                        reason="fleed server setup: roles"
                    )
                except Exception:
                    pass
            created_roles[r_name] = role

        admin_role = created_roles.get("admin")
        mod_role = created_roles.get("moderator")
        booster_role = created_roles.get("booster")
        vip_role = created_roles.get("vip")
        pic_perms_role = created_roles.get("pic perms")
        member_role = created_roles.get("member")
        jail_role = created_roles.get("jailed")
        mute_role = created_roles.get("muted")
        imute_role = created_roles.get("imuted")
        rmute_role = created_roles.get("rmuted")

        # ==========================================
        # 2. CATEGORIES & CHANNELS SETUP
        # ==========================================
        
        # --- Category 1: information ---
        cat_info = discord.utils.get(guild.categories, name="information")
        if not cat_info:
            cat_info = await guild.create_category(name="information", reason="fleed server setup")
        
        info_overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=True, read_messages=True),
            guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True, manage_messages=True)
        }
        
        ch_rules = discord.utils.get(cat_info.text_channels, name="rules")
        if not ch_rules:
            ch_rules = await guild.create_text_channel(name="rules", category=cat_info, overwrites=info_overwrites, topic="server rules")
            rules_desc = (
                "1. respect everyone\n"
                "2. no spam or self promotion\n"
                "3. follow discord tos\n"
                "4. use appropriate channels\n"
                "5. listen to staff"
            )
            await ch_rules.send(embed=fleed_embed(title="rules", description=rules_desc))

        ch_announcements = discord.utils.get(cat_info.text_channels, name="announcements")
        if not ch_announcements:
            ch_announcements = await guild.create_text_channel(name="announcements", category=cat_info, overwrites=info_overwrites, topic="announcements")

        ch_welcome = discord.utils.get(cat_info.text_channels, name="welcome")
        if not ch_welcome:
            ch_welcome = await guild.create_text_channel(name="welcome", category=cat_info, overwrites=info_overwrites, topic="welcome")

        ch_boosts = discord.utils.get(cat_info.text_channels, name="boosts")
        if not ch_boosts:
            ch_boosts = await guild.create_text_channel(name="boosts", category=cat_info, overwrites=info_overwrites, topic="boosts")

        # --- Category 2: text ---
        cat_chat = discord.utils.get(guild.categories, name="text")
        if not cat_chat:
            cat_chat = await guild.create_category(name="text", reason="fleed server setup")

        # #chat: text chat where @everyone has no attach_files/embed_links, pic perms / boosters / staff have pic perms
        chat_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=False, embed_links=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True, manage_messages=True)
        }
        if pic_perms_role:
            chat_overwrites[pic_perms_role] = discord.PermissionOverwrite(attach_files=True, embed_links=True)
        if booster_role:
            chat_overwrites[booster_role] = discord.PermissionOverwrite(attach_files=True, embed_links=True)
        if vip_role:
            chat_overwrites[vip_role] = discord.PermissionOverwrite(attach_files=True, embed_links=True)
        if mod_role:
            chat_overwrites[mod_role] = discord.PermissionOverwrite(attach_files=True, embed_links=True)
        if admin_role:
            chat_overwrites[admin_role] = discord.PermissionOverwrite(attach_files=True, embed_links=True)

        ch_chat = discord.utils.get(cat_chat.text_channels, name="chat")
        if not ch_chat:
            ch_chat = await guild.create_text_channel(name="chat", category=cat_chat, overwrites=chat_overwrites, topic="general chat")
        else:
            try:
                for target, ov in chat_overwrites.items():
                    await ch_chat.set_permissions(target, overwrite=ov)
            except Exception:
                pass

        # #media: dedicated image/media posting channel (everyone can post media)
        media_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True, manage_messages=True)
        }
        ch_media = discord.utils.get(cat_chat.text_channels, name="media")
        if not ch_media:
            ch_media = await guild.create_text_channel(name="media", category=cat_chat, overwrites=media_overwrites, topic="media")
        else:
            try:
                for target, ov in media_overwrites.items():
                    await ch_media.set_permissions(target, overwrite=ov)
            except Exception:
                pass

        # #commands: bot commands channel
        cmds_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=False, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True, manage_messages=True)
        }
        ch_cmds = discord.utils.get(cat_chat.text_channels, name="commands")
        if not ch_cmds:
            ch_cmds = await guild.create_text_channel(name="commands", category=cat_chat, overwrites=cmds_overwrites, topic="bot commands")

        # #levels: level up alerts channel (read-only for members)
        ch_levels = discord.utils.get(cat_chat.text_channels, name="levels")
        if not ch_levels:
            ch_levels = await guild.create_text_channel(name="levels", category=cat_chat, overwrites=info_overwrites, topic="levels")

        # --- Category 3: voice ---
        cat_voice = discord.utils.get(guild.categories, name="voice")
        if not cat_voice:
            cat_voice = await guild.create_category(name="voice", reason="fleed server setup")

        vc_lounge = discord.utils.get(cat_voice.voice_channels, name="lounge")
        if not vc_lounge:
            vc_lounge = await guild.create_voice_channel(name="lounge", category=cat_voice)

        vc_gaming = discord.utils.get(cat_voice.voice_channels, name="gaming")
        if not vc_gaming:
            vc_gaming = await guild.create_voice_channel(name="gaming", category=cat_voice)

        # VoiceMaster Join To Create & Interface
        vc_vm = discord.utils.get(cat_voice.voice_channels, name="join to create")
        if not vc_vm:
            vc_vm = await guild.create_voice_channel(name="join to create", category=cat_voice, reason="voicemaster setup")

        tc_vm = discord.utils.get(cat_voice.text_channels, name="interface")
        if not tc_vm:
            vm_overwrites = {
                guild.default_role: discord.PermissionOverwrite(send_messages=False, view_channel=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True, manage_messages=True, view_channel=True)
            }
            tc_vm = await guild.create_text_channel(name="interface", category=cat_voice, overwrites=vm_overwrites, topic="voicemaster interface")
            
            try:
                from cogs.voice import create_voicemaster_embed, VoiceMasterView
                vm_embed = await create_voicemaster_embed(guild, self.bot)
                vm_view = VoiceMasterView(self.bot, guild)
                await tc_vm.send(embed=vm_embed, view=vm_view)
            except Exception:
                pass

        # --- Category 4: support ---
        cat_support = discord.utils.get(guild.categories, name="support")
        if not cat_support:
            cat_support = await guild.create_category(name="support", reason="fleed server setup")

        ch_tickets = discord.utils.get(cat_support.text_channels, name="tickets")
        if not ch_tickets:
            ch_tickets = await guild.create_text_channel(name="tickets", category=cat_support, overwrites=info_overwrites, topic="tickets")
            ticket_desc = "type `,tickets open` to create a ticket"
            await ch_tickets.send(embed=fleed_embed(title="support tickets", description=ticket_desc))

        # --- Category 5: staff ---
        cat_staff = discord.utils.get(guild.categories, name="staff")
        staff_overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False, read_messages=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, manage_messages=True, manage_channels=True)
        }
        if admin_role:
            staff_overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
        if mod_role:
            staff_overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)

        if not cat_staff:
            cat_staff = await guild.create_category(name="staff", overwrites=staff_overwrites, reason="fleed server setup")
        else:
            try:
                for target, ov in staff_overwrites.items():
                    await cat_staff.set_permissions(target, overwrite=ov)
            except Exception:
                pass

        ch_staff_chat = discord.utils.get(cat_staff.text_channels, name="staff")
        if not ch_staff_chat:
            ch_staff_chat = await guild.create_text_channel(name="staff", category=cat_staff, topic="staff chat")

        ch_modlog = discord.utils.get(cat_staff.text_channels, name="mod-logs")
        if not ch_modlog:
            ch_modlog = await guild.create_text_channel(name="mod-logs", category=cat_staff, topic="mod logs")

        ch_audit = discord.utils.get(cat_staff.text_channels, name="audit-logs")
        if not ch_audit:
            ch_audit = await guild.create_text_channel(name="audit-logs", category=cat_staff, topic="audit logs")

        ch_jail = discord.utils.get(cat_staff.text_channels, name="jail")
        if not ch_jail:
            jail_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False, read_messages=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, manage_messages=True)
            }
            if jail_role:
                jail_overwrites[jail_role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, read_message_history=True, attach_files=False, embed_links=False)
            if admin_role:
                jail_overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
            if mod_role:
                jail_overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
            ch_jail = await guild.create_text_channel(name="jail", category=cat_staff, overwrites=jail_overwrites, topic="jail cell")

        # ==========================================
        # 3. GLOBAL CHANNEL PERMISSIONS ENFORCEMENT
        # ==========================================
        try:
            for ch in guild.channels:
                if ch.id != ch_jail.id and isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel)):
                    if jail_role:
                        await ch.set_permissions(jail_role, view_channel=False, reason="fleed setup: isolate jailed role")
                    if isinstance(ch, discord.TextChannel):
                        if imute_role:
                            await ch.set_permissions(imute_role, attach_files=False, embed_links=False, reason="fleed setup: imute")
                        if rmute_role:
                            await ch.set_permissions(rmute_role, add_reactions=False, reason="fleed setup: rmute")
                        if mute_role:
                            await ch.set_permissions(mute_role, send_messages=False, add_reactions=False, reason="fleed setup: mute")
        except Exception:
            pass

        # ==========================================
        # 4. DATABASE AUTOMATION CONFIGURATIONS
        # ==========================================
        
        # Guild settings
        await self.bot.db.execute(
            """
            INSERT INTO guild_settings (guild_id, modlog_id, jail_id, imuted_id, rmuted_id, muted_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                modlog_id = excluded.modlog_id,
                jail_id = excluded.jail_id,
                imuted_id = excluded.imuted_id,
                rmuted_id = excluded.rmuted_id,
                muted_id = excluded.muted_id
            """,
            (guild.id, ch_modlog.id, ch_jail.id, imute_role.id if imute_role else None, rmute_role.id if rmute_role else None, mute_role.id if mute_role else None)
        )

        # VoiceMaster
        await self.bot.db.execute(
            """
            INSERT INTO voicemaster_config (guild_id, channel_id, category_id, interface_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                category_id = excluded.category_id,
                interface_id = excluded.interface_id
            """,
            (guild.id, vc_vm.id, cat_voice.id, tc_vm.id)
        )

        # Welcome & Leave
        await self.bot.db.execute(
            "INSERT INTO welcome_config (guild_id, channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id",
            (guild.id, ch_welcome.id)
        )
        await self.bot.db.execute(
            "INSERT INTO leave_config (guild_id, channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id",
            (guild.id, ch_welcome.id)
        )

        # Levels
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO level_config (guild_id) VALUES (?)",
            (guild.id,)
        )

        # AutoRole
        if member_role:
            await self.bot.db.execute(
                "INSERT OR REPLACE INTO autoroles (guild_id, role_id) VALUES (?, ?)",
                (guild.id, member_role.id)
            )

        # Audit Logging
        for ev in ["messages", "members", "server", "voice", "roles", "channels"]:
            await self.bot.db.execute(
                "INSERT OR REPLACE INTO logs_config (guild_id, channel_id, event_type) VALUES (?, ?, ?)",
                (guild.id, ch_audit.id, ev)
            )

        # AntiNuke & AntiRaid
        await self.bot.db.execute(
            "INSERT INTO antinuke_config (guild_id, enabled) VALUES (?, 1) ON CONFLICT(guild_id) DO UPDATE SET enabled = 1",
            (guild.id,)
        )
        await self.bot.db.execute(
            "INSERT INTO antiraid_config (guild_id, enabled, massjoin, massmention, avatar, age, unverifiedbots) VALUES (?, 1, 1, 1, 1, 1, 1) ON CONFLICT(guild_id) DO UPDATE SET enabled = 1, massjoin = 1, massmention = 1, avatar = 1, age = 1, unverifiedbots = 1",
            (guild.id,)
        )

        # ==========================================
        # 5. COMPLETION SUMMARY EMBED
        # ==========================================
        summary_desc = (
            f"completed server setup for **{guild.name.lower()}**\n\n"
            f"**roles**\n"
            f"staff: {admin_role.mention if admin_role else 'admin'}, {mod_role.mention if mod_role else 'moderator'}\n"
            f"members: {member_role.mention if member_role else 'member'}, {pic_perms_role.mention if pic_perms_role else 'pic perms'}\n"
            f"punishments: {jail_role.mention if jail_role else 'jailed'}, {mute_role.mention if mute_role else 'muted'}, {imute_role.mention if imute_role else 'imuted'}, {rmute_role.mention if rmute_role else 'rmuted'}\n\n"
            f"**channels**\n"
            f"info: {ch_rules.mention}, {ch_announcements.mention}, {ch_welcome.mention}\n"
            f"text: {ch_chat.mention}, {ch_media.mention}, {ch_cmds.mention}, {ch_levels.mention}\n"
            f"voice: {vc_vm.mention} & {tc_vm.mention}\n"
            f"support: {ch_tickets.mention}\n"
            f"staff: {ch_modlog.mention}, {ch_audit.mention}, {ch_jail.mention}\n\n"
            f"**automations**\n"
            f"voicemaster, welcome, leave, levels, autorole, mod logs, audit logs, antinuke, antiraid"
        )
        await msg.edit(embed=success_embed(summary_desc, ctx.author))

    @setup_group.command(name="mod", aliases=["moderation"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def setup_mod(self, ctx):
        guild = ctx.guild

        # 1. Create or get Moderation Category
        category = discord.utils.get(guild.categories, name="staff")
        if not category:
            category = await guild.create_category(name="staff", reason="fleed setup: moderation category")

        # 2. Create Roles if they don't exist
        jail_role = discord.utils.get(guild.roles, name="jailed") or await guild.create_role(name="jailed", color=discord.Color(0x2B2D31), reason="fleed setup: jail role")
        imute_role = discord.utils.get(guild.roles, name="imuted") or await guild.create_role(name="imuted", color=discord.Color(0x2B2D31), reason="fleed setup: image mute role")
        rmute_role = discord.utils.get(guild.roles, name="rmuted") or await guild.create_role(name="rmuted", color=discord.Color(0x2B2D31), reason="fleed setup: reaction mute role")
        mute_role = discord.utils.get(guild.roles, name="muted") or await guild.create_role(name="muted", color=discord.Color(0x2B2D31), reason="fleed setup: mute role")

        # 3. Create Channels
        modlog_channel = discord.utils.get(category.text_channels, name="mod-logs")
        if not modlog_channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
            }
            modlog_channel = await guild.create_text_channel(
                name="mod-logs",
                category=category,
                overwrites=overwrites,
                topic="moderation logs",
                reason="fleed setup: modlog channel"
            )

        jail_channel = discord.utils.get(category.text_channels, name="jail")
        if not jail_channel:
            jail_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                jail_role: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=False, embed_links=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
            }
            jail_channel = await guild.create_text_channel(
                name="jail",
                category=category,
                overwrites=jail_overwrites,
                topic="jail cell",
                reason="fleed setup: jail channel"
            )

        # 4. Set channel overwrites across guild channels
        try:
            for ch in guild.channels:
                if ch.id != jail_channel.id and isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel)):
                    await ch.set_permissions(jail_role, view_channel=False, reason="fleed setup: restrict jailed role")
                    if isinstance(ch, discord.TextChannel):
                        await ch.set_permissions(imute_role, attach_files=False, embed_links=False, reason="fleed setup: imute permissions")
                        await ch.set_permissions(rmute_role, add_reactions=False, reason="fleed setup: rmute permissions")
                        await ch.set_permissions(mute_role, send_messages=False, add_reactions=False, reason="fleed setup: mute permissions")
        except Exception:
            pass

        # 5. Save to database
        await self.bot.db.execute(
            """
            INSERT INTO guild_settings (guild_id, modlog_id, jail_id, imuted_id, rmuted_id, muted_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                modlog_id = excluded.modlog_id,
                jail_id = excluded.jail_id,
                imuted_id = excluded.imuted_id,
                rmuted_id = excluded.rmuted_id,
                muted_id = excluded.muted_id
            """,
            (guild.id, modlog_channel.id, jail_channel.id, imute_role.id, rmute_role.id, mute_role.id)
        )

        desc = (
            f"completed moderation setup\n"
            f"category: {category.name}\n"
            f"mod logs: {modlog_channel.mention}\n"
            f"jail channel: {jail_channel.mention}\n"
            f"jail role: {jail_role.mention}\n"
            f"image mute role: {imute_role.mention}\n"
            f"reaction mute role: {rmute_role.mention}\n"
            f"mute role: {mute_role.mention}"
        )
        await ctx.send(embed=success_embed(desc, ctx.author))

    @setup_group.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def setup_reset(self, ctx):
        guild = ctx.guild
        row = await self.bot.db.fetchrow("SELECT modlog_id, jail_id, imuted_id, rmuted_id FROM guild_settings WHERE guild_id = ?", (guild.id,))
        if row:
            for ch_id in [row["modlog_id"], row["jail_id"]]:
                if ch_id:
                    ch = guild.get_channel(ch_id)
                    if ch:
                        try:
                            await ch.delete(reason="fleed setup reset")
                        except Exception:
                            pass
            for r_id in [row["imuted_id"], row["rmuted_id"]]:
                if r_id:
                    r = guild.get_role(r_id)
                    if r:
                        try:
                            await r.delete(reason="fleed setup reset")
                        except Exception:
                            pass
            category = discord.utils.get(guild.categories, name="staff") or discord.utils.get(guild.categories, name="fleed-mod")
            if category and len(category.channels) == 0:
                try:
                    await category.delete(reason="fleed setup reset")
                except Exception:
                    pass

            await self.bot.db.execute("UPDATE guild_settings SET modlog_id = NULL, jail_id = NULL, imuted_id = NULL, rmuted_id = NULL, muted_id = NULL WHERE guild_id = ?", (guild.id,))

        await ctx.send(embed=success_embed("reset all moderation roles and channels configuration", ctx.author))

    @commands.group(name="protect", invoke_without_command=True)
    async def protect_group(self, ctx):
        await send_group_help(ctx, self.protect_group, "moderation")

    @protect_group.command(name="list", aliases=["ls"])
    async def protect_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id FROM protected_members WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(title="protected members", description="\n".join(f"<@{r['user_id']}>" for r in rows) or "none", author=ctx.author))

    @protect_group.command(name="add")
    @commands.has_permissions(administrator=True)
    async def protect_add(self, ctx, member: discord.Member):
        await self.bot.db.execute("INSERT OR IGNORE INTO protected_members (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"protected {member.mention} from automated moderation", ctx.author))

    @protect_group.command(name="remove", aliases=["delete", "del"])
    @commands.has_permissions(administrator=True)
    async def protect_remove(self, ctx, member: discord.Member):
        await self.bot.db.execute("DELETE FROM protected_members WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"removed protection from {member.mention}", ctx.author))

    # ==================== CLEARSERVER (OWNER ONLY) ====================

    @commands.command(name="clearserver", aliases=["serverclear", "wipeguild", "guildwipe", "nukeguild"])
    @commands.bot_has_permissions(administrator=True)
    async def clearserver_cmd(self, ctx):
        # strictly server owner or bot owner
        is_owner = _is_owner_exempt(ctx)
        if not is_owner:
            return await ctx.send(embed=error_embed("only the server owner can execute clearserver", ctx.author))

        view = ClearServerConfirmView(self.bot, ctx.author)
        embed = fleed_embed(
            title="clear server confirmation",
            description="warning: this will permanently delete all channels, categories, roles, and bot settings in this server.\nclick confirm to proceed.",
            author=ctx.author
        )
        await ctx.send(embed=embed, view=view)

    # ==================== EXTENDED MODERATION TOOLKIT ====================

    @commands.command(name="voicedeafen", aliases=["vdeafen", "deafen"])
    @commands.has_permissions(mute_members=True)
    @commands.bot_has_permissions(mute_members=True, deafen_members=True)
    async def voicedeafen(self, ctx, member: discord.Member):
        """server deafens a member in their current voice channel"""
        if not member.voice or not member.voice.channel:
            return await ctx.send(embed=warn_embed(f"{member.mention} is not in a voice channel", ctx.author))
        if member.top_role >= ctx.guild.me.top_role and member.id != ctx.guild.owner_id:
            return await ctx.send(embed=error_embed("i cannot deafen that member, role hierarchy", ctx.author))
        try:
            await member.edit(deafen=True, reason=f"voicedeafen by {ctx.author}")
        except discord.Forbidden:
            return await ctx.send(embed=error_embed("missing permission to deafen that member", ctx.author))
        await ctx.send(embed=success_embed(f"deafened {member.mention} in {member.voice.channel.name}", ctx.author))

    @commands.command(name="voiceundeafen", aliases=["vundeafen", "undeafen"])
    @commands.has_permissions(mute_members=True)
    @commands.bot_has_permissions(deafen_members=True)
    async def voiceundeafen(self, ctx, member: discord.Member):
        """removes a server deafen from a member"""
        if not member.voice:
            return await ctx.send(embed=warn_embed(f"{member.mention} is not in a voice channel", ctx.author))
        try:
            await member.edit(deafen=False, reason=f"voiceundeafen by {ctx.author}")
        except discord.Forbidden:
            return await ctx.send(embed=error_embed("missing permission to undeafen that member", ctx.author))
        await ctx.send(embed=success_embed(f"undeafened {member.mention}", ctx.author))

    @commands.command(name="voicemute", aliases=["vmute", "supress", "suppress"])
    @commands.has_permissions(mute_members=True)
    @commands.bot_has_permissions(mute_members=True)
    async def voicemute(self, ctx, member: discord.Member):
        """server mutes a member so nobody in voice can hear them"""
        if not member.voice or not member.voice.channel:
            return await ctx.send(embed=warn_embed(f"{member.mention} is not in a voice channel", ctx.author))
        if member.top_role >= ctx.guild.me.top_role and member.id != ctx.guild.owner_id:
            return await ctx.send(embed=error_embed("i cannot voice mute that member, role hierarchy", ctx.author))
        try:
            await member.edit(mute=True, reason=f"voicemute by {ctx.author}")
        except discord.Forbidden:
            return await ctx.send(embed=error_embed("missing permission to voice mute that member", ctx.author))
        await ctx.send(embed=success_embed(f"voice muted {member.mention} in {member.voice.channel.name}", ctx.author))

    @commands.command(name="voiceunmute", aliases=["vunmute"])
    @commands.has_permissions(mute_members=True)
    @commands.bot_has_permissions(mute_members=True)
    async def voiceunmute(self, ctx, member: discord.Member):
        """removes a server voice mute from a member"""
        if not member.voice:
            return await ctx.send(embed=warn_embed(f"{member.mention} is not in a voice channel", ctx.author))
        try:
            await member.edit(mute=False, reason=f"voiceunmute by {ctx.author}")
        except discord.Forbidden:
            return await ctx.send(embed=error_embed("missing permission to voice unmute that member", ctx.author))
        await ctx.send(embed=success_embed(f"voice unmuted {member.mention}", ctx.author))

    @commands.command(name="drainchannel", aliases=["vcdrain"])
    @commands.has_permissions(move_members=True)
    @commands.bot_has_permissions(move_members=True)
    async def drainchannel(self, ctx, channel: discord.VoiceChannel = None):
        """disconnects every member from a voice channel"""
        channel = channel or (ctx.author.voice.channel if ctx.author.voice else None)
        if not channel:
            return await ctx.send(embed=warn_embed("specify a voice channel or join one first", ctx.author))
        members = channel.members
        disconnected = 0
        for m in members:
            try:
                await m.move_to(None, reason=f"drainchannel by {ctx.author}")
                disconnected += 1
            except discord.Forbidden:
                pass
        await ctx.send(embed=success_embed(f"disconnected {disconnected}/{len(members)} members from {channel.name}", ctx.author))

    @commands.command(name="disconnectbots", aliases=["vcbotkick"])
    @commands.has_permissions(move_members=True)
    @commands.bot_has_permissions(move_members=True)
    async def disconnectbots(self, ctx):
        """disconnects every bot from all voice channels"""
        moved = 0
        for vc in ctx.guild.voice_channels:
            for m in vc.members:
                if m.bot:
                    try:
                        await m.move_to(None, reason=f"disconnectbots by {ctx.author}")
                        moved += 1
                    except discord.Forbidden:
                        pass
        await ctx.send(embed=success_embed(f"disconnected {moved} bots from voice", ctx.author))

    @commands.command(name="vcstats", aliases=["voicestats"])
    async def vcstats(self, ctx):
        """shows occupancy of every voice channel"""
        lines = []
        for vc in sorted(ctx.guild.voice_channels, key=lambda c: c.position):
            count = len(vc.members)
            lines.append(f"{vc.name}: **{count}** connected")
        embed = fleed_embed(title=f"voice stats ({len(ctx.guild.voice_channels)} channels)", description="\n".join(lines) or "no voice channels", author=ctx.author)
        await ctx.send(embed=embed)

    @commands.command(name="emptyvcs")
    async def emptyvcs(self, ctx):
        """lists all voice channels with nobody in them"""
        empty = [vc.name for vc in ctx.guild.voice_channels if not vc.members]
        embed = fleed_embed(title=f"empty voice channels ({len(empty)})", description="\n".join(empty) or "none", author=ctx.author)
        await ctx.send(embed=embed)

    @commands.command(name="prunevcs")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def prunevcs(self, ctx):
        """deletes every empty voice channel in the server"""
        deleted = 0
        for vc in list(ctx.guild.voice_channels):
            if not vc.members:
                try:
                    await vc.delete(reason=f"prunevcs by {ctx.author}")
                    deleted += 1
                except discord.Forbidden:
                    pass
        await ctx.send(embed=success_embed(f"deleted {deleted} empty voice channels", ctx.author))

    @commands.command(name="dehoist", aliases=["fixhoisting"])
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def dehoist(self, ctx):
        """renames every member whose name starts with hoisting characters (!, ., #, *, etc)"""
        hoist_chars = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
        fixed = 0
        for m in ctx.guild.members:
            if m.bot or m.top_role >= ctx.guild.me.top_role:
                continue
            name = m.display_name
            if name and name[0] in hoist_chars:
                stripped = name.lstrip(hoist_chars).strip() or m.name
                try:
                    await m.edit(nick=stripped[:32], reason=f"dehoist by {ctx.author}")
                    fixed += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
        await ctx.send(embed=success_embed(f"dehoisted {fixed} members", ctx.author))

    @commands.command(name="decancer", aliases=["clean-nick", "nickclean"])
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def decancer(self, ctx, member: discord.Member = None):
        """removes special unicode characters from a members nickname (all members if none given)"""
        def _clean(name: str) -> str:
            cleaned = "".join(ch if ord(ch) < 0x2100 or ch == "™" else "" for ch in name)
            return cleaned.strip()[:32]

        targets = [member] if member else [m for m in ctx.guild.members if not m.bot and m.top_role < ctx.guild.me.top_role]
        fixed = 0
        for m in targets:
            name = m.display_name
            if name and _clean(name) != name and _clean(name):
                try:
                    await m.edit(nick=_clean(name), reason=f"decancer by {ctx.author}")
                    fixed += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
                if member:
                    break
        await ctx.send(embed=success_embed(f"decancered {fixed} nickname(s)", ctx.author))

    @commands.command(name="nickscan", aliases=["hoistscan"])
    @commands.has_permissions(manage_nicknames=True)
    async def nickscan(self, ctx):
        """reports how many members have hoisted or special character nicknames"""
        hoist_chars = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
        hoisted = sum(1 for m in ctx.guild.members if m.display_name and m.display_name[0] in hoist_chars)
        cancered = sum(1 for m in ctx.guild.members if m.display_name and any(ord(ch) >= 0x2100 and ch != "™" for ch in m.display_name))
        desc = f"hoisted names: **{hoisted}**\nspecial character names: **{cancered}**\ntotal members: **{ctx.guild.member_count}**"
        await ctx.send(embed=fleed_embed(title="nickname scan", description=desc, author=ctx.author))

    @commands.command(name="massnick", aliases=["nickall"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def massnick(self, ctx, *, nickname: str):
        """sets the same nickname for every human member"""
        applied = 0
        for m in ctx.guild.members:
            if m.bot or m.top_role >= ctx.guild.me.top_role:
                continue
            try:
                await m.edit(nick=nickname[:32], reason=f"massnick by {ctx.author}")
                applied += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"set nickname for {applied} members", ctx.author))

    @commands.command(name="resetnicks", aliases=["unnickall"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def resetnicks(self, ctx):
        """removes nicknames from every member the bot can edit"""
        cleared = 0
        for m in ctx.guild.members:
            if m.bot or m.nick is None or m.top_role >= ctx.guild.me.top_role:
                continue
            try:
                await m.edit(nick=None, reason=f"resetnicks by {ctx.author}")
                cleared += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"reset {cleared} nicknames", ctx.author))

    @commands.command(name="tempban", aliases=["tban"])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def tempban(self, ctx, member: discord.Member, duration: str, *, reason: str = None):
        """bans a member and automatically unbans them after the duration"""
        seconds = parse_duration(duration)
        if not seconds or seconds <= 0:
            return await ctx.send(embed=warn_embed("invalid duration, example: 1d12h", ctx.author))
        if member.id == ctx.author.id:
            return await ctx.send(embed=error_embed("you cannot tempban yourself", ctx.author))
        if member.top_role >= ctx.author.top_role and not _is_owner_exempt(ctx):
            return await ctx.send(embed=error_embed("you cannot tempban someone with an equal or higher role", ctx.author))
        if member.top_role >= ctx.guild.me.top_role and member.id != ctx.guild.owner_id:
            return await ctx.send(embed=error_embed("i cannot tempban that member, role hierarchy", ctx.author))
        await member.ban(reason=f"tempban ({duration}) by {ctx.author}: {reason or 'no reason provided'}", delete_message_days=0)
        await send_modlog(self.bot, ctx.guild, "tempban", ctx.author, member, f"{reason or 'no reason provided'} (duration: {duration})")
        asyncio.create_task(self._tempban_expire(ctx.guild.id, member.id, seconds))
        await ctx.send(embed=success_embed(f"tempbanned {member.mention} for **{format_remaining(seconds)}**", ctx.author))

    async def _tempban_expire(self, guild_id: int, user_id: int, seconds: int):
        await asyncio.sleep(seconds)
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        try:
            await guild.unban(discord.Object(id=user_id), reason="tempban expired")
        except (discord.NotFound, discord.Forbidden):
            pass

    @commands.command(name="massban", aliases=["multiban"])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def massban(self, ctx, user_ids: str, *, reason: str = None):
        """bans multiple users by id, separated by spaces or commas"""
        ids = [int(x) for x in re.findall(r"\d{15,20}", user_ids)]
        if not ids:
            return await ctx.send(embed=warn_embed("provide at least one valid user id", ctx.author))
        banned = 0
        for uid in ids[:25]:
            try:
                await ctx.guild.ban(discord.Object(id=uid), reason=f"massban by {ctx.author}: {reason or 'no reason provided'}", delete_message_days=0)
                banned += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await send_modlog(self.bot, ctx.guild, "massban", ctx.author, None, f"banned {banned} users: {reason or 'no reason provided'}")
        await ctx.send(embed=success_embed(f"banned {banned}/{len(ids)} users", ctx.author))

    @commands.command(name="masskick", aliases=["multikick"])
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def masskick(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = None):
        """kicks multiple members at once"""
        if not members:
            return await ctx.send(embed=warn_embed("provide at least one member", ctx.author))
        kicked = 0
        for m in members[:20]:
            if m.bot or (m.top_role >= ctx.author.top_role and not _is_owner_exempt(ctx)) or m.top_role >= ctx.guild.me.top_role:
                continue
            try:
                await m.kick(reason=f"masskick by {ctx.author}: {reason or 'no reason provided'}")
                kicked += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await send_modlog(self.bot, ctx.guild, "masskick", ctx.author, None, f"kicked {kicked} members: {reason or 'no reason provided'}")
        await ctx.send(embed=success_embed(f"kicked {kicked}/{len(members)} members", ctx.author))

    @commands.command(name="baninfo", aliases=["isbanned", "checkban"])
    @commands.has_permissions(ban_members=True)
    async def baninfo(self, ctx, user_id: str):
        """checks if a user id is banned and shows the ban reason"""
        if not user_id.isdigit() or not 15 <= len(user_id) <= 20:
            return await ctx.send(embed=warn_embed("provide a valid user id", ctx.author))
        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=int(user_id)))
        except discord.NotFound:
            return await ctx.send(embed=fleed_embed(description=f"`{user_id}` is **not** banned", author=ctx.author))
        user, reason = ban_entry.user, ban_entry.reason
        desc = f"user: {user} (`{user.id}`)\nreason: {reason or 'no reason provided'}"
        await ctx.send(embed=fleed_embed(title="ban info", description=desc, author=ctx.author))

    @commands.command(name="recentbans", aliases=["lastbans"])
    @commands.has_permissions(ban_members=True)
    async def recentbans(self, ctx, limit: int = 10):
        """lists the most recent bans in the server"""
        try:
            bans = [b async for b in ctx.guild.bans(limit=limit)]
        except discord.Forbidden:
            return await ctx.send(embed=error_embed("i need the ban members permission to list bans", ctx.author))
        if not bans:
            return await ctx.send(embed=fleed_embed(description="no bans found", author=ctx.author))
        lines = [f"{b.user} (`{b.user.id}`): {b.reason or 'no reason'}" for b in bans[:limit]]
        await ctx.send(embed=fleed_embed(title=f"recent bans ({len(bans)})", description="\n".join(lines), author=ctx.author))

    @commands.command(name="banstats")
    @commands.has_permissions(ban_members=True)
    async def banstats(self, ctx):
        """counts total bans and bans performed by the bot"""
        total = sum(1 for _ in await ctx.guild.bans())
        rows = await self.bot.db.fetch("SELECT COUNT(*) as c FROM modhistory WHERE guild_id = ? AND action IN ('ban','hardban','tempban','massban')", (ctx.guild.id,))
        bot_bans = rows[0]["c"] if rows else 0
        desc = f"total bans on server: **{total}**\ncases logged by bot: **{bot_bans}**"
        await ctx.send(embed=fleed_embed(title="ban stats", description=desc, author=ctx.author))

    @commands.command(name="case")
    @commands.has_permissions(manage_messages=True)
    async def case_lookup(self, ctx, case_number: int):
        """shows a single moderation case by number"""
        rows = await self.bot.db.fetch("SELECT rowid, * FROM modhistory WHERE guild_id = ? ORDER BY timestamp", (ctx.guild.id,))
        if case_number < 1 or case_number > len(rows):
            return await ctx.send(embed=warn_embed(f"case #{case_number} does not exist", ctx.author))
        row = rows[case_number - 1]
        action = row["action"]
        user_str = f"<@{row['user_id']}>" if row["user_id"] else "unknown"
        mod_str = f"<@{row['moderator_id']}>" if row["moderator_id"] else "unknown"
        desc = f"case **#{case_number}**\naction: **{action}**\nuser: {user_str}\nmoderator: {mod_str}\nreason: {row['reason']}\nwhen: <t:{row['timestamp']}:R>"
        await ctx.send(embed=fleed_embed(title="moderation case", description=desc, author=ctx.author))

    @commands.command(name="editreason", aliases=["casereason"])
    @commands.has_permissions(manage_messages=True)
    async def editreason(self, ctx, case_number: int, *, new_reason: str):
        """edits the reason of a logged moderation case"""
        rows = await self.bot.db.fetch("SELECT rowid FROM modhistory WHERE guild_id = ? ORDER BY timestamp", (ctx.guild.id,))
        if case_number < 1 or case_number > len(rows):
            return await ctx.send(embed=warn_embed(f"case #{case_number} does not exist", ctx.author))
        target = rows[case_number - 1]
        await self.bot.db.execute("UPDATE modhistory SET reason = ? WHERE rowid = ?", (new_reason, target["rowid"]))
        await ctx.send(embed=success_embed(f"updated reason for case #{case_number}", ctx.author))

    @commands.command(name="delcase", aliases=["removecase"])
    @commands.has_permissions(administrator=True)
    async def delcase(self, ctx, case_number: int):
        """deletes a moderation case from the log"""
        rows = await self.bot.db.fetch("SELECT rowid FROM modhistory WHERE guild_id = ? ORDER BY timestamp", (ctx.guild.id,))
        if case_number < 1 or case_number > len(rows):
            return await ctx.send(embed=warn_embed(f"case #{case_number} does not exist", ctx.author))
        target = rows[case_number - 1]
        await self.bot.db.execute("DELETE FROM modhistory WHERE rowid = ?", (target["rowid"],))
        await ctx.send(embed=success_embed(f"deleted case #{case_number}", ctx.author))

    @commands.command(name="latestcase", aliases=["lastcase"])
    @commands.has_permissions(manage_messages=True)
    async def latestcase(self, ctx):
        """shows the most recent moderation case"""
        row = await self.bot.db.fetchrow("SELECT rowid, * FROM modhistory WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 1", (ctx.guild.id,))
        if not row:
            return await ctx.send(embed=fleed_embed(description="no moderation cases logged yet", author=ctx.author))
        total = await self.bot.db.fetchrow("SELECT COUNT(*) as c FROM modhistory WHERE guild_id = ?", (ctx.guild.id,))
        desc = f"case **#{total['c']}**\naction: **{row['action']}**\nuser: <@{row['user_id']}>\nmoderator: <@{row['moderator_id']}>\nreason: {row['reason']}\nwhen: <t:{row['timestamp']}:R>"
        await ctx.send(embed=fleed_embed(title="latest case", description=desc, author=ctx.author))

    @commands.command(name="modstats")
    @commands.has_permissions(manage_messages=True)
    async def modstats(self, ctx):
        """shows a breakdown of all moderation actions by type"""
        rows = await self.bot.db.fetch("SELECT action, COUNT(*) as c FROM modhistory WHERE guild_id = ? GROUP BY action ORDER BY c DESC", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=fleed_embed(description="no moderation cases logged yet", author=ctx.author))
        lines = [f"{r['action']}: **{r['c']}**" for r in rows]
        await ctx.send(embed=fleed_embed(title="moderation stats", description="\n".join(lines), author=ctx.author))

    @commands.command(name="modtop", aliases=["topmods"])
    @commands.has_permissions(manage_messages=True)
    async def modtop(self, ctx):
        """ranks moderators by number of logged cases"""
        rows = await self.bot.db.fetch("SELECT moderator_id, COUNT(*) as c FROM modhistory WHERE guild_id = ? GROUP BY moderator_id ORDER BY c DESC LIMIT 10", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=fleed_embed(description="no moderation cases logged yet", author=ctx.author))
        lines = [f"`{i}.` <@{r['moderator_id']}> — **{r['c']}** cases" for i, r in enumerate(rows, 1)]
        await ctx.send(embed=fleed_embed(title="top moderators", description="\n".join(lines), author=ctx.author))

    @commands.command(name="resetmodhistory", aliases=["clearmodhistory"])
    @commands.has_permissions(administrator=True)
    async def resetmodhistory(self, ctx, member: discord.Member = None):
        """wipes logged moderation cases for a member or the whole server"""
        if member:
            await self.bot.db.execute("DELETE FROM modhistory WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
            await ctx.send(embed=success_embed(f"cleared mod history for {member.mention}", ctx.author))
        else:
            await self.bot.db.execute("DELETE FROM modhistory WHERE guild_id = ?", (ctx.guild.id,))
            await ctx.send(embed=success_embed("cleared all mod history for this server", ctx.author))

    @commands.command(name="altcheck", aliases=["suscheck"])
    @commands.has_permissions(manage_messages=True)
    async def altcheck(self, ctx, member: discord.Member):
        """analyzes a member for alt account indicators"""
        now = discord.utils.utcnow()
        account_age = now - member.created_at
        join_age = now - member.joined_at if member.joined_at else None
        flags = []
        if account_age.days < 7:
            flags.append("account younger than 7 days")
        if account_age.days < 30:
            flags.append("account younger than 30 days")
        if join_age and join_age.total_seconds() < 3600:
            flags.append("joined less than an hour ago")
        if not member.avatar:
            flags.append("no custom avatar")
        if len([r for r in member.roles if not r.is_default()]) == 0:
            flags.append("no roles assigned")
        verdict = "**suspicious**" if len(flags) >= 3 else ("**possible alt**" if len(flags) >= 1 else "**clean**")
        desc = (
            f"member: {member.mention}\naccount created: <t:{int(member.created_at.timestamp())}:R>\n"
            f"joined: <t:{int(member.joined_at.timestamp())}:R> \n" if member.joined_at else "joined: unknown\n"
        ) + f"indicators: {', '.join(flags) if flags else 'none'}\nverdict: {verdict}"
        await ctx.send(embed=fleed_embed(title="alt check", description=desc, author=ctx.author))

    @commands.command(name="altsweep", aliases=["freshaccounts"])
    @commands.has_permissions(manage_messages=True)
    async def altsweep(self, ctx, max_days: int = 7):
        """lists every member whose account is younger than the given days"""
        cutoff = discord.utils.utcnow() - datetime.timedelta(days=max_days)
        fresh = [m for m in ctx.guild.members if m.created_at > cutoff and not m.bot]
        if not fresh:
            return await ctx.send(embed=fleed_embed(description=f"no members with accounts younger than {max_days} days", author=ctx.author))
        fresh.sort(key=lambda m: m.created_at, reverse=True)
        entries = [f"`{idx:02}` {m.mention} — created <t:{int(m.created_at.timestamp())}:R>" for idx, m in enumerate(fresh, start=1)]
        await send_paginated_embed(ctx, f"fresh accounts ({len(fresh)})", entries, per_page=10, item_name="accounts")

    @commands.command(name="raidcheck")
    @commands.has_permissions(manage_messages=True)
    async def raidcheck(self, ctx):
        """analyzes recent joins to detect a possible raid pattern"""
        now = discord.utils.utcnow()
        members = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at, reverse=True)[:50]
        if not members:
            return await ctx.send(embed=fleed_embed(description="no join data available", author=ctx.author))
        last_hour = sum(1 for m in members if (now - m.joined_at).total_seconds() < 3600)
        fresh_accounts = sum(1 for m in members if (now - m.created_at).days < 7)
        no_avatar = sum(1 for m in members if not m.avatar)
        risk = "high" if last_hour >= 15 and fresh_accounts >= 10 else ("medium" if last_hour >= 8 else "low")
        desc = f"joins in the last hour: **{last_hour}**\nfresh accounts (<7d) among recent joins: **{fresh_accounts}**\nno avatar among recent joins: **{no_avatar}**\nraid risk: **{risk}**"
        await ctx.send(embed=fleed_embed(title="raid check", description=desc, author=ctx.author))

    @commands.command(name="raidcleanup", aliases=["kickunder"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(kick_members=True)
    async def raidcleanup(self, ctx, joined_within_hours: int = 24):
        """kicks members who joined within the given hours and hold no roles (raid cleanup)"""
        now = discord.utils.utcnow()
        cutoff = now - datetime.timedelta(hours=joined_within_hours)
        targets = [m for m in ctx.guild.members if m.joined_at and m.joined_at > cutoff and not [r for r in m.roles if not r.is_default()] and not m.bot and m.top_role < ctx.guild.me.top_role]
        kicked = 0
        for m in targets[:50]:
            try:
                await m.kick(reason=f"raidcleanup by {ctx.author}")
                kicked += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await send_modlog(self.bot, ctx.guild, "raidcleanup", ctx.author, None, f"kicked {kicked} members joined within {joined_within_hours}h")
        await ctx.send(embed=success_embed(f"kicked {kicked}/{len(targets)} raid-join members", ctx.author))

    @commands.command(name="banunder", aliases=["raidban"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(ban_members=True)
    async def banunder(self, ctx, joined_within_hours: int = 24):
        """bans members who joined within the given hours and hold no roles"""
        now = discord.utils.utcnow()
        cutoff = now - datetime.timedelta(hours=joined_within_hours)
        targets = [m for m in ctx.guild.members if m.joined_at and m.joined_at > cutoff and not [r for r in m.roles if not r.is_default()] and not m.bot and m.top_role < ctx.guild.me.top_role]
        banned = 0
        for m in targets[:50]:
            try:
                await m.ban(reason=f"banunder by {ctx.author}", delete_message_days=1)
                banned += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await send_modlog(self.bot, ctx.guild, "banunder", ctx.author, None, f"banned {banned} members joined within {joined_within_hours}h")
        await ctx.send(embed=success_embed(f"banned {banned}/{len(targets)} raid-join members", ctx.author))

    @commands.command(name="joinrate")
    @commands.has_permissions(manage_messages=True)
    async def joinrate(self, ctx):
        """shows how many members joined in the last hour, day and week"""
        now = discord.utils.utcnow()
        members = [m for m in ctx.guild.members if m.joined_at]
        hour = sum(1 for m in members if (now - m.joined_at).total_seconds() < 3600)
        day = sum(1 for m in members if (now - m.joined_at).total_seconds() < 86400)
        week = sum(1 for m in members if (now - m.joined_at).total_seconds() < 604800)
        desc = f"last hour: **{hour}**\nlast 24 hours: **{day}**\nlast 7 days: **{week}**\ntotal members: **{ctx.guild.member_count}**"
        await ctx.send(embed=fleed_embed(title="join rate", description=desc, author=ctx.author))

    @commands.command(name="roleless", aliases=["norole"])
    @commands.has_permissions(manage_messages=True)
    async def roleless(self, ctx):
        """lists every member who has no roles besides @everyone"""
        no_role = [m for m in ctx.guild.members if not m.bot and not [r for r in m.roles if not r.is_default()]]
        if not no_role:
            return await ctx.send(embed=fleed_embed(description="every member has at least one role", author=ctx.author))
        entries = [f"`{idx:02}` {m.mention} (`{m.id}`)" for idx, m in enumerate(no_role, start=1)]
        await send_paginated_embed(ctx, f"roleless members ({len(no_role)})", entries, per_page=10, item_name="members")

    @commands.command(name="pin")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def pin(self, ctx, message_id: str = None):
        """pins a message by id, or the message you reply to"""
        msg = None
        if message_id and message_id.isdigit():
            try:
                msg = await ctx.channel.fetch_message(int(message_id))
            except discord.NotFound:
                return await ctx.send(embed=warn_embed("message not found in this channel", ctx.author))
        elif ctx.message.reference:
            msg = ctx.message.reference.resolved or await ctx.channel.fetch_message(ctx.message.reference.message_id)
        else:
            return await ctx.send(embed=warn_embed("provide a message id or reply to a message", ctx.author))
        try:
            await msg.pin(reason=f"pinned by {ctx.author}")
        except discord.Forbidden:
            return await ctx.send(embed=error_embed("i cannot pin messages here", ctx.author))
        await ctx.send(embed=success_embed(f"pinned [message]({msg.jump_url})", ctx.author))

    @commands.command(name="unpin")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def unpin(self, ctx, message_id: str):
        """unpins a message by id"""
        if not message_id.isdigit():
            return await ctx.send(embed=warn_embed("provide a valid message id", ctx.author))
        for msg in await ctx.channel.pins():
            if msg.id == int(message_id):
                await msg.unpin(reason=f"unpinned by {ctx.author}")
                return await ctx.send(embed=success_embed("unpinned the message", ctx.author))
        await ctx.send(embed=warn_embed("that message is not pinned", ctx.author))

    @commands.command(name="unpinall", aliases=["clearpins"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def unpinall(self, ctx):
        """unpins every message in this channel"""
        pins = await ctx.channel.pins()
        for msg in pins:
            try:
                await msg.unpin(reason=f"unpinall by {ctx.author}")
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"unpinned {len(pins)} messages", ctx.author))

    @commands.command(name="pins")
    async def pins_list(self, ctx):
        """lists pinned messages in this channel"""
        pinned = await ctx.channel.pins()
        if not pinned:
            return await ctx.send(embed=fleed_embed(description="no pinned messages in this channel", author=ctx.author))
        entries = [f"`{idx:02}` [{m.author.name.lower()}]({m.jump_url}): {(m.content or '[attachment/embed]')[:60]}" for idx, m in enumerate(pinned, start=1)]
        await send_paginated_embed(ctx, f"pinned messages ({len(pinned)})", entries, per_page=10, item_name="pins")

    @commands.command(name="archiveallthreads")
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def archiveallthreads(self, ctx, channel: discord.TextChannel = None):
        """archives every active thread in a channel"""
        channel = channel or ctx.channel
        archived = 0
        for thread in channel.threads:
            if not thread.archived:
                try:
                    await thread.edit(archived=True, reason=f"archiveallthreads by {ctx.author}")
                    archived += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
        await ctx.send(embed=success_embed(f"archived {archived} threads in #{channel.name}", ctx.author))

    @commands.command(name="purgethreads")
    @commands.has_permissions(manage_threads=True, manage_channels=True)
    @commands.bot_has_permissions(manage_threads=True, manage_channels=True)
    async def purgethreads(self, ctx, channel: discord.TextChannel = None):
        """deletes every thread in a channel"""
        channel = channel or ctx.channel
        deleted = 0
        for thread in list(channel.threads):
            try:
                await thread.delete(reason=f"purgethreads by {ctx.author}")
                deleted += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"deleted {deleted} threads in #{channel.name}", ctx.author))

    @commands.command(name="nukethis", aliases=["recreate"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def nukethis(self, ctx):
        """deletes and recreates the current channel with identical settings"""
        ch = ctx.channel
        if not isinstance(ch, discord.TextChannel):
            return await ctx.send(embed=warn_embed("this only works in text channels", ctx.author))
        overwrites = ch.overwrites
        new_ch = await ctx.guild.create_text_channel(
            name=ch.name, category=ch.category, position=ch.position, topic=ch.topic,
            slowmode_delay=ch.slowmode_delay, nsfw=ch.nsfw, overwrites=overwrites,
            reason=f"nukethis by {ctx.author}"
        )
        await ch.delete(reason=f"nukethis by {ctx.author}")
        await new_ch.send(embed=success_embed(f"nuked #{ch.name}, this channel is brand new", ctx.author))

    @commands.command(name="categorylock")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def categorylock(self, ctx, category: discord.CategoryChannel):
        """locks every channel inside a category"""
        locked = 0
        for ch in category.channels:
            try:
                await ch.set_permissions(ctx.guild.default_role, send_messages=False, reason=f"categorylock by {ctx.author}")
                locked += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"locked {locked} channels in {category.name}", ctx.author))

    @commands.command(name="categoryunlock")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def categoryunlock(self, ctx, category: discord.CategoryChannel):
        """unlocks every channel inside a category"""
        unlocked = 0
        for ch in category.channels:
            try:
                await ch.set_permissions(ctx.guild.default_role, send_messages=None, reason=f"categoryunlock by {ctx.author}")
                unlocked += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"unlocked {unlocked} channels in {category.name}", ctx.author))

    @commands.command(name="syncall")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def syncall(self, ctx, category: discord.CategoryChannel):
        """syncs permission overwrites of all channels in a category to the category"""
        synced = 0
        for ch in category.channels:
            try:
                await ch.sync_permissions(reason=f"syncall by {ctx.author}")
                synced += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"synced {synced} channels to {category.name}", ctx.author))

    @commands.command(name="overwrites", aliases=["channeloverwrites"])
    @commands.has_permissions(manage_channels=True)
    async def overwrites(self, ctx, channel: discord.abc.GuildChannel = None):
        """shows every permission overwrite set on a channel"""
        channel = channel or ctx.channel
        lines = []
        for target, perms in channel.overwrites.items():
            allowed = [p for p, v in perms if v is True]
            denied = [p for p, v in perms if v is False]
            if not allowed and not denied:
                continue
            lines.append(f"**{target.name}**: allow: {', '.join(allowed) or 'none'} | deny: {', '.join(denied) or 'none'}")
        await ctx.send(embed=fleed_embed(title=f"overwrites for #{channel.name}", description="\n".join(lines) or "no overwrites set", author=ctx.author))

    @commands.command(name="resetchannelperms", aliases=["clearchannelperms"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def resetchannelperms(self, ctx, channel: discord.abc.GuildChannel = None):
        """deletes all permission overwrites on a channel"""
        channel = channel or ctx.channel
        removed = 0
        for target in list(channel.overwrites.keys()):
            try:
                await channel.set_permissions(target, overwrite=None, reason=f"resetchannelperms by {ctx.author}")
                removed += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"removed {removed} overwrites from #{channel.name}", ctx.author))

    @commands.command(name="myperms", aliases=["mypermissions"])
    async def myperms(self, ctx, channel: discord.abc.GuildChannel = None):
        """lists your effective permissions in a channel"""
        channel = channel or ctx.channel
        perms = channel.permissions_for(ctx.author)
        allowed = sorted([p[0].replace('_', ' ') for p in perms if p[1] is True])
        await ctx.send(embed=fleed_embed(title=f"your permissions in #{channel.name}", description=", ".join(allowed), author=ctx.author))

    @commands.command(name="botperms", aliases=["mybotperms"])
    @commands.has_permissions(manage_guild=True)
    async def botperms(self, ctx, channel: discord.abc.GuildChannel = None):
        """lists the bots effective permissions in a channel"""
        channel = channel or ctx.channel
        perms = channel.permissions_for(ctx.guild.me)
        allowed = sorted([p[0].replace('_', ' ') for p in perms if p[1] is True])
        await ctx.send(embed=fleed_embed(title=f"my permissions in #{channel.name}", description=", ".join(allowed), author=ctx.author))

    @commands.command(name="permcompare", aliases=["permsdiff"])
    @commands.has_permissions(manage_roles=True)
    async def permcompare(self, ctx, role1: discord.Role, role2: discord.Role):
        """compres the permissions of two roles and shows the differences"""  # typo guard below (fixed wording)
        p1, p2 = role1.permissions, role2.permissions
        only1 = [p[0].replace('_', ' ') for p in p1 if p[1] and not getattr(p2, p[0])]
        only2 = [p[0].replace('_', ' ') for p in p2 if p[1] and not getattr(p1, p[0])]
        desc = f"**{role1.name}** only: {', '.join(sorted(only1)) or 'none'}\n**{role2.name}** only: {', '.join(sorted(only2)) or 'none'}"
        await ctx.send(embed=fleed_embed(title="permission comparison", description=desc, author=ctx.author))

    @commands.command(name="whohas")
    @commands.has_permissions(manage_messages=True)
    async def whohas(self, ctx, permission: str):
        """lists members who hold a specific permission, example: whohas manage_messages"""
        perm_name = permission.lower().strip()
        valid = [p.name for p in discord.Permissions()]
        matched = next((p for p in valid if p.lower() == perm_name), None)
        if not matched:
            return await ctx.send(embed=warn_embed(f"unknown permission, valid examples: {', '.join(valid[:8])}", ctx.author))
        holders = [m for m in ctx.guild.members if getattr(m.guild_permissions, matched)]
        if not holders:
            return await ctx.send(embed=fleed_embed(description=f"no members hold `{perm_name}`", author=ctx.author))
        entries = [f"`{idx:02}` {m.mention} (`{m.id}`)" for idx, m in enumerate(holders, start=1)]
        await send_paginated_embed(ctx, f"members with {matched.replace('_', ' ')} ({len(holders)})", entries, per_page=10, item_name="members")

    @commands.command(name="adminlist", aliases=["administrators", "listadmins"])
    @commands.has_permissions(manage_messages=True)
    async def adminlist(self, ctx):
        """lists every member who has administrator permissions"""
        admins = [m for m in ctx.guild.members if m.guild_permissions.administrator and not m.bot]
        if not admins:
            return await ctx.send(embed=fleed_embed(description="no administrators found", author=ctx.author))
        entries = [f"`{idx:02}` {m.mention} — **{m.top_role.name}** (`{m.id}`)" for idx, m in enumerate(admins, start=1)]
        await send_paginated_embed(ctx, f"administrators ({len(admins)})", entries, per_page=10, item_name="admins")

    @commands.command(name="invitescan", aliases=["scaninvites"])
    @commands.has_permissions(manage_messages=True)
    async def invitescan(self, ctx, limit: int = 100):
        """scans recent messages for discord invite links"""
        pattern = re.compile(r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)/[a-zA-Z0-9]+")
        found = []
        async for msg in ctx.channel.history(limit=min(limit, 500)):
            if msg.author.bot:
                continue
            hits = pattern.findall(msg.content)
            if hits:
                found.append(f"{msg.author.mention}: [jump to message]({msg.jump_url})")
        if not found:
            return await ctx.send(embed=fleed_embed(description="no invite links found in recent messages", author=ctx.author))
        entries = [f"`{idx:02}` {item}" for idx, item in enumerate(found, start=1)]
        await send_paginated_embed(ctx, f"invite links found ({len(found)})", entries, per_page=10, item_name="invites")

    @commands.command(name="linkscan", aliases=["scanlinks"])
    @commands.has_permissions(manage_messages=True)
    async def linkscan(self, ctx, limit: int = 100):
        """scans recent messages for external links"""
        pattern = re.compile(r"https?://[^\s>]+")
        found = []
        async for msg in ctx.channel.history(limit=min(limit, 500)):
            if msg.author.bot:
                continue
            if pattern.search(msg.content):
                found.append(f"{msg.author.mention}: [jump to message]({msg.jump_url})")
        if not found:
            return await ctx.send(embed=fleed_embed(description="no links found in recent messages", author=ctx.author))
        entries = [f"`{idx:02}` {item}" for idx, item in enumerate(found, start=1)]
        await send_paginated_embed(ctx, f"links found ({len(found)})", entries, per_page=10, item_name="links")

    @commands.command(name="mentiontrain", aliases=["mentionscan"])
    @commands.has_permissions(manage_messages=True)
    async def mentiontrain(self, ctx, limit: int = 100):
        """finds recent messages that mention many members at once"""
        found = []
        async for msg in ctx.channel.history(limit=min(limit, 500)):
            if msg.author.bot:
                continue
            mention_count = len(msg.raw_mentions)
            if mention_count >= 5:
                found.append(f"{msg.author.mention} mentioned **{mention_count}** users: [jump]({msg.jump_url})")
        if not found:
            return await ctx.send(embed=fleed_embed(description="no mass mentions found in recent messages", author=ctx.author))
        entries = [f"`{idx:02}` {item}" for idx, item in enumerate(found, start=1)]
        await send_paginated_embed(ctx, f"mass mentions found ({len(found)})", entries, per_page=10, item_name="mentions")

    @commands.command(name="spamscan")
    @commands.has_permissions(manage_messages=True)
    async def spamscan(self, ctx, limit: int = 100):
        """detects repeated identical messages posted recently in this channel"""
        seen = {}
        async for msg in ctx.channel.history(limit=min(limit, 500)):
            if msg.author.bot or not msg.content:
                continue
            key = (msg.author.id, msg.content.strip().lower())
            seen[key] = seen.get(key, 0) + 1
        repeats = [f"<@{uid}> posted the same message **{count}** times" for (uid, _), count in seen.items() if count >= 3]
        if not repeats:
            return await ctx.send(embed=fleed_embed(description="no spam patterns found in recent messages", author=ctx.author))
        entries = [f"`{idx:02}` {item}" for idx, item in enumerate(repeats, start=1)]
        await send_paginated_embed(ctx, f"spam patterns found ({len(repeats)})", entries, per_page=10, item_name="patterns")

    @commands.command(name="lastmsg", aliases=["latestmessage"])
    @commands.has_permissions(manage_messages=True)
    async def lastmsg(self, ctx, channel: discord.TextChannel = None):
        """fetches the last message sent in a channel"""
        channel = channel or ctx.channel
        try:
            async for msg in channel.history(limit=1):
                desc = f"author: {msg.author.mention}\ncontent: {(msg.content or '[embed/attachment]')[:300]}\nsent: <t:{int(msg.created_at.timestamp())}:R>\n[jump]({msg.jump_url})"
                return await ctx.send(embed=fleed_embed(title=f"last message in #{channel.name}", description=desc, author=ctx.author))
        except discord.Forbidden:
            return await ctx.send(embed=error_embed(f"i cannot read #{channel.name}", ctx.author))
        await ctx.send(embed=warn_embed(f"no messages found in #{channel.name}", ctx.author))

    @commands.command(name="msgcount", aliases=["activitycount"])
    @commands.has_permissions(manage_messages=True)
    async def msgcount(self, ctx, member: discord.Member, limit: int = 500):
        """counts how many of the last messages in this channel belong to a member"""
        count = 0
        async for msg in ctx.channel.history(limit=min(limit, 1000)):
            if msg.author.id == member.id:
                count += 1
        await ctx.send(embed=fleed_embed(description=f"{member.mention} sent **{count}** of the last {min(limit, 1000)} messages here", author=ctx.author))

    @commands.command(name="slowmodeall", aliases=["setslowmodeall"])
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmodeall(self, ctx, seconds: int):
        """sets slowmode on every text channel, 0 disables"""
        seconds = max(0, min(seconds, 21600))
        changed = 0
        for ch in ctx.guild.text_channels:
            try:
                await ch.edit(slowmode_delay=seconds, reason=f"slowmodeall by {ctx.author}")
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"set slowmode to {seconds}s on {changed} channels", ctx.author))

    @commands.command(name="nsfwscan")
    @commands.has_permissions(manage_channels=True)
    async def nsfwscan(self, ctx):
        """lists all channels marked as nsfw"""
        nsfw = [ch.name for ch in ctx.guild.text_channels if ch.nsfw]
        await ctx.send(embed=fleed_embed(title=f"nsfw channels ({len(nsfw)})", description="\n".join(nsfw) or "none", author=ctx.author))

    @commands.command(name="rolesempty", aliases=["checkemptyroles"])
    @commands.has_permissions(manage_roles=True)
    async def emptyroles(self, ctx):
        """lists roles that have no members"""
        empty = [r.name for r in ctx.guild.roles if not r.is_default() and not r.managed and len(r.members) == 0]
        await ctx.send(embed=fleed_embed(title=f"empty roles ({len(empty)})", description="\n".join(empty[:40]) or "none", author=ctx.author))

    @commands.command(name="pruneroles", aliases=["deletemptyroles"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def pruneroles(self, ctx):
        """deletes every empty non-managed role below the bot"""
        deleted = 0
        for r in list(ctx.guild.roles):
            if r.is_default() or r.managed or r >= ctx.guild.me.top_role or len(r.members) > 0:
                continue
            try:
                await r.delete(reason=f"pruneroles by {ctx.author}")
                deleted += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
        await ctx.send(embed=success_embed(f"deleted {deleted} empty roles", ctx.author))

    @commands.command(name="duperoles", aliases=["duplicatedroles"])
    @commands.has_permissions(manage_roles=True)
    async def duperoles(self, ctx):
        """finds roles that share the exact same name"""
        names = {}
        for r in ctx.guild.roles:
            names.setdefault(r.name.lower(), []).append(r)
        dupes = {k: v for k, v in names.items() if len(v) > 1}
        lines = [f"**{k}** x{len(v)} (ids: {', '.join(str(r.id) for r in v)})" for k, v in dupes.items()]
        await ctx.send(embed=fleed_embed(title=f"duplicate role names ({len(dupes)})", description="\n".join(lines[:25]) or "none", author=ctx.author))

    @commands.command(name="sensitiveroles", aliases=["riskyroles"])
    @commands.has_permissions(manage_roles=True)
    async def sensitiveroles(self, ctx):
        """lists roles that hold dangerous permissions"""
        danger = {"administrator", "manage_guild", "manage_roles", "manage_channels", "ban_members", "kick_members", "mention_everyone", "manage_webhooks"}
        lines = []
        for r in sorted(ctx.guild.roles, reverse=True):
            held = [p for p in danger if getattr(r.permissions, p, False)]
            if held:
                lines.append(f"**{r.name}** ({len(r.members)} members): {', '.join(sorted(held).replace('_', ' ') for _ in [0]) if False else ', '.join(h.replace('_', ' ') for h in sorted(held))}")
        await ctx.send(embed=fleed_embed(title="roles with dangerous permissions", description="\n".join(lines[:30]) or "none", author=ctx.author))

    @commands.command(name="verifymember", aliases=["verify"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def verifymember(self, ctx, member: discord.Member, role: discord.Role = None):
        """grants the verification role to a member and logs it"""
        role = role or discord.utils.get(ctx.guild.roles, name="verified")
        if not role:
            return await ctx.send(embed=warn_embed("role not found, create a role named `verified` or pass one", ctx.author))
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed("that role is above my highest role", ctx.author))
        await member.add_roles(role, reason=f"verified by {ctx.author}")
        await send_modlog(self.bot, ctx.guild, "verify", ctx.author, member, "manual verification")
        await ctx.send(embed=success_embed(f"verified {member.mention} with role {role.name}", ctx.author))

    @commands.command(name="unverifymember", aliases=["unverify"])
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unverifymember(self, ctx, member: discord.Member, role: discord.Role = None):
        """removes the verification role from a member"""
        role = role or discord.utils.get(ctx.guild.roles, name="verified")
        if not role or role not in member.roles:
            return await ctx.send(embed=warn_embed("that member does not hold the verification role", ctx.author))
        await member.remove_roles(role, reason=f"unverified by {ctx.author}")
        await send_modlog(self.bot, ctx.guild, "unverify", ctx.author, member, "manual unverification")
        await ctx.send(embed=success_embed(f"unverified {member.mention}", ctx.author))

    @commands.command(name="temprole")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def temprole(self, ctx, member: discord.Member, role: discord.Role, duration: str):
        """gives a member a role and removes it automatically after the duration"""
        seconds = parse_duration(duration)
        if not seconds or seconds <= 0:
            return await ctx.send(embed=warn_embed("invalid duration, example: 2h", ctx.author))
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=error_embed("that role is above my highest role", ctx.author))
        await member.add_roles(role, reason=f"temprole ({duration}) by {ctx.author}")
        asyncio.create_task(self._temprole_expire(ctx.guild.id, member.id, role.id, seconds))
        await send_modlog(self.bot, ctx.guild, "temprole", ctx.author, member, f"{role.name} for {duration}")
        await ctx.send(embed=success_embed(f"given {role.name} to {member.mention} for **{format_remaining(seconds)}**", ctx.author))

    async def _temprole_expire(self, guild_id: int, member_id: int, role_id: int, seconds: int):
        await asyncio.sleep(seconds)
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(member_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.remove_roles(role, reason="temprole expired")
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.command(name="simjoin", aliases=["testjoin"])
    @commands.has_permissions(administrator=True)
    async def simjoin(self, ctx, member: discord.Member = None):
        """simulates a member join event to test welcome configuration"""
        member = member or ctx.author
        self.bot.dispatch("member_join", member)
        await ctx.send(embed=success_embed(f"dispatched fake join event for {member.mention}", ctx.author))

    @commands.command(name="simleave", aliases=["testleave"])
    @commands.has_permissions(administrator=True)
    async def simleave(self, ctx, member: discord.Member = None):
        """simulates a member leave event to test leave configuration"""
        member = member or ctx.author
        self.bot.dispatch("member_remove", member)
        await ctx.send(embed=success_embed(f"dispatched fake leave event for {member.mention}", ctx.author))

    @commands.command(name="mods", aliases=["staffonline"])
    @commands.has_permissions(manage_messages=True)
    async def mods(self, ctx):
        """lists staff members (kick/ban/manage perms) and whether they are online"""
        staff = [m for m in ctx.guild.members if not m.bot and (m.guild_permissions.kick_members or m.guild_permissions.ban_members or m.guild_permissions.manage_guild)]
        if not staff:
            return await ctx.send(embed=fleed_embed(description="no staff members found", author=ctx.author))
        online = [m for m in staff if m.status != discord.Status.offline]
        lines = [f"{m.mention} — {m.status.name}" for m in online[:20]]
        lines.append(f"--- {len(staff) - len(online)} offline staff")
        await ctx.send(embed=fleed_embed(title=f"staff ({len(online)}/{len(staff)} online)", description="\n".join(lines), author=ctx.author))

    @commands.command(name="mutuals", aliases=["sharedservers"])
    async def mutuals(self, ctx, user: discord.User = None):
        """shows servers you share with the bot or another user"""
        user = user or ctx.author
        shared = [g for g in self.bot.guilds if user in g.members] if not user.bot else [g for g in self.bot.guilds if g.get_member(user.id)]
        names = [g.name for g in shared[:30]]
        await ctx.send(embed=fleed_embed(title=f"shared servers with {user.name} ({len(shared)})", description="\n".join(names) or "none", author=ctx.author))

    @commands.command(name="joinedposition", aliases=["joinpos"])
    async def joinedposition(self, ctx, member: discord.Member = None):
        """shows a members position in the server join order"""
        member = member or ctx.author
        if not member.joined_at:
            return await ctx.send(embed=warn_embed("join date unknown for that member", ctx.author))
        joined_sorted = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at)
        pos = joined_sorted.index(member) + 1
        desc = f"{member.mention} is member **#{pos}** of **{len(joined_sorted)}**\njoined <t:{int(member.joined_at.timestamp())}:R>"
        await ctx.send(embed=fleed_embed(title="join position", description=desc, author=ctx.author))

    @commands.command(name="accountage", aliases=["accage"])
    async def accountage(self, ctx, member: discord.Member = None):
        """shows how old a discord account is"""
        member = member or ctx.author
        age = discord.utils.utcnow() - member.created_at
        days = age.days
        desc = f"{member.mention}\naccount created <t:{int(member.created_at.timestamp())}:f>\nage: **{days} days** ({days // 365} years, {(days % 365) // 30} months)"
        await ctx.send(embed=fleed_embed(title="account age", description=desc, author=ctx.author))

    @commands.command(name="newestmembers", aliases=["recentjoins"])
    @commands.has_permissions(manage_messages=True)
    async def newestmembers(self, ctx, count: int = 10):
        """lists the newest members by join date"""
        joined = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at, reverse=True)
        if not joined:
            return await ctx.send(embed=warn_embed("no join data available", ctx.author))
        lines = [f"{m.mention} — <t:{int(m.joined_at.timestamp())}:R>" for m in joined[:max(1, min(count, 25))]]
        await ctx.send(embed=fleed_embed(title="newest members", description="\n".join(lines), author=ctx.author))

    @commands.command(name="oldestmembers", aliases=["firstjoins"])
    @commands.has_permissions(manage_messages=True)
    async def oldestmembers(self, ctx, count: int = 10):
        """lists the longest standing members by join date"""
        joined = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at)
        if not joined:
            return await ctx.send(embed=warn_embed("no join data available", ctx.author))
        lines = [f"{m.mention} — <t:{int(m.joined_at.timestamp())}:R>" for m in joined[:max(1, min(count, 25))]]
        await ctx.send(embed=fleed_embed(title="oldest members", description="\n".join(lines), author=ctx.author))

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not getattr(self, "_joinlock_guilds", None):
            return
        if member.guild.id in self._joinlock_guilds:
            try:
                await member.kick(reason="joinlock active")
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.command(name="joinlock", aliases=["gate"])
    @commands.has_permissions(administrator=True)
    async def joinlock(self, ctx, state: str):
        """enables or disables joinlock which auto-kicks every new join, state: on/off"""
        if not hasattr(self, "_joinlock_guilds"):
            self._joinlock_guilds = set()
        state = state.lower()
        if state in ("on", "enable", "true", "yes", "1"):
            self._joinlock_guilds.add(ctx.guild.id)
            await send_modlog(self.bot, ctx.guild, "joinlock", ctx.author, None, "joinlock enabled")
            await ctx.send(embed=success_embed("joinlock enabled, new joins will be kicked", ctx.author))
        elif state in ("off", "disable", "false", "no", "0"):
            self._joinlock_guilds.discard(ctx.guild.id)
            await send_modlog(self.bot, ctx.guild, "joinlock", ctx.author, None, "joinlock disabled")
            await ctx.send(embed=success_embed("joinlock disabled", ctx.author))
        else:
            await ctx.send(embed=warn_embed("usage: joinlock on | off", ctx.author))

class ClearServerConfirmView(discord.ui.View):
    def __init__(self, bot, author: discord.Member):
        super().__init__(timeout=30)
        self.bot = bot
        self.author = author

    @discord.ui.button(label="confirm", style=discord.ButtonStyle.danger, custom_id="clearserver_confirm")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message(embed=error_embed("you cannot interact with this confirmation", interaction.user), ephemeral=True)

        guild = interaction.guild
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=fleed_embed(description="wiping server... please wait", author=self.author), view=self)

        # 1. Create fallback text channel
        fallback_ch = None
        try:
            fallback_ch = await guild.create_text_channel(name="general", reason="clearserver: fallback channel")
        except Exception:
            fallback_ch = interaction.channel

        # 2. Delete all other channels and categories
        for ch in list(guild.channels):
            if fallback_ch and ch.id == fallback_ch.id:
                continue
            try:
                await ch.delete(reason="clearserver: owner wipe")
                await asyncio.sleep(0.1)
            except Exception:
                pass

        # 3. Delete custom roles (below bot's highest role, non-managed, non-@everyone)
        bot_top = guild.me.top_role
        for role in list(guild.roles):
            if role.is_default() or role.managed or role >= bot_top:
                continue
            try:
                await role.delete(reason="clearserver: owner wipe")
                await asyncio.sleep(0.1)
            except Exception:
                pass

        # 4. Delete custom emojis & stickers
        for emoji in list(guild.emojis):
            try:
                await emoji.delete(reason="clearserver: owner wipe")
            except Exception:
                pass
        for sticker in list(guild.stickers):
            try:
                await sticker.delete(reason="clearserver: owner wipe")
            except Exception:
                pass

        # 5. Clear Database configurations
        tables = [
            "guild_settings", "voicemaster_config", "welcome_config", "leave_config",
            "starboard_config", "confessions_config", "level_config", "autorole_config",
            "logging_config", "antinuke_config", "antiraid_config", "filter_words",
            "filter_regex", "antiraid_patterns", "reaction_roles", "sticky_messages",
            "timers", "autoresponders", "autoreactions", "pingonjoin", "vanity_roles",
            "badge_roles", "fakepermissions"
        ]
        for tbl in tables:
            try:
                await self.bot.db.execute(f"DELETE FROM {tbl} WHERE guild_id = ?", (guild.id,))
            except Exception:
                pass

        # 6. Post success in new fallback channel
        if fallback_ch:
            try:
                await fallback_ch.send(embed=success_embed(f"successfully cleared all channels, roles, and settings for **{guild.name.lower()}**", self.author))
            except Exception:
                pass

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.secondary, custom_id="clearserver_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message(embed=error_embed("you cannot interact with this confirmation", interaction.user), ephemeral=True)

        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=fleed_embed(description="cancelled clear server operation", author=self.author), view=self)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
