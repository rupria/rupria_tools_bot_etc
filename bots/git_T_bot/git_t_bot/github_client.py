from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import aiohttp


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    html_url: str
    message: str
    author_name: str
    committed_at: str


@dataclass(frozen=True)
class CompareInfo:
    html_url: str
    total_commits: int


class GitHubApiError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token

    async def _request(self, session: aiohttp.ClientSession, endpoint: str) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "git_T_bot/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        async with session.get(f"https://api.github.com{endpoint}", headers=headers, timeout=20) as response:
            if response.status >= 400:
                detail = await response.text()
                raise GitHubApiError(f"GitHub API 요청 실패 ({response.status}): {detail[:300]}")
            return await response.json()

    async def get_latest_commit(
        self,
        session: aiohttp.ClientSession,
        repository: str,
        branch: str,
    ) -> CommitInfo:
        owner, repo = repository.split("/", 1)
        data = await self._request(
            session,
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/commits/{quote(branch, safe='')}",
        )
        return CommitInfo(
            sha=str(data["sha"]),
            html_url=str(data["html_url"]),
            message=str(data.get("commit", {}).get("message", "")),
            author_name=str(
                data.get("author", {}).get("login")
                or data.get("commit", {}).get("author", {}).get("name")
                or "unknown"
            ),
            committed_at=str(data.get("commit", {}).get("author", {}).get("date") or ""),
        )

    async def compare_commits(
        self,
        session: aiohttp.ClientSession,
        repository: str,
        previous_sha: str,
        latest_sha: str,
    ) -> CompareInfo:
        owner, repo = repository.split("/", 1)
        data = await self._request(
            session,
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/compare/{quote(previous_sha, safe='')}...{quote(latest_sha, safe='')}",
        )
        return CompareInfo(
            html_url=str(data.get("html_url", "")),
            total_commits=int(data.get("total_commits", 0)),
        )

    def make_demo_commit(self) -> CommitInfo:
        return CommitInfo(
            sha="abcdef1234567890abcdef1234567890abcdef12",
            html_url="https://github.com/rupria/rupria_tools_bot_etc/commit/abcdef1234567890abcdef1234567890abcdef12",
            message="테스트 알림 커밋 메시지",
            author_name="git_T_bot",
            committed_at="2026-08-27T00:00:00Z",
        )

    def make_demo_compare(self) -> CompareInfo:
        return CompareInfo(
            html_url="https://github.com/rupria/rupria_tools_bot_etc/compare/old...new",
            total_commits=3,
        )
