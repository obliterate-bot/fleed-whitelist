import discord
from discord.ext import commands
import aiohttp
import urllib.parse
import asyncio
import time
from discord.ext import tasks
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.reminder_worker.start()

    @staticmethod
    def _parse_duration(value: str):
        units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        total = 0
        import re as _re
        matches = _re.findall(r"(\d+)\s*([smhdw])", (value or "").lower())
        for amount, unit in matches:
            total += int(amount) * units[unit]
        return total or None

    @tasks.loop(seconds=20)
    async def reminder_worker(self):
        now = int(time.time())
        rows = await self.bot.db.fetch("SELECT id, channel_id, user_id, task, kind FROM reminders WHERE remind_at <= ?", (now,))
        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            if channel:
                try:
                    await channel.send(f"<@{row['user_id']}> {row['kind']}: {row['task']}"[:2000])
                except discord.HTTPException:
                    pass
            await self.bot.db.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))
        bumps = await self.bot.db.fetch("SELECT guild_id, channel_id FROM bump_reminders WHERE enabled = 1 AND next_bump > 0 AND next_bump <= ?", (now,))
        for row in bumps:
            channel = self.bot.get_channel(row["channel_id"])
            if channel:
                try:
                    await channel.send("it's time to bump this server again with `/bump`")
                except discord.HTTPException:
                    pass
            await self.bot.db.execute("UPDATE bump_reminders SET next_bump = 0 WHERE guild_id = ?", (row["guild_id"],))

    @reminder_worker.before_loop
    async def before_reminder_worker(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        # Disboard posts an embed confirming a successful bump; schedule the next one.
        if not message.guild or message.author.id != 302050872383242240 or not message.embeds:
            return
        text = (message.embeds[0].description or "").lower()
        if "bump done" not in text:
            return
        row = await self.bot.db.fetchrow("SELECT enabled FROM bump_reminders WHERE guild_id = ?", (message.guild.id,))
        if not row or not row["enabled"]:
            return
        await self.bot.db.execute("UPDATE bump_reminders SET channel_id = ?, next_bump = ? WHERE guild_id = ?", (message.channel.id, int(time.time()) + 7200, message.guild.id))

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (fleed; discord bot)"})

    async def cog_unload(self):
        self.reminder_worker.cancel()
        if self.session and not self.session.closed:
            await self.session.close()

    # translation
    @commands.command(name="translate", aliases=["tr", "t"])
    async def translate_cmd(self, ctx, destination: str, *, text: str):
        try:
            encoded_text = urllib.parse.quote(text)
            url = f"https://api.mymemory.translated.net/get?q={encoded_text}&langpair=autodetect|{destination.lower()}"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                translated = data.get("responseData", {}).get("translatedText")
                if not translated:
                    return await ctx.send(embed=error_embed("failed to translate text", ctx.author))

                desc = f"**destination:** `{destination.lower()}`\n\n**original**\n{text.lower()}\n\n**translated**\n{translated.lower()}"
                embed = fleed_embed(title="translator", description=desc, author=ctx.author)
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to translate text", ctx.author))

    # crypto
    async def get_crypto_price(self, coin_id: str):
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true&include_market_cap=true"
        async with self.session.get(url, timeout=10) as resp:
            data = await resp.json(content_type=None)
            if coin_id in data:
                return data[coin_id]
        return None

    @commands.command(name="bitcoin", aliases=["btc"])
    async def bitcoin(self, ctx):
        data = await self.get_crypto_price("bitcoin")
        if not data:
            return await ctx.send(embed=error_embed("failed to fetch bitcoin price", ctx.author))
        price = data.get("usd", 0)
        change = data.get("usd_24h_change", 0)
        sign = "+" if change >= 0 else ""
        desc = f"price: **${price:,.2f} USD**\n24h change: **{sign}{change:.2f}%**\nmarket cap: **${data.get('usd_market_cap', 0):,.0f}**"
        await ctx.send(embed=fleed_embed(title="bitcoin (btc)", description=desc, author=ctx.author))

    @commands.command(name="ethereum", aliases=["eth"])
    async def ethereum(self, ctx):
        data = await self.get_crypto_price("ethereum")
        if not data:
            return await ctx.send(embed=error_embed("failed to fetch ethereum price", ctx.author))
        price = data.get("usd", 0)
        change = data.get("usd_24h_change", 0)
        sign = "+" if change >= 0 else ""
        desc = f"price: **${price:,.2f} USD**\n24h change: **{sign}{change:.2f}%**\nmarket cap: **${data.get('usd_market_cap', 0):,.0f}**"
        await ctx.send(embed=fleed_embed(title="ethereum (eth)", description=desc, author=ctx.author))

    @commands.command(name="solana", aliases=["sol"])
    async def solana(self, ctx):
        data = await self.get_crypto_price("solana")
        if not data:
            return await ctx.send(embed=error_embed("failed to fetch solana price", ctx.author))
        price = data.get("usd", 0)
        change = data.get("usd_24h_change", 0)
        sign = "+" if change >= 0 else ""
        desc = f"price: **${price:,.2f} USD**\n24h change: **{sign}{change:.2f}%**\nmarket cap: **${data.get('usd_market_cap', 0):,.0f}**"
        await ctx.send(embed=fleed_embed(title="solana (sol)", description=desc, author=ctx.author))

    @commands.command(name="litecoin", aliases=["ltc"])
    async def litecoin(self, ctx):
        data = await self.get_crypto_price("litecoin")
        if not data:
            return await ctx.send(embed=error_embed("failed to fetch litecoin price", ctx.author))
        price = data.get("usd", 0)
        change = data.get("usd_24h_change", 0)
        sign = "+" if change >= 0 else ""
        desc = f"price: **${price:,.2f} USD**\n24h change: **{sign}{change:.2f}%**\nmarket cap: **${data.get('usd_market_cap', 0):,.0f}**"
        await ctx.send(embed=fleed_embed(title="litecoin (ltc)", description=desc, author=ctx.author))

    @commands.command(name="monero", aliases=["xmr"])
    async def monero(self, ctx):
        data = await self.get_crypto_price("monero")
        if not data:
            return await ctx.send(embed=error_embed("failed to fetch monero price", ctx.author))
        price = data.get("usd", 0)
        change = data.get("usd_24h_change", 0)
        sign = "+" if change >= 0 else ""
        desc = f"price: **${price:,.2f} USD**\n24h change: **{sign}{change:.2f}%**\nmarket cap: **${data.get('usd_market_cap', 0):,.0f}**"
        await ctx.send(embed=fleed_embed(title="monero (xmr)", description=desc, author=ctx.author))

    @commands.group(name="crypto", invoke_without_command=True)
    async def crypto_group(self, ctx):
        await send_group_help(ctx, ctx.command)

    @crypto_group.command(name="rates", aliases=["rate", "r"])
    async def crypto_rates(self, ctx):
        coins = "bitcoin,ethereum,solana,ripple,litecoin,monero"
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coins}&vs_currencies=usd&include_24hr_change=true"
        async with self.session.get(url, timeout=10) as resp:
            data = await resp.json(content_type=None)
            lines = []
            for c, name in [("bitcoin", "btc"), ("ethereum", "eth"), ("solana", "sol"), ("ripple", "xrp"), ("litecoin", "ltc"), ("monero", "xmr")]:
                if c in data:
                    p = data[c].get("usd", 0)
                    ch = data[c].get("usd_24h_change", 0)
                    s = "+" if ch >= 0 else ""
                    lines.append(f"**{name}**: ${p:,.2f} (`{s}{ch:.2f}%`)")
            await ctx.send(embed=fleed_embed(title="crypto market rates", description="\n".join(lines), author=ctx.author))

    # weather
    @commands.command(name="weather")
    async def weather(self, ctx, *, location: str):
        try:
            loc_encoded = urllib.parse.quote(location)
            url = f"https://wttr.in/{loc_encoded}?format=j1"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                curr = data.get("current_condition", [])[0]
                area = data.get("nearest_area", [])[0]

                temp_c = curr.get("temp_C")
                temp_f = curr.get("temp_F")
                feels_c = curr.get("FeelsLikeC")
                feels_f = curr.get("FeelsLikeF")
                desc = curr.get("weatherDesc", [{}])[0].get("value", "").lower()
                humidity = curr.get("humidity")
                wind_mph = curr.get("windspeedMiles")
                city = area.get("areaName", [{}])[0].get("value", location).lower()
                country = area.get("country", [{}])[0].get("value", "").lower()

                info = f"**condition:** {desc}\n**temperature:** {temp_c}°c / {temp_f}°f (feels like {feels_c}°c / {feels_f}°f)\n**humidity:** {humidity}%\n**wind:** {wind_mph} mph\n**location:** {city}, {country}"
                await ctx.send(embed=fleed_embed(title=f"weather: {city}", description=info, author=ctx.author))
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch weather information", ctx.author))

    # minecraft server status
    @commands.command(name="mcstatus", aliases=["mcserver", "mcsrv"])
    async def minecraft_server(self, ctx, server_ip: str):
        try:
            url = f"https://api.mcsrvstat.us/3/{server_ip}"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                online = data.get("online", False)
                if not online:
                    return await ctx.send(embed=warn_embed(f"server `{server_ip.lower()}` is currently offline", ctx.author))

                players = data.get("players", {})
                online_p = players.get("online", 0)
                max_p = players.get("max", 0)
                version = data.get("version", "unknown")
                motd_clean = " ".join(data.get("motd", {}).get("clean", []))

                desc = f"**status:** online\n**players:** {online_p:,} / {max_p:,}\n**version:** {version}\n**motd:** {motd_clean.lower()}"
                embed = fleed_embed(title=f"minecraft — {server_ip.lower()}", description=desc, author=ctx.author)
                if data.get("icon"):
                    embed.set_thumbnail(url=f"https://api.mcsrvstat.us/icon/{server_ip}")
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch minecraft server info", ctx.author))

    # ip lookup
    @commands.command(name="ipinfo", aliases=["ip", "geoip"])
    async def ipinfo(self, ctx, ip_address: str):
        try:
            url = f"http://ip-api.com/json/{ip_address}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,query"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                if data.get("status") != "success":
                    return await ctx.send(embed=warn_embed(f"invalid ip or lookup failed: {data.get('message', 'error')}", ctx.author))

                desc = f"**ip:** `{data.get('query')}`\n**country:** {data.get('country', '').lower()} ({data.get('countryCode')})\n**city:** {data.get('city', '').lower()}, {data.get('regionName', '').lower()}\n**isp:** {data.get('isp', '').lower()}\n**org:** {data.get('org', '').lower()}\n**timezone:** `{data.get('timezone')}`"
                await ctx.send(embed=fleed_embed(title="ip lookup", description=desc, author=ctx.author))
        except Exception:
            await ctx.send(embed=error_embed("failed to lookup ip address", ctx.author))

    # qr code generator
    @commands.command(name="qrcode", aliases=["qr"])
    async def qrcode(self, ctx, *, text: str):
        encoded = urllib.parse.quote(text)
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded}"
        embed = fleed_embed(title="qr code", author=ctx.author)
        embed.set_image(url=qr_url)
        await ctx.send(embed=embed)

    # fortnite
    @commands.group(name="fortnite", invoke_without_command=True)
    async def fortnite_group(self, ctx):
        await send_group_help(ctx, ctx.command)

    @fortnite_group.command(name="map")
    async def fortnite_map(self, ctx):
        try:
            url = "https://fortnite-api.com/v1/map"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                map_url = data.get("data", {}).get("images", {}).get("pois")
                embed = fleed_embed(title="fortnite map & pois", author=ctx.author)
                if map_url:
                    embed.set_image(url=map_url)
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch fortnite map", ctx.author))

    @fortnite_group.command(name="news")
    async def fortnite_news(self, ctx):
        try:
            url = "https://fortnite-api.com/v2/news"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                motds = data.get("data", {}).get("br", {}).get("motds", [])
                if not motds:
                    return await ctx.send(embed=warn_embed("no current fortnite news found", ctx.author))
                top = motds[0]
                desc = f"**{top.get('title', '').lower()}**\n{top.get('body', '').lower()}"
                embed = fleed_embed(title="fortnite news", description=desc, author=ctx.author)
                if top.get("image"):
                    embed.set_image(url=top.get("image"))
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch fortnite news", ctx.author))

    # pypi
    @commands.command(name="pypi")
    async def pypi_cmd(self, ctx, *, package: str):
        try:
            url = f"https://pypi.org/pypi/{package.lower()}/json"
            async with self.session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return await ctx.send(embed=warn_embed(f"pypi package `{package.lower()}` not found", ctx.author))
                data = await resp.json(content_type=None)
                info = data.get("info", {})
                version = info.get("version", "unknown")
                summary = info.get("summary", "no summary").lower()
                author = info.get("author", "unknown").lower()
                license_type = info.get("license", "unknown")

                desc = f"**command:** `pip install {package.lower()}`\n**version:** `{version}`\n**author:** {author}\n**license:** {license_type}\n\n{summary}"
                await ctx.send(embed=fleed_embed(title=f"pypi — {package.lower()}", description=desc, author=ctx.author))
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch pypi package", ctx.author))



    # stickymessage
    @commands.group(name="stickymessage", invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def stickymessage(self, ctx):
        await send_group_help(ctx, ctx.command)

    @stickymessage.command(name="add", aliases=["create", "set"])
    async def stickymessage_add(self, ctx, channel: discord.TextChannel, *, content: str):
        await self.bot.db.execute("INSERT OR REPLACE INTO sticky_messages (guild_id, channel_id, content) VALUES (?, ?, ?)", (ctx.guild.id, channel.id, content))
        await ctx.send(embed=success_embed(f"added sticky message to {channel.mention}", ctx.author))

    @stickymessage.command(name="remove", aliases=["delete", "del"])
    async def stickymessage_remove(self, ctx, channel: discord.TextChannel):
        await self.bot.db.execute("DELETE FROM sticky_messages WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, channel.id))
        await ctx.send(embed=success_embed(f"removed sticky message from {channel.mention}", ctx.author))

    # google search
    @commands.command(name="google", aliases=["search", "g"])
    async def google_cmd(self, ctx, *, query: str):
        encoded = urllib.parse.quote(query)
        desc = f"[**Search results for `{query.lower()}`**](https://www.google.com/search?q={encoded})"
        await ctx.send(embed=fleed_embed(title="google search", description=desc, author=ctx.author))

    # timer
    @commands.command(name="timer")
    async def timer_cmd(self, ctx, seconds: int, *, label: str = "timer"):
        if seconds < 1 or seconds > 86400:
            return await ctx.send(embed=error_embed("timer must be between 1 second and 24 hours", ctx.author))
        await self.bot.db.execute(
            "INSERT INTO reminders (guild_id, channel_id, user_id, task, remind_at, kind) VALUES (?, ?, ?, ?, ?, 'timer')",
            (ctx.guild.id, ctx.channel.id, ctx.author.id, label, int(time.time()) + seconds),
        )
        await ctx.send(embed=success_embed(f"timer set for **{seconds}s** — {label.lower()}", ctx.author))

    # reminder
    @commands.group(name="reminder", aliases=["remind", "remindme"], invoke_without_command=True)
    async def reminder_group(self, ctx, time_str: str = None, *, task: str = "reminder"):
        if not time_str:
            return await send_group_help(ctx, ctx.command, "utility")
        seconds = self._parse_duration(time_str)
        if not seconds:
            return await ctx.send(embed=error_embed("use a duration such as `10m`, `2h30m`, or `1d`", ctx.author))
        await self.bot.db.execute(
            "INSERT INTO reminders (guild_id, channel_id, user_id, task, remind_at, kind) VALUES (?, ?, ?, ?, ?, 'reminder')",
            (ctx.guild.id, ctx.channel.id, ctx.author.id, task, int(time.time()) + seconds),
        )
        await ctx.send(embed=success_embed(f"reminder set for **{time_str.lower()}**: {task.lower()}", ctx.author))

    @reminder_group.command(name="list")
    async def reminder_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT id, task, remind_at, kind FROM reminders WHERE guild_id = ? AND user_id = ? ORDER BY remind_at", (ctx.guild.id, ctx.author.id))
        lines = [f"`{r['id']}` {r['kind']}: {r['task']} — <t:{r['remind_at']}:R>" for r in rows]
        await ctx.send(embed=fleed_embed(title="active reminders", description="\n".join(lines) or "no active reminders pending", author=ctx.author))

    @reminder_group.command(name="cancel", aliases=["delete", "remove"])
    async def reminder_cancel(self, ctx, reminder_id: int):
        await self.bot.db.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, ctx.author.id))
        await ctx.send(embed=success_embed(f"cancelled reminder `{reminder_id}`", ctx.author))

    # bumpreminder
    @commands.command(name="bumpreminder", aliases=["bumpremind"])
    @commands.has_permissions(manage_guild=True)
    async def bumpreminder_cmd(self, ctx, status: str = "on"):
        val = status.lower() in ["on", "enable", "true", "1"]
        await self.bot.db.execute(
            "INSERT INTO bump_reminders (guild_id, channel_id, enabled) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?, enabled = ?",
            (ctx.guild.id, ctx.channel.id, int(val), ctx.channel.id, int(val)),
        )
        await ctx.send(embed=success_embed(f"disboard bump reminder set to `{'enabled' if val else 'disabled'}`", ctx.author))

    # webhook
    @commands.group(name="webhook", invoke_without_command=True)
    @commands.has_permissions(manage_webhooks=True)
    async def webhook_group(self, ctx):
        await send_group_help(ctx, ctx.command, "utility")

    @webhook_group.command(name="create")
    async def webhook_create(self, ctx, name: str, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        wh = await ch.create_webhook(name=name)
        await ctx.send(embed=success_embed(f"created webhook `{wh.name}` in {ch.mention}\nurl: `{wh.url}`", ctx.author))

    @webhook_group.command(name="delete")
    async def webhook_delete(self, ctx, webhook_id: int):
        whs = await ctx.guild.webhooks()
        target = discord.utils.get(whs, id=webhook_id)
        if not target:
            return await ctx.send(embed=error_embed("webhook not found", ctx.author))
        await target.delete()
        await ctx.send(embed=success_embed(f"deleted webhook `{target.name}`", ctx.author))

    @webhook_group.command(name="list")
    async def webhook_list(self, ctx):
        whs = await ctx.guild.webhooks()
        if not whs:
            return await ctx.send(embed=warn_embed("no webhooks created in this server", ctx.author))
        lines = [f"`{w.name}` (`{w.id}`) in {w.channel.mention}" for w in whs[:15]]
        await ctx.send(embed=fleed_embed(title="server webhooks", description="\n".join(lines), author=ctx.author))

    # emoji
    @commands.group(name="emoji", aliases=["emojis", "e"], invoke_without_command=True)
    async def emoji_group(self, ctx, emoji: discord.PartialEmoji = None):
        if not emoji:
            return await send_group_help(ctx, ctx.command, "utility")
        embed = fleed_embed(title=f"emoji: {emoji.name}", description=f"id: `{emoji.id}`\nanimated: `{emoji.animated}`", author=ctx.author)
        embed.set_image(url=emoji.url)
        await ctx.send(embed=embed)

    @emoji_group.command(name="add", aliases=["steal", "create"])
    @commands.has_permissions(manage_emojis=True)
    async def emoji_add(self, ctx, emoji: discord.PartialEmoji, *, name: str = None):
        name = name or emoji.name
        async with self.session.get(emoji.url) as resp:
            if resp.status != 200:
                return await ctx.send(embed=error_embed("failed to download emoji", ctx.author))
            data = await resp.read()
            new_e = await ctx.guild.create_custom_emoji(name=name, image=data)
            await ctx.send(embed=success_embed(f"created emoji {new_e}", ctx.author))

    @emoji_group.command(name="remove", aliases=["delete", "del"])
    @commands.has_permissions(manage_emojis=True)
    async def emoji_remove(self, ctx, emoji: discord.Emoji):
        await emoji.delete()
        await ctx.send(embed=success_embed(f"deleted emoji `{emoji.name}`", ctx.author))

    # sticker
    @commands.group(name="sticker", aliases=["stickers"], invoke_without_command=True)
    async def sticker_group(self, ctx):
        await send_group_help(ctx, ctx.command, "utility")

    @sticker_group.command(name="add", aliases=["steal"])
    @commands.has_permissions(manage_emojis_and_stickers=True)
    async def sticker_add(self, ctx, name: str):
        await ctx.send(embed=success_embed(f"created sticker `{name.lower()}`", ctx.author))

    @commands.command(name="calc", aliases=["calculate", "math", "evaluate"])
    async def calc_cmd(self, ctx, *, expression: str):
        import ast
        try:
            tree = ast.parse(expression, mode='eval')
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.operator, ast.unaryop)):
                    return await ctx.send(embed=error_embed("expression contains unsupported operators", ctx.author))
            result = eval(compile(tree, '<string>', 'eval'))
            await ctx.send(embed=fleed_embed(title="calculator", description=f"`{expression}` = `{result}`", author=ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to calculate: {str(e).lower()}", ctx.author))

    @commands.command(name="poll")
    async def poll_cmd(self, ctx, question: str, *options: str):
        if len(options) < 2:
            return await ctx.send(embed=warn_embed("provide at least 2 options for the poll", ctx.author))
        if len(options) > 10:
            return await ctx.send(embed=warn_embed("maximum 10 options allowed", ctx.author))
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        desc = "\n".join(f"{emojis[i]} {opt.lower()}" for i, opt in enumerate(options))
        embed = fleed_embed(title=question.lower(), description=desc, author=ctx.author)
        embed.set_footer(text=f"poll by {ctx.author.name.lower()}")
        msg = await ctx.send(embed=embed)
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])

    @commands.command(name="quickpoll", aliases=["yesno", "ynpoll"])
    async def quickpoll_cmd(self, ctx, *, question: str):
        embed = fleed_embed(title="poll", description=question.lower(), author=ctx.author)
        embed.set_footer(text=f"asked by {ctx.author.name.lower()}")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    @commands.command(name="snowflake", aliases=["inspectid", "parseid"])
    async def snowflake_cmd(self, ctx, snowflake_id: int):
        created_at = discord.utils.snowflake_time(snowflake_id)
        internal_worker_id = (snowflake_id & 0x3E0000) >> 17
        internal_process_id = (snowflake_id & 0x1F000) >> 12
        increment = snowflake_id & 0xFFF
        ts = int(created_at.timestamp())
        desc = (
            f"**ID:** `{snowflake_id}`\n"
            f"**Created:** <t:{ts}:F> (<t:{ts}:R>)\n"
            f"**Worker ID:** `{internal_worker_id}`\n"
            f"**Process ID:** `{internal_process_id}`\n"
            f"**Sequence:** `{increment}`"
        )
        await ctx.send(embed=fleed_embed(title="discord snowflake inspector", description=desc, author=ctx.author))

    @commands.command(name="timestamp", aliases=["ts", "epoch"])
    async def timestamp_cmd(self, ctx, unix_time: int = None):
        ts = unix_time or int(discord.utils.utcnow().timestamp())
        desc = (
            f"**Unix Timestamp:** `{ts}`\n\n"
            f"**Relative:** `<t:{ts}:R>` -> <t:{ts}:R>\n"
            f"**Short Time:** `<t:{ts}:t>` -> <t:{ts}:t>\n"
            f"**Long Time:** `<t:{ts}:T>` -> <t:{ts}:T>\n"
            f"**Short Date:** `<t:{ts}:d>` -> <t:{ts}:d>\n"
            f"**Long Date:** `<t:{ts}:D>` -> <t:{ts}:D>\n"
            f"**Short Date/Time:** `<t:{ts}:f>` -> <t:{ts}:f>\n"
            f"**Long Date/Time:** `<t:{ts}:F>` -> <t:{ts}:F>"
        )
        await ctx.send(embed=fleed_embed(title="discord timestamp formatter", description=desc, author=ctx.author))

    @commands.command(name="color", aliases=["hex", "colour"])
    async def color_cmd(self, ctx, hex_code: str):
        import colorsys
        c = hex_code.lstrip('#')
        if len(c) == 3:
            c = "".join(x*2 for x in c)
        if len(c) != 6 or not all(x in "0123456789abcdefABCDEF" for x in c):
            return await ctx.send(embed=error_embed("invalid 6-character hex code", ctx.author))
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
        lum = 0.2126*(r/255) + 0.7152*(g/255) + 0.0722*(b/255)
        comp_r, comp_g, comp_b = 255 - r, 255 - g, 255 - b
        desc = (
            f"**Hex:** `#{c.lower()}`\n"
            f"**RGB:** `rgb({r}, {g}, {b})`\n"
            f"**HSL:** `hsl({int(h*360)}, {int(s*100)}%, {int(l*100)}%)`\n"
            f"**Luminance:** `{lum:.4f}` ({'light' if lum > 0.5 else 'dark'})\n"
            f"**Complementary:** `#{comp_r:02x}{comp_g:02x}{comp_b:02x}`"
        )
        embed = fleed_embed(title=f"color: #{c.lower()}", description=desc, author=ctx.author)
        embed.color = int(c, 16)
        await ctx.send(embed=embed)

    @commands.command(name="base64_encode", aliases=["b64encode", "b64enc"])
    async def base64_encode(self, ctx, *, text: str):
        import base64
        enc = base64.b64encode(text.encode()).decode()
        await ctx.send(embed=fleed_embed(title="base64 encode", description=f"```{enc}```", author=ctx.author))

    @commands.command(name="base64_decode", aliases=["b64decode", "b64dec"])
    async def base64_decode(self, ctx, *, text: str):
        import base64
        try:
            dec = base64.b64decode(text.encode()).decode('utf-8', errors='replace')
            await ctx.send(embed=fleed_embed(title="base64 decode", description=f"```{dec}```", author=ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"invalid base64: {str(e).lower()}", ctx.author))

    @commands.command(name="morse_encode", aliases=["morse"])
    async def morse_encode(self, ctx, *, text: str):
        morse_dict = {'A':'.-','B':'-...','C':'-.-.','D':'-..','E':'.','F':'..-.','G':'--.','H':'....','I':'..','J':'.---','K':'-.-','L':'.-..','M':'--','N':'-.','O':'---','P':'.--.','Q':'--.-','R':'.-.','S':'...','T':'-','U':'..-','V':'...-','W':'.--','X':'-..-','Y':'-.--','Z':'--..','1':'.----','2':'..---','3':'...--','4':'....-','5':'.....','6':'-....','7':'--...','8':'---..','9':'----.','0':'-----',' ':'/'}
        res = ' '.join(morse_dict.get(c.upper(), c) for c in text)
        await ctx.send(embed=fleed_embed(title="morse code", description=f"```{res}```", author=ctx.author))

    @commands.command(name="pingrole", aliases=["roleping", "mentionrole"])
    @commands.has_permissions(mention_everyone=True)
    async def pingrole(self, ctx, role: discord.Role, *, message: str = ""):
        """ping a role even if it's unmentionable by temporarily making it mentionable (requires mention everyone permission)"""
        was_mentionable = role.mentionable
        try:
            if not was_mentionable and ctx.guild.me.guild_permissions.manage_roles:
                await role.edit(mentionable=True, reason=f"pingrole command by {ctx.author}")
            
            allowed = discord.AllowedMentions(roles=[role], users=False, everyone=False)
            content = f"{role.mention} {message}".strip()
            await ctx.send(content, allowed_mentions=allowed)
        finally:
            if not was_mentionable and ctx.guild.me.guild_permissions.manage_roles:
                await role.edit(mentionable=False, reason="pingrole command reset")



    @commands.command(name="abs_val", help="Calculate absolute value of a number")
    async def abs_val_cmd(self, ctx, number: float):
        res = abs(number)
        await ctx.send(embed=fleed_embed(title='absolute value', description=f'|{number:g}| = **{res:g}**', author=ctx.author))

    @commands.command(name="round_num", help="Round a number to given decimal places")
    async def round_num_cmd(self, ctx, number: float, decimals: int = 0):
        res = round(number, decimals)
        await ctx.send(embed=fleed_embed(title='round number', description=f'{number} rounded to {decimals} decimals = **{res}**', author=ctx.author))

    @commands.command(name="floor_num", help="Compute mathematical floor (greatest integer <= x)")
    async def floor_num_cmd(self, ctx, number: float):
        import math
        res = math.floor(number)
        await ctx.send(embed=fleed_embed(title='floor', description=f'⌊{number:g}⌋ = **{res}**', author=ctx.author))

    @commands.command(name="ceil_num", help="Compute mathematical ceiling (smallest integer >= x)")
    async def ceil_num_cmd(self, ctx, number: float):
        import math
        res = math.ceil(number)
        await ctx.send(embed=fleed_embed(title='ceiling', description=f'⌈{number:g}⌉ = **{res}**', author=ctx.author))

    @commands.command(name="is_even", help="Check if an integer is even or odd")
    async def is_even_cmd(self, ctx, number: int):
        res = (number % 2 == 0)
        desc = f'**{number:,}** is **even**' if res else f'**{number:,}** is **odd**'
        await ctx.send(embed=fleed_embed(title='even/odd check', description=desc, author=ctx.author))

    @commands.command(name="sign_num", help="Check the sign of a number (+, -, or 0)")
    async def sign_num_cmd(self, ctx, number: float):
        import math
        sign = 'positive (+1)' if number > 0 else 'negative (-1)' if number < 0 else 'zero (0)'
        await ctx.send(embed=fleed_embed(title='sign check', description=f'sign of {number:g} is **{sign}**', author=ctx.author))

    @commands.command(name="int_div", help="Perform integer division with quotient and remainder")
    async def int_div_cmd(self, ctx, a: int, b: int):
        if b == 0: return await ctx.send(embed=error_embed('division by zero', ctx.author))
        q, r = divmod(a, b)
        await ctx.send(embed=fleed_embed(title='integer division', description=f'{a} ÷ {b} = **{q}** with remainder **{r}**', author=ctx.author))

    @commands.command(name="clamp_num", help="Clamp a value between minimum and maximum bounds")
    async def clamp_num_cmd(self, ctx, val: float, min_val: float, max_val: float):
        res = max(min_val, min(val, max_val))
        await ctx.send(embed=fleed_embed(title='clamp value', description=f'clamped {val:g} into [{min_val:g}, {max_val:g}] = **{res:g}**', author=ctx.author))

    @commands.command(name="lerp_calc", help="Compute linear interpolation between a and b at t")
    async def lerp_calc_cmd(self, ctx, a: float, b: float, t: float):
        res = a + (b - a) * t
        await ctx.send(embed=fleed_embed(title='linear interpolation', description=f'lerp({a:g}, {b:g}, {t:g}) = **{res:.6f}**', author=ctx.author))

    @commands.command(name="sum_nums", help="Calculate the sum of a list of numbers")
    async def sum_nums_cmd(self, ctx, *numbers: float):
        if not numbers: return await ctx.send(embed=error_embed('provide at least one number', ctx.author))
        res = sum(numbers)
        await ctx.send(embed=fleed_embed(title='sum', description=f'sum of {len(numbers)} numbers = **{res:g}**', author=ctx.author))

    @commands.command(name="product_nums", help="Calculate the product of a list of numbers")
    async def product_nums_cmd(self, ctx, *numbers: float):
        if not numbers: return await ctx.send(embed=error_embed('provide at least one number', ctx.author))
        import math
        res = math.prod(numbers)
        await ctx.send(embed=fleed_embed(title='product', description=f'product of {len(numbers)} numbers = **{res:g}**', author=ctx.author))

    @commands.command(name="min_num", help="Find the minimum value from arguments")
    async def min_num_cmd(self, ctx, *numbers: float):
        if not numbers: return await ctx.send(embed=error_embed('provide at least one number', ctx.author))
        await ctx.send(embed=fleed_embed(title='minimum value', description=f'min = **{min(numbers):g}**', author=ctx.author))

    @commands.command(name="max_num", help="Find the maximum value from arguments")
    async def max_num_cmd(self, ctx, *numbers: float):
        if not numbers: return await ctx.send(embed=error_embed('provide at least one number', ctx.author))
        await ctx.send(embed=fleed_embed(title='maximum value', description=f'max = **{max(numbers):g}**', author=ctx.author))

    @commands.command(name="range_num", help="Calculate the statistical range (max - min) of numbers")
    async def range_num_cmd(self, ctx, *numbers: float):
        if len(numbers) < 2: return await ctx.send(embed=error_embed('provide at least two numbers', ctx.author))
        res = max(numbers) - min(numbers)
        await ctx.send(embed=fleed_embed(title='range', description=f'range = **{res:g}** (min: {min(numbers):g}, max: {max(numbers):g})', author=ctx.author))

    @commands.command(name="geometric_mean", help="Calculate geometric mean of positive numbers")
    async def geometric_mean_cmd(self, ctx, *numbers: float):
        if not numbers or any(n <= 0 for n in numbers): return await ctx.send(embed=error_embed('provide positive numbers only', ctx.author))
        import statistics
        gm = statistics.geometric_mean(numbers)
        await ctx.send(embed=fleed_embed(title='geometric mean', description=f'geometric mean = **{gm:.6f}**', author=ctx.author))

    @commands.command(name="harmonic_mean", help="Calculate harmonic mean of positive numbers")
    async def harmonic_mean_cmd(self, ctx, *numbers: float):
        if not numbers or any(n <= 0 for n in numbers): return await ctx.send(embed=error_embed('provide positive numbers only', ctx.author))
        import statistics
        hm = statistics.harmonic_mean(numbers)
        await ctx.send(embed=fleed_embed(title='harmonic mean', description=f'harmonic mean = **{hm:.6f}**', author=ctx.author))

    @commands.command(name="circle_area", help="Calculate area of a circle given radius")
    async def circle_area_cmd(self, ctx, radius: float):
        import math
        if radius < 0: return await ctx.send(embed=error_embed('radius cannot be negative', ctx.author))
        area = math.pi * radius * radius
        await ctx.send(embed=fleed_embed(title='circle area', description=f'area for r={radius:g} = **{area:.4f}**', author=ctx.author))

    @commands.command(name="circle_perimeter", help="Calculate circumference (perimeter) of a circle")
    async def circle_perimeter_cmd(self, ctx, radius: float):
        import math
        if radius < 0: return await ctx.send(embed=error_embed('radius cannot be negative', ctx.author))
        circ = 2 * math.pi * radius
        await ctx.send(embed=fleed_embed(title='circle circumference', description=f'circumference for r={radius:g} = **{circ:.4f}**', author=ctx.author))

    @commands.command(name="sphere_volume", help="Calculate volume of a sphere given radius")
    async def sphere_volume_cmd(self, ctx, radius: float):
        import math
        if radius < 0: return await ctx.send(embed=error_embed('radius cannot be negative', ctx.author))
        vol = (4/3) * math.pi * (radius**3)
        await ctx.send(embed=fleed_embed(title='sphere volume', description=f'volume for r={radius:g} = **{vol:.4f}**', author=ctx.author))

    @commands.command(name="sphere_surface", help="Calculate surface area of a sphere given radius")
    async def sphere_surface_cmd(self, ctx, radius: float):
        import math
        if radius < 0: return await ctx.send(embed=error_embed('radius cannot be negative', ctx.author))
        sa = 4 * math.pi * (radius**2)
        await ctx.send(embed=fleed_embed(title='sphere surface area', description=f'surface area for r={radius:g} = **{sa:.4f}**', author=ctx.author))

    @commands.command(name="cylinder_volume", help="Calculate volume of a cylinder")
    async def cylinder_volume_cmd(self, ctx, radius: float, height: float):
        import math
        if radius < 0 or height < 0: return await ctx.send(embed=error_embed('dimensions cannot be negative', ctx.author))
        vol = math.pi * (radius**2) * height
        await ctx.send(embed=fleed_embed(title='cylinder volume', description=f'volume for r={radius:g}, h={height:g} = **{vol:.4f}**', author=ctx.author))

    @commands.command(name="cone_volume", help="Calculate volume of a cone")
    async def cone_volume_cmd(self, ctx, radius: float, height: float):
        import math
        if radius < 0 or height < 0: return await ctx.send(embed=error_embed('dimensions cannot be negative', ctx.author))
        vol = (1/3) * math.pi * (radius**2) * height
        await ctx.send(embed=fleed_embed(title='cone volume', description=f'volume for r={radius:g}, h={height:g} = **{vol:.4f}**', author=ctx.author))

    @commands.command(name="triangle_area", help="Calculate area of a triangle given base and height")
    async def triangle_area_cmd(self, ctx, base: float, height: float):
        if base < 0 or height < 0: return await ctx.send(embed=error_embed('dimensions cannot be negative', ctx.author))
        area = 0.5 * base * height
        await ctx.send(embed=fleed_embed(title='triangle area', description=f'area for b={base:g}, h={height:g} = **{area:.4f}**', author=ctx.author))

    @commands.command(name="heron_area", help="Calculate triangle area using Heron's formula given 3 sides")
    async def heron_area_cmd(self, ctx, a: float, b: float, c: float):
        import math
        if a <= 0 or b <= 0 or c <= 0 or (a+b<=c) or (a+c<=b) or (b+c<=a): return await ctx.send(embed=error_embed('invalid triangle side lengths', ctx.author))
        s = (a + b + c) / 2
        area = math.sqrt(s * (s - a) * (s - b) * (s - c))
        await ctx.send(embed=fleed_embed(title='triangle area (heron)', description=f'sides ({a:g}, {b:g}, {c:g}) -> area = **{area:.4f}**', author=ctx.author))

    @commands.command(name="yards_to_meters", help="Convert yards to meters")
    async def yards_to_meters_cmd(self, ctx, yards: float):
        m = yards * 0.9144
        await ctx.send(embed=fleed_embed(title='length conversion', description=f'{yards:g} yd = **{m:.4f} m**', author=ctx.author))

    @commands.command(name="meters_to_yards", help="Convert meters to yards")
    async def meters_to_yards_cmd(self, ctx, meters: float):
        yd = meters / 0.9144
        await ctx.send(embed=fleed_embed(title='length conversion', description=f'{meters:g} m = **{yd:.4f} yd**', author=ctx.author))

    @commands.command(name="nautical_to_km", help="Convert nautical miles to kilometers")
    async def nautical_to_km_cmd(self, ctx, nmi: float):
        km = nmi * 1.852
        await ctx.send(embed=fleed_embed(title='distance conversion', description=f'{nmi:g} nmi = **{km:.4f} km**', author=ctx.author))

    @commands.command(name="km_to_nautical", help="Convert kilometers to nautical miles")
    async def km_to_nautical_cmd(self, ctx, km: float):
        nmi = km / 1.852
        await ctx.send(embed=fleed_embed(title='distance conversion', description=f'{km:g} km = **{nmi:.4f} nmi**', author=ctx.author))

    @commands.command(name="lightyears_to_km", help="Convert light-years to kilometers")
    async def lightyears_to_km_cmd(self, ctx, ly: float):
        km = ly * 9.461e12
        await ctx.send(embed=fleed_embed(title='astronomical distance', description=f'{ly:g} ly = **{km:.4e} km**', author=ctx.author))

    @commands.command(name="au_to_km", help="Convert astronomical units (AU) to kilometers")
    async def au_to_km_cmd(self, ctx, au: float):
        km = au * 149597870.7
        await ctx.send(embed=fleed_embed(title='astronomical distance', description=f'{au:g} AU = **{km:,.2f} km**', author=ctx.author))

    @commands.command(name="parsecs_to_ly", help="Convert parsecs to light-years")
    async def parsecs_to_ly_cmd(self, ctx, pc: float):
        ly = pc * 3.26156
        await ctx.send(embed=fleed_embed(title='astronomical distance', description=f'{pc:g} pc = **{ly:.4f} ly**', author=ctx.author))

    @commands.command(name="tonnes_to_tons", help="Convert metric tonnes to US short tons")
    async def tonnes_to_tons_cmd(self, ctx, tonnes: float):
        tons = tonnes * 1.10231
        await ctx.send(embed=fleed_embed(title='weight conversion', description=f'{tonnes:g} tonnes = **{tons:.4f} US tons**', author=ctx.author))

    @commands.command(name="tons_to_tonnes", help="Convert US short tons to metric tonnes")
    async def tons_to_tonnes_cmd(self, ctx, tons: float):
        tonnes = tons / 1.10231
        await ctx.send(embed=fleed_embed(title='weight conversion', description=f'{tons:g} US tons = **{tonnes:.4f} tonnes**', author=ctx.author))

    @commands.command(name="stones_to_kg", help="Convert British stones to kilograms")
    async def stones_to_kg_cmd(self, ctx, stones: float):
        kg = stones * 6.35029
        await ctx.send(embed=fleed_embed(title='weight conversion', description=f'{stones:g} st = **{kg:.4f} kg**', author=ctx.author))

    @commands.command(name="kg_to_stones", help="Convert kilograms to British stones")
    async def kg_to_stones_cmd(self, ctx, kg: float):
        st = kg / 6.35029
        await ctx.send(embed=fleed_embed(title='weight conversion', description=f'{kg:g} kg = **{st:.4f} st**', author=ctx.author))

    @commands.command(name="carats_to_grams", help="Convert gemstone carats to grams")
    async def carats_to_grams_cmd(self, ctx, carats: float):
        g = carats * 0.2
        await ctx.send(embed=fleed_embed(title='weight conversion', description=f'{carats:g} ct = **{g:.4f} g**', author=ctx.author))

    @commands.command(name="ml_to_floz", help="Convert milliliters to US fluid ounces")
    async def ml_to_floz_cmd(self, ctx, ml: float):
        oz = ml * 0.033814
        await ctx.send(embed=fleed_embed(title='volume conversion', description=f'{ml:g} mL = **{oz:.4f} fl oz**', author=ctx.author))

    @commands.command(name="floz_to_ml", help="Convert US fluid ounces to milliliters")
    async def floz_to_ml_cmd(self, ctx, floz: float):
        ml = floz / 0.033814
        await ctx.send(embed=fleed_embed(title='volume conversion', description=f'{floz:g} fl oz = **{ml:.4f} mL**', author=ctx.author))

    @commands.command(name="cups_to_ml", help="Convert US cups to milliliters")
    async def cups_to_ml_cmd(self, ctx, cups: float):
        ml = cups * 236.588
        await ctx.send(embed=fleed_embed(title='volume conversion', description=f'{cups:g} cups = **{ml:.2f} mL**', author=ctx.author))

    @commands.command(name="tablespoons_to_ml", help="Convert tablespoons to milliliters")
    async def tablespoons_to_ml_cmd(self, ctx, tbsp: float):
        ml = tbsp * 14.7868
        await ctx.send(embed=fleed_embed(title='volume conversion', description=f'{tbsp:g} tbsp = **{ml:.2f} mL**', author=ctx.author))

    @commands.command(name="teaspoons_to_ml", help="Convert teaspoons to milliliters")
    async def teaspoons_to_ml_cmd(self, ctx, tsp: float):
        ml = tsp * 4.92892
        await ctx.send(embed=fleed_embed(title='volume conversion', description=f'{tsp:g} tsp = **{ml:.2f} mL**', author=ctx.author))

    @commands.command(name="mps_to_kmh", help="Convert meters per second to km/h")
    async def mps_to_kmh_cmd(self, ctx, mps: float):
        kmh = mps * 3.6
        await ctx.send(embed=fleed_embed(title='speed conversion', description=f'{mps:g} m/s = **{kmh:.2f} km/h**', author=ctx.author))

    @commands.command(name="mach_to_kmh", help="Convert Mach number (speed of sound in air) to km/h")
    async def mach_to_kmh_cmd(self, ctx, mach: float):
        kmh = mach * 1234.8
        await ctx.send(embed=fleed_embed(title='speed conversion', description=f'Mach {mach:g} = **{kmh:,.2f} km/h**', author=ctx.author))

    @commands.command(name="bits_to_bytes", help="Convert raw bits to bytes")
    async def bits_to_bytes_cmd(self, ctx, bits: int):
        b = bits / 8
        await ctx.send(embed=fleed_embed(title='data conversion', description=f'{bits:,} bits = **{b:g} Bytes**', author=ctx.author))

    @commands.command(name="bytes_to_bits", help="Convert bytes to bits")
    async def bytes_to_bits_cmd(self, ctx, bytes_count: int):
        b = bytes_count * 8
        await ctx.send(embed=fleed_embed(title='data conversion', description=f'{bytes_count:,} Bytes = **{b:,} bits**', author=ctx.author))

    @commands.command(name="kib_to_kb", help="Convert binary Kibibytes (KiB) to decimal Kilobytes (KB)")
    async def kib_to_kb_cmd(self, ctx, kib: float):
        kb = kib * 1.024
        await ctx.send(embed=fleed_embed(title='data conversion', description=f'{kib:g} KiB = **{kb:.4f} KB**', author=ctx.author))

    @commands.command(name="mib_to_mb", help="Convert binary Mebibytes (MiB) to decimal Megabytes (MB)")
    async def mib_to_mb_cmd(self, ctx, mib: float):
        mb = mib * 1.048576
        await ctx.send(embed=fleed_embed(title='data conversion', description=f'{mib:g} MiB = **{mb:.4f} MB**', author=ctx.author))

    @commands.command(name="gib_to_gb", help="Convert binary Gibibytes (GiB) to decimal Gigabytes (GB)")
    async def gib_to_gb_cmd(self, ctx, gib: float):
        gb = gib * 1.073741824
        await ctx.send(embed=fleed_embed(title='data conversion', description=f'{gib:g} GiB = **{gb:.4f} GB**', author=ctx.author))

    @commands.command(name="seconds_to_hours", help="Convert seconds to hours and minutes breakdown")
    async def seconds_to_hours_cmd(self, ctx, seconds: float):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        await ctx.send(embed=fleed_embed(title='time conversion', description=f'{seconds:g}s = **{int(h)}h {int(m)}m {s:g}s**', author=ctx.author))

    @commands.command(name="hours_to_days", help="Convert hours to days")
    async def hours_to_days_cmd(self, ctx, hours: float):
        d = hours / 24
        await ctx.send(embed=fleed_embed(title='time conversion', description=f'{hours:g} hours = **{d:.4f} days**', author=ctx.author))

    @commands.command(name="days_to_years", help="Convert days to solar years (365.25 days)")
    async def days_to_years_cmd(self, ctx, days: float):
        y = days / 365.25
        await ctx.send(embed=fleed_embed(title='time conversion', description=f'{days:g} days = **{y:.4f} years**', author=ctx.author))

    @commands.command(name="kwh_to_joules", help="Convert kilowatt-hours (kWh) to megajoules")
    async def kwh_to_joules_cmd(self, ctx, kwh: float):
        mj = kwh * 3.6
        await ctx.send(embed=fleed_embed(title='energy conversion', description=f'{kwh:g} kWh = **{mj:,.2f} MJ**', author=ctx.author))

    @commands.command(name="btu_to_joules", help="Convert British Thermal Units (BTU) to joules")
    async def btu_to_joules_cmd(self, ctx, btu: float):
        j = btu * 1055.06
        await ctx.send(embed=fleed_embed(title='energy conversion', description=f'{btu:g} BTU = **{j:,.2f} J**', author=ctx.author))

    @commands.command(name="bar_to_psi", help="Convert bar atmospheric pressure to PSI")
    async def bar_to_psi_cmd(self, ctx, bar: float):
        psi = bar * 14.5038
        await ctx.send(embed=fleed_embed(title='pressure conversion', description=f'{bar:g} bar = **{psi:.4f} PSI**', author=ctx.author))

    @commands.command(name="atm_to_pascal", help="Convert standard atmospheres to Pascals")
    async def atm_to_pascal_cmd(self, ctx, atm: float):
        pa = atm * 101325
        await ctx.send(embed=fleed_embed(title='pressure conversion', description=f'{atm:g} atm = **{pa:,.2f} Pa**', author=ctx.author))

    @commands.command(name="torr_to_pascal", help="Convert Torr (mmHg) to Pascals")
    async def torr_to_pascal_cmd(self, ctx, torr: float):
        pa = torr * 133.322
        await ctx.send(embed=fleed_embed(title='pressure conversion', description=f'{torr:g} Torr = **{pa:.2f} Pa**', author=ctx.author))

    @commands.command(name="text_slugify", help="Transform text into URL-safe slug format")
    async def text_slugify_cmd(self, ctx, *, text: str):
        import re
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', text).strip('-').lower()
        await ctx.send(embed=fleed_embed(title='slugified text', description=f'`{slug}`', author=ctx.author))

    @commands.command(name="text_camelcase", help="Convert text to camelCase")
    async def text_camelcase_cmd(self, ctx, *, text: str):
        words = re.sub(r'[^a-zA-Z0-9]', ' ', text).split()
        if not words: return await ctx.send(embed=error_embed('empty text', ctx.author))
        res = words[0].lower() + ''.join(w.capitalize() for w in words[1:])
        await ctx.send(embed=fleed_embed(title='camelCase', description=f'`{res}`', author=ctx.author))

    @commands.command(name="text_snakecase", help="Convert text to snake_case")
    async def text_snakecase_cmd(self, ctx, *, text: str):
        words = re.sub(r'[^a-zA-Z0-9]', ' ', text).split()
        res = '_'.join(w.lower() for w in words)
        await ctx.send(embed=fleed_embed(title='snake_case', description=f'`{res}`', author=ctx.author))

    @commands.command(name="text_kebabcase", help="Convert text to kebab-case")
    async def text_kebabcase_cmd(self, ctx, *, text: str):
        words = re.sub(r'[^a-zA-Z0-9]', ' ', text).split()
        res = '-'.join(w.lower() for w in words)
        await ctx.send(embed=fleed_embed(title='kebab-case', description=f'`{res}`', author=ctx.author))

    @commands.command(name="text_pascalcase", help="Convert text to PascalCase")
    async def text_pascalcase_cmd(self, ctx, *, text: str):
        words = re.sub(r'[^a-zA-Z0-9]', ' ', text).split()
        res = ''.join(w.capitalize() for w in words)
        await ctx.send(embed=fleed_embed(title='PascalCase', description=f'`{res}`', author=ctx.author))

    @commands.command(name="text_titlecase", help="Convert text to proper Title Case")
    async def text_titlecase_cmd(self, ctx, *, text: str):
        res = text.title()
        await ctx.send(embed=fleed_embed(title='Title Case', description=res, author=ctx.author))

    @commands.command(name="text_leet", help="Translate text into 1337 (leet) speak")
    async def text_leet_cmd(self, ctx, *, text: str):
        leet_map = {'a':'4','e':'3','l':'1','t':'7','s':'5','o':'0','g':'9','b':'8'}
        out = ''.join(leet_map.get(c.lower(), c) for c in text)
        await ctx.send(embed=fleed_embed(title='leet speak', description=out, author=ctx.author))

    @commands.command(name="text_sponge", help="Apply Mocking SpongeBob alternating case to text")
    async def text_sponge_cmd(self, ctx, *, text: str):
        out = ''.join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(text))
        await ctx.send(embed=fleed_embed(title='mock text', description=out, author=ctx.author))

    @commands.command(name="text_clap", help="Insert clap emojis 👏 between words")
    async def text_clap_cmd(self, ctx, *, text: str):
        words = text.split()
        out = ' 👏 '.join(words)
        await ctx.send(out[:2000])

    @commands.command(name="text_strikethrough", help="Apply markdown strikethrough to text")
    async def text_strikethrough_cmd(self, ctx, *, text: str):
        await ctx.send(f'~~{text[:1990]}~~')

    @commands.command(name="text_spoiler", help="Wrap text inside Discord spoiler tags")
    async def text_spoiler_cmd(self, ctx, *, text: str):
        await ctx.send(f'||{text[:1990]}||')

    @commands.command(name="text_underline", help="Apply markdown underline to text")
    async def text_underline_cmd(self, ctx, *, text: str):
        await ctx.send(f'__{text[:1990]}__')

    @commands.command(name="text_codeblock", help="Wrap code inside formatted markdown codeblock")
    async def text_codeblock_cmd(self, ctx, lang: str, *, code: str):
        await ctx.send(f'```{lang}\n{code[:1980]}\n```')

    @commands.command(name="text_sortlines", help="Sort lines of text alphabetically")
    async def text_sortlines_cmd(self, ctx, *, text: str):
        lines = sorted(text.splitlines())
        out = '\n'.join(lines)
        await ctx.send(embed=fleed_embed(title='sorted lines', description=f'```{out[:4000]}```', author=ctx.author))

    @commands.command(name="text_deduplicatelines", help="Remove duplicate lines from text preserving order")
    async def text_deduplicatelines_cmd(self, ctx, *, text: str):
        lines = text.splitlines()
        seen = set()
        unique = [x for x in lines if not (x in seen or seen.add(x))]
        out = '\n'.join(unique)
        await ctx.send(embed=fleed_embed(title='deduplicated lines', description=f'```{out[:4000]}```', author=ctx.author))

    @commands.command(name="text_shufflewords", help="Randomly shuffle the order of words in text")
    async def text_shufflewords_cmd(self, ctx, *, text: str):
        import random
        words = text.split()
        random.shuffle(words)
        await ctx.send(embed=fleed_embed(title='shuffled words', description=' '.join(words), author=ctx.author))

    @commands.command(name="text_shuffleletters", help="Randomly shuffle characters inside each word")
    async def text_shuffleletters_cmd(self, ctx, *, text: str):
        import random
        def shuf(w):
            if len(w) <= 3: return w
            mid = list(w[1:-1])
            random.shuffle(mid)
            return w[0] + ''.join(mid) + w[-1]
        words = text.split()
        out = ' '.join(shuf(w) for w in words)
        await ctx.send(embed=fleed_embed(title='scrambled words', description=out, author=ctx.author))

    @commands.command(name="text_frequency", help="Compute character frequency breakdown in text")
    async def text_frequency_cmd(self, ctx, *, text: str):
        from collections import Counter
        counts = Counter(text.lower().replace(' ', '').replace('\n', ''))
        top5 = counts.most_common(10)
        desc = '\n'.join([f'`{char}`: {cnt:,} times ({(cnt/len(text))*100:.1f}%)' for char, cnt in top5])
        await ctx.send(embed=fleed_embed(title='character frequency', description=desc, author=ctx.author))

    @commands.command(name="text_palindrome_check", help="Check if text is an exact palindrome")
    async def text_palindrome_check_cmd(self, ctx, *, text: str):
        cleaned = re.sub(r'[^a-zA-Z0-9]', '', text).lower()
        is_pal = (cleaned == cleaned[::-1])
        desc = f'**\"{text}\"** is **a valid palindrome**' if is_pal else f'**\"{text}\"** is **not a palindrome**'
        await ctx.send(embed=fleed_embed(title='palindrome check', description=desc, author=ctx.author))

    @commands.command(name="text_anagram_check", help="Check if two words or phrases are anagrams")
    async def text_anagram_check_cmd(self, ctx, word1: str, word2: str):
        c1 = sorted(re.sub(r'[^a-zA-Z0-9]', '', word1).lower())
        c2 = sorted(re.sub(r'[^a-zA-Z0-9]', '', word2).lower())
        is_ana = (c1 == c2)
        desc = f'`{word1}` and `{word2}` are **anagrams**' if is_ana else f'`{word1}` and `{word2}` are **not anagrams**'
        await ctx.send(embed=fleed_embed(title='anagram check', description=desc, author=ctx.author))

    @commands.command(name="text_hexdump", help="Display formatted hex dump with ASCII sidebar")
    async def text_hexdump_cmd(self, ctx, *, text: str):
        data = text.encode('utf-8')[:256]
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hex_bytes = ' '.join(f'{b:02x}' for b in chunk)
            ascii_repr = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
            lines.append(f'{i:08x}  {hex_bytes:<48}  |{ascii_repr}|')
        await ctx.send(f'```\n' + '\n'.join(lines) + '\n```')

    @commands.command(name="vigenere_encrypt", help="Encrypt text using classical Vigenère polyalphabetic cipher")
    async def vigenere_encrypt_cmd(self, ctx, key: str, *, plaintext: str):
        key_clean = ''.join(filter(str.isalpha, key)).upper()
        if not key_clean: return await ctx.send(embed=error_embed('key must contain alphabet characters', ctx.author))
        res = []
        k_idx = 0
        for ch in plaintext:
            if ch.isalpha():
                base = ord('A') if ch.isupper() else ord('a')
                shift = ord(key_clean[k_idx % len(key_clean)]) - ord('A')
                res.append(chr(base + (ord(ch) - base + shift) % 26))
                k_idx += 1
            else: res.append(ch)
        await ctx.send(embed=fleed_embed(title='vigenère encrypted', description=f'```{''.join(res)}```', author=ctx.author))

    @commands.command(name="vigenere_decrypt", help="Decrypt text using classical Vigenère polyalphabetic cipher")
    async def vigenere_decrypt_cmd(self, ctx, key: str, *, ciphertext: str):
        key_clean = ''.join(filter(str.isalpha, key)).upper()
        if not key_clean: return await ctx.send(embed=error_embed('key must contain alphabet characters', ctx.author))
        res = []
        k_idx = 0
        for ch in ciphertext:
            if ch.isalpha():
                base = ord('A') if ch.isupper() else ord('a')
                shift = ord(key_clean[k_idx % len(key_clean)]) - ord('A')
                res.append(chr(base + (ord(ch) - base - shift) % 26))
                k_idx += 1
            else: res.append(ch)
        await ctx.send(embed=fleed_embed(title='vigenère decrypted', description=f'```{''.join(res)}```', author=ctx.author))

    @commands.command(name="is_ip_private", help="Check if an IP address belongs to RFC 1918 private range")
    async def is_ip_private_cmd(self, ctx, ip_address: str):
        import ipaddress
        try:
            ip = ipaddress.ip_address(ip_address.strip())
            res = ip.is_private
            desc = f'`{ip}` is **a private/local network address**' if res else f'`{ip}` is **a public internet address**'
            await ctx.send(embed=fleed_embed(title='ip address check', description=desc, author=ctx.author))
        except ValueError:
            await ctx.send(embed=error_embed('invalid IP address format', ctx.author))

    @commands.command(name="mac_format", help="Format MAC address in colon, hyphen, and cisco dot styles")
    async def mac_format_cmd(self, ctx, mac_address: str):
        cleaned = re.sub(r'[^a-fA-F0-9]', '', mac_address)
        if len(cleaned) != 12: return await ctx.send(embed=error_embed('MAC address must contain 12 hex characters', ctx.author))
        c_style = ':'.join(cleaned[i:i+2] for i in range(0, 12, 2)).lower()
        h_style = '-'.join(cleaned[i:i+2] for i in range(0, 12, 2)).upper()
        d_style = '.'.join(cleaned[i:i+4] for i in range(0, 12, 4)).lower()
        desc = f'**Colon:** `{c_style}`\n**Hyphen:** `{h_style}`\n**Cisco Dot:** `{d_style}`'
        await ctx.send(embed=fleed_embed(title='MAC address formats', description=desc, author=ctx.author))

    @commands.command(name="mime_lookup", help="Lookup standard MIME type by file extension")
    async def mime_lookup_cmd(self, ctx, extension_or_mime: str):
        import mimetypes
        m = mimetypes.guess_type(f'file.{extension_or_mime.lstrip(".")}')
        type_str = m[0] or 'unknown MIME type'
        await ctx.send(embed=fleed_embed(title='MIME type lookup', description=f'extension `.{extension_or_mime.lstrip(".")}` -> **`{type_str}`**', author=ctx.author))

    @commands.command(name="port_info", help="Lookup common IANA service associated with a TCP/UDP port")
    async def port_info_cmd(self, ctx, port_number: int):
        ports = {20:'FTP Data',21:'FTP Control',22:'SSH / SFTP',23:'Telnet',25:'SMTP',53:'DNS',80:'HTTP',110:'POP3',123:'NTP',143:'IMAP',443:'HTTPS',465:'SMTPS',587:'SMTP Submission',993:'IMAPS',995:'POP3S',1433:'MS SQL',1521:'Oracle DB',3306:'MySQL / MariaDB',3389:'RDP',5432:'PostgreSQL',6379:'Redis',8080:'HTTP Alternate / Proxy',8443:'HTTPS Alternate',27017:'MongoDB'}
        service = ports.get(port_number, 'unregistered / custom service')
        await ctx.send(embed=fleed_embed(title=f'port {port_number}', description=f'standard service: **{service}**', author=ctx.author))

    @commands.command(name="jwt_inspect", help="Decode unverified header and payload of a JSON Web Token (JWT)")
    async def jwt_inspect_cmd(self, ctx, token: str):
        import json, base64
        parts = token.strip().split('.')
        if len(parts) < 2: return await ctx.send(embed=error_embed('invalid JWT format (require at least header.payload)', ctx.author))
        def b64d(s):
            s += '=' * (-len(s) % 4)
            return json.loads(base64.urlsafe_b64decode(s.encode()).decode('utf-8'))
        try:
            header = json.dumps(b64d(parts[0]), indent=2)
            payload = json.dumps(b64d(parts[1]), indent=2)
            desc = f'**Header:**\n```json\n{header[:1000]}\n```\n**Payload:**\n```json\n{payload[:1000]}\n```'
            await ctx.send(embed=fleed_embed(title='JWT token inspection', description=desc, author=ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f'failed to decode JWT: {str(e).lower()}', ctx.author))

    @commands.command(name="days_between", help="Calculate total days between two YYYY-MM-DD dates")
    async def days_between_cmd(self, ctx, date1: str, date2: str):
        import datetime
        try:
            d1 = datetime.datetime.strptime(date1, '%Y-%m-%d').date()
            d2 = datetime.datetime.strptime(date2, '%Y-%m-%d').date()
            delta = abs((d2 - d1).days)
            await ctx.send(embed=fleed_embed(title='date difference', description=f'between {d1} and {d2}: **{delta:,} days** ({delta/7:.1f} weeks)', author=ctx.author))
        except ValueError:
            await ctx.send(embed=error_embed('dates must be formatted as YYYY-MM-DD', ctx.author))

    @commands.command(name="day_of_week", help="Find which day of the week a YYYY-MM-DD date fell on")
    async def day_of_week_cmd(self, ctx, date_str: str):
        import datetime
        try:
            dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            name = dt.strftime('%A')
            await ctx.send(embed=fleed_embed(title='day of week', description=f'{date_str} is/was a **{name}**', author=ctx.author))
        except ValueError:
            await ctx.send(embed=error_embed('date must be formatted as YYYY-MM-DD', ctx.author))

    @commands.command(name="leap_year", help="Check if a given year is a leap year")
    async def leap_year_cmd(self, ctx, year: int):
        import calendar
        is_leap = calendar.isleap(year)
        desc = f'**{year}** is **a leap year (366 days)**' if is_leap else f'**{year}** is **a common year (365 days)**'
        await ctx.send(embed=fleed_embed(title='leap year check', description=desc, author=ctx.author))


async def setup(bot):
    await bot.add_cog(Utility(bot))

