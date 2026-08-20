import discord
from discord.ext import commands
import sys
import traceback
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help
import config

class Developer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_errors = {}

    @commands.hybrid_command(name="cmds")
    async def cmds(self, ctx):
        total = len(list(self.bot.walk_commands()))
        await ctx.send(embed=fleed_embed(title="commands", description=f"total registered commands: {total}", author=ctx.author))

    @commands.hybrid_group(name="developer", aliases=["x", "dev"], invoke_without_command=True)
    @commands.is_owner()
    async def developer(self, ctx):
        await send_group_help(ctx, ctx.command)

    @developer.group(name="blacklist", invoke_without_command=True)
    @commands.is_owner()
    async def dev_blacklist(self, ctx):
        await send_group_help(ctx, ctx.command)

    @dev_blacklist.command(name="user")
    @commands.is_owner()
    async def dev_blacklist_user(self, ctx, user_id: int, *, reason: str = "none"):
        await self.bot.db.execute("INSERT OR REPLACE INTO blacklists (target_id, target_type, reason) VALUES (?, 'user', ?)", (user_id, reason))
        await ctx.send(embed=success_embed(f"blacklisted user `{user_id}`", ctx.author))

    @dev_blacklist.command(name="guild")
    @commands.is_owner()
    async def dev_blacklist_guild(self, ctx, guild_id: int, *, reason: str = "none"):
        await self.bot.db.execute("INSERT OR REPLACE INTO blacklists (target_id, target_type, reason) VALUES (?, 'guild', ?)", (guild_id, reason))
        await ctx.send(embed=success_embed(f"blacklisted guild `{guild_id}`", ctx.author))

    @dev_blacklist.command(name="list")
    @commands.is_owner()
    async def dev_blacklist_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT target_id, target_type, reason FROM blacklists")
        if not rows:
            return await ctx.send(embed=warn_embed(description="no active blacklists", author=ctx.author))
        lines = [f"`{r['target_id']}` ({r['target_type']}): {r['reason']}" for r in rows]
        await ctx.send(embed=fleed_embed(title="blacklists", description="\n".join(lines), author=ctx.author))

    @developer.command(name="traceback")
    @commands.is_owner()
    async def dev_traceback(self, ctx, error_code: str):
        tb = self.last_errors.get(error_code, "error code not found in memory")
        await ctx.send(embed=fleed_embed(title=f"traceback {error_code}", description=f"```py\n{tb[:3900]}\n```", author=ctx.author))

    @developer.command(name="portal")
    @commands.is_owner()
    async def dev_portal(self, ctx, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send(embed=error_embed("guild not found", ctx.author))
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).create_instant_invite:
                invite = await channel.create_invite(max_age=300, max_uses=1)
                return await ctx.send(embed=fleed_embed(description=f"invite: {invite.url}", author=ctx.author))
        await ctx.send(embed=error_embed("no invite permissions in target guild", ctx.author))

    @developer.command(name="load")
    @commands.is_owner()
    async def dev_load(self, ctx, extension: str):
        try:
            await self.bot.load_extension(f"cogs.{extension}")
            await ctx.send(embed=success_embed(f"loaded `{extension}`", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to load: {e}", ctx.author))

    @developer.command(name="reload", aliases=["rl"])
    @commands.is_owner()
    async def dev_reload(self, ctx, extension: str):
        try:
            await self.bot.reload_extension(f"cogs.{extension}")
            await ctx.send(embed=success_embed(f"reloaded `{extension}`", ctx.author))
        except Exception as e:
            await ctx.send(embed=error_embed(f"failed to reload: {e}", ctx.author))

    @developer.command(name="sync")
    @commands.is_owner()
    async def dev_sync(self, ctx):
        synced = await self.bot.tree.sync()
        await ctx.send(embed=success_embed(f"synced {len(synced)} application commands", ctx.author))

    @developer.group(name="premium", invoke_without_command=True)
    @commands.is_owner()
    async def dev_premium(self, ctx):
        await send_group_help(ctx, ctx.command)

    @dev_premium.command(name="useradd")
    @commands.is_owner()
    async def dev_premium_user_add(self, ctx, user_id: int, duration: int = 0):
        await self.bot.db.execute("INSERT OR REPLACE INTO premium (target_id, target_type, expires_at) VALUES (?, 'user', ?)", (user_id, duration))
        await ctx.send(embed=success_embed(f"granted premium to user `{user_id}`", ctx.author))

    @dev_premium.command(name="userremove")
    @commands.is_owner()
    async def dev_premium_user_remove(self, ctx, user_id: int):
        await self.bot.db.execute("DELETE FROM premium WHERE target_id = ? AND target_type = 'user'", (user_id,))
        await ctx.send(embed=success_embed(f"removed premium from user `{user_id}`", ctx.author))

    @dev_premium.command(name="guildadd")
    @commands.is_owner()
    async def dev_premium_guild_add(self, ctx, guild_id: int, duration: int = 0):
        await self.bot.db.execute("INSERT OR REPLACE INTO premium (target_id, target_type, expires_at) VALUES (?, 'guild', ?)", (guild_id, duration))
        await ctx.send(embed=success_embed(f"granted premium to guild `{guild_id}`", ctx.author))

    @dev_premium.command(name="guildremove")
    @commands.is_owner()
    async def dev_premium_guild_remove(self, ctx, guild_id: int):
        await self.bot.db.execute("DELETE FROM premium WHERE target_id = ? AND target_type = 'guild'", (guild_id,))
        await ctx.send(embed=success_embed(f"removed premium from guild `{guild_id}`", ctx.author))

    @developer.command(name="guild")
    @commands.is_owner()
    async def dev_guild(self, ctx, guild_id: int):
        g = self.bot.get_guild(guild_id)
        if not g:
            return await ctx.send(embed=error_embed("guild not found", ctx.author))
        desc = f"name: {g.name.lower()}\nowner: {str(g.owner).lower()} (`{g.owner_id}`)\nmembers: {g.member_count}\nchannels: {len(g.channels)}\nroles: {len(g.roles)}"
        await ctx.send(embed=fleed_embed(title=f"guild `{guild_id}`", description=desc, author=ctx.author))

    @developer.command(name="user")
    @commands.is_owner()
    async def dev_user(self, ctx, user_id: int):
        u = await self.bot.fetch_user(user_id)
        if not u:
            return await ctx.send(embed=error_embed("user not found", ctx.author))
        desc = f"username: {u.name.lower()}\nbot: {u.bot}\ncreated: {u.created_at.strftime('%y-%m-%d %h:%m:%s')}"
        await ctx.send(embed=fleed_embed(title=f"user `{user_id}`", description=desc, author=ctx.author))

    @developer.group(name="lavalink", invoke_without_command=True)
    @commands.is_owner()
    async def dev_lavalink(self, ctx):
        await send_group_help(ctx, ctx.command)

    @dev_lavalink.command(name="status")
    @commands.is_owner()
    async def dev_lavalink_status(self, ctx):
        await ctx.send(embed=fleed_embed(title="lavalink status", description="nodes connected: 0\nping: 0ms\nstatus: offline / standalone", author=ctx.author))

    @commands.command(name="portal")
    @commands.is_owner()
    async def direct_portal(self, ctx, guild_id: int):
        await self.dev_portal(ctx, guild_id)

    @commands.command(name="reload", aliases=["rl"])
    @commands.is_owner()
    async def direct_reload(self, ctx, extension: str):
        await self.dev_reload(ctx, extension)

    @commands.command(name="load")
    @commands.is_owner()
    async def direct_load(self, ctx, extension: str):
        await self.dev_load(ctx, extension)

    @commands.command(name="sync")
    @commands.is_owner()
    async def direct_sync(self, ctx):
        await self.dev_sync(ctx)

    @commands.command(name="traceback", aliases=["tb"])
    @commands.is_owner()
    async def direct_traceback(self, ctx, error_code: str):
        await self.dev_traceback(ctx, error_code)

    @commands.command(name="blacklist")
    @commands.is_owner()
    async def direct_blacklist(self, ctx, target_type: str = None, target_id: int = None, *, reason: str = "none"):
        if not target_type or not target_id:
            return await send_group_help(ctx, self.dev_blacklist, "developer")
        if target_type.lower() in ["user", "member", "u"]:
            await self.dev_blacklist_user(ctx, target_id, reason=reason)
        elif target_type.lower() in ["guild", "server", "g"]:
            await self.dev_blacklist_guild(ctx, target_id, reason=reason)
        else:
            await send_group_help(ctx, self.dev_blacklist, "developer")

    @commands.command(name="blacklists")
    @commands.is_owner()
    async def direct_blacklists(self, ctx):
        await self.dev_blacklist_list(ctx)

    @commands.command(name="premium")
    @commands.is_owner()
    async def direct_premium(self, ctx, action: str = None, target_type: str = None, target_id: int = None, duration: int = 0):
        if not action or not target_type or not target_id:
            return await send_group_help(ctx, self.dev_premium, "developer")
        if action.lower() in ["add", "grant", "give"]:
            if target_type.lower() in ["user", "u"]:
                await self.dev_premium_user_add(ctx, target_id, duration)
            else:
                await self.dev_premium_guild_add(ctx, target_id, duration)
        elif action.lower() in ["remove", "revoke", "del", "rm"]:
            if target_type.lower() in ["user", "u"]:
                await self.dev_premium_user_remove(ctx, target_id)
            else:
                await self.dev_premium_guild_remove(ctx, target_id)

    @commands.command(name="guild")
    @commands.is_owner()
    async def direct_guild(self, ctx, guild_id: int):
        await self.dev_guild(ctx, guild_id)

    @commands.command(name="user")
    @commands.is_owner()
    async def direct_user(self, ctx, user_id: int):
        await self.dev_user(ctx, user_id)

async def setup(bot):
    await bot.add_cog(Developer(bot))
