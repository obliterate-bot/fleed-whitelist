import discord
from discord.ext import commands, tasks
import datetime
import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help


def render_daily_leaderboard(guild_name: str, date_str: str, top_users: list, total_messages: int, title_badge: str = "DAILY CHAT LEADERBOARD") -> io.BytesIO:
    W, H = 960, 700
    card = Image.new("RGBA", (W, H), (13, 13, 16, 255))
    draw = ImageDraw.Draw(card)

    # Angular Yellow/Gold geometric slashes on top right
    draw.polygon([(W - 180, 0), (W, 0), (W, 140), (W - 80, 0)], fill=(245, 197, 24, 255))
    draw.polygon([(W - 220, 0), (W - 190, 0), (W - 80, 160), (W - 110, 160)], fill=(32, 32, 38, 255))
    draw.polygon([(W - 245, 0), (W - 230, 0), (W - 120, 160), (W - 135, 160)], fill=(245, 197, 24, 80))

    # Card outer border
    draw.rounded_rectangle([(0, 0), (W - 1, H - 1)], radius=24, outline=(38, 38, 46, 255), width=2)

    # Fonts
    try:
        font_title = ImageFont.truetype("arialbd.ttf", 30)
        font_sub = ImageFont.truetype("arial.ttf", 17)
        font_h1 = ImageFont.truetype("arialbd.ttf", 25)
        font_row_name = ImageFont.truetype("arialbd.ttf", 18)
        font_row_val = ImageFont.truetype("arial.ttf", 15)
        font_rank_num = ImageFont.truetype("arialbd.ttf", 19)
        font_badge = ImageFont.truetype("arialbd.ttf", 13)
    except Exception:
        font_title = font_sub = font_h1 = font_row_name = font_row_val = font_rank_num = font_badge = ImageFont.load_default()

    # Header Badge
    badge_w = 290 if "WEEKLY" in title_badge else 275
    draw.rounded_rectangle([(40, 35), (40 + badge_w, 70)], radius=17, fill=(245, 197, 24, 255))
    draw.text((55, 43), title_badge, font=font_badge, fill=(13, 13, 16, 255))

    clean_guild = (guild_name[:24] + "…") if len(guild_name) > 24 else guild_name
    draw.text((40, 82), clean_guild.lower(), font=font_title, fill=(255, 255, 255, 255))
    draw.text((40, 122), f"{date_str} • {total_messages:,} total messages", font=font_sub, fill=(160, 160, 172, 255))

    # #1 Winner Showcase Card (Upper section)
    if top_users:
        winner = top_users[0]  # (rank, username, count, av_bytes)
        w_x, w_y, w_w, w_h = 40, 160, W - 80, 125
        # Winner background
        draw.rounded_rectangle([(w_x, w_y), (w_x + w_w, w_y + w_h)], radius=16, fill=(22, 22, 28, 255), outline=(245, 197, 24, 200), width=2)

        # Winner Avatar
        av_size = 90
        av_x, av_y = w_x + 18, w_y + 17
        mask = Image.new("L", (av_size, av_size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, av_size, av_size), fill=255)

        if len(winner) > 3 and winner[3]:
            try:
                av = Image.open(io.BytesIO(winner[3])).convert("RGBA").resize((av_size, av_size), Image.Resampling.LANCZOS)
            except Exception:
                av = Image.new("RGBA", (av_size, av_size), (35, 35, 42, 255))
        else:
            av = Image.new("RGBA", (av_size, av_size), (35, 35, 42, 255))
            adraw = ImageDraw.Draw(av)
            adraw.text((av_size // 2, av_size // 2), winner[1][:1].upper(), fill=(245, 197, 24, 255), anchor="mm")

        card.paste(av, (av_x, av_y), mask)
        draw.ellipse((av_x - 3, av_y - 3, av_x + av_size + 3, av_y + av_size + 3), outline=(245, 197, 24, 255), width=3)

        # Winner tag
        draw.text((w_x + 130, w_y + 18), "TOP CHATTER OF THE PERIOD", font=font_badge, fill=(245, 197, 24, 255))
        clean_w_name = str(winner[1]).lower().lstrip("@")
        w_name = f"@{clean_w_name}"
        draw.text((w_x + 130, w_y + 40), w_name, font=font_h1, fill=(255, 255, 255, 255))

        # Winner messages & bar
        pct = (winner[2] / max(1, total_messages)) * 100
        stat_txt = f"{winner[2]:,} messages ({pct:.1f}% of chat)"
        draw.text((w_x + 130, w_y + 78), stat_txt, font=font_sub, fill=(200, 200, 210, 255))

        # Big Winner progress bar
        wbar_x = w_x + 500
        wbar_y = w_y + 48
        wbar_w = w_w - 525
        draw.rounded_rectangle([(wbar_x, wbar_y), (wbar_x + wbar_w, wbar_y + 26)], radius=13, fill=(14, 14, 18, 255), outline=(45, 45, 54, 255), width=1)
        wfill = max(13, int(wbar_w * min(1.0, winner[2] / max(1, total_messages))))
        draw.rounded_rectangle([(wbar_x, wbar_y), (wbar_x + wfill, wbar_y + 26)], radius=13, fill=(245, 197, 24, 255))

    # Ranks #2 through #10 Grid (2 columns x 4-5 rows)
    rest_users = top_users[1:11]
    col_w = (W - 100) // 2
    row_h = 66
    base_y = 310

    for idx, u in enumerate(rest_users):
        col = idx // 5
        row = idx % 5
        rx = 40 + col * (col_w + 20)
        ry = base_y + row * (row_h + 10)

        is_top3 = (u[0] <= 3)
        outline_c = (245, 197, 24, 140) if is_top3 else (35, 35, 42, 255)
        draw.rounded_rectangle([(rx, ry), (rx + col_w, ry + row_h)], radius=14, fill=(18, 18, 23, 255), outline=outline_c, width=1)

        # Rank badge
        rank_c = (245, 197, 24, 255) if is_top3 else (160, 160, 172, 255)
        draw.text((rx + 16, ry + 21), f"#{u[0]}", font=font_rank_num, fill=rank_c)

        # Mini Avatar
        r_av_size = 44
        r_av_x, r_av_y = rx + 52, ry + 11
        r_mask = Image.new("L", (r_av_size, r_av_size), 0)
        r_mask_draw = ImageDraw.Draw(r_mask)
        r_mask_draw.ellipse((0, 0, r_av_size, r_av_size), fill=255)

        if len(u) > 3 and u[3]:
            try:
                r_av = Image.open(io.BytesIO(u[3])).convert("RGBA").resize((r_av_size, r_av_size), Image.Resampling.LANCZOS)
            except Exception:
                r_av = Image.new("RGBA", (r_av_size, r_av_size), (35, 35, 42, 255))
        else:
            r_av = Image.new("RGBA", (r_av_size, r_av_size), (32, 32, 38, 255))
            r_adraw = ImageDraw.Draw(r_av)
            r_adraw.text((r_av_size // 2, r_av_size // 2), u[1][:1].upper(), fill=(245, 197, 24, 255) if is_top3 else (180, 180, 190, 255), anchor="mm")

        card.paste(r_av, (r_av_x, r_av_y), r_mask)
        r_ring_c = (245, 197, 24, 255) if is_top3 else (50, 50, 60, 255)
        draw.ellipse((r_av_x - 1, r_av_y - 1, r_av_x + r_av_size + 1, r_av_y + r_av_size + 1), outline=r_ring_c, width=2)

        # Username
        clean_uname = str(u[1]).lower().lstrip("@")
        uname = f"@{clean_uname}"
        if len(uname) > 13:
            uname = uname[:11] + "…"
        draw.text((rx + 108, ry + 12), uname, font=font_row_name, fill=(255, 255, 255, 255))

        # Message count
        draw.text((rx + 108, ry + 38), f"{u[2]:,} msgs", font=font_row_val, fill=(160, 160, 172, 255))

        # Mini bar
        mbar_x = rx + 255
        mbar_y = ry + 26
        mbar_w = col_w - 275
        draw.rounded_rectangle([(mbar_x, mbar_y), (mbar_x + mbar_w, mbar_y + 14)], radius=7, fill=(12, 12, 16, 255))
        pct_u = u[2] / max(1, top_users[0][2] if top_users else 1)
        mfill = max(7, int(mbar_w * min(1.0, pct_u)))
        bar_fill_c = (245, 197, 24, 255) if is_top3 else (200, 200, 210, 255)
        draw.rounded_rectangle([(mbar_x, mbar_y), (mbar_x + mfill, mbar_y + 14)], radius=7, fill=bar_fill_c)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf


class Activity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.daily_leaderboard_loop.start()

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"})
        # Initialize tables
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS daily_messages (
                guild_id INTEGER,
                user_id INTEGER,
                date_str TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id, date_str)
            )
        """)
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS daily_chat_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                enabled INTEGER DEFAULT 1,
                last_posted_date TEXT
            )
        """)

    async def cog_unload(self):
        self.daily_leaderboard_loop.cancel()
        if self.session and not self.session.closed:
            await self.session.close()

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot or message.content.startswith((",", "/", "!")):
            return

        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        await self.bot.db.execute("""
            INSERT INTO daily_messages (guild_id, user_id, date_str, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id, user_id, date_str)
            DO UPDATE SET count = count + 1
        """, (message.guild.id, message.author.id, date_str))

    async def fetch_leaderboard_data(self, guild: discord.Guild, date_str: str = None, days: int = 1):
        if days == 1:
            if not date_str:
                date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            rows = await self.bot.db.fetch("""
                SELECT user_id, count FROM daily_messages
                WHERE guild_id = ? AND date_str = ?
                ORDER BY count DESC
                LIMIT 10
            """, (guild.id, date_str))
            total_row = await self.bot.db.fetchrow("""
                SELECT SUM(count) as total FROM daily_messages
                WHERE guild_id = ? AND date_str = ?
            """, (guild.id, date_str))
            total_msgs = total_row["total"] if total_row and total_row["total"] else 0
        else:
            # Multi-day aggregate (e.g. weekly)
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            rows = await self.bot.db.fetch("""
                SELECT user_id, SUM(count) as count FROM daily_messages
                WHERE guild_id = ? AND date_str >= ?
                GROUP BY user_id
                ORDER BY count DESC
                LIMIT 10
            """, (guild.id, cutoff))
            total_row = await self.bot.db.fetchrow("""
                SELECT SUM(count) as total FROM daily_messages
                WHERE guild_id = ? AND date_str >= ?
            """, (guild.id, cutoff))
            total_msgs = total_row["total"] if total_row and total_row["total"] else 0

        # Build top users list with avatars
        top_users = []
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"})

        for idx, r in enumerate(rows, 1):
            uid = r["user_id"]
            user = guild.get_member(uid) or self.bot.get_user(uid)
            uname = user.name if user else f"user_{uid}"
            av_bytes = None
            if user and hasattr(user, "display_avatar") and user.display_avatar:
                try:
                    av_bytes = await user.display_avatar.with_format("png").with_size(128).read()
                except Exception:
                    try:
                        av_bytes = await user.display_avatar.read()
                    except Exception:
                        pass
            top_users.append((idx, uname, r["count"], av_bytes))

        return top_users, total_msgs

    @tasks.loop(minutes=5)
    async def daily_leaderboard_loop(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        yesterday_str = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_display = (now - datetime.timedelta(days=1)).strftime("%B %d, %Y")

        configs = await self.bot.db.fetch("SELECT guild_id, channel_id, last_posted_date FROM daily_chat_config WHERE enabled = 1")
        for cfg in configs:
            guild_id = cfg["guild_id"]
            channel_id = cfg["channel_id"]
            last_posted = cfg["last_posted_date"]

            if not channel_id or last_posted == yesterday_str:
                continue

            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            try:
                top_users, total_msgs = await self.fetch_leaderboard_data(guild, date_str=yesterday_str, days=1)
                if not top_users or total_msgs <= 0:
                    # No chat on yesterday, still update date
                    await self.bot.db.execute("UPDATE daily_chat_config SET last_posted_date = ? WHERE guild_id = ?", (yesterday_str, guild_id))
                    continue

                card_buf = render_daily_leaderboard(
                    guild_name=guild.name,
                    date_str=yesterday_display,
                    top_users=top_users,
                    total_messages=total_msgs,
                    title_badge="DAILY CHAT LEADERBOARD"
                )

                file = discord.File(fp=card_buf, filename=f"daily_chat_{yesterday_str}.png")
                await channel.send(
                    content=f"⚡ **daily chat leaderboard — {yesterday_display}**",
                    file=file
                )
                await self.bot.db.execute("UPDATE daily_chat_config SET last_posted_date = ? WHERE guild_id = ?", (yesterday_str, guild_id))
            except Exception as e:
                print(f"[Daily LB Error] Guild {guild_id}: {e}")

    @daily_leaderboard_loop.before_loop
    async def before_daily_loop(self):
        await self.bot.wait_until_ready()

    @commands.group(name="dailychat", aliases=["chatlb", "dailylb", "activity", "chatleaderboard", "dailyboard"], invoke_without_command=True)
    async def daily_group(self, ctx, target: str = None):
        """View today's live daily chat leaderboard or specify 'yesterday'"""
        now = datetime.datetime.now(datetime.timezone.utc)
        if target and target.lower() in ["yesterday", "prev", "yday"]:
            date_str = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            display_date = (now - datetime.timedelta(days=1)).strftime("%B %d, %Y")
        else:
            date_str = now.strftime("%Y-%m-%d")
            display_date = now.strftime("%B %d, %Y") + " (Live)"

        top_users, total_msgs = await self.fetch_leaderboard_data(ctx.guild, date_str=date_str, days=1)
        if not top_users:
            return await ctx.send(embed=warn_embed("no chat activity recorded for this date yet", ctx.author))

        card_buf = render_daily_leaderboard(
            guild_name=ctx.guild.name,
            date_str=display_date,
            top_users=top_users,
            total_messages=total_msgs,
            title_badge="DAILY CHAT LEADERBOARD"
        )
        file = discord.File(fp=card_buf, filename=f"daily_chat_{date_str}.png")
        await ctx.send(file=file)

    @daily_group.command(name="channel", aliases=["setchannel"])
    @commands.has_permissions(administrator=True)
    async def daily_channel(self, ctx, *, channel: str = None):
        """Set the channel where daily chat leaderboards are posted automatically at midnight UTC"""
        if channel is None:
            cfg = await self.bot.db.fetchrow("SELECT channel_id, enabled FROM daily_chat_config WHERE guild_id = ?", (ctx.guild.id,))
            if not cfg or not cfg["channel_id"] or not cfg["enabled"]:
                return await ctx.send(embed=fleed_embed(title="daily leaderboard channel", description="automated daily chat leaderboard is currently **disabled**", author=ctx.author))
            ch = ctx.guild.get_channel(cfg["channel_id"])
            ch_mention = ch.mention if ch else f"`#{cfg['channel_id']}`"
            return await ctx.send(embed=fleed_embed(title="daily leaderboard channel", description=f"automated daily chat leaderboard is posted daily to {ch_mention}", author=ctx.author))

        lower_c = channel.lower().strip()
        if lower_c in ["none", "remove", "clear", "off", "disable", "disabled"]:
            await self.bot.db.execute("INSERT INTO daily_chat_config (guild_id, channel_id, enabled) VALUES (?, NULL, 0) ON CONFLICT(guild_id) DO UPDATE SET enabled = 0, channel_id = NULL", (ctx.guild.id,))
            return await ctx.send(embed=success_embed("disabled automated daily chat leaderboard posting", ctx.author))

        target_ch = None
        clean_id = lower_c.replace("<#", "").replace(">", "").strip()
        if clean_id.isdigit():
            target_ch = ctx.guild.get_channel(int(clean_id))
        if not target_ch:
            target_ch = discord.utils.find(lambda c: c.name.lower() == lower_c or c.name.lower() == lower_c.lstrip("#"), ctx.guild.text_channels)

        if not target_ch:
            return await ctx.send(embed=error_embed(f"could not find channel `{channel}`", ctx.author))

        await self.bot.db.execute("INSERT INTO daily_chat_config (guild_id, channel_id, enabled) VALUES (?, ?, 1) ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?, enabled = 1", (ctx.guild.id, target_ch.id, target_ch.id))
        await ctx.send(embed=success_embed(f"set automated daily chat leaderboard channel to {target_ch.mention}", ctx.author))

    @daily_group.command(name="test")
    @commands.has_permissions(administrator=True)
    async def daily_test(self, ctx):
        """Immediately test the daily leaderboard post in the configured channel"""
        cfg = await self.bot.db.fetchrow("SELECT channel_id FROM daily_chat_config WHERE guild_id = ?", (ctx.guild.id,))
        target_ch = ctx.channel
        if cfg and cfg["channel_id"]:
            ch = ctx.guild.get_channel(cfg["channel_id"])
            if ch:
                target_ch = ch

        now = datetime.datetime.now(datetime.timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        display_date = now.strftime("%B %d, %Y")

        top_users, total_msgs = await self.fetch_leaderboard_data(ctx.guild, date_str=date_str, days=1)
        if not top_users:
            top_users = [(1, ctx.author.name, 1, None)]
            total_msgs = 1

        card_buf = render_daily_leaderboard(
            guild_name=ctx.guild.name,
            date_str=display_date,
            top_users=top_users,
            total_messages=total_msgs,
            title_badge="DAILY CHAT LEADERBOARD"
        )
        file = discord.File(fp=card_buf, filename="daily_test.png")
        await target_ch.send(
            content=f"⚡ **[test] daily chat leaderboard — {display_date}**",
            file=file
        )
        if target_ch.id != ctx.channel.id:
            await ctx.send(embed=success_embed(f"sent test daily leaderboard to {target_ch.mention}", ctx.author))

    @commands.command(name="weekly", aliases=["weeklychat", "weeklylb"])
    async def weekly_leaderboard(self, ctx):
        """View the top 10 chatters over the last 7 days"""
        now = datetime.datetime.now(datetime.timezone.utc)
        display_date = f"Past 7 Days (Ending {now.strftime('%b %d')})"
        top_users, total_msgs = await self.fetch_leaderboard_data(ctx.guild, days=7)
        if not top_users:
            return await ctx.send(embed=warn_embed("no chat activity recorded over the past 7 days yet", ctx.author))

        card_buf = render_daily_leaderboard(
            guild_name=ctx.guild.name,
            date_str=display_date,
            top_users=top_users,
            total_messages=total_msgs,
            title_badge="WEEKLY CHAT LEADERBOARD"
        )
        file = discord.File(fp=card_buf, filename="weekly_chat.png")
        await ctx.send(file=file)

    @commands.command(name="messages", aliases=["chatstats", "messagecount"])
    async def messages_stats(self, ctx, member: discord.Member = None):
        """View your personal daily and weekly message count"""
        target = member or ctx.author
        now = datetime.datetime.now(datetime.timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        week_cutoff = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")

        # Today's count
        today_row = await self.bot.db.fetchrow("""
            SELECT count FROM daily_messages
            WHERE guild_id = ? AND user_id = ? AND date_str = ?
        """, (ctx.guild.id, target.id, today_str))
        today_count = today_row["count"] if today_row else 0

        # Week count
        week_row = await self.bot.db.fetchrow("""
            SELECT SUM(count) as total FROM daily_messages
            WHERE guild_id = ? AND user_id = ? AND date_str >= ?
        """, (ctx.guild.id, target.id, week_cutoff))
        week_count = week_row["total"] if week_row and week_row["total"] else 0

        # All-time count
        all_row = await self.bot.db.fetchrow("""
            SELECT SUM(count) as total FROM daily_messages
            WHERE guild_id = ? AND user_id = ?
        """, (ctx.guild.id, target.id))
        all_count = all_row["total"] if all_row and all_row["total"] else 0

        desc = (
            f"**today**: `{today_count:,}` messages\n"
            f"**past 7 days**: `{week_count:,}` messages\n"
            f"**all-time**: `{all_count:,}` messages"
        )
        embed = fleed_embed(title=f"{target.display_name.lower()}'s message activity", description=desc, author=target)
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Activity(bot))
