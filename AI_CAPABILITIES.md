# Fleed AI capabilities

## Live server awareness

The AI now receives a live, permission-filtered snapshot of the current Discord server:

- Visible channels, categories, topics, channel IDs, and channel mentions
- Members, display names, usernames, user IDs, mentions, statuses, and roles
- Server roles and role membership counts
- The current speaker and their relevant Discord permissions
- Recent messages when a user asks for a summary, searches chat, or asks what someone said

Private channels and message history the requesting member cannot access are excluded.

## Natural-language actions

The action planner can:

- Run any registered prefix command and nested subcommand
- Run a current-channel command in another visible channel
- Send a plain message to a chosen channel
- Send a rich embed with title, description, color, fields, footer, thumbnail, and image
- Broadcast rich embeds or messages to multiple channels simultaneously
- Create public threads, add starter messages, pin/unpin messages, and react with emojis
- Perform targeted message purges (bots, links, images, invites, embeds, files, humans)
- Trigger emergency server lockdowns and unlocks (`lockdown all`, `unlockdown all`)
- Adjust channel slowmodes (`slowmode 5s`, `slowmode disable`)
- Execute mass role grants and removals (`role all add`, `role humans add`, `role bots add`)
- Launch timed giveaways with custom durations, winner counts, and prizes
- Clean and standardize server channel and role formatting (capitalization, dashes, lowercase)
- Configure automated autoresponders and triggers

## Examples

- `purge 50 bot messages in #general`
- `clean 20 links in #media`
- `lock down the server` / `unlock all channels`
- `set slowmode to 5s in #general` / `turn off slowmode in #chat`
- `give @Member to all humans` / `remove @Event from all members`
- `start a 24h giveaway in #giveaways with 2 winners for Discord Nitro`
- `fix the capitalization on all lowercase roles`
- `format all channels with a ・ so like ・gen`
- `add appropriate emojis to all the channel names`
- `format all channels with dashes and lowercase`
- `when someone says .gg reply with https://discord.gg/fleed`
- `send a blue embed in #announcements and #updates titled Maintenance with description Starts at 10 PM`
- `disconnect everyone in #general-vc` / `mute all in #study-vc`
- `summarize what happened in #general`
- `what did daniel say in #updates?`

## Permission behavior

AI actions never bypass the requesting member's Discord permissions. Registered commands still run through Discord.py's normal checks, converters, cooldowns, owner restrictions, and bot permission checks. Cross-channel actions also require both the member and bot to see and send in the target channel.

## Universal bulk mode

The AI can plan up to 50 mixed actions from one natural-language request. Bulk plans may include any registered command plus messages, embeds, threads, reactions, pins, and unpins across permitted channels.

Examples:

- `fix every obviously misspelled role name`
- `give these five users the event role`
- `send this announcement to every public event channel`
- `purge 10 messages in #bot-spam, #commands, and #testing`
- `lock all staff-only channels`
- `create feedback threads in each project channel`

Every multi-action plan is shown in a preview embed and must be confirmed by the requesting member. Each item then runs sequentially with its normal Discord permissions, hierarchy rules, command checks, cooldowns, and bot permissions. Invalid, duplicate, ambiguous, or inaccessible targets are skipped or rejected.

## universal dynamic routing (latest update)

- the router's live catalog now lists **every registered command** with aliases and runtime signatures. the compact catalog is marked authoritative for the llm, so any command — including deeply nested subcommands — can be planned from natural language, not just the top-ranked candidates (detailed candidates raised 100 -> 150).
- **api-free fallback router**: if every ai provider fails or times out, a local matcher still routes your words against all command names, aliases, and descriptions, fills in members/roles/channels/numbers/durations from your message, and executes through the normal invoker (permissions and confirmations still fully enforced). it never invents required targets; when a clear command match is incomplete, it asks for the missing argument and shows the exact syntax.
- **channel emoji theming works offline** too: "add appropriate emojis to all the channel names" builds a keyword-matched emoji rename plan per channel (announcements -> 📢, clips -> 🎬, etc.) with the usual preview + confirm flow.
- routed command lines are **fuzzy-corrected** before execution (casing, extra spaces, filler words like "run"/"please", aliases, and conservative command-name typos are resolved onto the canonical registered command), so near-miss plans still run the right command.
- every model-generated action is validated against the live command registry before execution. invented commands, malformed channel IDs, duplicate bulk actions, and ambiguous fuzzy matches are rejected rather than run in the wrong place.
- action routing can use Groq, OpenRouter, or an OpenAI-compatible endpoint when configured, then falls back to the local matcher if all configured providers fail.
- the chat responder can **no longer claim an action is pending**: if no action was routed, it says so and gives you the exact prefix command instead of pretending a preview is coming.
- the deterministic bulk channel formatter no longer intercepts creative requests (emojis, icons, themes, aesthetics) — those always reach the smart planner.

### name resolution without pings
- "show me fleeds pfp", "mute daniel for 10m", "ban carlos for spamming" — plain names now resolve with no @ping needed. usernames, display names, global names, and possessives ("fleeds") are matched case-insensitively against the live member cache, **including bot users** like fleed itself.
- the ai router's entity context now surfaces name-matched members (bots included) as exact mention ids, and is instructed to never refuse an action just because the target wasn't pinged; unmatched names pass through so discord's own converters get a shot.
- the offline fallback router does the same name resolution when filling member arguments, so this works even with every ai api down.
- a bare leading bot name ("fleed do x") is treated as addressing the bot, not as the target. explicit pings always take priority over names in text.

### conversation memory + follow-up actions (latest update)
- the action router now sees the last few messages in the channel, so follow-ups like "ping all those and next to each of them put - Record: 0-0 in one team per line" resolve "those" to the roles/channels/members the bot just listed.
- that exact pattern also works with every ai api down: a deterministic planner matches role names from the bot's previous reply and posts one line per role (e.g. "@Sinaloa Sinners - Record: 0-0").
- entity context now includes "conversation role/channel/user" entries so the ai maps names from earlier replies to exact pingable ids.
- the offline matcher no longer misfires commands off long conversational sentences (a 16-word sentence containing the word "ping" won't run the ping command).
- when every ai provider fails, the bot now says so clearly instead of a bare "no response from ai".
