from __future__ import annotations

import importlib
import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
bot_main = importlib.import_module("main")


class DummyPermissions:
    def __init__(self, *, administrator: bool = False) -> None:
        self.administrator = administrator


class DummyRole:
    def __init__(self, role_id: int) -> None:
        self.id = role_id


class DummyMember:
    def __init__(self, *, administrator: bool = False, role_ids: tuple[int, ...] = ()) -> None:
        self.guild_permissions = DummyPermissions(administrator=administrator)
        self.roles = [DummyRole(role_id) for role_id in role_ids]


class DummyGuild:
    def __init__(self, guild_id: int) -> None:
        self.id = guild_id


class DummyChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id


class DummyContext:
    def __init__(self, *, guild_id: int, channel_id: int, member: DummyMember) -> None:
        self.guild = DummyGuild(guild_id)
        self.channel = DummyChannel(channel_id)
        self.author = member


class DummyInteraction:
    def __init__(self, *, guild_id: int, channel_id: int, member: DummyMember) -> None:
        self.guild = DummyGuild(guild_id)
        self.channel = DummyChannel(channel_id)
        self.user = member


class AuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_settings = bot_main.settings
        bot_main.settings = replace(
            bot_main.settings,
            guild_id="1",
            admin_channel_id="2",
            allowed_role_ids=("9",),
        )

    def tearDown(self) -> None:
        bot_main.settings = self.original_settings

    def test_admin_bypasses_guild_channel_and_role_restrictions_for_prefix_commands(self) -> None:
        ctx = DummyContext(guild_id=999, channel_id=999, member=DummyMember(administrator=True))
        self.assertTrue(bot_main.is_authorized(ctx))

    def test_admin_bypasses_guild_channel_and_role_restrictions_for_slash_commands(self) -> None:
        interaction = DummyInteraction(guild_id=999, channel_id=999, member=DummyMember(administrator=True))
        self.assertTrue(bot_main.is_interaction_authorized(interaction))

    def test_non_admin_still_needs_allowed_channel(self) -> None:
        ctx = DummyContext(guild_id=1, channel_id=999, member=DummyMember(role_ids=(9,)))
        self.assertFalse(bot_main.is_authorized(ctx))

    def test_non_admin_still_needs_allowed_guild(self) -> None:
        interaction = DummyInteraction(guild_id=999, channel_id=2, member=DummyMember(role_ids=(9,)))
        self.assertFalse(bot_main.is_interaction_authorized(interaction))

    def test_non_admin_can_use_allowed_channel_with_allowed_role(self) -> None:
        interaction = DummyInteraction(guild_id=1, channel_id=2, member=DummyMember(role_ids=(9,)))
        self.assertTrue(bot_main.is_interaction_authorized(interaction))


if __name__ == "__main__":
    unittest.main()
