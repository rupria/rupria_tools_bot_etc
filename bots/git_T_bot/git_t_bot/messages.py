from __future__ import annotations

import discord

from .config import WatchTarget
from .github_client import ChangedFileInfo, CommitInfo, CompareCommitInfo, CompareInfo


def short_sha(value: str) -> str:
    return value[:7]


def first_line(text: str) -> str:
    return text.splitlines()[0].strip() if text else ""


def truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def owner_name(repository: str) -> str:
    return repository.split("/", 1)[0]


def build_change_scale_text(compare_info: CompareInfo | None) -> str:
    if compare_info is None:
        return "변경 규모: 커밋 1개"

    file_count = len(compare_info.files)
    commit_count = compare_info.total_commits or len(compare_info.commits) or 1
    if not compare_info.files:
        return f"변경 규모: 커밋 {commit_count}개"

    return f"변경 규모: {file_count}개 파일 · {commit_count}개 커밋"


def build_commit_summary_lines(latest_commit: CommitInfo, compare_info: CompareInfo | None) -> list[str]:
    commit_items: tuple[CompareCommitInfo, ...]
    if compare_info and compare_info.commits:
        commit_items = compare_info.commits
    else:
        commit_items = (
            CompareCommitInfo(
                sha=latest_commit.sha,
                html_url=latest_commit.html_url,
                message=latest_commit.message,
                author_name=latest_commit.author_name,
            ),
        )

    lines = [
        f"[`{short_sha(commit.sha)}`]({commit.html_url or latest_commit.html_url}) {truncate(first_line(commit.message), 90)}"
        for commit in commit_items[:4]
    ]
    remaining_count = len(commit_items) - len(lines)
    if remaining_count > 0:
        lines.append(f"... 외 {remaining_count}개 커밋")
    return lines


def build_author_summary(latest_commit: CommitInfo, compare_info: CompareInfo | None) -> str:
    authors: list[str] = []
    if compare_info and compare_info.commits:
        for commit in compare_info.commits:
            if commit.author_name not in authors:
                authors.append(commit.author_name)
    if not authors:
        authors.append(latest_commit.author_name)
    if len(authors) <= 3:
        return "\n".join(authors)
    return "\n".join([*authors[:3], f"... 외 {len(authors) - 3}명"])


def format_changed_file_line(changed_file: ChangedFileInfo) -> str:
    file_name = truncate(changed_file.filename, 72)
    return f"`{file_name}` +{changed_file.additions} / -{changed_file.deletions}"


def build_file_summary_lines(compare_info: CompareInfo | None) -> list[str]:
    if not compare_info or not compare_info.files:
        return ["비교 파일 정보가 아직 없습니다."]

    lines = [format_changed_file_line(changed_file) for changed_file in compare_info.files[:5]]
    remaining_count = len(compare_info.files) - len(lines)
    if remaining_count > 0:
        lines.append(f"... 외 {remaining_count}개 파일")
    return lines


def build_commit_embed(
    watch: WatchTarget,
    previous_sha: str,
    latest_commit: CommitInfo,
    compare_info: CompareInfo | None,
) -> discord.Embed:
    links = [f"[커밋 열기]({latest_commit.html_url})"]
    if compare_info and compare_info.html_url:
        links.append(f"[변경 보기]({compare_info.html_url})")

    embed = discord.Embed(
        title=f"{watch.repository} · {watch.branch}",
        url=compare_info.html_url if compare_info and compare_info.html_url else latest_commit.html_url,
        description="\n".join(
            [
                f"감시 사용자: {owner_name(watch.repository)}",
                build_change_scale_text(compare_info),
                " | ".join(links),
            ]
        ),
        color=discord.Color.red(),
    )
    commit_count = compare_info.total_commits if compare_info and compare_info.total_commits else 1
    embed.add_field(
        name=f"커밋 메시지 ({commit_count}개)",
        value="\n".join(build_commit_summary_lines(latest_commit, compare_info)),
        inline=False,
    )
    embed.add_field(
        name="커밋 작성자",
        value=build_author_summary(latest_commit, compare_info),
        inline=False,
    )
    embed.add_field(
        name="변경 파일 · 줄 수",
        value="\n".join(build_file_summary_lines(compare_info)),
        inline=False,
    )
    embed.add_field(
        name="비교 범위",
        value=f"{short_sha(previous_sha) if previous_sha else '-'} -> {short_sha(latest_commit.sha)}",
        inline=False,
    )
    if latest_commit.committed_at:
        embed.timestamp = discord.utils.parse_time(latest_commit.committed_at)
    embed.set_footer(text="중앙 GitHub 감시 봇. 대상 저장소 설치 불필요")
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
