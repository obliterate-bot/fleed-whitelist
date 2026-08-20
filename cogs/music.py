import discord
from discord.ext import commands
import asyncio
import yt_dlp
import datetime
import traceback
import shutil
import os
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help, send_paginated_embed

# Suppress yt-dlp bug report logs
yt_dlp.utils.bug_reports_message = lambda *args, **kwargs: ''

def get_ffmpeg_executable():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    which = shutil.which("ffmpeg")
    if which:
        return which
    return "ffmpeg"

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch1',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.9):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url') or data.get('url')
        self.duration = int(data.get('duration') or 0)
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader')

    @classmethod
    async def create_source(cls, search: str, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        
        # If not a URL, use SoundCloud search for fast and non-blocked audio streams
        if not search.startswith(('http://', 'https://')):
            query = f"scsearch1:{search}"
        else:
            query = search

        to_run = lambda: ytdl.extract_info(query, download=False)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data and data['entries']:
            data = data['entries'][0]

        source_url = data.get('url')
        ffmpeg_exe = get_ffmpeg_executable()
        audio = discord.FFmpegPCMAudio(source_url, executable=ffmpeg_exe, **FFMPEG_OPTIONS)
        return cls(audio, data=data), data


class MusicControlView(discord.ui.View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="pause/resume", style=discord.ButtonStyle.secondary, custom_id="fleed_music_toggle")
    async def toggle_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            return await interaction.response.send_message("not connected to a voice channel", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message("paused playback", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message("resumed playback", ephemeral=True)
        else:
            await interaction.response.send_message("no audio currently playing", ephemeral=True)

    @discord.ui.button(label="skip", style=discord.ButtonStyle.secondary, custom_id="fleed_music_skip")
    async def skip_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message("nothing is currently playing to skip", ephemeral=True)
        vc.stop()
        await interaction.response.send_message("skipped current track", ephemeral=True)

    @discord.ui.button(label="queue", style=discord.ButtonStyle.secondary, custom_id="fleed_music_queue")
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        queue = self.cog.queues.get(self.guild_id, [])
        if not queue:
            return await interaction.response.send_message("the queue is currently empty", ephemeral=True)
        lines = [f"`{i}` **{t['title'].lower()}** ({datetime.timedelta(seconds=t.get('duration', 0) or 0)})" for i, t in enumerate(queue[:10], 1)]
        embed = fleed_embed(title="music queue", description="\n".join(lines), author=interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="stop", style=discord.ButtonStyle.danger, custom_id="fleed_music_stop")
    async def stop_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.cog.queues[self.guild_id] = []
            await vc.disconnect()
            await interaction.response.send_message("disconnected and cleared music queue", ephemeral=True)
        else:
            await interaction.response.send_message("not connected to a voice channel", ephemeral=True)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.current_tracks = {}
        self.loop_states = {}

    async def cog_load(self):
        try:
            if not discord.opus.is_loaded():
                discord.opus._load_default()
        except Exception:
            pass

    def play_next(self, ctx):
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id, [])
        vc = ctx.guild.voice_client

        if not vc or not vc.is_connected():
            return

        if self.loop_states.get(guild_id, False) and guild_id in self.current_tracks:
            track = self.current_tracks[guild_id]
        elif queue:
            track = queue.pop(0)
            self.current_tracks[guild_id] = track
        else:
            self.current_tracks.pop(guild_id, None)
            return

        async def _play():
            try:
                source, data = await YTDLSource.create_source(track["search"], loop=self.bot.loop)
                vc.play(source, after=lambda e: self.play_next(ctx))
                dur = datetime.timedelta(seconds=int(data.get("duration") or 0))
                desc = f"**now playing**\n[{data.get('title', '').lower()}]({data.get('webpage_url') or data.get('url', '')})\n\n**duration:** `{dur}` | **requester:** {track['author'].mention}"
                embed = fleed_embed(title="music player", description=desc, author=track["author"])
                if data.get("thumbnail"):
                    embed.set_thumbnail(url=data.get("thumbnail"))
                view = MusicControlView(self, guild_id)
                await ctx.send(embed=embed, view=view)
            except Exception as e:
                await ctx.send(embed=error_embed(f"playback error: {e}", track["author"]))
                self.play_next(ctx)

        asyncio.run_coroutine_threadsafe(_play(), self.bot.loop)

    @commands.command(name="join", aliases=["connect", "summon"])
    async def join_channel(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send(embed=error_embed("you must be in a voice channel first", ctx.author))
        
        channel = ctx.author.voice.channel
        permissions = channel.permissions_for(ctx.guild.me)
        if not permissions.connect or not permissions.speak:
            return await ctx.send(embed=error_embed("i need `connect` and `speak` permissions in that voice channel", ctx.author))

        try:
            if ctx.voice_client:
                if ctx.voice_client.channel != channel:
                    await ctx.voice_client.move_to(channel)
            else:
                await channel.connect(timeout=15.0, reconnect=True)
            await ctx.send(embed=success_embed(f"joined voice channel {channel.mention}", ctx.author))
        except discord.ClientException as e:
            await ctx.send(embed=error_embed(f"voice client error: {e}", ctx.author))
        except asyncio.TimeoutError:
            await ctx.send(embed=error_embed("connection to voice channel timed out", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to join voice channel: {e}", ctx.author))

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, search: str):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send(embed=error_embed("you must join a voice channel first", ctx.author))

        channel = ctx.author.voice.channel
        permissions = channel.permissions_for(ctx.guild.me)
        if not permissions.connect or not permissions.speak:
            return await ctx.send(embed=error_embed("i need `connect` and `speak` permissions in that voice channel", ctx.author))

        try:
            if not ctx.voice_client:
                await channel.connect(timeout=15.0, reconnect=True)
            elif ctx.voice_client.channel != channel:
                await ctx.voice_client.move_to(channel)
        except Exception as e:
            return await ctx.send(embed=error_embed(f"failed to connect to voice channel: {e}", ctx.author))

        guild_id = ctx.guild.id
        if guild_id not in self.queues:
            self.queues[guild_id] = []

        await ctx.send(embed=fleed_embed(description=f"searching for `{search.lower()}`...", author=ctx.author))

        try:
            # Query track info
            query = search if search.startswith(('http://', 'https://')) else f"scsearch1:{search}"
            to_run = lambda: ytdl.extract_info(query, download=False)
            data = await self.bot.loop.run_in_executor(None, to_run)
            if 'entries' in data and data['entries']:
                data = data['entries'][0]

            track_info = {
                "title": data.get("title", search),
                "url": data.get("webpage_url") or data.get("url", ""),
                "duration": int(data.get("duration") or 0),
                "thumbnail": data.get("thumbnail"),
                "search": search,
                "author": ctx.author
            }

            vc = ctx.voice_client
            if vc.is_playing() or vc.is_paused():
                self.queues[guild_id].append(track_info)
                dur = datetime.timedelta(seconds=track_info.get("duration", 0) or 0)
                desc = f"added to queue: **[{track_info['title'].lower()}]({track_info['url']})** (`{dur}`)\nposition in queue: **#{len(self.queues[guild_id])}**"
                await ctx.send(embed=success_embed(desc, ctx.author))
            else:
                self.current_tracks[guild_id] = track_info
                source, _ = await YTDLSource.create_source(track_info["search"], loop=self.bot.loop)
                vc.play(source, after=lambda e: self.play_next(ctx))
                dur = datetime.timedelta(seconds=int(data.get("duration") or 0))
                desc = f"**now playing**\n[{data.get('title', '').lower()}]({data.get('webpage_url') or data.get('url', '')})\n\n**duration:** `{dur}` | **requester:** {ctx.author.mention}"
                embed = fleed_embed(title="music player", description=desc, author=ctx.author)
                if data.get("thumbnail"):
                    embed.set_thumbnail(url=data.get("thumbnail"))
                view = MusicControlView(self, guild_id)
                await ctx.send(embed=embed, view=view)
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to play song: {e}", ctx.author))

    @commands.command(name="pause")
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send(embed=success_embed("paused music playback", ctx.author))
        else:
            await ctx.send(embed=warn_embed("nothing is playing to pause", ctx.author))

    @commands.command(name="resume")
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send(embed=success_embed("resumed music playback", ctx.author))
        else:
            await ctx.send(embed=warn_embed("player is not paused", ctx.author))

    @commands.command(name="skip", aliases=["next", "s_music"])
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send(embed=success_embed("skipped current track", ctx.author))
        else:
            await ctx.send(embed=warn_embed("nothing is playing to skip", ctx.author))

    @commands.command(name="stop", aliases=["disconnect", "dc"])
    async def stop(self, ctx):
        if ctx.voice_client:
            self.queues[ctx.guild.id] = []
            self.current_tracks.pop(ctx.guild.id, None)
            await ctx.voice_client.disconnect()
            await ctx.send(embed=success_embed("disconnected and cleared music queue", ctx.author))
        else:
            await ctx.send(embed=warn_embed("not connected to a voice channel", ctx.author))

    @commands.command(name="queue", aliases=["q"])
    async def queue_cmd(self, ctx):
        queue = self.queues.get(ctx.guild.id, [])
        curr = self.current_tracks.get(ctx.guild.id)
        if not curr and not queue:
            return await ctx.send(embed=warn_embed("music queue is empty", ctx.author))

        entries = []
        if curr:
            dur = datetime.timedelta(seconds=curr.get("duration", 0) or 0)
            entries.append(f"🎧 **now playing:** [{curr['title'].lower()}]({curr.get('url', '')}) (`{dur}`)\n")

        for i, t in enumerate(queue, 1):
            dur = datetime.timedelta(seconds=t.get("duration", 0) or 0)
            entries.append(f"`{i:02}` [{t['title'].lower()}]({t.get('url', '')}) (`{dur}`) — requested by {t['author'].mention}")

        await send_paginated_embed(ctx, f"music queue ({len(queue)} in queue)", entries, per_page=10, item_name="tracks")

    @commands.command(name="playing", aliases=["song", "current", "track"])
    async def nowplaying(self, ctx):
        curr = self.current_tracks.get(ctx.guild.id)
        if not curr or not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send(embed=warn_embed("no music currently playing", ctx.author))

        dur = datetime.timedelta(seconds=curr.get("duration", 0) or 0)
        desc = f"**title:** [{curr['title'].lower()}]({curr.get('url', '')})\n**duration:** `{dur}`\n**requester:** {curr['author'].mention}"
        embed = fleed_embed(title="now playing", description=desc, author=ctx.author)
        if curr.get("thumbnail"):
            embed.set_thumbnail(url=curr.get("thumbnail"))
        await ctx.send(embed=embed, view=MusicControlView(self, ctx.guild.id))

    @commands.command(name="loop", aliases=["repeat"])
    async def loop_track(self, ctx):
        current_state = self.loop_states.get(ctx.guild.id, False)
        self.loop_states[ctx.guild.id] = not current_state
        state_str = "enabled" if self.loop_states[ctx.guild.id] else "disabled"
        await ctx.send(embed=success_embed(f"track loop {state_str}", ctx.author))

    @commands.command(name="shuffle")
    async def shuffle_queue(self, ctx):
        queue = self.queues.get(ctx.guild.id, [])
        if len(queue) < 2:
            return await ctx.send(embed=warn_embed("not enough tracks in queue to shuffle", ctx.author))
        import random
        random.shuffle(queue)
        await ctx.send(embed=success_embed(f"shuffled **{len(queue)}** tracks in queue", ctx.author))

    @commands.command(name="removequeue", aliases=["removetrack", "rq"])
    async def remove_track(self, ctx, index: int):
        queue = self.queues.get(ctx.guild.id, [])
        if not queue or index > len(queue) or index < 1:
            return await ctx.send(embed=warn_embed(f"invalid index (1-{len(queue)})", ctx.author))
        removed = queue.pop(index - 1)
        await ctx.send(embed=success_embed(f"removed **{removed['title'].lower()}** from queue", ctx.author))

    @commands.command(name="skipto")
    async def skipto_track(self, ctx, index: int):
        queue = self.queues.get(ctx.guild.id, [])
        if not queue or index > len(queue) or index < 1:
            return await ctx.send(embed=warn_embed(f"invalid index (1-{len(queue)})", ctx.author))
        del queue[:index - 1]
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        await ctx.send(embed=success_embed(f"skipped directly to track **#{index}**", ctx.author))

    @commands.command(name="volume", aliases=["vol"])
    async def volume_cmd(self, ctx, volume: int):
        if not ctx.voice_client or not ctx.voice_client.source:
            return await ctx.send(embed=warn_embed("nothing currently playing", ctx.author))
        if volume < 0 or volume > 200:
            return await ctx.send(embed=warn_embed("volume must be between 0 and 200", ctx.author))
        if hasattr(ctx.voice_client.source, "volume"):
            ctx.voice_client.source.volume = volume / 100
        await ctx.send(embed=success_embed(f"volume set to **{volume}%**", ctx.author))

async def setup(bot):
    await bot.add_cog(Music(bot))
