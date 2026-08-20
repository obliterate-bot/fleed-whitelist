import discord
from discord.ext import commands
import aiohttp
import datetime
import urllib.parse
import xml.etree.ElementTree as ET
from utils import fleed_embed, success_embed, error_embed, warn_embed, send_group_help


class Socials(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())

    async def cog_unload(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ==================== BIO LOOKUPS ====================

    @commands.group(name="bio", invoke_without_command=True)
    async def bio_group(self, ctx):
        await send_group_help(ctx, ctx.command, "socials")

    @bio_group.command(name="guns")
    async def bio_guns(self, ctx, username: str):
        target = username.lower().lstrip("@")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        try:
            import json
            async with self.session.get(f"https://guns.lol/{target}", headers=headers) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    idx = html.find(r'{\"data\":')
                    if idx != -1:
                        sub = html[idx:]
                        unescaped = sub.replace(r'\"', '"').replace(r'\\', '\\')
                        count = 0
                        end = 0
                        for i, c in enumerate(unescaped):
                            if c == '{':
                                count += 1
                            elif c == '}':
                                count -= 1
                                if count == 0:
                                    end = i + 1
                                    break
                        if end > 0:
                            parsed = json.loads(unescaped[:end])
                            data = parsed.get("data", {})
                            if data and data.get("username", "").lower() == target:
                                config = data.get("config", {}) or {}
                                bio = config.get("description") or "no bio provided"
                                display_name = config.get("display_name") or config.get("title") or target
                                avatar = config.get("avatar") or f"https://og.guns.lol/api/og?username={target}"
                                views = config.get("views", 0)

                                socials = []
                                for s in config.get("socials", []):
                                    s_name = s.get("social")
                                    s_val = s.get("value")
                                    if s_name and s_val:
                                        if s_val.startswith(("http://", "https://")):
                                            socials.append(f"[{s_name.lower()}]({s_val})")
                                        else:
                                            socials.append(f"{s_name.lower()}: `{s_val.lower()}`")

                                badges = [b.get("name") or b.get("badge") for b in data.get("badges", []) if isinstance(b, dict) and (b.get("name") or b.get("badge"))]
                                if data.get("verified"):
                                    badges.insert(0, "verified")
                                if data.get("premium"):
                                    badges.append("premium")

                                desc_lines = []
                                if display_name and display_name.lower() != target:
                                    desc_lines.append(f"**display:** {display_name.lower()}")
                                desc_lines.append(f"**bio:** {bio.lower()}")
                                if badges:
                                    desc_lines.append(f"**badges:** {', '.join(badges)}")
                                if data.get("account_created"):
                                    desc_lines.append(f"**created:** <t:{data['account_created']}:R>")
                                if views:
                                    desc_lines.append(f"**views:** {views:,}")
                                if socials:
                                    desc_lines.append(f"**socials:** {' • '.join(socials)}")
                                desc_lines.append(f"\n[guns.lol/{target}](https://guns.lol/{target})")

                                embed = fleed_embed(title=f"guns.lol — {target}", description="\n".join(desc_lines), author=ctx.author)
                                if avatar:
                                    embed.set_thumbnail(url=avatar)
                                return await ctx.send(embed=embed)
        except Exception:
            pass
        await ctx.send(embed=fleed_embed(title=f"guns.lol — {target}", description=f"profile: https://guns.lol/{target}", author=ctx.author))

    @bio_group.command(name="haunt")
    async def bio_haunt(self, ctx, username: str):
        target = username.lower().lstrip("@")
        await ctx.send(embed=fleed_embed(title=f"haunt.bio — {target}", description=f"profile: https://haunt.bio/{target}", author=ctx.author))

    # ==================== ROBLOX LOOKUPS ====================

    @commands.group(name="roblox", aliases=["rbx"], invoke_without_command=True)
    async def roblox_group(self, ctx, username: str = None):
        if not username:
            return await send_group_help(ctx, ctx.command)
        await self.roblox_user(ctx, username)

    @roblox_group.command(name="user", aliases=["u"])
    async def roblox_user(self, ctx, username: str):
        try:
            # 1. Resolve username to user ID
            payload = {"usernames": [username], "excludeBannedUsers": False}
            async with self.session.post("https://users.roblox.com/v1/usernames/users", json=payload) as resp:
                data = await resp.json()
                users = data.get("data", [])
                if not users:
                    return await ctx.send(embed=warn_embed(f"roblox user `{username.lower()}` not found", ctx.author))
                user_id = users[0]["id"]
                display_name = users[0]["displayName"]
                real_name = users[0]["name"]

            # 2. Get profile details & ban status
            async with self.session.get(f"https://users.roblox.com/v1/users/{user_id}") as resp:
                profile = await resp.json()

            # 3. Get Friends, Followers, Following count
            friends_count = 0
            followers_count = 0
            following_count = 0
            try:
                async with self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/friends/count") as r:
                    friends_count = (await r.json()).get("count", 0)
                async with self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/followers/count") as r:
                    followers_count = (await r.json()).get("count", 0)
                async with self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/followings/count") as r:
                    following_count = (await r.json()).get("count", 0)
            except Exception:
                pass

            # 4. Get Presence (Online/In-Game/Studio/Offline)
            presence_status = "offline"
            try:
                async with self.session.post("https://presence.roblox.com/v1/presence/users", json={"userIds": [user_id]}) as r:
                    pres_data = await r.json()
                    presences = pres_data.get("userPresences", [])
                    if presences:
                        ptype = presences[0].get("userPresenceType", 0)
                        types_map = {0: "offline", 1: "online", 2: "in-game", 3: "in-studio"}
                        presence_status = types_map.get(ptype, "offline")
                        loc = presences[0].get("lastLocation")
                        if loc and ptype == 2:
                            clean_loc = loc.replace("`", "").strip()
                            presence_status = f"playing {clean_loc.lower()}"
            except Exception:
                pass

            # 5. Get avatar headshot thumbnail
            avatar_url = None
            async with self.session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png&isCircular=false") as resp:
                thumb_data = await resp.json()
                if thumb_data.get("data"):
                    avatar_url = thumb_data["data"][0].get("imageUrl")

            created_str = profile.get("created", "")
            created_fmt = "unknown"
            if created_str:
                try:
                    dt = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    created_fmt = f"<t:{int(dt.timestamp())}:R>"
                except Exception:
                    created_fmt = f"`{created_str[:10]}`"

            banned = profile.get("isBanned", False)

            desc = (
                f"**username:** [{real_name.lower()}](https://www.roblox.com/users/{user_id}/profile)\n"
                f"**display:** {display_name.lower()}\n"
                f"**id:** `{user_id}`\n"
                f"**status:** `{presence_status}`\n"
                f"**banned:** `{'yes' if banned else 'no'}`\n"
                f"**created:** {created_fmt}\n"
                f"**friends:** {friends_count:,} • **followers:** {followers_count:,} • **following:** {following_count:,}"
            )

            if profile.get("description"):
                desc += f"\n\n*\"{profile['description'][:250].lower()}\"*"

            embed = fleed_embed(title=f"roblox — {real_name.lower()}", description=desc, author=ctx.author)
            if avatar_url:
                embed.set_thumbnail(url=avatar_url)
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to lookup roblox user", ctx.author))

    @roblox_group.command(name="avatar", aliases=["av"])
    async def roblox_avatar(self, ctx, username: str):
        try:
            payload = {"usernames": [username], "excludeBannedUsers": False}
            async with self.session.post("https://users.roblox.com/v1/usernames/users", json=payload) as resp:
                data = await resp.json()
                users = data.get("data", [])
                if not users:
                    return await ctx.send(embed=warn_embed(f"roblox user `{username.lower()}` not found", ctx.author))
                user_id = users[0]["id"]
                real_name = users[0]["name"]

            async with self.session.get(f"https://thumbnails.roblox.com/v1/users/avatar?userIds={user_id}&size=720x720&format=Png&isCircular=false") as resp:
                thumb_data = await resp.json()
                if thumb_data.get("data"):
                    avatar_url = thumb_data["data"][0].get("imageUrl")
                    embed = fleed_embed(title=f"roblox avatar — {real_name.lower()}", description=f"[profile link](https://www.roblox.com/users/{user_id}/profile)", author=ctx.author)
                    embed.set_image(url=avatar_url)
                    return await ctx.send(embed=embed)
            await ctx.send(embed=warn_embed("avatar render not available", ctx.author))
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch avatar", ctx.author))

    # ==================== URBAN DICTIONARY ====================

    @commands.hybrid_command(name="urban", aliases=["ud"])
    async def urban(self, ctx, *, term: str):
        try:
            async with self.session.get(f"https://api.urbandictionary.com/v0/define?term={urllib.parse.quote(term)}") as resp:
                data = await resp.json()
                entries = data.get("list", [])
                if not entries:
                    return await ctx.send(embed=warn_embed(f"no definition found for `{term.lower()}`", ctx.author))

                top = entries[0]
                clean_def = top["definition"].replace("[", "").replace("]", "")[:1000].lower()
                clean_ex = top["example"].replace("[", "").replace("]", "")[:300].lower()

                author = top.get("author", "anonymous").lower()
                written = top.get("written_on", "")
                time_str = ""
                if written:
                    try:
                        dt = datetime.datetime.fromisoformat(written.replace("Z", "+00:00"))
                        time_str = f" • <t:{int(dt.timestamp())}:R>"
                    except Exception:
                        pass

                desc = f"**definition**\n{clean_def}"
                if clean_ex:
                    desc += f"\n\n**example**\n*{clean_ex}*"

                desc += f"\n\n**author:** `{author}`{time_str}\n[open on urbandictionary]({top.get('permalink', '')})"

                embed = fleed_embed(title=f"urban dictionary — {term.lower()}", description=desc, author=ctx.author)
                embed.set_footer(text=f"thumbs up: {top.get('thumbs_up', 0):,} | thumbs down: {top.get('thumbs_down', 0):,}")
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to query urban dictionary", ctx.author))

    # ==================== CRYPTO TICKER ====================

    @commands.hybrid_command(name="ticker", aliases=["cg", "coingecko"])
    async def ticker(self, ctx, coin: str = "bitcoin"):
        try:
            coin_id = coin.lower()
            aliases = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana", "ltc": "litecoin", "xmr": "monero", "doge": "dogecoin", "xrp": "ripple"}
            coin_id = aliases.get(coin_id, coin_id)

            async with self.session.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&community_data=false&developer_data=false") as resp:
                if resp.status != 200:
                    # Fallback to simple price
                    async with self.session.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true&include_market_cap=true") as s_resp:
                        s_data = await s_resp.json()
                        if coin_id not in s_data:
                            return await ctx.send(embed=warn_embed(f"crypto coin `{coin.lower()}` not found", ctx.author))
                        info = s_data[coin_id]
                        price = info.get("usd", 0)
                        change = info.get("usd_24h_change", 0)
                        mcap = info.get("usd_market_cap", 0)
                        sign = "+" if change >= 0 else ""
                        desc = f"**price:** ${price:,.2f} USD\n**24h change:** {sign}{change:.2f}%\n**market cap:** ${mcap:,.0f}"
                        return await ctx.send(embed=fleed_embed(title=f"crypto — {coin_id}", description=desc, author=ctx.author))

                cd = await resp.json()
                md = cd.get("market_data", {})
                symbol = cd.get("symbol", coin_id).upper()
                rank = cd.get("market_cap_rank", "N/A")
                price = md.get("current_price", {}).get("usd", 0)
                change_24h = md.get("price_change_percentage_24h", 0) or 0
                high_24h = md.get("high_24h", {}).get("usd", 0)
                low_24h = md.get("low_24h", {}).get("usd", 0)
                mcap = md.get("market_cap", {}).get("usd", 0)
                volume = md.get("total_volume", {}).get("usd", 0)
                ath = md.get("ath", {}).get("usd", 0)
                ath_change = md.get("ath_change_percentage", {}).get("usd", 0) or 0

                sign = "+" if change_24h >= 0 else ""
                desc = (
                    f"**price:** ${price:,.2f} USD ({symbol})\n"
                    f"**rank:** `#{rank}`\n"
                    f"**24h change:** `{sign}{change_24h:.2f}%`\n"
                    f"**24h high / low:** `${high_24h:,.2f}` / `${low_24h:,.2f}`\n"
                    f"**market cap:** `${mcap:,.0f}`\n"
                    f"**24h volume:** `${volume:,.0f}`\n"
                    f"**all-time high:** `${ath:,.2f}` (`{ath_change:.2f}%`)"
                )

                embed = fleed_embed(title=f"crypto — {cd.get('name', coin_id).lower()}", description=desc, author=ctx.author)
                img = cd.get("image", {}).get("large")
                if img:
                    embed.set_thumbnail(url=img)
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to fetch crypto price", ctx.author))

    # ==================== GITHUB LOOKUPS ====================

    @commands.hybrid_group(name="github", aliases=["gh"], invoke_without_command=True)
    async def github_group(self, ctx, username: str = None):
        if not username:
            return await send_group_help(ctx, ctx.command)
        await self.github_user(ctx, username)

    @github_group.command(name="user")
    async def github_user(self, ctx, username: str):
        try:
            async with self.session.get(f"https://api.github.com/users/{username}") as resp:
                if resp.status != 200:
                    return await ctx.send(embed=warn_embed(f"github user `{username.lower()}` not found", ctx.author))
                data = await resp.json()

                name = data.get("name") or data.get("login")
                login = data.get("login")
                bio = data.get("bio") or "no bio provided"
                location = data.get("location")
                company = data.get("company")
                blog = data.get("blog")
                twitter = data.get("twitter_username")
                repos = data.get("public_repos", 0)
                gists = data.get("public_gists", 0)
                followers = data.get("followers", 0)
                following = data.get("following", 0)

                created_raw = data.get("created_at")
                created_str = ""
                if created_raw:
                    try:
                        dt = datetime.datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                        created_str = f"<t:{int(dt.timestamp())}:R>"
                    except Exception:
                        created_str = f"`{created_raw[:10]}`"

                desc_lines = [
                    f"**name:** [{name.lower()}](https://github.com/{login})",
                    f"**bio:** {bio.lower()}",
                ]
                if company:
                    desc_lines.append(f"**company:** {company.lower()}")
                if location:
                    desc_lines.append(f"**location:** {location.lower()}")
                if blog:
                    blog_url = blog if blog.startswith("http") else f"https://{blog}"
                    desc_lines.append(f"**website:** [{blog.lower()}]({blog_url})")
                if twitter:
                    desc_lines.append(f"**twitter:** [@{twitter.lower()}](https://x.com/{twitter})")

                desc_lines.append(f"**repositories:** {repos:,} • **gists:** {gists:,}")
                desc_lines.append(f"**followers:** {followers:,} • **following:** {following:,}")
                if created_str:
                    desc_lines.append(f"**joined:** {created_str}")

                embed = fleed_embed(title=f"github — {login.lower()}", description="\n".join(desc_lines), author=ctx.author)
                if data.get("avatar_url"):
                    embed.set_thumbnail(url=data["avatar_url"])
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to lookup github user", ctx.author))

    @github_group.command(name="repo")
    async def github_repo(self, ctx, repo_path: str):
        try:
            clean_path = repo_path.strip().replace("https://github.com/", "").rstrip("/")
            async with self.session.get(f"https://api.github.com/repos/{clean_path}") as resp:
                if resp.status != 200:
                    return await ctx.send(embed=warn_embed(f"github repo `{clean_path.lower()}` not found", ctx.author))
                data = await resp.json()

                full_name = data.get("full_name", clean_path)
                desc_text = data.get("description") or "no description provided"
                lang = data.get("language") or "none"
                stars = data.get("stargazers_count", 0)
                forks = data.get("forks_count", 0)
                issues = data.get("open_issues_count", 0)
                watchers = data.get("watchers_count", 0)
                default_branch = data.get("default_branch", "main")
                license_name = (data.get("license") or {}).get("spdx_id") or "none"

                updated_raw = data.get("pushed_at") or data.get("updated_at")
                updated_str = ""
                if updated_raw:
                    try:
                        dt = datetime.datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                        updated_str = f"<t:{int(dt.timestamp())}:R>"
                    except Exception:
                        pass

                desc_lines = [
                    f"**repository:** [{full_name.lower()}](https://github.com/{full_name})",
                    f"**description:** {desc_text.lower()}",
                    f"**language:** `{lang.lower()}` • **license:** `{license_name.lower()}` • **branch:** `{default_branch}`",
                    f"**stars:** {stars:,} • **forks:** {forks:,} • **issues:** {issues:,} • **watchers:** {watchers:,}"
                ]
                if updated_str:
                    desc_lines.append(f"**last update:** {updated_str}")

                embed = fleed_embed(title=f"github repo — {data.get('name', clean_path).lower()}", description="\n".join(desc_lines), author=ctx.author)
                owner = data.get("owner", {})
                if owner.get("avatar_url"):
                    embed.set_thumbnail(url=owner["avatar_url"])
                await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to lookup github repo", ctx.author))

    # ==================== STEAM LOOKUPS ====================

    @commands.command(name="steam")
    async def steam_cmd(self, ctx, *, username: str):
        clean_target = username.strip().replace("https://steamcommunity.com/id/", "").replace("https://steamcommunity.com/profiles/", "").rstrip("/")
        url = f"https://steamcommunity.com/profiles/{clean_target}/?xml=1" if clean_target.isdigit() else f"https://steamcommunity.com/id/{clean_target}/?xml=1"
        try:
            async with self.session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    xml_text = await resp.text()
                    root = ET.fromstring(xml_text)
                    steam_id = root.findtext('steamID')
                    if steam_id:
                        steam_id64 = root.findtext('steamID64')
                        state = root.findtext('stateMessage') or root.findtext('onlineState') or "offline"
                        avatar = root.findtext('avatarFull') or root.findtext('avatarMedium')
                        vac_banned = root.findtext('vacBanned') == "1"
                        trade_ban = root.findtext('tradeBanState') or "None"
                        member_since = root.findtext('memberSince')
                        custom_url = root.findtext('customURL')
                        summary = root.findtext('summary')

                        profile_link = f"https://steamcommunity.com/profiles/{steam_id64}" if steam_id64 else f"https://steamcommunity.com/id/{clean_target}"
                        
                        desc_lines = [
                            f"**name:** [{steam_id.lower()}]({profile_link})",
                            f"**status:** `{state.lower()}`",
                            f"**vac ban:** `{'banned' if vac_banned else 'clean'}` • **trade ban:** `{trade_ban.lower()}`",
                            f"**id64:** `{steam_id64}`",
                        ]
                        if custom_url:
                            desc_lines.append(f"**custom url:** `{custom_url.lower()}`")
                        if member_since:
                            desc_lines.append(f"**member since:** `{member_since}`")
                        if summary:
                            clean_sum = summary.replace("<br>", "\n").replace("[b]", "").replace("[/b]", "")[:200].strip()
                            if clean_sum:
                                desc_lines.append(f"\n*\"{clean_sum.lower()}\"*")

                        embed = fleed_embed(title=f"steam — {steam_id.lower()}", description="\n".join(desc_lines), author=ctx.author)
                        if avatar:
                            embed.set_thumbnail(url=avatar)
                        return await ctx.send(embed=embed)
        except Exception:
            pass
        await ctx.send(embed=fleed_embed(title=f"steam — {clean_target.lower()}", description=f"profile: https://steamcommunity.com/id/{clean_target}", author=ctx.author))

    # ==================== OTHER SOCIAL PROFILE RESOLVERS ====================

    @commands.command(name="valorant", aliases=["val"])
    async def valorant_cmd(self, ctx, username: str, *, tag: str = None):
        clean_tag = (tag or "NA1").lstrip("#")
        try:
            url = f"https://api.henrikdev.xyz/valorant/v1/mmr/na/{urllib.parse.quote(username)}/{urllib.parse.quote(clean_tag)}"
            async with self.session.get(url, timeout=15) as resp:
                payload = await resp.json(content_type=None)
            data = payload.get("data") if isinstance(payload, dict) else None
            if resp.status != 200 or not data:
                return await ctx.send(embed=warn_embed(f"could not find valorant player `{username.lower()}#{clean_tag.lower()}`", ctx.author))
            
            desc = (
                f"**rank:** `{data.get('currenttierpatched', 'unranked').lower()}`\n"
                f"**rating:** `{data.get('ranking_in_tier', 0)} RR`\n"
                f"**last change:** `{data.get('mmr_change_to_last_game', 0)} RR`\n"
                f"**elo:** `{data.get('elo', 0):,}`\n\n"
                f"[tracker.gg profile](https://tracker.gg/valorant/profile/riot/{urllib.parse.quote(username)}%23{urllib.parse.quote(clean_tag)}/overview)"
            )
            embed = fleed_embed(title=f"valorant — {username.lower()}#{clean_tag.lower()}", description=desc, author=ctx.author)
            icon = (data.get("images") or {}).get("small") if isinstance(data.get("images"), dict) else None
            if icon:
                embed.set_thumbnail(url=icon)
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send(embed=error_embed("failed to look up that valorant player", ctx.author))

    @commands.command(name="telegram", aliases=["tg"])
    async def telegram_cmd(self, ctx, *, channel_or_user: str):
        target = channel_or_user.lstrip("@")
        desc = f"**channel / user:** `@{target.lower()}`\n**link:** [t.me/{target}](https://t.me/{target})"
        embed = fleed_embed(title=f"telegram — @{target.lower()}", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

    @commands.command(name="instagram", aliases=["ig", "insta"])
    async def instagram_cmd(self, ctx, *, username: str):
        target = username.lstrip("@")
        desc = f"**username:** `@{target.lower()}`\n**profile:** [instagram.com/{target}](https://instagram.com/{target})"
        embed = fleed_embed(title=f"instagram — @{target.lower()}", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

    @commands.command(name="tiktok", aliases=["tik", "tok"])
    async def tiktok_cmd(self, ctx, *, username: str):
        target = username.lstrip("@")
        desc = f"**username:** `@{target.lower()}`\n**profile:** [tiktok.com/@{target}](https://tiktok.com/@{target})"
        embed = fleed_embed(title=f"tiktok — @{target.lower()}", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

    @commands.command(name="twitter", aliases=["tweet", "tw"])
    async def twitter_cmd(self, ctx, *, username: str):
        target = username.lstrip("@")
        desc = f"**handle:** `@{target.lower()}`\n**profile:** [x.com/{target}](https://x.com/{target})"
        embed = fleed_embed(title=f"x (twitter) — @{target.lower()}", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

    @commands.command(name="youtube", aliases=["yt"])
    async def youtube_cmd(self, ctx, *, query: str):
        encoded = urllib.parse.quote(query)
        desc = f"[**search results for `{query.lower()}` on youtube**](https://www.youtube.com/results?search_query={encoded})"
        await ctx.send(embed=fleed_embed(title="youtube search", description=desc, author=ctx.author))

    @commands.command(name="twitch", aliases=["ttv"])
    async def twitch_cmd(self, ctx, *, channel: str):
        target = channel.lstrip("@")
        desc = f"**channel:** `{target.lower()}`\n**stream:** [twitch.tv/{target}](https://twitch.tv/{target})"
        embed = fleed_embed(title=f"twitch — {target.lower()}", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

    @commands.command(name="reddit", aliases=["sub", "subreddit"])
    async def reddit_cmd(self, ctx, *, subreddit: str):
        target = subreddit.replace("r/", "").lstrip("/")
        desc = f"**subreddit:** `r/{target.lower()}`\n**community:** [reddit.com/r/{target}](https://reddit.com/r/{target})"
        embed = fleed_embed(title=f"reddit — r/{target.lower()}", description=desc, author=ctx.author)
        await ctx.send(embed=embed)

    @commands.command(name="spotifysearch", aliases=["spotsearch"])
    async def spotify_search_cmd(self, ctx, *, query: str):
        encoded = urllib.parse.quote(query)
        desc = f"[**search `{query.lower()}` on spotify**](https://open.spotify.com/search/{encoded})"
        await ctx.send(embed=fleed_embed(title="spotify search", description=desc, author=ctx.author))

    @commands.command(name="reposters")
    async def reposters_cmd(self, ctx):
        await ctx.send(embed=fleed_embed(
            title="media reposters",
            description="this build does not host media reposting. use `instagram`, `tiktok`, `twitter`, and `reddit` to get direct profile links instead.",
            author=ctx.author,
        ))


async def setup(bot):
    await bot.add_cog(Socials(bot))

