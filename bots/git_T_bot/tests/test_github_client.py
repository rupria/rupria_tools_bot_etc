from __future__ import annotations

import unittest
from unittest.mock import patch

from git_t_bot.github_client import GitHubClient


class FakeResponse:
    def __init__(self, headers: dict[str, str], status: int = 403) -> None:
        self.headers = headers
        self.status = status


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

    def test_invalid_token_uses_five_minute_backoff(self) -> None:
        response = FakeResponse({}, status=401)
        self.assertEqual(GitHubClient._backoff_seconds_for_status(response), 300)  # type: ignore[arg-type]

    @patch("git_t_bot.github_client.time.monotonic", return_value=100)
    def test_health_snapshot_reports_remaining_backoff(self, _) -> None:
        client = GitHubClient("test-token")
        client.blocked_until = 125
        client.blocked_status = 401
        snapshot = client.health_snapshot()
        self.assertEqual(snapshot["retry_after"], 25)
        self.assertEqual(snapshot["blocked_status"], 401)


if __name__ == "__main__":
    unittest.main()
