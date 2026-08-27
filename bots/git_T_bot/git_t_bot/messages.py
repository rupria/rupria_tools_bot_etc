from __future__ import annotations

import discord

from .config import WatchTarget
from .github_client import BranchInfo, ChangedFileInfo, CommitInfo, CompareCommitInfo, CompareInfo


def short_sha(value: str) -> str:
    return value[:7]


def first_line(text: str) -> str:
    return text.splitlines()[0].strip() if text else ""


def truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


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


def format_watch_user(user: str) -> str:
    return "*" if user == "*" else f"@{user}"


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
        title=watch.repository,
        url=compare_info.html_url if compare_info and compare_info.html_url else latest_commit.html_url,
        description="\n".join(
            [
                f"브랜치 : {watch.branch}",
                f"감지 사용자 : {format_watch_user(watch.user)}",
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
            f"{prefix}watch list [repository] [branch] [user]",
            f"{prefix}watch branches owner/repo [branch] [user]",
            f"{prefix}watch add owner/repo branch [user] [#channel]",
            f"{prefix}watch remove owner/repo branch [user] [#channel]",
            f"{prefix}watch check",
            f"{prefix}watch test [#channel]",
            "/github_watches repository:* branch:* user:*",
            "/github_branches repository:owner/repo branch:* user:*",
            "/github_watch_add repository:owner/repo branch:main user:* channel:#alerts",
            "/github_watch_remove repository:owner/repo branch:main user:* channel:#alerts",
        ]
    )


def build_list_text(
    watches: list[WatchTarget],
    repository: str = "*",
    branch: str = "*",
    user: str = "*",
) -> str:
    if not watches:
        return "\n".join(
            [
                "조건과 일치하는 감시 대상이 없습니다.",
                f"레포지토리 : {repository}",
                f"브랜치 : {branch}",
                f"감지 사용자 : {format_watch_user(user)}",
            ]
        )
    lines = [
        f"현재 감시 대상 {len(watches)}개",
        f"레포지토리 : {repository}",
        f"브랜치 : {branch}",
        f"감지 사용자 : {format_watch_user(user)}",
    ]
    for index, watch in enumerate(watches, start=1):
        lines.append(
            f"{index}. {watch.repository} / {watch.branch} / {format_watch_user(watch.user)} -> <#{watch.channel_id}> [{watch.source}]"
        )
    return "\n".join(lines)


def build_branch_list_text(
    watches: list[WatchTarget],
    repository: str | None = None,
    branch: str = "*",
    user: str = "*",
) -> str:
    if not watches:
        if repository:
            return "\n".join(
                [
                    "조건과 일치하는 감시 대상을 찾지 못했습니다.",
                    f"레포지토리 : {repository}",
                    f"브랜치 : {branch}",
                    f"감지 사용자 : {format_watch_user(user)}",
                ]
            )
        return "현재 등록된 감시 대상이 없습니다."

    grouped: dict[str, dict[str, list[WatchTarget]]] = {}
    for watch in sorted(watches, key=lambda item: (item.repository.lower(), item.branch, item.user, item.channel_id)):
        grouped.setdefault(watch.repository, {}).setdefault(watch.branch, []).append(watch)

    heading = "브랜치 기준 감시 현황"
    if repository:
        heading = f"{repository} 브랜치 감시 현황"

    lines = [
        f"{heading} {len(watches)}개",
        f"브랜치 : {branch}",
        f"감지 사용자 : {format_watch_user(user)}",
    ]
    for repo_name, branches in grouped.items():
        lines.append(repo_name)
        for branch_name, branch_watches in branches.items():
            lines.append(f"- {branch_name}")
            for branch_watch in branch_watches:
                lines.append(
                    f"  감지 사용자 : {format_watch_user(branch_watch.user)} -> <#{branch_watch.channel_id}> [{branch_watch.source}]"
                )
    return "\n".join(lines)


def build_repository_branch_catalog_text(
    repository: str,
    branches: tuple[BranchInfo, ...],
    watches: list[WatchTarget],
    branch: str = "*",
    user: str = "*",
) -> str:
    if not branches:
        return f"{repository} 저장소에서 브랜치를 찾지 못했습니다."

    lines = [
        f"{repository} 브랜치 목록 {len(branches)}개",
        f"브랜치 : {branch}",
        f"감지 사용자 : {format_watch_user(user)}",
    ]
    watches_by_branch: dict[str, list[WatchTarget]] = {}
    for watch in sorted(watches, key=lambda item: (item.branch, item.user, item.channel_id)):
        watches_by_branch.setdefault(watch.branch.lower(), []).append(watch)

    for branch_info in branches:
        suffix = " [보호]" if branch_info.protected else ""
        lines.append(f"- {branch_info.name}{suffix}")
        branch_watches = watches_by_branch.get(branch_info.name.lower(), [])
        if not branch_watches:
            lines.append("  감시 없음")
            continue
        for watch in branch_watches:
            lines.append(
                f"  감지 사용자 : {format_watch_user(watch.user)} -> <#{watch.channel_id}> [{watch.source}]"
            )
    return "\n".join(lines)


def build_startup_text(watches: list[WatchTarget], poll_interval_ms: int) -> str:
    return "git_T_bot 실행됨"


def build_watch_added_text(watch: WatchTarget, latest_sha: str) -> str:
    return "\n".join(
        [
            "감시를 추가했습니다.",
            f"레포지토리 : {watch.repository}",
            f"브랜치 : {watch.branch}",
            f"감지 사용자 : {format_watch_user(watch.user)}",
            f"채널 : <#{watch.channel_id}>",
            f"기준 SHA: {short_sha(latest_sha)}",
        ]
    )


def build_watch_removed_text(watch: WatchTarget) -> str:
    return "\n".join(
        [
            "감시를 제거했습니다.",
            f"레포지토리 : {watch.repository}",
            f"브랜치 : {watch.branch}",
            f"감지 사용자 : {format_watch_user(watch.user)}",
            f"채널 : <#{watch.channel_id}>",
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
