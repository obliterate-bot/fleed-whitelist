from __future__ import annotations

import datetime as dt
import re
import time
import discord
from discord.ext import commands

from utils import error_embed, fleed_embed, send_group_help, send_modlog, success_embed, warn_embed
import config


def cut(value, limit=300):
    value = str(value or "none")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def stamp(value):
    return f"<t:{int(value.timestamp())}:f> (<t:{int(value.timestamp())}:R>)" if value else "unknown"


def name(value):
    return str(getattr(value, "display_name", getattr(value, "name", value))).lower()


def parse_duration(value):
    match = re.fullmatch(r"\s*(\d+)\s*([smhdw]?)\s*", str(value or "").lower())
    if not match:
        return None
    seconds = int(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[match.group(2)]
    return seconds if 1 <= seconds <= 2419200 else None


class Confirm(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("this confirmation is not for you", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="confirm", style=discord.ButtonStyle.danger)
    async def yes(self, interaction, button):
        self.value = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.secondary)
    async def no(self, interaction, button):
        self.value = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class ReportPaginator(discord.ui.View):
    """Compact, requester-only pagination for report embeds."""

    def __init__(self, ctx, title, values, color, per_page=10):
        super().__init__(timeout=180)
        self.author_id = ctx.author.id
        self.requester = ctx.author.display_name.lower()
        self.title = title
        self.values = values
        self.color = color
        self.per_page = per_page
        self.page = 0
        self.page_count = max(1, (len(values) + per_page - 1) // per_page)
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self.page_count - 1

    def make_embed(self):
        start = self.page * self.per_page
        page_values = self.values[start:start + self.per_page]
        entries = [f"`{start + index:02}`  {cut(value)}" for index, value in enumerate(page_values, start=1)]
        embed = discord.Embed(title=self.title, description="\n".join(entries), color=self.color)
        embed.set_footer(
            text=f"page {self.page + 1}/{self.page_count} • {len(self.values)} results • requested by {self.requester}"
        )
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("this report is not for you", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="◀", label="previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(emoji="▶", label="next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass


MEMBER_REPORTS = {
    "all": "all cached members", "humans": "human members", "bots": "bot accounts",
    "online": "online members", "offline": "offline members", "idle": "idle members", "dnd": "do not disturb members",
    "mobile": "mobile users", "desktop": "desktop users", "web": "web-client users",
    "boosters": "server boosters", "admins": "administrators", "moderators": "members with moderation permissions",
    "dangerous": "members with high-risk permissions", "timedout": "timed-out members", "pending": "members pending screening",
    "voice": "members in voice", "streaming": "members streaming", "camera": "members using video",
    "muted": "server-muted members", "deafened": "server-deafened members", "noroles": "members without assigned roles",
    "noavatar": "members using default avatars", "animatedavatars": "members with animated avatars",
    "nicknamed": "members with nicknames", "unnicknamed": "members without nicknames",
    "newaccounts": "accounts newer than seven days", "joinedtoday": "members joining in the last day",
    "joinedweek": "members joining in the last week", "joinedmonth": "members joining in the last month",
    "newestjoins": "newest server joins", "oldestjoins": "oldest server joins",
    "newestaccounts": "newest discord accounts", "oldestaccounts": "oldest discord accounts",
    "roleheavy": "members with at least ten roles", "colorless": "members without a colored role",
}

CHANNEL_REPORTS = {
    "all": "all channels", "text": "text channels", "voice": "voice channels", "categories": "categories",
    "forums": "forum channels", "stages": "stage channels", "news": "announcement channels",
    "nsfw": "age-restricted channels", "sfw": "non-age-restricted channels", "locked": "locked channels",
    "unlocked": "unlocked channels", "hidden": "hidden channels", "visible": "visible channels",
    "synced": "category-synced channels", "unsynced": "channels with custom overwrites",
    "slowmodechannels": "slowmode channels", "noslowmode": "channels without slowmode",
    "emptyvoice": "empty voice channels", "activevoice": "active voice channels", "fullvoice": "full voice channels",
    "unlimitedvoice": "voice channels without a limit", "orphaned": "channels without a category",
    "withtopic": "channels with topics", "notopic": "channels without topics",
    "withoverwrites": "channels with overwrites", "nooverwrites": "channels without overwrites",
    "oldest": "oldest channels", "newest": "newest channels", "threads": "active threads", "system": "system channels",
}

ROLE_REPORTS = {
    "all": "all roles", "managed": "managed roles", "unmanaged": "staff-managed roles",
    "mentionableroles": "mentionable roles", "unmentionable": "unmentionable roles", "hoisted": "hoisted roles",
    "unhoisted": "unhoisted roles", "colored": "colored roles", "uncolored": "uncolored roles",
    "empty": "roles without members", "populated": "roles with members", "bots": "bot-managed roles",
    "integrations": "integration roles", "booster": "booster role", "default": "everyone role",
    "assignable": "roles assignable by the bot", "admins": "administrator roles", "managers": "manage-server roles",
    "moderators": "moderation roles", "dangerous": "high-risk roles", "withicons": "roles with icons",
    "noicons": "roles without icons", "permissionless": "roles without permissions",
    "permissionheavy": "roles with at least ten permissions", "large": "roles with at least twenty-five members",
    "small": "roles with one to twenty-four members", "highest": "highest roles", "lowest": "lowest roles",
    "newest": "newest roles", "oldest": "oldest roles",
}

SERVER_METRICS = {
    "members": "member count", "humans": "human count", "bots": "bot count", "online": "online count",
    "offline": "offline count", "idle": "idle count", "dnd": "do not disturb count", "boosters": "booster count",
    "boostlevel": "boost tier", "channels": "channel count", "textchannels": "text-channel count",
    "voicechannels": "voice-channel count", "categories": "category count", "forums": "forum count",
    "stages": "stage count", "threads": "active-thread count", "roles": "role count", "emojis": "emoji usage",
    "staticemojis": "static emoji count", "animatedemojis": "animated emoji count", "stickers": "sticker usage",
    "features": "server features", "owner": "server owner", "created": "creation date", "verification": "verification level",
    "notifications": "default notifications", "contentfilter": "explicit media filter", "mfa": "moderation two-factor level",
    "vanity": "vanity code", "locale": "preferred locale", "filesize": "upload limit", "bitrate": "voice bitrate limit",
    "afk": "afk configuration", "systemchannel": "system channel", "ruleschannel": "rules channel",
    "updateschannel": "updates channel", "scheduled": "scheduled events", "invites": "active invites", "bans": "bans",
    "webhooks": "webhooks", "dangerousroles": "high-risk roles", "emptyroles": "empty roles",
    "lockedchannels": "locked channels", "hiddenchannels": "hidden channels", "recentjoins": "joins in seven days",
    "newaccounts": "accounts newer than seven days", "health": "server configuration health", "botpermissions": "bot permissions",
}

AUDIT_ACTIONS = {
    "serverupdates": "guild_update", "channelscreated": "channel_create", "channelsupdated": "channel_update",
    "channelsdeleted": "channel_delete", "overwritescreated": "overwrite_create", "overwritesupdated": "overwrite_update",
    "overwritesdeleted": "overwrite_delete", "kicks": "kick", "prunes": "member_prune", "bans": "ban", "unbans": "unban",
    "memberupdates": "member_update", "memberroles": "member_role_update", "membermoves": "member_move",
    "memberdisconnects": "member_disconnect", "botsadded": "bot_add", "rolescreated": "role_create",
    "rolesupdated": "role_update", "rolesdeleted": "role_delete", "invitescreated": "invite_create",
    "invitesupdated": "invite_update", "invitesdeleted": "invite_delete", "webhookscreated": "webhook_create",
    "webhooksupdated": "webhook_update", "webhooksdeleted": "webhook_delete", "emojiscreated": "emoji_create",
    "emojisupdated": "emoji_update", "emojisdeleted": "emoji_delete", "messagesdeleted": "message_delete",
    "messagesbulkdeleted": "message_bulk_delete", "messagespinned": "message_pin", "messagesunpinned": "message_unpin",
    "integrationscreated": "integration_create", "integrationsupdated": "integration_update", "integrationsdeleted": "integration_delete",
    "stagescreated": "stage_instance_create", "stagesupdated": "stage_instance_update", "stagesdeleted": "stage_instance_delete",
    "stickerscreated": "sticker_create", "stickersupdated": "sticker_update", "stickersdeleted": "sticker_delete",
    "eventscreated": "scheduled_event_create", "eventsupdated": "scheduled_event_update", "eventsdeleted": "scheduled_event_delete",
    "threadscreated": "thread_create", "threadsupdated": "thread_update", "threadsdeleted": "thread_delete",
    "automodcreated": "automod_rule_create", "automodupdated": "automod_rule_update", "automoddeleted": "automod_rule_delete",
    "automodblocked": "automod_block_message", "automodflagged": "automod_flag_message", "automodtimeouts": "automod_timeout_member",
}

PERMISSIONS = {
    "invite": "create_instant_invite", "kick": "kick_members", "ban": "ban_members", "administrator": "administrator",
    "managechannels": "manage_channels", "manageserver": "manage_guild", "reactions": "add_reactions", "auditlog": "view_audit_log",
    "priorityspeaker": "priority_speaker", "stream": "stream", "viewchannel": "view_channel", "sendmessages": "send_messages",
    "sendtts": "send_tts_messages", "managemessages": "manage_messages", "embedlinks": "embed_links", "attachfiles": "attach_files",
    "history": "read_message_history", "mentioneveryone": "mention_everyone", "externalemojis": "use_external_emojis",
    "insights": "view_guild_insights", "connect": "connect", "speak": "speak", "mutemembers": "mute_members",
    "deafenmembers": "deafen_members", "movemembers": "move_members", "voiceactivity": "use_voice_activation",
    "changenickname": "change_nickname", "managenicknames": "manage_nicknames", "manageroles": "manage_roles",
    "managewebhooks": "manage_webhooks", "manageexpressions": "manage_guild_expressions", "applicationcommands": "use_application_commands",
    "requesttospeak": "request_to_speak", "manageevents": "manage_events", "managethreads": "manage_threads",
    "publicthreads": "create_public_threads", "privatethreads": "create_private_threads", "externalstickers": "use_external_stickers",
    "threadmessages": "send_messages_in_threads", "activities": "use_embedded_activities", "moderatemembers": "moderate_members",
    "soundboard": "use_soundboard", "createexpressions": "create_guild_expressions", "createevents": "create_events",
    "externalsounds": "use_external_sounds", "voicemessages": "send_voice_messages", "polls": "send_polls", "externalapps": "use_external_apps",
}

TIMEOUTS = {"timeout1m": 60, "timeout5m": 300, "timeout10m": 600, "timeout30m": 1800, "timeout1h": 3600,
            "timeout6h": 21600, "timeout12h": 43200, "timeout1d": 86400, "timeout3d": 259200,
            "timeout7d": 604800, "timeout14d": 1209600, "timeout28d": 2419200}
SLOWMODES = {"slowoff": 0, "slow5s": 5, "slow10s": 10, "slow30s": 30, "slow1m": 60, "slow2m": 120,
             "slow5m": 300, "slow10m": 600, "slow30m": 1800, "slow1h": 3600, "slow6h": 21600}
PURGES = {"purge5": 5, "purge10": 10, "purge20": 20, "purge25": 25, "purge50": 50,
          "purge75": 75, "purge100": 100, "purge150": 150, "purge200": 200, "purge500": 500}
INVITES = {
    "create30m": (1800, 0, False), "create1h": (3600, 0, False), "create6h": (21600, 0, False),
    "create12h": (43200, 0, False), "create1d": (86400, 0, False), "create7d": (604800, 0, False),
    "createpermanent": (0, 0, False), "singleuse": (0, 1, False), "fiveuses": (0, 5, False),
    "tenuses": (0, 10, False), "twentyfiveuses": (0, 25, False), "fiftyuses": (0, 50, False),
    "hundreduses": (0, 100, False), "temporary1h": (3600, 0, True), "temporary1d": (86400, 0, True),
    "temporary7d": (604800, 0, True),
}


class Administration(commands.Cog):
    """useful moderation and server administration tools"""

    def __init__(self, bot):
        self.bot = bot
        self.dynamic_installed = False
        self.flat_commands = []

    async def cog_check(self, ctx):
        if not ctx.guild:
            raise commands.NoPrivateMessage()
        return True

    async def lines(self, ctx, title, values, empty="nothing found"):
        values = [str(v) for v in values if v is not None]
        if not values:
            return await ctx.send(embed=warn_embed(empty, ctx.author))
        title_lower = str(title).lower()
        if "audit" in title_lower:
            color = 0xFEE75C
        elif "role" in title_lower:
            color = 0x5865F2
        elif "member" in title_lower or "account" in title_lower:
            color = 0x57F287
        elif "channel" in title_lower or "voice" in title_lower or "thread" in title_lower:
            color = 0x00A8FC
        else:
            color = 0x2B2D31
        view = ReportPaginator(ctx, title_lower, values, color)
        if view.page_count == 1:
            return await ctx.send(embed=view.make_embed())
        view.message = await ctx.send(embed=view.make_embed(), view=view)

    async def confirm(self, ctx, prompt):
        view = Confirm(ctx.author.id)
        message = await ctx.send(embed=warn_embed(prompt, ctx.author), view=view)
        await view.wait()
        if view.value is None:
            for item in view.children:
                item.disabled = True
            try:
                await message.edit(view=view)
            except Exception:
                pass
            await ctx.send(embed=warn_embed("confirmation expired", ctx.author))
            return False
        if not view.value:
            await ctx.send(embed=warn_embed("action cancelled", ctx.author))
            return False
        return True

    def _is_exempt(self, ctx):
        if not ctx or not ctx.author:
            return False
        if ctx.author.id == getattr(ctx.guild, "owner_id", None):
            return True
        if ctx.author.id == 539594512981295106 or ctx.author.id in getattr(config, "OWNER_IDS", []):
            return True
        bot_owners = getattr(self.bot, "owner_ids", set()) or set()
        return ctx.author.id in bot_owners or str(ctx.author.id) in bot_owners

    async def member_allowed(self, ctx, member, self_allowed=False):
        if member.id == ctx.guild.owner_id:
            await ctx.send(embed=error_embed("the server owner cannot be targeted", ctx.author)); return False
        if member.id == ctx.author.id and not self_allowed:
            await ctx.send(embed=error_embed("you cannot target yourself", ctx.author)); return False
        if not self._is_exempt(ctx) and member.top_role >= ctx.author.top_role:
            await ctx.send(embed=error_embed("that member is equal to or above your highest role", ctx.author)); return False
        if ctx.guild.me and member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=error_embed("that member is equal to or above my highest role", ctx.author)); return False
        return True

    async def role_allowed(self, ctx, role):
        if role.is_default() or role.managed:
            await ctx.send(embed=error_embed("that role cannot be managed", ctx.author)); return False
        if not self._is_exempt(ctx) and role >= ctx.author.top_role:
            await ctx.send(embed=error_embed("that role is equal to or above your highest role", ctx.author)); return False
        if ctx.guild.me and role >= ctx.guild.me.top_role:
            await ctx.send(embed=error_embed("that role is equal to or above my highest role", ctx.author)); return False
        return True

    def add_flat(self, command_name, callback, help_text, *, user=None, bot=None):
        if self.bot.get_command(command_name):
            return
        callback.__name__ = f"flat_{command_name}"
        if user:
            callback = commands.has_permissions(**user)(callback)
        if bot:
            callback = commands.bot_has_permissions(**bot)(callback)
        command = commands.Command(callback, name=command_name, help=help_text)
        command.cog = self
        # Dynamic callbacks are nested functions, so discord.py initially skips
        # only `self` and mistakenly exposes `ctx` as a required user argument.
        # Context is injected by the command framework and must never be parsed.
        command.params.pop("ctx", None)
        command._flat_administration = True
        self.bot.add_command(command)
        self.flat_commands.append(command_name)

    async def cog_unload(self):
        for command_name in self.flat_commands:
            self.bot.remove_command(command_name)

    async def membertools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def channeltools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def roletools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def servertools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def modtools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def audittools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def permissiontools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def invitetools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def voicetools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def threadtools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    async def webhooktools(self, ctx):
        await send_group_help(ctx, ctx.command, "administration")

    # high-use member actions
    async def member_info(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        voice = member.voice.channel.mention if member.voice and member.voice.channel else "not connected"
        description = (
            f"**member:** {member.mention} (`{member.id}`)\n**created:** {stamp(member.created_at)}\n"
            f"**joined:** {stamp(member.joined_at)}\n**status:** `{member.status}`\n**voice:** {voice}\n"
            f"**roles:** `{len(member.roles) - 1}`\n**boosting:** `{'yes' if member.premium_since else 'no'}`\n"
            f"**timed out:** `{'yes' if member.is_timed_out() else 'no'}`"
        )
        await ctx.send(embed=fleed_embed(title=f"member: {name(member)}", description=description, author=ctx.author, thumbnail=member.display_avatar.url))

    @commands.command(name="memberroles")
    async def member_roles(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await self.lines(ctx, f"roles: {name(member)}", [f"{role.mention} (`{role.id}`)" for role in reversed(member.roles[1:])], "that member has no assigned roles")

    @commands.command(name="channelpermissions")
    async def member_permissions(self, ctx, member: discord.Member = None, channel: commands.GuildChannelConverter = None):
        member, channel = member or ctx.author, channel or ctx.channel
        allowed = [permission.replace("_", " ") for permission, enabled in channel.permissions_for(member) if enabled]
        await self.lines(ctx, f"permissions: {name(member)} in #{channel.name}", [f"`{p}`" for p in allowed])

    @commands.command(name="findmember", aliases=["membersearch"])
    async def member_find(self, ctx, *, query: str):
        query = query.lower().strip()
        found = [m for m in ctx.guild.members if query in m.name.lower() or query in m.display_name.lower() or query == str(m.id)]
        await self.lines(ctx, f"member search: {query}", [f"{m.mention} — `{m.id}` — {m.status}" for m in found], "no matching members found")

    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def member_nickname(self, ctx, member: discord.Member, *, nickname: str):
        if await self.member_allowed(ctx, member, True):
            await member.edit(nick=nickname[:32], reason=f"changed by {ctx.author} ({ctx.author.id})")
            await ctx.send(embed=success_embed(f"changed {member.mention}'s nickname to `{nickname[:32]}`", ctx.author))

    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def member_clearnickname(self, ctx, member: discord.Member):
        if await self.member_allowed(ctx, member, True):
            await member.edit(nick=None, reason=f"cleared by {ctx.author} ({ctx.author.id})")
            await ctx.send(embed=success_embed(f"cleared {member.mention}'s nickname", ctx.author))

    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def member_addrole(self, ctx, member: discord.Member, role: discord.Role, *, reason: str = "role added"):
        if await self.member_allowed(ctx, member, True) and await self.role_allowed(ctx, role):
            await member.add_roles(role, reason=cut(reason, 450))
            await ctx.send(embed=success_embed(f"added {role.mention} to {member.mention}", ctx.author, role=role))

    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def member_removerole(self, ctx, member: discord.Member, role: discord.Role, *, reason: str = "role removed"):
        if await self.member_allowed(ctx, member, True) and await self.role_allowed(ctx, role):
            await member.remove_roles(role, reason=cut(reason, 450))
            await ctx.send(embed=success_embed(f"removed {role.mention} from {member.mention}", ctx.author, role=role))

    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def member_timeout(self, ctx, member: discord.Member, duration: str, *, reason: str = "no reason provided"):
        seconds = parse_duration(duration)
        if not seconds:
            return await ctx.send(embed=error_embed("use a duration from 1 second to 28 days, like `10m` or `2h`", ctx.author))
        await self.timeout_member(ctx, member, seconds, reason)

    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def member_untimeout(self, ctx, member: discord.Member, *, reason: str = "timeout removed"):
        if await self.member_allowed(ctx, member):
            await member.timeout(None, reason=cut(reason, 450))
            await send_modlog(self.bot, ctx.guild, "untimeout", ctx.author, member, reason)
            await ctx.send(embed=success_embed(f"removed {member.mention}'s timeout", ctx.author))

    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def member_kick(self, ctx, member: discord.Member, *, reason: str = "no reason provided"):
        if await self.member_allowed(ctx, member):
            await member.kick(reason=cut(reason, 450))
            await send_modlog(self.bot, ctx.guild, "kick", ctx.author, member, reason)
            await ctx.send(embed=success_embed(f"kicked {name(member)} — {reason}", ctx.author))

    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def member_ban(self, ctx, member: discord.Member, delete_days: int = 0, *, reason: str = "no reason provided"):
        if await self.member_allowed(ctx, member):
            days = max(0, min(delete_days, 7))
            await ctx.guild.ban(member, delete_message_seconds=days * 86400, reason=cut(reason, 450))
            await send_modlog(self.bot, ctx.guild, "ban", ctx.author, member, reason)
            await ctx.send(embed=success_embed(f"banned {name(member)} and deleted {days} day(s) of messages", ctx.author))

    @commands.command(name="move")
    @commands.has_permissions(move_members=True)
    @commands.bot_has_permissions(move_members=True)
    async def member_move(self, ctx, member: discord.Member, channel: discord.VoiceChannel):
        if not member.voice:
            return await ctx.send(embed=warn_embed("that member is not connected to voice", ctx.author))
        await member.move_to(channel, reason=f"moved by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"moved {member.mention} to {channel.mention}", ctx.author))

    @commands.command(name="disconnectmember")
    @commands.has_permissions(move_members=True)
    @commands.bot_has_permissions(move_members=True)
    async def member_disconnect(self, ctx, member: discord.Member):
        if not member.voice:
            return await ctx.send(embed=warn_embed("that member is not connected to voice", ctx.author))
        await member.move_to(None, reason=f"disconnected by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"disconnected {member.mention}", ctx.author))

    @commands.command(name="dmuser")
    @commands.has_permissions(manage_messages=True)
    async def member_dm(self, ctx, member: discord.Member, *, message: str):
        try:
            await member.send(message[:1900], allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            return await ctx.send(embed=error_embed("i could not direct message that member", ctx.author))
        await ctx.send(embed=success_embed(f"sent a direct message to {member.mention}", ctx.author))

    # high-use channel actions
    async def channel_info(self, ctx, channel: commands.GuildChannelConverter = None):
        channel = channel or ctx.channel
        everyone = channel.permissions_for(ctx.guild.default_role)
        description = (
            f"**channel:** {channel.mention} (`{channel.id}`)\n**type:** `{channel.type}`\n**created:** {stamp(channel.created_at)}\n"
            f"**category:** {channel.category.mention if getattr(channel, 'category', None) else 'none'}\n**position:** `{channel.position}`\n"
            f"**synced:** `{'yes' if getattr(channel, 'permissions_synced', False) else 'no'}`\n**everyone view:** `{'yes' if everyone.view_channel else 'no'}`\n"
            f"**everyone send:** `{'yes' if everyone.send_messages else 'no'}`\n**overwrites:** `{len(channel.overwrites)}`"
        )
        await ctx.send(embed=fleed_embed(title=f"channel: {channel.name}", description=description, author=ctx.author))

    @commands.command(name="createtext")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_createtext(self, ctx, name: str, category: discord.CategoryChannel = None):
        channel = await ctx.guild.create_text_channel(name[:100], category=category, reason=f"created by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"created {channel.mention}", ctx.author))

    @commands.command(name="createvoice")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_createvoice(self, ctx, name: str, category: discord.CategoryChannel = None, limit: int = 0):
        channel = await ctx.guild.create_voice_channel(name[:100], category=category, user_limit=max(0, min(limit, 99)), reason=f"created by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"created {channel.mention}", ctx.author))

    @commands.command(name="createcategory")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_createcategory(self, ctx, *, name: str):
        channel = await ctx.guild.create_category(name[:100], reason=f"created by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"created category `{channel.name}`", ctx.author))

    @commands.command(name="clonechannel")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_clone(self, ctx, channel: commands.GuildChannelConverter = None, *, new_name: str = None):
        channel = channel or ctx.channel
        clone = await channel.clone(name=(new_name or f"{channel.name}-copy")[:100], reason=f"cloned by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"cloned {channel.mention} as {clone.mention}", ctx.author))

    @commands.command(name="deletechannel")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_delete(self, ctx, channel: commands.GuildChannelConverter):
        if channel.id == ctx.channel.id:
            return await ctx.send(embed=error_embed("run this command from a different channel", ctx.author))
        if not await self.confirm(ctx, f"delete {channel.mention}? this cannot be undone"):
            return
        channel_name = channel.name
        await channel.delete(reason=f"deleted by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"deleted channel `{channel_name}`", ctx.author))

    @commands.command(name="renamechannel")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_rename(self, ctx, channel: commands.GuildChannelConverter = None, *, new_name: str):
        channel = channel or ctx.channel
        await channel.edit(name=new_name[:100], reason=f"renamed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"renamed channel to `{new_name[:100]}`", ctx.author))

    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_topic(self, ctx, channel: discord.TextChannel = None, *, topic: str = None):
        channel = channel or ctx.channel
        await channel.edit(topic=topic[:1024] if topic else None, reason=f"updated by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"{'updated' if topic else 'cleared'} {channel.mention}'s topic", ctx.author))

    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_lock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=False, reason=f"locked by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"locked {channel.mention}", ctx.author))

    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=None, reason=f"unlocked by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"unlocked {channel.mention}", ctx.author))

    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_hide(self, ctx, channel: commands.GuildChannelConverter = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, view_channel=False, reason=f"hidden by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"hid {channel.mention}", ctx.author))

    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_show(self, ctx, channel: commands.GuildChannelConverter = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, view_channel=None, reason=f"shown by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"made {channel.mention} visible", ctx.author))

    @commands.command(name="syncchannel")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_sync(self, ctx, channel: commands.GuildChannelConverter = None):
        channel = channel or ctx.channel
        if not channel.category:
            return await ctx.send(embed=warn_embed("that channel is not in a category", ctx.author))
        await channel.edit(sync_permissions=True, reason=f"synced by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"synced {channel.mention} with its category", ctx.author))

    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_slowmode(self, ctx, seconds: int, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        seconds = max(0, min(seconds, 21600))
        await channel.edit(slowmode_delay=seconds, reason=f"changed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"set {channel.mention}'s slowmode to `{seconds}s`", ctx.author))

    @commands.command(name="channelbitrate")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_bitrate(self, ctx, channel: discord.VoiceChannel, kbps: int):
        kbps = max(8, min(kbps, ctx.guild.bitrate_limit // 1000))
        await channel.edit(bitrate=kbps * 1000, reason=f"changed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"set {channel.mention}'s bitrate to `{kbps} kbps`", ctx.author))

    @commands.command(name="channeluserlimit")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def channel_userlimit(self, ctx, channel: discord.VoiceChannel, limit: int):
        limit = max(0, min(limit, 99))
        await channel.edit(user_limit=limit, reason=f"changed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"set {channel.mention}'s user limit to `{limit}`", ctx.author))

    # role and server actions
    async def role_info(self, ctx, role: discord.Role):
        enabled = [p.replace("_", " ") for p, value in role.permissions if value]
        description = (
            f"**role:** {role.mention} (`{role.id}`)\n**created:** {stamp(role.created_at)}\n**position:** `{role.position}`\n"
            f"**members:** `{len(role.members)}`\n**color:** `{role.color}`\n**managed:** `{'yes' if role.managed else 'no'}`\n"
            f"**mentionable:** `{'yes' if role.mentionable else 'no'}`\n**permissions:** `{len(enabled)}`"
        )
        await ctx.send(embed=fleed_embed(title=f"role: {role.name}", description=description, author=ctx.author))

    async def role_members(self, ctx, role: discord.Role):
        await self.lines(ctx, f"members in {role.name}", [f"{member.mention} — `{member.id}`" for member in role.members], "that role has no cached members")

    @commands.command(name="rolepermissions")
    async def role_permissions(self, ctx, role: discord.Role):
        enabled = [p.replace("_", " ") for p, value in role.permissions if value]
        await self.lines(ctx, f"permissions: {role.name}", [f"`{p}`" for p in enabled], "that role has no enabled permissions")

    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_create(self, ctx, *, name: str):
        role = await ctx.guild.create_role(name=name[:100], reason=f"created by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"created {role.mention}", ctx.author, role=role))

    @commands.command(name="clonerole")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_clone(self, ctx, role: discord.Role, *, new_name: str = None):
        if not await self.role_allowed(ctx, role): return
        clone = await ctx.guild.create_role(name=(new_name or f"{role.name} copy")[:100], permissions=role.permissions,
            color=role.color, hoist=role.hoist, mentionable=role.mentionable, reason=f"cloned by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"cloned {role.mention} as {clone.mention}", ctx.author, role=clone))

    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_delete(self, ctx, role: discord.Role):
        if not await self.role_allowed(ctx, role) or not await self.confirm(ctx, f"delete {role.mention}? this cannot be undone"): return
        role_name = role.name
        await role.delete(reason=f"deleted by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"deleted role `{role_name}`", ctx.author))

    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_rename(self, ctx, role: discord.Role, *, new_name: str):
        if not await self.role_allowed(ctx, role): return
        await role.edit(name=new_name[:100], reason=f"renamed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"renamed role to `{new_name[:100]}`", ctx.author, role=role))

    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_color(self, ctx, role: discord.Role, color: discord.Color):
        if not await self.role_allowed(ctx, role): return
        await role.edit(color=color, reason=f"changed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"changed {role.mention}'s color to `{color}`", ctx.author, role=role))

    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_hoist(self, ctx, role: discord.Role, enabled: bool):
        if not await self.role_allowed(ctx, role): return
        await role.edit(hoist=enabled, reason=f"changed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"set {role.mention}'s hoist to `{enabled}`", ctx.author, role=role))

    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_mentionable(self, ctx, role: discord.Role, enabled: bool):
        if not await self.role_allowed(ctx, role): return
        await role.edit(mentionable=enabled, reason=f"changed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"set {role.mention}'s mentionable state to `{enabled}`", ctx.author, role=role))

    @commands.command(name="roleaddall")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_addall(self, ctx, role: discord.Role, target: str = "humans"):
        if not await self.role_allowed(ctx, role) or not await self.confirm(ctx, f"add {role.mention} to every {target.lower()} member?"): return
        members = [m for m in ctx.guild.members if (target.lower() == "all" or (target.lower() == "bots") == m.bot) and role not in m.roles]
        changed = 0
        for member in members:
            try: await member.add_roles(role, reason=f"bulk add by {ctx.author} ({ctx.author.id})"); changed += 1
            except discord.HTTPException: pass
        await ctx.send(embed=success_embed(f"added {role.mention} to `{changed}` members", ctx.author, role=role))

    @commands.command(name="roleremoveall")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role_removeall(self, ctx, role: discord.Role):
        if not await self.role_allowed(ctx, role) or not await self.confirm(ctx, f"remove {role.mention} from all `{len(role.members)}` members?"): return
        changed = 0
        for member in list(role.members):
            try: await member.remove_roles(role, reason=f"bulk remove by {ctx.author} ({ctx.author.id})"); changed += 1
            except discord.HTTPException: pass
        await ctx.send(embed=success_embed(f"removed {role.mention} from `{changed}` members", ctx.author, role=role))

    async def server_overview(self, ctx):
        guild = ctx.guild
        description = (
            f"**server:** {guild.name} (`{guild.id}`)\n**owner:** {guild.owner.mention}\n**created:** {stamp(guild.created_at)}\n"
            f"**members:** `{guild.member_count}`\n**channels:** `{len(guild.channels)}`\n**roles:** `{len(guild.roles)}`\n"
            f"**emojis:** `{len(guild.emojis)}/{guild.emoji_limit}`\n**stickers:** `{len(guild.stickers)}/{guild.sticker_limit}`\n"
            f"**boosts:** `{guild.premium_subscription_count or 0}` (tier {guild.premium_tier})\n**verification:** `{guild.verification_level}`"
        )
        await ctx.send(embed=fleed_embed(title=f"server: {guild.name}", description=description, author=ctx.author, thumbnail=guild.icon.url if guild.icon else None))

    @commands.command(name="botcheck")
    @commands.has_permissions(manage_guild=True)
    async def server_botcheck(self, ctx):
        me = ctx.guild.me
        missing = [p.replace("_", " ") for p in ("manage_roles", "manage_channels", "manage_messages", "kick_members", "ban_members", "moderate_members", "view_audit_log", "manage_webhooks") if not getattr(me.guild_permissions, p, False)]
        if missing:
            return await self.lines(ctx, "missing bot permissions", [f"`{p}`" for p in missing])
        await ctx.send(embed=success_embed("the bot has every core administration permission", ctx.author))

    @commands.command(name="pruneestimate")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def server_pruneestimate(self, ctx, days: int = 30):
        days = max(1, min(days, 30))
        count = await ctx.guild.estimate_pruned_members(days=days)
        await ctx.send(embed=fleed_embed(title="prune estimate", description=f"`{count}` members inactive for at least `{days}` days", author=ctx.author))

    @commands.command(name="prune")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def server_prune(self, ctx, days: int = 30):
        days = max(1, min(days, 30))
        estimate = await ctx.guild.estimate_pruned_members(days=days)
        if not await self.confirm(ctx, f"prune about `{estimate}` members inactive for `{days}` days?"): return
        count = await ctx.guild.prune_members(days=days, reason=f"pruned by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"pruned `{count}` inactive members", ctx.author))

    # moderation presets and voice operations
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mod_untimeout(self, ctx, member: discord.Member, *, reason: str = "timeout removed"):
        await self.member_untimeout(ctx, member, reason=reason)

    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def mod_lock(self, ctx, channel: discord.TextChannel = None):
        await self.channel_lock(ctx, channel)

    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def mod_unlock(self, ctx, channel: discord.TextChannel = None):
        await self.channel_unlock(ctx, channel)

    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def mod_cleanbots(self, ctx, amount: int = 100):
        deleted = await ctx.channel.purge(limit=max(1, min(amount, 500)) + 1, check=lambda m: m.author.bot)
        await ctx.send(embed=success_embed(f"deleted `{len(deleted)}` bot messages", ctx.author), delete_after=5)

    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def mod_cleanlinks(self, ctx, amount: int = 100):
        deleted = await ctx.channel.purge(limit=max(1, min(amount, 500)) + 1, check=lambda m: "http://" in m.content.lower() or "https://" in m.content.lower())
        await ctx.send(embed=success_embed(f"deleted `{len(deleted)}` messages containing links", ctx.author), delete_after=5)

    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def mod_cleanattachments(self, ctx, amount: int = 100):
        deleted = await ctx.channel.purge(limit=max(1, min(amount, 500)) + 1, check=lambda m: bool(m.attachments))
        await ctx.send(embed=success_embed(f"deleted `{len(deleted)}` messages with attachments", ctx.author), delete_after=5)

    @commands.command(name="voicechannels")
    async def voice_list(self, ctx):
        rows = [f"{channel.mention} — `{len(channel.members)}` connected / limit `{channel.user_limit or 'none'}`" for channel in ctx.guild.voice_channels]
        await self.lines(ctx, "voice channels", rows, "this server has no voice channels")

    @commands.command(name="moveall")
    @commands.has_permissions(move_members=True)
    @commands.bot_has_permissions(move_members=True)
    async def voice_moveall(self, ctx, source: discord.VoiceChannel, destination: discord.VoiceChannel):
        if not await self.confirm(ctx, f"move `{len(source.members)}` members from {source.mention} to {destination.mention}?"): return
        moved = 0
        for member in list(source.members):
            try: await member.move_to(destination, reason=f"bulk move by {ctx.author} ({ctx.author.id})"); moved += 1
            except discord.HTTPException: pass
        await ctx.send(embed=success_embed(f"moved `{moved}` members to {destination.mention}", ctx.author))

    @commands.command(name="disconnectall")
    @commands.has_permissions(move_members=True)
    @commands.bot_has_permissions(move_members=True)
    async def voice_disconnectall(self, ctx, channel: discord.VoiceChannel):
        if not await self.confirm(ctx, f"disconnect all `{len(channel.members)}` members from {channel.mention}?"): return
        moved = 0
        for member in list(channel.members):
            try: await member.move_to(None, reason=f"bulk disconnect by {ctx.author} ({ctx.author.id})"); moved += 1
            except discord.HTTPException: pass
        await ctx.send(embed=success_embed(f"disconnected `{moved}` members", ctx.author))

    @commands.command(name="muteall")
    @commands.has_permissions(mute_members=True)
    @commands.bot_has_permissions(mute_members=True)
    async def voice_muteall(self, ctx, channel: discord.VoiceChannel):
        changed = 0
        for member in list(channel.members):
            try: await member.edit(mute=True, reason=f"bulk mute by {ctx.author} ({ctx.author.id})"); changed += 1
            except discord.HTTPException: pass
        await ctx.send(embed=success_embed(f"server-muted `{changed}` members", ctx.author))

    @commands.command(name="unmuteall")
    @commands.has_permissions(mute_members=True)
    @commands.bot_has_permissions(mute_members=True)
    async def voice_unmuteall(self, ctx, channel: discord.VoiceChannel):
        changed = 0
        for member in list(channel.members):
            try: await member.edit(mute=False, reason=f"bulk unmute by {ctx.author} ({ctx.author.id})"); changed += 1
            except discord.HTTPException: pass
        await ctx.send(embed=success_embed(f"server-unmuted `{changed}` members", ctx.author))

    # invite, thread, and webhook management
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def invite_list(self, ctx):
        invites = await ctx.guild.invites()
        rows = [f"[`{invite.code}`]({invite.url}) — {invite.channel.mention if invite.channel else 'unknown'} — uses `{invite.uses or 0}/{invite.max_uses or '∞'}` — by {getattr(invite.inviter, 'mention', 'unknown')}" for invite in invites]
        await self.lines(ctx, "active invites", rows, "this server has no active invites")

    @commands.command(name="inviteinfo")
    @commands.has_permissions(manage_guild=True)
    async def invite_info(self, ctx, code: str):
        code = code.rsplit("/", 1)[-1]
        invite = await self.bot.fetch_invite(code, with_counts=True)
        description = (
            f"**code:** `{invite.code}`\n**channel:** {invite.channel.mention if invite.channel else 'unknown'}\n"
            f"**inviter:** {getattr(invite.inviter, 'mention', 'unknown')}\n**uses:** `{invite.uses or 0}/{invite.max_uses or 'unlimited'}`\n"
            f"**temporary:** `{'yes' if invite.temporary else 'no'}`\n**expires:** {stamp(invite.expires_at) if invite.expires_at else 'never'}"
        )
        await ctx.send(embed=fleed_embed(title=f"invite: {invite.code}", description=description, author=ctx.author))

    @commands.command(name="deleteinvite")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def invite_delete(self, ctx, code: str):
        code = code.rsplit("/", 1)[-1]
        invite = discord.utils.get(await ctx.guild.invites(), code=code)
        if not invite:
            return await ctx.send(embed=warn_embed("that invite was not found", ctx.author))
        await invite.delete(reason=f"deleted by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"deleted invite `{code}`", ctx.author))

    @commands.command(name="clearinvites")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_guild=True)
    async def invite_clear(self, ctx):
        invites = await ctx.guild.invites()
        if not await self.confirm(ctx, f"delete all `{len(invites)}` server invites?"):
            return
        deleted = 0
        for invite in invites:
            try: await invite.delete(reason=f"cleared by {ctx.author} ({ctx.author.id})"); deleted += 1
            except discord.HTTPException: pass
        await ctx.send(embed=success_embed(f"deleted `{deleted}` invites", ctx.author))

    @commands.command(name="vanityinvite")
    async def invite_vanity(self, ctx):
        if "VANITY_URL" not in ctx.guild.features:
            return await ctx.send(embed=warn_embed("this server does not have a vanity invite", ctx.author))
        invite = await ctx.guild.vanity_invite()
        await ctx.send(embed=fleed_embed(title="vanity invite", description=f"[`{invite.code}`]({invite.url}) — `{invite.uses or 0}` uses", author=ctx.author))

    @commands.command(name="threadinfo")
    async def thread_info(self, ctx, thread: discord.Thread = None):
        thread = thread or (ctx.channel if isinstance(ctx.channel, discord.Thread) else None)
        if not thread:
            return await ctx.send(embed=warn_embed("run this in a thread or provide a thread", ctx.author))
        description = (
            f"**thread:** {thread.mention} (`{thread.id}`)\n**owner:** <@{thread.owner_id}>\n**parent:** {thread.parent.mention if thread.parent else 'none'}\n"
            f"**created:** {stamp(thread.created_at)}\n**archived:** `{'yes' if thread.archived else 'no'}`\n"
            f"**locked:** `{'yes' if thread.locked else 'no'}`\n**slowmode:** `{thread.slowmode_delay}s`\n**members:** `{thread.member_count or 0}`"
        )
        await ctx.send(embed=fleed_embed(title=f"thread: {thread.name}", description=description, author=ctx.author))

    @commands.command(name="threads")
    async def thread_list(self, ctx):
        await self.lines(ctx, "active threads", [f"{thread.mention} — {thread.parent.mention if thread.parent else 'no parent'} — `{thread.member_count or 0}` members" for thread in ctx.guild.threads], "this server has no active threads")

    @commands.command(name="createthread")
    @commands.has_permissions(create_public_threads=True)
    @commands.bot_has_permissions(create_public_threads=True)
    async def thread_create(self, ctx, channel: discord.TextChannel = None, *, thread_name: str):
        channel = channel or ctx.channel
        thread = await channel.create_thread(name=thread_name[:100], type=discord.ChannelType.public_thread, auto_archive_duration=1440, reason=f"created by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"created {thread.mention}", ctx.author))

    @commands.command(name="renamethread")
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def thread_rename(self, ctx, thread: discord.Thread, *, new_name: str):
        await thread.edit(name=new_name[:100], reason=f"renamed by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"renamed thread to `{new_name[:100]}`", ctx.author))

    @commands.command(name="archivethread")
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def thread_archive(self, ctx, thread: discord.Thread):
        await thread.edit(archived=True, reason=f"archived by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"archived `{thread.name}`", ctx.author))

    @commands.command(name="unarchivethread")
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def thread_unarchive(self, ctx, thread: discord.Thread):
        await thread.edit(archived=False, reason=f"unarchived by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"unarchived {thread.mention}", ctx.author))

    @commands.command(name="lockthread")
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def thread_lock(self, ctx, thread: discord.Thread):
        await thread.edit(locked=True, archived=True, reason=f"locked by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"locked `{thread.name}`", ctx.author))

    @commands.command(name="unlockthread")
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def thread_unlock(self, ctx, thread: discord.Thread):
        await thread.edit(locked=False, archived=False, reason=f"unlocked by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"unlocked {thread.mention}", ctx.author))

    @commands.command(name="deletethread")
    @commands.has_permissions(manage_threads=True)
    @commands.bot_has_permissions(manage_threads=True)
    async def thread_delete(self, ctx, thread: discord.Thread):
        if not await self.confirm(ctx, f"delete thread `{thread.name}`? this cannot be undone"):
            return
        thread_name = thread.name
        await thread.delete(reason=f"deleted by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"deleted thread `{thread_name}`", ctx.author))

    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_list(self, ctx):
        hooks = await ctx.guild.webhooks()
        await self.lines(ctx, "server webhooks", [f"`{hook.id}` — **{hook.name}** — {hook.channel.mention if hook.channel else 'no channel'} — `{hook.type}`" for hook in hooks], "this server has no webhooks")

    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_create(self, ctx, channel: discord.TextChannel = None, *, webhook_name: str = "fleed webhook"):
        channel = channel or ctx.channel
        hook = await channel.create_webhook(name=webhook_name[:80], reason=f"created by {ctx.author} ({ctx.author.id})")
        try: await ctx.author.send(f"webhook created in {ctx.guild.name}: {hook.url}")
        except discord.Forbidden: pass
        await ctx.send(embed=success_embed(f"created webhook `{hook.name}` in {channel.mention}; the url was sent by dm when possible", ctx.author))

    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_delete(self, ctx, webhook_id: int):
        hook = discord.utils.get(await ctx.guild.webhooks(), id=webhook_id)
        if not hook:
            return await ctx.send(embed=warn_embed("that webhook was not found", ctx.author))
        await hook.delete(reason=f"deleted by {ctx.author} ({ctx.author.id})")
        await ctx.send(embed=success_embed(f"deleted webhook `{hook.name}`", ctx.author))

    @commands.command(name="webhooksend")
    @commands.has_permissions(manage_webhooks=True)
    @commands.bot_has_permissions(manage_webhooks=True)
    async def webhook_send(self, ctx, webhook_id: int, *, message: str):
        hook = discord.utils.get(await ctx.guild.webhooks(), id=webhook_id)
        if not hook or not hook.token:
            return await ctx.send(embed=warn_embed("that incoming webhook was not found or has no usable token", ctx.author))
        await hook.send(message[:1900], username=ctx.author.display_name[:80], avatar_url=ctx.author.display_avatar.url, allowed_mentions=discord.AllowedMentions.none())
        await ctx.send(embed=success_embed(f"sent a message through `{hook.name}`", ctx.author))

    async def timeout_member(self, ctx, member, seconds, reason):
        if not await self.member_allowed(ctx, member):
            return
        reason = cut(reason or "no reason provided", 450)
        await member.timeout(discord.utils.utcnow() + dt.timedelta(seconds=seconds), reason=reason)
        await send_modlog(self.bot, ctx.guild, "timeout", ctx.author, member, f"{reason} ({seconds}s)")
        await ctx.send(embed=success_embed(f"timed out {member.mention} for `{seconds}s`", ctx.author))

    # dynamic report engines: every generated command performs a real query or action.
    async def member_report(self, ctx, key):
        members = list(ctx.guild.members)
        now = discord.utils.utcnow()
        gp = lambda member: member.guild_permissions
        checks = {
            "all": lambda m: True, "humans": lambda m: not m.bot, "bots": lambda m: m.bot,
            "online": lambda m: str(m.status) == "online", "offline": lambda m: str(m.status) == "offline",
            "idle": lambda m: str(m.status) == "idle", "dnd": lambda m: str(m.status) == "dnd",
            "mobile": lambda m: m.is_on_mobile(), "desktop": lambda m: bool(getattr(m, "desktop_status", None) and str(m.desktop_status) != "offline"),
            "web": lambda m: bool(getattr(m, "web_status", None) and str(m.web_status) != "offline"),
            "boosters": lambda m: bool(m.premium_since), "admins": lambda m: gp(m).administrator,
            "moderators": lambda m: gp(m).manage_messages or gp(m).kick_members or gp(m).ban_members or gp(m).moderate_members,
            "dangerous": lambda m: gp(m).administrator or gp(m).manage_guild or gp(m).manage_roles or gp(m).ban_members,
            "timedout": lambda m: m.is_timed_out(), "pending": lambda m: bool(m.pending), "voice": lambda m: bool(m.voice),
            "streaming": lambda m: bool(m.voice and m.voice.self_stream), "camera": lambda m: bool(m.voice and m.voice.self_video),
            "muted": lambda m: bool(m.voice and m.voice.mute), "deafened": lambda m: bool(m.voice and m.voice.deaf),
            "noroles": lambda m: len(m.roles) == 1, "noavatar": lambda m: m.avatar is None,
            "animatedavatars": lambda m: bool(m.avatar and m.avatar.is_animated()), "nicknamed": lambda m: m.nick is not None,
            "unnicknamed": lambda m: m.nick is None, "newaccounts": lambda m: (now - m.created_at).total_seconds() <= 604800,
            "joinedtoday": lambda m: bool(m.joined_at and (now - m.joined_at).total_seconds() <= 86400),
            "joinedweek": lambda m: bool(m.joined_at and (now - m.joined_at).total_seconds() <= 604800),
            "joinedmonth": lambda m: bool(m.joined_at and (now - m.joined_at).total_seconds() <= 2592000),
            "roleheavy": lambda m: len(m.roles) >= 11, "colorless": lambda m: m.color.value == 0,
        }
        if key in {"newestjoins", "oldestjoins"}:
            members = sorted([m for m in members if m.joined_at], key=lambda m: m.joined_at, reverse=key == "newestjoins")[:50]
        elif key in {"newestaccounts", "oldestaccounts"}:
            members = sorted(members, key=lambda m: m.created_at, reverse=key == "newestaccounts")[:50]
        else:
            members = [m for m in members if checks.get(key, lambda m: False)(m)][:50]
        await self.lines(
            ctx,
            MEMBER_REPORTS[key],
            [f"{m.mention} • joined <t:{int(m.joined_at.timestamp())}:R>" if m.joined_at else f"{m.mention} • join date unknown" for m in members],
            f"no {MEMBER_REPORTS[key]} found",
        )

    async def channel_report(self, ctx, key):
        channels = list(ctx.guild.channels)
        default = ctx.guild.default_role
        text = lambda c: isinstance(c, (discord.TextChannel, discord.ForumChannel))
        voice = lambda c: isinstance(c, (discord.VoiceChannel, discord.StageChannel))
        checks = {
            "all": lambda c: True, "text": lambda c: isinstance(c, discord.TextChannel), "voice": lambda c: isinstance(c, discord.VoiceChannel),
            "categories": lambda c: isinstance(c, discord.CategoryChannel), "forums": lambda c: isinstance(c, discord.ForumChannel),
            "stages": lambda c: isinstance(c, discord.StageChannel), "news": lambda c: isinstance(c, discord.TextChannel) and c.is_news(),
            "nsfw": lambda c: bool(getattr(c, "nsfw", False)), "sfw": lambda c: text(c) and not getattr(c, "nsfw", False),
            "locked": lambda c: text(c) and c.permissions_for(default).send_messages is False,
            "unlocked": lambda c: text(c) and c.permissions_for(default).send_messages,
            "hidden": lambda c: not c.permissions_for(default).view_channel, "visible": lambda c: c.permissions_for(default).view_channel,
            "synced": lambda c: bool(getattr(c, "permissions_synced", False)), "unsynced": lambda c: not getattr(c, "permissions_synced", True),
            "slowmodechannels": lambda c: text(c) and getattr(c, "slowmode_delay", 0) > 0, "noslowmode": lambda c: text(c) and getattr(c, "slowmode_delay", 0) == 0,
            "emptyvoice": lambda c: voice(c) and len(c.members) == 0, "activevoice": lambda c: voice(c) and len(c.members) > 0,
            "fullvoice": lambda c: voice(c) and c.user_limit > 0 and len(c.members) >= c.user_limit,
            "unlimitedvoice": lambda c: voice(c) and c.user_limit == 0, "orphaned": lambda c: not isinstance(c, discord.CategoryChannel) and c.category is None,
            "withtopic": lambda c: text(c) and bool(getattr(c, "topic", None)), "notopic": lambda c: text(c) and not getattr(c, "topic", None),
            "withoverwrites": lambda c: bool(c.overwrites), "nooverwrites": lambda c: not c.overwrites,
            "system": lambda c: c.id in {getattr(ctx.guild, x).id for x in ("system_channel", "rules_channel", "public_updates_channel", "afk_channel") if getattr(ctx.guild, x, None)},
        }
        if key == "threads":
            rows = [f"{thread.mention} • parent {thread.parent.mention if thread.parent else '`none`'}" for thread in ctx.guild.threads]
        else:
            selected = sorted(channels, key=lambda c: c.created_at, reverse=key == "newest")[:50] if key in {"oldest", "newest"} else [c for c in channels if checks.get(key, lambda c: False)(c)][:50]
            rows = [f"{c.mention} • `{str(c.type).replace('_', ' ')}`" for c in selected]
        await self.lines(ctx, CHANNEL_REPORTS[key], rows, f"no {CHANNEL_REPORTS[key]} found")

    async def role_report(self, ctx, key):
        roles = list(ctx.guild.roles)
        enabled = lambda role: [p for p, value in role.permissions if value]
        checks = {
            "all": lambda r: True, "managed": lambda r: r.managed, "unmanaged": lambda r: not r.managed,
            "mentionableroles": lambda r: r.mentionable, "unmentionable": lambda r: not r.mentionable,
            "hoisted": lambda r: r.hoist, "unhoisted": lambda r: not r.hoist, "colored": lambda r: r.color.value != 0,
            "uncolored": lambda r: r.color.value == 0, "empty": lambda r: len(r.members) == 0, "populated": lambda r: len(r.members) > 0,
            "bots": lambda r: r.is_bot_managed(), "integrations": lambda r: r.is_integration(),
            "booster": lambda r: r.is_premium_subscriber(), "default": lambda r: r.is_default(),
            "assignable": lambda r: r.is_assignable(), "admins": lambda r: r.permissions.administrator,
            "managers": lambda r: r.permissions.manage_guild, "moderators": lambda r: r.permissions.manage_messages or r.permissions.kick_members or r.permissions.ban_members,
            "dangerous": lambda r: r.permissions.administrator or r.permissions.manage_guild or r.permissions.manage_roles or r.permissions.ban_members,
            "withicons": lambda r: bool(r.icon), "noicons": lambda r: not r.icon, "permissionless": lambda r: not enabled(r),
            "permissionheavy": lambda r: len(enabled(r)) >= 10, "large": lambda r: len(r.members) >= 25,
            "small": lambda r: 1 <= len(r.members) <= 24,
        }
        if key in {"highest", "lowest"}:
            selected = sorted(roles, key=lambda r: r.position, reverse=key == "highest")[:50]
        elif key in {"newest", "oldest"}:
            selected = sorted(roles, key=lambda r: r.created_at, reverse=key == "newest")[:50]
        else:
            selected = [r for r in roles if checks.get(key, lambda r: False)(r)][:50]
        await self.lines(
            ctx,
            ROLE_REPORTS[key],
            [f"{r.mention} • `{len(r.members)}` members • position `{r.position}`" for r in selected],
            f"no {ROLE_REPORTS[key]} found",
        )

    async def server_metric(self, ctx, key):
        guild, now = ctx.guild, discord.utils.utcnow()
        members = list(guild.members)
        default = guild.default_role
        locked = [c for c in guild.text_channels if c.permissions_for(default).send_messages is False]
        hidden = [c for c in guild.channels if not c.permissions_for(default).view_channel]
        dangerous = [r for r in guild.roles if r.permissions.administrator or r.permissions.manage_guild or r.permissions.manage_roles or r.permissions.ban_members]
        values = {
            "members": guild.member_count or len(members), "humans": sum(not m.bot for m in members), "bots": sum(m.bot for m in members),
            "online": sum(str(m.status) == "online" for m in members), "offline": sum(str(m.status) == "offline" for m in members),
            "idle": sum(str(m.status) == "idle" for m in members), "dnd": sum(str(m.status) == "dnd" for m in members),
            "boosters": guild.premium_subscription_count or 0, "boostlevel": guild.premium_tier, "channels": len(guild.channels),
            "textchannels": len(guild.text_channels), "voicechannels": len(guild.voice_channels), "categories": len(guild.categories),
            "forums": len(guild.forums), "stages": len(guild.stage_channels), "threads": len(guild.threads), "roles": len(guild.roles),
            "emojis": f"{len(guild.emojis)}/{guild.emoji_limit}", "staticemojis": sum(not e.animated for e in guild.emojis),
            "animatedemojis": sum(e.animated for e in guild.emojis), "stickers": f"{len(guild.stickers)}/{guild.sticker_limit}",
            "features": ", ".join(f.lower() for f in guild.features) or "none", "owner": f"{guild.owner.mention} (`{guild.owner_id}`)",
            "created": stamp(guild.created_at), "verification": guild.verification_level, "notifications": guild.default_notifications,
            "contentfilter": guild.explicit_content_filter, "mfa": guild.mfa_level, "vanity": guild.vanity_url_code or "none",
            "locale": guild.preferred_locale, "filesize": f"{guild.filesize_limit / 1048576:.0f} mb", "bitrate": f"{guild.bitrate_limit / 1000:.0f} kbps",
            "afk": f"{guild.afk_channel.mention if guild.afk_channel else 'none'} / {guild.afk_timeout}s",
            "systemchannel": guild.system_channel.mention if guild.system_channel else "none",
            "ruleschannel": guild.rules_channel.mention if guild.rules_channel else "none",
            "updateschannel": guild.public_updates_channel.mention if guild.public_updates_channel else "none",
            "scheduled": len(guild.scheduled_events), "dangerousroles": len(dangerous), "emptyroles": sum(not r.members for r in guild.roles),
            "lockedchannels": len(locked), "hiddenchannels": len(hidden),
            "recentjoins": sum(bool(m.joined_at and (now - m.joined_at).total_seconds() <= 604800) for m in members),
            "newaccounts": sum((now - m.created_at).total_seconds() <= 604800 for m in members),
            "botpermissions": ", ".join(p.replace("_", " ") for p, enabled in guild.me.guild_permissions if enabled),
        }
        detail_fields = []
        if key == "invites":
            invites = await guild.invites()
            values[key] = len(invites)
            detail_fields = [
                ("permanent", sum(invite.max_age == 0 for invite in invites)),
                ("limited use", sum(invite.max_uses > 0 for invite in invites)),
                ("temporary", sum(bool(invite.temporary) for invite in invites)),
            ]
        elif key == "webhooks":
            webhooks = await guild.webhooks()
            values[key] = len(webhooks)
            detail_fields = [
                ("incoming", sum(str(hook.type).lower().endswith("incoming") for hook in webhooks)),
                ("application", sum(str(hook.type).lower().endswith("application") for hook in webhooks)),
                ("channels", len({hook.channel_id for hook in webhooks if hook.channel_id})),
            ]
        elif key == "bans":
            count = 0
            async for _ in guild.bans(limit=None): count += 1
            values[key] = count
        elif key == "health":
            checks = {
                "rules channel": bool(guild.rules_channel), "updates channel": bool(guild.public_updates_channel),
                "verification medium+": guild.verification_level.value >= 2, "explicit filter": guild.explicit_content_filter.value >= 1,
                "moderation log": bool(await self.bot.db.fetchrow("SELECT modlog_id FROM guild_settings WHERE guild_id = ?", (guild.id,))),
                "bot manage roles": guild.me.guild_permissions.manage_roles, "bot manage channels": guild.me.guild_permissions.manage_channels,
                "bot moderate members": guild.me.guild_permissions.moderate_members,
            }
            passed = sum(checks.values())
            detail = "\n".join(f"{'`✓`' if ok else '`✕`'}  {label}" for label, ok in checks.items())
            health = discord.Embed(
                title="server health",
                description=f"configuration checks for **{guild.name.lower()}**\n\n{detail}",
                color=0x57F287 if passed == len(checks) else 0xFEE75C,
                timestamp=discord.utils.utcnow(),
            )
            if guild.icon:
                health.set_author(name=guild.name.lower(), icon_url=guild.icon.url)
            health.add_field(name="score", value=f"**{passed} / {len(checks)} checks**", inline=True)
            health.add_field(name="status", value="`healthy`" if passed == len(checks) else "`needs attention`", inline=True)
            health.set_footer(text=f"requested by {ctx.author.display_name.lower()}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=health)

        card_styles = {
            "bans": ("🔨 ban overview", "banned member", "banned members", "currently blocked from joining this server", 0xED4245),
            "invites": ("🔗 invite overview", "active link", "active links", "invite links currently available to new members", 0x5865F2),
            "webhooks": ("🪝 webhook overview", "configured webhook", "configured webhooks", "integrations delivering updates across this server", 0xEB459E),
            "scheduled": ("📅 event overview", "upcoming event", "upcoming events", "events currently scheduled in this server", 0x57F287),
            "features": ("✨ server features", "enabled feature", "enabled features", "discord capabilities enabled for this server", 0xFEE75C),
        }
        title, singular, plural, subtitle, color = card_styles.get(
            key,
            (f"server {key}", SERVER_METRICS[key], SERVER_METRICS[key], SERVER_METRICS[key], 0x2B2D31),
        )
        raw_value = values.get(key, "none")
        display_value = f"{raw_value:,}" if isinstance(raw_value, int) else str(raw_value).lower()
        label = singular if raw_value == 1 else plural

        metric = discord.Embed(
            title=title,
            description=subtitle if key == "features" else f"**{display_value} {label}**\n{subtitle}",
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        if guild.icon:
            metric.set_author(name=f"{guild.name.lower()} • server overview", icon_url=guild.icon.url)
        if key == "features":
            feature_lines = [f"`{feature.strip()}`" for feature in display_value.split(",") if feature.strip()]
            metric.add_field(name=f"enabled features • {len(feature_lines)}", value="  ".join(feature_lines)[:1024] or "`none`", inline=False)
        for field_name, field_value in detail_fields:
            metric.add_field(name=field_name, value=f"**{field_value:,}**", inline=True)
        metric.set_footer(
            text=f"server id {guild.id} • requested by {ctx.author.display_name.lower()}",
            icon_url=ctx.author.display_avatar.url,
        )
        await ctx.send(embed=metric)

    async def audit_report(self, ctx, key, limit):
        action = getattr(discord.AuditLogAction, AUDIT_ACTIONS[key], None)
        if action is None:
            return await ctx.send(embed=warn_embed("that audit action is unavailable in this discord.py version", ctx.author))
        rows = []
        async for entry in ctx.guild.audit_logs(limit=max(1, min(limit, 25)), action=action):
            target = name(entry.target) if entry.target else "unknown"
            actor = entry.user.mention if entry.user else "unknown"
            rows.append(f"**{target}** • {actor} • <t:{int(entry.created_at.timestamp())}:R> • {cut(entry.reason or 'no reason', 70)}")
        await self.lines(ctx, f"audit: {key}", rows, "no matching audit entries found")

    async def permission_report(self, ctx, key, member, channel):
        member, channel = member or ctx.author, channel or ctx.channel
        flag = PERMISSIONS[key]
        allowed = getattr(channel.permissions_for(member), flag, False)
        embed = success_embed if allowed else error_embed
        await ctx.send(embed=embed(f"{member.mention} is `{'allowed' if allowed else 'denied'}` `{flag.replace('_', ' ')}` in {channel.mention}", ctx.author))

    @commands.command(name="checkpermission", aliases=["checkperm"])
    async def check_permission(self, ctx, member: discord.Member, permission: str, channel: commands.GuildChannelConverter = None):
        clean = permission.lower().replace("_", "").replace(" ", "")
        key = next((key for key, flag in PERMISSIONS.items() if clean in {key.lower(), flag.replace("_", "").lower()}), None)
        if not key:
            return await ctx.send(embed=error_embed("unknown permission; use a discord permission name such as `manage_messages`", ctx.author))
        await self.permission_report(ctx, key, member, channel)

    def install_dynamic_commands(self):
        if self.dynamic_installed:
            return
        self.dynamic_installed = True

        def report_callback(kind, key):
            async def callback(self, ctx):
                await getattr(self, f"{kind}_report")(ctx, key)
            return callback

        member_names = {
            "all":"allmembers", "web":"webmembers", "dangerous":"dangerousmembers", "pending":"pendingmembers",
            "voice":"voiceusers", "muted":"mutedvoice", "deafened":"deafenedvoice", "boosters":None, "admins":"adminmembers",
        }
        for key, description in MEMBER_REPORTS.items():
            command_name = member_names.get(key, key)
            if command_name:
                self.add_flat(command_name, report_callback("member", key), f"list {description}")

        channel_names = {
            "all":"allchannels", "text":"textchannels", "voice":None, "categories":"categories", "forums":"forums",
            "stages":"stages", "news":"newschannels", "nsfw":"nsfwchannels", "sfw":"sfwchannels",
            "locked":"lockedchannels", "unlocked":"unlockedchannels", "hidden":"hiddenchannels", "visible":"visiblechannels",
            "synced":"syncedchannels", "unsynced":"unsyncedchannels", "noslowmode":"noslowmodechannels",
            "orphaned":"orphanedchannels", "withtopic":"topicchannels", "notopic":"notopicchannels",
            "withoverwrites":"overwritechannels", "nooverwrites":"nooverwritechannels", "oldest":"oldestchannels",
            "newest":"newestchannels", "threads":None, "system":"systemchannels",
        }
        for key, description in CHANNEL_REPORTS.items():
            command_name = channel_names.get(key, key)
            if command_name:
                self.add_flat(command_name, report_callback("channel", key), f"list {description}")

        role_names = {key: f"{key}roles" for key in ROLE_REPORTS}
        role_names.update({"all":"allroles", "default":"defaultrole", "booster":"boosterroleinfo"})
        for key, description in ROLE_REPORTS.items():
            self.add_flat(role_names[key], report_callback("role", key), f"list {description}")

        def server_callback(key):
            async def callback(self, ctx):
                await self.server_metric(ctx, key)
            return callback
        for key, command_name in {"features":"serverfeatures", "scheduled":"scheduledevents", "invites":"invitecount", "bans":"bancount", "webhooks":"webhookcount"}.items():
            self.add_flat(command_name, server_callback(key), f"show the server's {SERVER_METRICS[key]}")

        def audit_callback(key):
            async def callback(self, ctx, limit: int = 10):
                await self.audit_report(ctx, key, limit)
            return callback
        for key in AUDIT_ACTIONS:
            if hasattr(discord.AuditLogAction, AUDIT_ACTIONS[key]):
                self.add_flat(f"audit{key}", audit_callback(key), f"show recent {key} audit entries", user={"view_audit_log":True}, bot={"view_audit_log":True})

        def invite_callback(settings):
            async def callback(self, ctx, channel: discord.TextChannel = None):
                channel = channel or ctx.channel
                max_age, max_uses, temporary = settings
                invite = await channel.create_invite(max_age=max_age, max_uses=max_uses, temporary=temporary, unique=True, reason=f"created by {ctx.author} ({ctx.author.id})")
                await ctx.send(embed=fleed_embed(title="invite created", description=f"[join server]({invite.url})", author=ctx.author))
            return callback
        invite_names = {"create30m":"invite30m", "create1h":"invite1h", "create6h":"invite6h", "create12h":"invite12h", "create1d":"invite1d", "create7d":"invite7d", "createpermanent":"invitepermanent", "singleuse":"invitesingleuse", "fiveuses":"invitefiveuses", "tenuses":"invitetenuses", "twentyfiveuses":"invitetwentyfiveuses", "fiftyuses":"invitefiftyuses", "hundreduses":"invitehundreduses", "temporary1h":"invitetemporary1h", "temporary1d":"invitetemporary1d", "temporary7d":"invitetemporary7d"}
        for key, settings in INVITES.items():
            self.add_flat(invite_names[key], invite_callback(settings), f"create a configured invite", user={"create_instant_invite":True}, bot={"create_instant_invite":True})


async def setup(bot):
    cog = Administration(bot)
    await bot.add_cog(cog)
    cog.install_dynamic_commands()
