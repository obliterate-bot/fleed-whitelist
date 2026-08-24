import discord
from discord.ext import commands
import io
import datetime
import html
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help

# ==================== HTML TRANSCRIPT GENERATOR ====================

def generate_html_transcript(guild: discord.Guild, channel: discord.TextChannel, messages: list, ticket_info: dict = None) -> io.BytesIO:
    opener_name = ticket_info.get("opener_name", "Unknown") if ticket_info else "Unknown"
    category = ticket_info.get("category", "General") if ticket_info else "General"
    created_at_str = datetime.datetime.now(datetime.timezone.utc).strftime("%B %d, %Y - %H:%M UTC")

    messages_html = []
    for m in messages:
        author_name = html.escape(str(m.author))
        avatar_url = m.author.display_avatar.url if m.author.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        timestamp = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
        content_html = html.escape(m.content).replace("\n", "<br>") if m.content else ""
        
        # Attachments
        att_html = ""
        for att in m.attachments:
            if any(att.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                att_html += f'<div class="attachment"><a href="{att.url}" target="_blank"><img src="{att.url}" style="max-width: 400px; max-height: 300px; border-radius: 8px; margin-top: 6px; display: block;" /></a></div>'
            else:
                att_html += f'<div class="attachment"><a href="{att.url}" target="_blank" style="color: #5865F2; text-decoration: none;">[file] {html.escape(att.filename)} ({att.size // 1024} KB)</a></div>'

        # Embeds
        embed_html = ""
        for em in m.embeds:
            em_title = html.escape(em.title) if em.title else ""
            em_desc = html.escape(em.description).replace("\n", "<br>") if em.description else ""
            color_hex = f"#{em.color.value:06x}" if em.color else "#5865F2"
            embed_html += f'''
            <div class="embed" style="border-left: 4px solid {color_hex}; background: #2B2D31; padding: 10px 14px; border-radius: 4px; margin-top: 6px; max-width: 500px;">
                {"<div style='font-weight: bold; margin-bottom: 4px; color: #fff;'>" + em_title + "</div>" if em_title else ""}
                {"<div style='color: #dbdee1; font-size: 0.9em;'>" + em_desc + "</div>" if em_desc else ""}
            </div>
            '''

        is_bot_badge = '<span class="bot-tag">BOT</span>' if m.author.bot else ''

        msg_block = f'''
        <div class="message">
            <img class="avatar" src="{avatar_url}" alt="avatar" />
            <div class="msg-content">
                <div class="msg-header">
                    <span class="author">{author_name}</span>
                    {is_bot_badge}
                    <span class="timestamp">{timestamp}</span>
                </div>
                <div class="msg-text">{content_html}</div>
                {att_html}
                {embed_html}
            </div>
        </div>
        '''
        messages_html.append(msg_block)

    full_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Transcript #{channel.name}</title>
    <style>
        body {{
            background-color: #1E1F22;
            color: #DBDEE1;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 24px;
        }}
        .header {{
            background: #2B2D31;
            padding: 20px 24px;
            border-radius: 10px;
            margin-bottom: 24px;
            border: 1px solid #35363C;
        }}
        .header h1 {{
            color: #FFFFFF;
            margin: 0 0 8px 0;
            font-size: 1.4em;
        }}
        .header p {{
            margin: 4px 0;
            color: #949BA4;
            font-size: 0.9em;
        }}
        .messages {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .message {{
            display: flex;
            gap: 14px;
            padding: 6px 12px;
            border-radius: 6px;
        }}
        .message:hover {{
            background-color: #26282C;
        }}
        .avatar {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
        }}
        .msg-content {{
            flex: 1;
        }}
        .msg-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .author {{
            font-weight: 600;
            color: #F2F3F5;
            font-size: 0.95em;
        }}
        .bot-tag {{
            background: #5865F2;
            color: #FFF;
            font-size: 0.65em;
            font-weight: bold;
            padding: 2px 4px;
            border-radius: 3px;
        }}
        .timestamp {{
            font-size: 0.75em;
            color: #949BA4;
        }}
        .msg-text {{
            font-size: 0.95em;
            line-height: 1.4;
            color: #DBDEE1;
            word-break: break-word;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Transcript: #{channel.name}</h1>
        <p><strong>Server:</strong> {html.escape(guild.name)} ({guild.id})</p>
        <p><strong>Opener:</strong> {html.escape(opener_name)} | <strong>Category:</strong> {html.escape(category)}</p>
        <p><strong>Generated on:</strong> {created_at_str} | <strong>Total Messages:</strong> {len(messages)}</p>
    </div>
    <div class="messages">
        {"".join(messages_html)}
    </div>
</body>
</html>'''
    return io.BytesIO(full_html.encode("utf-8"))


# ==================== MODALS ====================

class TicketOpenModal(discord.ui.Modal):
    def __init__(self, bot, category_name: str):
        super().__init__(title=f"Open Ticket: {category_name[:25]}")
        self.bot = bot
        self.category_name = category_name

        self.reason_input = discord.ui.TextInput(
            label="Subject / Topic",
            placeholder="briefly state what you need assistance with...",
            min_length=3,
            max_length=100,
            required=True
        )
        self.add_item(self.reason_input)

        self.desc_input = discord.ui.TextInput(
            label="Description / Details",
            placeholder="provide any relevant details, links, or info here...",
            style=discord.TextStyle.paragraph,
            min_length=5,
            max_length=1000,
            required=False
        )
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Defer interaction immediately to prevent Discord 3.0s modal timeout error
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                pass

        await create_ticket_channel(
            bot=self.bot,
            interaction=interaction,
            category_name=self.category_name,
            subject=self.reason_input.value.strip(),
            description=self.desc_input.value.strip() or "no additional description provided."
        )


class TicketRenameModal(discord.ui.Modal, title="Rename Ticket"):
    name_input = discord.ui.TextInput(label="New Channel Name", placeholder="e.g. solved-billing", max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                pass
        new_name = self.name_input.value.lower().replace(" ", "-")
        await interaction.channel.edit(name=new_name, reason=f"ticket renamed by {interaction.user}")
        await interaction.followup.send(embed=success_embed(f"renamed ticket to `#{new_name}`", interaction.user), ephemeral=True)


class TicketAddUserModal(discord.ui.Modal, title="Add Member to Ticket"):
    user_input = discord.ui.TextInput(label="User ID or Username", placeholder="enter user ID or username...", min_length=2)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                pass
        guild = interaction.guild
        query = self.user_input.value.strip()
        target = None
        if query.isdigit():
            target = guild.get_member(int(query))
        if not target:
            target = discord.utils.find(lambda m: query.lower() in m.name.lower() or query.lower() in m.display_name.lower(), guild.members)
        if not target:
            return await interaction.followup.send(embed=error_embed("could not find that member in this server", interaction.user), ephemeral=True)

        await interaction.channel.set_permissions(target, view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True)
        await interaction.followup.send(embed=success_embed(f"added {target.mention} to this ticket", interaction.user), ephemeral=True)


class TicketTransferModal(discord.ui.Modal, title="Transfer Ticket"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    staff_input = discord.ui.TextInput(label="Staff Member ID or Username", placeholder="enter staff user ID or name...")

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                pass
        guild = interaction.guild
        query = self.staff_input.value.strip()
        target = None
        if query.isdigit():
            target = guild.get_member(int(query))
        if not target:
            target = discord.utils.find(lambda m: query.lower() in m.name.lower() or query.lower() in m.display_name.lower(), guild.members)
        if not target:
            return await interaction.followup.send(embed=error_embed("could not find that member", interaction.user), ephemeral=True)

        await self.bot.db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (target.id, interaction.channel.id))
        await interaction.channel.set_permissions(target, view_channel=True, send_messages=True, attach_files=True, embed_links=True)
        await interaction.followup.send(embed=success_embed(f"ticket transferred to {target.mention}", interaction.user), ephemeral=True)


# ==================== CORE TICKET CREATION LOGIC ====================

async def create_ticket_channel(bot, interaction: discord.Interaction, category_name: str, subject: str, description: str):
    # Ensure interaction is deferred immediately
    if not interaction.response.is_done():
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

    async def send_response(embed):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            pass

    guild = interaction.guild
    if not guild:
        return await send_response(error_embed("tickets can only be opened within a server.", interaction.user))

    user = interaction.user

    # Fetch configuration safely
    raw_cfg = await bot.db.fetchrow("SELECT * FROM ticket_config WHERE guild_id = ?", (guild.id,))
    cfg = dict(raw_cfg) if raw_cfg else {}
    
    # Check open ticket limit per user
    existing_rows = await bot.db.fetch("SELECT channel_id FROM tickets WHERE guild_id = ? AND opener_id = ? AND status = 'open'", (guild.id, user.id))
    if len(existing_rows) >= 3:
        return await send_response(warn_embed("you already have 3 open tickets. please close previous ones first.", user))

    # Increment counter
    counter = (cfg.get("ticket_counter") or 0) + 1
    await bot.db.execute(
        "INSERT INTO ticket_config (guild_id, ticket_counter) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET ticket_counter = ?",
        (guild.id, counter, counter)
    )

    # Get target category
    target_category = None
    if cfg.get("category_id"):
        target_category = guild.get_channel(cfg.get("category_id"))
    if not target_category:
        target_category = discord.utils.get(guild.categories, name="tickets")
        if not target_category:
            try:
                target_category = await guild.create_category(name="tickets", reason="ticket system auto setup")
            except Exception:
                pass

    # Permission Overwrites
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True, attach_files=True, embed_links=True)
    }

    # Support Roles overwrite if configured
    support_roles = []
    if cfg.get("support_role_ids"):
        for r_id in str(cfg.get("support_role_ids")).split(","):
            r_id = r_id.strip()
            if r_id.isdigit():
                role_obj = guild.get_role(int(r_id))
                if role_obj:
                    support_roles.append(role_obj)
                    overwrites[role_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True)

    channel_name = f"ticket-{counter:04d}"
    topic_str = f"Ticket #{counter:04d} | Opener: {user} ({user.id}) | Category: {category_name}"
    
    try:
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=target_category,
            overwrites=overwrites,
            topic=topic_str,
            reason=f"ticket opened by {user}"
        )
    except Exception as e:
        return await send_response(error_embed(f"failed to create ticket channel: {e}", user))

    # Save to database
    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    await bot.db.execute(
        """
        INSERT INTO tickets (guild_id, channel_id, opener_id, ticket_num, category, topic, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
        """,
        (guild.id, ticket_channel.id, user.id, counter, category_name, subject, now_ts)
    )

    # Welcome Card in new ticket
    embed = fleed_embed(
        title=f"ticket #{counter:04d} — {category_name.lower()}",
        description=(
            f"welcome {user.mention}\n"
            f"a support representative will be with you shortly.\n\n"
            f"**subject:** {subject}\n"
            f"**details:** {description}\n\n"
            f"use the control panel below to manage this ticket."
        ),
        author=user
    )
    embed.set_footer(text=f"ticket id: {counter:04d} | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

    ping_content = f"{user.mention}" + (" " + " ".join(r.mention for r in support_roles) if support_roles else "")
    await ticket_channel.send(content=ping_content, embed=embed, view=TicketControlView(bot))
    await send_response(success_embed(f"ticket opened in {ticket_channel.mention}", user))


# ==================== VIEWS ====================

class TicketCategorySelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="General Support", description="Assistance, questions, or general help", value="General Support"),
            discord.SelectOption(label="Billing & Donations", description="Store, purchases, and donation questions", value="Billing & Donations"),
            discord.SelectOption(label="Report Member / Staff", description="Report rule violations or staff conduct", value="Report Member"),
            discord.SelectOption(label="Partnerships & Business", description="Server partnerships and inquiries", value="Partnerships"),
            discord.SelectOption(label="Other Inquiries", description="Custom or miscellaneous questions", value="Other Inquiries"),
        ]
        super().__init__(placeholder="select ticket category...", min_values=1, max_values=1, options=options, custom_id="fleed_ticket_select_cat")

    async def callback(self, interaction: discord.Interaction):
        category_name = self.values[0]
        await interaction.response.send_modal(TicketOpenModal(self.bot, category_name))


class TicketPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketCategorySelect(bot))

    @discord.ui.button(label="create ticket", style=discord.ButtonStyle.secondary, custom_id="fleed_ticket_btn_create")
    async def btn_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketOpenModal(self.bot, "General Support"))


class TicketControlOptionsSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="Add Member", description="Grant a member access to this ticket", value="add"),
            discord.SelectOption(label="Rename Ticket", description="Rename this channel", value="rename"),
            discord.SelectOption(label="Transfer Ticket", description="Reassign this ticket to another staff member", value="transfer"),
            discord.SelectOption(label="Lock / Unlock", description="Toggle whether the opener can send messages", value="lock"),
        ]
        super().__init__(placeholder="ticket options & tools...", min_values=1, max_values=1, options=options, custom_id="fleed_ticket_opt_select")

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "add":
            await interaction.response.send_modal(TicketAddUserModal())
        elif action == "rename":
            await interaction.response.send_modal(TicketRenameModal())
        elif action == "transfer":
            await interaction.response.send_modal(TicketTransferModal(self.bot))
        elif action == "lock":
            row = await self.bot.db.fetchrow("SELECT opener_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
            if not row:
                return await interaction.response.send_message(embed=error_embed("ticket data not found", interaction.user), ephemeral=True)
            opener = interaction.guild.get_member(row["opener_id"])
            if not opener:
                return await interaction.response.send_message(embed=error_embed("ticket opener is no longer in the server", interaction.user), ephemeral=True)

            current_perms = interaction.channel.permissions_for(opener)
            can_send = current_perms.send_messages
            new_val = not can_send
            await interaction.channel.set_permissions(opener, send_messages=new_val, attach_files=new_val, embed_links=new_val)
            state_text = "unlocked" if new_val else "locked"
            await interaction.response.send_message(embed=success_embed(f"ticket has been **{state_text}** for {opener.mention}", interaction.user))


class CloseConfirmView(discord.ui.View):
    def __init__(self, bot, opener_id: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.opener_id = opener_id

    @discord.ui.button(label="close & transcript", style=discord.ButtonStyle.danger, custom_id="fleed_ticket_confirm_close")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await close_ticket_process(self.bot, interaction.channel, interaction.user, reason="ticket closed by staff")

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.secondary, custom_id="fleed_ticket_cancel_close")
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        await interaction.response.send_message(embed=warn_embed("ticket closure cancelled", interaction.user), ephemeral=True)


class TicketControlView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketControlOptionsSelect(bot))

    @discord.ui.button(label="close", style=discord.ButtonStyle.danger, custom_id="fleed_ticket_close_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await self.bot.db.fetchrow("SELECT opener_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        opener_id = row["opener_id"] if row else interaction.user.id
        view = CloseConfirmView(self.bot, opener_id)
        await interaction.response.send_message(
            embed=warn_embed("are you sure you want to close and archive this ticket?", interaction.user),
            view=view
        )

    @discord.ui.button(label="claim", style=discord.ButtonStyle.secondary, custom_id="fleed_ticket_claim_btn")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await self.bot.db.fetchrow("SELECT claimed_by FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        current_claim = row["claimed_by"] if row else None

        if current_claim == interaction.user.id:
            # Unclaim
            await self.bot.db.execute("UPDATE tickets SET claimed_by = NULL WHERE channel_id = ?", (interaction.channel.id,))
            button.label = "claim"
            button.style = discord.ButtonStyle.secondary
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=warn_embed(f"{interaction.user.mention} unclaimed this ticket", interaction.user))
        else:
            # Claim
            await self.bot.db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (interaction.user.id, interaction.channel.id))
            button.label = f"claimed by {interaction.user.display_name.lower()[:15]}"
            button.style = discord.ButtonStyle.primary
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=success_embed(f"{interaction.user.mention} has claimed this ticket", interaction.user))

    @discord.ui.button(label="transcript", style=discord.ButtonStyle.secondary, custom_id="fleed_ticket_transcript_btn")
    async def transcript_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        messages = [m async for m in interaction.channel.history(limit=1000, oldest_first=True)]
        
        row = await self.bot.db.fetchrow("SELECT * FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        opener = interaction.guild.get_member(row["opener_id"]) if row else None
        ticket_info = {
            "opener_name": str(opener) if opener else (f"User ID {row['opener_id']}" if row else "Unknown"),
            "category": row["category"] if row else "General"
        }
        
        html_file = generate_html_transcript(interaction.guild, interaction.channel, messages, ticket_info)
        file = discord.File(html_file, filename=f"transcript-{interaction.channel.name}.html")
        await interaction.followup.send(
            embed=fleed_embed(title="ticket transcript", description=f"generated transcript for {interaction.channel.mention} ({len(messages)} messages)", author=interaction.user),
            file=file
        )


async def close_ticket_process(bot, channel: discord.TextChannel, closed_by: discord.User, reason: str = "closed by staff"):
    guild = channel.guild
    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    # Fetch info
    ticket_row = await bot.db.fetchrow("SELECT * FROM tickets WHERE channel_id = ?", (channel.id,))
    cfg = await bot.db.fetchrow("SELECT * FROM ticket_config WHERE guild_id = ?", (guild.id,))

    # Update DB
    await bot.db.execute("UPDATE tickets SET status = 'closed', closed_at = ?, closed_by = ? WHERE channel_id = ?", (now_ts, closed_by.id, channel.id))

    # Fetch messages for transcript
    messages = [m async for m in channel.history(limit=1000, oldest_first=True)]
    opener = guild.get_member(ticket_row["opener_id"]) if ticket_row else None
    ticket_info = {
        "opener_name": str(opener) if opener else (f"User ID {ticket_row['opener_id']}" if ticket_row else "Unknown"),
        "category": ticket_row["category"] if ticket_row else "General"
    }

    html_file = generate_html_transcript(guild, channel, messages, ticket_info)
    file_bytes = html_file.getvalue()

    # Post to transcript log channel if configured
    if cfg and cfg["transcript_channel_id"]:
        log_ch = guild.get_channel(cfg["transcript_channel_id"])
        if log_ch:
            opener_str = opener.mention if opener else (f"`{ticket_row['opener_id']}`" if ticket_row else "`unknown`")
            log_embed = fleed_embed(
                title=f"ticket closed — #{channel.name}",
                description=(
                    f"**opener:** {opener_str}\n"
                    f"**closed by:** {closed_by.mention}\n"
                    f"**category:** {ticket_info['category']}\n"
                    f"**reason:** {reason}\n"
                    f"**messages:** `{len(messages)}`"
                ),
                author=closed_by
            )
            log_embed.set_footer(text=f"closed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
            try:
                log_file = discord.File(io.BytesIO(file_bytes), filename=f"transcript-{channel.name}.html")
                await log_ch.send(embed=log_embed, file=log_file)
            except Exception:
                pass

    # Send DM to opener
    if opener:
        try:
            dm_embed = fleed_embed(
                title=f"ticket closed in {guild.name.lower()}",
                description=f"your ticket `#{channel.name}` has been closed by {closed_by.mention}.\na complete transcript of your ticket is attached below.",
                author=closed_by
            )
            dm_file = discord.File(io.BytesIO(file_bytes), filename=f"transcript-{channel.name}.html")
            await opener.send(embed=dm_embed, file=dm_file)
        except Exception:
            pass

    # Countdown and delete
    await channel.send(embed=warn_embed("ticket will be deleted in 5 seconds...", closed_by))
    await discord.utils.sleep_until(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=5))
    try:
        await channel.delete(reason=f"ticket closed: {reason}")
    except Exception:
        pass


# ==================== INTERACTIVE SETUP WIZARD ====================

class TicketSetupWizard(discord.ui.View):
    def __init__(self, bot, author: discord.Member, guild: discord.Guild):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.guild = guild
        self.step = 1

        self.support_roles: list = []
        self.panel_channel: discord.TextChannel = None
        self.category: discord.CategoryChannel = None
        self.transcript_channel: discord.TextChannel = None

        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(embed=error_embed("only the person who started this setup wizard can use it", interaction.user), ephemeral=True)
            return False
        return True

    def get_embed(self) -> discord.Embed:
        if self.step == 1:
            desc = (
                "**step 1 of 2: staff roles**\n\n"
                "which roles should have access to tickets?\n"
                "- select one or more roles from the dropdown below\n"
                "- or click **skip** if only administrators should handle tickets"
            )
            em = fleed_embed(title="ticket setup wizard", description=desc, author=self.author)
            em.set_footer(text="step 1/2 | staff roles")
            return em

        elif self.step == 2:
            if self.support_roles:
                roles_text = ", ".join(r.mention for r in self.support_roles)
            else:
                roles_text = "`none (admins only)`"
            desc = (
                f"**staff roles:** {roles_text}\n\n"
                "**step 2 of 2: auto setup**\n\n"
                "click **1-click auto setup** to automatically create:\n"
                "- a `support` category with proper permissions\n"
                "- a `#tickets` panel channel\n"
                "- a `#ticket-logs` transcript channel\n"
                "- deploy the interactive ticket panel"
            )
            em = fleed_embed(title="ticket setup wizard", description=desc, author=self.author)
            em.set_footer(text="step 2/2 | auto setup")
            return em

    def update_components(self):
        self.clear_items()

        if self.step == 1:
            role_select = discord.ui.RoleSelect(
                placeholder="select staff roles...",
                min_values=1,
                max_values=10
            )
            async def role_callback(interaction: discord.Interaction):
                self.support_roles = list(role_select.values)
                self.step = 2
                self.update_components()
                await interaction.response.edit_message(embed=self.get_embed(), view=self)
            role_select.callback = role_callback
            self.add_item(role_select)

            skip_btn = discord.ui.Button(label="skip (admins only)", style=discord.ButtonStyle.secondary)
            async def skip_callback(interaction: discord.Interaction):
                self.support_roles = []
                self.step = 2
                self.update_components()
                await interaction.response.edit_message(embed=self.get_embed(), view=self)
            skip_btn.callback = skip_callback
            self.add_item(skip_btn)

            cancel_btn = discord.ui.Button(label="cancel", style=discord.ButtonStyle.danger)
            async def cancel_callback(interaction: discord.Interaction):
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=warn_embed("ticket setup cancelled", interaction.user), view=self)
            cancel_btn.callback = cancel_callback
            self.add_item(cancel_btn)

        elif self.step == 2:
            one_click_btn = discord.ui.Button(label="1-click auto setup", style=discord.ButtonStyle.primary)
            async def one_click_callback(interaction: discord.Interaction):
                await self.auto_setup_all(interaction)
            one_click_btn.callback = one_click_callback
            self.add_item(one_click_btn)

            back_btn = discord.ui.Button(label="back", style=discord.ButtonStyle.secondary)
            async def back_callback(interaction: discord.Interaction):
                self.step = 1
                self.update_components()
                await interaction.response.edit_message(embed=self.get_embed(), view=self)
            back_btn.callback = back_callback
            self.add_item(back_btn)

            cancel_btn = discord.ui.Button(label="cancel", style=discord.ButtonStyle.danger)
            async def cancel_callback(interaction: discord.Interaction):
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(embed=warn_embed("ticket setup cancelled", interaction.user), view=self)
            cancel_btn.callback = cancel_callback
            self.add_item(cancel_btn)

    async def auto_setup_all(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = self.guild
        errors = []
        roles = self.support_roles

        # 1. Support Category
        cat = discord.utils.find(lambda c: c.name.lower() in ["support", "tickets"], guild.categories)
        if not cat:
            cat_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
            }
            for r in roles:
                cat_overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True)
            try:
                cat = await guild.create_category(name="support", overwrites=cat_overwrites, reason="ticket auto setup")
            except Exception as e:
                import traceback
                traceback.print_exc()
                errors.append(f"category: {e}")
        self.category = cat

        # 2. Transcripts Channel
        log_ch = discord.utils.find(lambda ch: ch.name.lower() in ["ticket-logs", "transcripts"], guild.text_channels)
        if not log_ch:
            log_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True)
            }
            for r in roles:
                log_overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
            try:
                log_ch = await guild.create_text_channel(name="ticket-logs", category=cat, overwrites=log_overwrites, topic="automated ticket transcripts", reason="ticket auto setup")
            except Exception as e:
                import traceback
                traceback.print_exc()
                errors.append(f"log channel: {e}")
        self.transcript_channel = log_ch

        # 3. Panel Channel
        panel_ch = discord.utils.find(lambda ch: ch.name.lower() in ["tickets", "create-a-ticket"], guild.text_channels)
        if not panel_ch:
            panel_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False, add_reactions=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True, manage_messages=True)
            }
            try:
                panel_ch = await guild.create_text_channel(name="tickets", category=cat, overwrites=panel_overwrites, topic="open a private support ticket", reason="ticket auto setup")
            except Exception as e:
                import traceback
                traceback.print_exc()
                errors.append(f"panel channel: {e}")
                panel_ch = interaction.channel
        self.panel_channel = panel_ch or interaction.channel

        if errors:
            print(f"[TICKET SETUP] auto setup had errors: {errors}")

        try:
            await self.finish_setup_deferred(interaction)
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(embed=error_embed(f"setup failed during finalization: {e}", interaction.user), ephemeral=True)
            except Exception:
                pass

    async def finish_setup_deferred(self, interaction: discord.Interaction):
        guild = self.guild
        final_panel = self.panel_channel or interaction.channel
        final_roles = self.support_roles
        final_cat = self.category
        final_log = self.transcript_channel

        role_ids_str = ",".join(str(r.id) for r in final_roles) if final_roles else ""
        cat_id = final_cat.id if final_cat else 0
        log_id = final_log.id if final_log else 0

        try:
            await self.bot.db.execute(
                """
                INSERT INTO ticket_config (guild_id, category_id, support_role_ids, transcript_channel_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    category_id = excluded.category_id,
                    support_role_ids = excluded.support_role_ids,
                    transcript_channel_id = excluded.transcript_channel_id
                """,
                (guild.id, cat_id, role_ids_str, log_id)
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            return await interaction.followup.send(embed=error_embed(f"failed to save ticket config to database: {e}", interaction.user), ephemeral=True)

        # Deploy Interactive Dropdown Panel
        panel_embed = fleed_embed(
            title="support ticket panel",
            description=(
                "welcome to our support system\n\n"
                "- select a category from the dropdown menu below\n"
                "- or click the **create ticket** button to open a ticket\n"
                "- our support team will be notified and respond promptly"
            ),
            author=self.author
        )
        panel_embed.set_footer(text=f"support system | {guild.name}")

        try:
            await final_panel.send(embed=panel_embed, view=TicketPanelView(self.bot))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return await interaction.followup.send(embed=error_embed(f"failed to send the ticket panel to {final_panel.mention}: {e}", interaction.user), ephemeral=True)

        if final_roles:
            roles_text = ", ".join(r.mention for r in final_roles)
        else:
            roles_text = "`none`"

        summary_desc = (
            f"**panel channel:** {final_panel.mention}\n"
            f"**category:** `{final_cat.name if final_cat else 'none'}`\n"
            f"**staff roles:** {roles_text}\n"
            f"**transcript logs:** {final_log.mention if final_log else '`none`'}\n\n"
            f"the interactive ticket panel has been deployed in {final_panel.mention}"
        )
        try:
            await interaction.edit_original_response(embed=fleed_embed(title="ticket setup completed", description=summary_desc, author=self.author), view=None)
        except Exception:
            try:
                await interaction.followup.send(embed=fleed_embed(title="ticket setup completed", description=summary_desc, author=self.author))
            except Exception:
                pass


# ==================== COG CLASS ====================

class Tickets(commands.Cog):
    """advanced ticket system with interactive dropdown panels, claiming, and html transcripts"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketPanelView(self.bot))
        self.bot.add_view(TicketControlView(self.bot))

    @commands.hybrid_group(name="tickets", aliases=["ticket"], invoke_without_command=True)
    async def tickets(self, ctx):
        await send_group_help(ctx, ctx.command, "tickets")

    @tickets.command(name="setup")
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def tickets_setup(self, ctx, channel: discord.TextChannel = None, support_role: discord.Role = None, category: discord.CategoryChannel = None):
        guild = ctx.guild

        if not guild.me.guild_permissions.manage_channels or not guild.me.guild_permissions.manage_roles:
            return await ctx.send(embed=error_embed("i need `manage channels` and `manage roles` permissions in this server to set up tickets", ctx.author))

        # If no arguments provided, launch the interactive step-by-step selector wizard!
        if channel is None and support_role is None and category is None:
            wizard = TicketSetupWizard(self.bot, ctx.author, guild)
            return await ctx.send(embed=wizard.get_embed(), view=wizard)

        # 1. Support Role (find existing or create)
        role = support_role
        if not role:
            role = discord.utils.find(lambda r: r.name.lower() in ["support", "support staff", "support team", "staff", "tickets", "moderator"], guild.roles)

        # 2. Support Category
        cat = category
        if not cat:
            cat = discord.utils.find(lambda c: c.name.lower() in ["support", "tickets", "help desk"], guild.categories)
            if not cat:
                cat_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
                }
                if role:
                    cat_overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True)
                try:
                    cat = await guild.create_category(name="support", overwrites=cat_overwrites, reason="automated ticket setup: category")
                except Exception:
                    pass

        # 3. Transcripts / Ticket Logs Channel (Staff only)
        log_ch = discord.utils.find(lambda ch: ch.name.lower() in ["ticket-logs", "transcripts", "ticket-transcripts"], guild.text_channels)
        if not log_ch and cat:
            log_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True)
            }
            if role:
                log_overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
            try:
                log_ch = await guild.create_text_channel(name="ticket-logs", category=cat, overwrites=log_overwrites, topic="automated ticket transcripts and closure archives")
            except Exception:
                pass

        # 4. Ticket Panel Channel
        panel_ch = channel
        if not panel_ch:
            panel_ch = discord.utils.find(lambda ch: ch.name.lower() in ["tickets", "create-a-ticket", "open-ticket", "ticket-panel"], guild.text_channels)
            if not panel_ch and cat:
                panel_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False, add_reactions=True, read_message_history=True),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True, manage_messages=True)
                }
                try:
                    panel_ch = await guild.create_text_channel(name="tickets", category=cat, overwrites=panel_overwrites, topic="open a private support ticket")
                except Exception:
                    panel_ch = ctx.channel

        if not panel_ch:
            panel_ch = ctx.channel

        # 5. Save Configuration to Database
        role_ids_str = str(role.id) if role else ""
        cat_id = cat.id if cat else 0
        log_id = log_ch.id if log_ch else 0

        await self.bot.db.execute(
            """
            INSERT INTO ticket_config (guild_id, category_id, support_role_ids, transcript_channel_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                category_id = excluded.category_id,
                support_role_ids = excluded.support_role_ids,
                transcript_channel_id = excluded.transcript_channel_id
            """,
            (guild.id, cat_id, role_ids_str, log_id)
        )

        # 6. Send the Interactive Panel into the panel channel
        panel_embed = fleed_embed(
            title="support ticket panel",
            description=(
                "welcome to our support system\n\n"
                "• select a category from the dropdown menu below\n"
                "• or click the **create ticket** button to open a ticket\n"
                "• our support team will be notified and respond promptly"
            ),
            author=ctx.author
        )
        panel_embed.set_footer(text=f"support system • {guild.name}")
        await panel_ch.send(embed=panel_embed, view=TicketPanelView(self.bot))

        # 7. Confirmation to user
        summary_desc = (
            f"**panel channel:** {panel_ch.mention}\n"
            f"**category:** `{cat.name if cat else 'none'}`\n"
            f"**support role:** {role.mention if role else '`none`'}\n"
            f"**transcript logs:** {log_ch.mention if log_ch else '`none`'}\n\n"
            f"the interactive panel has been deployed in {panel_ch.mention}"
        )
        await ctx.send(embed=fleed_embed(title="automated ticket setup complete", description=summary_desc, author=ctx.author))

    @tickets.command(name="panel")
    @commands.has_permissions(administrator=True)
    async def tickets_panel(self, ctx, channel: discord.TextChannel = None):
        target_ch = channel or ctx.channel
        embed = fleed_embed(
            title="support ticket panel",
            description=(
                "need help or have questions?\n\n"
                "• select a category from the dropdown menu below\n"
                "• or click the **create ticket** button to open a ticket\n"
                "• a private channel will be created for you and staff"
            ),
            author=ctx.author
        )
        embed.set_footer(text=f"support system • {ctx.guild.name}")
        await target_ch.send(embed=embed, view=TicketPanelView(self.bot))
        if target_ch != ctx.channel:
            await ctx.send(embed=success_embed(f"posted ticket panel in {target_ch.mention}", ctx.author))

    @tickets.command(name="close")
    async def tickets_close(self, ctx, channel: discord.TextChannel = None, *, reason: str = "ticket closed"):
        ch = channel or ctx.channel
        row = await self.bot.db.fetchrow("SELECT opener_id FROM tickets WHERE channel_id = ?", (ch.id,))
        if not row and not ch.name.startswith("ticket-"):
            return await ctx.send(embed=error_embed("this is not an active ticket channel", ctx.author))
        
        await close_ticket_process(self.bot, ch, ctx.author, reason=reason)

    @tickets.command(name="claim")
    async def tickets_claim(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await self.bot.db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (ctx.author.id, ch.id))
        await ctx.send(embed=success_embed(f"{ctx.author.mention} has claimed this ticket", ctx.author))

    @tickets.command(name="unclaim")
    async def tickets_unclaim(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await self.bot.db.execute("UPDATE tickets SET claimed_by = NULL WHERE channel_id = ?", (ch.id,))
        await ctx.send(embed=success_embed(f"unclaimed {ch.mention}", ctx.author))

    @tickets.command(name="lock")
    @commands.has_permissions(manage_channels=True)
    async def tickets_lock(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        row = await self.bot.db.fetchrow("SELECT opener_id FROM tickets WHERE channel_id = ?", (ch.id,))
        if row:
            opener = ctx.guild.get_member(row["opener_id"])
            if opener:
                await ch.set_permissions(opener, send_messages=False, attach_files=False, embed_links=False)
        await ctx.send(embed=warn_embed(f"locked {ch.mention} (opener can no longer type)", ctx.author))

    @tickets.command(name="unlock")
    @commands.has_permissions(manage_channels=True)
    async def tickets_unlock(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        row = await self.bot.db.fetchrow("SELECT opener_id FROM tickets WHERE channel_id = ?", (ch.id,))
        if row:
            opener = ctx.guild.get_member(row["opener_id"])
            if opener:
                await ch.set_permissions(opener, send_messages=True, attach_files=True, embed_links=True)
        await ctx.send(embed=success_embed(f"unlocked {ch.mention}", ctx.author))

    @tickets.command(name="transcript")
    async def tickets_transcript(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        messages = [m async for m in ch.history(limit=1000, oldest_first=True)]
        
        row = await self.bot.db.fetchrow("SELECT * FROM tickets WHERE channel_id = ?", (ch.id,))
        opener = ctx.guild.get_member(row["opener_id"]) if row else None
        ticket_info = {
            "opener_name": str(opener) if opener else (f"User ID {row['opener_id']}" if row else "Unknown"),
            "category": row["category"] if row else "General"
        }
        
        html_file = generate_html_transcript(ctx.guild, ch, messages, ticket_info)
        file = discord.File(html_file, filename=f"transcript-{ch.name}.html")
        await ctx.send(
            embed=fleed_embed(title="ticket transcript", description=f"generated transcript for {ch.mention} ({len(messages)} messages)", author=ctx.author),
            file=file
        )

    @tickets.command(name="add")
    @commands.has_permissions(manage_channels=True)
    async def tickets_add_user(self, ctx, member: discord.Member, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await ch.set_permissions(member, view_channel=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True)
        await ctx.send(embed=success_embed(f"added {member.mention} to {ch.mention}", ctx.author))

    @tickets.command(name="remove")
    @commands.has_permissions(manage_channels=True)
    async def tickets_remove_user(self, ctx, member: discord.Member, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        await ch.set_permissions(member, overwrite=None)
        await ctx.send(embed=success_embed(f"removed {member.mention} from {ch.mention}", ctx.author))

    @tickets.command(name="rename")
    @commands.has_permissions(manage_channels=True)
    async def tickets_rename(self, ctx, *, new_name: str):
        cleaned = new_name.lower().replace(" ", "-")
        await ctx.channel.edit(name=cleaned, reason=f"ticket rename by {ctx.author}")
        await ctx.send(embed=success_embed(f"renamed ticket to `#{cleaned}`", ctx.author))

    @tickets.command(name="topic")
    @commands.has_permissions(manage_channels=True)
    async def tickets_topic(self, ctx, *, new_topic: str):
        await ctx.channel.edit(topic=new_topic, reason=f"ticket topic by {ctx.author}")
        await ctx.send(embed=success_embed(f"updated ticket topic to `{new_topic}`", ctx.author))

    @tickets.command(name="transfer")
    @commands.has_permissions(manage_channels=True)
    async def tickets_transfer(self, ctx, staff_member: discord.Member):
        await self.bot.db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (staff_member.id, ctx.channel.id))
        await ctx.channel.set_permissions(staff_member, view_channel=True, send_messages=True, attach_files=True, embed_links=True)
        await ctx.send(embed=success_embed(f"transferred ticket to {staff_member.mention}", ctx.author))

    @tickets.group(name="config", aliases=["settings"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def tickets_config_grp(self, ctx):
        cfg = await self.bot.db.fetchrow("SELECT * FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,))
        cat_str = f"<#{cfg['category_id']}>" if cfg and cfg["category_id"] else "`default (tickets)`"
        roles_list = []
        if cfg and "support_role_ids" in cfg.keys() and cfg["support_role_ids"]:
            for r_id in str(cfg["support_role_ids"]).split(","):
                r_id = r_id.strip()
                if r_id.isdigit():
                    roles_list.append(f"<@&{r_id}>")
        role_str = ", ".join(roles_list) if roles_list else "`none`"
        total = cfg["ticket_counter"] if cfg and cfg["ticket_counter"] else 0

        desc = (
            f"**category:** {cat_str}\n"
            f"**transcripts channel:** {trans_str}\n"
            f"**staff roles:** {role_str}\n"
            f"**total tickets opened:** `{total}`\n\n"
            f"use `,tickets config transcripts <#channel>` to enable auto-logging."
        )
        await ctx.send(embed=fleed_embed(title="ticket system configuration", description=desc, author=ctx.author))

    @tickets_config_grp.command(name="transcripts", aliases=["transcriptchannel", "logs"])
    @commands.has_permissions(administrator=True)
    async def config_transcripts(self, ctx, channel: discord.TextChannel = None):
        ch_id = channel.id if channel else 0
        await self.bot.db.execute(
            "INSERT INTO ticket_config (guild_id, transcript_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET transcript_channel_id = ?",
            (ctx.guild.id, ch_id, ch_id)
        )
        msg = f"transcripts will be sent to {channel.mention}" if channel else "disabled automated transcript logging"
        await ctx.send(embed=success_embed(msg, ctx.author))

    @tickets_config_grp.command(name="role", aliases=["supportrole", "staffrole", "roles"])
    @commands.has_permissions(administrator=True)
    async def config_role(self, ctx, role: discord.Role = None):
        r_str = str(role.id) if role else ""
        await self.bot.db.execute(
            "INSERT INTO ticket_config (guild_id, support_role_ids) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET support_role_ids = ?",
            (ctx.guild.id, r_str, r_str)
        )
        msg = f"staff role set to {role.mention}" if role else "cleared staff roles"
        await ctx.send(embed=success_embed(msg, ctx.author))

    @tickets.command(name="stats", aliases=["ticketstats"])
    async def direct_ticket_stats(self, ctx):
        open_rows = await self.bot.db.fetch("SELECT id FROM tickets WHERE guild_id = ? AND status = 'open'", (ctx.guild.id,))
        total_rows = await self.bot.db.fetch("SELECT id FROM tickets WHERE guild_id = ?", (ctx.guild.id,))
        open_count = len(open_rows)
        total_count = len(total_rows)
        desc = f"**open tickets:** `{open_count}`\n**total tickets created:** `{total_count}`"
        await ctx.send(embed=fleed_embed(title="ticket statistics", description=desc, author=ctx.author))

    # Top-level alias shortcuts
    @commands.command(name="panel")
    @commands.has_permissions(administrator=True)
    async def direct_panel(self, ctx, channel: discord.TextChannel = None):
        await self.tickets_panel(ctx, channel)

    @commands.command(name="close")
    async def direct_close(self, ctx, channel: discord.TextChannel = None, *, reason: str = "ticket closed"):
        await self.tickets_close(ctx, channel, reason=reason)

    @commands.command(name="claim")
    async def direct_claim(self, ctx, channel: discord.TextChannel = None):
        await self.tickets_claim(ctx, channel)

    @commands.command(name="unclaim")
    async def direct_unclaim(self, ctx, channel: discord.TextChannel = None):
        await self.tickets_unclaim(ctx, channel)

    @commands.command(name="transcript")
    async def direct_transcript(self, ctx, channel: discord.TextChannel = None):
        await self.tickets_transcript(ctx, channel)


async def setup(bot):
    await bot.add_cog(Tickets(bot))
