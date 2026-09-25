from __future__ import annotations

import hashlib
import hmac
import unittest

from git_t_bot.webhook import (
    derive_repository_secret,
    parse_push_event,
    repository_from_payload,
    verify_webhook_signature,
)


def make_push_payload() -> dict:
    return {
        "ref": "refs/heads/dev",
        "before": "1" * 40,
        "after": "2" * 40,
        "compare": "https://github.com/rupria/gitproject/compare/old...new",
        "created": False,
        "deleted": False,
        "forced": False,
        "size": 2,
        "repository": {
            "full_name": "rupria/gitproject",
            "html_url": "https://github.com/rupria/gitproject",
            "default_branch": "main",
        },
        "sender": {"login": "rupria"},
        "pusher": {"name": "rupria"},
        "commits": [
            {
                "id": "a" * 40,
                "message": "첫 번째 변경",
                "timestamp": "2026-09-25T01:00:00Z",
                "url": "https://github.com/rupria/gitproject/commit/" + "a" * 40,
                "author": {"name": "RUPRIA", "username": "rupria"},
                "added": ["new.txt"],
                "removed": [],
                "modified": ["README.md"],
            },
            {
                "id": "2" * 40,
                "message": "웹훅 전환",
                "timestamp": "2026-09-25T01:01:00Z",
                "url": "https://github.com/rupria/gitproject/commit/" + "2" * 40,
                "author": {"name": "RUPRIA", "username": "rupria"},
                "added": [],
                "removed": ["old.txt"],
                "modified": ["README.md"],
            },
        ],
        "head_commit": {
            "id": "2" * 40,
            "message": "웹훅 전환",
            "timestamp": "2026-09-25T01:01:00Z",
            "url": "https://github.com/rupria/gitproject/commit/" + "2" * 40,
            "author": {"name": "RUPRIA", "username": "rupria"},
        },
    }


class WebhookTests(unittest.TestCase):
    def test_repository_secret_is_stable_and_repository_specific(self) -> None:
        first = derive_repository_secret("master-secret", "rupria/gitproject")
        second = derive_repository_secret("master-secret", "https://github.com/rupria/gitproject")
        other = derive_repository_secret("master-secret", "rupria/other")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertNotEqual(
            derive_repository_secret("master-secret", "rupria/gitproject", "11111111111111111"),
            derive_repository_secret("master-secret", "rupria/gitproject", "22222222222222222"),
        )

    def test_verify_webhook_signature(self) -> None:
        payload = b'{"zen":"Keep it logically awesome."}'
        signature = "sha256=" + hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(payload, signature, "secret"))
        self.assertFalse(verify_webhook_signature(payload, signature, "wrong"))
        self.assertFalse(verify_webhook_signature(payload, "", "secret"))

    def test_parse_push_event_uses_payload_without_api_lookup(self) -> None:
        event = parse_push_event(make_push_payload())
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.repository, "rupria/gitproject")
        self.assertEqual(event.branch, "dev")
        self.assertEqual(event.default_branch, "main")
        self.assertEqual(event.latest_commit.author_name, "rupria")
        self.assertEqual(event.compare_info.total_commits, 2)
        self.assertEqual(len(event.compare_info.commits), 2)
        self.assertEqual(
            [(item.filename, item.status) for item in event.compare_info.files],
            [("new.txt", "added"), ("README.md", "modified"), ("old.txt", "removed")],
        )
        self.assertTrue(all(item.additions is None for item in event.compare_info.files))

    def test_parse_push_event_ignores_tag_and_deleted_branch(self) -> None:
        tag_payload = make_push_payload()
        tag_payload["ref"] = "refs/tags/v1.0.0"
        self.assertIsNone(parse_push_event(tag_payload))

        deleted_payload = make_push_payload()
        deleted_payload["deleted"] = True
        self.assertIsNone(parse_push_event(deleted_payload))

    def test_repository_from_payload_requires_full_name(self) -> None:
        self.assertEqual(repository_from_payload(make_push_payload()), "rupria/gitproject")
        with self.assertRaises(ValueError):
            repository_from_payload({"repository": {}})


if __name__ == "__main__":
    unittest.main()
