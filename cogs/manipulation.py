import discord
from discord.ext import commands
from utils import fleed_embed, success_embed, error_embed

class Manipulation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def render_filter(self, ctx, effect: str, member: discord.Member = None, text: str = None):
        target = member or ctx.author
        desc = f"applied **{effect}** effect to {target.display_name.lower()}'s avatar"
        if text:
            desc += f"\ntext: {text.lower()}"
        embed = fleed_embed(title=f"image {effect}", description=desc, author=target)
        embed.set_image(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="imagefilter", aliases=["imgfilter", "manipulate"])
    async def filter_cmd(self, ctx, effect: str = "blur", member: discord.Member = None, *, text: str = None):
        await self.render_filter(ctx, effect, member, text)

    @commands.command(name="wiggle")
    async def wiggle(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "wiggle", member)

    @commands.command(name="wall")
    async def wall(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "wall", member)

    @commands.command(name="hearts")
    async def hearts(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "hearts", member)

    @commands.command(name="neon")
    async def neon(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "neon", member)

    @commands.command(name="warp")
    async def warp(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "warp", member)

    @commands.command(name="infinity")
    async def infinity(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "infinity", member)

    @commands.command(name="optics")
    async def optics(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "optics", member)

    @commands.command(name="layers")
    async def layers(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "layers", member)

    @commands.command(name="melt")
    async def melt(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "melt", member)

    @commands.command(name="halfinvert")
    async def halfinvert(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "halfinvert", member)

    @commands.command(name="minecraft")
    async def minecraft(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "minecraft", member)

    @commands.command(name="3d")
    async def three_d(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "3d", member)

    @commands.command(name="ads")
    async def ads(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "ads", member)

    @commands.command(name="bayer")
    async def bayer(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "bayer", member)

    @commands.command(name="bevel")
    async def bevel(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "bevel", member)

    @commands.command(name="drip")
    async def drip(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "drip", member)

    @commands.command(name="tunnel")
    async def tunnel(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "tunnel", member)

    @commands.command(name="tv")
    async def tv(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "tv", member)

    @commands.command(name="wanted")
    async def wanted(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "wanted", member)

    @commands.command(name="glitch")
    async def glitch(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "glitch", member)

    @commands.command(name="magnify")
    async def magnify(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "magnify", member)

    @commands.command(name="stretch")
    async def stretch(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "stretch", member)

    @commands.command(name="globe")
    async def globe(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "globe", member)

    @commands.command(name="matrix")
    async def matrix(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "matrix", member)

    @commands.command(name="tiles")
    async def tiles(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "tiles", member)

    @commands.command(name="drake")
    async def drake(self, ctx, top_text: str, bottom_text: str):
        await self.render_filter(ctx, "drake", ctx.author, f"top: {top_text} | bot: {bottom_text}")

    @commands.command(name="gallery")
    async def gallery(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "gallery", member)

    @commands.command(name="logoff")
    async def logoff(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "logoff", member)

    @commands.command(name="sadcat")
    async def sadcat(self, ctx, *, text: str):
        await self.render_filter(ctx, "sadcat", ctx.author, text)

    @commands.command(name="supreme")
    async def supreme(self, ctx, *, text: str):
        await self.render_filter(ctx, "supreme", ctx.author, text)

    @commands.command(name="earthquake")
    async def earthquake(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "earthquake", member)

    @commands.command(name="gameboy")
    async def gameboy(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "gameboy", member)

    @commands.command(name="lsd")
    async def lsd(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "lsd", member)

    @commands.command(name="facts")
    async def facts(self, ctx, *, text: str):
        await self.render_filter(ctx, "facts", ctx.author, text)

    @commands.command(name="dizzy")
    async def dizzy(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "dizzy", member)

    @commands.command(name="oogway")
    async def oogway(self, ctx, *, text: str):
        await self.render_filter(ctx, "oogway", ctx.author, text)

    @commands.command(name="didyoumean")
    async def didyoumean(self, ctx, top: str, bottom: str):
        await self.render_filter(ctx, "didyoumean", ctx.author, f"{top} -> {bottom}")

    @commands.command(name="dither")
    async def dither(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "dither", member)

    @commands.command(name="pooh")
    async def pooh(self, ctx, text1: str, text2: str):
        await self.render_filter(ctx, "pooh", ctx.author, f"{text1} vs {text2}")

    @commands.command(name="captcha")
    async def captcha(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "captcha", member)

    @commands.command(name="cube")
    async def cube(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "cube", member)

    @commands.command(name="alert")
    async def alert(self, ctx, *, text: str):
        await self.render_filter(ctx, "alert", ctx.author, text)

    @commands.command(name="calling")
    async def calling(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "calling", member)

    @commands.command(name="cracks")
    async def cracks(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "cracks", member)

    @commands.command(name="gun")
    async def gun(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "gun", member)

    @commands.command(name="cow")
    async def cow(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "cow", member)

    @commands.command(name="console")
    async def console(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "console", member)

    @commands.command(name="spin")
    async def spin(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "spin", member)

    @commands.command(name="canny")
    async def canny(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "canny", member)

    @commands.command(name="clock")
    async def clock(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "clock", member)

    @commands.command(name="stereo")
    async def stereo(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "stereo", member)

    @commands.command(name="ship")
    async def ship(self, ctx, user1: discord.Member, user2: discord.Member = None):
        target2 = user2 or ctx.author
        await ctx.send(embed=fleed_embed(title="compatibility match", description=f"{user1.mention} + {target2.mention} = 88% love", author=ctx.author))

    @commands.command(name="cinema")
    async def cinema(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "cinema", member)

    @commands.command(name="lines")
    async def lines(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "lines", member)

    @commands.command(name="cartoon")
    async def cartoon(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "cartoon", member)

    @commands.command(name="fire")
    async def fire(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "fire", member)

    @commands.command(name="liquefy")
    async def liquefy(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "liquefy", member)

    @commands.command(name="slice")
    async def slice_img(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "slice", member)

    @commands.command(name="bonks")
    async def bonks(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "bonks", member)

    @commands.command(name="flush")
    async def flush(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "flush", member)

    @commands.command(name="laundry")
    async def laundry(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "laundry", member)

    @commands.command(name="soap")
    async def soap(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "soap", member)

    @commands.command(name="bomb")
    async def bomb(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "bomb", member)

    @commands.command(name="fall")
    async def fall(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "fall", member)

    @commands.command(name="letters")
    async def letters(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "letters", member)

    @commands.command(name="fan")
    async def fan(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "fan", member)

    @commands.command(name="shock")
    async def shock(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "shock", member)

    @commands.command(name="boil")
    async def boil(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "boil", member)

    @commands.command(name="knit")
    async def knit(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "knit", member)

    @commands.command(name="shred")
    async def shred(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "shred", member)

    @commands.command(name="blur")
    async def blur(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "blur", member)

    @commands.command(name="equations")
    async def equations(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "equations", member)

    @commands.command(name="lamp")
    async def lamp(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "lamp", member)

    @commands.command(name="shear")
    async def shear(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "shear", member)

    @commands.command(name="blocks")
    async def blocks(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "blocks", member)

    @commands.command(name="explicit")
    async def explicit(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "explicit", member)

    @commands.command(name="invert")
    async def invert(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "invert", member)

    @commands.command(name="shine")
    async def shine(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "shine", member)

    @commands.command(name="billboard")
    async def billboard(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "billboard", member)

    @commands.command(name="emojify")
    async def emojify(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "emojify", member)

    @commands.command(name="ipcam")
    async def ipcam(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "ipcam", member)

    @commands.command(name="endless")
    async def endless(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "endless", member)

    @commands.command(name="zonk")
    async def zonk(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "zonk", member)

    @commands.command(name="ripped")
    async def ripped(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "ripped", member)

    @commands.command(name="sensitive")
    async def sensitive(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "sensitive", member)

    @commands.command(name="rain")
    async def rain(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "rain", member)

    @commands.command(name="reflection")
    async def reflection(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "reflection", member)

    @commands.command(name="pyramid")
    async def pyramid(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "pyramid", member)

    @commands.command(name="radiate")
    async def radiate(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "radiate", member)

    @commands.command(name="poly")
    async def poly(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "poly", member)

    @commands.command(name="print")
    async def print_img(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "print", member)

    @commands.command(name="plank")
    async def plank(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "plank", member)

    @commands.command(name="plates")
    async def plates(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "plates", member)

    @commands.command(name="phase")
    async def phase(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "phase", member)

    @commands.command(name="phone")
    async def phone(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "phone", member)

    @commands.command(name="patpat")
    async def patpat(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "patpat", member)

    @commands.command(name="pattern")
    async def pattern(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "pattern", member)

    @commands.command(name="painting")
    async def painting(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "painting", member)

    @commands.command(name="paparazzi")
    async def paparazzi(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "paparazzi", member)

    @commands.command(name="pixelate", aliases=["pixel"])
    async def pixelate(self, ctx, member: discord.Member = None):
        await self.render_filter(ctx, "pixelate", member)

async def setup(bot):
    await bot.add_cog(Manipulation(bot))
