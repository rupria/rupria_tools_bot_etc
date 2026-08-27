from __future__ import annotations

import unittest

from git_t_bot.config import WatchTarget
from git_t_bot.github_client import BranchInfo, GitHubClient
from git_t_bot.messages import (
    build_branch_list_text,
    build_commit_embed,
    build_help_text,
    build_list_text,
    build_poll_summary_text,
    build_repository_branch_catalog_text,
    build_watch_added_text,
    short_sha,
)


class MessageTests(unittest.TestCase):
    def test_short_sha(self) -> None:
        self.assertEqual(short_sha("abcdef1234567890"), "abcdef1")

    def test_build_list_text(self) -> None:
        text = build_list_text(
            [WatchTarget("rupria/rupria_tools_bot_etc", "main", "12345678901234567", "saved", "rupria")],
            "rupria/rupria_tools_bot_etc",
            "main",
            "rupria",
        )
        self.assertIn("레포지토리 : rupria/rupria_tools_bot_etc", text)
        self.assertIn("브랜치 : main", text)
        self.assertIn("감지 사용자 : @rupria", text)
        self.assertIn("[saved]", text)

    def test_build_branch_list_text(self) -> None:
        text = build_branch_list_text(
            [
                WatchTarget("rupria/rupria_tools_bot_etc", "dev", "12345678901234568", "env", "*"),
                WatchTarget("rupria/rupria_tools_bot_etc", "main", "12345678901234567", "saved", "rupria"),
                WatchTarget("rupria/rupria_tools_bot_etc", "main", "12345678901234569", "saved", "*"),
            ],
            None,
            "*",
            "*",
        )
        self.assertIn("브랜치 기준 감시 현황 3개", text)
        self.assertIn("브랜치 : *", text)
        self.assertIn("- dev", text)
        self.assertIn("감지 사용자 : * -> <#12345678901234568> [env]", text)
        self.assertIn("감지 사용자 : @rupria -> <#12345678901234567> [saved]", text)

    def test_build_watch_added_text(self) -> None:
        text = build_watch_added_text(
            WatchTarget("rupria/rupria_tools_bot_etc", "main", "12345678901234567", user="rupria"),
            "abcdef1234567890",
        )
        self.assertIn("abcdef1", text)
        self.assertIn("감지 사용자 : @rupria", text)

    def test_build_commit_embed(self) -> None:
        client = GitHubClient("")
        watch = WatchTarget("rupria/data-collection-workspace", "main", "12345678901234567", user="rupria")
        embed = build_commit_embed(
            watch,
            "1234567890abcdef1234567890abcdef12345678",
            client.make_demo_commit(),
            client.make_demo_compare(),
        )
        self.assertEqual(embed.title, "rupria/data-collection-workspace")
        self.assertIn("브랜치 : main", embed.description)
        self.assertIn("감지 사용자 : @rupria", embed.description)
        self.assertIn("변경 규모: 4개 파일 · 3개 커밋", embed.description)
        self.assertEqual(embed.fields[0].name, "커밋 메시지 (3개)")
        self.assertIn("81cc880", embed.fields[0].value)
        self.assertEqual(embed.fields[2].name, "변경 파일 · 줄 수")
        self.assertIn("data23_ML_분류분석.ipynb", embed.fields[2].value)

    def test_build_repository_branch_catalog_text(self) -> None:
        text = build_repository_branch_catalog_text(
            "rupria/rupria_tools_bot_etc",
            (
                BranchInfo("dev", False),
                BranchInfo("main", True),
            ),
            [
                WatchTarget("rupria/rupria_tools_bot_etc", "main", "12345678901234567", "saved", "rupria"),
            ],
            "*",
            "*",
        )
        self.assertIn("rupria/rupria_tools_bot_etc 브랜치 목록 2개", text)
        self.assertIn("- main [보호]", text)
        self.assertIn("감지 사용자 : @rupria -> <#12345678901234567> [saved]", text)
        self.assertIn("- dev", text)
        self.assertIn("감시 없음", text)

    def test_build_help_text(self) -> None:
        text = build_help_text("!")
        self.assertIn("!watch branches owner/repo [branch] [user]", text)
        self.assertIn("/github_branches repository:owner/repo branch:* user:*", text)

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
