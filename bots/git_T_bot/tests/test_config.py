from __future__ import annotations

import unittest

from git_t_bot.config import (
    WatchTarget,
    create_watch_key,
    dedupe_watches,
    normalize_branch_targets,
    normalize_repository,
    normalize_repository_targets,
    normalize_user_targets,
    parse_watch_targets,
)


class ConfigTests(unittest.TestCase):
    def test_normalize_repository_from_url(self) -> None:
        self.assertEqual(
            normalize_repository("https://github.com/rupria/rupria_tools_bot_etc.git"),
            "rupria/rupria_tools_bot_etc",
        )

    def test_parse_watch_targets(self) -> None:
        watches = parse_watch_targets(
            "rupria/rupria_tools_bot_etc|main|12345678901234567|rupria,rupria/rupria_tools_bot_etc|dev|12345678901234568"
        )
        self.assertEqual(len(watches), 2)
        self.assertEqual(watches[0].branch, "main")
        self.assertEqual(watches[0].user, "rupria")
        self.assertEqual(watches[1].branch, "dev")
        self.assertEqual(watches[1].user, "*")

    def test_dedupe_watches(self) -> None:
        watches = dedupe_watches(
            [
                WatchTarget("rupria/rupria_tools_bot_etc", "main", "12345678901234567", user="rupria"),
                WatchTarget("https://github.com/rupria/rupria_tools_bot_etc", "main", "12345678901234567", user="@rupria"),
            ]
        )
        self.assertEqual(len(watches), 1)
        self.assertEqual(
            create_watch_key(watches[0]),
            "rupria/rupria_tools_bot_etc::main::rupria::12345678901234567",
        )

    def test_normalize_repository_targets_supports_multiple_values(self) -> None:
        self.assertEqual(
            normalize_repository_targets("rupria/rupria_tools_bot_etc, https://github.com/rupria/gitproject"),
            ("rupria/rupria_tools_bot_etc", "rupria/gitproject"),
        )

    def test_normalize_branch_targets_dedupes_values(self) -> None:
        self.assertEqual(
            normalize_branch_targets("main, test, main"),
            ("main", "test"),
        )

    def test_normalize_user_targets_collapse_wildcard(self) -> None:
        self.assertEqual(normalize_user_targets("rupria, *"), ("*",))


if __name__ == "__main__":
    unittest.main()
