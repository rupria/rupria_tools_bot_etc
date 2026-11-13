from __future__ import annotations

import unittest
from unittest.mock import patch

import aiohttp

from git_t_bot.github_client import GitHubClient


class FakeResponse:
    def __init__(
        self,
        headers: dict[str, str],
        status: int = 403,
        data: object | None = None,
        body: str = "",
    ) -> None:
        self.headers = headers
        self.status = status
        self.data = data
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def json(self):
        return self.data

    async def text(self) -> str:
        return self.body


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = responses
        self.headers: list[dict[str, str]] = []

    def get(self, _, *, headers: dict[str, str], timeout: int):
        self.headers.append(headers)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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

    def test_transient_backoff_grows_and_caps_at_five_minutes(self) -> None:
        client = GitHubClient("test-token")
        self.assertEqual([client._next_transient_backoff() for _ in range(6)], [15, 30, 60, 120, 240, 300])


class GitHubClientAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_etag_reuses_cached_response_on_not_modified(self) -> None:
        data = {"sha": "abc"}
        session = FakeSession(
            [
                FakeResponse({"ETag": '"etag-1"'}, status=200, data=data),
                FakeResponse({}, status=304),
            ]
        )
        client = GitHubClient("test-token")

        first = await client._request(session, "/repos/owner/repo/commits/main")  # type: ignore[arg-type]
        second = await client._request(session, "/repos/owner/repo/commits/main")  # type: ignore[arg-type]

        self.assertEqual(first, data)
        self.assertEqual(second, data)
        self.assertNotIn("If-None-Match", session.headers[0])
        self.assertEqual(session.headers[1]["If-None-Match"], '"etag-1"')
        self.assertEqual(client.last_status, 304)

    async def test_network_failure_opens_transient_circuit_breaker(self) -> None:
        session = FakeSession([aiohttp.ClientConnectionError("offline")])
        client = GitHubClient("test-token")

        with self.assertRaisesRegex(RuntimeError, "연결 실패"):
            await client._request(session, "/rate_limit")  # type: ignore[arg-type]

        snapshot = client.health_snapshot()
        self.assertGreater(snapshot["retry_after"], 0)
        self.assertIn("offline", snapshot["last_error"])


if __name__ == "__main__":
    unittest.main()
