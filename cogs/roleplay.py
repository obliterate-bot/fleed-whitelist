import discord
from discord.ext import commands
import aiohttp
from utils import fleed_embed, success_embed, error_embed, send_group_help

ACTION_ENDPOINT_MAP = {
    "kill": ["punch", "smack", "slap"],
    "shoot": ["angrystare", "mad", "punch"],
    "bonk": ["smack", "slap", "punch"],
    "highfive": ["brofist", "cheers", "clap"],
    "hug": ["hug"],
    "kiss": ["kiss"],
    "slap": ["slap"],
    "pat": ["pat"],
    "cuddle": ["cuddle"],
    "bite": ["bite"],
    "punch": ["punch"],
    "stare": ["stare"],
    "tickle": ["tickle"],
    "feed": ["feed"],
    "poke": ["poke"],
    "dance": ["dance"],
    "cry": ["cry"],
    "blush": ["blush"],
    "handhold": ["handhold"],
    "lick": ["lick"],
    "wink": ["wink"],
    "wave": ["wave"],
    "smile": ["smile"],
    "pout": ["pout"]
}

class Roleplay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        self.session = aiohttp.ClientSession(headers=headers)

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_gif(self, action: str) -> str:
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        endpoints = ACTION_ENDPOINT_MAP.get(action.lower(), [action.lower()])

        for ep in endpoints:
            # 1. OtakuGIFs
            try:
                url = f"https://api.otakugifs.xyz/gif?reaction={ep}"
                async with self.session.get(url, timeout=3) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("url"):
                            return data.get("url")
            except Exception:
                pass

            # 2. PurrBot
            try:
                url = f"https://purrbot.site/api/img/sfw/{ep}/gif"
                async with self.session.get(url, timeout=3) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        link = data.get("link") or data.get("url")
                        if link and not data.get("error"):
                            return link
            except Exception:
                pass

            # 3. Nekos.life
            try:
                url = f"https://nekos.life/api/v2/img/{ep}"
                async with self.session.get(url, timeout=3) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("url"):
                            return data.get("url")
            except Exception:
                pass

        # Universal fallback
        return "https://cdn.otakugifs.xyz/gifs/dance/a567747565dd2855.gif"

    async def execute_rp(self, ctx, action_name: str, past_verb: str, target: discord.Member = None):
        gif_url = await self.fetch_gif(action_name)

        if target and target.id == ctx.author.id:
            desc = f"{ctx.author.mention} {past_verb} themselves"
        elif target:
            desc = f"{ctx.author.mention} {past_verb} {target.mention}"
        else:
            desc = f"{ctx.author.mention} is {past_verb}"

        embed = fleed_embed(description=desc, author=ctx.author, image=gif_url)
        await ctx.send(embed=embed)

    @commands.command(name="hug")
    async def hug(self, ctx, member: discord.Member):
        """Hug another server member"""
        await self.execute_rp(ctx, "hug", "hugged", member)

    @commands.command(name="kiss")
    async def kiss(self, ctx, member: discord.Member):
        """Give a sweet kiss to a member"""
        await self.execute_rp(ctx, "kiss", "kissed", member)

    @commands.command(name="slap")
    async def slap(self, ctx, member: discord.Member):
        """Slap a member across the face"""
        await self.execute_rp(ctx, "slap", "slapped", member)

    @commands.command(name="pat")
    async def pat(self, ctx, member: discord.Member):
        """Gently pat a member on the head"""
        await self.execute_rp(ctx, "pat", "patted", member)

    @commands.command(name="cuddle")
    async def cuddle(self, ctx, member: discord.Member):
        """Cuddle closely with a member"""
        await self.execute_rp(ctx, "cuddle", "cuddled", member)

    @commands.command(name="bite")
    async def bite(self, ctx, member: discord.Member):
        """Bite a member playfully or angrily"""
        await self.execute_rp(ctx, "bite", "bit", member)

    @commands.command(name="punch")
    async def punch(self, ctx, member: discord.Member):
        """Throw a punch at a member"""
        await self.execute_rp(ctx, "punch", "punched", member)

    @commands.command(name="stare")
    async def stare(self, ctx, member: discord.Member = None):
        """Stare intensely at a member or into the void"""
        await self.execute_rp(ctx, "stare", "stared at", member)

    @commands.command(name="tickle")
    async def tickle(self, ctx, member: discord.Member):
        """Tickle another member"""
        await self.execute_rp(ctx, "tickle", "tickled", member)

    @commands.command(name="feed")
    async def feed(self, ctx, member: discord.Member):
        """Feed delicious food to a member"""
        await self.execute_rp(ctx, "feed", "fed", member)

    @commands.command(name="highfive", aliases=["hf"])
    async def highfive(self, ctx, member: discord.Member):
        """High-five another member"""
        await self.execute_rp(ctx, "highfive", "high-fived", member)

    @commands.command(name="poke")
    async def poke(self, ctx, member: discord.Member):
        """Poke a member to get their attention"""
        await self.execute_rp(ctx, "poke", "poked", member)

    @commands.command(name="dance")
    async def dance(self, ctx, member: discord.Member = None):
        """Dance happily with a member or solo"""
        await self.execute_rp(ctx, "dance", "danced with", member)

    @commands.command(name="cry")
    async def cry(self, ctx):
        """Burst into tears in chat"""
        await self.execute_rp(ctx, "cry", "crying")

    @commands.command(name="blush")
    async def blush(self, ctx):
        """Blush shyly in chat"""
        await self.execute_rp(ctx, "blush", "blushing")

    @commands.command(name="shoot", aliases=["gunshoot"])
    async def shoot(self, ctx, member: discord.Member):
        """Playfully shoot at a member"""
        await self.execute_rp(ctx, "shoot", "shot", member)

    @commands.command(name="handhold")
    async def handhold(self, ctx, member: discord.Member):
        """Hold hands warmly with a member"""
        await self.execute_rp(ctx, "handhold", "held hands with", member)

    @commands.command(name="lick")
    async def lick(self, ctx, member: discord.Member):
        """Lick a member"""
        await self.execute_rp(ctx, "lick", "licked", member)

    @commands.command(name="wink")
    async def wink(self, ctx, member: discord.Member = None):
        """Wink at a member playfully"""
        await self.execute_rp(ctx, "wink", "winked at", member)

    @commands.command(name="wave")
    async def wave(self, ctx, member: discord.Member = None):
        """Wave hello to a member"""
        await self.execute_rp(ctx, "wave", "waved at", member)

    @commands.command(name="smile")
    async def smile(self, ctx, member: discord.Member = None):
        """Smile warmly at a member"""
        await self.execute_rp(ctx, "smile", "smiled at", member)

    @commands.command(name="pout")
    async def pout(self, ctx):
        """Pout in chat"""
        await self.execute_rp(ctx, "pout", "pouting")

    @commands.command(name="bonk")
    async def bonk(self, ctx, member: discord.Member):
        """Bonk a member over the head"""
        await self.execute_rp(ctx, "bonk", "bonked", member)

    @commands.command(name="kill")
    async def kill(self, ctx, member: discord.Member):
        """Anime-kill a member in roleplay"""
        await self.execute_rp(ctx, "kill", "killed", member)

    @commands.group(name="roleplay", invoke_without_command=True)
    async def roleplay(self, ctx):
        await send_group_help(ctx, ctx.command)

    @roleplay.command(name="list")
    async def roleplay_list(self, ctx):
        actions = ["hug", "kiss", "slap", "pat", "cuddle", "bite", "punch", "stare", "tickle", "feed", "highfive", "poke", "dance", "cry", "blush", "shoot", "handhold", "lick", "wink", "wave", "smile", "pout", "bonk", "kill"]
        await ctx.send(embed=fleed_embed(title="roleplay actions", description=", ".join(actions), author=ctx.author))

async def setup(bot):
    await bot.add_cog(Roleplay(bot))
