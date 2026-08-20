import discord
from discord.ext import commands
import random
import time
import aiohttp
import urllib.parse
import html
import os
import asyncio
from collections import defaultdict
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help

WORDS_SET = set()
VALID_SYLLABLES = []

def load_wordlist():
    global WORDS_SET, VALID_SYLLABLES
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    words_path = os.path.join(base_dir, "data", "words.txt")
    if not os.path.exists(words_path):
        words_path = os.path.join("data", "words.txt")

    if os.path.exists(words_path):
        try:
            with open(words_path, "r", encoding="utf-8") as f:
                WORDS_SET = {line.strip().lower() for line in f if len(line.strip()) >= 2 and line.strip().isalpha()}
        except Exception:
            pass

    if not WORDS_SET:
        WORDS_SET = {"string", "strong", "destroy", "queen", "quick", "quiet", "player", "programming", "blacktea", "apple", "banana", "bottle", "window", "message", "channel"}

    syllables = defaultdict(int)
    for w in WORDS_SET:
        if len(w) >= 3:
            for i in range(len(w) - 1):
                syllables[w[i:i+2]] += 1
            for i in range(len(w) - 2):
                syllables[w[i:i+3]] += 1

    VALID_SYLLABLES = [s.upper() for s, count in syllables.items() if count >= 20 and len(s) in (2, 3)]
    if not VALID_SYLLABLES:
        VALID_SYLLABLES = ["STR", "QUA", "ING", "PRO", "EX", "CON", "DIS", "RE", "TE", "AN", "ER", "IN", "ST", "SH", "CH", "TH"]

load_wordlist()

class BlackTeaLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member):
        super().__init__(timeout=45)
        self.host = host
        self.players = [host]
        self.started = False
        self.cancelled = False

    def build_embed(self) -> discord.Embed:
        lines = [f"`{i+1}.` {p.mention}" for i, p in enumerate(self.players)]
        desc = (
            f"**host:** {self.host.mention}\n"
            f"**players ({len(self.players)}/10):**\n" + "\n".join(lines) + "\n\n"
            "*click `join` to enter the match. host can click `start` to begin!*"
        )
        return fleed_embed(title="blacktea lobby", description=desc, author=self.host)

    @discord.ui.button(label="join", style=discord.ButtonStyle.secondary)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            if interaction.user.id == self.host.id:
                return await interaction.response.send_message("host cannot leave the lobby (use cancel to abort)", ephemeral=True)
            self.players.remove(interaction.user)
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        else:
            if len(self.players) >= 10:
                return await interaction.response.send_message("lobby is full (max 10 players)", ephemeral=True)
            self.players.append(interaction.user)
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="start", style=discord.ButtonStyle.success)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("only the host can start the game", ephemeral=True)
        self.started = True
        self.stop()

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("only the host can cancel the game", ephemeral=True)
        self.cancelled = True
        self.stop()

class TriviaButtonView(discord.ui.View):
    def __init__(self, author_id: int, correct_answer: str, options: list):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.correct_answer = correct_answer

        for opt in options:
            btn = discord.ui.Button(label=opt[:80].lower(), style=discord.ButtonStyle.secondary)
            btn.callback = self.make_callback(opt)
            self.add_item(btn)

    def make_callback(self, chosen: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message("this is not your trivia game", ephemeral=True)
            for child in self.children:
                child.disabled = True
                if child.label == self.correct_answer.lower():
                    child.style = discord.ButtonStyle.success
                elif child.label == chosen.lower():
                    child.style = discord.ButtonStyle.danger

            if chosen.lower() == self.correct_answer.lower():
                await interaction.response.edit_message(content=f"correct — answer was **{self.correct_answer.lower()}**", view=self)
            else:
                await interaction.response.edit_message(content=f"incorrect — correct answer was **{self.correct_answer.lower()}**", view=self)
            self.stop()
        return callback

MONOPOLY_BOARD = [
    {"name": "go", "type": "go", "cost": 0, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "mediterranean ave", "type": "property", "cost": 60, "rent": 10, "group": "brown", "upgrade_cost": 50, "upgrade_rent": [25, 50, 100]},
    {"name": "community chest", "type": "chest", "cost": 0, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "baltic ave", "type": "property", "cost": 60, "rent": 10, "group": "brown", "upgrade_cost": 50, "upgrade_rent": [25, 50, 100]},
    {"name": "income tax", "type": "tax", "cost": 100, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "reading railroad", "type": "railroad", "cost": 200, "rent": 25, "group": "railroad", "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "oriental ave", "type": "property", "cost": 100, "rent": 15, "group": "lightblue", "upgrade_cost": 50, "upgrade_rent": [35, 70, 140]},
    {"name": "chance", "type": "chance", "cost": 0, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "connecticut ave", "type": "property", "cost": 120, "rent": 20, "group": "lightblue", "upgrade_cost": 50, "upgrade_rent": [45, 90, 180]},
    {"name": "jail", "type": "jail", "cost": 0, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "st charles place", "type": "property", "cost": 140, "rent": 25, "group": "pink", "upgrade_cost": 100, "upgrade_rent": [55, 110, 220]},
    {"name": "electric company", "type": "utility", "cost": 150, "rent": 30, "group": "utility", "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "states ave", "type": "property", "cost": 140, "rent": 25, "group": "pink", "upgrade_cost": 100, "upgrade_rent": [55, 110, 220]},
    {"name": "pennsylvania railroad", "type": "railroad", "cost": 200, "rent": 25, "group": "railroad", "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "st james place", "type": "property", "cost": 180, "rent": 35, "group": "orange", "upgrade_cost": 100, "upgrade_rent": [75, 150, 300]},
    {"name": "community chest", "type": "chest", "cost": 0, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "new york ave", "type": "property", "cost": 200, "rent": 40, "group": "orange", "upgrade_cost": 100, "upgrade_rent": [85, 170, 340]},
    {"name": "free parking", "type": "parking", "cost": 0, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "kentucky ave", "type": "property", "cost": 220, "rent": 45, "group": "red", "upgrade_cost": 150, "upgrade_rent": [95, 190, 380]},
    {"name": "chance", "type": "chance", "cost": 0, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "illinois ave", "type": "property", "cost": 240, "rent": 50, "group": "red", "upgrade_cost": 150, "upgrade_rent": [105, 210, 420]},
    {"name": "go to jail", "type": "go_to_jail", "cost": 0, "rent": 0, "group": None, "upgrade_cost": 0, "upgrade_rent": []},
    {"name": "park place", "type": "property", "cost": 350, "rent": 75, "group": "darkblue", "upgrade_cost": 200, "upgrade_rent": [150, 300, 600]},
    {"name": "boardwalk", "type": "property", "cost": 400, "rent": 100, "group": "darkblue", "upgrade_cost": 200, "upgrade_rent": [200, 400, 800]}
]

MONOPOLY_GROUPS = {
    "brown": [1, 3],
    "lightblue": [6, 8],
    "pink": [10, 12],
    "orange": [14, 16],
    "red": [18, 20],
    "darkblue": [22, 23],
    "railroad": [5, 13],
    "utility": [11]
}

MONOPOLY_CHANCE = [
    {"text": "advance to go collect 200 cash", "type": "goto", "pos": 0, "collect": 200},
    {"text": "speeding fine pay 50 cash", "type": "pay", "amount": 50},
    {"text": "bank dividend collect 100 cash", "type": "gain", "amount": 100},
    {"text": "go directly to jail do not pass go", "type": "jail"},
    {"text": "building loan matures collect 150 cash", "type": "gain", "amount": 150},
    {"text": "pay hospital bill of 100 cash", "type": "pay", "amount": 100},
    {"text": "lottery win collect 200 cash", "type": "gain", "amount": 200},
    {"text": "advance to boardwalk", "type": "goto", "pos": 23, "collect": 0}
]

MONOPOLY_CHEST = [
    {"text": "doctor fee pay 50 cash", "type": "pay", "amount": 50},
    {"text": "inheritance collect 100 cash", "type": "gain", "amount": 100},
    {"text": "tax refund collect 50 cash", "type": "gain", "amount": 50},
    {"text": "school fees pay 50 cash", "type": "pay", "amount": 50},
    {"text": "holiday fund matures collect 100 cash", "type": "gain", "amount": 100},
    {"text": "beauty contest prize collect 25 cash", "type": "gain", "amount": 25},
    {"text": "street repair costs pay 75 cash", "type": "pay", "amount": 75},
    {"text": "consultancy fee collect 50 cash", "type": "gain", "amount": 50}
]

class MonopolyPlayer:
    def __init__(self, member: discord.Member):
        self.member = member
        self.cash = 1000
        self.pos = 0
        self.in_jail = False
        self.jail_turns = 0
        self.bankrupt = False
        self.properties = []

    @property
    def name(self) -> str:
        return self.member.display_name.lower()

    @property
    def mention(self) -> str:
        return self.member.mention

class MonopolyLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member):
        super().__init__(timeout=60)
        self.host = host
        self.players = [host]
        self.started = False
        self.cancelled = False

    def build_embed(self) -> discord.Embed:
        lines = [f"`{i+1}.` {p.display_name.lower()}" for i, p in enumerate(self.players)]
        desc = (
            f"host: {self.host.display_name.lower()}\n"
            f"players ({len(self.players)}/4):\n" + "\n".join(lines) +
            "\n\nclick join to enter lobby host can start with 2 to 4 players"
        )
        return fleed_embed(title="monopoly lobby", description=desc, author=self.host)

    @discord.ui.button(label="join", style=discord.ButtonStyle.secondary)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            return await interaction.response.send_message("you are already in the lobby", ephemeral=True)
        if len(self.players) >= 4:
            return await interaction.response.send_message("lobby is full max 4 players", ephemeral=True)
        self.players.append(interaction.user)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="leave", style=discord.ButtonStyle.secondary)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in self.players:
            return await interaction.response.send_message("you are not in the lobby", ephemeral=True)
        if interaction.user.id == self.host.id:
            return await interaction.response.send_message("host cannot leave use cancel to abort", ephemeral=True)
        self.players.remove(interaction.user)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="start", style=discord.ButtonStyle.success)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("only the host can start the game", ephemeral=True)
        if len(self.players) < 2:
            return await interaction.response.send_message("need at least 2 players to start monopoly", ephemeral=True)
        self.started = True
        self.stop()

    @discord.ui.button(label="cancel", style=discord.ButtonStyle.danger)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("only the host can cancel the game", ephemeral=True)
        self.cancelled = True
        self.stop()

class MonopolyGameView(discord.ui.View):
    def __init__(self, players: list[discord.Member]):
        super().__init__(timeout=90)
        self.players = [MonopolyPlayer(p) for p in players]
        self.turn_idx = 0
        self.round_num = 1
        self.owners = {}
        self.upgrades = {}
        self.stage = "pre_roll"
        self.pending_tile = None
        self.last_action = "game started first player roll the dice"
        self.doubles_count = 0
        self.rolled_doubles = False
        self.game_over = False
        self.winner = None
        self.message = None
        self.refresh_buttons()

    @property
    def current(self) -> MonopolyPlayer:
        return self.players[self.turn_idx]

    def get_rent(self, tile_idx: int) -> int:
        tile = MONOPOLY_BOARD[tile_idx]
        owner_id = self.owners.get(tile_idx)
        if owner_id is None:
            return 0
        group = tile.get("group")
        if not group:
            return tile.get("rent", 0)
        lvl = self.upgrades.get(tile_idx, 0)
        if lvl > 0 and tile.get("upgrade_rent"):
            return tile["upgrade_rent"][min(lvl - 1, len(tile["upgrade_rent"]) - 1)]
        group_tiles = MONOPOLY_GROUPS.get(group, [])
        owns_all = all(self.owners.get(t) == owner_id for t in group_tiles)
        if group == "railroad":
            return 50 if owns_all else 25
        elif group == "utility":
            return tile.get("rent", 30)
        else:
            base = tile.get("rent", 10)
            return base * 2 if owns_all else base

    def get_upgradeable_properties(self, player: MonopolyPlayer) -> list[int]:
        upgradeable = []
        for group, tiles in MONOPOLY_GROUPS.items():
            if group in ("railroad", "utility"):
                continue
            if all(self.owners.get(t) == player.member.id for t in tiles):
                for t in tiles:
                    lvl = self.upgrades.get(t, 0)
                    cost = MONOPOLY_BOARD[t]["upgrade_cost"]
                    if lvl < 3 and player.cash >= cost:
                        upgradeable.append(t)
        return upgradeable

    def cleanup_bankrupt(self, player: MonopolyPlayer):
        to_del = [t for t, pid in self.owners.items() if pid == player.member.id]
        for t in to_del:
            del self.owners[t]
            self.upgrades.pop(t, None)
        player.properties.clear()

    def check_win(self):
        active = [p for p in self.players if not p.bankrupt]
        if len(active) <= 1:
            self.game_over = True
            self.winner = active[0] if active else None
            self.stop()

    def build_embed(self) -> discord.Embed:
        if self.game_over and self.winner:
            desc = (
                f"game over\n"
                f"winner is {self.winner.name} with {self.winner.cash} cash\n\n"
                f"last action:\n{self.last_action}"
            )
            return fleed_embed(title="monopoly winner", description=desc, author=self.winner.member)

        cur = self.current
        tile_now = MONOPOLY_BOARD[cur.pos]
        tile_name = tile_now["name"]

        standings = []
        for p in self.players:
            if p.bankrupt:
                standings.append(f"`{p.name}` bankrupt")
            else:
                props = len(p.properties)
                jail_str = " (in jail)" if p.in_jail else ""
                standings.append(f"`{p.name}` {p.cash} cash | tile {p.pos+1} {MONOPOLY_BOARD[p.pos]['name']}{jail_str} | {props} properties")

        desc = (
            f"turn {self.round_num} — {cur.mention}'s turn\n"
            f"cash: {cur.cash} | tile: {tile_name} ({cur.pos+1}/24)\n\n"
            f"players:\n" + "\n".join(standings) + "\n\n"
            f"last action:\n{self.last_action}"
        )
        return fleed_embed(title="monopoly", description=desc, author=cur.member)

    def refresh_buttons(self):
        self.clear_items()
        cur = self.current

        if self.game_over:
            return

        if self.stage == "pre_roll":
            if cur.in_jail:
                pay_btn = discord.ui.Button(label="pay 50 fine", style=discord.ButtonStyle.primary, disabled=(cur.cash < 50))
                pay_btn.callback = self.pay_fine_callback
                self.add_item(pay_btn)

                roll_jail_btn = discord.ui.Button(label="roll doubles", style=discord.ButtonStyle.secondary)
                roll_jail_btn.callback = self.roll_jail_callback
                self.add_item(roll_jail_btn)
            else:
                roll_btn = discord.ui.Button(label="roll dice", style=discord.ButtonStyle.primary)
                roll_btn.callback = self.roll_dice_callback
                self.add_item(roll_btn)

            props_btn = discord.ui.Button(label="my properties", style=discord.ButtonStyle.secondary)
            props_btn.callback = self.props_callback
            self.add_item(props_btn)

            forfeit_btn = discord.ui.Button(label="forfeit", style=discord.ButtonStyle.danger)
            forfeit_btn.callback = self.forfeit_callback
            self.add_item(forfeit_btn)

        elif self.stage == "landed_unowned":
            tile = MONOPOLY_BOARD[self.pending_tile]
            can_buy = cur.cash >= tile["cost"]
            buy_btn = discord.ui.Button(label=f"buy for {tile['cost']}", style=discord.ButtonStyle.success, disabled=not can_buy)
            buy_btn.callback = self.buy_callback
            self.add_item(buy_btn)

            pass_btn = discord.ui.Button(label="pass", style=discord.ButtonStyle.secondary)
            pass_btn.callback = self.pass_callback
            self.add_item(pass_btn)

            props_btn = discord.ui.Button(label="my properties", style=discord.ButtonStyle.secondary)
            props_btn.callback = self.props_callback
            self.add_item(props_btn)

            forfeit_btn = discord.ui.Button(label="forfeit", style=discord.ButtonStyle.danger)
            forfeit_btn.callback = self.forfeit_callback
            self.add_item(forfeit_btn)

        elif self.stage == "post_roll":
            upgradeables = self.get_upgradeable_properties(cur)
            if upgradeables:
                first_t = upgradeables[0]
                cost = MONOPOLY_BOARD[first_t]["upgrade_cost"]
                up_btn = discord.ui.Button(label=f"upgrade {MONOPOLY_BOARD[first_t]['name']} ({cost})", style=discord.ButtonStyle.success)
                up_btn.callback = self.upgrade_callback
                self.add_item(up_btn)

            end_label = "roll again" if (self.rolled_doubles and not cur.in_jail and not cur.bankrupt) else "end turn"
            end_btn = discord.ui.Button(label=end_label, style=discord.ButtonStyle.primary)
            end_btn.callback = self.end_turn_callback
            self.add_item(end_btn)

            props_btn = discord.ui.Button(label="my properties", style=discord.ButtonStyle.secondary)
            props_btn.callback = self.props_callback
            self.add_item(props_btn)

            forfeit_btn = discord.ui.Button(label="forfeit", style=discord.ButtonStyle.danger)
            forfeit_btn.callback = self.forfeit_callback
            self.add_item(forfeit_btn)

    async def roll_dice_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.current.member.id:
            return await interaction.response.send_message("this is not your turn", ephemeral=True)

        cur = self.current
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        is_doubles = (d1 == d2)
        self.rolled_doubles = is_doubles

        if is_doubles:
            self.doubles_count += 1
        else:
            self.doubles_count = 0

        if self.doubles_count >= 3:
            cur.pos = 9
            cur.in_jail = True
            self.doubles_count = 0
            self.rolled_doubles = False
            self.stage = "post_roll"
            self.last_action = f"{cur.name} rolled 3 doubles in a row and got sent to jail"
            self.refresh_buttons()
            return await interaction.response.edit_message(embed=self.build_embed(), view=self)

        old_pos = cur.pos
        new_pos = (old_pos + d1 + d2) % 24
        passed_go = (new_pos < old_pos)
        if passed_go:
            cur.cash += 200

        cur.pos = new_pos
        tile = MONOPOLY_BOARD[new_pos]
        pass_go_str = " passed go +200 cash and" if passed_go else ""

        if tile["type"] in ("property", "railroad", "utility"):
            if new_pos not in self.owners:
                self.stage = "landed_unowned"
                self.pending_tile = new_pos
                self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} landed on unowned {tile['name']} price {tile['cost']}"
            elif self.owners[new_pos] == cur.member.id:
                self.stage = "post_roll"
                self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} landed on own property {tile['name']}"
            else:
                owner = next((p for p in self.players if p.member.id == self.owners[new_pos]), None)
                rent = self.get_rent(new_pos)
                cur.cash -= rent
                if owner:
                    owner.cash += rent
                if cur.cash < 0:
                    cur.bankrupt = True
                    self.cleanup_bankrupt(cur)
                    self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} landed on {tile['name']} paid {rent} rent to {owner.name if owner else 'bank'} and went bankrupt"
                    self.check_win()
                else:
                    self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} landed on {tile['name']} and paid {rent} rent to {owner.name if owner else 'bank'}"
                self.stage = "post_roll"

        elif tile["type"] == "go":
            cur.cash += 200
            self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}) landed on go and collected 200 cash"
            self.stage = "post_roll"

        elif tile["type"] == "tax":
            cur.cash -= tile["cost"]
            if cur.cash < 0:
                cur.bankrupt = True
                self.cleanup_bankrupt(cur)
                self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} landed on income tax paid {tile['cost']} and went bankrupt"
                self.check_win()
            else:
                self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} landed on income tax and paid {tile['cost']} cash"
            self.stage = "post_roll"

        elif tile["type"] == "chance":
            card = random.choice(MONOPOLY_CHANCE)
            self.apply_card(cur, card, "chance", d1, d2, pass_go_str)
            self.stage = "post_roll"

        elif tile["type"] == "chest":
            card = random.choice(MONOPOLY_CHEST)
            self.apply_card(cur, card, "community chest", d1, d2, pass_go_str)
            self.stage = "post_roll"

        elif tile["type"] == "go_to_jail":
            cur.pos = 9
            cur.in_jail = True
            self.doubles_count = 0
            self.rolled_doubles = False
            self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}) landed on go to jail and went straight to jail"
            self.stage = "post_roll"

        elif tile["type"] in ("jail", "parking"):
            self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} landed on {tile['name']} safe"
            self.stage = "post_roll"

        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    def apply_card(self, cur: MonopolyPlayer, card: dict, deck_name: str, d1: int, d2: int, pass_go_str: str):
        if card["type"] == "gain":
            cur.cash += card["amount"]
            self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} drew {deck_name}: {card['text']}"
        elif card["type"] == "pay":
            cur.cash -= card["amount"]
            if cur.cash < 0:
                cur.bankrupt = True
                self.cleanup_bankrupt(cur)
                self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} drew {deck_name}: {card['text']} and went bankrupt"
                self.check_win()
            else:
                self.last_action = f"{cur.name} rolled {d1} and {d2} ({d1+d2}){pass_go_str} drew {deck_name}: {card['text']}"
        elif card["type"] == "jail":
            cur.pos = 9
            cur.in_jail = True
            self.doubles_count = 0
            self.rolled_doubles = False
            self.last_action = f"{cur.name} drew {deck_name}: {card['text']} and was sent to jail"
        elif card["type"] == "goto":
            cur.pos = card["pos"]
            if card.get("collect", 0) > 0:
                cur.cash += card["collect"]
            self.last_action = f"{cur.name} drew {deck_name}: {card['text']} and moved to {MONOPOLY_BOARD[cur.pos]['name']}"

    async def buy_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.current.member.id:
            return await interaction.response.send_message("this is not your turn", ephemeral=True)
        cur = self.current
        tile = MONOPOLY_BOARD[self.pending_tile]
        if cur.cash >= tile["cost"]:
            cur.cash -= tile["cost"]
            self.owners[self.pending_tile] = cur.member.id
            cur.properties.append(self.pending_tile)
            self.last_action = f"{cur.name} bought {tile['name']} for {tile['cost']} cash"
        self.stage = "post_roll"
        self.pending_tile = None
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def pass_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.current.member.id:
            return await interaction.response.send_message("this is not your turn", ephemeral=True)
        cur = self.current
        tile = MONOPOLY_BOARD[self.pending_tile]
        self.last_action = f"{cur.name} passed on buying {tile['name']}"
        self.stage = "post_roll"
        self.pending_tile = None
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def upgrade_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.current.member.id:
            return await interaction.response.send_message("this is not your turn", ephemeral=True)
        cur = self.current
        upgradeables = self.get_upgradeable_properties(cur)
        if upgradeables:
            t = upgradeables[0]
            cost = MONOPOLY_BOARD[t]["upgrade_cost"]
            cur.cash -= cost
            self.upgrades[t] = self.upgrades.get(t, 0) + 1
            lvl = self.upgrades[t]
            new_rent = self.get_rent(t)
            self.last_action = f"{cur.name} upgraded {MONOPOLY_BOARD[t]['name']} to level {lvl} new rent is {new_rent}"
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def end_turn_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.current.member.id:
            return await interaction.response.send_message("this is not your turn", ephemeral=True)
        cur = self.current
        if self.rolled_doubles and not cur.in_jail and not cur.bankrupt:
            self.stage = "pre_roll"
            self.rolled_doubles = False
            self.last_action = f"{cur.name} rolled doubles and gets to roll again"
        else:
            self.doubles_count = 0
            self.rolled_doubles = False
            self.stage = "pre_roll"

            next_turn = (self.turn_idx + 1) % len(self.players)
            if next_turn == 0:
                self.round_num += 1
            self.turn_idx = next_turn
            while self.players[self.turn_idx].bankrupt:
                self.turn_idx = (self.turn_idx + 1) % len(self.players)

            self.check_win()
            if not self.game_over:
                next_p = self.current
                if next_p.in_jail:
                    next_p.jail_turns += 1
                    if next_p.jail_turns > 3:
                        if next_p.cash >= 50:
                            next_p.cash -= 50
                            next_p.in_jail = False
                            next_p.jail_turns = 0
                            self.last_action = f"{next_p.name} served 3 turns in jail paid 50 fine and is released"
                        else:
                            next_p.bankrupt = True
                            self.cleanup_bankrupt(next_p)
                            self.last_action = f"{next_p.name} could not pay jail fine and went bankrupt"
                            self.check_win()

        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def pay_fine_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.current.member.id:
            return await interaction.response.send_message("this is not your turn", ephemeral=True)
        cur = self.current
        if cur.cash >= 50:
            cur.cash -= 50
            cur.in_jail = False
            cur.jail_turns = 0
            self.last_action = f"{cur.name} paid 50 jail fine and is free to roll"
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def roll_jail_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.current.member.id:
            return await interaction.response.send_message("this is not your turn", ephemeral=True)
        cur = self.current
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        if d1 == d2:
            cur.in_jail = False
            cur.jail_turns = 0
            cur.pos = (cur.pos + d1 + d2) % 24
            self.last_action = f"{cur.name} rolled doubles {d1} and {d2} broke out of jail and moved to {MONOPOLY_BOARD[cur.pos]['name']}"
            self.stage = "post_roll"
        else:
            self.last_action = f"{cur.name} rolled {d1} and {d2} failed to roll doubles and stays in jail"
            self.stage = "post_roll"
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def forfeit_callback(self, interaction: discord.Interaction):
        player = next((p for p in self.players if p.member.id == interaction.user.id), None)
        if not player or player.bankrupt:
            return await interaction.response.send_message("you cannot forfeit right now", ephemeral=True)

        player.bankrupt = True
        self.cleanup_bankrupt(player)
        self.last_action = f"{player.name} forfeited and left the game"
        self.check_win()

        if not self.game_over and self.current.bankrupt:
            self.turn_idx = (self.turn_idx + 1) % len(self.players)
            while self.players[self.turn_idx].bankrupt:
                self.turn_idx = (self.turn_idx + 1) % len(self.players)
            self.stage = "pre_roll"

        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def props_callback(self, interaction: discord.Interaction):
        player = next((p for p in self.players if p.member.id == interaction.user.id), None)
        if not player:
            return await interaction.response.send_message("you are not in this game", ephemeral=True)
        if not player.properties:
            return await interaction.response.send_message(f"you do not own any properties cash: {player.cash}", ephemeral=True)

        lines = []
        total_val = player.cash
        for t in player.properties:
            tile = MONOPOLY_BOARD[t]
            lvl = self.upgrades.get(t, 0)
            rent = self.get_rent(t)
            lvl_str = f"level {lvl}" if lvl > 0 else "base"
            total_val += tile["cost"] + (lvl * tile["upgrade_cost"])
            lines.append(f"tile {t+1} {tile['name']} ({tile['group']}) | {lvl_str} | rent {rent} | cost {tile['cost']}")

        desc = (
            f"properties for {player.name}:\n" + "\n".join(lines) +
            f"\n\ncash: {player.cash} | total net worth: {total_val}"
        )
        await interaction.response.send_message(desc, ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                embed = fleed_embed(title="monopoly", description="game timed out due to inactivity", author=self.current.member)
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

class BasketballPlayer:
    def __init__(self, member: discord.Member):
        self.member = member
        self.score = 0
        self.fgm = 0
        self.fga = 0
        self.threes_made = 0
        self.threes_att = 0
        self.dunks = 0
        self.blocks = 0
        self.steals = 0
        self.ankles_broken = 0
        self.streak = 0
        self.on_fire = False

    @property
    def name(self) -> str:
        return self.member.display_name.lower()

    @property
    def mention(self) -> str:
        return self.member.mention

class Basketball1v1GameView(discord.ui.View):
    def __init__(self, p1: discord.Member, p2: discord.Member):
        super().__init__(timeout=60)
        self.p1 = BasketballPlayer(p1)
        self.p2 = BasketballPlayer(p2)
        self.players = [self.p1, self.p2]
        self.possession_idx = random.choice([0, 1])
        self.phase = "offense"
        self.pending_offense_move = None
        self.game_over = False
        self.winner = None
        self.last_play_log = f"coin toss won by **{self.players[self.possession_idx].name}** — starting with the ball!"
        self.message = None
        self.refresh_buttons()

    @property
    def offense_player(self) -> BasketballPlayer:
        return self.players[self.possession_idx]

    @property
    def defense_player(self) -> BasketballPlayer:
        return self.players[1 - self.possession_idx]

    def switch_possession(self):
        self.possession_idx = 1 - self.possession_idx

    def check_win(self):
        p1 = self.p1
        p2 = self.p2
        if p1.score >= 11 and (p1.score - p2.score >= 2 or p1.score >= 15):
            self.game_over = True
            self.winner = p1
            self.stop()
        elif p2.score >= 11 and (p2.score - p1.score >= 2 or p2.score >= 15):
            self.game_over = True
            self.winner = p2
            self.stop()

    def build_embed(self) -> discord.Embed:
        p1 = self.p1
        p2 = self.p2
        off = self.offense_player
        deff = self.defense_player

        if self.game_over and self.winner:
            loser = p2 if self.winner.member.id == p1.member.id else p1
            desc = (
                f"**{self.winner.name} won the 1v1 match!**\n\n"
                f"**final score:** {p1.name} **{p1.score}** — **{p2.score}** {p2.name}\n\n"
                f"**box score:**\n"
                f"**{self.winner.name}:** {self.winner.score} pts | {self.winner.fgm}/{self.winner.fga} FG | {self.winner.threes_made} 3PM | {self.winner.dunks} dunks | {self.winner.blocks} blk | {self.winner.steals} stl | {self.winner.ankles_broken} ankle breakers\n"
                f"**{loser.name}:** {loser.score} pts | {loser.fgm}/{loser.fga} FG | {loser.threes_made} 3PM | {loser.dunks} dunks | {loser.blocks} blk | {loser.steals} stl | {loser.ankles_broken} ankle breakers\n\n"
                f"**game winner:**\n{self.last_play_log}"
            )
            return fleed_embed(title="1v1 basketball match — final", description=desc, author=self.winner.member)

        p1_fire = " (on fire)" if p1.on_fire else ""
        p2_fire = " (on fire)" if p2.on_fire else ""

        p1_poss = "> " if self.possession_idx == 0 else ""
        p2_poss = "> " if self.possession_idx == 1 else ""

        scoreboard = (
            f"**{p1_poss}{p1.name}** (`{p1.score}`){p1_fire}  vs  **{p2_poss}{p2.name}** (`{p2.score}`){p2_fire}\n"
            f"**target:** first to 11 (win by 2) | **possession:** {off.mention}"
        )

        if self.phase == "offense":
            status = f"**{off.mention} is choosing an offensive move...**"
        else:
            status = f"**{deff.mention} is choosing a defensive coverage!**"

        desc = f"{scoreboard}\n\n{status}\n\n**last play:**\n{self.last_play_log}"
        return fleed_embed(title="1v1 street basketball match", description=desc, author=off.member)

    def refresh_buttons(self):
        self.clear_items()

        if self.game_over:
            return

        if self.phase == "offense":
            dunk_btn = discord.ui.Button(label="drive & dunk (2pt)", style=discord.ButtonStyle.primary, row=0)
            dunk_btn.callback = self.make_offense_callback("dunk")
            self.add_item(dunk_btn)

            mid_btn = discord.ui.Button(label="mid-range (2pt)", style=discord.ButtonStyle.primary, row=0)
            mid_btn.callback = self.make_offense_callback("mid")
            self.add_item(mid_btn)

            three_btn = discord.ui.Button(label="stepback 3 (3pt)", style=discord.ButtonStyle.primary, row=0)
            three_btn.callback = self.make_offense_callback("three")
            self.add_item(three_btn)

            cross_btn = discord.ui.Button(label="crossover", style=discord.ButtonStyle.secondary, row=1)
            cross_btn.callback = self.make_offense_callback("crossover")
            self.add_item(cross_btn)

            pump_btn = discord.ui.Button(label="pump fake", style=discord.ButtonStyle.secondary, row=1)
            pump_btn.callback = self.make_offense_callback("pumpfake")
            self.add_item(pump_btn)

            forfeit_btn = discord.ui.Button(label="forfeit", style=discord.ButtonStyle.danger, row=1)
            forfeit_btn.callback = self.forfeit_callback
            self.add_item(forfeit_btn)

        else:
            contest_btn = discord.ui.Button(label="contest shot", style=discord.ButtonStyle.primary, row=0)
            contest_btn.callback = self.make_defense_callback("contest")
            self.add_item(contest_btn)

            block_btn = discord.ui.Button(label="protect rim / block", style=discord.ButtonStyle.primary, row=0)
            block_btn.callback = self.make_defense_callback("block")
            self.add_item(block_btn)

            steal_btn = discord.ui.Button(label="swipe steal", style=discord.ButtonStyle.secondary, row=1)
            steal_btn.callback = self.make_defense_callback("steal")
            self.add_item(steal_btn)

            charge_btn = discord.ui.Button(label="stand ground / charge", style=discord.ButtonStyle.secondary, row=1)
            charge_btn.callback = self.make_defense_callback("charge")
            self.add_item(charge_btn)

            forfeit_btn = discord.ui.Button(label="forfeit", style=discord.ButtonStyle.danger, row=1)
            forfeit_btn.callback = self.forfeit_callback
            self.add_item(forfeit_btn)

    def make_offense_callback(self, move: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.offense_player.member.id:
                if interaction.user.id == self.defense_player.member.id:
                    return await interaction.response.send_message("you are on defense right now", ephemeral=True)
                return await interaction.response.send_message("you are not in this game", ephemeral=True)

            self.pending_offense_move = move
            self.phase = "defense"
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        return callback

    def make_defense_callback(self, reaction: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.defense_player.member.id:
                if interaction.user.id == self.offense_player.member.id:
                    return await interaction.response.send_message("waiting for defender's coverage", ephemeral=True)
                return await interaction.response.send_message("you are not in this game", ephemeral=True)

            self.resolve_play(self.pending_offense_move, reaction)
            self.pending_offense_move = None
            self.phase = "offense"
            self.check_win()
            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        return callback

    def resolve_play(self, offense_move: str, defense_move: str):
        off = self.offense_player
        deff = self.defense_player
        off.fga += 1

        roll = random.random()
        bonus = 0.15 if off.on_fire else 0.0

        if offense_move == "dunk":
            if defense_move == "block":
                if roll < 0.40:
                    deff.blocks += 1
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{deff.name} met {off.name} at the apex and swatted the dunk into the bleachers! (block)**"
                    self.switch_possession()
                elif roll < 0.65:
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.dunks += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} got hacked by {deff.name} at the rim but finished through contact! (+2 pts)**"
                    self.switch_possession()
                else:
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.dunks += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} posterized {deff.name} with a savage tomahawk slam! (+2 pts)**"
                    self.switch_possession()

            elif defense_move == "charge":
                if roll < 0.30:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{deff.name} stood like a brick wall and drew the offensive charge on {off.name}!**"
                    self.switch_possession()
                else:
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.dunks += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} bulldozed through {deff.name} for the power layup! (+2 pts)**"
                    self.switch_possession()

            elif defense_move == "steal":
                if roll < 0.15:
                    deff.steals += 1
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{deff.name} poked the ball loose on {off.name}'s gather! (steal)**"
                    self.switch_possession()
                else:
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.dunks += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} blew past {deff.name}'s swipe and threw down a vicious windmill dunk! (+2 pts)**"
                    self.switch_possession()

            else: # contest
                if roll < (0.80 + bonus):
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.dunks += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} rose over {deff.name}'s contest and rattled the rim with a monster jam! (+2 pts)**"
                    self.switch_possession()
                else:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{off.name}'s contested layup rolled off the iron! {deff.name} snatches the rebound.**"
                    self.switch_possession()

        elif offense_move == "three":
            off.threes_att += 1
            if defense_move == "contest":
                if roll < (0.40 + bonus):
                    pts = 3
                    off.score += pts
                    off.fgm += 1
                    off.threes_made += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} drilled a heavily contested stepback 3 right in {deff.name}'s eye! (+3 pts)**"
                    self.switch_possession()
                else:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{off.name}'s stepback 3 clanked off the back iron! {deff.name} secures the board.**"
                    self.switch_possession()

            elif defense_move in ("block", "charge"):
                if roll < (0.75 + bonus):
                    pts = 3
                    off.score += pts
                    off.fgm += 1
                    off.threes_made += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{deff.name} sagged into the paint — {off.name} stepped back and splashed an uncontested 3! (+3 pts)**"
                    self.switch_possession()
                else:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{off.name} missed the open 3-pointer! Ball bounces out to {deff.name}.**"
                    self.switch_possession()

            else: # steal
                if roll < 0.25:
                    deff.steals += 1
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{deff.name} gambled on the reach and slapped the ball away! (steal)**"
                    self.switch_possession()
                elif roll < 0.50:
                    pts = 3
                    off.score += pts
                    off.fgm += 1
                    off.threes_made += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} was fouled on the perimeter and STILL splashed the 3! (+3 pts)**"
                    self.switch_possession()
                else:
                    pts = 3
                    off.score += pts
                    off.fgm += 1
                    off.threes_made += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} pulled up from deep over {deff.name}'s swipe... BANG! (+3 pts)**"
                    self.switch_possession()

        elif offense_move == "mid":
            if defense_move == "contest":
                if roll < (0.50 + bonus):
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} elevated over {deff.name} and buried the mid-range pull-up! (+2 pts)**"
                    self.switch_possession()
                else:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{off.name}'s mid-range jumper rimmed out! {deff.name} grabs the defensive rebound.**"
                    self.switch_possession()

            elif defense_move in ("block", "charge"):
                if roll < (0.80 + bonus):
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} stopped on a dime and drained the open free-throw line jumper! (+2 pts)**"
                    self.switch_possession()
                else:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{off.name}'s open mid-range jumper bounced off the rim!**"
                    self.switch_possession()

            else: # steal
                if roll < 0.20:
                    deff.steals += 1
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{deff.name} jumped the passing lane and stole the rock from {off.name}!**"
                    self.switch_possession()
                else:
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} took one dribble around {deff.name}'s swipe and swished the middy! (+2 pts)**"
                    self.switch_possession()

        elif offense_move == "crossover":
            if defense_move == "steal":
                pts = 2
                off.score += pts
                off.fgm += 1
                off.ankles_broken += 1
                off.streak += 1
                if off.streak >= 2: off.on_fire = True
                self.last_play_log = f"**OH MY GOODNESS! {off.name} crossed over so hard {deff.name} hit the floor! Easy bucket! (+2 pts)**"
                self.switch_possession()

            elif defense_move == "charge":
                if roll < 0.40:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{deff.name} stayed disciplined, absorbed the contact, and forced a travel on {off.name}!**"
                    self.switch_possession()
                else:
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} used a lightning in-and-out dribble to glide past {deff.name} for a finger roll! (+2 pts)**"
                    self.switch_possession()

            else: # contest or block
                if roll < (0.75 + bonus):
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{off.name} shook {deff.name} with a behind-the-back move and floated it in off glass! (+2 pts)**"
                    self.switch_possession()
                else:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{off.name} created separation with a crossover but the floater spun out!**"
                    self.switch_possession()

        elif offense_move == "pumpfake":
            if defense_move in ("block", "contest"):
                pts = 2
                off.score += pts
                off.fgm += 1
                off.streak += 1
                if off.streak >= 2: off.on_fire = True
                self.last_play_log = f"**{deff.name} bit hard on the pump fake and flew past! {off.name} walked in for an easy layup! (+2 pts)**"
                self.switch_possession()
            else:
                if roll < 0.35:
                    pts = 2
                    off.score += pts
                    off.fgm += 1
                    off.streak += 1
                    if off.streak >= 2: off.on_fire = True
                    self.last_play_log = f"**{deff.name} didn't jump, but {off.name} hit the tough fadeaway anyway! (+2 pts)**"
                    self.switch_possession()
                else:
                    off.streak = 0
                    off.on_fire = False
                    self.last_play_log = f"**{deff.name} stayed on the ground! {off.name} forced up a bad shot that hit all backboard.**"
                    self.switch_possession()

    async def forfeit_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in (self.p1.member.id, self.p2.member.id):
            return await interaction.response.send_message("you are not in this game", ephemeral=True)

        for child in self.children:
            child.disabled = True

        surrenderer = self.p1 if interaction.user.id == self.p1.member.id else self.p2
        winner = self.p2 if surrenderer == self.p1 else self.p1
        self.game_over = True
        self.winner = winner
        self.last_play_log = f"**{surrenderer.name} forfeited the match!**"
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                embed = fleed_embed(title="1v1 basketball match", description="match timed out due to inactivity", author=self.p1.member)
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.active_blacktea_channels = set()
        self.active_monopoly_channels = set()
        self.active_basketball_channels = set()
        self.active_guessnumber_channels = set()

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (fleed; discord bot)"})

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # lyrics
    @commands.hybrid_command(name="lyrics", aliases=["lyric"])
    async def lyrics(self, ctx, *, song: str):
        try:
            encoded = urllib.parse.quote(song)
            url = f"https://lrclib.net/api/search?q={encoded}"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                if not data:
                    return await ctx.send(embed=warn_embed(f"no lyrics found for `{song.lower()}`", ctx.author))

                top = data[0]
                plain_lyrics = top.get("plainLyrics") or top.get("syncedLyrics")
                if not plain_lyrics:
                    return await ctx.send(embed=warn_embed(f"lyrics text unavailable for `{song.lower()}`", ctx.author))

                title = f"{top.get('trackName', song).lower()} — {top.get('artistName', '').lower()}"
                clean_lyrics = plain_lyrics[:2000].lower()
                embed = fleed_embed(title=title, description=clean_lyrics, author=ctx.author)
                embed.set_footer(text=f"album: {top.get('albumName', 'single').lower()}")
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch lyrics", ctx.author))

    # meme
    @commands.hybrid_command(name="meme")
    async def meme(self, ctx):
        try:
            async with self.session.get("https://meme-api.com/gimme", timeout=10) as resp:
                data = await resp.json(content_type=None)
                embed = fleed_embed(title=data.get("title", "meme").lower(), author=ctx.author)
                embed.set_image(url=data.get("url"))
                embed.set_footer(text=f"r/{data.get('subreddit', 'memes')} | {data.get('ups', 0):,} upvotes")
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch meme", ctx.author))

    # joke
    @commands.hybrid_command(name="joke")
    async def joke(self, ctx):
        try:
            url = "https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,religious,political,racist,sexist"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                if data.get("type") == "single":
                    desc = data.get("joke", "").lower()
                else:
                    desc = f"{data.get('setup', '').lower()}\n\n*{data.get('delivery', '').lower()}*"
                embed = fleed_embed(title="joke", description=desc, author=ctx.author)
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch joke", ctx.author))

    # trivia
    @commands.hybrid_command(name="trivia")
    async def trivia(self, ctx):
        try:
            async with self.session.get("https://opentdb.com/api.php?amount=1&type=multiple", timeout=10) as resp:
                data = await resp.json(content_type=None)
                results = data.get("results", [])
                if not results:
                    return await ctx.send(embed=error_embed("trivia question unavailable", ctx.author))

                q_data = results[0]
                question = html.unescape(q_data.get("question", "")).lower()
                correct = html.unescape(q_data.get("correct_answer", ""))
                incorrects = [html.unescape(a) for a in q_data.get("incorrect_answers", [])]

                options = incorrects + [correct]
                random.shuffle(options)

                view = TriviaButtonView(ctx.author.id, correct, options)
                desc = f"**category:** {q_data.get('category', '').lower()} | **difficulty:** {q_data.get('difficulty', '').lower()}\n\n{question}"
                embed = fleed_embed(title="trivia", description=desc, author=ctx.author)
                await ctx.send(embed=embed, view=view)
        except Exception:
            await ctx.send(embed=error_embed("failed to start trivia", ctx.author))

    # fact
    @commands.hybrid_command(name="fact", aliases=["randomfact"])
    async def fact(self, ctx):
        try:
            async with self.session.get("https://uselessfacts.jsph.pl/random.json?language=en", timeout=10) as resp:
                data = await resp.json(content_type=None)
                text = data.get("text", "").lower()
                embed = fleed_embed(title="random fact", description=text, author=ctx.author)
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch fact", ctx.author))

    # anime search
    @commands.hybrid_command(name="anime")
    async def anime(self, ctx, *, query: str):
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://kitsu.io/api/edge/anime?filter[text]={encoded}&page[limit]=1"
            async with self.session.get(url, timeout=10) as resp:
                data = await resp.json(content_type=None)
                anime_list = data.get("data", [])
                if not anime_list:
                    return await ctx.send(embed=warn_embed(f"no anime found for `{query.lower()}`", ctx.author))

                attr = anime_list[0].get("attributes", {})
                title = attr.get("canonicalTitle", query).lower()
                synopsis = attr.get("synopsis", "no synopsis available")[:500].lower()
                rating = attr.get("averageRating", "n/a")
                episodes = attr.get("episodeCount", "unknown")
                status = attr.get("status", "unknown").lower()
                poster = attr.get("posterImage", {}).get("large")

                desc = f"**rating:** {rating}/100\n**episodes:** {episodes}\n**status:** {status}\n\n{synopsis}..."
                embed = fleed_embed(title=f"anime: {title}", description=desc, author=ctx.author)
                if poster:
                    embed.set_thumbnail(url=poster)
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to search anime", ctx.author))

    # gangs
    @commands.hybrid_group(name="gang", aliases=["gangs"], invoke_without_command=True)
    async def gang(self, ctx):
        await send_group_help(ctx, self.gang, "fun")

    @gang.command(name="create", aliases=["c"])
    async def gang_create(self, ctx, *, gang_name: str):
        existing = await self.bot.db.fetchrow("SELECT gang_name FROM gang_members WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        if existing:
            return await ctx.send(embed=error_embed("you are already in a gang", ctx.author))
        await self.bot.db.execute("INSERT INTO gangs (guild_id, gang_name, owner_id) VALUES (?, ?, ?)", (ctx.guild.id, gang_name.lower(), ctx.author.id))
        await self.bot.db.execute("INSERT INTO gang_members (guild_id, gang_name, user_id, is_admin) VALUES (?, ?, ?, 1)", (ctx.guild.id, gang_name.lower(), ctx.author.id))
        await ctx.send(embed=success_embed(f"created gang `{gang_name.lower()}`", ctx.author))

    @gang.command(name="leave", aliases=["l"])
    async def gang_leave(self, ctx):
        member = await self.bot.db.fetchrow("SELECT gang_name FROM gang_members WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        if not member:
            return await ctx.send(embed=error_embed("you are not in a gang", ctx.author))
        gang = await self.bot.db.fetchrow("SELECT owner_id FROM gangs WHERE guild_id = ? AND gang_name = ?", (ctx.guild.id, member["gang_name"]))
        if gang and gang["owner_id"] == ctx.author.id:
            return await ctx.send(embed=error_embed("gang owners cannot leave, use gang disband or gang transfer", ctx.author))
        await self.bot.db.execute("DELETE FROM gang_members WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
        await ctx.send(embed=success_embed("left your gang", ctx.author))

    @gang.command(name="info", aliases=["i"])
    async def gang_info(self, ctx, *, gang_name: str = None):
        if not gang_name:
            user_g = await self.bot.db.fetchrow("SELECT gang_name FROM gang_members WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, ctx.author.id))
            if not user_g:
                return await ctx.send(embed=error_embed("provide a gang name or join one", ctx.author))
            gang_name = user_g["gang_name"]
        gang = await self.bot.db.fetchrow("SELECT * FROM gangs WHERE guild_id = ? AND gang_name = ?", (ctx.guild.id, gang_name.lower()))
        if not gang:
            return await ctx.send(embed=error_embed("gang not found", ctx.author))
        members = await self.bot.db.fetch("SELECT user_id FROM gang_members WHERE guild_id = ? AND gang_name = ?", (ctx.guild.id, gang_name.lower()))
        owner = self.bot.get_user(gang["owner_id"])
        owner_name = str(owner).lower() if owner else str(gang["owner_id"])
        embed = fleed_embed(title=f"gang: {gang_name.lower()}", description=f"owner: {owner_name}\nmembers: {len(members)}", author=ctx.author)
        if gang["banner_url"]:
            embed.set_image(url=gang["banner_url"])
        await ctx.send(embed=embed)

    # diary
    @commands.hybrid_group(name="diary", invoke_without_command=True)
    async def diary_group(self, ctx):
        await send_group_help(ctx, ctx.command, "fun")

    @diary_group.command(name="add", aliases=["write"])
    async def diary_add(self, ctx, *, content: str):
        now = int(time.time())
        await self.bot.db.execute("INSERT INTO diary (user_id, content, created_at) VALUES (?, ?, ?)", (ctx.author.id, content, now))
        await ctx.send(embed=success_embed("saved diary entry", ctx.author))

    @diary_group.command(name="list", aliases=["view"])
    async def diary_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT id, content, created_at FROM diary WHERE user_id = ? ORDER BY id DESC LIMIT 10", (ctx.author.id,))
        if not rows:
            return await ctx.send(embed=warn_embed("your diary is empty", ctx.author))
        lines = [f"`#{r['id']}` — {r['content'][:80]}" for r in rows]
        await ctx.send(embed=fleed_embed(title="your diary entries", description="\n".join(lines), author=ctx.author))

    @diary_group.command(name="clear")
    async def diary_clear(self, ctx):
        await self.bot.db.execute("DELETE FROM diary WHERE user_id = ?", (ctx.author.id,))
        await ctx.send(embed=success_embed("cleared all diary entries", ctx.author))

    # uwulock
    @commands.hybrid_group(name="uwulock", invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def uwulock_group(self, ctx, member: discord.Member = None):
        if member is None:
            return await send_group_help(ctx, ctx.command, "fun")
        row = await self.bot.db.fetchrow("SELECT * FROM uwulock WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        if row:
            await self.bot.db.execute("DELETE FROM uwulock WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
            await ctx.send(embed=success_embed(f"unlocked {member.mention} from uwulock", ctx.author))
        else:
            await self.bot.db.execute("INSERT INTO uwulock (guild_id, user_id) VALUES (?, ?)", (ctx.guild.id, member.id))
            await ctx.send(embed=success_embed(f"locked {member.mention} to uwu speak", ctx.author))

    @uwulock_group.command(name="list")
    async def uwulock_list(self, ctx):
        rows = await self.bot.db.fetch("SELECT user_id FROM uwulock WHERE guild_id = ?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(embed=warn_embed("no members are currently uwulocked", ctx.author))
        lines = [f"<@{r['user_id']}>" for r in rows]
        await ctx.send(embed=fleed_embed(title="uwulocked members", description="\n".join(lines), author=ctx.author))

    # birthday
    @commands.hybrid_group(name="birthday", aliases=["bday"], invoke_without_command=True)
    async def birthday_group(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        row = await self.bot.db.fetchrow("SELECT month, day FROM birthdays WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, target.id))
        if not row:
            return await ctx.send(embed=warn_embed(f"no birthday set for {target.mention}", ctx.author))
        months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
        m_name = months[row["month"] - 1] if 1 <= row["month"] <= 12 else str(row["month"])
        await ctx.send(embed=fleed_embed(title=f"{target.display_name.lower()}'s birthday", description=f"{m_name} {row['day']}", author=target))

    @birthday_group.command(name="set")
    async def birthday_set(self, ctx, month: int, day: int):
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return await ctx.send(embed=error_embed("invalid date — format: `,birthday set <month 1-12> <day 1-31>`", ctx.author))
        await self.bot.db.execute("INSERT OR REPLACE INTO birthdays (guild_id, user_id, month, day) VALUES (?, ?, ?, ?)", (ctx.guild.id, ctx.author.id, month, day))
        await ctx.send(embed=success_embed(f"saved birthday for {ctx.author.mention}", ctx.author))

    # 8ball
    @commands.command(name="8ball", aliases=["eightball"])
    async def eightball(self, ctx, *, question: str):
        responses = [
            "it is certain", "without a doubt", "yes definitely", "you may rely on it",
            "as i see it, yes", "most likely", "outlook good", "yes", "signs point to yes",
            "reply hazy, try again", "ask again later", "better not tell you now", "cannot predict now",
            "concentrate and ask again", "don't count on it", "my reply is no", "my sources say no",
            "outlook not so good", "very doubtful"
        ]
        ans = random.choice(responses)
        embed = fleed_embed(title="magic 8-ball", description=f"**question:** {question.lower()}\n**answer:** {ans}", author=ctx.author)
        await ctx.send(embed=embed)

    # tictactoe
    @commands.command(name="tictactoe", aliases=["ttt"])
    async def tictactoe(self, ctx, opponent: discord.Member):
        if opponent.id == ctx.author.id or opponent.bot:
            return await ctx.send(embed=warn_embed("mention another server member to play against", ctx.author))

        class TTTButton(discord.ui.Button):
            def __init__(self, x: int, y: int):
                super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
                self.x = x
                self.y = y

            async def callback(self, interaction: discord.Interaction):
                view: TTTView = self.view
                if interaction.user.id != view.current_player.id:
                    return await interaction.response.send_message("it is not your turn", ephemeral=True)
                
                symbol = "X" if view.current_player.id == view.p1.id else "O"
                self.label = symbol
                self.style = discord.ButtonStyle.danger if symbol == "X" else discord.ButtonStyle.primary
                self.disabled = True
                view.board[self.y][self.x] = symbol

                winner = view.check_winner()
                if winner:
                    for child in view.children:
                        child.disabled = True
                    win_player = view.p1 if winner == "X" else view.p2
                    await interaction.response.edit_message(content=f"{win_player.mention} **won the tictactoe match!**", view=view)
                    return view.stop()
                elif view.is_full():
                    for child in view.children:
                        child.disabled = True
                    await interaction.response.edit_message(content="**tictactoe game tied!**", view=view)
                    return view.stop()

                view.current_player = view.p2 if view.current_player.id == view.p1.id else view.p1
                turn_sym = "X" if view.current_player.id == view.p1.id else "O"
                await interaction.response.edit_message(content=f"**tictactoe match:** {view.p1.mention} (X) vs {view.p2.mention} (O)\n**turn:** {view.current_player.mention} ({turn_sym})", view=view)

        class TTTView(discord.ui.View):
            def __init__(self, p1: discord.Member, p2: discord.Member):
                super().__init__(timeout=60)
                self.p1 = p1
                self.p2 = p2
                self.current_player = p1
                self.board = [["" for _ in range(3)] for _ in range(3)]
                for y in range(3):
                    for x in range(3):
                        self.add_item(TTTButton(x, y))

            def check_winner(self):
                for row in self.board:
                    if row[0] == row[1] == row[2] != "":
                        return row[0]
                for col in range(3):
                    if self.board[0][col] == self.board[1][col] == self.board[2][col] != "":
                        return self.board[0][col]
                if self.board[0][0] == self.board[1][1] == self.board[2][2] != "":
                    return self.board[0][0]
                if self.board[0][2] == self.board[1][1] == self.board[2][0] != "":
                    return self.board[0][2]
                return None

            def is_full(self):
                return all(self.board[y][x] != "" for y in range(3) for x in range(3))

        view = TTTView(ctx.author, opponent)
        await ctx.send(f"**tictactoe match:** {ctx.author.mention} (X) vs {opponent.mention} (O)\n**turn:** {ctx.author.mention} (X)", view=view)

    # connect4
    @commands.command(name="connect4", aliases=["c4", "connectfour"])
    async def connect4_cmd(self, ctx, opponent: discord.Member):
        """Play an interactive Connect Four match against another server member"""
        if opponent.id == ctx.author.id or opponent.bot:
            return await ctx.send(embed=warn_embed("mention another server member to play against", ctx.author))

        class C4ColButton(discord.ui.Button):
            def __init__(self, col: int, row_pos: int):
                super().__init__(label=str(col + 1), style=discord.ButtonStyle.secondary, row=row_pos)
                self.col = col

            async def callback(self, interaction: discord.Interaction):
                view: C4View = self.view
                if interaction.user.id != view.current_player.id:
                    if interaction.user.id in (view.p1.id, view.p2.id):
                        return await interaction.response.send_message("it is not your turn", ephemeral=True)
                    return await interaction.response.send_message("this is not your game", ephemeral=True)

                token = "X" if view.current_player.id == view.p1.id else "O"
                dropped = view.drop_token(self.col, token)
                if dropped == -1:
                    self.disabled = True
                    return await interaction.response.send_message("this column is full", ephemeral=True)

                if view.board[0][self.col] != ".":
                    self.disabled = True

                if view.check_winner(token):
                    for child in view.children:
                        child.disabled = True
                    win_desc = f"{view.current_player.mention} ({token}) **won the connect four match!**"
                    await interaction.response.edit_message(embed=view.build_embed(win_desc), view=view)
                    return view.stop()

                if view.is_full():
                    for child in view.children:
                        child.disabled = True
                    tie_desc = "**connect four match tied! board is full.**"
                    await interaction.response.edit_message(embed=view.build_embed(tie_desc), view=view)
                    return view.stop()

                view.current_player = view.p2 if view.current_player.id == view.p1.id else view.p1
                await interaction.response.edit_message(embed=view.build_embed(), view=view)

        class C4ForfeitButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="forfeit", style=discord.ButtonStyle.danger, row=1)

            async def callback(self, interaction: discord.Interaction):
                view: C4View = self.view
                if interaction.user.id not in (view.p1.id, view.p2.id):
                    return await interaction.response.send_message("this is not your game", ephemeral=True)

                for child in view.children:
                    child.disabled = True

                surrenderer = interaction.user
                winner = view.p2 if surrenderer.id == view.p1.id else view.p1
                status = f"{surrenderer.mention} **forfeited!** {winner.mention} **wins the game!**"
                await interaction.response.edit_message(embed=view.build_embed(status), view=view)
                view.stop()

        class C4View(discord.ui.View):
            def __init__(self, p1: discord.Member, p2: discord.Member):
                super().__init__(timeout=90)
                self.p1 = p1
                self.p2 = p2
                self.current_player = p1
                self.message = None
                self.board = [["." for _ in range(7)] for _ in range(6)]

                # Add column buttons (1-4 on row 0, 5-7 on row 1)
                for c in range(4):
                    self.add_item(C4ColButton(c, row_pos=0))
                for c in range(4, 7):
                    self.add_item(C4ColButton(c, row_pos=1))
                self.add_item(C4ForfeitButton())

            def drop_token(self, col: int, token: str) -> int:
                for r in range(5, -1, -1):
                    if self.board[r][col] == ".":
                        self.board[r][col] = token
                        return r
                return -1

            def check_winner(self, token: str) -> bool:
                # Horizontal
                for r in range(6):
                    for c in range(4):
                        if self.board[r][c] == self.board[r][c+1] == self.board[r][c+2] == self.board[r][c+3] == token:
                            return True
                # Vertical
                for r in range(3):
                    for c in range(7):
                        if self.board[r][c] == self.board[r+1][c] == self.board[r+2][c] == self.board[r+3][c] == token:
                            return True
                # Diagonal \
                for r in range(3):
                    for c in range(4):
                        if self.board[r][c] == self.board[r+1][c+1] == self.board[r+2][c+2] == self.board[r+3][c+3] == token:
                            return True
                # Diagonal /
                for r in range(3, 6):
                    for c in range(4):
                        if self.board[r][c] == self.board[r-1][c+1] == self.board[r-2][c+2] == self.board[r-3][c+3] == token:
                            return True
                return False

            def is_full(self) -> bool:
                return all(self.board[0][c] != "." for c in range(7))

            def render_board(self) -> str:
                lines = [" ".join(self.board[r]) for r in range(6)]
                lines.append("1 2 3 4 5 6 7")
                return "```\n" + "\n".join(lines) + "\n```"

            def build_embed(self, status: str = None) -> discord.Embed:
                p1_tag = f"{self.p1.mention} (X)"
                p2_tag = f"{self.p2.mention} (O)"
                cur_sym = "X" if self.current_player.id == self.p1.id else "O"

                if status:
                    desc = f"**players:** {p1_tag} vs {p2_tag}\n\n{self.render_board()}\n\n{status}"
                else:
                    desc = f"**players:** {p1_tag} vs {p2_tag}\n**turn:** {self.current_player.mention} ({cur_sym})\n\n{self.render_board()}"

                return fleed_embed(title="connect four", description=desc, author=self.current_player)

            async def on_timeout(self):
                for child in self.children:
                    child.disabled = True
                if self.message:
                    try:
                        embed = self.build_embed("**game timed out due to inactivity.**")
                        await self.message.edit(embed=embed, view=self)
                    except Exception:
                        pass

        view = C4View(ctx.author, opponent)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg


    # choose
    @commands.command(name="choose", aliases=["pick"])
    async def choose_cmd(self, ctx, *, choices: str):
        parts = [p.strip() for p in (choices.split(" or ") if " or " in choices else choices.split(",")) if p.strip()]
        if len(parts) < 2:
            parts = choices.split()
        if len(parts) < 2:
            return await ctx.send(embed=error_embed("provide at least 2 choices separated by commas or 'or'", ctx.author))
        pick = random.choice(parts)
        await ctx.send(embed=fleed_embed(description=f"i choose **{pick.lower()}**", author=ctx.author))

    # rps
    @commands.command(name="rps")
    async def rps_cmd(self, ctx, choice: str):
        choice = choice.lower()
        valid = ["rock", "paper", "scissors"]
        if choice not in valid:
            return await ctx.send(embed=error_embed("choose `rock`, `paper`, or `scissors`", ctx.author))
        bot_choice = random.choice(valid)
        if choice == bot_choice:
            res = "tie"
        elif (choice == "rock" and bot_choice == "scissors") or (choice == "paper" and bot_choice == "rock") or (choice == "scissors" and bot_choice == "paper"):
            res = "you win"
        else:
            res = "you lose"
        await ctx.send(embed=fleed_embed(title="rock paper scissors", description=f"you: `{choice}` vs bot: `{bot_choice}`\n**result:** {res}", author=ctx.author))

    # uwuify
    @commands.command(name="uwuify", aliases=["uwu"])
    async def uwuify_cmd(self, ctx, *, text: str):
        uwu = text.replace("r", "w").replace("l", "w").replace("R", "W").replace("L", "W")
        uwu = uwu.replace("th", "d").replace("Th", "D") + " uwu~"
        await ctx.send(embed=fleed_embed(description=uwu, author=ctx.author))

    # blunt & vape
    @commands.hybrid_group(name="blunt", invoke_without_command=True)
    async def blunt_group(self, ctx):
        await self.smoke(ctx)

    @blunt_group.command(name="spark")
    async def blunt_spark(self, ctx):
        await self.spark(ctx)

    @blunt_group.command(name="smoke")
    async def blunt_smoke(self, ctx):
        await self.smoke(ctx)

    @blunt_group.command(name="taps")
    async def blunt_taps(self, ctx):
        await self.taps(ctx)

    @commands.command(name="spark")
    async def spark(self, ctx):
        await self.bot.db.execute("INSERT INTO blunt (guild_id, sparked, taps) VALUES (?, 1, 0) ON CONFLICT(guild_id) DO UPDATE SET sparked = 1", (ctx.guild.id,))
        await ctx.send(embed=success_embed("lit the blunt", ctx.author))

    @commands.command(name="smoke")
    async def smoke(self, ctx):
        row = await self.bot.db.fetchrow("SELECT * FROM blunt WHERE guild_id = ?", (ctx.guild.id,))
        if not row or not row["sparked"]:
            return await ctx.send(embed=error_embed("the blunt is not lit, use spark", ctx.author))
        await self.bot.db.execute("UPDATE blunt SET taps = taps + 1 WHERE guild_id = ?", (ctx.guild.id,))
        await ctx.send(embed=fleed_embed(description=f"{ctx.author.display_name.lower()} hit the blunt", author=ctx.author))

    @commands.command(name="taps")
    async def taps(self, ctx, member: discord.Member = None):
        row = await self.bot.db.fetchrow("SELECT taps FROM blunt WHERE guild_id = ?", (ctx.guild.id,))
        count = row["taps"] if row else 0
        await ctx.send(embed=fleed_embed(description=f"blunt has been tapped {count} times", author=ctx.author))

    @commands.hybrid_group(name="vape", invoke_without_command=True)
    async def vape(self, ctx):
        await send_group_help(ctx, ctx.command)

    @vape.command(name="steal", aliases=["claim"])
    async def vape_steal(self, ctx):
        await self.bot.db.execute("INSERT INTO vape (guild_id, holder_id, hits) VALUES (?, ?, 0) ON CONFLICT(guild_id) DO UPDATE SET holder_id = ?", (ctx.guild.id, ctx.author.id, ctx.author.id))
        await ctx.send(embed=success_embed(f"{ctx.author.display_name.lower()} stole the vape", ctx.author))

    @vape.command(name="hits", aliases=["h"])
    async def vape_hits(self, ctx):
        row = await self.bot.db.fetchrow("SELECT * FROM vape WHERE guild_id = ?", (ctx.guild.id,))
        if not row:
            return await ctx.send(embed=warn_embed(description="no vape in this server yet, use vape steal", author=ctx.author))
        holder = self.bot.get_user(row["holder_id"])
        h_name = str(holder).lower() if holder else "nobody"
        await ctx.send(embed=fleed_embed(title="vape status", description=f"holder: {h_name}\nflavor: {row['flavor']}\nhits: {row['hits']}", author=ctx.author))

    # fun extras
    @commands.command(name="wyr", aliases=["wouldyourather"])
    async def wyr(self, ctx):
        prompts = [
            "be invisible or be able to fly",
            "always be 10 minutes late or 20 minutes early",
            "never listen to music again or never watch movies again",
            "have unlimited money or unlimited time"
        ]
        await ctx.send(embed=fleed_embed(title="would you rather", description=random.choice(prompts), author=ctx.author))

    @commands.command(name="roast")
    async def roast(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        roasts = [
            "light travels faster than sound, which is why you seemed bright until you spoke",
            "you bring everyone so much joy when you leave the room",
            "mirrors cannot talk, lucky for you they cannot laugh either"
        ]
        await ctx.send(embed=fleed_embed(description=f"{target.mention} {random.choice(roasts)}", author=target))

    @commands.command(name="iq")
    async def iq(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        val = random.randint(40, 160)
        await ctx.send(embed=fleed_embed(description=f"{target.display_name.lower()}'s iq is {val}", author=target))

    @commands.command(name="howgay", aliases=["gay"])
    async def howgay(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        await ctx.send(embed=fleed_embed(description=f"{target.display_name.lower()} is {random.randint(0, 100)}% gay", author=target))

    @commands.command(name="howles", aliases=["howlesbian", "lesbian"])
    async def howles(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        await ctx.send(embed=fleed_embed(description=f"{target.display_name.lower()} is {random.randint(0, 100)}% lesbian", author=target))

    @commands.command(name="howautism", aliases=["autism"])
    async def howautism(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        await ctx.send(embed=fleed_embed(description=f"{target.display_name.lower()} is {random.randint(0, 100)}% autistic", author=target))

    @commands.command(name="howsexy", aliases=["sexy", "howhot", "hot"])
    async def howsexy(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        await ctx.send(embed=fleed_embed(description=f"{target.display_name.lower()} is {random.randint(0, 100)}% sexy", author=target))

    @commands.command(name="pp", aliases=["dih"])
    async def pp(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        length = "=" * random.randint(0, 14)
        await ctx.send(embed=fleed_embed(title=f"{target.display_name.lower()}'s size", description=f"8{length}D", author=target))

    # blacktea word bomb game
    @commands.command(name="blacktea", aliases=["bt", "wordbomb"])
    async def blacktea_cmd(self, ctx):
        """Start a fast-paced BlackTea word bomb game in the channel"""
        if ctx.channel.id in self.active_blacktea_channels:
            return await ctx.send(embed=error_embed("a blacktea game is already running in this channel", ctx.author))

        self.active_blacktea_channels.add(ctx.channel.id)
        lobby = BlackTeaLobbyView(ctx.author)
        msg = await ctx.send(embed=lobby.build_embed(), view=lobby)

        try:
            await lobby.wait()

            if lobby.cancelled or (not lobby.started and len(lobby.players) == 0):
                for child in lobby.children:
                    child.disabled = True
                await msg.edit(embed=fleed_embed(title="🍵 blacktea lobby", description="lobby cancelled or timed out", author=ctx.author), view=lobby)
                return

            # Disable lobby buttons
            for child in lobby.children:
                child.disabled = True
            await msg.edit(view=lobby)

            players = list(lobby.players)
            lives = {p.id: 2 for p in players}
            used_words = set()
            round_num = 1
            is_solo = (len(players) == 1)

            start_desc = (
                f"match started with **{len(players)} player{'s' if len(players) > 1 else ''}**!\n"
                f"each player has **2 lives**. you have **10 seconds** to type a valid english word."
            )
            await ctx.send(embed=fleed_embed(title="blacktea match start", description=start_desc, author=ctx.author))
            await asyncio.sleep(2)

            while (not is_solo and len(players) > 1) or (is_solo and len(players) == 1):
                for player in list(players):
                    if player.id not in lives or lives[player.id] <= 0:
                        continue
                    syll = random.choice(VALID_SYLLABLES)
                    example_word = next((w for w in WORDS_SET if syll.lower() in w and w not in used_words), "valid word")
                    p_lives = f"{lives[player.id]} lives"

                    turn_embed = fleed_embed(
                        title=f"round {round_num}",
                        description=(
                            f"**turn:** {player.mention} ({p_lives})\n"
                            f"type a word containing: **`{syll}`**\n"
                            f"**10 seconds remaining**"
                        ),
                        author=player
                    )
                    await ctx.send(embed=turn_embed)

                    def check_msg(m):
                        return m.channel.id == ctx.channel.id and m.author.id == player.id

                    word_accepted = False
                    start_time = time.time()
                    time_limit = 10.0

                    while time.time() - start_time < time_limit:
                        remaining = time_limit - (time.time() - start_time)
                        if remaining <= 0:
                            break
                        try:
                            msg = await self.bot.wait_for("message", check=check_msg, timeout=remaining)
                            guess = msg.content.strip().lower()

                            if not guess.isalpha():
                                continue

                            if syll.lower() not in guess:
                                continue

                            if guess in used_words:
                                await ctx.send(embed=error_embed(f"`{guess}` was already used in this match", player), delete_after=3)
                                continue

                            if guess not in WORDS_SET:
                                await ctx.send(embed=error_embed(f"`{guess}` is not in the english dictionary", player), delete_after=3)
                                continue

                            # Success!
                            used_words.add(guess)
                            word_accepted = True
                            await ctx.send(embed=success_embed(f"**`{guess}`** accepted!", player))
                            break
                        except asyncio.TimeoutError:
                            break

                    if not word_accepted:
                        lives[player.id] -= 1
                        if lives[player.id] <= 0:
                            await ctx.send(embed=error_embed(f"ran out of lives and was eliminated! (example: `{example_word}`)", player))
                            players.remove(player)
                        else:
                            await ctx.send(embed=error_embed(f"ran out of time! lives remaining: {lives[player.id]} (example: `{example_word}`)", player))

                    if is_solo and len(players) == 0:
                        break
                    elif not is_solo and len(players) <= 1:
                        break

                    await asyncio.sleep(1.5)

                round_num += 1
                if is_solo and len(players) == 0:
                    break
                if not is_solo and len(players) <= 1:
                    break

            # Winner announcement
            if not is_solo and len(players) == 1:
                winner = players[0]
                win_desc = f"{winner.mention} **won the blacktea match** after **{round_num-1} rounds** and **{len(used_words)} words**!"
                await ctx.send(embed=fleed_embed(title="blacktea winner", description=win_desc, author=winner))
            elif is_solo:
                await ctx.send(embed=fleed_embed(title="blacktea game over", description=f"solo run finished! survived **{round_num-1} rounds** and played **{len(used_words)} words**!", author=ctx.author))
            else:
                await ctx.send(embed=fleed_embed(title="blacktea game over", description="no players survived the match!", author=ctx.author))

        finally:
            self.active_blacktea_channels.discard(ctx.channel.id)

    @commands.command(name="rate")
    async def rate_cmd(self, ctx, *, thing: str):
        val = hash(thing.lower().strip()) % 101
        await ctx.send(embed=fleed_embed(title="rating", description=f"i would rate **{thing.lower()}** a **{val}/100**", author=ctx.author))

    @commands.command(name="quote")
    async def quote_cmd(self, ctx):
        quotes = [
            ("simplicity is prerequisite for reliability.", "edsger w. dijkstra"),
            ("make it work, make it right, make it fast.", "kent beck"),
            ("first, solve the problem. then, write the code.", "john johnson"),
            ("talk is cheap. show me the code.", "linus torvalds"),
            ("any fool can write code that a computer can understand. good programmers write code that humans can understand.", "martin fowler")
        ]
        q, a = random.choice(quotes)
        await ctx.send(embed=fleed_embed(title="quote", description=f"*\"{q}\"*\n— **{a}**", author=ctx.author))

    @commands.command(name="mock")
    async def mock_cmd(self, ctx, *, text: str):
        res = ''.join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(text))
        await ctx.send(embed=fleed_embed(title="mock", description=res, author=ctx.author))

    @commands.command(name="clap")
    async def clap_cmd(self, ctx, *, text: str):
        res = ' 👏 '.join(text.split())
        await ctx.send(embed=fleed_embed(title="clap", description=res, author=ctx.author))

    @commands.command(name="vaporwave")
    async def vaporwave_cmd(self, ctx, *, text: str):
        res = ''.join(chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) <= 0x7E else c for c in text)
        await ctx.send(embed=fleed_embed(title="vaporwave", description=res, author=ctx.author))

    @commands.command(name="reverse_text", aliases=["revtext"])
    async def reverse_text_cmd(self, ctx, *, text: str):
        await ctx.send(embed=fleed_embed(title="reverse text", description=text[::-1], author=ctx.author))

    @commands.command(name="regional", aliases=["bigtext"])
    async def regional_cmd(self, ctx, *, text: str):
        mapping = {c: f":regional_indicator_{c.lower()}:" for c in "abcdefghijklmnopqrstuvwxyz"}
        res = " ".join(mapping.get(c.lower(), c) for c in text)
        await ctx.send(res[:2000])

    @commands.command(name="monopoly", aliases=["mp"])
    async def monopoly_cmd(self, ctx):
        if ctx.channel.id in self.active_monopoly_channels:
            return await ctx.send(embed=error_embed("a monopoly game is already running in this channel", ctx.author))

        self.active_monopoly_channels.add(ctx.channel.id)
        lobby = MonopolyLobbyView(ctx.author)
        msg = await ctx.send(embed=lobby.build_embed(), view=lobby)

        try:
            await lobby.wait()
            if lobby.cancelled or not lobby.started or len(lobby.players) < 2:
                for child in lobby.children:
                    child.disabled = True
                await msg.edit(embed=fleed_embed(title="monopoly lobby", description="lobby cancelled or timed out", author=ctx.author), view=lobby)
                return

            for child in lobby.children:
                child.disabled = True
            await msg.edit(view=lobby)

            game_view = MonopolyGameView(lobby.players)
            game_msg = await ctx.send(embed=game_view.build_embed(), view=game_view)
            game_view.message = game_msg
            await game_view.wait()

        finally:
            self.active_monopoly_channels.discard(ctx.channel.id)

    @commands.command(name="1v1", aliases=["basketball", "hoops", "ball", "bb"])
    async def basketball_1v1_cmd(self, ctx, opponent: discord.Member):
        """Play an interactive 1v1 street basketball match against another server member"""
        if opponent.id == ctx.author.id or opponent.bot:
            return await ctx.send(embed=warn_embed("mention another server member to play a 1v1 basketball match against", ctx.author))

        if ctx.channel.id in self.active_basketball_channels:
            return await ctx.send(embed=error_embed("a basketball match is already active in this channel", ctx.author))

        self.active_basketball_channels.add(ctx.channel.id)
        view = Basketball1v1GameView(ctx.author, opponent)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

        try:
            await view.wait()
        finally:
            self.active_basketball_channels.discard(ctx.channel.id)

    @commands.command(name="guessnumber", aliases=["gtn", "guessnum", "guess"])
    async def guessnumber_cmd(self, ctx, arg1: str = None, arg2: str = None):
        """Guess a secret number within any range you pick (multiplayer first to guess wins)"""
        if ctx.channel.id in self.active_guessnumber_channels:
            return await ctx.send(embed=error_embed("a guess the number game is already running in this channel", ctx.author))

        min_val = 1
        max_val = 100

        try:
            if arg1 is not None and arg2 is not None:
                min_val = int(arg1.replace(",", ""))
                max_val = int(arg2.replace(",", ""))
            elif arg1 is not None and arg2 is None:
                max_val = int(arg1.replace(",", ""))
        except ValueError:
            return await ctx.send(embed=error_embed("invalid range numbers — format: `,gtn <min> <max>` or `,gtn <max>`", ctx.author))

        if min_val > max_val:
            min_val, max_val = max_val, min_val

        if min_val == max_val:
            return await ctx.send(embed=error_embed("min and max cannot be the same number", ctx.author))

        if max_val - min_val > 100000000:
            return await ctx.send(embed=error_embed("range is too large (maximum span is 100,000,000)", ctx.author))

        secret = random.randint(min_val, max_val)
        total_guesses = 0

        self.active_guessnumber_channels.add(ctx.channel.id)

        start_desc = (
            f"i have picked a secret number between **{min_val:,}** and **{max_val:,}**!\n\n"
            f"anyone in chat can guess — whoever guesses it first wins!\n"
            f"host can type `cancel` to quit."
        )
        start_embed = fleed_embed(title="guess the number", description=start_desc, author=ctx.author)
        await ctx.send(embed=start_embed)

        def check_msg(m):
            return m.channel.id == ctx.channel.id and not m.author.bot

        try:
            while True:
                try:
                    msg = await self.bot.wait_for("message", check=check_msg, timeout=60.0)
                except asyncio.TimeoutError:
                    timeout_desc = f"**game timed out due to inactivity!** the secret number was **{secret:,}**."
                    return await ctx.send(embed=error_embed(timeout_desc, ctx.author))

                content = msg.content.strip().lower()
                if content in ("cancel", "quit", "exit", "stop"):
                    is_host = (msg.author.id == ctx.author.id)
                    is_mod = getattr(msg.author.guild_permissions, "manage_messages", False) if hasattr(msg.author, "guild_permissions") else False
                    if is_host or is_mod:
                        cancel_desc = f"**game cancelled by {msg.author.mention}!** the secret number was **{secret:,}**."
                        return await ctx.send(embed=warn_embed(cancel_desc, ctx.author))

                cleaned = content.replace(",", "")
                if not cleaned.lstrip("-").isdigit():
                    continue

                guess = int(cleaned)
                total_guesses += 1

                if guess == secret:
                    win_desc = (
                        f"**correct!** {msg.author.mention} guessed the secret number **{secret:,}** first "
                        f"and won the game after **{total_guesses}** total guess{'es' if total_guesses != 1 else ''}!"
                    )
                    return await ctx.send(embed=success_embed(win_desc, msg.author))

                hint = "too low" if guess < secret else "too high"
                feedback = (
                    f"**{msg.author.display_name.lower()}**: **{guess:,}** is **{hint}** (range: **{min_val:,}** – **{max_val:,}**)"
                )
                await ctx.send(embed=fleed_embed(title="guess the number", description=feedback, author=msg.author))

        finally:
            self.active_guessnumber_channels.discard(ctx.channel.id)

async def setup(bot):
    await bot.add_cog(Fun(bot))


