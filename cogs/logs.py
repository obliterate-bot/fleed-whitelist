import discord
from discord.ext import commands
import datetime
from utils import fleed_embed, success_embed, error_embed, send_group_help, warn_embed

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_log_channel(self, guild_id: int, event_type: str):
        rows = await self.bot.db.fetch("SELECT channel_id, color FROM logs_config WHERE guild_id = ? AND (event_type = ? OR event_type = 'all')", (guild_id, event_type.lower()))
        channels = []
        for r in rows:
            ch = self.bot.get_channel(r["channel_id"])
            if ch:
                channels.append((ch, r["color"]))
        return channels

    async def send_log(self, guild_id: int, event_type: str, embed: discord.Embed):
        targets = await self.get_log_channel(guild_id, event_type)
        for ch, col in targets:
            try:
                if col:
                    embed.color = col
                await ch.send(embed=embed)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        desc = f"author: {message.author.mention} (`{message.author.id}`)\nchannel: {message.channel.mention}\ncontent: {message.content.lower() if message.content else '[no text content]'}"
        embed = fleed_embed(title="message deleted", description=desc, author=message.author)
        if message.attachments:
            embed.set_footer(text=f"attachments: {len(message.attachments)}")
        await self.send_log(message.guild.id, "messages", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        desc = f"author: {before.author.mention} (`{before.author.id}`)\nchannel: {before.channel.mention}\nbefore: {before.content.lower() if before.content else '[empty]'}\nafter: {after.content.lower() if after.content else '[empty]'}"
        embed = fleed_embed(title="message edited", description=desc, author=before.author)
        await self.send_log(before.guild.id, "messages", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        desc = f"user: {member.mention} (`{member.id}`)\ncreated: <t:{int(member.created_at.timestamp())}:R>\nmembers: {member.guild.member_count:,}"
        embed = fleed_embed(title="member joined", description=desc, author=member)
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        await self.send_log(member.guild.id, "members", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        desc = f"user: {member.mention} (`{member.id}`)\njoined: <t:{int(member.joined_at.timestamp()) if member.joined_at else 0}:R>\nmembers: {member.guild.member_count:,}"
        embed = fleed_embed(title="member left", description=desc, author=member)
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        await self.send_log(member.guild.id, "members", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            added = [r.mention for r in after.roles if r not in before.roles]
            removed = [r.mention for r in before.roles if r not in after.roles]
            desc = f"user: {after.mention} (`{after.id}`)\n"
            if added:
                desc += f"added roles: {', '.join(added)}\n"
            if removed:
                desc += f"removed roles: {', '.join(removed)}\n"
            embed = fleed_embed(title="roles updated", description=desc, author=after)
            await self.send_log(after.guild.id, "roles", embed)

        if before.nick != after.nick:
            desc = f"user: {after.mention} (`{after.id}`)\nbefore: `{before.nick.lower() if before.nick else 'none'}`\nafter: `{after.nick.lower() if after.nick else 'none'}`"
            embed = fleed_embed(title="nickname changed", description=desc, author=after)
            await self.send_log(after.guild.id, "members", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        desc = f"role: {role.mention} (`{role.id}`)\ncolor: `{str(role.color).lower()}`"
        embed = fleed_embed(title="role created", description=desc)
        await self.send_log(role.guild.id, "roles", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        desc = f"role: `{role.name.lower()}` (`{role.id}`)"
        embed = fleed_embed(title="role deleted", description=desc)
        await self.send_log(role.guild.id, "roles", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        desc = f"channel: {channel.mention} (`{channel.id}`)\ntype: `{str(channel.type).lower()}`"
        embed = fleed_embed(title="channel created", description=desc)
        await self.send_log(channel.guild.id, "channels", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        desc = f"channel: `#{channel.name.lower()}` (`{channel.id}`)\ntype: `{str(channel.type).lower()}`"
        embed = fleed_embed(title="channel deleted", description=desc)
        await self.send_log(channel.guild.id, "channels", embed)

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"name: `{before.name.lower()}` -> `{after.name.lower()}`")
        if before.icon != after.icon:
            changes.append(f"icon: [new icon]({after.icon.url if after.icon else 'none'})")
        if before.banner != after.banner:
            changes.append(f"banner: [new banner]({after.banner.url if after.banner else 'none'})")
        if getattr(before, "vanity_url_code", None) != getattr(after, "vanity_url_code", None):
            changes.append(f"vanity: `discord.gg/{before.vanity_url_code}` -> `discord.gg/{after.vanity_url_code}`")
        if changes:
            embed = fleed_embed(title="server updated", description="\n".join(changes))
            await self.send_log(after.id, "server", embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"name: `{before.name.lower()}` -> `{after.name.lower()}`")
        if before.color != after.color:
            changes.append(f"color: `{str(before.color).lower()}` -> `{str(after.color).lower()}`")
        if before.permissions != after.permissions:
            added_perms = [p[0].replace("_", " ") for p in after.permissions if p not in before.permissions and p[1]]
            removed_perms = [p[0].replace("_", " ") for p in before.permissions if p not in after.permissions and not p[1]]
            if added_perms:
                changes.append(f"granted: {', '.join(added_perms[:5])}")
            if removed_perms:
                changes.append(f"denied: {', '.join(removed_perms[:5])}")
        if changes:
            embed = fleed_embed(title=f"role updated: @{after.name.lower()}", description="\n".join(changes))
            await self.send_log(after.guild.id, "roles", embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"name: `#{before.name.lower()}` -> `#{after.name.lower()}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(f"topic: `{str(after.topic)[:100].lower() if after.topic else 'none'}`")
        if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
            changes.append(f"slowmode: `{before.slowmode_delay}s` -> `{after.slowmode_delay}s`")
        if getattr(before, "nsfw", False) != getattr(after, "nsfw", False):
            changes.append(f"nsfw: `{'enabled' if after.nsfw else 'disabled'}`")
        if changes:
            embed = fleed_embed(title=f"channel updated: #{after.name.lower()}", description="\n".join(changes))
            await self.send_log(after.guild.id, "channels", embed)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        added = [e for e in after if e not in before]
        removed = [e for e in before if e not in after]
        changes = []
        if added:
            changes.append(f"added: {' '.join(str(e) for e in added[:10])}")
        if removed:
            changes.append(f"deleted: {', '.join(f'`:{e.name}:`' for e in removed[:10])}")
        if changes:
            embed = fleed_embed(title="emojis updated", description="\n".join(changes))
            await self.send_log(guild.id, "server", embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if not invite.guild:
            return
        inviter_str = invite.inviter.mention if invite.inviter else "unknown"
        desc = f"code: `discord.gg/{invite.code}`\ncreated by: {inviter_str}\nchannel: {invite.channel.mention if invite.channel else 'unknown'}\nexpires: {'never' if invite.max_age == 0 else f'{invite.max_age}s'}"
        embed = fleed_embed(title="invite created", description=desc)
        await self.send_log(invite.guild.id, "server", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel != after.channel:
            if not before.channel and after.channel:
                desc = f"user: {member.mention} (`{member.id}`)\njoined: {after.channel.mention}"
                embed = fleed_embed(title="voice connected", description=desc, author=member)
                await self.send_log(member.guild.id, "voice", embed)
            elif before.channel and not after.channel:
                desc = f"user: {member.mention} (`{member.id}`)\nleft: {before.channel.mention}"
                embed = fleed_embed(title="voice disconnected", description=desc, author=member)
                await self.send_log(member.guild.id, "voice", embed)
            elif before.channel and after.channel:
                desc = f"user: {member.mention} (`{member.id}`)\nmoved: {before.channel.mention} -> {after.channel.mention}"
                embed = fleed_embed(title="voice moved", description=desc, author=member)
                await self.send_log(member.guild.id, "voice", embed)
        else:
            if before.self_mute != after.self_mute:
                state = "muted" if after.self_mute else "unmuted"
                embed = fleed_embed(title=f"voice {state}", description=f"user: {member.mention} (`{member.id}`)\nchannel: {after.channel.mention if after.channel else 'none'}", author=member)
                await self.send_log(member.guild.id, "voice", embed)
            if before.self_deaf != after.self_deaf:
                state = "deafened" if after.self_deaf else "undeafened"
                embed = fleed_embed(title=f"voice {state}", description=f"user: {member.mention} (`{member.id}`)\nchannel: {after.channel.mention if after.channel else 'none'}", author=member)
                await self.send_log(member.guild.id, "voice", embed)

    @commands.hybrid_group(name="logs", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def logs(self, ctx):
        await send_group_help(ctx, ctx.command)

    @logs.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def logs_add(self, ctx, channel: discord.TextChannel = None, event: str = "all"):
        valid_events = ["all", "messages", "members", "roles", "channels", "voice", "server", "moderation"]
        ev = event.lower()
        if ev not in valid_events:
            return await ctx.send(embed=warn_embed(f"invalid event type. choose from: {', '.join(valid_events)}", ctx.author))
        ch = channel or ctx.channel
        await self.bot.db.execute("INSERT OR REPLACE INTO logs_config (guild_id, channel_id, event_type) VALUES (?, ?, ?)", (ctx.guild.id, ch.id, ev))
        await ctx.send(embed=success_embed(f"logging `{ev}` in {ch.mention}", ctx.author))

    @logs.command(name="remove", aliases=["clear"])
    @commands.has_permissions(manage_guild=True)
    async def logs_remove(self, ctx, channel: discord.TextChannel = None, event: str = None):
        if channel and event:
            await self.bot.db.execute("DELETE FROM logs_config WHERE guild_id = ? AND channel_id = ? AND event_type = ?", (ctx.guild.id, channel.id, event.lower()))
            return await ctx.send(embed=success_embed(f"removed `{event.lower()}` logs from {channel.mention}", ctx.author))
        elif channel:
            await self.bot.db.execute("DELETE FROM logs_config WHERE guild_id = ? AND channel_id = ?", (ctx.guild.id, channel.id))
            return await ctx.send(embed=success_embed(f"removed all logs from {channel.mention}", ctx.author))
        await self.bot.db.execute("DELETE FROM logs_config WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("cleared all server logging channels", ctx.author))

    @logs.command(name="view", aliases=["list"])
    @commands.has_permissions(manage_guild=True)
    async def logs_view(self, ctx):
        rows = await self.bot.db.fetch("SELECT channel_id, event_type FROM logs_config WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no logging channels configured", author=ctx.author))
        lines = [f"<#{r['channel_id']}>: `{r['event_type']}`" for r in rows]
        await ctx.send(embed=fleed_embed(title="configured log channels", description="\n".join(lines), author=ctx.author))

    @logs.command(name="messages", aliases=["msg"])
    @commands.has_permissions(manage_guild=True)
    async def logs_messages_cmd(self, ctx, channel: discord.TextChannel = None):
        await self.logs_add(ctx, channel=channel, event="messages")

    @logs.command(name="members", aliases=["mbr"])
    @commands.has_permissions(manage_guild=True)
    async def logs_members_cmd(self, ctx, channel: discord.TextChannel = None):
        await self.logs_add(ctx, channel=channel, event="members")

    @logs.command(name="roles", aliases=["role"])
    @commands.has_permissions(manage_guild=True)
    async def logs_roles_cmd(self, ctx, channel: discord.TextChannel = None):
        await self.logs_add(ctx, channel=channel, event="roles")

    @logs.command(name="channels", aliases=["ch"])
    @commands.has_permissions(manage_guild=True)
    async def logs_channels_cmd(self, ctx, channel: discord.TextChannel = None):
        await self.logs_add(ctx, channel=channel, event="channels")

    @logs.command(name="voice", aliases=["vc"])
    @commands.has_permissions(manage_guild=True)
    async def logs_voice_cmd(self, ctx, channel: discord.TextChannel = None):
        await self.logs_add(ctx, channel=channel, event="voice")

    @logs.command(name="server", aliases=["guild"])
    @commands.has_permissions(manage_guild=True)
    async def logs_server_cmd(self, ctx, channel: discord.TextChannel = None):
        await self.logs_add(ctx, channel=channel, event="server")

    @logs.command(name="moderation", aliases=["mod"])
    @commands.has_permissions(manage_guild=True)
    async def logs_moderation_cmd(self, ctx, channel: discord.TextChannel = None):
        await self.logs_add(ctx, channel=channel, event="moderation")

async def setup(bot):
    await bot.add_cog(Logs(bot))

