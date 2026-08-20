import discord
from discord.ext import commands, tasks
import asyncio
import json
import random
import time
import aiohttp
import io
from PIL import Image
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help

class Server(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.autopfp_worker.start()

    def cog_unload(self):
        self.autopfp_worker.cancel()

    def _counter_value(self, guild, metric):
        return {
            "members": guild.member_count,
            "humans": sum(not m.bot for m in guild.members),
            "bots": sum(m.bot for m in guild.members),
            "channels": len(guild.channels),
            "roles": max(0, len(guild.roles) - 1),
            "boosts": guild.premium_subscription_count or 0,
        }.get(metric)

    async def _refresh_counters(self, guild):
        rows = await self.bot.db.fetch("SELECT channel_id, metric FROM server_counters WHERE guild_id = ?", (guild.id,))
        for row in rows:
            channel = guild.get_channel(row["channel_id"])
            value = self._counter_value(guild, row["metric"])
            if not channel or value is None:
                continue
            name = f"{row['metric']}: {value}"
            if channel.name != name:
                try:
                    await channel.edit(name=name, reason="automatic server counter refresh")
                except discord.HTTPException:
                    pass

    @tasks.loop(minutes=1)
    async def autopfp_worker(self):
        now = int(time.time())
        rows = await self.bot.db.fetch("SELECT guild_id, channel_id, interval_minutes, last_posted FROM autopfp_config")
        for row in rows:
            if now - int(row["last_posted"] or 0) < max(5, int(row["interval_minutes"] or 60)) * 60:
                continue
            guild = self.bot.get_guild(row["guild_id"])
            channel = guild.get_channel(row["channel_id"]) if guild else None
            members = [m for m in guild.members if not m.bot and m.display_avatar] if guild else []
            if not channel or not members:
                continue
            member = random.choice(members)
            embed = fleed_embed(title=f"{member.display_name.lower()}'s avatar", author=member)
            embed.set_image(url=member.display_avatar.url)
            try:
                await channel.send(embed=embed)
                await self.bot.db.execute("UPDATE autopfp_config SET last_posted = ? WHERE channel_id = ?", (now, channel.id))
            except discord.HTTPException:
                pass

    @autopfp_worker.before_loop
    async def before_autopfp_worker(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self._refresh_counters(member.guild)
        await self._send_greeting(member, "welcome_config")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self._refresh_counters(member.guild)
        await self._send_greeting(member, "leave_config")

    @staticmethod
    def _render_greeting(template: str, member) -> str:
        guild = member.guild
        values = {
            "{user}": str(member),
            "{user.mention}": member.mention,
            "{user.name}": member.name,
            "{user.display_name}": member.display_name,
            "{user.id}": str(member.id),
            "{user.avatar}": member.display_avatar.url,
            "{guild.name}": guild.name,
            "{guild.id}": str(guild.id),
            "{guild.count}": str(guild.member_count or len(guild.members)),
            "{guild.boosts}": str(guild.premium_subscription_count or 0),
        }
        rendered = template or ""
        for key, value in values.items():
            rendered = rendered.replace(key, value)
        return rendered[:2000]

    @staticmethod
    async def _get_pfp_color(member) -> discord.Color:
        try:
            avatar_bytes = await member.display_avatar.replace(size=64, format="png").read()
            img = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
            img = img.resize((1, 1), Image.Resampling.LANCZOS)
            r, g, b = img.getpixel((0, 0))
            return discord.Color.from_rgb(r, g, b)
        except Exception:
            if hasattr(member, "color") and member.color != discord.Color.default():
                return member.color
            return discord.Color(0x2b2d31)

    async def _build_welcome_embed(self, member, custom_template: str = None) -> discord.Embed:
        guild = member.guild
        color = await self._get_pfp_color(member)
        count = guild.member_count or len(guild.members)
        
        if custom_template:
            rendered = self._render_greeting(custom_template, member).lower()
        else:
            rendered = f"welcome {member.mention} to {guild.name.lower()}\nyou are our {count:,}th member"

        embed = discord.Embed(
            title=f"welcome to {guild.name.lower()}",
            description=rendered,
            color=color
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="account created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="member count", value=f"{count:,}", inline=True)
        embed.set_footer(text=f"user id: {member.id} • member #{count:,}")
        return embed

    async def _send_greeting(self, member, table: str):
        row = await self.bot.db.fetchrow(
            f"SELECT channel_id, message FROM {table} WHERE guild_id = ?", (member.guild.id,)
        )
        if not row or not row["channel_id"]:
            return
        channel = member.guild.get_channel(row["channel_id"])
        if not channel or not channel.permissions_for(member.guild.me).send_messages:
            return

        if table == "welcome_config":
            embed = await self._build_welcome_embed(member, row["message"])
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass
        else:
            default = "goodbye {user.mention}"
            content = self._render_greeting(row["message"] or default, member).lower()
            if content:
                try:
                    await channel.send(content)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self._refresh_counters(channel.guild)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self.bot.db.execute("DELETE FROM server_counters WHERE channel_id = ?", (channel.id,))
        await self.bot.db.execute("DELETE FROM autopfp_config WHERE channel_id = ?", (channel.id,))
        await self._refresh_counters(channel.guild)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self._refresh_counters(role.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self._refresh_counters(role.guild)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.premium_since is None and after.premium_since is not None:
            row = await self.bot.db.fetchrow("SELECT channel_id, message FROM boost_config WHERE guild_id = ?", (after.guild.id,))
            channel = after.guild.get_channel(row["channel_id"]) if row and row["channel_id"] else None
            if channel:
                template = row["message"] or "thank you {user} for boosting {guild.name}!"
                text = template.replace("{user}", after.mention).replace("{guild.name}", after.guild.name)
                await channel.send(text[:2000], allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        if before.premium_since != after.premium_since:
            await self._refresh_counters(after.guild)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == getattr(self.bot.user, "id", None) or not payload.guild_id:
            return
        emoji = str(payload.emoji)
        if emoji in {"◀️", "▶️"}:
            rows = await self.bot.db.fetch(
                "SELECT channel_id, page_number, content, current_page FROM pagination_pages WHERE guild_id = ? AND message_id = ? ORDER BY page_number",
                (payload.guild_id, payload.message_id),
            )
            if rows:
                current = int(rows[0]["current_page"] or 1)
                current = current - 1 if emoji == "◀️" else current + 1
                current = ((current - 1) % len(rows)) + 1
                row = rows[current - 1]
                channel = self.bot.get_channel(row["channel_id"])
                if channel:
                    try:
                        message = await channel.fetch_message(payload.message_id)
                        await message.edit(embed=fleed_embed(title=f"page {current}/{len(rows)}", description=row["content"]))
                        await self.bot.db.execute("UPDATE pagination_pages SET current_page = ? WHERE guild_id = ? AND message_id = ?", (current, payload.guild_id, payload.message_id))
                        user = self.bot.get_user(payload.user_id)
                        if user:
                            await message.remove_reaction(payload.emoji, user)
                    except discord.HTTPException:
                        pass

        starboard = await self.bot.db.fetchrow("SELECT channel_id, threshold, color FROM starboards WHERE guild_id = ? AND emoji = ?", (payload.guild_id, emoji))
        if not starboard:
            return
        ignored = await self.bot.db.fetchrow("SELECT 1 FROM starboard_ignored WHERE guild_id = ? AND channel_id = ?", (payload.guild_id, payload.channel_id))
        if ignored:
            return
        source = self.bot.get_channel(payload.channel_id)
        board = self.bot.get_channel(starboard["channel_id"])
        if not source or not board:
            return
        try:
            message = await source.fetch_message(payload.message_id)
            reaction = discord.utils.find(lambda r: str(r.emoji) == emoji, message.reactions)
            if not reaction or reaction.count < starboard["threshold"]:
                return
            embed = fleed_embed(description=message.content[:3500] or "(attachment or embed)", author=message.author)
            embed.color = starboard["color"] or 0xFEE75C
            embed.add_field(name="source", value=f"[jump to message]({message.jump_url}) • {emoji} {reaction.count}", inline=False)
            if message.attachments and message.attachments[0].content_type and message.attachments[0].content_type.startswith("image/"):
                embed.set_image(url=message.attachments[0].url)
            existing = await self.bot.db.fetchrow("SELECT board_message_id FROM starboard_posts WHERE guild_id = ? AND source_message_id = ? AND emoji = ?", (payload.guild_id, payload.message_id, emoji))
            if existing:
                board_message = await board.fetch_message(existing["board_message_id"])
                await board_message.edit(embed=embed)
            else:
                board_message = await board.send(embed=embed)
                await self.bot.db.execute("INSERT INTO starboard_posts (guild_id, source_message_id, board_message_id, emoji) VALUES (?, ?, ?, ?)", (payload.guild_id, payload.message_id, board_message.id, emoji))
        except discord.HTTPException:
            pass

    # pagination
    @commands.group(name="pagination", invoke_without_command=True)
    async def pagination(self, ctx):
        await send_group_help(ctx, ctx.command)

    @pagination.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def pagination_add(self, ctx, message_id: int, *, script: str):
        try:
            await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            return await ctx.send(embed=error_embed("that message does not exist in this channel", ctx.author))
        rows = await self.bot.db.fetch("SELECT page_number FROM pagination_pages WHERE guild_id = ? AND message_id = ?", (ctx.guild.id, message_id))
        page = len(rows) + 1
        await self.bot.db.execute("INSERT INTO pagination_pages (guild_id, channel_id, message_id, page_number, content) VALUES (?, ?, ?, ?, ?)", (ctx.guild.id, ctx.channel.id, message_id, page, script[:4000]))
        await ctx.send(embed=success_embed(f"added page {page} to message {message_id}", ctx.author))

    @pagination.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def pagination_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT message_id, channel_id, COUNT(*) AS pages FROM pagination_pages WHERE guild_id = ? GROUP BY message_id, channel_id", (ctx.guild.id,))
        lines = [f"`{r['message_id']}` in <#{r['channel_id']}> — {r['pages']} pages" for r in rows]
        await ctx.send(embed=fleed_embed(title="pagination embeds", description="\n".join(lines) or "none configured", author=ctx.author))

    @pagination.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def pagination_set(self, ctx, message_id: int):
        rows = await self.bot.db.fetch("SELECT page_number, content FROM pagination_pages WHERE guild_id = ? AND message_id = ? ORDER BY page_number", (ctx.guild.id, message_id))
        if not rows:
            return await ctx.send(embed=error_embed("add at least one page before activating pagination", ctx.author))
        message = await ctx.channel.fetch_message(message_id)
        await message.edit(embed=fleed_embed(title=f"page 1/{len(rows)}", description=rows[0]["content"]))
        await message.add_reaction("◀️"); await message.add_reaction("▶️")
        await ctx.send(embed=success_embed(f"activated pagination for message {message_id}", ctx.author))

    @pagination.command(name="delete", aliases=["remove"])
    @commands.has_permissions(manage_guild=True)
    async def pagination_delete(self, ctx, message_id: int):
        await self.bot.db.execute("DELETE FROM pagination_pages WHERE guild_id = ? AND message_id = ?", (ctx.guild.id, message_id))
        await ctx.send(embed=success_embed(f"deleted pagination for message {message_id}", ctx.author))

    @pagination.command(name="restorereactions")
    @commands.has_permissions(manage_guild=True)
    async def pagination_restorereactions(self, ctx, message_id: int):
        message = await ctx.channel.fetch_message(message_id)
        await message.add_reaction("◀️"); await message.add_reaction("▶️")
        await ctx.send(embed=success_embed(f"restored reactions for pagination message {message_id}", ctx.author))

    # confessions
    @commands.hybrid_group(name="confessions", invoke_without_command=True)
    async def confessions(self, ctx):
        await send_group_help(ctx, ctx.command)

    @confessions.command(name="add", aliases=["set"])
    @commands.has_permissions(manage_guild=True)
    async def confessions_add(self, ctx, channel: discord.TextChannel):
        await self.bot.db.execute(
            "INSERT INTO confessions_config (guild_id, channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?",
            (ctx.guild.id, channel.id, channel.id),
        )
        await ctx.send(embed=success_embed(f"set confessions channel to {channel.mention}", ctx.author))

    @confessions.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def confessions_remove(self, ctx):
        await self.bot.db.execute("DELETE FROM confessions_config WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("removed confessions channel", ctx.author))

    @confessions.command(name="config")
    @commands.has_permissions(manage_guild=True)
    async def confessions_config(self, ctx):
        row = await self.bot.db.fetchrow("SELECT channel_id, upvote, downvote FROM confessions_config WHERE guild_id = ?", (ctx.guild.id,))
        channel = f"<#{row['channel_id']}>" if row and row["channel_id"] else "none"
        upvote = row["upvote"] if row else "⬆️"; downvote = row["downvote"] if row else "⬇️"
        muted = await self.bot.db.fetch("SELECT user_id FROM confession_muted WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(title="confessions config", description=f"channel: {channel}\nemojis: {upvote} / {downvote}\nmuted users: {len(muted)}", author=ctx.author))

    @confessions.command(name="mute")
    @commands.has_permissions(manage_messages=True)
    async def confessions_mute(self, ctx, number: int):
        entry = await self.bot.db.fetchrow("SELECT author_id FROM confession_entries WHERE guild_id = ? AND confession_number = ?", (ctx.guild.id, number))
        if not entry:
            return await ctx.send(embed=error_embed(f"confession #{number} was not found", ctx.author))
        await self.bot.db.execute("INSERT OR IGNORE INTO confession_muted (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, entry["author_id"]))
        await ctx.send(embed=success_embed(f"muted author of confession #{number}", ctx.author))

    @confessions.command(name="unmute")
    @commands.has_permissions(manage_messages=True)
    async def confessions_unmute(self, ctx, number: int):
        entry = await self.bot.db.fetchrow("SELECT author_id FROM confession_entries WHERE guild_id = ? AND confession_number = ?", (ctx.guild.id, number))
        if not entry:
            return await ctx.send(embed=error_embed(f"confession #{number} was not found", ctx.author))
        await self.bot.db.execute("DELETE FROM confession_muted WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, entry["author_id"]))
        await ctx.send(embed=success_embed(f"unmuted author of confession #{number}", ctx.author))

    @confessions.group(name="emojis", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def confessions_emojis(self, ctx):
        await send_group_help(ctx, ctx.command)

    @confessions_emojis.command(name="set")
    async def confessions_emojis_set(self, ctx, upvote: str, downvote: str):
        await self.bot.db.execute(
            "INSERT INTO confessions_config (guild_id, upvote, downvote) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET upvote = ?, downvote = ?",
            (ctx.guild.id, upvote, downvote, upvote, downvote),
        )
        await ctx.send(embed=success_embed(f"set confession reactions to `{upvote}` and `{downvote}`", ctx.author))

    @confessions_emojis.command(name="reset")
    async def confessions_emojis_reset(self, ctx):
        await self.bot.db.execute("UPDATE confessions_config SET upvote = '⬆️', downvote = '⬇️' WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset confession reactions", ctx.author))

    @confessions_emojis.command(name="view")
    async def confessions_emojis_view(self, ctx):
        row = await self.bot.db.fetchrow("SELECT upvote, downvote FROM confessions_config WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(title="confessions emojis", description=f"upvote: {row['upvote'] if row else '⬆️'}\ndownvote: {row['downvote'] if row else '⬇️'}", author=ctx.author))

    @confessions.group(name="blacklist", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def confessions_blacklist(self, ctx):
        await send_group_help(ctx, ctx.command)

    @confessions_blacklist.command(name="add")
    async def confessions_blacklist_add(self, ctx, word: str):
        await self.bot.db.execute("INSERT OR IGNORE INTO confession_blacklist (guild_id, word) VALUES (?, ?)", (ctx.guild.id, word.lower()))
        await ctx.send(embed=success_embed(f"blacklisted word `{word.lower()}` from confessions", ctx.author))

    @confessions_blacklist.command(name="remove")
    async def confessions_blacklist_remove(self, ctx, word: str):
        await self.bot.db.execute("DELETE FROM confession_blacklist WHERE guild_id = ? AND word = ?", (ctx.guild.id, word.lower()))
        await ctx.send(embed=success_embed(f"removed word `{word.lower()}` from confessions blacklist", ctx.author))

    @confessions_blacklist.command(name="list")
    async def confessions_blacklist_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT word FROM confession_blacklist WHERE guild_id = ? ORDER BY word", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(title="confessions blacklisted words", description=", ".join(f"`{r['word']}`" for r in rows) or "none", author=ctx.author))

    @confessions_blacklist.command(name="clear")
    async def confessions_blacklist_clear(self, ctx):
        await self.bot.db.execute("DELETE FROM confession_blacklist WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("cleared confessions blacklist", ctx.author))

    @commands.command(name="confess", aliases=["confession"])
    @commands.guild_only()
    async def confess_submit(self, ctx, *, confession: str):
        row = await self.bot.db.fetchrow("SELECT channel_id, upvote, downvote FROM confessions_config WHERE guild_id = ?", (ctx.guild.id,))
        if not row or not row["channel_id"]:
            return await ctx.send(embed=error_embed("confessions are not configured in this server", ctx.author), delete_after=8)
        if await self.bot.db.fetchrow("SELECT 1 FROM confession_muted WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id)):
            return await ctx.send(embed=error_embed("you are muted from sending confessions", ctx.author), delete_after=8)
        blocked = await self.bot.db.fetch("SELECT word FROM confession_blacklist WHERE guild_id = ?", (ctx.guild.id,))
        lowered = confession.lower()
        if any(r["word"] in lowered for r in blocked):
            return await ctx.send(embed=error_embed("that confession contains a blocked word", ctx.author), delete_after=8)
        channel = ctx.guild.get_channel(row["channel_id"])
        if not channel:
            return await ctx.send(embed=error_embed("the configured confessions channel no longer exists", ctx.author))
        previous = await self.bot.db.fetchrow("SELECT MAX(confession_number) AS maximum FROM confession_entries WHERE guild_id = ?", (ctx.guild.id,))
        number = int(previous["maximum"] or 0) + 1
        message = await channel.send(embed=fleed_embed(title=f"confession #{number}", description=confession[:4000]))
        for emoji in (row["upvote"] or "⬆️", row["downvote"] or "⬇️"):
            try: await message.add_reaction(emoji)
            except discord.HTTPException: pass
        await self.bot.db.execute("INSERT INTO confession_entries (guild_id, confession_number, author_id, message_id, created_at) VALUES (?, ?, ?, ?, ?)", (ctx.guild.id, number, ctx.author.id, message.id, int(time.time())))
        try: await ctx.message.delete()
        except discord.HTTPException: pass
        try: await ctx.author.send(embed=success_embed(f"posted confession #{number}", ctx.author))
        except discord.HTTPException: pass

    # counter
    @commands.group(name="counter", invoke_without_command=True)
    @commands.has_permissions(manage_channels=True)
    async def counter(self, ctx):
        await send_group_help(ctx, ctx.command)

    @counter.command(name="options", aliases=["events"])
    async def counter_options(self, ctx):
        await ctx.send(embed=fleed_embed(title="counter options", description="metrics: members, humans, bots, channels, roles, boosts\nkinds: voice, text, stage", author=ctx.author))

    @counter.command(name="add")
    async def counter_add(self, ctx, metric_raw: str, kind_raw: str):
        metric = metric_raw.lower(); kind = kind_raw.lower()
        value = self._counter_value(ctx.guild, metric)
        if value is None:
            return await ctx.send(embed=error_embed("metric must be members, humans, bots, channels, roles, or boosts", ctx.author))
        name = f"{metric}: {value}"
        if kind == "voice": channel = await ctx.guild.create_voice_channel(name, reason=f"counter created by {ctx.author}")
        elif kind == "text": channel = await ctx.guild.create_text_channel(name, reason=f"counter created by {ctx.author}")
        elif kind == "stage": channel = await ctx.guild.create_stage_channel(name, reason=f"counter created by {ctx.author}")
        else: return await ctx.send(embed=error_embed("kind must be voice, text, or stage", ctx.author))
        await self.bot.db.execute("INSERT INTO server_counters (guild_id, channel_id, metric, channel_kind) VALUES (?, ?, ?, ?)", (ctx.guild.id, channel.id, metric, kind))
        await ctx.send(embed=success_embed(f"created {metric} counter {channel.mention}", ctx.author))

    @counter.command(name="remove", aliases=["delete", "del"])
    async def counter_remove(self, ctx, channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel):
        await self.bot.db.execute("DELETE FROM server_counters WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, channel.id))
        await channel.delete(reason=f"counter removed by {ctx.author}")
        await ctx.send(embed=success_embed(f"removed counter from {channel.name.lower()}", ctx.author))



    # customize
    @commands.hybrid_group(name="customize", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def customize(self, ctx):
        await send_group_help(ctx, ctx.command)

    @customize.command(name="avatar")
    async def customize_avatar(self, ctx, url: str = None):
        await ctx.send(embed=error_embed("Discord bot avatars are global, not server-specific; use the Developer Portal to change it safely", ctx.author))

    @customize.command(name="banner")
    async def customize_banner(self, ctx, url: str = None):
        await ctx.send(embed=error_embed("Discord bot banners are global, not server-specific; use the Developer Portal to change it safely", ctx.author))

    @customize.command(name="bio")
    async def customize_bio(self, ctx, *, bio: str = None):
        await ctx.send(embed=error_embed("Discord bot bios are global, not server-specific; use the Developer Portal to change it safely", ctx.author))

    @customize.command(name="name")
    async def customize_name(self, ctx, *, name: str):
        await ctx.guild.me.edit(nick=name)
        await ctx.send(embed=success_embed(f"updated bot nickname to `{name.lower()}`", ctx.author))

    @customize.command(name="reset")
    async def customize_reset(self, ctx):
        await ctx.guild.me.edit(nick=None)
        await ctx.send(embed=success_embed("reset bot appearance in this server", ctx.author))

    # welcome & leave
    @commands.hybrid_group(name="welcome", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx):
        await send_group_help(ctx, ctx.command)

    @welcome.command(name="setup")
    async def welcome_setup(self, ctx, channel: discord.TextChannel = None):
        ch = channel
        if not ch:
            existing = discord.utils.get(ctx.guild.text_channels, name="welcome")
            if existing:
                ch = existing
            else:
                leave_row = await self.bot.db.fetchrow("SELECT channel_id FROM leave_config WHERE guild_id = ?", (ctx.guild.id,))
                target_cat = None
                if leave_row and leave_row["channel_id"]:
                    leave_ch = ctx.guild.get_channel(leave_row["channel_id"])
                    if leave_ch:
                        target_cat = leave_ch.category
                if not target_cat:
                    target_cat = discord.utils.get(ctx.guild.categories, name="information")
                
                try:
                    ch = await ctx.guild.create_text_channel(
                        name="welcome",
                        category=target_cat,
                        reason=f"welcome setup by {ctx.author}"
                    )
                except Exception:
                    ch = ctx.channel

        await self.bot.db.execute("INSERT INTO welcome_config (guild_id, channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?", (ctx.guild.id, ch.id, ch.id))
        await ctx.send(embed=success_embed(f"welcome messages enabled in {ch.mention}", ctx.author))

    @welcome.command(name="channel", aliases=["ch"])
    async def welcome_channel(self, ctx, channel: discord.TextChannel):
        await self.welcome_setup(ctx, channel)

    @welcome.command(name="message", aliases=["msg"])
    async def welcome_message(self, ctx, *, template: str):
        await self.bot.db.execute("INSERT INTO welcome_config (guild_id, message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET message = ?", (ctx.guild.id, template, template))
        await ctx.send(embed=success_embed("updated welcome message template", ctx.author))

    @welcome.command(name="view")
    async def welcome_view(self, ctx):
        row = await self.bot.db.fetchrow("SELECT message FROM welcome_config WHERE guild_id = ?", (ctx.guild.id,))
        msg = row["message"] if row and row["message"] else "welcome {user} to {guild.name}"
        await ctx.send(embed=fleed_embed(title="welcome template", description=msg, author=ctx.author))

    @welcome.command(name="test", aliases=["preview"])
    async def welcome_test(self, ctx):
        row = await self.bot.db.fetchrow("SELECT message FROM welcome_config WHERE guild_id = ?", (ctx.guild.id,))
        template = row["message"] if row else None
        embed = await self._build_welcome_embed(ctx.author, template)
        await ctx.send(embed=embed)

    @welcome.command(name="reset", aliases=["remove", "delete"])
    async def welcome_reset(self, ctx):
        await self.bot.db.execute("DELETE FROM welcome_config WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("removed welcome message configuration", ctx.author))

    @commands.hybrid_group(name="leave", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def leave(self, ctx):
        await send_group_help(ctx, ctx.command)

    @leave.command(name="setup")
    async def leave_setup(self, ctx, channel: discord.TextChannel = None):
        ch = channel
        if not ch:
            existing = (
                discord.utils.get(ctx.guild.text_channels, name="goodbye")
                or discord.utils.get(ctx.guild.text_channels, name="leave")
            )
            if existing:
                ch = existing
            else:
                welcome_row = await self.bot.db.fetchrow("SELECT channel_id FROM welcome_config WHERE guild_id = ?", (ctx.guild.id,))
                target_cat = None
                if welcome_row and welcome_row["channel_id"]:
                    welcome_ch = ctx.guild.get_channel(welcome_row["channel_id"])
                    if welcome_ch:
                        target_cat = welcome_ch.category
                if not target_cat:
                    target_cat = discord.utils.get(ctx.guild.categories, name="information")
                
                try:
                    ch = await ctx.guild.create_text_channel(
                        name="goodbye",
                        category=target_cat,
                        reason=f"leave setup by {ctx.author}"
                    )
                except Exception:
                    ch = ctx.channel

        await self.bot.db.execute("INSERT INTO leave_config (guild_id, channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?", (ctx.guild.id, ch.id, ch.id))
        await ctx.send(embed=success_embed(f"leave messages enabled in {ch.mention}", ctx.author))

    @leave.command(name="channel", aliases=["ch"])
    async def leave_channel(self, ctx, channel: discord.TextChannel):
        await self.leave_setup(ctx, channel)

    @leave.command(name="message", aliases=["msg"])
    async def leave_message(self, ctx, *, template: str):
        await self.bot.db.execute("INSERT INTO leave_config (guild_id, message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET message = ?", (ctx.guild.id, template, template))
        await ctx.send(embed=success_embed("updated leave message template", ctx.author))

    @leave.command(name="view")
    async def leave_view(self, ctx):
        row = await self.bot.db.fetchrow("SELECT message FROM leave_config WHERE guild_id = ?", (ctx.guild.id,))
        msg = row["message"] if row and row["message"] else "goodbye {user}"
        await ctx.send(embed=fleed_embed(title="leave template", description=msg, author=ctx.author))

    @leave.command(name="test", aliases=["preview"])
    async def leave_test(self, ctx):
        row = await self.bot.db.fetchrow("SELECT message FROM leave_config WHERE guild_id = ?", (ctx.guild.id,))
        template = (row["message"] if row else None) or "goodbye {user.mention}"
        await ctx.send(embed=fleed_embed(title="leave preview", description=self._render_greeting(template, ctx.author), author=ctx.author))

    @leave.command(name="reset", aliases=["remove", "delete"])
    async def leave_reset(self, ctx):
        await self.bot.db.execute("DELETE FROM leave_config WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("removed leave configuration", ctx.author))

    # boosterrole
    @commands.hybrid_group(name="boosterrole", invoke_without_command=True)
    async def boosterrole(self, ctx):
        await send_group_help(ctx, ctx.command)

    @boosterrole.command(name="setup", aliases=["enable"])
    @commands.has_permissions(manage_roles=True)
    async def boosterrole_setup(self, ctx):
        await self.bot.db.execute("INSERT INTO booster_config (guild_id, enabled) VALUES (?, 1) ON CONFLICT(guild_id) DO UPDATE SET enabled = 1", (ctx.guild.id,))
        await ctx.send(embed=success_embed("enabled booster role system", ctx.author))

    @boosterrole.command(name="disable", aliases=["reset"])
    @commands.has_permissions(manage_roles=True)
    async def boosterrole_disable(self, ctx):
        await self.bot.db.execute("UPDATE booster_config SET enabled = 0 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("disabled booster role system", ctx.author))

    @boosterrole.command(name="base", aliases=["baserole"])
    @commands.has_permissions(manage_roles=True)
    async def boosterrole_base(self, ctx, role: discord.Role = None):
        r_id = role.id if role else 0
        await self.bot.db.execute("UPDATE booster_config SET base_role = ? WHERE guild_id = ?", (r_id, ctx.guild.id))
        await ctx.send(embed=success_embed(f"set booster base role to {role.name if role else 'none'}", ctx.author))

    @boosterrole.command(name="limit")
    @commands.has_permissions(manage_roles=True)
    async def boosterrole_limit(self, ctx, limit: int):
        await self.bot.db.execute("UPDATE booster_config SET limit_count = ? WHERE guild_id = ?", (min(249, limit), ctx.guild.id))
        await ctx.send(embed=success_embed(f"set booster role limit to {min(249, limit)}", ctx.author))

    @boosterrole.command(name="hoist")
    @commands.has_permissions(manage_roles=True)
    async def boosterrole_hoist(self, ctx, state: str):
        val = 1 if state.lower() in ["on", "true", "1"] else 0
        await self.bot.db.execute("UPDATE booster_config SET hoist = ? WHERE guild_id = ?", (val, ctx.guild.id))
        await ctx.send(embed=success_embed(f"set booster role hoist to {val == 1}", ctx.author))

    @boosterrole.command(name="create", aliases=["make"])
    async def boosterrole_create(self, ctx, *, name_and_colors: str):
        filters = await self.bot.db.fetch("SELECT word FROM booster_filters WHERE guild_id = ?", (ctx.guild.id,))
        if any(r["word"] in name_and_colors.lower() for r in filters):
            return await ctx.send(embed=error_embed("that role name contains a filtered word", ctx.author))
        existing = await self.bot.db.fetchrow("SELECT role_id FROM booster_roles WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        if existing:
            return await ctx.send(embed=error_embed("you already have a custom booster role", ctx.author))
        if not ctx.author.premium_since:
            return await ctx.send(embed=error_embed("you must be actively boosting this server", ctx.author))
        role = await ctx.guild.create_role(name=name_and_colors)
        await ctx.author.add_roles(role)
        await self.bot.db.execute("INSERT OR REPLACE INTO booster_roles (guild_id, user_id, role_id) VALUES (?, ?, ?)", (ctx.guild.id, ctx.author.id, role.id))
        await ctx.send(embed=success_embed(f"created custom booster role {role.mention}", ctx.author, role=role))

    @boosterrole.command(name="delete", aliases=["remove", "del", "rm"])
    async def boosterrole_delete(self, ctx):
        row = await self.bot.db.fetchrow("SELECT role_id FROM booster_roles WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        if not row:
            return await ctx.send(embed=error_embed("you do not have a custom booster role", ctx.author))
        role = ctx.guild.get_role(row["role_id"])
        if role:
            await role.delete()
        await self.bot.db.execute("DELETE FROM booster_roles WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        await ctx.send(embed=success_embed("deleted your booster role", ctx.author, role=role))

    @boosterrole.command(name="rename", aliases=["name"])
    async def boosterrole_rename(self, ctx, *, name: str):
        row = await self.bot.db.fetchrow("SELECT role_id FROM booster_roles WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        if not row:
            return await ctx.send(embed=error_embed("you do not have a custom booster role", ctx.author))
        role = ctx.guild.get_role(row["role_id"])
        if role:
            await role.edit(name=name)
        await ctx.send(embed=success_embed(f"renamed booster role to `{name.lower()}`", ctx.author, role=role))

    @boosterrole.command(name="color", aliases=["colour"])
    async def boosterrole_color(self, ctx, colors: str):
        row = await self.bot.db.fetchrow("SELECT role_id FROM booster_roles WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        if not row:
            return await ctx.send(embed=error_embed("you do not have a custom booster role", ctx.author))
        role = ctx.guild.get_role(row["role_id"])
        if role:
            col = int(colors.replace("#", ""), 16)
            await role.edit(color=discord.Color(col))
        await ctx.send(embed=success_embed(f"changed booster role color to `{colors.lower()}`", ctx.author, role=role))

    @boosterrole.command(name="icon", aliases=["icn"])
    async def boosterrole_icon(self, ctx, icon_input: str = None):
        row = await self.bot.db.fetchrow("SELECT role_id FROM booster_roles WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        role = ctx.guild.get_role(row["role_id"]) if row else None
        if not role:
            return await ctx.send(embed=error_embed("you do not have a custom booster role", ctx.author))
        source = icon_input or (ctx.message.attachments[0].url if ctx.message.attachments else None)
        try:
            if not source or source.lower() in {"remove", "reset", "none"}:
                await role.edit(display_icon=None, reason=f"booster role icon removed by {ctx.author}")
            else:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                    async with session.get(source) as response:
                        if response.status != 200:
                            raise RuntimeError(f"image returned HTTP {response.status}")
                        icon_bytes = await response.read()
                if len(icon_bytes) > 256 * 1024:
                    return await ctx.send(embed=error_embed("role icon must be under 256 KB", ctx.author))
                await role.edit(display_icon=icon_bytes, reason=f"booster role icon changed by {ctx.author}")
            await ctx.send(embed=success_embed("updated booster role icon", ctx.author, role=role))
        except Exception as exc:
            await ctx.send(embed=error_embed(f"could not update role icon: {str(exc)[:250]}", ctx.author))

    @boosterrole.command(name="sync")
    @commands.has_permissions(manage_roles=True)
    async def boosterrole_sync(self, ctx):
        config_row = await self.bot.db.fetchrow("SELECT base_role FROM booster_config WHERE guild_id = ?", (ctx.guild.id,))
        base = ctx.guild.get_role(config_row["base_role"]) if config_row and config_row["base_role"] else ctx.guild.premium_subscriber_role
        if not base:
            return await ctx.send(embed=error_embed("configure a booster base role first", ctx.author))
        rows = await self.bot.db.fetch("SELECT role_id FROM booster_roles WHERE guild_id = ?", (ctx.guild.id,))
        roles = [ctx.guild.get_role(r["role_id"]) for r in rows]
        roles = [r for r in roles if r and r < ctx.guild.me.top_role]
        moved = 0
        for offset, role in enumerate(roles, 1):
            try:
                await role.edit(position=min(ctx.guild.me.top_role.position - 1, base.position + offset), reason=f"booster role sync by {ctx.author}")
                moved += 1
            except discord.HTTPException:
                pass
        await ctx.send(embed=success_embed(f"synced {moved} booster role positions", ctx.author))

    @boosterrole.command(name="include", aliases=["bypass"])
    @commands.has_permissions(manage_roles=True)
    async def boosterrole_include(self, ctx, role: discord.Role, member: discord.Member):
        owner_row = await self.bot.db.fetchrow("SELECT user_id FROM booster_roles WHERE guild_id = ? AND role_id = ?", (ctx.guild.id, role.id))
        if not owner_row:
            return await ctx.send(embed=error_embed("that is not a managed booster role", ctx.author))
        await member.add_roles(role, reason=f"booster role share approved by {ctx.author}")
        await self.bot.db.execute("INSERT OR IGNORE INTO booster_shares (guild_id, owner_id, user_id) VALUES (?, ?, ?)", (ctx.guild.id, owner_row["user_id"], member.id))
        await ctx.send(embed=success_embed(f"included {member.mention} with {role.name}", ctx.author, role=role))

    @boosterrole.command(name="list", aliases=["all"])
    async def boosterrole_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id, role_id FROM booster_roles WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no booster roles in this server", author=ctx.author))
        lines = [f"<@{r['user_id']}> -> <@&{r['role_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="booster roles", description="\n".join(lines), author=ctx.author))

    @boosterrole.group(name="filter", invoke_without_command=True)
    async def boosterrole_filter(self, ctx):
        await send_group_help(ctx, ctx.command)

    @boosterrole_filter.command(name="add")
    async def boosterrole_filter_add(self, ctx, word: str):
        await self.bot.db.execute("INSERT OR IGNORE INTO booster_filters (guild_id, word) VALUES (?, ?)", (ctx.guild.id, word.lower()))
        await ctx.send(embed=success_embed(f"added `{word.lower()}` to booster role name filter", ctx.author))

    @boosterrole_filter.command(name="remove", aliases=["delete", "del"])
    async def boosterrole_filter_remove(self, ctx, word: str):
        await self.bot.db.execute("DELETE FROM booster_filters WHERE guild_id = ? AND word = ?", (ctx.guild.id, word.lower()))
        await ctx.send(embed=success_embed(f"removed `{word.lower()}` from booster role filter", ctx.author))

    @boosterrole_filter.command(name="list", aliases=["all"])
    async def boosterrole_filter_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT word FROM booster_filters WHERE guild_id = ? ORDER BY word", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(title="booster role filtered words", description=", ".join(f"`{r['word']}`" for r in rows) or "none", author=ctx.author))

    @boosterrole.group(name="shares", invoke_without_command=True)
    async def boosterrole_shares(self, ctx):
        await send_group_help(ctx, ctx.command)

    @boosterrole_shares.command(name="list")
    async def boosterrole_shares_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id FROM booster_shares WHERE guild_id = ? AND owner_id = ?", (ctx.guild.id, ctx.author.id))
        users = [f"<@{r['user_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="shared booster role with", description="\n".join(users) or "none", author=ctx.author))

    @boosterrole_shares.command(name="max")
    @commands.has_permissions(manage_guild=True)
    async def boosterrole_shares_max(self, ctx, max_shares: int):
        await self.bot.db.execute("UPDATE booster_config SET max_shares = ? WHERE guild_id = ?", (max_shares, ctx.guild.id))
        await ctx.send(embed=success_embed(f"set max booster role shares to {max_shares}", ctx.author))

    @boosterrole_shares.command(name="remove")
    async def boosterrole_shares_remove(self, ctx, member: discord.Member):
        await self.bot.db.execute("DELETE FROM booster_shares WHERE guild_id = ? AND owner_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id, member.id))
        await ctx.send(embed=success_embed(f"removed {member.mention} from your booster role shares", ctx.author))

    @boosterrole.group(name="share", invoke_without_command=True)
    async def boosterrole_share(self, ctx):
        await send_group_help(ctx, ctx.command, "server")

    @boosterrole_share.command(name="leave")
    async def boosterrole_share_leave(self, ctx, owner: discord.Member):
        await self.bot.db.execute("DELETE FROM booster_shares WHERE guild_id = ? AND owner_id = ? AND user_id = ?", (ctx.guild.id, owner.id, ctx.author.id))
        await ctx.send(embed=success_embed(f"stopped using {owner.mention}'s shared booster role", ctx.author))

    # prefix
    @commands.hybrid_group(name="prefix", invoke_without_command=True)
    async def prefix(self, ctx):
        await send_group_help(ctx, ctx.command)

    @prefix.command(name="set")
    @commands.has_permissions(administrator=True)
    async def prefix_set(self, ctx, prefix_str: str):
        await self.bot.db.execute("INSERT INTO guild_settings (guild_id, prefix) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET prefix = ?", (ctx.guild.id, prefix_str, prefix_str))
        await ctx.send(embed=success_embed(f"server prefix set to `{prefix_str}`", ctx.author))

    @prefix.command(name="remove", aliases=["reset"])
    @commands.has_permissions(administrator=True)
    async def prefix_remove(self, ctx):
        await self.bot.db.execute("UPDATE guild_settings SET prefix = NULL WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset server prefix to default `,`", ctx.author))

    @prefix.command(name="self")
    @commands.has_permissions(manage_guild=True)
    async def prefix_self(self, ctx, prefix_str: str = None):
        await self.bot.db.execute("INSERT INTO user_settings (user_id, prefix) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET prefix = ?", (ctx.author.id, prefix_str, prefix_str))
        await ctx.send(embed=success_embed(f"personal prefix set to `{prefix_str or 'default'}`", ctx.author))

    # autopfp
    @commands.hybrid_group(name="autopfp", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def autopfp(self, ctx):
        await send_group_help(ctx, ctx.command)

    @autopfp.command(name="setup")
    async def autopfp_setup(self, ctx):
        await self.bot.db.execute("INSERT OR REPLACE INTO autopfp_config (guild_id, channel_id, interval_minutes, last_posted) VALUES (?, ?, COALESCE((SELECT interval_minutes FROM autopfp_config WHERE channel_id = ?), 60), 0)", (ctx.guild.id, ctx.channel.id, ctx.channel.id))
        await ctx.send(embed=success_embed(f"configured autopfp in {ctx.channel.mention}", ctx.author))

    @autopfp.command(name="remove")
    async def autopfp_remove(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        await self.bot.db.execute("DELETE FROM autopfp_config WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"removed autopfp from {target.mention}", ctx.author))

    @autopfp.command(name="list")
    async def autopfp_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT channel_id, interval_minutes FROM autopfp_config WHERE guild_id = ?", (ctx.guild.id,))
        lines = [f"<#{r['channel_id']}> — every {r['interval_minutes']} minutes" for r in rows]
        await ctx.send(embed=fleed_embed(title="autopfp channels", description="\n".join(lines) or "none", author=ctx.author))

    @autopfp.command(name="test")
    async def autopfp_test(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        members = [m for m in ctx.guild.members if not m.bot and m.display_avatar]
        if not members:
            return await ctx.send(embed=error_embed("no eligible members were found", ctx.author))
        member = random.choice(members)
        embed = fleed_embed(title=f"{member.display_name.lower()}'s avatar", author=member); embed.set_image(url=member.display_avatar.url)
        await target.send(embed=embed)
        await ctx.send(embed=success_embed(f"posted a test profile picture in {target.mention}", ctx.author))

    @autopfp.command(name="interval")
    async def autopfp_interval(self, ctx, channel: discord.TextChannel, interval: int):
        interval = max(5, min(interval, 10080))
        changed = await self.bot.db.fetchrow("SELECT 1 FROM autopfp_config WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, channel.id))
        if not changed:
            return await ctx.send(embed=error_embed("run `autopfp setup` in that channel first", ctx.author))
        await self.bot.db.execute("UPDATE autopfp_config SET interval_minutes = ? WHERE guild_id = ? AND channel_id = ?", (interval, ctx.guild.id, channel.id))
        await ctx.send(embed=success_embed(f"set autopfp interval for {channel.mention} to {interval}m", ctx.author))

    # alias
    @commands.hybrid_group(name="alias", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def alias_cmd(self, ctx):
        await send_group_help(ctx, ctx.command)

    @alias_cmd.command(name="add")
    async def alias_add(self, ctx, *, args: str):
        parts = args.strip().split(maxsplit=1)
        if len(parts) != 2:
            return await ctx.send(embed=error_embed("use `alias add <shortcut> <command>`", ctx.author))
        shortcut, command_text = parts[0].lower(), parts[1].strip()
        if self.bot.get_command(shortcut):
            return await ctx.send(embed=error_embed(f"`{shortcut}` is already a registered command or alias", ctx.author))
        if not self.bot.get_command(command_text.split()[0]):
            return await ctx.send(embed=error_embed(f"target command `{command_text.split()[0]}` does not exist", ctx.author))
        await self.bot.db.execute("INSERT OR REPLACE INTO custom_aliases (guild_id, shortcut, command_text) VALUES (?, ?, ?)", (ctx.guild.id, shortcut, command_text))
        await ctx.send(embed=success_embed(f"added alias `{shortcut}` → `{command_text.lower()}`", ctx.author))

    @alias_cmd.command(name="remove")
    async def alias_remove(self, ctx, shortcut: str = None):
        if not shortcut:
            return await send_group_help(ctx, ctx.command.parent, "server")
        await self.bot.db.execute("DELETE FROM custom_aliases WHERE guild_id = ? AND shortcut = ?", (ctx.guild.id, shortcut.lower()))
        await ctx.send(embed=success_embed(f"removed alias `{shortcut.lower()}`", ctx.author))

    @alias_cmd.command(name="removeall")
    async def alias_removeall(self, ctx, command: str = None):
        if command:
            await self.bot.db.execute("DELETE FROM custom_aliases WHERE guild_id = ? AND (command_text = ? OR command_text LIKE ?)", (ctx.guild.id, command.lower(), command.lower() + " %"))
        else:
            await self.bot.db.execute("DELETE FROM custom_aliases WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed(f"removed aliases for `{command.lower() if command else 'all commands'}`", ctx.author))

    @alias_cmd.command(name="reset")
    async def alias_reset(self, ctx):
        await self.bot.db.execute("DELETE FROM custom_aliases WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset all custom aliases", ctx.author))

    @alias_cmd.command(name="list")
    async def alias_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT shortcut, command_text FROM custom_aliases WHERE guild_id = ? ORDER BY shortcut", (ctx.guild.id,))
        lines = [f"`{r['shortcut']}` → `{r['command_text']}`" for r in rows]
        await ctx.send(embed=fleed_embed(title="server command aliases", description="\n".join(lines) or "none", author=ctx.author))

    # starboard
    @commands.group(name="starboard", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def starboard(self, ctx):
        await send_group_help(ctx, ctx.command)

    @starboard.command(name="add", aliases=["create"])
    async def starboard_add(self, ctx, channel: discord.TextChannel, emoji: str, threshold: int = 3):
        await self.bot.db.execute("INSERT OR REPLACE INTO starboards (guild_id, channel_id, emoji, threshold) VALUES (?, ?, ?, ?)", (ctx.guild.id, channel.id, emoji, threshold))
        await ctx.send(embed=success_embed(f"starboard created in {channel.mention} with {emoji} (min: {threshold})", ctx.author))

    @starboard.command(name="remove", aliases=["delete", "del", "rm"])
    async def starboard_remove(self, ctx, emoji: str):
        await self.bot.db.execute("DELETE FROM starboards WHERE guild_id = ? AND emoji = ?", (ctx.guild.id, emoji))
        await ctx.send(embed=success_embed(f"removed starboard for {emoji}", ctx.author))

    @starboard.command(name="list", aliases=["show", "all"])
    async def starboard_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT channel_id, emoji, threshold FROM starboards WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no starboards configured", author=ctx.author))
        lines = [f"{r['emoji']} -> <#{r['channel_id']}> (threshold: {r['threshold']})" for r in rows]
        await ctx.send(embed=fleed_embed(title="starboards", description="\n".join(lines), author=ctx.author))

    @starboard.command(name="move", aliases=["update", "channel"])
    async def starboard_move(self, ctx, emoji: str, channel: discord.TextChannel):
        await self.bot.db.execute("UPDATE starboards SET channel_id = ? WHERE guild_id = ? AND emoji = ?", (channel.id, ctx.guild.id, emoji))
        await ctx.send(embed=success_embed(f"moved starboard {emoji} to {channel.mention}", ctx.author))

    @starboard.command(name="color")
    async def starboard_color(self, ctx, emoji: str, color: str):
        col = int(color.replace("#", ""), 16)
        await self.bot.db.execute("UPDATE starboards SET color = ? WHERE guild_id = ? AND emoji = ?", (col, ctx.guild.id, emoji))
        await ctx.send(embed=success_embed(f"set starboard color for {emoji} to `{color.lower()}`", ctx.author))

    @starboard.command(name="ignore")
    async def starboard_ignore(self, ctx, target: discord.TextChannel):
        await self.bot.db.execute("INSERT OR IGNORE INTO starboard_ignored (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"ignored {target.mention} from starboard", ctx.author))

    @starboard.command(name="unignore")
    async def starboard_unignore(self, ctx, target: discord.TextChannel):
        await self.bot.db.execute("DELETE FROM starboard_ignored WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, target.id))
        await ctx.send(embed=success_embed(f"unignored {target.mention} from starboard", ctx.author))

    # backup
    @commands.group(name="backup", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def backup(self, ctx):
        await send_group_help(ctx, ctx.command)

    @backup.command(name="create")
    async def backup_create(self, ctx, name: str, *, description: str = "none"):
        backup_id = f"bk_{ctx.guild.id}_{int(time.time())}"
        settings = await self.bot.db.fetchrow("SELECT * FROM guild_settings WHERE guild_id = ?", (ctx.guild.id,))
        snapshot = {
            "version": 1,
            "guild": {"name": ctx.guild.name, "id": ctx.guild.id},
            "roles": [
                {
                    "name": role.name,
                    "color": role.color.value,
                    "permissions": role.permissions.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "position": role.position,
                }
                for role in ctx.guild.roles
                if not role.is_default() and not role.managed
            ],
            "channels": [
                {
                    "name": channel.name,
                    "type": str(channel.type),
                    "category": channel.category.name if getattr(channel, "category", None) else None,
                    "position": channel.position,
                    "topic": getattr(channel, "topic", None),
                    "nsfw": getattr(channel, "nsfw", False),
                    "slowmode": getattr(channel, "slowmode_delay", 0),
                    "bitrate": getattr(channel, "bitrate", None),
                    "user_limit": getattr(channel, "user_limit", None),
                }
                for channel in ctx.guild.channels
            ],
            "guild_settings": dict(settings) if settings else None,
        }
        await self.bot.db.execute(
            "INSERT INTO server_backups (guild_id, backup_id, name, description, snapshot_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (ctx.guild.id, backup_id, name, description, json.dumps(snapshot), int(time.time())),
        )
        await ctx.send(embed=success_embed(f"created backup `{backup_id}` ({name.lower()})", ctx.author))

    @backup.command(name="restore")
    async def backup_restore(self, ctx, backup_id: str, mode: str = "all"):
        row = await self.bot.db.fetchrow("SELECT snapshot_json FROM server_backups WHERE guild_id = ? AND backup_id = ?", (ctx.guild.id, backup_id))
        if not row:
            return await ctx.send(embed=error_embed(f"backup `{backup_id}` was not found", ctx.author))
        mode = mode.lower()
        if mode not in {"all", "roles", "channels", "settings"}:
            return await ctx.send(embed=error_embed("mode must be all, roles, channels, or settings", ctx.author))
        snapshot = json.loads(row["snapshot_json"])
        created_roles = created_channels = 0
        if mode in {"all", "roles"}:
            existing = {role.name.lower() for role in ctx.guild.roles}
            for item in sorted(snapshot.get("roles", []), key=lambda role: role.get("position", 0)):
                if item["name"].lower() in existing:
                    continue
                try:
                    await ctx.guild.create_role(
                        name=item["name"], color=discord.Color(item.get("color", 0)),
                        permissions=discord.Permissions(item.get("permissions", 0)),
                        hoist=bool(item.get("hoist")), mentionable=bool(item.get("mentionable")),
                        reason=f"restored from backup {backup_id} by {ctx.author}",
                    )
                    existing.add(item["name"].lower()); created_roles += 1
                except discord.HTTPException:
                    pass
        if mode in {"all", "channels"}:
            categories = {category.name.lower(): category for category in ctx.guild.categories}
            for item in snapshot.get("channels", []):
                if item.get("type") != "category" or item["name"].lower() in categories:
                    continue
                try:
                    category = await ctx.guild.create_category(item["name"], reason=f"restored from backup {backup_id}")
                    categories[item["name"].lower()] = category; created_channels += 1
                except discord.HTTPException:
                    pass
            existing = {(str(channel.type), channel.name.lower()) for channel in ctx.guild.channels}
            for item in sorted(snapshot.get("channels", []), key=lambda channel: channel.get("position", 0)):
                kind = item.get("type")
                if kind == "category" or (kind, item["name"].lower()) in existing:
                    continue
                category = categories.get((item.get("category") or "").lower())
                try:
                    if kind == "text":
                        await ctx.guild.create_text_channel(item["name"], category=category, topic=item.get("topic"), nsfw=bool(item.get("nsfw")), slowmode_delay=int(item.get("slowmode") or 0), reason=f"restored from backup {backup_id}")
                    elif kind == "voice":
                        await ctx.guild.create_voice_channel(item["name"], category=category, bitrate=item.get("bitrate"), user_limit=int(item.get("user_limit") or 0), reason=f"restored from backup {backup_id}")
                    elif kind == "stage_voice":
                        await ctx.guild.create_stage_channel(item["name"], category=category, reason=f"restored from backup {backup_id}")
                    else:
                        continue
                    existing.add((kind, item["name"].lower())); created_channels += 1
                except discord.HTTPException:
                    pass
        if mode in {"all", "settings"} and snapshot.get("guild_settings"):
            settings = snapshot["guild_settings"]
            allowed = {"prefix", "embed_color", "vcrole_id", "muted_id", "rmuted_id", "imuted_id", "jail_id", "dj_id", "modlog_id", "base_role_id", "tags_enabled", "quote_enabled", "quote_redirect_channel", "autoplay", "twentyfour_seven", "disable_custom_fms", "snipe_protect"}
            values = {key: settings[key] for key in allowed if key in settings}
            if values:
                columns = ", ".join(values)
                placeholders = ", ".join("?" for _ in values)
                updates = ", ".join(f"{column} = excluded.{column}" for column in values)
                await self.bot.db.execute(f"INSERT INTO guild_settings (guild_id, {columns}) VALUES (?, {placeholders}) ON CONFLICT(guild_id) DO UPDATE SET {updates}", (ctx.guild.id, *values.values()))
        await ctx.send(embed=success_embed(f"restored backup `{backup_id}`: {created_roles} roles, {created_channels} channels, settings {'yes' if mode in {'all', 'settings'} else 'no'}", ctx.author))

    @backup.command(name="view")
    async def backup_view(self, ctx, backup_id: str):
        row = await self.bot.db.fetchrow("SELECT name, description, snapshot_json, created_at FROM server_backups WHERE guild_id = ? AND backup_id = ?", (ctx.guild.id, backup_id))
        if not row:
            return await ctx.send(embed=error_embed(f"backup `{backup_id}` was not found", ctx.author))
        snapshot = json.loads(row["snapshot_json"])
        desc = f"name: {row['name']}\ndescription: {row['description'] or 'none'}\nroles: {len(snapshot.get('roles', []))}\nchannels: {len(snapshot.get('channels', []))}\nsettings: {'included' if snapshot.get('guild_settings') else 'not included'}\ncreated: <t:{row['created_at']}:R>"
        await ctx.send(embed=fleed_embed(title=f"backup `{backup_id}`", description=desc, author=ctx.author))

    @backup.command(name="delete")
    async def backup_delete(self, ctx, backup_id: str):
        await self.bot.db.execute("DELETE FROM server_backups WHERE guild_id = ? AND backup_id = ?", (ctx.guild.id, backup_id))
        await ctx.send(embed=success_embed(f"deleted backup `{backup_id}`", ctx.author))

    @backup.command(name="list")
    async def backup_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT backup_id, name, created_at FROM server_backups WHERE guild_id = ? ORDER BY created_at DESC", (ctx.guild.id,))
        lines = [f"`{r['backup_id']}` — {r['name']} (<t:{r['created_at']}:R>)" for r in rows]
        await ctx.send(embed=fleed_embed(title="server backups", description="\n".join(lines) or "none saved", author=ctx.author))

    @backup.command(name="rename")
    async def backup_rename(self, ctx, backup_id: str, name: str, *, description: str = "none"):
        exists = await self.bot.db.fetchrow("SELECT 1 FROM server_backups WHERE guild_id = ? AND backup_id = ?", (ctx.guild.id, backup_id))
        if not exists:
            return await ctx.send(embed=error_embed(f"backup `{backup_id}` was not found", ctx.author))
        await self.bot.db.execute("UPDATE server_backups SET name = ?, description = ? WHERE guild_id = ? AND backup_id = ?", (name, description, ctx.guild.id, backup_id))
        await ctx.send(embed=success_embed(f"renamed backup `{backup_id}` to `{name.lower()}`", ctx.author))

    # boost
    @commands.group(name="boost", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def boost(self, ctx):
        await send_group_help(ctx, ctx.command)

    @boost.command(name="channel", aliases=["set", "ch"])
    async def boost_channel(self, ctx, channel: discord.TextChannel):
        await self.bot.db.execute("INSERT INTO boost_config (guild_id, channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?", (ctx.guild.id, channel.id, channel.id))
        await ctx.send(embed=success_embed(f"set boost announcements to {channel.mention}", ctx.author))

    @boost.command(name="message", aliases=["msg", "setmessage"])
    async def boost_message(self, ctx, *, message_template: str):
        await self.bot.db.execute("INSERT INTO boost_config (guild_id, message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET message = ?", (ctx.guild.id, message_template, message_template))
        await ctx.send(embed=success_embed("updated boost message template", ctx.author))

    @boost.command(name="view", aliases=["preview", "test"])
    async def boost_view(self, ctx):
        row = await self.bot.db.fetchrow("SELECT channel_id, message FROM boost_config WHERE guild_id = ?", (ctx.guild.id,))
        template = row["message"] if row and row["message"] else "thank you {user} for boosting {guild.name}!"
        preview = template.replace("{user}", ctx.author.mention).replace("{guild.name}", ctx.guild.name)
        channel = f"<#{row['channel_id']}>" if row and row["channel_id"] else "not configured"
        await ctx.send(embed=fleed_embed(title="boost notification preview", description=f"channel: {channel}\n\n{preview}", author=ctx.author))

    @boost.command(name="remove", aliases=["delete", "del", "disable"])
    async def boost_remove(self, ctx):
        await self.bot.db.execute("DELETE FROM boost_config WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("removed boost notifications configuration", ctx.author))

    # invoke commands
    @commands.hybrid_group(name="invoke", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke(self, ctx):
        await send_group_help(ctx, ctx.command)

    @invoke.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    async def invoke_setup(self, ctx, command: str = None):
        if not command:
            return await send_group_help(ctx, ctx.command.parent, "server")
        command = command.lower()
        if not self.bot.get_command(command):
            return await ctx.send(embed=error_embed(f"command `{command}` does not exist", ctx.author))
        default = "completed `{command}` for {user}"
        await self.bot.db.execute("INSERT OR IGNORE INTO invoke_messages (guild_id, command_name, msg_type, message) VALUES (?, ?, 'message', ?)", (ctx.guild.id, command, default))
        await ctx.send(embed=success_embed(f"enabled invoke messages for `{command}`", ctx.author))

    @invoke.command(name="reset")
    @commands.has_permissions(manage_guild=True)
    async def invoke_reset(self, ctx, command: str = None):
        if command:
            await self.bot.db.execute("DELETE FROM invoke_messages WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, command.lower()))
        else:
            await self.bot.db.execute("DELETE FROM invoke_messages WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed(f"disabled invoke messages for `{command.lower() if command else 'all'}`", ctx.author))

    @invoke.command(name="list")
    @commands.has_permissions(manage_guild=True)
    async def invoke_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT command_name, msg_type FROM invoke_messages WHERE guild_id = ? ORDER BY command_name, msg_type", (ctx.guild.id,))
        lines = [f"`{r['command_name']}` — {r['msg_type']}" for r in rows]
        await ctx.send(embed=fleed_embed(title="invoke messages", description="\n".join(lines) or "none configured", author=ctx.author))

    @invoke.command(name="settings", aliases=["config"])
    @commands.has_permissions(manage_guild=True)
    async def invoke_settings(self, ctx):
        rows = await self.bot.db.fetch("SELECT command_name, msg_type FROM invoke_messages WHERE guild_id = ?", (ctx.guild.id,))
        commands_count = len({r["command_name"] for r in rows})
        await ctx.send(embed=fleed_embed(title="invoke configuration", description=f"configured commands: {commands_count}\nconfigured scripts: {len(rows)}\nuse `invoke set <command> <message|dm> <template>`", author=ctx.author))

    @invoke.command(name="set")
    @commands.has_permissions(manage_guild=True)
    async def invoke_set(self, ctx, command: str, message_type: str, *, template: str):
        command = command.lower(); message_type = message_type.lower()
        if not self.bot.get_command(command):
            return await ctx.send(embed=error_embed(f"command `{command}` does not exist", ctx.author))
        if message_type not in {"message", "dm"}:
            return await ctx.send(embed=error_embed("message type must be `message` or `dm`", ctx.author))
        await self.bot.db.execute("INSERT OR REPLACE INTO invoke_messages (guild_id, command_name, msg_type, message) VALUES (?, ?, ?, ?)", (ctx.guild.id, command, message_type, template[:1900]))
        await ctx.send(embed=success_embed(f"updated `{command}` {message_type} invoke template", ctx.author))

    @invoke.command(name="variables", aliases=["vars"])
    @commands.has_permissions(manage_guild=True)
    async def invoke_variables(self, ctx):
        await ctx.send(embed=fleed_embed(title="invoke variables", description="{user}, {moderator}, {reason}, {guild.name}, {case_id}", author=ctx.author))

    @invoke.command(name="test")
    @commands.has_permissions(manage_guild=True)
    async def invoke_test(self, ctx, command: str = "ban"):
        rows = await self.bot.db.fetch("SELECT msg_type, message FROM invoke_messages WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, command.lower()))
        if not rows:
            return await ctx.send(embed=warn_embed(f"no invoke template configured for `{command.lower()}`", ctx.author))
        lines = [f"**{r['msg_type']}:** {self._render_invoke(r['message'], ctx, command)}" for r in rows]
        await ctx.send(embed=fleed_embed(title=f"invoke test: {command.lower()}", description="\n\n".join(lines), author=ctx.author))

    @invoke.command(name="delete", aliases=["remove", "del"])
    @commands.has_permissions(manage_guild=True)
    async def invoke_delete(self, ctx, command: str = None, message_type: str = None):
        if not command:
            return await send_group_help(ctx, ctx.command.parent, "server")
        if message_type:
            await self.bot.db.execute("DELETE FROM invoke_messages WHERE guild_id = ? AND command_name = ? AND msg_type = ?", (ctx.guild.id, command.lower(), message_type.lower()))
        else:
            await self.bot.db.execute("DELETE FROM invoke_messages WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, command.lower()))
        await ctx.send(embed=success_embed("removed invoke message script", ctx.author))

    # invoke sub-handlers for all punishments
    async def _invoke_view_helper(self, ctx, cmd_name, sub):
        message_type = sub if sub in {"message", "dm"} else None
        if message_type:
            rows = await self.bot.db.fetch("SELECT msg_type, message FROM invoke_messages WHERE guild_id = ? AND command_name = ? AND msg_type = ?", (ctx.guild.id, cmd_name, message_type))
        else:
            rows = await self.bot.db.fetch("SELECT msg_type, message FROM invoke_messages WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, cmd_name))
        lines = [f"**{r['msg_type']}:** {r['message']}" for r in rows]
        await ctx.send(embed=fleed_embed(title=f"invoke {cmd_name}", description="\n\n".join(lines) or "no template configured", author=ctx.author))

    def _render_invoke(self, template, ctx, command):
        return str(template).replace("{user}", ctx.author.mention).replace("{moderator}", ctx.author.mention).replace("{guild.name}", ctx.guild.name).replace("{command}", command)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if not ctx.guild or not ctx.command or ctx.command.root_parent and ctx.command.root_parent.name == "invoke":
            return
        root = ctx.command.root_parent.name if ctx.command.root_parent else ctx.command.name
        rows = await self.bot.db.fetch("SELECT msg_type, message FROM invoke_messages WHERE guild_id = ? AND command_name = ?", (ctx.guild.id, root.lower()))
        for row in rows:
            text = self._render_invoke(row["message"], ctx, root.lower())[:1900]
            try:
                if row["msg_type"] == "dm": await ctx.author.send(text)
                else: await ctx.send(text, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
            except discord.HTTPException:
                pass

    @invoke.group(name="strip", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_strip(self, ctx):
        await self._invoke_view_helper(ctx, "strip", "general")
    @invoke_strip.command(name="view")
    async def invoke_strip_view(self, ctx):
        await self._invoke_view_helper(ctx, "strip", "view")
    @invoke_strip.command(name="dm")
    async def invoke_strip_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "strip", "dm")
    @invoke_strip.command(name="message")
    async def invoke_strip_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "strip", "message")

    @invoke.group(name="staffstrip", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_staffstrip(self, ctx):
        await self._invoke_view_helper(ctx, "staffstrip", "general")
    @invoke_staffstrip.command(name="view")
    async def invoke_staffstrip_view(self, ctx):
        await self._invoke_view_helper(ctx, "staffstrip", "view")
    @invoke_staffstrip.command(name="dm")
    async def invoke_staffstrip_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "staffstrip", "dm")
    @invoke_staffstrip.command(name="message")
    async def invoke_staffstrip_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "staffstrip", "message")

    @invoke.group(name="unban", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_unban(self, ctx):
        await self._invoke_view_helper(ctx, "unban", "general")
    @invoke_unban.command(name="view")
    async def invoke_unban_view(self, ctx):
        await self._invoke_view_helper(ctx, "unban", "view")
    @invoke_unban.command(name="dm")
    async def invoke_unban_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "unban", "dm")
    @invoke_unban.command(name="message")
    async def invoke_unban_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "unban", "message")

    @invoke.group(name="jail", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_jail(self, ctx):
        await self._invoke_view_helper(ctx, "jail", "general")
    @invoke_jail.command(name="view")
    async def invoke_jail_view(self, ctx):
        await self._invoke_view_helper(ctx, "jail", "view")
    @invoke_jail.command(name="dm")
    async def invoke_jail_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "jail", "dm")
    @invoke_jail.command(name="message")
    async def invoke_jail_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "jail", "message")

    @invoke.group(name="unjail", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_unjail(self, ctx):
        await self._invoke_view_helper(ctx, "unjail", "general")
    @invoke_unjail.command(name="view")
    async def invoke_unjail_view(self, ctx):
        await self._invoke_view_helper(ctx, "unjail", "view")
    @invoke_unjail.command(name="dm")
    async def invoke_unjail_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "unjail", "dm")
    @invoke_unjail.command(name="message")
    async def invoke_unjail_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "unjail", "message")

    @invoke.group(name="imute", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_imute(self, ctx):
        await self._invoke_view_helper(ctx, "imute", "general")
    @invoke_imute.command(name="view")
    async def invoke_imute_view(self, ctx):
        await self._invoke_view_helper(ctx, "imute", "view")
    @invoke_imute.command(name="dm")
    async def invoke_imute_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "imute", "dm")
    @invoke_imute.command(name="message")
    async def invoke_imute_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "imute", "message")

    @invoke.group(name="iunmute", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_iunmute(self, ctx):
        await self._invoke_view_helper(ctx, "iunmute", "general")
    @invoke_iunmute.command(name="view")
    async def invoke_iunmute_view(self, ctx):
        await self._invoke_view_helper(ctx, "iunmute", "view")
    @invoke_iunmute.command(name="dm")
    async def invoke_iunmute_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "iunmute", "dm")
    @invoke_iunmute.command(name="message")
    async def invoke_iunmute_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "iunmute", "message")

    @invoke.group(name="rmute", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_rmute(self, ctx):
        await self._invoke_view_helper(ctx, "rmute", "general")
    @invoke_rmute.command(name="view")
    async def invoke_rmute_view(self, ctx):
        await self._invoke_view_helper(ctx, "rmute", "view")
    @invoke_rmute.command(name="dm")
    async def invoke_rmute_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "rmute", "dm")
    @invoke_rmute.command(name="message")
    async def invoke_rmute_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "rmute", "message")

    @invoke.group(name="runmute", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_runmute(self, ctx):
        await self._invoke_view_helper(ctx, "runmute", "general")
    @invoke_runmute.command(name="view")
    async def invoke_runmute_view(self, ctx):
        await self._invoke_view_helper(ctx, "runmute", "view")
    @invoke_runmute.command(name="dm")
    async def invoke_runmute_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "runmute", "dm")
    @invoke_runmute.command(name="message")
    async def invoke_runmute_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "runmute", "message")

    @invoke.group(name="timeout", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_timeout(self, ctx):
        await self._invoke_view_helper(ctx, "timeout", "general")
    @invoke_timeout.command(name="view")
    async def invoke_timeout_view(self, ctx):
        await self._invoke_view_helper(ctx, "timeout", "view")
    @invoke_timeout.command(name="dm")
    async def invoke_timeout_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "timeout", "dm")
    @invoke_timeout.command(name="message")
    async def invoke_timeout_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "timeout", "message")

    @invoke.group(name="untimeout", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_untimeout(self, ctx):
        await self._invoke_view_helper(ctx, "untimeout", "general")
    @invoke_untimeout.command(name="view")
    async def invoke_untimeout_view(self, ctx):
        await self._invoke_view_helper(ctx, "untimeout", "view")
    @invoke_untimeout.command(name="dm")
    async def invoke_untimeout_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "untimeout", "dm")
    @invoke_untimeout.command(name="message")
    async def invoke_untimeout_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "untimeout", "message")

    @invoke.group(name="ban", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_ban(self, ctx):
        await self._invoke_view_helper(ctx, "ban", "general")
    @invoke_ban.command(name="view")
    async def invoke_ban_view(self, ctx):
        await self._invoke_view_helper(ctx, "ban", "view")
    @invoke_ban.command(name="dm")
    async def invoke_ban_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "ban", "dm")
    @invoke_ban.command(name="message")
    async def invoke_ban_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "ban", "message")

    @invoke.group(name="hardban", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_hardban(self, ctx):
        await self._invoke_view_helper(ctx, "hardban", "general")
    @invoke_hardban.command(name="view")
    async def invoke_hardban_view(self, ctx):
        await self._invoke_view_helper(ctx, "hardban", "view")
    @invoke_hardban.command(name="dm")
    async def invoke_hardban_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "hardban", "dm")
    @invoke_hardban.command(name="message")
    async def invoke_hardban_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "hardban", "message")

    @invoke.group(name="softban", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_softban(self, ctx):
        await self._invoke_view_helper(ctx, "softban", "general")
    @invoke_softban.command(name="view")
    async def invoke_softban_view(self, ctx):
        await self._invoke_view_helper(ctx, "softban", "view")
    @invoke_softban.command(name="dm")
    async def invoke_softban_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "softban", "dm")
    @invoke_softban.command(name="message")
    async def invoke_softban_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "softban", "message")

    @invoke.group(name="kick", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_kick(self, ctx):
        await self._invoke_view_helper(ctx, "kick", "general")
    @invoke_kick.command(name="view")
    async def invoke_kick_view(self, ctx):
        await self._invoke_view_helper(ctx, "kick", "view")
    @invoke_kick.command(name="dm")
    async def invoke_kick_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "kick", "dm")
    @invoke_kick.command(name="message")
    async def invoke_kick_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "kick", "message")

    @invoke.group(name="warn", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def invoke_warn(self, ctx):
        await self._invoke_view_helper(ctx, "warn", "general")
    @invoke_warn.command(name="view")
    async def invoke_warn_view(self, ctx):
        await self._invoke_view_helper(ctx, "warn", "view")
    @invoke_warn.command(name="dm")
    async def invoke_warn_dm(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "warn", "dm")
    @invoke_warn.command(name="message")
    async def invoke_warn_message(self, ctx, sub: str = "view"):
        await self._invoke_view_helper(ctx, "warn", "message")

async def setup(bot):
    await bot.add_cog(Server(bot))
