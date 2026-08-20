import discord
from discord.ext import commands
import datetime
from utils import fleed_embed, success_embed, warn_embed, send_group_help, send_paginated_embed

class Snipe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.snipes = {}
        self.edit_snipes = {}
        self.reaction_snipes = {}
        self.voice_snipes = {}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild or member.bot:
            return
        gid = member.guild.id
        if gid not in self.voice_snipes:
            self.voice_snipes[gid] = []

        now = datetime.datetime.now(datetime.timezone.utc)
        if before.channel and not after.channel:
            self.voice_snipes[gid].insert(0, {
                "member": member,
                "action": f"left {before.channel.mention}",
                "timestamp": now
            })
        elif before.channel and after.channel and before.channel != after.channel:
            self.voice_snipes[gid].insert(0, {
                "member": member,
                "action": f"moved {before.channel.mention} -> {after.channel.mention}",
                "timestamp": now
            })
        self.voice_snipes[gid] = self.voice_snipes[gid][:25]

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild and not message.author.bot:
            if message.channel.id not in self.snipes:
                self.snipes[message.channel.id] = []
            
            attachments = [a.proxy_url or a.url for a in message.attachments if a.url]
            stickers = [s.url for s in message.stickers if s.url]

            self.snipes[message.channel.id].insert(0, {
                "author": message.author,
                "content": message.content or "",
                "attachments": attachments,
                "stickers": stickers,
                "created_at": message.created_at
            })
            self.snipes[message.channel.id] = self.snipes[message.channel.id][:20]

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild and not before.author.bot and before.content != after.content:
            if before.channel.id not in self.edit_snipes:
                self.edit_snipes[before.channel.id] = []
            self.edit_snipes[before.channel.id].insert(0, {
                "author": before.author,
                "before": before.content,
                "after": after.content,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            })
            self.edit_snipes[before.channel.id] = self.edit_snipes[before.channel.id][:20]

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        if reaction.message.guild and not user.bot:
            if reaction.message.channel.id not in self.reaction_snipes:
                self.reaction_snipes[reaction.message.channel.id] = []
            self.reaction_snipes[reaction.message.channel.id].insert(0, {
                "author": user,
                "emoji": str(reaction.emoji),
                "message_id": reaction.message.id,
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            })
            self.reaction_snipes[reaction.message.channel.id] = self.reaction_snipes[reaction.message.channel.id][:20]

    @commands.hybrid_command(name="snipe", aliases=["s"])
    async def snipe(self, ctx, target: str = None):
        list_snipes = self.snipes.get(ctx.channel.id, [])
        if not list_snipes:
            return await ctx.send(embed=warn_embed("no deleted messages to snipe", ctx.author))
        
        index = 1
        filtered = list_snipes
        if target:
            if target.isdigit():
                index = int(target)
            else:
                clean_target = target.replace("<@", "").replace(">", "").replace("!", "").lower()
                filtered = [s for s in list_snipes if str(s["author"].id) == clean_target or clean_target in s["author"].name.lower() or clean_target in s["author"].display_name.lower()]
                if not filtered:
                    return await ctx.send(embed=warn_embed(f"no deleted messages from `{target.lower()}`", ctx.author))

        if index > len(filtered) or index < 1:
            return await ctx.send(embed=warn_embed(f"index out of range (1-{len(filtered)})", ctx.author))
        
        hit = filtered[index - 1]
        desc = hit["content"].lower() if hit["content"] else ""
        
        embed = fleed_embed(description=desc, author=hit["author"])
        if hit["attachments"]:
            embed.set_image(url=hit["attachments"][0])
        elif hit["stickers"]:
            embed.set_image(url=hit["stickers"][0])
            
        embed.set_footer(text=f"sniped message {index}/{len(filtered)}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="voicesnipe", aliases=["vs"])
    async def voicesnipe(self, ctx):
        actions = self.voice_snipes.get(ctx.guild.id, [])
        if not actions:
            return await ctx.send(embed=warn_embed("no recent voice channel actions", ctx.author))
        
        entries = [f"`{idx:02}` {a['member'].mention} {a['action']} (<t:{int(a['timestamp'].timestamp())}:R>)" for idx, a in enumerate(actions, 1)]
        await send_paginated_embed(ctx, f"voice actions ({len(actions)})", entries, per_page=10, item_name="actions")

    @commands.hybrid_command(name="snipesearch", aliases=["snipescan"])
    async def snipesearch(self, ctx, *, query: str):
        list_snipes = self.snipes.get(ctx.channel.id, [])
        matches = [s for s in list_snipes if query.lower() in s["content"].lower()]
        if not matches:
            return await ctx.send(embed=warn_embed(f"no deleted messages containing `{query.lower()}`", ctx.author))
        
        entries = [f"`{idx:02}` {m['author'].mention}: {m['content'][:60].lower()}" for idx, m in enumerate(matches, 1)]
        await send_paginated_embed(ctx, f"snipe search: '{query.lower()}'", entries, per_page=10, item_name="messages")

    @commands.hybrid_command(name="snipelist", aliases=["sl"])
    async def snipelist(self, ctx):
        list_snipes = self.snipes.get(ctx.channel.id, [])
        if not list_snipes:
            return await ctx.send(embed=warn_embed("no deleted messages in this channel", ctx.author))
        
        entries = []
        for i, s in enumerate(list_snipes, 1):
            txt = s["content"][:40] if s["content"] else "[attachment]"
            entries.append(f"`{i:02}` {s['author'].name.lower()}: {txt.lower()}")
        
        await send_paginated_embed(ctx, f"deleted messages ({len(list_snipes)})", entries, per_page=10, item_name="snipes")

    @commands.hybrid_command(name="editsnipe", aliases=["es"])
    async def editsnipe(self, ctx, index: int = 1):
        list_snipes = self.edit_snipes.get(ctx.channel.id, [])
        if not list_snipes or index > len(list_snipes) or index < 1:
            return await ctx.send(embed=warn_embed("no edited messages to snipe", ctx.author))
        
        target = list_snipes[index - 1]
        desc = f"before: {target['before'].lower()}\nafter: {target['after'].lower()}"
        embed = fleed_embed(description=desc, author=target["author"])
        embed.set_footer(text=f"edited message {index}/{len(list_snipes)}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="reactionsnipe", aliases=["rs"])
    async def reactionsnipe(self, ctx, index: int = 1):
        list_snipes = self.reaction_snipes.get(ctx.channel.id, [])
        if not list_snipes or index > len(list_snipes) or index < 1:
            return await ctx.send(embed=warn_embed("no removed reactions to snipe", ctx.author))
        
        target = list_snipes[index - 1]
        desc = f"removed {target['emoji']} from message `{target['message_id']}`"
        embed = fleed_embed(description=desc, author=target["author"])
        embed.set_footer(text=f"reaction snipe {index}/{len(list_snipes)}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearsnipe", aliases=["cs", "clearsnipes"])
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe(self, ctx):
        self.snipes.pop(ctx.channel.id, None)
        self.edit_snipes.pop(ctx.channel.id, None)
        self.reaction_snipes.pop(ctx.channel.id, None)
        await ctx.send(embed=success_embed("cleared all snipes for this channel", ctx.author))

    @commands.hybrid_command(name="cleareditsnipe", aliases=["ces"])
    @commands.has_permissions(manage_messages=True)
    async def cleareditsnipe(self, ctx):
        self.edit_snipes.pop(ctx.channel.id, None)
        await ctx.send(embed=success_embed("cleared edit snipes for this channel", ctx.author))

    @commands.hybrid_command(name="clearreactionsnipe", aliases=["crs"])
    @commands.has_permissions(manage_messages=True)
    async def clearreactionsnipe(self, ctx):
        self.reaction_snipes.pop(ctx.channel.id, None)
        await ctx.send(embed=success_embed("cleared reaction snipes for this channel", ctx.author))

async def setup(bot):
    await bot.add_cog(Snipe(bot))


