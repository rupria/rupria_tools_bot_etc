from __future__ import annotations

from dataclasses import dataclass
import math
import time
from urllib.parse import quote

import aiohttp


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    html_url: str
    message: str
    author_name: str
    committed_at: str
    author_email: str = ""


@dataclass(frozen=True)
class CompareInfo:
    html_url: str
    total_commits: int
    commits: tuple["CompareCommitInfo", ...] = ()
    files: tuple["ChangedFileInfo", ...] = ()


@dataclass(frozen=True)
class CompareCommitInfo:
    sha: str
    html_url: str
    message: str
    author_name: str
    author_email: str = ""


@dataclass(frozen=True)
class ChangedFileInfo:
    filename: str
    additions: int
    deletions: int
    status: str


@dataclass(frozen=True)
class BranchInfo:
    name: str
    protected: bool


class GitHubApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, retry_after: int = 0) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self.blocked_until = 0.0

    @staticmethod
    def _retry_after_seconds(response: aiohttp.ClientResponse) -> int:
        retry_after = response.headers.get("Retry-After", "").strip()
        if retry_after.isdigit():
            return max(int(retry_after), 1)
        reset_at = response.headers.get("X-RateLimit-Reset", "").strip()
        if response.headers.get("X-RateLimit-Remaining") == "0" and reset_at.isdigit():
            return max(int(reset_at) - int(time.time()) + 1, 1)
        return 60

    async def _request(self, session: aiohttp.ClientSession, endpoint: str) -> object:
        remaining_backoff = self.blocked_until - time.monotonic()
        if remaining_backoff > 0:
            retry_after = math.ceil(remaining_backoff)
            raise GitHubApiError(
                f"GitHub API 재시도 대기 중입니다. {retry_after}초 후 다시 확인합니다.",
                status=403,
                retry_after=retry_after,
            )
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
                retry_after = 0
                if response.status in {403, 429}:
                    retry_after = self._retry_after_seconds(response)
                    self.blocked_until = time.monotonic() + retry_after
                raise GitHubApiError(
                    f"GitHub API 요청 실패 ({response.status}): {detail[:300]}",
                    status=response.status,
                    retry_after=retry_after,
                )
            return await response.json()

    async def get_default_branch(self, session: aiohttp.ClientSession, repository: str) -> str:
        owner, repo = repository.split("/", 1)
        data = await self._request(
            session,
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}",
        )
        if not isinstance(data, dict):
            raise GitHubApiError("GitHub 저장소 응답 형식이 예상과 다릅니다.")
        branch = str(data.get("default_branch", "")).strip()
        if not branch:
            raise GitHubApiError("GitHub 저장소의 기본 브랜치를 찾지 못했습니다.")
        return branch

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
        if not isinstance(data, dict):
            raise GitHubApiError("GitHub 커밋 응답 형식이 예상과 다릅니다.")
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
            author_email=str(data.get("commit", {}).get("author", {}).get("email") or ""),
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
        if not isinstance(data, dict):
            raise GitHubApiError("GitHub 비교 응답 형식이 예상과 다릅니다.")
        return CompareInfo(
            html_url=str(data.get("html_url", "")),
            total_commits=int(data.get("total_commits", 0)),
            commits=tuple(
                CompareCommitInfo(
                    sha=str(commit.get("sha", "")),
                    html_url=str(commit.get("html_url", "")),
                    message=str(commit.get("commit", {}).get("message", "")),
                    author_name=str(
                        commit.get("author", {}).get("login")
                        or commit.get("commit", {}).get("author", {}).get("name")
                        or "unknown"
                    ),
                    author_email=str(commit.get("commit", {}).get("author", {}).get("email") or ""),
                )
                for commit in data.get("commits", [])
            ),
            files=tuple(
                ChangedFileInfo(
                    filename=str(changed_file.get("filename", "")),
                    additions=int(changed_file.get("additions", 0)),
                    deletions=int(changed_file.get("deletions", 0)),
                    status=str(changed_file.get("status", "")),
                )
                for changed_file in data.get("files", [])
            ),
        )

    async def list_branches(
        self,
        session: aiohttp.ClientSession,
        repository: str,
    ) -> tuple[BranchInfo, ...]:
        owner, repo = repository.split("/", 1)
        data = await self._request(
            session,
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/branches?per_page=100",
        )
        if not isinstance(data, list):
            raise GitHubApiError("GitHub 브랜치 응답 형식이 예상과 다릅니다.")
        branches: list[BranchInfo] = []
        for branch in data:
            if not isinstance(branch, dict):
                continue
            name = str(branch.get("name", "")).strip()
            if not name:
                continue
            branches.append(
                BranchInfo(
                    name=name,
                    protected=bool(branch.get("protected", False)),
                )
            )
        return tuple(branches)

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
            commits=(
                CompareCommitInfo(
                    sha="81cc8801234567890abcdef1234567890abcdef",
                    html_url="https://github.com/rupria/rupria_tools_bot_etc/commit/81cc8801234567890abcdef1234567890abcdef",
                    message="26.08.05 수업내용 업데이트",
                    author_name="rupria",
                ),
                CompareCommitInfo(
                    sha="7265aa21234567890abcdef1234567890abcdef",
                    html_url="https://github.com/rupria/rupria_tools_bot_etc/commit/7265aa21234567890abcdef1234567890abcdef",
                    message="회귀 분석 결과 정리",
                    author_name="rupria",
                ),
                CompareCommitInfo(
                    sha="44beef91234567890abcdef1234567890abcdef",
                    html_url="https://github.com/rupria/rupria_tools_bot_etc/commit/44beef91234567890abcdef1234567890abcdef",
                    message="Python 구현 노트 정리",
                    author_name="rupria",
                ),
            ),
            files=(
                ChangedFileInfo(
                    filename="data23_ML_분류분석.ipynb",
                    additions=56,
                    deletions=1,
                    status="modified",
                ),
                ChangedFileInfo(
                    filename="data23_ML_회귀분석_성능평가(metric).ipynb",
                    additions=383,
                    deletions=0,
                    status="modified",
                ),
                ChangedFileInfo(
                    filename="data24_ML_정사하강법_회귀평가자료.ipynb",
                    additions=157,
                    deletions=0,
                    status="modified",
                ),
                ChangedFileInfo(
                    filename="data25_ML_회귀_python구현.ipynb",
                    additions=887,
                    deletions=0,
                    status="modified",
                ),
            ),
        )
