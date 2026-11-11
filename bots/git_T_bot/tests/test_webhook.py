from __future__ import annotations

import hashlib
import hmac
import unittest

from git_t_bot.webhook import parse_push_payload, verify_github_signature


class WebhookTests(unittest.TestCase):
    def test_signature_validation(self) -> None:
        payload = b'{"zen":"Keep it logically awesome."}'
        secret = "test-secret"
        signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        self.assertTrue(verify_github_signature(payload, secret, signature))
        self.assertFalse(verify_github_signature(payload, secret, "sha256=invalid"))

    def test_parse_branch_push(self) -> None:
        push = parse_push_payload(
            {
                "ref": "refs/heads/main",
                "before": "a" * 40,
                "after": "b" * 40,
                "deleted": False,
                "repository": {"full_name": "owner/repo"},
                "pusher": {"name": "octocat"},
                "head_commit": {
                    "id": "b" * 40,
                    "url": "https://github.com/owner/repo/commit/" + "b" * 40,
                    "message": "Webhook support",
                    "timestamp": "2026-09-07T10:00:00+09:00",
                    "author": {"name": "Octocat", "username": "octocat"},
                },
            }
        )

        self.assertIsNotNone(push)
        assert push is not None
        self.assertEqual(push.repository, "owner/repo")
        self.assertEqual(push.branch, "main")
        self.assertEqual(push.latest_commit.author_name, "octocat")

    def test_ignore_tag_push(self) -> None:
        self.assertIsNone(parse_push_payload({"ref": "refs/tags/v1.0", "deleted": False}))


if __name__ == "__main__":
    unittest.main()
