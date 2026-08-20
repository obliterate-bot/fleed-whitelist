# pyright: reportPrivateUsage=false, reportUninitializedInstanceVariable=false

import unittest
from types import SimpleNamespace

from discord.ext import commands

from cogs.ai import (
    _looks_like_non_action_request,
    _normalize_router_plan,
    _resolve_command_line,
    _synthesize_command_args,
    build_nlp_command_catalog,
)


class FakeBot:
    def __init__(self, command_list):
        self.command_list = command_list

    def walk_commands(self):
        for command in self.command_list:
            yield command
            if isinstance(command, commands.Group):
                yield from command.walk_commands()


def make_command(name, aliases=None, callback=None):
    if callback is None:
        async def callback(ctx):
            return None
    return commands.Command(callback, name=name, aliases=aliases or [])


class NlpRouterTests(unittest.TestCase):
    def setUp(self):
        self.avatar = make_command("avatar", aliases=["pfp", "av"])
        self.banner = make_command("banner")

        async def role_group_callback(ctx):
            return None

        async def role_rename_callback(ctx, role: str, *, name: str):
            return None

        self.role_group = commands.Group(role_group_callback, name="role", aliases=["roles", "r"])
        self.role_group.add_command(
            commands.Command(role_rename_callback, name="rename", aliases=["name"])
        )
        self.bot = FakeBot([self.avatar, self.banner, self.role_group])

    def test_compact_catalog_contains_every_command(self):
        command_list = [make_command(f"command{i}") for i in range(30)]
        bot = FakeBot(command_list)

        compact, detailed = build_nlp_command_catalog(bot, "run command1", max_candidates=3)

        self.assertEqual(30, len(compact.splitlines()))
        self.assertIn("command29", compact)
        self.assertEqual(3, detailed.count("- command:"))

    def test_resolver_handles_aliases_nested_aliases_and_typos(self):
        self.assertEqual("avatar Fleed", _resolve_command_line(self.bot, "pfp Fleed"))
        self.assertEqual(
            "role rename @Mods Senior Mods",
            _resolve_command_line(self.bot, "role name @Mods Senior Mods"),
        )
        self.assertEqual(
            "role rename @Mods Senior Mods",
            _resolve_command_line(self.bot, "roles name @Mods Senior Mods"),
        )
        self.assertEqual(
            "avatar Fleed",
            _resolve_command_line(self.bot, "please run avatr Fleed"),
        )

    def test_normalizer_rejects_invented_commands(self):
        self.assertIsNone(
            _normalize_router_plan(
                self.bot,
                {"action": "command", "command": "invented Fleed", "channel_id": None},
            )
        )

    def test_normalizer_rejects_malformed_target_channel(self):
        self.assertIsNone(
            _normalize_router_plan(
                self.bot,
                {"action": "command", "command": "avatar Fleed", "channel_id": "general"},
            )
        )

    def test_non_action_guard_blocks_help_negation_and_hypotheticals(self):
        self.assertTrue(_looks_like_non_action_request("how does purge work?"))
        self.assertTrue(_looks_like_non_action_request("don't ban Daniel"))
        self.assertTrue(_looks_like_non_action_request("hypothetically, ban Daniel"))
        self.assertFalse(_looks_like_non_action_request("can you ban Daniel for spam"))
        self.assertFalse(_looks_like_non_action_request("what is my balance"))

    def test_normalizer_canonicalizes_model_command(self):
        plan = _normalize_router_plan(
            self.bot,
            {"action": "command", "command": "AVATR Fleed", "channel_id": None},
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual("avatar Fleed", plan["command"])

    def test_required_argument_is_not_silently_omitted(self):
        async def required_callback(ctx, target: str):
            return None

        command = commands.Command(required_callback, name="required")
        message = SimpleNamespace(mentions=[], role_mentions=[], channel_mentions=[])

        self.assertIsNone(_synthesize_command_args(command, None, message, "run required"))

    def test_final_free_text_argument_is_extracted(self):
        async def play_callback(ctx, *, query: str):
            return None

        command = commands.Command(play_callback, name="play")
        message = SimpleNamespace(mentions=[], role_mentions=[], channel_mentions=[])

        line = _synthesize_command_args(command, None, message, "could you play never gonna give you up")

        self.assertEqual("play never gonna give you up", line)


if __name__ == "__main__":
    unittest.main()
