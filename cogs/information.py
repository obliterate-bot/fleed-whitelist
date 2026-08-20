import discord
from discord.ext import commands
import time
import datetime
import base64
import urllib.parse
import aiohttp
import config
from utils import fleed_embed, success_embed, error_embed, warn_embed, command_not_found_embed, command_help_embed, CommandGroupPaginatorView, send_group_help, find_role, send_paginated_embed, PaginatorView

class Information(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # info commands
    @commands.hybrid_command(name="help", aliases=["h"])
    async def help_cmd(self, ctx, *, command_or_category: str = None):
        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None

        def _get_cog_commands(cog):
            cmds = []
            for cmd in cog.get_commands():
                if getattr(cmd, "hidden", False):
                    continue
                cmds.append(cmd.name)
                if isinstance(cmd, commands.Group):
                    for sub in cmd.walk_commands():
                        if not getattr(sub, "hidden", False):
                            cmds.append(f"{cmd.name} {sub.name}")
            return cmds

        if command_or_category:
            cmd = self.bot.get_command(command_or_category.lower())
            if cmd:
                if isinstance(cmd, commands.Group) and len(cmd.commands) > 0:
                    cmd_list = [cmd] + list(cmd.walk_commands())
                    view = CommandGroupPaginatorView(
                        ctx.author.id,
                        cmd_list,
                        prefix=ctx.prefix or ",",
                        module_name=cmd.cog_name.lower() if cmd.cog_name else "general"
                    )
                    embed = view.get_embed(ctx.author)
                    return await ctx.send(embed=embed, view=view)
                embed = command_help_embed(ctx.author, cmd, prefix=ctx.prefix or ",")
                return await ctx.send(embed=embed)
            
            cog = self.bot.get_cog(command_or_category.title()) or self.bot.get_cog(command_or_category.lower())
            if not cog:
                for c in self.bot.cogs.values():
                    if c.qualified_name.lower() == command_or_category.lower():
                        cog = c
                        break
            if cog:
                cmds = _get_cog_commands(cog)
                desc = ", ".join(cmds[:60])
                if len(cmds) > 60:
                    desc += f"\n...and {len(cmds) - 60} more"
                embed = discord.Embed(
                    title=f"category: {cog.qualified_name.lower()}",
                    description=f"`{desc}`",
                    color=0x2B2D31
                )
                if bot_avatar:
                    embed.set_thumbnail(url=bot_avatar)
                embed.set_footer(text=f"{len(cmds):,} commands in category")
                return await ctx.send(embed=embed)
            
            # command or category does not exist
            embed, _ = command_not_found_embed(ctx.author, command_or_category)
            return await ctx.send(embed=embed)

        # Build dynamic category map from active cogs
        cogs_info = {}
        for cog_name, cog in sorted(self.bot.cogs.items(), key=lambda x: x[0].lower()):
            cmds = _get_cog_commands(cog)
            if cmds:
                cogs_info[cog_name.lower()] = {
                    "cog": cog,
                    "cmds": cmds,
                    "count": len(cmds),
                    "preview": ", ".join(cmds[:10]) + (f" (+{len(cmds)-10} more)" if len(cmds) > 10 else "")
                }

        total_cmds = sum(info["count"] for info in cogs_info.values())

        embed = discord.Embed(
            title="fleed command menu",
            description=(
                f"prefix: `,`\n"
                f"type `,help <command>` for command details\n"
                f"select a module below to inspect commands\n\n"
                f"[**Fleed Commands**](http://fleed.oops.wtf/commands.html)\n"
                f"join the discord server @ **discord.gg/fleed**"
            ),
            color=0x2B2D31
        )
        if bot_avatar:
            embed.set_thumbnail(url=bot_avatar)
        
        for category, info in list(cogs_info.items())[:6]:
            embed.add_field(name=f"{category} ({info['count']})", value=f"`{info['preview']}`", inline=False)

        class HelpDropdown(discord.ui.Select):
            def __init__(self, bot_ref, author_id):
                options = [
                    discord.SelectOption(label=cat, description=f"{info['count']} commands")
                    for cat, info in cogs_info.items()
                ][:25]
                super().__init__(placeholder="select a category...", min_values=1, max_values=1, options=options)
                self.bot_ref = bot_ref
                self.author_id = author_id

            async def callback(self, interaction: discord.Interaction):
                if interaction.user.id != self.author_id:
                    return await interaction.response.send_message("this menu is not for you", ephemeral=True)
                selected = self.values[0]
                info = cogs_info.get(selected)
                if info:
                    cmd_str = ", ".join(info["cmds"][:60])
                    if len(info["cmds"]) > 60:
                        cmd_str += f"\n...and {len(info['cmds']) - 60} more"
                    res_embed = discord.Embed(
                        title=f"category: {selected} ({info['count']} commands)",
                        description=(
                            f"`{cmd_str}`\n\n"
                            f"[**Fleed Commands**](http://fleed.oops.wtf/commands.html) • join the discord server @ **discord.gg/fleed**"
                        ),
                        color=0x2B2D31
                    )
                    if bot_avatar:
                        res_embed.set_thumbnail(url=bot_avatar)
                    res_embed.set_footer(text=f"{info['count']:,} commands • type ,help <command> for syntax")
                    await interaction.response.edit_message(embed=res_embed)

        class HelpView(discord.ui.View):
            def __init__(self, bot_ref, author_id):
                super().__init__(timeout=120)
                self.add_item(HelpDropdown(bot_ref, author_id))
                self.add_item(discord.ui.Button(label="Fleed Commands", url="http://fleed.oops.wtf/commands.html", style=discord.ButtonStyle.link))
                self.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/fleed", style=discord.ButtonStyle.link))

        view = HelpView(self.bot, ctx.author.id)
        embed.set_footer(text=f"total commands: {total_cmds:,} • type ,help <command> for syntax")
        await ctx.send(embed=embed, view=view)

    @commands.command(name="commandlist", aliases=["commandslist", "cmdcount", "cmdlist", "allcommands", "totalcommands", "botcommands"])
    async def commandlist(self, ctx):
        """View the total command count and category breakdown"""
        category_counts = {}
        total_commands = 0

        for cog_name, cog in sorted(self.bot.cogs.items()):
            cat_count = 0
            for cmd in cog.get_commands():
                if getattr(cmd, "hidden", False):
                    continue
                cat_count += 1
                if isinstance(cmd, commands.Group):
                    cat_count += len(list(cmd.walk_commands()))
            category_counts[cog_name.lower()] = cat_count
            total_commands += cat_count

        sorted_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
        lines = [f"**{cat}**: `{count:,}`" for cat, count in sorted_cats]

        mid = (len(lines) + 1) // 2
        col1 = "\n".join(lines[:mid])
        col2 = "\n".join(lines[mid:])

        embed = discord.Embed(
            title=f"fleed commands ({total_commands:,})",
            description=(
                f"fleed currently has **{total_commands:,}** commands across **{len(category_counts)}** modules.\n\n"
                f"browse the full interactive registry online at:\n"
                f"[**fleed.oops.wtf/commands**](http://fleed.oops.wtf/commands.html)\n"
            ),
            color=0x2B2D31
        )
        if self.bot.user and self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="categories", value=col1, inline=True)
        if col2:
            embed.add_field(name="more", value=col2, inline=True)

        embed.set_footer(text=f"type ,help <command> for syntax • {total_commands:,} commands")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="View Commands Online", url="http://fleed.oops.wtf/commands.html", style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/fleed", style=discord.ButtonStyle.link))

        await ctx.send(embed=embed, view=view)

    @commands.command(name="ping", aliases=["latency"])
    async def ping(self, ctx):
        lat = round(self.bot.latency * 1000)
        await ctx.send(embed=fleed_embed(description=f"latency: `{lat}ms`", author=ctx.author))

    @commands.hybrid_command(name="membercount", aliases=["mc"])
    async def membercount(self, ctx):
        g = ctx.guild
        total = g.member_count or len(g.members)
        humans = len([m for m in g.members if not m.bot])
        bots = len([m for m in g.members if m.bot])
        
        desc = (
            f"**Total:** {total:,}\n"
            f"**Humans:** {humans:,} ({round(humans / max(1, total) * 100)}%)\n"
            f"**Bots:** {bots:,} ({round(bots / max(1, total) * 100)}%)"
        )
        embed = discord.Embed(
            title=f"{g.name.lower()} member count",
            description=desc,
            color=0x2B2D31
        )
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        await ctx.send(embed=embed)

    @commands.command(name="inrole", aliases=["ir"])
    async def inrole(self, ctx, *, role: str):
        target_role = find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"role \"{role}\" not found.", ctx.author))

        entries = [f"`{idx:02}` {m.mention} (`{m.id}`)" for idx, m in enumerate(target_role.members, start=1)]
        color = target_role.color.value if target_role.color.value != 0 else 0x2B2D31
        await send_paginated_embed(
            ctx,
            title=f"in role: @{target_role.name.lower()}",
            entries=entries,
            per_page=10,
            color=color,
            empty_text="no members in this role",
            item_name="members"
        )

    @commands.hybrid_command(name="userinfo", aliases=["ui", "whois", "uinfo"])
    async def userinfo(self, ctx, *, member: discord.Member = None):
        target = member or ctx.author
        try:
            user = await self.bot.fetch_user(target.id)
        except Exception:
            user = target
        
        # Flags & Badges
        badges = []
        if target.bot:
            badges.append("Bot")
        if target.id == ctx.guild.owner_id:
            badges.append("Server Owner")
        flags = target.public_flags
        if flags.staff:
            badges.append("Discord Staff")
        if flags.partner:
            badges.append("Partnered Server Owner")
        if flags.hypesquad:
            badges.append("HypeSquad Events")
        if flags.bug_hunter:
            badges.append("Bug Hunter Level 1")
        if flags.bug_hunter_level_2:
            badges.append("Bug Hunter Level 2")
        if flags.hypesquad_bravery:
            badges.append("HypeSquad Bravery")
        if flags.hypesquad_brilliance:
            badges.append("HypeSquad Brilliance")
        if flags.hypesquad_balance:
            badges.append("HypeSquad Balance")
        if flags.early_supporter:
            badges.append("Early Supporter")
        if flags.verified_bot_developer or flags.early_verified_bot_developer:
            badges.append("Early Verified Bot Developer")
        if flags.active_developer:
            badges.append("Active Developer")
        if target.premium_since:
            badges.append("Server Booster")

        # Key Permissions
        key_perms = []
        if target.guild_permissions.administrator:
            key_perms.append("Administrator")
        else:
            if target.guild_permissions.manage_guild:
                key_perms.append("Manage Server")
            if target.guild_permissions.ban_members:
                key_perms.append("Ban Members")
            if target.guild_permissions.kick_members:
                key_perms.append("Kick Members")
            if target.guild_permissions.manage_roles:
                key_perms.append("Manage Roles")
            if target.guild_permissions.manage_channels:
                key_perms.append("Manage Channels")
            if target.guild_permissions.mention_everyone:
                key_perms.append("Mention Everyone")
            if target.guild_permissions.manage_messages:
                key_perms.append("Manage Messages")
            if target.guild_permissions.view_audit_log:
                key_perms.append("View Audit Log")

        created_ts = int(target.created_at.timestamp())
        joined_ts = int(target.joined_at.timestamp()) if target.joined_at else None
        
        # Calculate Join position
        sorted_members = sorted(ctx.guild.members, key=lambda m: m.joined_at or m.created_at)
        try:
            join_pos = sorted_members.index(target) + 1
        except ValueError:
            join_pos = "?"

        # Roles (excluding @everyone)
        roles = [r.mention for r in reversed(target.roles[1:])]
        roles_str = " ".join(roles[:8]) if roles else "None"
        if len(roles) > 8:
            roles_str += f" (+{len(roles) - 8} more)"

        color = target.color if target.color.value != 0 else 0x2B2D31

        embed = discord.Embed(color=color)
        embed.set_author(name=f"{target.name} ({target.id})", icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=target.display_avatar.url)

        # Dates field
        dates_desc = (
            f"**Created:** <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
            f"**Joined:** <t:{joined_ts}:D> (<t:{joined_ts}:R>)" if joined_ts else f"**Created:** <t:{created_ts}:D> (<t:{created_ts}:R>)"
        )
        embed.add_field(name="Dates", value=dates_desc, inline=False)

        # Information field
        info_desc = (
            f"**Nickname:** {target.nick or 'None'}\n"
            f"**Join Position:** #{join_pos}\n"
            f"**Top Role:** {target.top_role.mention if target.top_role else 'None'}\n"
            f"**Badges:** {', '.join(badges) if badges else 'None'}\n"
            f"**Key Permissions:** {', '.join(key_perms) if key_perms else 'Standard'}"
        )
        embed.add_field(name="Information", value=info_desc, inline=False)

        # Roles field
        embed.add_field(name=f"Roles ({len(target.roles) - 1})", value=roles_str, inline=False)

        if getattr(user, "banner", None):
            embed.set_image(url=user.banner.url)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverinfo", aliases=["si", "sinfo", "guildinfo"])
    async def serverinfo(self, ctx):
        g = ctx.guild
        owner = g.owner or await self.bot.fetch_user(g.owner_id)
        created_ts = int(g.created_at.timestamp())
        
        humans = len([m for m in g.members if not m.bot])
        bots = len([m for m in g.members if m.bot])
        
        text_channels = len(g.text_channels)
        voice_channels = len(g.voice_channels)
        categories = len(g.categories)
        
        embed = discord.Embed(color=0x2B2D31)
        embed.set_author(name=f"{g.name} ({g.id})", icon_url=g.icon.url if g.icon else None)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        if g.banner:
            embed.set_image(url=g.banner.url)

        # Overview
        overview_desc = (
            f"**Owner:** {owner.mention if owner else f'<@{g.owner_id}>'}\n"
            f"**Created:** <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
            f"**Verification:** {str(g.verification_level).capitalize()}\n"
            f"**Vanity:** {f'discord.gg/{g.vanity_url_code}' if g.vanity_url_code else 'None'}"
        )
        embed.add_field(name="Overview", value=overview_desc, inline=True)

        # Statistics
        stats_desc = (
            f"**Members:** {g.member_count:,} ({humans:,} humans, {bots:,} bots)\n"
            f"**Channels:** {len(g.channels)} ({text_channels} text, {voice_channels} voice, {categories} cats)\n"
            f"**Roles:** {len(g.roles)}\n"
            f"**Emojis:** {len(g.emojis)} / {g.emoji_limit}\n"
            f"**Boosts:** Level {g.premium_tier} ({g.premium_subscription_count} boosts)"
        )
        embed.add_field(name="Statistics", value=stats_desc, inline=True)

        embed.set_footer(text=f"ID: {g.id} • Shard: 0")
        await ctx.send(embed=embed)

    @commands.command(name="botinfo", aliases=["bi", "about"])
    async def botinfo(self, ctx):
        import platform, psutil
        
        proc = psutil.Process()
        mem = proc.memory_info().rss / 1024 / 1024
        
        total_members = sum(g.member_count for g in self.bot.guilds)
        total_channels = sum(len(g.channels) for g in self.bot.guilds)
        total_commands = len(list(self.bot.walk_commands()))
        
        embed = discord.Embed(color=0x2B2D31)
        embed.set_author(name=f"{self.bot.user.name} ({self.bot.user.id})", icon_url=self.bot.user.display_avatar.url)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        stats_desc = (
            f"**Servers:** {len(self.bot.guilds):,}\n"
            f"**Users:** {total_members:,}\n"
            f"**Channels:** {total_channels:,}\n"
            f"**Commands:** {total_commands:,}\n"
            f"**Latency:** {round(self.bot.latency * 1000)}ms"
        )
        embed.add_field(name="Statistics", value=stats_desc, inline=True)

        system_desc = (
            f"**Developer:** undix (daniel / obliterate)\n"
            f"**Python:** {platform.python_version()}\n"
            f"**discord.py:** {discord.__version__}\n"
            f"**Memory:** {mem:.2f} MB\n"
            f"**Host OS:** {platform.system()} {platform.release()}"
        )
        embed.add_field(name="System", value=system_desc, inline=True)

        embed.set_footer(text="fleed • Created with discord.py")
        await ctx.send(embed=embed)



    @commands.command(name="screenshot", aliases=["ss"])
    async def screenshot(self, ctx, url: str):
        target = url.strip()
        if not target.startswith(("http://", "https://")):
            target = "https://" + target
        parsed = urllib.parse.urlparse(target)
        if not parsed.hostname:
            return await ctx.send(embed=error_embed("provide a valid website URL", ctx.author))
        screenshot_url = "https://image.thum.io/get/fullpage/" + urllib.parse.quote(target, safe=":/?&=%#")
        embed = fleed_embed(title=f"screenshot: {parsed.hostname.lower()}", description=f"[open website]({target})", author=ctx.author)
        embed.set_image(url=screenshot_url)
        await ctx.send(embed=embed)

    @commands.command(name="ocr")
    async def ocr(self, ctx, image_url: str = None):
        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        if not attachment and ctx.message.reference and ctx.message.reference.resolved:
            resolved = ctx.message.reference.resolved
            attachment = resolved.attachments[0] if getattr(resolved, "attachments", None) else None
        source_url = image_url or (attachment.url if attachment else None)
        if not source_url:
            return await ctx.send(embed=error_embed("attach an image, reply to one, or provide an image URL", ctx.author))
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(source_url) as response:
                    if response.status != 200:
                        raise RuntimeError(f"image download returned HTTP {response.status}")
                    if response.content_length and response.content_length > 8 * 1024 * 1024:
                        return await ctx.send(embed=error_embed("image must be smaller than 8 MB", ctx.author))
                    image_bytes = await response.read()
                    if len(image_bytes) > 8 * 1024 * 1024:
                        return await ctx.send(embed=error_embed("image must be smaller than 8 MB", ctx.author))
                    mime = response.headers.get("Content-Type", "image/png").split(";", 1)[0]

                groq_key = (os.getenv("GROQ_API_KEY", "") or getattr(config, "GROQ_API_KEY", "")).strip()
                if not groq_key:
                    return await ctx.send(embed=error_embed("OCR requires `GROQ_API_KEY` configured in .env", ctx.author))

                payload = {
                    "model": "llama-3.2-11b-vision-preview",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Transcribe all visible text exactly. Return only the transcription."},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"}},
                        ],
                    }],
                    "max_tokens": 1200,
                }
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {groq_key}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                }
                endpoint = "https://api.groq.com/openai/v1/chat/completions"
                async with session.post(endpoint, json=payload, headers=headers) as response:
                    data = await response.json(content_type=None)
                    if response.status >= 400:
                        raise RuntimeError(str(data.get("error") or data)[:300])
            text = str(data.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
            if not text:
                return await ctx.send(embed=warn_embed("no readable text was detected", ctx.author))
            await ctx.send(embed=fleed_embed(title="extracted image text", description=text[:4000], author=ctx.author))
        except Exception as exc:
            await ctx.send(embed=error_embed(f"OCR failed: {str(exc)[:300]}", ctx.author))

    @commands.command(name="reverse", aliases=["reversesearch"])
    async def reverse_search(self, ctx, image_url: str = None):
        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        if not attachment and ctx.message.reference and ctx.message.reference.resolved:
            resolved = ctx.message.reference.resolved
            attachment = resolved.attachments[0] if getattr(resolved, "attachments", None) else None
        source_url = image_url or (attachment.url if attachment else None)
        if not source_url:
            return await ctx.send(embed=error_embed("attach an image, reply to one, or provide an image URL", ctx.author))
        lens_url = "https://lens.google.com/uploadbyurl?url=" + urllib.parse.quote(source_url, safe="")
        tineye_url = "https://tineye.com/search?url=" + urllib.parse.quote(source_url, safe="")
        embed = fleed_embed(
            title="reverse image search",
            description=f"[search with Google Lens]({lens_url})\n[search with TinEye]({tineye_url})",
            author=ctx.author,
        )
        embed.set_thumbnail(url=source_url)
        await ctx.send(embed=embed)

    # timezone & afk & namehistory
    @commands.group(name="timezone", invoke_without_command=True)
    async def timezone(self, ctx):
        await send_group_help(ctx, ctx.command, "information")

    @timezone.command(name="set")
    async def timezone_set(self, ctx, *, location: str):
        await self.bot.db.execute("INSERT INTO user_settings (user_id, timezone) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET timezone = ?", (ctx.author.id, location.lower(), location.lower()))
        await ctx.send(embed=success_embed(f"set timezone to `{location.lower()}`", ctx.author))

    @commands.group(name="afk", invoke_without_command=True)
    async def afk_group(self, ctx, *, reason: str = "afk"):
        now = int(time.time())
        await self.bot.db.execute("INSERT INTO user_settings (user_id, afk_message, afk_time) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET afk_message = ?, afk_time = ?", (ctx.author.id, reason, now, reason, now))
        await ctx.send(embed=fleed_embed(description=f"set afk: {reason.lower()}", author=ctx.author))

    @afk_group.command(name="reset", aliases=["clear"])
    async def afk_reset(self, ctx):
        await self.bot.db.execute("UPDATE user_settings SET afk_message = NULL, afk_time = 0 WHERE user_id = ?", (ctx.author.id,))
        await ctx.send(embed=success_embed("cleared custom afk status", ctx.author))

    @afk_group.command(name="embed")
    async def afk_embed(self, ctx, *, script: str):
        await self.bot.db.execute("INSERT INTO user_settings (user_id, afk_message) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET afk_message = ?", (ctx.author.id, script, script))
        await ctx.send(embed=success_embed("set custom afk template", ctx.author))

    @commands.group(name="namehistory", invoke_without_command=True)
    async def namehistory(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        rows = await self.bot.db.fetch("SELECT old_name, timestamp FROM name_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (target.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description=f"no name history for {target.mention}", author=target))
        names = [f"`{r['old_name']}`" for r in rows]
        await ctx.send(embed=fleed_embed(title=f"{target.display_name.lower()}'s past names", description=", ".join(names), author=target))

    @namehistory.command(name="clear", aliases=["reset"])
    async def namehistory_clear(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        await self.bot.db.execute("DELETE FROM name_history WHERE user_id = ?", (target.id,))
        await ctx.send(embed=success_embed(f"cleared name history for {target.mention}", ctx.author))

    @commands.command(name="clearnames", aliases=["clearnamehistory", "clnh", "clearnh"])
    async def clearnames(self, ctx, member: discord.Member = None):
        await self.namehistory_clear(ctx, member)

    @commands.hybrid_command(name="avatar", aliases=["av", "pfp"])
    async def avatar_cmd(self, ctx, *, user: discord.User = None):
        target = user or ctx.author
        url = target.display_avatar.url
        embed = fleed_embed(title=f"{target.display_name.lower()}'s avatar", author=target)
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="banner")
    async def banner_cmd(self, ctx, *, user: discord.User = None):
        target = user or ctx.author
        try:
            fetched = await self.bot.fetch_user(target.id)
            if fetched.banner:
                embed = fleed_embed(title=f"{target.display_name.lower()}'s banner", author=target)
                embed.set_image(url=fetched.banner.url)
                return await ctx.send(embed=embed)
        except Exception:
            pass
        await ctx.send(embed=warn_embed(f"{target.mention} has no profile banner", ctx.author))

    @commands.hybrid_command(name="roleinfo", aliases=["ri"])
    async def roleinfo_cmd(self, ctx, *, role: str):
        target_role = find_role(ctx.guild, role)
        if not target_role:
            return await ctx.send(embed=error_embed(f"role \"{role}\" not found.", ctx.author))

        desc = (
            f"**ID:** `{target_role.id}`\n"
            f"**Color:** `{str(target_role.color).lower()}`\n"
            f"**Position:** `{target_role.position}`\n"
            f"**Members:** `{len(target_role.members)}`\n"
            f"**Mentionable:** `{target_role.mentionable}`\n"
            f"**Hoisted:** `{target_role.hoist}`"
        )
        embed = fleed_embed(title=f"role: @{target_role.name.lower()}", description=desc, author=ctx.author)
        embed.color = target_role.color if target_role.color.value != 0 else 0x2B2D31
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="permissions", aliases=["perms"])
    async def permissions_cmd(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        allowed = [perm.replace("_", " ").lower() for perm, val in target.guild_permissions if val]
        desc = ", ".join(allowed) if allowed else "none"
        await ctx.send(embed=fleed_embed(title=f"permissions for {target.display_name.lower()}", description=desc, author=target))

    @commands.hybrid_command(name="firstmessage", aliases=["firstmsg"])
    async def firstmessage_cmd(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        async for msg in ch.history(limit=1, oldest_first=True):
            desc = f"**author:** {msg.author.mention}\n**sent:** <t:{int(msg.created_at.timestamp())}:R>\n**content:** {msg.content or '(attachment/embed)'}\n\n[**Jump to Message**]({msg.jump_url})"
            return await ctx.send(embed=fleed_embed(title=f"first message in #{ch.name.lower()}", description=desc, author=ctx.author))
        await ctx.send(embed=warn_embed("no messages found in channel", ctx.author))

    @commands.hybrid_command(name="channelinfo", aliases=["ci", "cinfo"])
    async def channelinfo_cmd(self, ctx, channel: discord.abc.GuildChannel = None):
        target = channel or ctx.channel
        created_ts = int(target.created_at.timestamp())
        ch_type = str(target.type).replace("_", " ").lower()

        desc = (
            f"**ID:** `{target.id}`\n"
            f"**Type:** `{ch_type}`\n"
            f"**Category:** `{target.category.name.lower() if target.category else 'none'}`\n"
            f"**Position:** `{target.position}`\n"
            f"**Created:** <t:{created_ts}:D> (<t:{created_ts}:R>)"
        )
        if isinstance(target, discord.TextChannel):
            desc += f"\n**Slowmode:** `{target.slowmode_delay}s`\n**NSFW:** `{target.is_nsfw()}`"
            if target.topic:
                desc += f"\n**Topic:** {target.topic.lower()}"
        elif isinstance(target, discord.VoiceChannel):
            desc += f"\n**Bitrate:** `{target.bitrate // 1000} kbps`\n**User Limit:** `{target.user_limit or 'unlimited'}`"

        embed = fleed_embed(title=f"channel: #{target.name.lower()}", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="emojiinfo", aliases=["ei"])
    async def emojiinfo_cmd(self, ctx, emoji: discord.Emoji):
        created_ts = int(emoji.created_at.timestamp())
        desc = (
            f"**Name:** `{emoji.name.lower()}`\n"
            f"**ID:** `{emoji.id}`\n"
            f"**Animated:** `{emoji.animated}`\n"
            f"**Managed:** `{emoji.managed}`\n"
            f"**Created:** <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
            f"[**Direct URL**]({emoji.url})"
        )
        embed = fleed_embed(title=f"emoji: {emoji.name.lower()}", description=desc, author=ctx.author)
        embed.set_thumbnail(url=emoji.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="boosters", aliases=["boostlist"])
    async def boosters_cmd(self, ctx):
        boosters = ctx.guild.premium_subscribers
        if not boosters:
            return await ctx.send(embed=warn_embed("this server has no active boosters", ctx.author))
        entries = [
            f"`{idx:02}` {m.mention} (boosting since <t:{int(m.premium_since.timestamp())}:R>)"
            for idx, m in enumerate(boosters, start=1)
        ]
        await send_paginated_embed(ctx, f"server boosters ({len(boosters)})", entries, per_page=10, item_name="boosters")

    @commands.hybrid_command(name="serverbanner", aliases=["sbanner"])
    async def serverbanner_cmd(self, ctx):
        if not ctx.guild.banner:
            return await ctx.send(embed=warn_embed("this server has no banner set", ctx.author))
        embed = fleed_embed(title=f"{ctx.guild.name.lower()}'s banner", author=ctx.author)
        embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="servericon", aliases=["sicon"])
    async def servericon_cmd(self, ctx):
        if not ctx.guild.icon:
            return await ctx.send(embed=warn_embed("this server has no icon set", ctx.author))
        embed = fleed_embed(title=f"{ctx.guild.name.lower()}'s icon", author=ctx.author)
        embed.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serversplash", aliases=["ssplash"])
    async def serversplash_cmd(self, ctx):
        if not ctx.guild.splash:
            return await ctx.send(embed=warn_embed("this server has no invite splash image", ctx.author))
        embed = fleed_embed(title=f"{ctx.guild.name.lower()}'s splash", author=ctx.author)
        embed.set_image(url=ctx.guild.splash.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="serverroles", aliases=["roleslist"])
    async def serverroles_cmd(self, ctx):
        roles = [r for r in reversed(ctx.guild.roles[1:])]
        if not roles:
            return await ctx.send(embed=warn_embed("no custom roles in server", ctx.author))
        entries = [f"`{idx:02}` {r.mention} (`{r.id}`)" for idx, r in enumerate(roles, start=1)]
        await send_paginated_embed(ctx, f"server roles ({len(roles)})", entries, per_page=15, item_name="roles")

    @commands.hybrid_command(name="serveremojis", aliases=["emojislist"])
    async def serveremojis_cmd(self, ctx):
        emojis = list(ctx.guild.emojis)
        if not emojis:
            return await ctx.send(embed=warn_embed("no custom emojis in server", ctx.author))
        entries = [f"`{idx:02}` {str(e)} `:{e.name}:`" for idx, e in enumerate(emojis, start=1)]
        await send_paginated_embed(ctx, f"server emojis ({len(emojis)})", entries, per_page=15, item_name="emojis")

    @commands.hybrid_command(name="uptime", aliases=["up"])
    async def uptime_cmd(self, ctx):
        import time
        start_time = getattr(self.bot, "_start_time", time.time())
        diff = int(time.time() - start_time)
        hours, remainder = divmod(diff, 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        await ctx.send(embed=fleed_embed(title="bot uptime", description=f"online for `{' '.join(parts)}`", author=ctx.author))

    @commands.hybrid_command(name="invite", aliases=["botinvite"])
    async def invite_cmd(self, ctx):
        inv_url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))
        desc = (
            f"[**Invite Fleed to your server**]({inv_url})\n"
            f"[**Support Server**](https://discord.gg/fleed)\n"
            f"[**Website & Commands**](http://fleed.oops.wtf/commands.html)"
        )
        embed = fleed_embed(title="fleed invite links", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Information(bot))
