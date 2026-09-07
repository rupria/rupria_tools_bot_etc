from __future__ import annotations

import unittest
from unittest.mock import patch

from git_t_bot.github_client import GitHubClient


class FakeResponse:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


class GitHubClientTests(unittest.TestCase):
    def test_retry_after_header_is_used_for_403_backoff(self) -> None:
        response = FakeResponse({"Retry-After": "120"})
        self.assertEqual(GitHubClient._retry_after_seconds(response), 120)  # type: ignore[arg-type]

    @patch("git_t_bot.github_client.time.time", return_value=1000)
    def test_rate_limit_reset_header_is_converted_to_seconds(self, _) -> None:
        response = FakeResponse(
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1060",
            }
        )
        self.assertEqual(GitHubClient._retry_after_seconds(response), 61)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
