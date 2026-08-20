import discord
from discord.ext import commands
import random
import time
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help

class BlackjackGameView(discord.ui.View):
    def __init__(self, cog, ctx, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(self.deck)
        self.player_cards = [self.deck.pop(), self.deck.pop()]
        self.dealer_cards = [self.deck.pop(), self.deck.pop()]

    def calculate_score(self, cards):
        score = sum(cards)
        aces = cards.count(11)
        while score > 21 and aces > 0:
            score -= 10
            aces -= 1
        return score

    def build_embed(self, finished=False):
        p_score = self.calculate_score(self.player_cards)
        p_hand = ", ".join(str(c) for c in self.player_cards)

        if finished:
            d_score = self.calculate_score(self.dealer_cards)
            d_hand = ", ".join(str(c) for c in self.dealer_cards)
        else:
            d_score = self.dealer_cards[0]
            d_hand = f"{self.dealer_cards[0]}, ?"

        desc = f"**your hand** ({p_score}): `[{p_hand}]`\n**dealer hand** ({d_score}): `[{d_hand}]`\n**bet**: `${self.bet:,}`"
        return fleed_embed(title="blackjack", description=desc, author=self.ctx.author)

    @discord.ui.button(label="hit", style=discord.ButtonStyle.secondary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("this is not your game", ephemeral=True)

        self.player_cards.append(self.deck.pop())
        p_score = self.calculate_score(self.player_cards)

        if p_score > 21:
            for child in self.children:
                child.disabled = True
            await self.cog.update_balance(self.ctx.guild.id, self.ctx.author.id, wallet_diff=-self.bet)
            embed = self.build_embed(finished=True)
            embed.description += f"\n\n**busted** — lost **${self.bet:,}**"
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="stand", style=discord.ButtonStyle.secondary)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("this is not your game", ephemeral=True)

        for child in self.children:
            child.disabled = True

        p_score = self.calculate_score(self.player_cards)
        while self.calculate_score(self.dealer_cards) < 17:
            self.dealer_cards.append(self.deck.pop())

        d_score = self.calculate_score(self.dealer_cards)
        embed = self.build_embed(finished=True)

        if d_score > 21 or p_score > d_score:
            await self.cog.update_balance(self.ctx.guild.id, self.ctx.author.id, wallet_diff=self.bet)
            embed.description += f"\n\n**winner** — won **${self.bet:,}**"
        elif p_score < d_score:
            await self.cog.update_balance(self.ctx.guild.id, self.ctx.author.id, wallet_diff=-self.bet)
            embed.description += f"\n\n**dealer wins** — lost **${self.bet:,}**"
        else:
            embed.description += "\n\n**push** — bet returned"

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="double", style=discord.ButtonStyle.secondary)
    async def double_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("this is not your game", ephemeral=True)

        wallet, _ = await self.cog.get_balance(self.ctx.guild.id, self.ctx.author.id)
        if wallet < self.bet * 2:
            return await interaction.response.send_message("insufficient balance to double down", ephemeral=True)

        self.bet *= 2
        for child in self.children:
            child.disabled = True

        self.player_cards.append(self.deck.pop())
        p_score = self.calculate_score(self.player_cards)

        if p_score <= 21:
            while self.calculate_score(self.dealer_cards) < 17:
                self.dealer_cards.append(self.deck.pop())

        d_score = self.calculate_score(self.dealer_cards)
        embed = self.build_embed(finished=True)

        if p_score > 21:
            await self.cog.update_balance(self.ctx.guild.id, self.ctx.author.id, wallet_diff=-self.bet)
            embed.description += f"\n\n**busted** — lost **${self.bet:,}**"
        elif d_score > 21 or p_score > d_score:
            await self.cog.update_balance(self.ctx.guild.id, self.ctx.author.id, wallet_diff=self.bet)
            embed.description += f"\n\n**winner** — won **${self.bet:,}**"
        elif p_score < d_score:
            await self.cog.update_balance(self.ctx.guild.id, self.ctx.author.id, wallet_diff=-self.bet)
            embed.description += f"\n\n**dealer wins** — lost **${self.bet:,}**"
        else:
            embed.description += "\n\n**push** — bet returned"

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_balance(self, guild_id: int, user_id: int):
        row = await self.bot.db.fetchrow("SELECT wallet, bank FROM economy WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        if not row:
            await self.bot.db.execute("INSERT INTO economy (guild_id, user_id, wallet, bank) VALUES (?, ?, 100, 0)", (guild_id, user_id))
            return 100, 0
        return row["wallet"], row["bank"]

    async def update_balance(self, guild_id: int, user_id: int, wallet_diff: int = 0, bank_diff: int = 0):
        await self.get_balance(guild_id, user_id)
        await self.bot.db.execute("UPDATE economy SET wallet = wallet + ?, bank = bank + ? WHERE guild_id = ? AND user_id = ?", (wallet_diff, bank_diff, guild_id, user_id))

    @commands.hybrid_group(name="economy", invoke_without_command=True)
    async def economy(self, ctx):
        await send_group_help(ctx, self.economy, "economy")

    @economy.command(name="enable", aliases=["on"])
    @commands.has_permissions(administrator=True)
    async def economy_enable(self, ctx):
        await self.bot.db.execute("INSERT INTO economy_config (guild_id, enabled) VALUES (?, 1) ON CONFLICT(guild_id) DO UPDATE SET enabled = 1", (ctx.guild.id,))
        await ctx.send(embed=success_embed("economy system enabled", ctx.author))

    @economy.command(name="disable", aliases=["off"])
    @commands.has_permissions(administrator=True)
    async def economy_disable(self, ctx):
        await self.bot.db.execute("INSERT INTO economy_config (guild_id, enabled) VALUES (?, 0) ON CONFLICT(guild_id) DO UPDATE SET enabled = 0", (ctx.guild.id,))
        await ctx.send(embed=success_embed("economy system disabled", ctx.author))

    @economy.command(name="preset")
    @commands.has_permissions(administrator=True)
    async def economy_preset(self, ctx, preset_name: str = "default"):
        await self.bot.db.execute("INSERT INTO economy_config (guild_id, preset) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET preset = ?", (ctx.guild.id, preset_name.lower(), preset_name.lower()))
        await ctx.send(embed=success_embed(f"economy preset set to `{preset_name.lower()}`", ctx.author))

    @economy.command(name="mode")
    @commands.has_permissions(administrator=True)
    async def economy_mode(self, ctx, mode: str = "guild"):
        mode = mode.lower()
        if mode not in ["guild", "global"]:
            return await ctx.send(embed=error_embed("mode must be `guild` or `global`", ctx.author))
        await self.bot.db.execute("INSERT INTO economy_config (guild_id, mode) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET mode = ?", (ctx.guild.id, mode, mode))
        await ctx.send(embed=success_embed(f"economy mode switched to `{mode}`", ctx.author))

    @economy.command(name="config", aliases=["settings"])
    @commands.has_permissions(administrator=True)
    async def economy_config(self, ctx):
        row = await self.bot.db.fetchrow("SELECT * FROM economy_config WHERE guild_id = ?", (ctx.guild.id,))
        enabled = "enabled" if not row or row["enabled"] else "disabled"
        mode = row["mode"] if row else "guild"
        preset = row["preset"] if row else "default"
        await ctx.send(embed=fleed_embed(title="economy configuration", description=f"status: {enabled}\nmode: {mode}\npreset: {preset}", author=ctx.author))

    @economy.command(name="leaderboard", aliases=["lb", "rich", "richest"])
    @commands.has_permissions(administrator=True)
    async def economy_leaderboard(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id, (wallet + bank) as total FROM economy WHERE guild_id = ? ORDER BY total DESC LIMIT 10", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed(description="no economy data in this server", author=ctx.author))
        lines = []
        for i, r in enumerate(rows, 1):
            user = self.bot.get_user(r["user_id"])
            tag = str(user).lower() if user else f"user_{r['user_id']}"
            lines.append(f"`{i}` {tag} — **${r['total']:,}**")
        await ctx.send(embed=fleed_embed(title="economy leaderboard", description="\n".join(lines), author=ctx.author))

    @economy.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def economy_reset(self, ctx, member: discord.Member = None):
        if member:
            await self.bot.db.execute("DELETE FROM economy WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
            return await ctx.send(embed=success_embed(f"reset economy data for {member.mention}", ctx.author))
        await self.bot.db.execute("DELETE FROM economy WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=success_embed("reset all economy data for this server", ctx.author))

    @commands.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def reset_admin(self, ctx, member: discord.Member):
        await self.bot.db.execute("DELETE FROM economy WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(embed=success_embed(f"reset economy for {member.mention}", ctx.author))

    @commands.command(name="balance", aliases=["bal", "wallet"])
    async def balance(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        wallet, bank = await self.get_balance(ctx.guild.id, target.id)
        desc = f"wallet: **${wallet:,}**\nbank: **${bank:,}**\ntotal: **${wallet + bank:,}**"
        await ctx.send(embed=fleed_embed(title=f"{target.display_name.lower()}'s balance", description=desc, author=target))

    @commands.command(name="deposit", aliases=["dep"])
    async def deposit(self, ctx, amount: str):
        wallet, bank = await self.get_balance(ctx.guild.id, ctx.author.id)
        val = wallet if amount.lower() in ["all", "max"] else int(amount)
        if val <= 0 or val > wallet:
            return await ctx.send(embed=error_embed("invalid deposit amount", ctx.author))
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-val, bank_diff=val)
        await ctx.send(embed=success_embed(f"deposited **${val:,}** to bank", ctx.author))

    @commands.command(name="withdraw", aliases=["with"])
    async def withdraw(self, ctx, amount: str):
        wallet, bank = await self.get_balance(ctx.guild.id, ctx.author.id)
        val = bank if amount.lower() in ["all", "max"] else int(amount)
        if val <= 0 or val > bank:
            return await ctx.send(embed=error_embed("invalid withdraw amount", ctx.author))
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=val, bank_diff=-val)
        await ctx.send(embed=success_embed(f"withdrew **${val:,}** from bank", ctx.author))

    @commands.command(name="daily")
    async def daily(self, ctx):
        row = await self.bot.db.fetchrow("SELECT daily_cooldown FROM economy WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        now = int(time.time())
        if row and now - row["daily_cooldown"] < 86400:
            remaining = 86400 - (now - row["daily_cooldown"])
            return await ctx.send(embed=warn_embed(f"daily available in {remaining // 3600}h {(remaining % 3600) // 60}m", ctx.author))
        reward = 500
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=reward)
        await self.bot.db.execute("UPDATE economy SET daily_cooldown = ? WHERE guild_id = ? AND user_id = ?", (now, ctx.guild.id, ctx.author.id))
        await ctx.send(embed=success_embed(f"claimed daily reward of **${reward:,}**", ctx.author))

    @commands.command(name="work")
    async def work(self, ctx, job: str = None):
        row = await self.bot.db.fetchrow("SELECT work_cooldown FROM economy WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        now = int(time.time())
        if row and now - row["work_cooldown"] < 3600:
            remaining = 3600 - (now - row["work_cooldown"])
            return await ctx.send(embed=warn_embed(f"work cooldown active: {remaining // 60}m remaining", ctx.author))
        payout = random.randint(100, 300)
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=payout)
        await self.bot.db.execute("UPDATE economy SET work_cooldown = ? WHERE guild_id = ? AND user_id = ?", (now, ctx.guild.id, ctx.author.id))
        await ctx.send(embed=success_embed(f"you worked and earned **${payout:,}**", ctx.author))

    @commands.command(name="crime")
    async def crime(self, ctx):
        row = await self.bot.db.fetchrow("SELECT crime_cooldown FROM economy WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        now = int(time.time())
        if row and now - row["crime_cooldown"] < 7200:
            remaining = 7200 - (now - row["crime_cooldown"])
            return await ctx.send(embed=warn_embed(f"crime cooldown: {remaining // 60}m left", ctx.author))
        success = random.choice([True, False])
        if success:
            gain = random.randint(250, 750)
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=gain)
            await self.bot.db.execute("UPDATE economy SET crime_cooldown = ? WHERE guild_id = ? AND user_id = ?", (now, ctx.guild.id, ctx.author.id))
            await ctx.send(embed=success_embed(f"crime successful, pocketed **${gain:,}**", ctx.author))
        else:
            fine = random.randint(100, 300)
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-fine)
            await self.bot.db.execute("UPDATE economy SET crime_cooldown = ? WHERE guild_id = ? AND user_id = ?", (now, ctx.guild.id, ctx.author.id))
            await ctx.send(embed=error_embed(f"caught by authorities, paid **${fine:,}** fine", ctx.author))

    @commands.command(name="rob", aliases=["steal"])
    async def rob(self, ctx, member: discord.Member):
        if member.id == ctx.author.id:
            return await ctx.send(embed=error_embed("cannot rob yourself", ctx.author))
        w_target, _ = await self.get_balance(ctx.guild.id, member.id)
        if w_target < 100:
            return await ctx.send(embed=error_embed("target wallet has too little cash", ctx.author))
        success = random.choice([True, False])
        if success:
            stolen = random.randint(50, min(500, w_target))
            await self.update_balance(ctx.guild.id, member.id, wallet_diff=-stolen)
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=stolen)
            await ctx.send(embed=success_embed(f"robbed {member.mention} for **${stolen:,}**", ctx.author))
        else:
            fine = random.randint(50, 200)
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-fine)
            await ctx.send(embed=error_embed(f"robbery failed, lost **${fine:,}**", ctx.author))

    @commands.command(name="transfer", aliases=["pay"])
    async def transfer(self, ctx, member: discord.Member, amount: int):
        if member.id == ctx.author.id or amount <= 0:
            return await ctx.send(embed=error_embed("invalid transfer", ctx.author))
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < amount:
            return await ctx.send(embed=error_embed("insufficient funds", ctx.author))
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
        await self.update_balance(ctx.guild.id, member.id, wallet_diff=amount)
        await ctx.send(embed=success_embed(f"transferred **${amount:,}** to {member.mention}", ctx.author))

    @commands.command(name="give")
    @commands.has_permissions(administrator=True)
    async def give(self, ctx, member: discord.Member, amount: int):
        await self.update_balance(ctx.guild.id, member.id, wallet_diff=amount)
        await ctx.send(embed=success_embed(f"added **${amount:,}** to {member.mention}'s wallet", ctx.author))

    @commands.command(name="take")
    @commands.has_permissions(administrator=True)
    async def take(self, ctx, member: discord.Member, amount: int):
        await self.update_balance(ctx.guild.id, member.id, wallet_diff=-amount)
        await ctx.send(embed=success_embed(f"removed **${amount:,}** from {member.mention}'s wallet", ctx.author))

    @commands.command(name="destroy")
    @commands.has_permissions(administrator=True)
    async def destroy(self, ctx, amount: int):
        if amount <= 0:
            return await ctx.send(embed=error_embed("amount must be positive", ctx.author))
        rows = await self.bot.db.fetch("SELECT user_id, wallet, bank FROM economy WHERE guild_id = ? ORDER BY (wallet + bank) DESC", (ctx.guild.id,))
        remaining = amount
        destroyed = 0
        for row in rows:
            if remaining <= 0:
                break
            available = max(0, row["wallet"]) + max(0, row["bank"])
            if available <= 0:
                continue
            take_wallet = min(max(0, row["wallet"]), remaining)
            take_bank = min(max(0, row["bank"]), remaining - take_wallet)
            await self.bot.db.execute(
                "UPDATE economy SET wallet = wallet - ?, bank = bank - ? WHERE guild_id = ? AND user_id = ?",
                (take_wallet, take_bank, ctx.guild.id, row["user_id"]),
            )
            destroyed += take_wallet + take_bank
            remaining -= take_wallet + take_bank
        await ctx.send(embed=success_embed(f"destroyed **${destroyed:,}** from this server's circulation", ctx.author))

    @commands.command(name="circulation", aliases=["circ"])
    async def circulation(self, ctx):
        row = await self.bot.db.fetchrow("SELECT SUM(wallet + bank) as total FROM economy WHERE guild_id = ?", (ctx.guild.id,))
        total = row["total"] if row and row["total"] else 0
        await ctx.send(embed=fleed_embed(title="economy circulation", description=f"total currency in circulation: **${total:,}**", author=ctx.author))

    # mini-games & gambling
    @commands.command(name="coinflip", aliases=["flip", "cf"])
    async def coinflip(self, ctx, amount: int, side: str):
        side = side.lower()
        if side not in ["heads", "tails", "h", "t"]:
            return await ctx.send(embed=error_embed("choice must be heads or tails", ctx.author))
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet amount", ctx.author))
        chosen = "heads" if side in ["heads", "h"] else "tails"
        outcome = random.choice(["heads", "tails"])
        if chosen == outcome:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=amount)
            await ctx.send(embed=success_embed(f"landed on **{outcome}** — won **${amount:,}**", ctx.author))
        else:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
            await ctx.send(embed=error_embed(f"landed on **{outcome}** — lost **${amount:,}**", ctx.author))

    @commands.command(name="dice", aliases=["roll"])
    async def dice(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet amount", ctx.author))
        bot_roll = random.randint(1, 6)
        user_roll = random.randint(1, 6)
        if user_roll > bot_roll:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=amount)
            await ctx.send(embed=success_embed(f"you rolled {user_roll}, bot rolled {bot_roll} — won **${amount:,}**", ctx.author))
        elif user_roll < bot_roll:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
            await ctx.send(embed=error_embed(f"you rolled {user_roll}, bot rolled {bot_roll} — lost **${amount:,}**", ctx.author))
        else:
            await ctx.send(embed=fleed_embed(description=f"both rolled {user_roll} — tie", author=ctx.author))

    @commands.command(name="gamble", aliases=["bet"])
    async def gamble(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        mult = random.choice([0, 0, 0.5, 1.5, 2.0, 3.0])
        winnings = int(amount * mult) - amount
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=winnings)
        if winnings >= 0:
            await ctx.send(embed=success_embed(f"multiplier {mult}x — won **${int(amount * mult):,}**", ctx.author))
        else:
            await ctx.send(embed=error_embed(f"multiplier {mult}x — lost **${amount:,}**", ctx.author))

    @commands.command(name="slots", aliases=["slot"])
    async def slots(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        symbols = ["seven", "cherry", "bell", "bar", "diamond"]
        s1, s2, s3 = random.choice(symbols), random.choice(symbols), random.choice(symbols)
        if s1 == s2 == s3:
            payout = amount * 5
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=payout)
            await ctx.send(embed=success_embed(f"[{s1} | {s2} | {s3}] — jackpot won **${payout:,}**", ctx.author))
        elif s1 == s2 or s2 == s3 or s1 == s3:
            payout = int(amount * 1.5)
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=payout - amount)
            await ctx.send(embed=success_embed(f"[{s1} | {s2} | {s3}] — 2 matches won **${payout:,}**", ctx.author))
        else:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
            await ctx.send(embed=error_embed(f"[{s1} | {s2} | {s3}] — no matches lost **${amount:,}**", ctx.author))

    @commands.command(name="crash")
    async def crash(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        crash_point = round(random.uniform(1.0, 5.0), 2)
        cashed_out = round(random.uniform(1.1, 3.5), 2)
        if cashed_out < crash_point:
            winnings = int(amount * cashed_out) - amount
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=winnings)
            await ctx.send(embed=success_embed(f"cashed out at {cashed_out}x (crashed at {crash_point}x) — profit **${winnings:,}**", ctx.author))
        else:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
            await ctx.send(embed=error_embed(f"crashed at {crash_point}x before cashout — lost **${amount:,}**", ctx.author))

    @commands.command(name="bombs", aliases=["minesweeper"])
    async def bombs(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        bombs_hit = random.choice([True, False, False])
        if not bombs_hit:
            mult = 2.2
            winnings = int(amount * mult) - amount
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=winnings)
            await ctx.send(embed=success_embed(f"cleared minefield safely — won **${int(amount * mult):,}**", ctx.author))
        else:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
            await ctx.send(embed=error_embed(f"hit a hidden bomb — lost **${amount:,}**", ctx.author))

    @commands.command(name="scratch", aliases=["scratchcard"])
    async def scratch(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        outcome = random.choice([0, 0.5, 1.2, 2.0, 4.0])
        winnings = int(amount * outcome) - amount
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=winnings)
        if winnings >= 0:
            await ctx.send(embed=success_embed(f"scratched {outcome}x card — won **${int(amount * outcome):,}**", ctx.author))
        else:
            await ctx.send(embed=error_embed(f"scratched {outcome}x card — lost **${amount:,}**", ctx.author))

    @commands.command(name="roulette")
    async def roulette(self, ctx, bet_type: str, amount: int):
        bet_type = bet_type.lower()
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        wheel_num = random.randint(0, 36)
        wheel_color = "green" if wheel_num == 0 else ("red" if wheel_num % 2 == 1 else "black")
        is_even = wheel_num != 0 and wheel_num % 2 == 0
        is_odd = wheel_num % 2 == 1

        won = False
        payout_mult = 2
        if bet_type in ["red", "black"] and bet_type == wheel_color:
            won = True
        elif bet_type == "green" and wheel_color == "green":
            won = True
            payout_mult = 14
        elif bet_type == "even" and is_even:
            won = True
        elif bet_type == "odd" and is_odd:
            won = True

        if won:
            profit = (amount * payout_mult) - amount
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=profit)
            await ctx.send(embed=success_embed(f"ball landed on **{wheel_num} ({wheel_color})** — won **${amount * payout_mult:,}**", ctx.author))
        else:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
            await ctx.send(embed=error_embed(f"ball landed on **{wheel_num} ({wheel_color})** — lost **${amount:,}**", ctx.author))

    @commands.command(name="plinko")
    async def plinko(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        mult = random.choice([0.2, 0.5, 1.0, 1.5, 2.5, 5.0])
        winnings = int(amount * mult) - amount
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=winnings)
        if winnings >= 0:
            await ctx.send(embed=success_embed(f"chip landed in {mult}x slot — won **${int(amount * mult):,}**", ctx.author))
        else:
            await ctx.send(embed=error_embed(f"chip landed in {mult}x slot — lost **${amount:,}**", ctx.author))

    @commands.command(name="highlow", aliases=["hl"])
    async def highlow(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        base_card = random.randint(2, 10)
        next_card = random.randint(1, 13)
        won = random.choice([True, False])
        if won:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=amount)
            await ctx.send(embed=success_embed(f"current card: {base_card} -> next card: {next_card} — correct guess won **${amount:,}**", ctx.author))
        else:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
            await ctx.send(embed=error_embed(f"current card: {base_card} -> next card: {next_card} — incorrect guess lost **${amount:,}**", ctx.author))

    @commands.command(name="ladder", aliases=["climb"])
    async def ladder(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet", ctx.author))
        steps = random.randint(0, 5)
        multipliers = [0, 1.2, 1.8, 2.5, 4.0, 7.5]
        mult = multipliers[steps]
        if mult > 1.0:
            winnings = int(amount * mult) - amount
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=winnings)
            await ctx.send(embed=success_embed(f"climbed {steps} rungs ({mult}x) — won **${int(amount * mult):,}**", ctx.author))
        else:
            await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-amount)
            await ctx.send(embed=error_embed(f"fell off ladder at step {steps} — lost **${amount:,}**", ctx.author))

    @commands.command(name="blackjack", aliases=["bj"])
    async def blackjack(self, ctx, amount: int):
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if amount <= 0 or amount > wallet:
            return await ctx.send(embed=error_embed("invalid bet amount", ctx.author))
        view = BlackjackGameView(self, ctx, amount)
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(name="open")
    async def open_box(self, ctx):
        row = await self.bot.db.fetchrow("SELECT last_open FROM economy WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        now = int(time.time())
        last = int(row["last_open"] or 0) if row and "last_open" in row.keys() else 0
        if now - last < 3600:
            return await ctx.send(embed=warn_embed(f"you can open another crate <t:{last + 3600}:R>", ctx.author))
        reward = random.randint(75, 600)
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=reward)
        await self.bot.db.execute("UPDATE economy SET last_open = ? WHERE guild_id = ? AND user_id = ?", (now, ctx.guild.id, ctx.author.id))
        await ctx.send(embed=fleed_embed(description=f"opened a mystery crate and found **${reward:,}**", author=ctx.author))

    # shop & jobs
    @commands.hybrid_group(name="job", aliases=["jobs"], invoke_without_command=True)
    async def job(self, ctx):
        rows = await self.bot.db.fetch("SELECT name, min_payout, max_payout, description FROM economy_jobs WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=fleed_embed(title="available jobs", description="no custom jobs configured for this server yet", author=ctx.author))
        lines = [f"**{r['name']}** (${r['min_payout']:,}-${r['max_payout']:,})\n{r['description']}" for r in rows]
        await ctx.send(embed=fleed_embed(title="available jobs", description="\n\n".join(lines), author=ctx.author))

    @job.command(name="add", aliases=["create"])
    @commands.has_permissions(manage_guild=True)
    async def job_add(self, ctx, name: str, min_payout: int, max_payout: int, *, description: str = "no description"):
        await self.bot.db.execute("INSERT OR REPLACE INTO economy_jobs (guild_id, name, min_payout, max_payout, description) VALUES (?, ?, ?, ?, ?)", (ctx.guild.id, name.lower(), min_payout, max_payout, description))
        await ctx.send(embed=success_embed(f"created job `{name.lower()}` paying ${min_payout}-${max_payout}", ctx.author))

    @job.command(name="remove", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def job_remove(self, ctx, name: str):
        await self.bot.db.execute("DELETE FROM economy_jobs WHERE guild_id = ? AND name = ?", (ctx.guild.id, name.lower()))
        await ctx.send(embed=success_embed(f"removed job `{name.lower()}`", ctx.author))

    @commands.hybrid_group(name="shop", invoke_without_command=True)
    async def shop(self, ctx):
        rows = await self.bot.db.fetch("SELECT name, price, role_id, description FROM economy_shop WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=fleed_embed(description="server shop is currently empty", author=ctx.author))
        lines = [f"**{r['name']}** — ${r['price']:,}\n{r['description']}" for r in rows]
        await ctx.send(embed=fleed_embed(title="server shop", description="\n\n".join(lines), author=ctx.author))

    @shop.command(name="add", aliases=["create"])
    @commands.has_permissions(manage_guild=True)
    async def shop_add(self, ctx, name: str, price: int, role: discord.Role = None, *, description: str = "none"):
        role_id = role.id if role else 0
        await self.bot.db.execute("INSERT OR REPLACE INTO economy_shop (guild_id, name, price, role_id, description) VALUES (?, ?, ?, ?, ?)", (ctx.guild.id, name.lower(), price, role_id, description))
        await ctx.send(embed=success_embed(f"added item `{name.lower()}` to shop for **${price:,}**", ctx.author))

    @shop.command(name="remove", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def shop_remove(self, ctx, name: str):
        await self.bot.db.execute("DELETE FROM economy_shop WHERE guild_id = ? AND name = ?", (ctx.guild.id, name.lower()))
        await ctx.send(embed=success_embed(f"removed `{name.lower()}` from shop", ctx.author))

    @shop.command(name="buy", aliases=["purchase"])
    async def shop_buy(self, ctx, *, item_name: str):
        row = await self.bot.db.fetchrow("SELECT price, role_id FROM economy_shop WHERE guild_id = ? AND name = ?", (ctx.guild.id, item_name.lower()))
        if not row:
            return await ctx.send(embed=error_embed("item not found in shop", ctx.author))
        wallet, _ = await self.get_balance(ctx.guild.id, ctx.author.id)
        if wallet < row["price"]:
            return await ctx.send(embed=error_embed("insufficient funds in wallet", ctx.author))
        await self.update_balance(ctx.guild.id, ctx.author.id, wallet_diff=-row["price"])
        if row["role_id"] != 0:
            r = ctx.guild.get_role(row["role_id"])
            if r:
                try:
                    await ctx.author.add_roles(r)
                except Exception:
                    pass
        await ctx.send(embed=success_embed(f"purchased `{item_name.lower()}` for **${row['price']:,}**", ctx.author))

async def setup(bot):
    await bot.add_cog(Economy(bot))
