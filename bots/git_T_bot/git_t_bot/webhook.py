from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac

from .config import normalize_repository
from .github_client import ChangedFileInfo, CommitInfo, CompareCommitInfo, CompareInfo


BRANCH_REF_PREFIX = "refs/heads/"
ZERO_SHA = "0" * 40


@dataclass(frozen=True)
class PushEvent:
    repository: str
    branch: str
    default_branch: str
    before_sha: str
    after_sha: str
    latest_commit: CommitInfo
    compare_info: CompareInfo


def derive_repository_secret(master_secret: str, repository: str, scope: str = "") -> str:
    normalized_repository = normalize_repository(repository).lower()
    secret_scope = f"{scope.strip()}:{normalized_repository}" if scope.strip() else normalized_repository
    return hmac.new(
        master_secret.encode("utf-8"),
        secret_scope.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def repository_from_payload(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("GitHub 웹훅 본문이 객체 형식이 아닙니다.")
    repository = payload.get("repository")
    if not isinstance(repository, dict):
        raise ValueError("GitHub 웹훅에 repository 정보가 없습니다.")
    full_name = str(repository.get("full_name", "")).strip()
    if not full_name:
        raise ValueError("GitHub 웹훅에 repository.full_name이 없습니다.")
    return normalize_repository(full_name)


def _commit_author(commit: dict, payload: dict) -> str:
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    committer = commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    pusher = payload.get("pusher") if isinstance(payload.get("pusher"), dict) else {}
    return str(
        author.get("username")
        or author.get("name")
        or committer.get("username")
        or committer.get("name")
        or sender.get("login")
        or pusher.get("name")
        or "unknown"
    )


def _changed_files(commits: list[dict]) -> tuple[ChangedFileInfo, ...]:
    files: dict[str, str] = {}
    for commit in commits:
        for status, field_name in (
            ("added", "added"),
            ("removed", "removed"),
            ("modified", "modified"),
        ):
            values = commit.get(field_name, [])
            if not isinstance(values, list):
                continue
            for value in values:
                filename = str(value).strip()
                if filename:
                    files[filename] = status
    return tuple(
        ChangedFileInfo(filename=filename, additions=None, deletions=None, status=status)
        for filename, status in files.items()
    )


def parse_push_event(payload: object) -> PushEvent | None:
    if not isinstance(payload, dict):
        raise ValueError("GitHub push 본문이 객체 형식이 아닙니다.")

    ref = str(payload.get("ref", ""))
    if not ref.startswith(BRANCH_REF_PREFIX):
        return None
    if bool(payload.get("deleted")):
        return None

    repository = repository_from_payload(payload)
    repository_data = payload.get("repository")
    assert isinstance(repository_data, dict)
    branch = ref.removeprefix(BRANCH_REF_PREFIX)
    default_branch = str(repository_data.get("default_branch", "")).strip()
    before_sha = str(payload.get("before", "")).strip()
    after_sha = str(payload.get("after", "")).strip()
    if not after_sha or after_sha == ZERO_SHA:
        return None

    raw_commits = payload.get("commits", [])
    commits = [item for item in raw_commits if isinstance(item, dict)] if isinstance(raw_commits, list) else []
    head_commit = payload.get("head_commit")
    if not isinstance(head_commit, dict):
        head_commit = commits[-1] if commits else {}

    repository_url = str(repository_data.get("html_url", "")).rstrip("/")
    latest_url = str(head_commit.get("url", "")).strip() or f"{repository_url}/commit/{after_sha}"
    latest_commit = CommitInfo(
        sha=str(head_commit.get("id") or after_sha),
        html_url=latest_url,
        message=str(head_commit.get("message", "")),
        author_name=_commit_author(head_commit, payload),
        committed_at=str(head_commit.get("timestamp", "")),
    )

    compare_commits = tuple(
        CompareCommitInfo(
            sha=str(commit.get("id", "")),
            html_url=str(commit.get("url", "")),
            message=str(commit.get("message", "")),
            author_name=_commit_author(commit, payload),
        )
        for commit in commits
    )
    size = payload.get("size")
    total_commits = int(size) if isinstance(size, int) and size >= 0 else len(compare_commits)
    compare_info = CompareInfo(
        html_url=str(payload.get("compare", "")),
        total_commits=total_commits,
        commits=compare_commits,
        files=_changed_files(commits),
    )
    return PushEvent(
        repository=repository,
        branch=branch,
        default_branch=default_branch,
        before_sha=before_sha,
        after_sha=after_sha,
        latest_commit=latest_commit,
        compare_info=compare_info,
    )
