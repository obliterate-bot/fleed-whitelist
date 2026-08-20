import asyncio
import io
import math
import urllib.parse

import aiohttp
import discord
from discord.ext import commands
from PIL import Image

import config
from utils import error_embed, fleed_embed, send_group_help, success_embed, warn_embed


class LastFMError(RuntimeError):
    pass


class LastFM(commands.Cog):
    """Real Last.fm commands backed by the public Last.fm API."""

    API_URL = "https://ws.audioscrobbler.com/2.0/"
    PERIODS = {
        "overall": "overall", "all": "overall",
        "7day": "7day", "week": "7day", "weekly": "7day",
        "1month": "1month", "month": "1month", "monthly": "1month",
        "3month": "3month", "3months": "3month",
        "6month": "6month", "6months": "6month",
        "12month": "12month", "year": "12month", "yearly": "12month",
    }

    def __init__(self, bot):
        self.bot = bot

    async def _api(self, method: str, **params):
        if not config.LASTFM_API_KEY:
            raise LastFMError("LASTFM_API_KEY is not configured in .env")
        query = {"method": method, "api_key": config.LASTFM_API_KEY, "format": "json", **params}
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self.API_URL, params=query) as response:
                data = await response.json(content_type=None)
        if response.status >= 400 or "error" in data:
            raise LastFMError(str(data.get("message") or f"Last.fm returned HTTP {response.status}"))
        return data

    async def _linked_username(self, member) -> str:
        row = await self.bot.db.fetchrow("SELECT lastfm_username FROM user_settings WHERE user_id = ?", (member.id,))
        if not row or not row["lastfm_username"]:
            raise LastFMError(f"{member.display_name} has not linked a Last.fm account; use `lastfm set <username>`")
        return str(row["lastfm_username"])

    @staticmethod
    def _period(value: str) -> str:
        return LastFM.PERIODS.get(str(value or "overall").lower(), "overall")

    @staticmethod
    def _image(item: dict):
        images = item.get("image") or []
        for image in reversed(images):
            url = image.get("#text") if isinstance(image, dict) else None
            if url:
                return url
        return None

    @staticmethod
    def _split_pair(value: str, label: str = "artist and track"):
        value = (value or "").strip()
        for separator in (" | ", " - ", " — ", " :: "):
            if separator in value:
                left, right = value.split(separator, 1)
                if left.strip() and right.strip():
                    return left.strip(), right.strip()
        raise LastFMError(f"provide {label} as `artist | title`")

    async def _send_error(self, ctx, exc):
        await ctx.send(embed=error_embed(str(exc)[:350], ctx.author))

    async def _recent_track(self, member):
        username = await self._linked_username(member)
        data = await self._api("user.getRecentTracks", user=username, limit=1, extended=1)
        tracks = data.get("recenttracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        if not tracks:
            raise LastFMError(f"no recent scrobbles found for `{username}`")
        return username, tracks[0]

    async def _linked_members(self, guild):
        linked = []
        for member in guild.members:
            row = await self.bot.db.fetchrow("SELECT lastfm_username FROM user_settings WHERE user_id = ?", (member.id,))
            if row and row["lastfm_username"]:
                linked.append((member, str(row["lastfm_username"])))
        return linked

    @commands.hybrid_group(name="lastfm", invoke_without_command=True, with_app_command=False)
    async def lastfm(self, ctx):
        await send_group_help(ctx, ctx.command, "lastfm")

    @commands.hybrid_command(name="nowplaying")
    async def nowplaying(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        try:
            username, track = await self._recent_track(target)
            artist = track.get("artist", {})
            artist_name = artist.get("name") or artist.get("#text") or "unknown artist"
            album = track.get("album", {}).get("#text") or "unknown album"
            playing = track.get("@attr", {}).get("nowplaying") == "true"
            plays = track.get("playcount")
            description = f"**{artist_name} — {track.get('name', 'unknown track')}**\nAlbum: {album}"
            if plays is not None:
                description += f"\nUser plays: {int(plays):,}"
            description += f"\nStatus: {'now playing' if playing else 'last scrobbled'}"
            embed = fleed_embed(title=f"{target.display_name.lower()}'s scrobble", description=description, author=target)
            image = self._image(track)
            if image:
                embed.set_thumbnail(url=image)
            embed.set_footer(text=f"Last.fm user: {username}")
            await ctx.send(embed=embed)
        except Exception as exc:
            await self._send_error(ctx, exc)

    @commands.hybrid_command(name="fm", aliases=["np"])
    async def fm_cmd(self, ctx, member: discord.Member = None, *, flags: str = None):
        await self.nowplaying(ctx, member)

    @lastfm.command(name="nowplaying", aliases=["np"])
    async def lastfm_nowplaying(self, ctx, member: discord.Member = None, *, flags: str = None):
        await self.nowplaying(ctx, member)

    @lastfm.command(name="set", aliases=["connect", "login"])
    async def lastfm_set(self, ctx, *, username: str):
        try:
            data = await self._api("user.getInfo", user=username.strip())
            canonical = data["user"]["name"]
            await self.bot.db.execute(
                "INSERT INTO user_settings (user_id, lastfm_username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET lastfm_username = ?",
                (ctx.author.id, canonical, canonical),
            )
            await ctx.send(embed=success_embed(f"linked Last.fm account `{canonical}`", ctx.author))
        except Exception as exc:
            await self._send_error(ctx, exc)

    @lastfm.command(name="logout", aliases=["disconnect"])
    async def lastfm_logout(self, ctx):
        await self.bot.db.execute("UPDATE user_settings SET lastfm_username = NULL WHERE user_id = ?", (ctx.author.id,))
        await ctx.send(embed=success_embed("unlinked Last.fm account", ctx.author))

    async def _top(self, ctx, kind: str, member=None, period="overall", limit=10):
        target = member or ctx.author
        username = await self._linked_username(target)
        method = {"tracks": "user.getTopTracks", "albums": "user.getTopAlbums", "artists": "user.getTopArtists"}[kind]
        container = {"tracks": "toptracks", "albums": "topalbums", "artists": "topartists"}[kind]
        item_key = {"tracks": "track", "albums": "album", "artists": "artist"}[kind]
        data = await self._api(method, user=username, period=self._period(period), limit=max(1, min(int(limit), 25)))
        items = data.get(container, {}).get(item_key, [])
        if isinstance(items, dict):
            items = [items]
        lines = []
        for index, item in enumerate(items, 1):
            artist = item.get("artist", {})
            artist_name = artist.get("name") or artist.get("#text")
            name = item.get("name", "unknown")
            label = name if kind == "artists" else f"{artist_name or 'unknown'} — {name}"
            lines.append(f"**{index}.** {label} — {int(item.get('playcount', 0)):,} plays")
        await ctx.send(embed=fleed_embed(title=f"{target.display_name.lower()}'s top {kind} ({self._period(period)})", description="\n".join(lines) or "no data", author=target))

    @lastfm.command(name="toptracks", aliases=["tt"])
    async def lastfm_toptracks(self, ctx, member: discord.Member = None, period: str = "overall"):
        try: await self._top(ctx, "tracks", member, period)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="topalbums", aliases=["tab", "topalbum", "albums", "tl"])
    async def lastfm_topalbums(self, ctx, member: discord.Member = None, period: str = "overall"):
        try: await self._top(ctx, "albums", member, period)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="topartists", aliases=["ta"])
    async def lastfm_topartists(self, ctx, member: discord.Member = None, period: str = "overall"):
        try: await self._top(ctx, "artists", member, period)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="recent", aliases=["recents"])
    async def lastfm_recent(self, ctx, member: discord.Member = None, limit: int = 10):
        target = member or ctx.author
        try:
            username = await self._linked_username(target)
            data = await self._api("user.getRecentTracks", user=username, limit=max(1, min(limit, 25)))
            tracks = data.get("recenttracks", {}).get("track", [])
            if isinstance(tracks, dict): tracks = [tracks]
            lines = []
            for index, track in enumerate(tracks, 1):
                artist = track.get("artist", {}).get("#text") or "unknown"
                now = " *(now playing)*" if track.get("@attr", {}).get("nowplaying") == "true" else ""
                lines.append(f"**{index}.** {artist} — {track.get('name', 'unknown')}{now}")
            await ctx.send(embed=fleed_embed(title=f"{target.display_name.lower()}'s recent tracks", description="\n".join(lines) or "no recent tracks", author=target))
        except Exception as exc:
            await self._send_error(ctx, exc)

    @lastfm.command(name="count", aliases=["total"])
    async def lastfm_count(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        try:
            username = await self._linked_username(target)
            user = (await self._api("user.getInfo", user=username))["user"]
            await ctx.send(embed=fleed_embed(description=f"{target.display_name.lower()} has **{int(user.get('playcount', 0)):,}** total scrobbles", author=target))
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="whois", aliases=["profile"])
    async def lastfm_whois(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        try:
            username = await self._linked_username(target)
            user = (await self._api("user.getInfo", user=username))["user"]
            registered = int(user.get("registered", {}).get("unixtime", 0) or 0)
            desc = f"**Username:** [{user['name']}]({user['url']})\n**Scrobbles:** {int(user.get('playcount', 0)):,}\n**Artists:** {int(user.get('artist_count', 0)):,}\n**Albums:** {int(user.get('album_count', 0)):,}\n**Tracks:** {int(user.get('track_count', 0)):,}"
            if registered: desc += f"\n**Registered:** <t:{registered}:D>"
            embed = fleed_embed(title=f"{target.display_name.lower()}'s Last.fm profile", description=desc, author=target)
            image = self._image(user)
            if image: embed.set_thumbnail(url=image)
            await ctx.send(embed=embed)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="whoknows", aliases=["wk"])
    async def lastfm_whoknows(self, ctx, *, artist: str):
        try:
            linked = await self._linked_members(ctx.guild)
            if not linked: raise LastFMError("nobody in this server has linked Last.fm")
            async def plays(entry):
                member, username = entry
                try:
                    info = (await self._api("artist.getInfo", artist=artist, username=username, autocorrect=1))["artist"]
                    return member, int(info.get("stats", {}).get("userplaycount", 0))
                except Exception:
                    return member, 0
            results = await asyncio.gather(*(plays(entry) for entry in linked[:30]))
            ranked = sorted((row for row in results if row[1] > 0), key=lambda row: row[1], reverse=True)
            lines = [f"**{i}.** {member.mention} — {count:,} plays" for i, (member, count) in enumerate(ranked[:20], 1)]
            await ctx.send(embed=fleed_embed(title=f"who knows {artist.lower()}", description="\n".join(lines) or "no linked member has plays", author=ctx.author))
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="taste", aliases=["compare"])
    async def lastfm_taste(self, ctx, member: discord.Member, period: str = "overall"):
        try:
            first = await self._linked_username(ctx.author)
            second = await self._linked_username(member)
            comparison = (await self._api("tasteometer.compare", type1="user", value1=first, type2="user", value2=second, limit=10))["comparison"]
            score = float(comparison.get("result", {}).get("score", 0)) * 100
            artists = comparison.get("result", {}).get("artists", {}).get("artist", [])
            if isinstance(artists, dict): artists = [artists]
            shared = ", ".join(a.get("name", "unknown") for a in artists[:8]) or "none"
            await ctx.send(embed=fleed_embed(title="music taste comparison", description=f"Compatibility with {member.mention}: **{score:.1f}%**\nShared artists: {shared}", author=ctx.author))
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="collage", aliases=["col", "chart", "art"])
    async def lastfm_collage(self, ctx, member: discord.Member = None, size: str = "3x3", period: str = "7day"):
        target = member or ctx.author
        try:
            parts = size.lower().split("x", 1)
            width, height = int(parts[0]), int(parts[1])
            if width < 1 or height < 1 or width * height > 25:
                raise LastFMError("collage size must be between 1x1 and 5x5")
            username = await self._linked_username(target)
            data = await self._api("user.getTopAlbums", user=username, period=self._period(period), limit=width * height)
            albums = data.get("topalbums", {}).get("album", [])
            if isinstance(albums, dict): albums = [albums]
            urls = [self._image(album) for album in albums]
            urls = [url for url in urls if url]
            if not urls: raise LastFMError("Last.fm did not return album artwork")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async def load(url):
                    async with session.get(url) as response: return await response.read() if response.status == 200 else None
                blobs = await asyncio.gather(*(load(url) for url in urls))
            canvas = Image.new("RGB", (width * 300, height * 300), (35, 35, 35))
            for index, blob in enumerate(blobs):
                if not blob: continue
                try:
                    cover = Image.open(io.BytesIO(blob)).convert("RGB").resize((300, 300))
                    canvas.paste(cover, ((index % width) * 300, (index // width) * 300))
                except Exception: continue
            output = io.BytesIO(); canvas.save(output, format="PNG", optimize=True); output.seek(0)
            await ctx.send(file=discord.File(output, filename=f"lastfm-{width}x{height}.png"))
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="favorites", aliases=["favs", "loved"])
    async def lastfm_favorites(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        try:
            username = await self._linked_username(target)
            data = await self._api("user.getLovedTracks", user=username, limit=15)
            tracks = data.get("lovedtracks", {}).get("track", [])
            if isinstance(tracks, dict): tracks = [tracks]
            lines = [f"**{i}.** {t.get('artist', {}).get('name', 'unknown')} — {t.get('name', 'unknown')}" for i, t in enumerate(tracks, 1)]
            await ctx.send(embed=fleed_embed(title=f"{target.display_name.lower()}'s loved tracks", description="\n".join(lines) or "no loved tracks", author=target))
        except Exception as exc: await self._send_error(ctx, exc)

    async def _info_command(self, ctx, kind, member, value):
        target = member or ctx.author
        username = await self._linked_username(target)
        if kind == "artist":
            data = (await self._api("artist.getInfo", artist=value, username=username, autocorrect=1))["artist"]
            stats = data.get("stats", {})
            desc = f"**Listeners:** {int(stats.get('listeners', 0)):,}\n**Global plays:** {int(stats.get('playcount', 0)):,}\n**Your plays:** {int(stats.get('userplaycount', 0)):,}\n[Open on Last.fm]({data.get('url')})"
            title = data.get("name", value)
        else:
            artist, title = self._split_pair(value, f"artist and {kind}")
            method = "track.getInfo" if kind == "track" else "album.getInfo"
            data = (await self._api(method, artist=artist, **{kind: title}, username=username, autocorrect=1))[kind]
            desc = f"**Artist:** {data.get('artist', {}).get('name') if isinstance(data.get('artist'), dict) else data.get('artist', artist)}\n**Global plays:** {int(data.get('playcount', 0)):,}\n**Your plays:** {int(data.get('userplaycount', 0)):,}\n[Open on Last.fm]({data.get('url')})"
            title = data.get("name", title)
        embed = fleed_embed(title=f"{kind}: {title}", description=desc, author=target)
        image = self._image(data)
        if image: embed.set_thumbnail(url=image)
        await ctx.send(embed=embed)

    @lastfm.command(name="artist", aliases=["a", "artistinfo"])
    async def lastfm_artist(self, ctx, member: discord.Member = None, *, artist: str):
        try: await self._info_command(ctx, "artist", member, artist)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="track", aliases=["tr", "trackinfo"])
    async def lastfm_track(self, ctx, member: discord.Member = None, *, track: str):
        try: await self._info_command(ctx, "track", member, track)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="album", aliases=["ab", "albuminfo"])
    async def lastfm_album(self, ctx, member: discord.Member = None, *, album: str):
        try: await self._info_command(ctx, "album", member, album)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="plays")
    async def lastfm_plays(self, ctx, member: discord.Member = None, *, artist: str):
        try: await self._info_command(ctx, "artist", member, artist)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="playstrack", aliases=["tplays"])
    async def lastfm_playstrack(self, ctx, member: discord.Member = None, *, artist_and_track: str):
        try: await self._info_command(ctx, "track", member, artist_and_track)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="playsalbum", aliases=["aplays"])
    async def lastfm_playsalbum(self, ctx, member: discord.Member = None, *, artist_and_album: str):
        try: await self._info_command(ctx, "album", member, artist_and_album)
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="scoreboard", aliases=["leaderboard", "sb", "playleaderboard"])
    async def lastfm_scoreboard(self, ctx):
        try:
            linked = await self._linked_members(ctx.guild)
            async def total(entry):
                member, username = entry
                try: return member, int((await self._api("user.getInfo", user=username))["user"].get("playcount", 0))
                except Exception: return member, 0
            results = sorted(await asyncio.gather(*(total(e) for e in linked[:50])), key=lambda row: row[1], reverse=True)
            lines = [f"**{i}.** {member.mention} — {plays:,} scrobbles" for i, (member, plays) in enumerate(results[:20], 1)]
            await ctx.send(embed=fleed_embed(title="server scrobble leaderboard", description="\n".join(lines) or "no linked users", author=ctx.author))
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="recommendation", aliases=["recommend"])
    async def lastfm_recommendation(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        try:
            username = await self._linked_username(target)
            top = (await self._api("user.getTopArtists", user=username, period="3month", limit=1)).get("topartists", {}).get("artist", [])
            if isinstance(top, list): top = top[0] if top else None
            if not top: raise LastFMError("not enough listening history for a recommendation")
            similar = (await self._api("artist.getSimilar", artist=top["name"], limit=10, autocorrect=1)).get("similarartists", {}).get("artist", [])
            names = [a.get("name") for a in similar if a.get("name")]
            await ctx.send(embed=fleed_embed(title="music recommendations", description="\n".join(f"• {name}" for name in names) or "none found", author=target))
        except Exception as exc: await self._send_error(ctx, exc)

    @lastfm.command(name="addfriend", aliases=["addfriends", "af"])
    async def lastfm_addfriend(self, ctx, user: discord.User):
        await self.bot.db.execute("INSERT OR IGNORE INTO lastfm_friends (user_id, friend_id) VALUES (?, ?)", (ctx.author.id, user.id))
        await ctx.send(embed=success_embed(f"added {user.mention} to your Last.fm friends", ctx.author))

    @lastfm.command(name="removefriend", aliases=["removefriends", "rf"])
    async def lastfm_removefriend(self, ctx, user: discord.User):
        await self.bot.db.execute("DELETE FROM lastfm_friends WHERE user_id = ? AND friend_id = ?", (ctx.author.id, user.id))
        await ctx.send(embed=success_embed(f"removed {user.mention} from your Last.fm friends", ctx.author))

    @lastfm.command(name="friends")
    async def lastfm_friends(self, ctx):
        rows = await self.bot.db.fetch("SELECT friend_id FROM lastfm_friends WHERE user_id = ?", (ctx.author.id,))
        await ctx.send(embed=fleed_embed(title="Last.fm friends", description="\n".join(f"<@{r['friend_id']}>" for r in rows) or "none", author=ctx.author))

    @lastfm.command(name="color", aliases=["colour"])
    async def lastfm_color(self, ctx, color_value: str):
        try:
            int(color_value.strip().lstrip("#"), 16)
        except ValueError:
            return await ctx.send(embed=error_embed("provide a hex color such as `#2b2d31`", ctx.author))
        await self.bot.db.execute("INSERT INTO user_settings (user_id, lastfm_color) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET lastfm_color = ?", (ctx.author.id, color_value.lower(), color_value.lower()))
        await ctx.send(embed=success_embed(f"set Last.fm embed color to `{color_value.lower()}`", ctx.author))

    @lastfm.command(name="customcommand", aliases=["cc", "custom"])
    async def lastfm_customcommand(self, ctx, command: str = None):
        value = command.lower() if command else None
        await self.bot.db.execute("INSERT INTO user_settings (user_id, lastfm_custom_cmd) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET lastfm_custom_cmd = ?", (ctx.author.id, value, value))
        await ctx.send(embed=success_embed(f"set custom Last.fm shortcut to `{value or 'none'}`", ctx.author))

    @lastfm.command(name="searchlinks", aliases=["links", "spotify", "youtube"])
    async def lastfm_searchlinks(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        try:
            _, track = await self._recent_track(target)
            artist = track.get("artist", {}).get("name") or track.get("artist", {}).get("#text") or ""
            query = f"{artist} {track.get('name', '')}".strip()
            encoded = urllib.parse.quote_plus(query)
            desc = f"[Spotify](https://open.spotify.com/search/{encoded}) • [YouTube](https://www.youtube.com/results?search_query={encoded}) • [SoundCloud](https://soundcloud.com/search?q={encoded})"
            await ctx.send(embed=fleed_embed(title=query, description=desc, author=target))
        except Exception as exc: await self._send_error(ctx, exc)

    # Top-level shortcuts preserve familiar command names without duplicating fake data.
    @commands.command(name="toptracks", aliases=["tt"])
    async def direct_toptracks(self, ctx, member: discord.Member = None, period: str = "overall"):
        await self.lastfm_toptracks(ctx, member, period)

    @commands.command(name="topalbums", aliases=["tab", "topalbum", "albums"])
    async def direct_topalbums(self, ctx, member: discord.Member = None, period: str = "overall"):
        await self.lastfm_topalbums(ctx, member, period)

    @commands.command(name="topartists", aliases=["ta"])
    async def direct_topartists(self, ctx, member: discord.Member = None, period: str = "overall"):
        await self.lastfm_topartists(ctx, member, period)

    @commands.command(name="whoknows", aliases=["wk"])
    async def direct_whoknows(self, ctx, *, artist: str):
        await self.lastfm_whoknows(ctx, artist=artist)

    @commands.command(name="taste", aliases=["compatibility", "compare"])
    async def direct_taste(self, ctx, member: discord.Member):
        await self.lastfm_taste(ctx, member)

    @commands.command(name="collage", aliases=["chart", "grid"])
    async def direct_collage(self, ctx, member: discord.Member = None, size: str = "3x3", period: str = "7day"):
        await self.lastfm_collage(ctx, member, size, period)

    @commands.command(name="recent", aliases=["recenttracks"])
    async def direct_recent(self, ctx, member: discord.Member = None, limit: int = 10):
        await self.lastfm_recent(ctx, member, limit)


async def setup(bot):
    await bot.add_cog(LastFM(bot))
