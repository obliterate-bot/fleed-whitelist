import discord
from discord.ext import commands
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help
import io
from PIL import Image

VM_APP_EMOJIS = {
    "lock": "<:vm_lock:1539043578247127093>",
    "unlock": "<:vm_unlock:1539043580897787934>",
    "ghost": "<:vm_ghost:1539043585176109067>",
    "reveal": "<:vm_reveal:1539043590116868146>",
    "rename": "<:vm_rename:1539043592692170813>",
    "claim": "<:vm_claim:1539043595414278314>",
    "increase": "<:vm_plus:1539043598123667517>",
    "decrease": "<:vm_minus:1539043601118396436>",
    "delete": "<:vm_delete:1539043604054409287>",
    "info": "<:vm_info:1539043607057666148>",
}

def resolve_vm_emoji(bot: commands.Bot, guild: discord.Guild, key: str) -> str:
    return VM_APP_EMOJIS.get(key, "🔒")

async def get_server_icon_color(guild: discord.Guild) -> int:
    if not guild or not guild.icon:
        return 0xFEE75C
    try:
        icon_bytes = await guild.icon.read()
        im = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
        im = im.resize((32, 32))
        colors = im.getcolors(32 * 32)
        if not colors:
            return 0xFEE75C
        best_color = None
        best_score = -1
        for count, (r, g, b, a) in colors:
            if a < 128:
                continue
            delta = max(r, g, b) - min(r, g, b)
            if 30 < (r + g + b) // 3 < 240:
                score = count * (delta + 1)
                if score > best_score:
                    best_score = score
                    best_color = (r, g, b)
        if best_color:
            return (best_color[0] << 16) + (best_color[1] << 8) + best_color[2]
    except Exception:
        pass
    return 0xFEE75C

async def create_voicemaster_embed(guild: discord.Guild, bot: commands.Bot) -> discord.Embed:
    icon_url = guild.icon.url if guild and guild.icon else (bot.user.display_avatar.url if bot and bot.user else None)
    color = await get_server_icon_color(guild)
    
    e_lock = VM_APP_EMOJIS["lock"]
    e_unlock = VM_APP_EMOJIS["unlock"]
    e_ghost = VM_APP_EMOJIS["ghost"]
    e_reveal = VM_APP_EMOJIS["reveal"]
    e_rename = VM_APP_EMOJIS["rename"]
    e_claim = VM_APP_EMOJIS["claim"]
    e_increase = VM_APP_EMOJIS["increase"]
    e_decrease = VM_APP_EMOJIS["decrease"]
    e_delete = VM_APP_EMOJIS["delete"]
    e_info = VM_APP_EMOJIS["info"]

    desc = (
        "Manage your voice channel by using the buttons below.\n\n"
        "**Button Usage**\n"
        f"{e_lock} — `Lock` the voice channel\n"
        f"{e_unlock} — `Unlock` the voice channel\n"
        f"{e_ghost} — `Ghost` the voice channel\n"
        f"{e_reveal} — `Reveal` the voice channel\n"
        f"{e_rename} — `Rename`\n"
        f"{e_claim} — `Claim` the voice channel\n"
        f"{e_increase} — `Increase` the user limit\n"
        f"{e_decrease} — `Decrease` the user limit\n"
        f"{e_delete} — `Delete`\n"
        f"{e_info} — `View channel information`"
    )

    embed = discord.Embed(
        title="VoiceMaster Interface",
        description=desc,
        color=color
    )
    if icon_url:
        embed.set_author(name=guild.name, icon_url=icon_url)
        embed.set_thumbnail(url=icon_url)
    else:
        embed.set_author(name=guild.name)

    return embed

class VoiceMasterRenameModal(discord.ui.Modal, title="rename voice channel"):
    name_input = discord.ui.TextInput(
        label="channel name",
        placeholder="enter new channel name...",
        min_length=1,
        max_length=50,
        required=True
    )

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value
        try:
            await self.vc.edit(name=new_name)
            await interaction.response.send_message(
                embed=success_embed(f"renamed voice channel to `{new_name.lower()}`", interaction.user),
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"failed to rename channel: {e}", interaction.user),
                ephemeral=True
            )

class VoiceMasterView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild = None):
        super().__init__(timeout=None)
        self.bot = bot

    async def get_user_channel(self, interaction: discord.Interaction):
        user = interaction.user
        if not user.voice or not user.voice.channel:
            await interaction.response.send_message(
                embed=error_embed("you must be in your voice channel to use this", user),
                ephemeral=True
            )
            return None, None
        
        vc = user.voice.channel
        row = await self.bot.db.fetchrow(
            "SELECT owner_id FROM voicemaster_channels WHERE channel_id = ?",
            (vc.id,)
        )
        if not row:
            await interaction.response.send_message(
                embed=error_embed("you are not in a temporary voice channel", user),
                ephemeral=True
            )
            return None, None

        return vc, row["owner_id"]

    @discord.ui.button(custom_id="vm_lock", style=discord.ButtonStyle.secondary, row=0, emoji=discord.PartialEmoji.from_str("<:vm_lock:1539043578247127093>"))
    async def btn_lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you do not own this voice channel", interaction.user), ephemeral=True)
        
        await vc.set_permissions(interaction.guild.default_role, connect=False)
        await self.bot.db.execute("UPDATE voicemaster_channels SET locked = 1 WHERE channel_id = ?", (vc.id,))
        await interaction.response.send_message(embed=success_embed(f"locked voice channel {vc.name.lower()}", interaction.user), ephemeral=True)

    @discord.ui.button(custom_id="vm_unlock", style=discord.ButtonStyle.secondary, row=0, emoji=discord.PartialEmoji.from_str("<:vm_unlock:1539043580897787934>"))
    async def btn_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you do not own this voice channel", interaction.user), ephemeral=True)
        
        await vc.set_permissions(interaction.guild.default_role, connect=True)
        await self.bot.db.execute("UPDATE voicemaster_channels SET locked = 0 WHERE channel_id = ?", (vc.id,))
        await interaction.response.send_message(embed=success_embed(f"unlocked voice channel {vc.name.lower()}", interaction.user), ephemeral=True)

    @discord.ui.button(custom_id="vm_ghost", style=discord.ButtonStyle.secondary, row=0, emoji=discord.PartialEmoji.from_str("<:vm_ghost:1539043585176109067>"))
    async def btn_ghost(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you do not own this voice channel", interaction.user), ephemeral=True)
        
        await vc.set_permissions(interaction.guild.default_role, view_channel=False)
        await self.bot.db.execute("UPDATE voicemaster_channels SET hidden = 1 WHERE channel_id = ?", (vc.id,))
        await interaction.response.send_message(embed=success_embed(f"hid voice channel {vc.name.lower()}", interaction.user), ephemeral=True)

    @discord.ui.button(custom_id="vm_reveal", style=discord.ButtonStyle.secondary, row=0, emoji=discord.PartialEmoji.from_str("<:vm_reveal:1539043590116868146>"))
    async def btn_reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you do not own this voice channel", interaction.user), ephemeral=True)
        
        await vc.set_permissions(interaction.guild.default_role, view_channel=True)
        await self.bot.db.execute("UPDATE voicemaster_channels SET hidden = 0 WHERE channel_id = ?", (vc.id,))
        await interaction.response.send_message(embed=success_embed(f"revealed voice channel {vc.name.lower()}", interaction.user), ephemeral=True)

    @discord.ui.button(custom_id="vm_claim", style=discord.ButtonStyle.secondary, row=0, emoji=discord.PartialEmoji.from_str("<:vm_claim:1539043595414278314>"))
    async def btn_claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id == interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you already own this voice channel", interaction.user), ephemeral=True)
        
        owner_member = interaction.guild.get_member(owner_id)
        if owner_member and owner_member in vc.members:
            return await interaction.response.send_message(embed=error_embed("the owner is still in this voice channel", interaction.user), ephemeral=True)
        
        await self.bot.db.execute("UPDATE voicemaster_channels SET owner_id = ? WHERE channel_id = ?", (interaction.user.id, vc.id))
        await vc.set_permissions(interaction.user, manage_channels=True, move_members=True, connect=True, speak=True, view_channel=True)
        await interaction.response.send_message(embed=success_embed("claimed ownership of current voice channel", interaction.user), ephemeral=True)

    @discord.ui.button(custom_id="vm_info", style=discord.ButtonStyle.secondary, row=1, emoji=discord.PartialEmoji.from_str("<:vm_info:1539043607057666148>"))
    async def btn_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        desc = (
            f"**owner:** <@{owner_id}>\n"
            f"**bitrate:** {vc.bitrate // 1000}kbps\n"
            f"**user limit:** {vc.user_limit or 'unlimited'}\n"
            f"**connected:** {len(vc.members)}"
        )
        embed = fleed_embed(title=f"channel info: {vc.name.lower()}", description=desc, author=interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(custom_id="vm_increase", style=discord.ButtonStyle.secondary, row=1, emoji=discord.PartialEmoji.from_str("<:vm_plus:1539043598123667517>"))
    async def btn_increase(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you do not own this voice channel", interaction.user), ephemeral=True)
        
        new_limit = min(99, (vc.user_limit or 0) + 1)
        await vc.edit(user_limit=new_limit)
        await interaction.response.send_message(embed=success_embed(f"increased user limit to {new_limit}", interaction.user), ephemeral=True)

    @discord.ui.button(custom_id="vm_decrease", style=discord.ButtonStyle.secondary, row=1, emoji=discord.PartialEmoji.from_str("<:vm_minus:1539043601118396436>"))
    async def btn_decrease(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you do not own this voice channel", interaction.user), ephemeral=True)
        
        new_limit = max(0, (vc.user_limit or 0) - 1)
        await vc.edit(user_limit=new_limit)
        await interaction.response.send_message(embed=success_embed(f"decreased user limit to {new_limit or 'unlimited'}", interaction.user), ephemeral=True)

    @discord.ui.button(custom_id="vm_rename", style=discord.ButtonStyle.secondary, row=1, emoji=discord.PartialEmoji.from_str("<:vm_rename:1539043592692170813>"))
    async def btn_rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you do not own this voice channel", interaction.user), ephemeral=True)
        
        modal = VoiceMasterRenameModal(vc)
        await interaction.response.send_modal(modal)

    @discord.ui.button(custom_id="vm_delete", style=discord.ButtonStyle.secondary, row=1, emoji=discord.PartialEmoji.from_str("<:vm_delete:1539043604054409287>"))
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self.get_user_channel(interaction)
        if not vc:
            return
        if owner_id != interaction.user.id:
            return await interaction.response.send_message(embed=error_embed("you do not own this voice channel", interaction.user), ephemeral=True)
        
        await interaction.response.send_message(embed=success_embed("deleting voice channel...", interaction.user), ephemeral=True)
        await self.bot.db.execute("DELETE FROM voicemaster_channels WHERE channel_id = ?", (vc.id,))
        try:
            await vc.delete(reason="voicemaster: deleted by owner via interface")
        except Exception:
            pass

class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(VoiceMasterView(self.bot))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        guild = member.guild

        # 1. Member joins the "join to create" voice channel
        if after.channel and after.channel != before.channel:
            cfg = await self.bot.db.fetchrow(
                "SELECT channel_id, category_id, default_name, default_bitrate, default_role, joinrole FROM voicemaster_config WHERE guild_id = ?",
                (guild.id,)
            )
            if cfg and cfg["channel_id"] and after.channel.id == cfg["channel_id"]:
                cat = guild.get_channel(cfg["category_id"]) or after.channel.category

                template = cfg["default_name"] or "{user}'s channel"
                channel_name = template.replace("{user}", member.display_name).replace("{username}", member.name)

                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                    member: discord.PermissionOverwrite(manage_channels=True, move_members=True, connect=True, speak=True, view_channel=True)
                }
                if cfg["default_role"]:
                    r = guild.get_role(cfg["default_role"])
                    if r:
                        overwrites[r] = discord.PermissionOverwrite(connect=True, view_channel=True)

                bitrate = min(guild.bitrate_limit, cfg["default_bitrate"] or 64000)

                try:
                    new_vc = await guild.create_voice_channel(
                        name=channel_name,
                        category=cat,
                        overwrites=overwrites,
                        bitrate=bitrate,
                        reason=f"voicemaster: created for {member.display_name}"
                    )
                    await member.move_to(new_vc)

                    await self.bot.db.execute(
                        "INSERT INTO voicemaster_channels (channel_id, guild_id, owner_id) VALUES (?, ?, ?) ON CONFLICT(channel_id) DO UPDATE SET owner_id = ?",
                        (new_vc.id, guild.id, member.id, member.id)
                    )

                    if cfg["joinrole"]:
                        join_r = guild.get_role(cfg["joinrole"])
                        if join_r:
                            try:
                                await member.add_roles(join_r, reason="voicemaster joinrole")
                            except Exception:
                                pass
                except Exception as e:
                    print(f"[VoiceMaster Error] failed to create temporary channel: {e}")

        # 2. Member leaves a temporary voice channel and it is now empty
        if before.channel and before.channel != after.channel:
            row = await self.bot.db.fetchrow(
                "SELECT channel_id FROM voicemaster_channels WHERE channel_id = ?",
                (before.channel.id,)
            )
            if row:
                remaining = [m for m in before.channel.members if not m.bot]
                if len(remaining) == 0:
                    await self.bot.db.execute("DELETE FROM voicemaster_channels WHERE channel_id = ?", (before.channel.id,))
                    try:
                        await before.channel.delete(reason="voicemaster: temporary voice channel empty")
                    except Exception:
                        pass

    @commands.group(name="voicemaster", aliases=["vm", "voice"], invoke_without_command=True)
    async def voicemaster(self, ctx):
        await send_group_help(ctx, ctx.command)

    @voicemaster.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def voicemaster_setup(self, ctx):
        guild = ctx.guild

        if not guild.me.guild_permissions.manage_channels:
            return await ctx.send(embed=error_embed("i need the `manage channels` permission in this server to create voicemaster channels", ctx.author))

        # 1. Create or get Category
        cat = discord.utils.get(guild.categories, name="voice channels")
        if not cat:
            cat = await guild.create_category(name="voice channels", reason="voicemaster setup: category")

        # 2. Create Voice Channel: join to create
        vc = discord.utils.get(cat.voice_channels, name="join to create")
        if not vc:
            vc = await guild.create_voice_channel(name="join to create", category=cat, reason="voicemaster setup: join to create")

        # 3. Create Text Channel: interface
        tc = discord.utils.get(cat.text_channels, name="interface")
        if not tc:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(send_messages=False, view_channel=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True, manage_messages=True, view_channel=True)
            }
            tc = await guild.create_text_channel(name="interface", category=cat, overwrites=overwrites, topic="voicemaster interface controls", reason="voicemaster setup: interface")

        # 4. Save to database
        await self.bot.db.execute(
            """
            INSERT INTO voicemaster_config (guild_id, channel_id, category_id, interface_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                category_id = excluded.category_id,
                interface_id = excluded.interface_id
            """,
            (guild.id, vc.id, cat.id, tc.id)
        )

        # 5. Send Interface in text channel
        embed = await create_voicemaster_embed(guild, self.bot)
        view = VoiceMasterView(self.bot, guild)
        await tc.send(embed=embed, view=view)

        await ctx.send(embed=success_embed(f"configured voicemaster in {cat.name} ({vc.mention} & {tc.mention})", ctx.author))

    @voicemaster.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def voicemaster_reset(self, ctx):
        row = await self.bot.db.fetchrow("SELECT channel_id, category_id, interface_id FROM voicemaster_config WHERE guild_id = ?", (ctx.guild.id,))
        if row:
            for ch_id in [row["channel_id"], row["interface_id"]]:
                if ch_id:
                    ch = ctx.guild.get_channel(ch_id)
                    if ch:
                        try:
                            await ch.delete(reason="voicemaster reset")
                        except Exception:
                            pass
            if row["category_id"]:
                cat = ctx.guild.get_channel(row["category_id"])
                if cat and len(cat.channels) == 0:
                    try:
                        await cat.delete(reason="voicemaster reset")
                    except Exception:
                        pass

            await self.bot.db.execute("DELETE FROM voicemaster_config WHERE guild_id = ?", (ctx.guild.id,))
            await self.bot.db.execute("DELETE FROM voicemaster_channels WHERE guild_id = ?", (ctx.guild.id,))

        await ctx.send(embed=success_embed("reset voicemaster configuration", ctx.author))

    @voicemaster.command(name="sendinterface", aliases=["interface"])
    @commands.has_permissions(administrator=True)
    async def voicemaster_sendinterface(self, ctx):
        embed = await create_voicemaster_embed(ctx.guild, self.bot)
        view = VoiceMasterView(self.bot, ctx.guild)
        await ctx.send(embed=embed, view=view)

    @voicemaster.command(name="lock")
    async def voicemaster_lock(self, ctx):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.set_permissions(ctx.guild.default_role, connect=False)
        await self.bot.db.execute("UPDATE voicemaster_channels SET locked = 1 WHERE channel_id = ?", (vc.id,))
        await ctx.send(embed=success_embed(f"locked voice channel {vc.name.lower()}", ctx.author))

    @voicemaster.command(name="unlock")
    async def voicemaster_unlock(self, ctx):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.set_permissions(ctx.guild.default_role, connect=True)
        await self.bot.db.execute("UPDATE voicemaster_channels SET locked = 0 WHERE channel_id = ?", (vc.id,))
        await ctx.send(embed=success_embed(f"unlocked voice channel {vc.name.lower()}", ctx.author))

    @voicemaster.command(name="hide", aliases=["ghost"])
    async def voicemaster_hide(self, ctx):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.set_permissions(ctx.guild.default_role, view_channel=False)
        await self.bot.db.execute("UPDATE voicemaster_channels SET hidden = 1 WHERE channel_id = ?", (vc.id,))
        await ctx.send(embed=success_embed(f"hid voice channel {vc.name.lower()}", ctx.author))

    @voicemaster.command(name="reveal", aliases=["unghost", "show", "unhide"])
    async def voicemaster_reveal(self, ctx):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.set_permissions(ctx.guild.default_role, view_channel=True)
        await self.bot.db.execute("UPDATE voicemaster_channels SET hidden = 0 WHERE channel_id = ?", (vc.id,))
        await ctx.send(embed=success_embed(f"revealed voice channel {vc.name.lower()}", ctx.author))

    @voicemaster.command(name="permit", aliases=["allow"])
    async def voicemaster_permit(self, ctx, user: discord.Member):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.set_permissions(user, connect=True, view_channel=True)
        await ctx.send(embed=success_embed(f"permitted {user.mention} to access {vc.name.lower()}", ctx.author))

    @voicemaster.command(name="reject", aliases=["kick"])
    async def voicemaster_reject(self, ctx, user: discord.Member):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.set_permissions(user, connect=False)
        if user.voice and user.voice.channel == vc:
            try:
                await user.move_to(None)
            except Exception:
                pass
        await ctx.send(embed=success_embed(f"rejected {user.mention} from {vc.name.lower()}", ctx.author))

    @voicemaster.command(name="rename", aliases=["name"])
    async def voicemaster_rename(self, ctx, *, name: str):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.edit(name=name)
        await ctx.send(embed=success_embed(f"renamed voice channel to `{name.lower()}`", ctx.author))

    @voicemaster.command(name="limit")
    async def voicemaster_limit(self, ctx, limit: int):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.edit(user_limit=limit)
        await ctx.send(embed=success_embed(f"set user limit for {vc.name.lower()} to {limit}", ctx.author))

    @voicemaster.command(name="bitrate")
    async def voicemaster_bitrate(self, ctx, bitrate: int):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await vc.edit(bitrate=min(ctx.guild.bitrate_limit, bitrate * 1000))
        await ctx.send(embed=success_embed(f"set bitrate for {vc.name.lower()} to {bitrate}kbps", ctx.author))

    @voicemaster.command(name="claim", aliases=["own"])
    async def voicemaster_claim(self, ctx):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in a voice channel to claim it", ctx.author))
        vc = ctx.author.voice.channel
        row = await self.bot.db.fetchrow("SELECT owner_id FROM voicemaster_channels WHERE channel_id = ?", (vc.id,))
        if row and row["owner_id"] == ctx.author.id:
            return await ctx.send(embed=error_embed("you already own this voice channel", ctx.author))
        
        await self.bot.db.execute("UPDATE voicemaster_channels SET owner_id = ? WHERE channel_id = ?", (ctx.author.id, vc.id))
        await vc.set_permissions(ctx.author, manage_channels=True, move_members=True, connect=True, speak=True, view_channel=True)
        await ctx.send(embed=success_embed("claimed ownership of current voice channel", ctx.author))

    @voicemaster.command(name="delete")
    async def voicemaster_delete(self, ctx):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        await self.bot.db.execute("DELETE FROM voicemaster_channels WHERE channel_id = ?", (vc.id,))
        await vc.delete(reason="voicemaster: deleted by owner")
        await ctx.send(embed=success_embed("deleted voice channel", ctx.author))

    @voicemaster.command(name="information", aliases=["info"])
    async def voicemaster_information(self, ctx):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("not in a voice channel", ctx.author))
        vc = ctx.author.voice.channel
        row = await self.bot.db.fetchrow("SELECT owner_id FROM voicemaster_channels WHERE channel_id = ?", (vc.id,))
        owner_str = f"<@{row['owner_id']}>" if row else ctx.author.mention
        desc = (
            f"**owner:** {owner_str}\n"
            f"**bitrate:** {vc.bitrate // 1000}kbps\n"
            f"**user limit:** {vc.user_limit or 'unlimited'}\n"
            f"**connected:** {len(vc.members)}"
        )
        await ctx.send(embed=fleed_embed(title=f"channel info: {vc.name.lower()}", description=desc, author=ctx.author))

    @voicemaster.command(name="region")
    async def voicemaster_region(self, ctx, region: str = "us-east"):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        row = await self.bot.db.fetchrow("SELECT owner_id FROM voicemaster_channels WHERE channel_id = ?", (vc.id,))
        if not row or row["owner_id"] != ctx.author.id:
            return await ctx.send(embed=error_embed("you do not own this voice channel", ctx.author))
        value = None if region.lower() in {"auto", "automatic", "none"} else region.lower()
        try:
            await vc.edit(rtc_region=value, reason=f"voicemaster region change by {ctx.author}")
        except (discord.HTTPException, TypeError) as exc:
            return await ctx.send(embed=error_embed(f"could not set that region: {str(exc)[:200]}", ctx.author))
        await ctx.send(embed=success_embed(f"changed voice region to `{value or 'automatic'}`", ctx.author))

    @voicemaster.command(name="status")
    async def voicemaster_status(self, ctx, *, status: str = None):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in your voice channel", ctx.author))
        vc = ctx.author.voice.channel
        row = await self.bot.db.fetchrow("SELECT owner_id FROM voicemaster_channels WHERE channel_id = ?", (vc.id,))
        if not row or row["owner_id"] != ctx.author.id:
            return await ctx.send(embed=error_embed("you do not own this voice channel", ctx.author))
        try:
            await self.bot.http.request(
                discord.http.Route("PUT", "/channels/{channel_id}/voice-status", channel_id=vc.id),
                json={"status": (status or "")[:500] or None},
            )
        except discord.HTTPException as exc:
            return await ctx.send(embed=error_embed(f"discord rejected the status update: {str(exc)[:200]}", ctx.author))
        await ctx.send(embed=success_embed(f"updated voice channel status to `{status.lower() if status else 'none'}`", ctx.author))

    @voicemaster.command(name="drag")
    async def voicemaster_drag(self, ctx, user: discord.Member):
        if not ctx.author.voice:
            return await ctx.send(embed=error_embed("you must be in a voice channel", ctx.author))
        if user.voice:
            await user.move_to(ctx.author.voice.channel)
            await ctx.send(embed=success_embed(f"dragged {user.mention} into your channel", ctx.author))
        else:
            await ctx.send(embed=error_embed(f"{user.mention} is not in a voice channel", ctx.author))

    @voicemaster.command(name="joinrole")
    @commands.has_permissions(manage_roles=True)
    async def voicemaster_joinrole(self, ctx, role: discord.Role = None):
        r_id = role.id if role else 0
        await self.bot.db.execute("UPDATE voicemaster_config SET joinrole = ? WHERE guild_id = ?", (r_id, ctx.guild.id))
        await ctx.send(embed=success_embed(f"set voicemaster join role to {role.name if role else 'none'}", ctx.author))

    @voicemaster.group(name="default", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def voicemaster_default(self, ctx):
        await send_group_help(ctx, ctx.command)

    @voicemaster_default.command(name="name")
    async def voicemaster_default_name(self, ctx, *, template: str = "{user}'s channel"):
        await self.bot.db.execute("UPDATE voicemaster_config SET default_name = ? WHERE guild_id = ?", (template, ctx.guild.id))
        await ctx.send(embed=success_embed(f"set default channel name to `{template.lower()}`", ctx.author))

    @voicemaster_default.command(name="bitrate")
    async def voicemaster_default_bitrate(self, ctx, bitrate: int = 64):
        await self.bot.db.execute("UPDATE voicemaster_config SET default_bitrate = ? WHERE guild_id = ?", (bitrate * 1000, ctx.guild.id))
        await ctx.send(embed=success_embed(f"set default bitrate to `{bitrate}kbps`", ctx.author))

    @voicemaster_default.command(name="role")
    async def voicemaster_default_role(self, ctx, role: discord.Role = None):
        r_id = role.id if role else 0
        await self.bot.db.execute("UPDATE voicemaster_config SET default_role = ? WHERE guild_id = ?", (r_id, ctx.guild.id))
        await ctx.send(embed=success_embed(f"set default channel access role to {role.name if role else 'none'}", ctx.author))

    @voicemaster_default.command(name="region")
    async def voicemaster_default_region(self, ctx, region: str = "us-east"):
        await self.bot.db.execute("UPDATE voicemaster_config SET default_region = ? WHERE guild_id = ?", (region, ctx.guild.id))
        await ctx.send(embed=success_embed(f"set default region to `{region.lower()}`", ctx.author))

async def setup(bot):
    await bot.add_cog(Voice(bot))

