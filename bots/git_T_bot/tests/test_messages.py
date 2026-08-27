from __future__ import annotations

import unittest

from git_t_bot.config import WatchTarget
from git_t_bot.messages import build_list_text, build_poll_summary_text, build_watch_added_text, short_sha


class MessageTests(unittest.TestCase):
    def test_short_sha(self) -> None:
        self.assertEqual(short_sha("abcdef1234567890"), "abcdef1")

    def test_build_list_text(self) -> None:
        text = build_list_text([WatchTarget("rupria/rupria_tools_bot_etc", "main", "12345678901234567", "saved")])
        self.assertIn("main", text)
        self.assertIn("[saved]", text)

    def test_build_watch_added_text(self) -> None:
        text = build_watch_added_text(
            WatchTarget("rupria/rupria_tools_bot_etc", "main", "12345678901234567"),
            "abcdef1234567890",
        )
        self.assertIn("abcdef1", text)

    def test_build_poll_summary_text(self) -> None:
        text = build_poll_summary_text(
            {
                "skipped": False,
                "watch_count": 3,
                "initialized_count": 1,
                "changed_count": 2,
                "error_count": 0,
            }
        )
        self.assertIn("감시 대상: 3개", text)
        self.assertIn("새 알림: 2개", text)


if __name__ == "__main__":
    unittest.main()
