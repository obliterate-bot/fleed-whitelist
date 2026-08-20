# Administration command suite

This file documents the practical administration commands added to the bot.

## Real-command-only build

- Removed **4,200** generated `module_feature_action` commands that used generic or placeholder behavior.
- Retained **1,091** statically defined native and administration command objects.
- The administration cog can register up to **294** additional concrete report, audit, permission, moderation, and invite commands.
- The resulting build contains up to **1,385** real command objects instead of inflating the count with generic combinations.

## Administration suite

- New administration command objects: up to **381** including its root groups.
- Audit and permission checks are version-gated and only register when supported by the installed Discord.py version.
- All commands are prefix commands, use the existing lowercase Fleed embed helpers, and enforce Discord permission checks on mutations.

### `membertools` — 51 subcommands

`addrole`, `admins`, `all`, `animatedavatars`, `ban`, `boosters`, `bots`, `camera`, `clearnickname`, `colorless`, `dangerous`, `deafened`, `desktop`, `disconnect`, `dm`, `dnd`, `find`, `humans`, `idle`, `info`, `joinedmonth`, `joinedtoday`, `joinedweek`, `kick`, `mobile`, `moderators`, `move`, `muted`, `newaccounts`, `newestaccounts`, `newestjoins`, `nickname`, `nicknamed`, `noavatar`, `noroles`, `offline`, `oldestaccounts`, `oldestjoins`, `online`, `pending`, `permissions`, `removerole`, `roleheavy`, `roles`, `streaming`, `timedout`, `timeout`, `unnicknamed`, `untimeout`, `voice`, `web`

### `channeltools` — 46 subcommands

`activevoice`, `all`, `bitrate`, `categories`, `clone`, `createcategory`, `createtext`, `createvoice`, `delete`, `emptyvoice`, `forums`, `fullvoice`, `hidden`, `hide`, `info`, `lock`, `locked`, `newest`, `news`, `nooverwrites`, `noslowmode`, `notopic`, `nsfw`, `oldest`, `orphaned`, `rename`, `sfw`, `show`, `slowmode`, `slowmodechannels`, `stages`, `sync`, `synced`, `system`, `text`, `threads`, `topic`, `unlimitedvoice`, `unlock`, `unlocked`, `unsynced`, `userlimit`, `visible`, `voice`, `withoverwrites`, `withtopic`

### `roletools` — 42 subcommands

`addall`, `admins`, `all`, `assignable`, `booster`, `bots`, `clone`, `color`, `colored`, `create`, `dangerous`, `default`, `delete`, `empty`, `highest`, `hoist`, `hoisted`, `info`, `integrations`, `large`, `lowest`, `managed`, `managers`, `members`, `mentionable`, `mentionableroles`, `moderators`, `newest`, `noicons`, `oldest`, `permissionheavy`, `permissionless`, `permissions`, `populated`, `removeall`, `rename`, `small`, `uncolored`, `unhoisted`, `unmanaged`, `unmentionable`, `withicons`

### `servertools` — 52 subcommands

`afk`, `animatedemojis`, `bans`, `bitrate`, `boosters`, `boostlevel`, `botcheck`, `botpermissions`, `bots`, `categories`, `channels`, `contentfilter`, `created`, `dangerousroles`, `dnd`, `emojis`, `emptyroles`, `features`, `filesize`, `forums`, `health`, `hiddenchannels`, `humans`, `idle`, `invites`, `locale`, `lockedchannels`, `members`, `mfa`, `newaccounts`, `notifications`, `offline`, `online`, `overview`, `owner`, `prune`, `pruneestimate`, `recentjoins`, `roles`, `ruleschannel`, `scheduled`, `stages`, `staticemojis`, `stickers`, `systemchannel`, `textchannels`, `threads`, `updateschannel`, `vanity`, `verification`, `voicechannels`, `webhooks`

### `modtools` — 39 subcommands

`cleanattachments`, `cleanbots`, `cleanlinks`, `lock`, `purge10`, `purge100`, `purge150`, `purge20`, `purge200`, `purge25`, `purge5`, `purge50`, `purge500`, `purge75`, `slow10m`, `slow10s`, `slow1h`, `slow1m`, `slow2m`, `slow30m`, `slow30s`, `slow5m`, `slow5s`, `slow6h`, `slowoff`, `timeout10m`, `timeout12h`, `timeout14d`, `timeout1d`, `timeout1h`, `timeout1m`, `timeout28d`, `timeout30m`, `timeout3d`, `timeout5m`, `timeout6h`, `timeout7d`, `unlock`, `untimeout`

### `audittools` — 53 subcommands

`automodblocked`, `automodcreated`, `automoddeleted`, `automodflagged`, `automodtimeouts`, `automodupdated`, `bans`, `botsadded`, `channelscreated`, `channelsdeleted`, `channelsupdated`, `emojiscreated`, `emojisdeleted`, `emojisupdated`, `eventscreated`, `eventsdeleted`, `eventsupdated`, `integrationscreated`, `integrationsdeleted`, `integrationsupdated`, `invitescreated`, `invitesdeleted`, `invitesupdated`, `kicks`, `memberdisconnects`, `membermoves`, `memberroles`, `memberupdates`, `messagesbulkdeleted`, `messagesdeleted`, `messagespinned`, `messagesunpinned`, `overwritescreated`, `overwritesdeleted`, `overwritesupdated`, `prunes`, `rolescreated`, `rolesdeleted`, `rolesupdated`, `serverupdates`, `stagescreated`, `stagesdeleted`, `stagesupdated`, `stickerscreated`, `stickersdeleted`, `stickersupdated`, `threadscreated`, `threadsdeleted`, `threadsupdated`, `unbans`, `webhookscreated`, `webhooksdeleted`, `webhooksupdated`

### `permissiontools` — 48 subcommands

`activities`, `administrator`, `applicationcommands`, `attachfiles`, `auditlog`, `ban`, `changenickname`, `connect`, `createevents`, `createexpressions`, `deafenmembers`, `embedlinks`, `externalapps`, `externalemojis`, `externalsounds`, `externalstickers`, `history`, `insights`, `invite`, `kick`, `managechannels`, `manageevents`, `manageexpressions`, `managemessages`, `managenicknames`, `manageroles`, `manageserver`, `managethreads`, `managewebhooks`, `mentioneveryone`, `moderatemembers`, `movemembers`, `mutemembers`, `polls`, `priorityspeaker`, `privatethreads`, `publicthreads`, `reactions`, `requesttospeak`, `sendmessages`, `sendtts`, `soundboard`, `speak`, `stream`, `threadmessages`, `viewchannel`, `voiceactivity`, `voicemessages`

### `invitetools` — 21 subcommands

`clear`, `create12h`, `create1d`, `create1h`, `create30m`, `create6h`, `create7d`, `createpermanent`, `delete`, `fiftyuses`, `fiveuses`, `hundreduses`, `info`, `list`, `singleuse`, `temporary1d`, `temporary1h`, `temporary7d`, `tenuses`, `twentyfiveuses`, `vanity`

### `voicetools` — 5 subcommands

`disconnectall`, `list`, `moveall`, `muteall`, `unmuteall`

### `threadtools` — 9 subcommands

`archive`, `create`, `delete`, `info`, `list`, `lock`, `rename`, `unarchive`, `unlock`

### `webhooktools` — 4 subcommands

`create`, `delete`, `list`, `send`
