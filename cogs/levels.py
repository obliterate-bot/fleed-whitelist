import discord
from discord.ext import commands, tasks
import random
import time
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help, send_paginated_embed


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        self.voice_states = {}
        self.voice_xp_loop.start()

    async def cog_load(self):
        try:
            await self.bot.db.execute("ALTER TABLE level_config ADD COLUMN channel_id INTEGER")
        except Exception:
            pass
        try:
            await self.bot.db.execute("ALTER TABLE level_config ADD COLUMN stack_roles INTEGER DEFAULT 1")
        except Exception:
            pass

    def cog_unload(self):
        self.voice_xp_loop.cancel()

    def get_xp_for_level(self, level: int) -> int:
        if level <= 0:
            return 0
        return int(100 * (level ** 1.5))

    async def get_level_data(self, guild_id: int, user_id: int):
        row = await self.bot.db.fetchrow("SELECT xp, level FROM levels WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        if not row:
            await self.bot.db.execute("INSERT OR IGNORE INTO levels (guild_id, user_id, xp, level) VALUES (?, ?, 0, 0)", (guild_id, user_id))
            return 0, 0
        return row["xp"], row["level"]

    @tasks.loop(minutes=1)
    async def voice_xp_loop(self):
        for guild in self.bot.guilds:
            cfg = await self.bot.db.fetchrow("SELECT rate FROM level_config WHERE guild_id = ?", (guild.id,))
            rate = cfg["rate"] if cfg and cfg["rate"] else 1.0
            for vc in guild.voice_channels:
                members = [m for m in vc.members if not m.bot and not m.voice.self_deaf and not m.voice.deaf]
                if len(members) >= 2:
                    for m in members:
                        xp_gain = int(random.randint(5, 10) * rate)
                        xp, level = await self.get_level_data(guild.id, m.id)
                        new_xp = xp + xp_gain
                        new_level = level
                        while new_xp >= self.get_xp_for_level(new_level + 1):
                            new_level += 1
                        await self.bot.db.execute("UPDATE levels SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?", (new_xp, new_level, guild.id, m.id))

    async def send_rank_card(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        xp, lvl = await self.get_level_data(ctx.guild.id, target.id)
        next_xp = self.get_xp_for_level(lvl + 1)
        curr_lvl_xp = self.get_xp_for_level(lvl)

        rel_xp = max(0, xp - curr_lvl_xp)
        rel_next_xp = max(1, next_xp - curr_lvl_xp)

        # Calculate rank position in server
        rows = await self.bot.db.fetch("SELECT user_id FROM levels WHERE guild_id = ? ORDER BY xp DESC", (ctx.guild.id,))
        rank_pos = 1
        for idx, r in enumerate(rows, 1):
            if r["user_id"] == target.id:
                rank_pos = idx
                break

        progress = max(0.0, min(1.0, rel_xp / max(1, rel_next_xp)))
        pct = f"{progress * 100:.1f}%"

        color = target.color if target.color.value != 0 else 0x2B2D31

        desc = (
            f"level: **{lvl}**\n"
            f"xp: **{rel_xp:,}** / **{rel_next_xp:,}** ({pct})\n"
            f"total xp: **{xp:,}**\n"
            f"rank: **#{rank_pos}**"
        )

        embed = discord.Embed(
            description=desc,
            color=color
        )
        embed.set_author(name=f"{target.name.lower()} ({target.id})", icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot or message.content.startswith((",", "/", "!")):
            return

        user_key = f"{message.guild.id}_{message.author.id}"
        now = time.time()
        if user_key in self.cooldowns and now - self.cooldowns[user_key] < 60:
            return
        self.cooldowns[user_key] = now

        cfg = await self.bot.db.fetchrow("SELECT rate, message, stack_roles, channel_id FROM level_config WHERE guild_id = ?", (message.guild.id,))
        rate = cfg["rate"] if cfg and cfg["rate"] else 1.0

        xp_gain = int(random.randint(15, 25) * rate)
        xp, level = await self.get_level_data(message.guild.id, message.author.id)
        new_xp = xp + xp_gain
        new_level = level

        while new_xp >= self.get_xp_for_level(new_level + 1):
            new_level += 1

        await self.bot.db.execute("UPDATE levels SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?", (new_xp, new_level, message.guild.id, message.author.id))

        if new_level > level:
            # check role rewards
            role_row = await self.bot.db.fetchrow("SELECT role_id FROM level_roles WHERE guild_id = ? AND rank = ?", (message.guild.id, new_level))
            if role_row:
                reward_role = message.guild.get_role(role_row["role_id"])
                if reward_role and reward_role not in message.author.roles:
                    try:
                        await message.author.add_roles(reward_role, reason="level reward")
                    except Exception:
                        pass

            # Determine where to send levelup message
            target_channel = message.channel
            if cfg and cfg["channel_id"] is not None:
                if cfg["channel_id"] == -1:
                    target_channel = None  # Disabled
                else:
                    designated_ch = message.guild.get_channel(cfg["channel_id"])
                    if designated_ch:
                        target_channel = designated_ch

            if target_channel:
                custom_msg = cfg["message"] if cfg and cfg["message"] else "{user} reached level {level}"
                formatted = custom_msg.replace("{user}", message.author.mention).replace("{level}", str(new_level)).lower()
                try:
                    await target_channel.send(embed=fleed_embed(title="level up", description=formatted, author=message.author))
                except Exception:
                    pass

    async def _send_leaderboard(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id, level, xp FROM levels WHERE guild_id = ? ORDER BY xp DESC", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed("no leveling data available", ctx.author))
        entries = []
        for i, r in enumerate(rows, 1):
            u = self.bot.get_user(r["user_id"])
            tag = u.name.lower() if u else f"user_{r['user_id']}"
            entries.append(f"`{i:02}` **{tag}** — lvl {r['level']} ({r['xp']:,} xp)")
        await send_paginated_embed(ctx, f"level leaderboard ({len(rows)})", entries, per_page=10, item_name="users")

    async def _send_roles(self, ctx):
        rows = await self.bot.db.fetch("SELECT rank, role_id FROM level_roles WHERE guild_id = ? ORDER BY rank", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed("no level role rewards set", ctx.author))
        entries = [f"lvl {r['rank']} -> <@&{r['role_id']}>" for r in rows]
        await send_paginated_embed(ctx, f"level rewards ({len(rows)})", entries, per_page=10, item_name="rewards")

    async def _set_channel(self, ctx, channel: str = None):
        if channel is None:
            cfg = await self.bot.db.fetchrow("SELECT channel_id FROM level_config WHERE guild_id = ?", (ctx.guild.id,))
            if not cfg or cfg["channel_id"] is None:
                return await ctx.send(embed=fleed_embed(title="level channel", description="level up messages are currently sent in the **current channel**", author=ctx.author))
            elif cfg["channel_id"] == -1:
                return await ctx.send(embed=fleed_embed(title="level channel", description="level up messages are currently **disabled**", author=ctx.author))
            else:
                ch = ctx.guild.get_channel(cfg["channel_id"])
                ch_name = ch.mention if ch else f"`#{cfg['channel_id']}`"
                return await ctx.send(embed=fleed_embed(title="level channel", description=f"level up messages are currently sent to {ch_name}", author=ctx.author))

        lower_c = channel.lower().strip()
        if lower_c in ["none", "remove", "clear", "default", "current"]:
            await self.bot.db.execute("INSERT INTO level_config (guild_id, channel_id) VALUES (?, NULL) ON CONFLICT(guild_id) DO UPDATE SET channel_id = NULL", (ctx.guild.id,))
            return await ctx.send(embed=success_embed("reset level up messages to send in the **current channel**", ctx.author))
        elif lower_c in ["off", "disable", "disabled", "none_messages"]:
            await self.bot.db.execute("INSERT INTO level_config (guild_id, channel_id) VALUES (?, -1) ON CONFLICT(guild_id) DO UPDATE SET channel_id = -1", (ctx.guild.id,))
            return await ctx.send(embed=success_embed("disabled level up notification messages", ctx.author))

        target_ch = None
        clean_id = lower_c.replace("<#", "").replace(">", "").strip()
        if clean_id.isdigit():
            target_ch = ctx.guild.get_channel(int(clean_id))
        if not target_ch:
            target_ch = discord.utils.find(lambda c: c.name.lower() == lower_c or c.name.lower() == lower_c.lstrip("#"), ctx.guild.text_channels)

        if not target_ch:
            return await ctx.send(embed=error_embed(f"could not find channel `{channel}`", ctx.author))

        await self.bot.db.execute("INSERT INTO level_config (guild_id, channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?", (ctx.guild.id, target_ch.id, target_ch.id))
        await ctx.send(embed=success_embed(f"set level up notifications channel to {target_ch.mention}", ctx.author))

    @commands.command(name="rank", aliases=["card", "rankcard", "levelcard"])
    async def rank_cmd(self, ctx, member: discord.Member = None):
        """view your server level and xp in a clean embed"""
        await self.send_rank_card(ctx, member)

    @commands.group(name="level", aliases=["lvl"], invoke_without_command=True)
    async def level_group(self, ctx, member: discord.Member = None):
        await self.send_rank_card(ctx, member)

    @level_group.command(name="channel")
    @commands.has_permissions(administrator=True)
    async def level_channel_sub(self, ctx, *, channel: str = None):
        await self._set_channel(ctx, channel=channel)

    @commands.command(name="levelupchannel", aliases=["setlevelupchannel"])
    @commands.has_permissions(administrator=True)
    async def direct_levelupchannel(self, ctx, *, channel: str = None):
        await self._set_channel(ctx, channel=channel)

    @level_group.command(name="leaderboard", aliases=["lb", "top"])
    async def level_leaderboard_sub(self, ctx):
        await self._send_leaderboard(ctx)

    @commands.command(name="leaderboard", aliases=["lb", "top"])
    async def direct_leaderboard(self, ctx):
        await self._send_leaderboard(ctx)

    @level_group.command(name="roles")
    async def level_roles_sub(self, ctx):
        await self._send_roles(ctx)

    @commands.command(name="levelroles", aliases=["lroles"])
    async def direct_levelroles(self, ctx):
        await self._send_roles(ctx)

    @level_group.command(name="add")
    @commands.has_permissions(administrator=True)
    async def level_add(self, ctx, rank: int, role: discord.Role):
        await self.bot.db.execute("INSERT OR REPLACE INTO level_roles (guild_id, rank, role_id) VALUES (?, ?, ?)", (ctx.guild.id, rank, role.id))
        await ctx.send(embed=success_embed(f"added reward {role.mention} for level {rank}", ctx.author))

    @level_group.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def level_remove(self, ctx, rank: int):
        await self.bot.db.execute("DELETE FROM level_roles WHERE guild_id = ? AND rank = ?", (ctx.guild.id, rank))
        await ctx.send(embed=success_embed(f"removed reward for level {rank}", ctx.author))

    @level_group.command(name="setrate")
    @commands.has_permissions(administrator=True)
    async def level_setrate(self, ctx, multiplier: float):
        await self.bot.db.execute("INSERT INTO level_config (guild_id, rate) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET rate = ?", (ctx.guild.id, multiplier, multiplier))
        await ctx.send(embed=success_embed(f"set xp multiplier to `{multiplier}x`", ctx.author))

    @level_group.command(name="message")
    @commands.has_permissions(administrator=True)
    async def level_set_message(self, ctx, *, message: str):
        await self.bot.db.execute("INSERT INTO level_config (guild_id, message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET message = ?", (ctx.guild.id, message, message))
        await ctx.send(embed=success_embed("updated level up message", ctx.author))

    @level_group.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def level_reset_user(self, ctx, member: discord.Member):
        await self.bot.db.execute("DELETE FROM levels WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"reset levels and xp for {member.mention}", ctx.author))

    @level_group.command(name="setlevel")
    @commands.has_permissions(administrator=True)
    async def level_set_lvl(self, ctx, member: discord.Member, new_level: int):
        if new_level < 0:
            return await ctx.send(embed=warn_embed("level must be >= 0", ctx.author))
        new_xp = int(100 * (new_level ** 1.5))
        await self.bot.db.execute("INSERT OR REPLACE INTO levels (guild_id, user_id, level, xp) VALUES (?, ?, ?, ?)", (ctx.guild.id, member.id, new_level, new_xp))
        await ctx.send(embed=success_embed(f"set {member.mention}'s level to `{new_level}` ({new_xp:,} xp)", ctx.author))

    @commands.command(name="setlevel")
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, target: discord.Member, level: int):
        await self.level_set_lvl(ctx, target, level)

    @level_group.command(name="setxp")
    @commands.has_permissions(administrator=True)
    async def level_set_xp_cmd(self, ctx, member: discord.Member, new_xp: int):
        if new_xp < 0:
            return await ctx.send(embed=warn_embed("xp must be >= 0", ctx.author))
        calc_lvl = int((new_xp / 100) ** (1 / 1.5))
        await self.bot.db.execute("INSERT OR REPLACE INTO levels (guild_id, user_id, level, xp) VALUES (?, ?, ?, ?)", (ctx.guild.id, member.id, calc_lvl, new_xp))
        await ctx.send(embed=success_embed(f"set {member.mention}'s xp to `{new_xp:,}` (level {calc_lvl})", ctx.author))

    @commands.command(name="setxp")
    @commands.has_permissions(administrator=True)
    async def setxp(self, ctx, target: discord.Member, amount: int):
        await self.level_set_xp_cmd(ctx, target, amount)

    @commands.command(name="removexp")
    @commands.has_permissions(administrator=True)
    async def removexp(self, ctx, target: discord.Member, amount: int):
        await self.bot.db.execute("UPDATE levels SET xp = MAX(0, xp - ?) WHERE guild_id = ? AND user_id = ?", (amount, ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"removed {amount:,} xp from {target.mention}", ctx.author))

    @level_group.command(name="givexp", aliases=["addxp"])
    @commands.has_permissions(administrator=True)
    async def level_give_xp(self, ctx, member: discord.Member, amount: int):
        row = await self.bot.db.fetchrow("SELECT level, xp FROM levels WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        curr_xp = row["xp"] if row else 0
        new_xp = max(0, curr_xp + amount)
        calc_lvl = int((new_xp / 100) ** (1 / 1.5))
        await self.bot.db.execute("INSERT OR REPLACE INTO levels (guild_id, user_id, level, xp) VALUES (?, ?, ?, ?)", (ctx.guild.id, member.id, calc_lvl, new_xp))
        await ctx.send(embed=success_embed(f"granted `{amount:,}` xp to {member.mention} (total: {new_xp:,} xp, level {calc_lvl})", ctx.author))

    @level_group.command(name="stackroles", aliases=["stack"])
    @commands.has_permissions(administrator=True)
    async def level_stack_roles(self, ctx, state: bool):
        val = 1 if state else 0
        await self.bot.db.execute("INSERT INTO level_config (guild_id, stack_roles) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET stack_roles = ?", (ctx.guild.id, val, val))
        msg = "enabled (members keep all previous level roles)" if state else "disabled (members only keep their highest level role)"
        await ctx.send(embed=success_embed(f"role reward stacking {msg}", ctx.author))

    @level_group.command(name="resetall", aliases=["clearall"])
    @commands.has_permissions(administrator=True)
    async def level_reset_all(self, ctx):
        await self.bot.db.execute("DELETE FROM levels WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset all levels and xp for this server", ctx.author))

async def setup(bot):
    await bot.add_cog(Levels(bot))

