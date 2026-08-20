# Real commands only

The old Cartesian expansion system created 4,200 names such as `module_feature_action` by combining every module, feature, and action. Many combinations returned generic summaries, synthetic history, or placeholder output instead of performing the requested operation.

That system has been removed completely:

- Removed `expansion.py`.
- Removed `expanded_runtime.py`.
- Removed expansion imports and registration calls from every cog.
- Removed the obsolete `expanded_command_events` table from the bundled database.
- Kept the bot's native commands.
- Kept the new administration suite, whose generated commands call concrete Discord API, database, audit-log, permission, reporting, invite, moderation, role, channel, thread, voice, and webhook logic.

No `module_feature_action` commands are registered anymore.
