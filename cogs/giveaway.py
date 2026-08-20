import discord
from discord.ext import commands, tasks
import random
import datetime
import re
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help


# ==================== TIME PARSING ====================

def parse_duration(duration_str: str) -> int:
    """Parse a human duration string like '1d', '2h30m', '1w' into seconds."""
    pattern = re.compile(r'(\d+)\s*([smhdw])', re.IGNORECASE)
    matches = pattern.findall(duration_str)
    if not matches:
        return 0

    total = 0
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
    for val, unit in matches:
        total += int(val) * units.get(unit.lower(), 0)
    return total


def format_duration(seconds: int) -> str:
    """Format seconds into a human readable string."""
    if seconds <= 0:
        return "ended"
    parts = []
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, seconds = divmod(seconds, 60)
    if d:
        parts.append(f"{int(d)}d")
    if h:
        parts.append(f"{int(h)}h")
    if m:
        parts.append(f"{int(m)}m")
    if seconds and not parts:
        parts.append(f"{int(seconds)}s")
    return " ".join(parts) if parts else "< 1m"


def format_timestamp(unix_ts: int) -> str:
    """Return a Discord relative timestamp."""
    return f"<t:{unix_ts}:R>"


# ==================== VIEWS ====================

class GiveawayEntryView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="enter giveaway", style=discord.ButtonStyle.primary, custom_id="fleed_giveaway_enter")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await self.bot.db.fetchrow(
            "SELECT * FROM giveaways WHERE message_id = ?",
            (interaction.message.id,)
        )
        if not row:
            return await interaction.response.send_message(
                embed=error_embed("this giveaway no longer exists", interaction.user),
                ephemeral=True
            )

        if row["ended"]:
            return await interaction.response.send_message(
                embed=error_embed("this giveaway has already ended", interaction.user),
                ephemeral=True
            )

        # Check required role
        if row["required_role_id"]:
            required_role = interaction.guild.get_role(row["required_role_id"])
            if required_role and required_role not in interaction.user.roles:
                return await interaction.response.send_message(
                    embed=error_embed(f"you need the {required_role.mention} role to enter this giveaway", interaction.user),
                    ephemeral=True
                )

        # Parse existing entries
        entries_str = row["entries"] or ""
        entries = [int(x) for x in entries_str.split(",") if x.strip().isdigit()]
        user_id = interaction.user.id

        if user_id in entries:
            # Withdraw
            entries.remove(user_id)
            new_entries = ",".join(str(e) for e in entries)
            await self.bot.db.execute(
                "UPDATE giveaways SET entries = ? WHERE message_id = ?",
                (new_entries, interaction.message.id)
            )

            # Update embed with new count
            await self._update_embed(interaction, row, len(entries))
            return await interaction.response.send_message(
                embed=warn_embed("you have withdrawn from this giveaway", interaction.user),
                ephemeral=True
            )
        else:
            # Enter
            entries.append(user_id)
            new_entries = ",".join(str(e) for e in entries)
            await self.bot.db.execute(
                "UPDATE giveaways SET entries = ? WHERE message_id = ?",
                (new_entries, interaction.message.id)
            )

            await self._update_embed(interaction, row, len(entries))
            return await interaction.response.send_message(
                embed=success_embed("you have entered the giveaway", interaction.user),
                ephemeral=True
            )

    async def _update_embed(self, interaction, row, entry_count):
        try:
            msg = interaction.message
            if msg.embeds:
                embed = msg.embeds[0]
                # Update the entries field
                for i, field in enumerate(embed.fields):
                    if field.name == "entries":
                        embed.set_field_at(i, name="entries", value=f"`{entry_count}`", inline=True)
                        break
                await msg.edit(embed=embed, view=self)
        except Exception:
            pass


class GiveawayEndedView(discord.ui.View):
    """Disabled view for ended giveaways."""
    def __init__(self):
        super().__init__(timeout=None)
        btn = discord.ui.Button(
            label="giveaway ended",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            custom_id="fleed_giveaway_ended"
        )
        self.add_item(btn)


# ==================== COG ====================

class Giveaways(commands.Cog):
    """giveaway system with timed draws, role requirements, and rerolls"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(GiveawayEntryView(self.bot))
        self.bot.add_view(GiveawayEndedView())
        self.giveaway_loop.start()

    async def cog_unload(self):
        self.giveaway_loop.cancel()

    # ==================== GIVEAWAY LOOP ====================

    @tasks.loop(seconds=15)
    async def giveaway_loop(self):
        """Check for giveaways that need to end."""
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        rows = await self.bot.db.fetch(
            "SELECT * FROM giveaways WHERE ended = 0 AND ends_at <= ?",
            (now,)
        )
        for row in rows:
            try:
                await self._end_giveaway(row)
            except Exception as e:
                print(f"[GIVEAWAY] error ending giveaway {row['id']}: {e}")

    @giveaway_loop.before_loop
    async def before_giveaway_loop(self):
        await self.bot.wait_until_ready()

    # ==================== INTERNAL ====================

    async def _end_giveaway(self, row):
        guild = self.bot.get_guild(row["guild_id"])
        if not guild:
            return

        channel = guild.get_channel(row["channel_id"])
        if not channel:
            return

        try:
            msg = await channel.fetch_message(row["message_id"])
        except Exception:
            await self.bot.db.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (row["id"],))
            return

        # Pick winners
        entries_str = row["entries"] or ""
        entries = [int(x) for x in entries_str.split(",") if x.strip().isdigit()]
        winner_count = row["winner_count"] or 1

        winners = []
        if entries:
            sample_size = min(winner_count, len(entries))
            winner_ids = random.sample(entries, sample_size)
            for wid in winner_ids:
                member = guild.get_member(wid)
                if member:
                    winners.append(member)

        winner_ids_str = ",".join(str(w.id) for w in winners)
        await self.bot.db.execute(
            "UPDATE giveaways SET ended = 1, winners = ? WHERE id = ?",
            (winner_ids_str, row["id"])
        )

        # Update the giveaway message
        host = guild.get_member(row["host_id"])
        host_mention = host.mention if host else f"<@{row['host_id']}>"

        if winners:
            winner_text = ", ".join(w.mention for w in winners)
            end_embed = fleed_embed(
                title=row["prize"],
                description=(
                    f"**winners:** {winner_text}\n"
                    f"**hosted by:** {host_mention}\n\n"
                    f"**entries:** `{len(entries)}`"
                ),
                color=0x2B2D31
            )
            end_embed.set_footer(text="giveaway ended")
            end_embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

            await msg.edit(embed=end_embed, view=GiveawayEndedView())
            await channel.send(
                f"congratulations {winner_text} -- you won **{row['prize']}**",
                reference=msg,
                mention_author=False
            )
        else:
            end_embed = fleed_embed(
                title=row["prize"],
                description=(
                    f"**winners:** no valid entries\n"
                    f"**hosted by:** {host_mention}\n\n"
                    f"**entries:** `{len(entries)}`"
                ),
                color=0x2B2D31
            )
            end_embed.set_footer(text="giveaway ended")
            end_embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

            await msg.edit(embed=end_embed, view=GiveawayEndedView())
            await channel.send(
                f"no valid entries for **{row['prize']}** -- nobody won",
                reference=msg,
                mention_author=False
            )

    # ==================== COMMANDS ====================

    @commands.hybrid_group(name="giveaway", aliases=["gw", "giveaways"], invoke_without_command=True)
    async def giveaway(self, ctx):
        await send_group_help(ctx, ctx.command, "giveaway")

    @giveaway.command(name="start", aliases=["create", "new"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_start(self, ctx, duration: str, winners: int, *, prize: str):
        """start a giveaway
        
        usage: ,giveaway start <duration> <winners> <prize>
        example: ,giveaway start 1d 1 Nitro Classic
        example: ,giveaway start 12h 3 $10 Gift Card
        """
        seconds = parse_duration(duration)
        if seconds < 10:
            return await ctx.send(embed=error_embed("duration must be at least 10 seconds (e.g. `1m`, `1h`, `1d`)", ctx.author))
        if seconds > 2592000:
            return await ctx.send(embed=error_embed("duration cannot exceed 30 days", ctx.author))
        if winners < 1:
            return await ctx.send(embed=error_embed("winner count must be at least 1", ctx.author))
        if winners > 50:
            return await ctx.send(embed=error_embed("winner count cannot exceed 50", ctx.author))

        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        ends_at = now + seconds

        embed = fleed_embed(
            title=prize,
            description=(
                f"click the button below to enter\n\n"
                f"**ends:** {format_timestamp(ends_at)}\n"
                f"**hosted by:** {ctx.author.mention}"
            ),
            color=0x2B2D31
        )
        embed.add_field(name="winners", value=f"`{winners}`", inline=True)
        embed.add_field(name="entries", value="`0`", inline=True)
        embed.set_footer(text=f"ends {format_duration(seconds)} from now")
        embed.timestamp = datetime.datetime.fromtimestamp(ends_at, tz=datetime.timezone.utc)

        view = GiveawayEntryView(self.bot)
        msg = await ctx.send(embed=embed, view=view)

        await self.bot.db.execute(
            """
            INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winner_count, ends_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ctx.guild.id, ctx.channel.id, msg.id, ctx.author.id, prize, winners, ends_at, now)
        )

        # Delete the command invocation
        try:
            await ctx.message.delete()
        except Exception:
            pass

    @giveaway.command(name="end", aliases=["stop"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_end(self, ctx, message_id: int = None):
        """end a giveaway early"""
        if message_id is None:
            # Try to find the most recent active giveaway in this channel
            row = await self.bot.db.fetchrow(
                "SELECT * FROM giveaways WHERE channel_id = ? AND ended = 0 ORDER BY created_at DESC LIMIT 1",
                (ctx.channel.id,)
            )
        else:
            row = await self.bot.db.fetchrow(
                "SELECT * FROM giveaways WHERE message_id = ? AND ended = 0",
                (message_id,)
            )

        if not row:
            return await ctx.send(embed=error_embed("no active giveaway found", ctx.author))

        await self._end_giveaway(row)
        await ctx.send(embed=success_embed(f"giveaway for **{row['prize']}** has been ended", ctx.author))

    @giveaway.command(name="reroll")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx, message_id: int = None, winners: int = 1):
        """reroll winners for an ended giveaway"""
        if message_id is None:
            row = await self.bot.db.fetchrow(
                "SELECT * FROM giveaways WHERE channel_id = ? AND ended = 1 ORDER BY created_at DESC LIMIT 1",
                (ctx.channel.id,)
            )
        else:
            row = await self.bot.db.fetchrow(
                "SELECT * FROM giveaways WHERE message_id = ? AND ended = 1",
                (message_id,)
            )

        if not row:
            return await ctx.send(embed=error_embed("no ended giveaway found to reroll", ctx.author))

        entries_str = row["entries"] or ""
        entries = [int(x) for x in entries_str.split(",") if x.strip().isdigit()]

        if not entries:
            return await ctx.send(embed=error_embed("no entries in this giveaway to reroll from", ctx.author))

        sample_size = min(winners, len(entries))
        winner_ids = random.sample(entries, sample_size)
        new_winners = []
        for wid in winner_ids:
            member = ctx.guild.get_member(wid)
            if member:
                new_winners.append(member)

        if not new_winners:
            return await ctx.send(embed=error_embed("could not find any valid members to reroll", ctx.author))

        winner_text = ", ".join(w.mention for w in new_winners)

        # Update DB
        winner_ids_str = ",".join(str(w.id) for w in new_winners)
        await self.bot.db.execute(
            "UPDATE giveaways SET winners = ? WHERE id = ?",
            (winner_ids_str, row["id"])
        )

        # Try referencing the original message
        try:
            channel = ctx.guild.get_channel(row["channel_id"])
            msg = await channel.fetch_message(row["message_id"])
            await ctx.send(
                f"rerolled -- new winner(s) for **{row['prize']}**: {winner_text}",
                reference=msg,
                mention_author=False
            )
        except Exception:
            await ctx.send(f"rerolled -- new winner(s) for **{row['prize']}**: {winner_text}")

    @giveaway.command(name="list", aliases=["active"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_list(self, ctx):
        """list all active giveaways in this server"""
        rows = await self.bot.db.fetch(
            "SELECT * FROM giveaways WHERE guild_id = ? AND ended = 0 ORDER BY ends_at ASC",
            (ctx.guild.id,)
        )

        if not rows:
            return await ctx.send(embed=warn_embed("no active giveaways in this server", ctx.author))

        lines = []
        for i, row in enumerate(rows, 1):
            entries_str = row["entries"] or ""
            entry_count = len([x for x in entries_str.split(",") if x.strip().isdigit()])
            lines.append(
                f"`{i}.` **{row['prize']}** in <#{row['channel_id']}>\n"
                f"   ends {format_timestamp(row['ends_at'])} | `{entry_count}` entries | `{row['winner_count']}` winners"
            )

        embed = fleed_embed(
            title=f"active giveaways ({len(rows)})",
            description="\n".join(lines),
            author=ctx.author
        )
        await ctx.send(embed=embed)

    @giveaway.command(name="info")
    async def giveaway_info(self, ctx, message_id: int):
        """view details about a specific giveaway"""
        row = await self.bot.db.fetchrow(
            "SELECT * FROM giveaways WHERE message_id = ?",
            (message_id,)
        )

        if not row:
            return await ctx.send(embed=error_embed("giveaway not found", ctx.author))

        entries_str = row["entries"] or ""
        entries = [int(x) for x in entries_str.split(",") if x.strip().isdigit()]
        status = "ended" if row["ended"] else "active"
        host = ctx.guild.get_member(row["host_id"])
        host_text = host.mention if host else f"`{row['host_id']}`"

        desc = (
            f"**prize:** {row['prize']}\n"
            f"**status:** `{status}`\n"
            f"**hosted by:** {host_text}\n"
            f"**winners:** `{row['winner_count']}`\n"
            f"**entries:** `{len(entries)}`\n"
            f"**channel:** <#{row['channel_id']}>\n"
        )

        if row["ended"] and row["winners"]:
            winner_ids = [int(x) for x in row["winners"].split(",") if x.strip().isdigit()]
            winner_mentions = []
            for wid in winner_ids:
                m = ctx.guild.get_member(wid)
                winner_mentions.append(m.mention if m else f"`{wid}`")
            desc += f"**drawn winners:** {', '.join(winner_mentions)}\n"

        if not row["ended"]:
            desc += f"**ends:** {format_timestamp(row['ends_at'])}\n"

        if row["required_role_id"]:
            desc += f"**required role:** <@&{row['required_role_id']}>\n"

        embed = fleed_embed(title="giveaway info", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

    @giveaway.command(name="cancel", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def giveaway_cancel(self, ctx, message_id: int = None):
        """cancel a giveaway without picking winners"""
        if message_id is None:
            row = await self.bot.db.fetchrow(
                "SELECT * FROM giveaways WHERE channel_id = ? AND ended = 0 ORDER BY created_at DESC LIMIT 1",
                (ctx.channel.id,)
            )
        else:
            row = await self.bot.db.fetchrow(
                "SELECT * FROM giveaways WHERE message_id = ?",
                (message_id,)
            )

        if not row:
            return await ctx.send(embed=error_embed("no giveaway found", ctx.author))

        # Delete from DB
        await self.bot.db.execute("DELETE FROM giveaways WHERE id = ?", (row["id"],))

        # Try to delete/edit the message
        try:
            channel = ctx.guild.get_channel(row["channel_id"])
            msg = await channel.fetch_message(row["message_id"])
            cancel_embed = fleed_embed(
                title=row["prize"],
                description="this giveaway has been cancelled",
                color=0x2B2D31
            )
            cancel_embed.set_footer(text="giveaway cancelled")
            await msg.edit(embed=cancel_embed, view=GiveawayEndedView())
        except Exception:
            pass

        await ctx.send(embed=success_embed(f"giveaway for **{row['prize']}** has been cancelled", ctx.author))


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
