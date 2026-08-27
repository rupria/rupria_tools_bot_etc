from __future__ import annotations

import discord

from .config import WatchTarget
from .github_client import CommitInfo, CompareInfo


def short_sha(value: str) -> str:
    return value[:7]


def first_line(text: str) -> str:
    return text.splitlines()[0].strip() if text else ""


def truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def build_commit_embed(
    watch: WatchTarget,
    previous_sha: str,
    latest_commit: CommitInfo,
    compare_info: CompareInfo | None,
) -> discord.Embed:
    summary = f"{compare_info.total_commits}개 커밋 반영" if compare_info and compare_info.total_commits else "새 커밋 반영"
    links = [f"[커밋 열기]({latest_commit.html_url})"]
    if compare_info and compare_info.html_url:
        links.append(f"[변경 보기]({compare_info.html_url})")

    embed = discord.Embed(
        title="브랜치 업데이트 알림",
        description=f"{truncate(first_line(latest_commit.message), 180)}\n{' | '.join(links)}",
        color=discord.Color.red(),
    )
    embed.add_field(name="저장소", value=watch.repository, inline=True)
    embed.add_field(name="브랜치", value=watch.branch, inline=True)
    embed.add_field(name="작성자", value=latest_commit.author_name, inline=True)
    embed.add_field(name="이전 SHA", value=short_sha(previous_sha) if previous_sha else "-", inline=True)
    embed.add_field(name="현재 SHA", value=short_sha(latest_commit.sha), inline=True)
    embed.add_field(name="반영 수", value=summary, inline=True)
    if latest_commit.committed_at:
        embed.timestamp = discord.utils.parse_time(latest_commit.committed_at)
    embed.set_footer(text="GitHub 브랜치 HEAD 변경을 감지했습니다.")
    return embed


def build_help_text(prefix: str) -> str:
    return "\n".join(
        [
            "사용 가능한 명령",
            f"{prefix}watch list",
            f"{prefix}watch branches [owner/repo]",
            f"{prefix}watch add owner/repo branch [#channel]",
            f"{prefix}watch remove owner/repo branch [#channel]",
            f"{prefix}watch check",
            f"{prefix}watch test [#channel]",
        ]
    )


def build_list_text(watches: list[WatchTarget]) -> str:
    if not watches:
        return "현재 등록된 감시 대상이 없습니다."
    lines = [f"현재 감시 대상 {len(watches)}개"]
    for index, watch in enumerate(watches, start=1):
        lines.append(f"{index}. {watch.repository} @ {watch.branch} -> <#{watch.channel_id}> [{watch.source}]")
    return "\n".join(lines)


def build_branch_list_text(watches: list[WatchTarget], repository: str | None = None) -> str:
    if not watches:
        if repository:
            return f"감시 중인 저장소를 찾지 못했습니다.\n{repository}"
        return "현재 등록된 감시 대상이 없습니다."

    grouped: dict[str, dict[str, list[WatchTarget]]] = {}
    for watch in sorted(watches, key=lambda item: (item.repository.lower(), item.branch, item.channel_id)):
        grouped.setdefault(watch.repository, {}).setdefault(watch.branch, []).append(watch)

    heading = "브랜치 기준 감시 현황"
    if repository:
        heading = f"{repository} 브랜치 감시 현황"

    lines = [f"{heading} {len(watches)}개"]
    for repo_name, branches in grouped.items():
        lines.append(repo_name)
        for branch_name, branch_watches in branches.items():
            channels = ", ".join(
                f"<#{branch_watch.channel_id}> [{branch_watch.source}]"
                for branch_watch in branch_watches
            )
            lines.append(f"- {branch_name}: {channels}")
    return "\n".join(lines)


def build_startup_text(watches: list[WatchTarget], poll_interval_ms: int) -> str:
    return "\n".join(
        [
            "git_T_bot 실행됨",
            f"감시 대상: {len(watches)}개",
            f"주기: {round(poll_interval_ms / 1000)}초",
        ]
    )


def build_watch_added_text(watch: WatchTarget, latest_sha: str) -> str:
    return "\n".join(
        [
            "감시를 추가했습니다.",
            f"{watch.repository} @ {watch.branch} -> <#{watch.channel_id}>",
            f"기준 SHA: {short_sha(latest_sha)}",
        ]
    )


def build_watch_removed_text(watch: WatchTarget) -> str:
    return "\n".join(
        [
            "감시를 제거했습니다.",
            f"{watch.repository} @ {watch.branch} -> <#{watch.channel_id}>",
        ]
    )


def build_poll_summary_text(result: dict[str, int | bool]) -> str:
    if result.get("skipped"):
        return "이미 점검이 진행 중이라 이번 요청은 건너뛰었습니다."
    return "\n".join(
        [
            "점검 완료",
            f"감시 대상: {result['watch_count']}개",
            f"초기화: {result['initialized_count']}개",
            f"새 알림: {result['changed_count']}개",
            f"오류: {result['error_count']}개",
        ]
    )
