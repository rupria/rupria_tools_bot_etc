from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .github_client import CommitInfo


ZERO_SHA = "0" * 40


@dataclass(frozen=True)
class PushInfo:
    repository: str
    branch: str
    before_sha: str
    after_sha: str
    latest_commit: CommitInfo


def verify_github_signature(payload: bytes, secret: str, signature: str) -> bool:
    if not secret or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_push_payload(payload: object) -> PushInfo | None:
    if not isinstance(payload, dict):
        return None

    ref = str(payload.get("ref", ""))
    if not ref.startswith("refs/heads/") or bool(payload.get("deleted")):
        return None

    repository_data = payload.get("repository")
    if not isinstance(repository_data, dict):
        return None
    repository = str(repository_data.get("full_name", "")).strip()
    if not repository:
        return None

    before_sha = str(payload.get("before", ""))
    after_sha = str(payload.get("after", ""))
    if not after_sha or after_sha == ZERO_SHA:
        return None

    head_commit = payload.get("head_commit")
    if not isinstance(head_commit, dict):
        return None
    author_data = head_commit.get("author")
    if not isinstance(author_data, dict):
        author_data = {}
    pusher_data = payload.get("pusher")
    if not isinstance(pusher_data, dict):
        pusher_data = {}

    return PushInfo(
        repository=repository,
        branch=ref.removeprefix("refs/heads/"),
        before_sha=before_sha,
        after_sha=after_sha,
        latest_commit=CommitInfo(
            sha=after_sha,
            html_url=str(head_commit.get("url", "")),
            message=str(head_commit.get("message", "")),
            author_name=str(
                author_data.get("username")
                or pusher_data.get("name")
                or author_data.get("name")
                or "unknown"
            ),
            committed_at=str(head_commit.get("timestamp", "")),
        ),
    )
