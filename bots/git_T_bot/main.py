from __future__ import annotations

import logging
from pathlib import Path
import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from git_t_bot.config import (
    WatchTarget,
    create_watch_key,
    dedupe_watches,
    load_settings,
    normalize_branch_targets,
    normalize_repository_targets,
    normalize_user_targets,
)
from git_t_bot.github_client import GitHubClient
from git_t_bot.messages import (
    build_branch_list_text,
    build_commit_embed,
    build_help_text,
    build_list_text,
    build_poll_summary_text,
    build_repository_branch_catalog_text,
    build_startup_text,
    build_watch_batch_added_text,
    build_watch_batch_removed_text,
)
from git_t_bot.storage import (
    ensure_data_dir,
    load_persisted_watches,
    load_runtime_state,
    save_persisted_watches,
    save_runtime_state,
)


PROJECT_ROOT = Path(__file__).resolve().parent
settings = load_settings(PROJECT_ROOT)
ensure_data_dir(settings.data_dir)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
logger = logging.getLogger("git_t_bot")

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True


async def close_http_session() -> None:
    global http_session
    if http_session is not None and not http_session.closed:
        await http_session.close()
    http_session = None


class GitTBot(commands.Bot):
    async def close(self) -> None:
        await close_http_session()
        await super().close()


bot = GitTBot(command_prefix=settings.command_prefix, intents=intents, help_command=None)
github = GitHubClient(settings.github_token)
saved_watches = load_persisted_watches(settings.watch_file)
runtime_state = load_runtime_state(settings.state_file)
last_admin_errors: dict[str, str] = {}
poll_in_flight = False
http_session: aiohttp.ClientSession | None = None
CHANNEL_MENTION_PATTERN = re.compile(r"^<#(\d{17,20})>$")


def get_all_watches() -> list[WatchTarget]:
    env_watches = [watch.with_source("env") for watch in settings.startup_watches]
    file_watches = [watch.with_source("saved") for watch in saved_watches]
    return dedupe_watches([*env_watches, *file_watches])


def watch_belongs_to_guild(watch: WatchTarget, guild: discord.Guild | None) -> bool:
    if guild is None:
        return False
    try:
        channel = guild.get_channel_or_thread(int(watch.channel_id))
    except (TypeError, ValueError):
        return False
    return channel is not None


def get_visible_watches(guild: discord.Guild | None) -> list[WatchTarget]:
    return [watch for watch in get_all_watches() if watch_belongs_to_guild(watch, guild)]


def is_discord_administrator(member: object) -> bool:
    permissions = getattr(member, "guild_permissions", None)
    return bool(getattr(permissions, "administrator", False))


def is_member_authorized(member: object) -> bool:
    if is_discord_administrator(member):
        return True
    if not settings.allowed_role_ids:
        return True
    author_roles = getattr(member, "roles", [])
    return any(str(role.id) in settings.allowed_role_ids for role in author_roles)


def is_authorized(ctx: commands.Context[commands.Bot]) -> bool:
    if ctx.guild is None:
        return False
    if is_discord_administrator(ctx.author):
        return True
    if settings.guild_id and str(ctx.guild.id) != settings.guild_id:
        return False
    if settings.admin_channel_id and str(ctx.channel.id) != settings.admin_channel_id:
        return False
    return is_member_authorized(ctx.author)


def is_interaction_authorized(interaction: discord.Interaction) -> bool:
    if interaction.guild is None or interaction.channel is None:
        return False
    if is_discord_administrator(interaction.user):
        return True
    if settings.guild_id and str(interaction.guild.id) != settings.guild_id:
        return False
    if settings.admin_channel_id and str(interaction.channel.id) != settings.admin_channel_id:
        return False
    return is_member_authorized(interaction.user)


def normalize_repository_filters(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return ("*",)
    return normalize_repository_targets(value)


def normalize_branch_filters(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return ("*",)
    return normalize_branch_targets(value)


def normalize_user_filters(value: str | None) -> tuple[str, ...]:
    if value is None or not value.strip():
        return ("*",)
    return normalize_user_targets(value)


def is_wildcard_filter(values: tuple[str, ...]) -> bool:
    return len(values) == 1 and values[0] == "*"


def build_match_set(values: tuple[str, ...]) -> set[str] | None:
    if is_wildcard_filter(values):
        return None
    return {value.lower() for value in values}


def filter_watches(
    watches: list[WatchTarget],
    repositories: tuple[str, ...] = ("*",),
    branches: tuple[str, ...] = ("*",),
    users: tuple[str, ...] = ("*",),
) -> list[WatchTarget]:
    repository_matches = build_match_set(repositories)
    branch_matches = build_match_set(branches)
    user_matches = build_match_set(users)
    filtered: list[WatchTarget] = []
    for watch in watches:
        if repository_matches is not None and watch.repository.lower() not in repository_matches:
            continue
        if branch_matches is not None and watch.branch.lower() not in branch_matches:
            continue
        if user_matches is not None and watch.user.lower() not in user_matches:
            continue
        filtered.append(watch)
    return filtered


def resolve_channel_argument(
    guild: discord.Guild | None,
    value: str,
) -> discord.TextChannel | discord.Thread | None:
    if guild is None:
        return None
    channel_id = ""
    match = CHANNEL_MENTION_PATTERN.fullmatch(value.strip())
    if match:
        channel_id = match.group(1)
    elif value.strip().isdigit():
        channel_id = value.strip()
    if not channel_id:
        return None
    channel = guild.get_channel_or_thread(int(channel_id))
    if isinstance(channel, (discord.TextChannel, discord.Thread)):
        return channel
    raise commands.BadArgument("텍스트 채널 또는 스레드만 감시 채널로 사용할 수 있습니다.")


def parse_watch_extra_arguments(
    ctx: commands.Context[commands.Bot],
    extra: tuple[str, ...],
) -> tuple[tuple[str, ...], discord.TextChannel | discord.Thread]:
    if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
        raise commands.BadArgument("텍스트 채널 또는 스레드에서만 감시를 등록할 수 있습니다.")

    user_inputs: list[str] = []
    target_channel: discord.TextChannel | discord.Thread = ctx.channel
    for item in extra:
        maybe_channel = resolve_channel_argument(ctx.guild, item)
        if maybe_channel is not None:
            target_channel = maybe_channel
            continue
        user_inputs.append(item)

    if not user_inputs:
        return ("*",), target_channel
    return normalize_user_targets(",".join(user_inputs)), target_channel


def build_watch_targets(
    repositories: tuple[str, ...],
    branches: tuple[str, ...],
    users: tuple[str, ...],
    channel_id: str,
) -> list[WatchTarget]:
    return dedupe_watches(
        [
            WatchTarget(repository=repository, branch=branch, channel_id=channel_id, user=user)
            for repository in repositories
            for branch in branches
            for user in users
        ]
    )


def author_matches_filter(author_name: str, user: str) -> bool:
    if user == "*":
        return True
    cleaned_author = author_name.strip().removeprefix("@").lower()
    return bool(cleaned_author) and cleaned_author == user


def should_send_alert(watch: WatchTarget, latest_commit, compare_info) -> bool:
    if watch.user == "*":
        return True
    if compare_info and compare_info.commits:
        return any(author_matches_filter(commit.author_name, watch.user) for commit in compare_info.commits)
    return author_matches_filter(latest_commit.author_name, watch.user)


async def reply_interaction(
    interaction: discord.Interaction,
    content: str,
    *,
    ephemeral: bool = True,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(
            content,
            ephemeral=ephemeral,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return
    await interaction.response.send_message(
        content,
        ephemeral=ephemeral,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def build_repository_branch_catalog(
    repository: str,
    branch_filters: tuple[str, ...] = ("*",),
    user_filters: tuple[str, ...] = ("*",),
    visible_watches: list[WatchTarget] | None = None,
) -> str:
    session = await get_session()
    branches = await github.list_branches(session, repository)
    branch_names = None if is_wildcard_filter(branch_filters) else {item.lower() for item in branch_filters}
    filtered_branches = tuple(
        branch_info
        for branch_info in sorted(branches, key=lambda item: item.name.lower())
        if branch_names is None or branch_info.name.lower() in branch_names
    )
    matching_watches = filter_watches(visible_watches or get_all_watches(), (repository,), branch_filters, user_filters)
    if not filtered_branches:
        return "\n".join(
            [
                "조건과 일치하는 GitHub 브랜치를 찾지 못했습니다.",
                f"레포지토리 : {repository}",
                f"브랜치 : {', '.join(branch_filters)}",
                f"감지 사용자 : {', '.join('*' if user == '*' else f'@{user}' for user in user_filters)}",
            ]
        )
    return build_repository_branch_catalog_text(
        repository,
        filtered_branches,
        matching_watches,
        branch_filters,
        user_filters,
    )


async def build_repository_branch_catalogs(
    repositories: tuple[str, ...],
    branch_filters: tuple[str, ...],
    user_filters: tuple[str, ...],
    visible_watches: list[WatchTarget] | None = None,
) -> str:
    return "\n\n".join(
        [
            await build_repository_branch_catalog(repository, branch_filters, user_filters, visible_watches)
            for repository in repositories
        ]
    )


async def reply(ctx: commands.Context[commands.Bot], content: str) -> None:
    await ctx.reply(content, mention_author=False, allowed_mentions=discord.AllowedMentions.none())


async def send_admin_notice(content: str) -> None:
    if not settings.admin_channel_id:
        logger.warning(content)
        return
    try:
        channel = bot.get_channel(int(settings.admin_channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(settings.admin_channel_id))
    except Exception:
        logger.warning("failed to resolve admin channel %s", settings.admin_channel_id)
        return
    if isinstance(channel, (discord.TextChannel, discord.Thread)):
        try:
            await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
            return
        except Exception:
            logger.warning("failed to send admin notice to %s", settings.admin_channel_id)
            logger.warning(content)
            return
    logger.warning(content)


def set_head_state(watch: WatchTarget, latest_sha: str) -> None:
    runtime_state["branches"][create_watch_key(watch)] = {
        "repository": watch.repository,
        "branch": watch.branch,
        "channel_id": watch.channel_id,
        "last_seen_sha": latest_sha,
    }


async def get_session() -> aiohttp.ClientSession:
    global http_session
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    return http_session


async def bootstrap_watches(watches: list[WatchTarget]) -> dict[str, str]:
    session = await get_session()
    cached_heads: dict[tuple[str, str], str] = {}
    latest_shas: dict[str, str] = {}
    for watch in watches:
        branch_key = (watch.repository.lower(), watch.branch.lower())
        latest_sha = cached_heads.get(branch_key)
        if latest_sha is None:
            latest_commit = await github.get_latest_commit(session, watch.repository, watch.branch)
            latest_sha = latest_commit.sha
            cached_heads[branch_key] = latest_sha
        set_head_state(watch, latest_sha)
        latest_shas[create_watch_key(watch)] = latest_sha
    save_runtime_state(settings.state_file, runtime_state)
    return latest_shas


async def announce_watch_error(watch: WatchTarget, error: Exception) -> None:
    key = create_watch_key(watch)
    message = f"{watch.repository}@{watch.branch}: {error}"
    if last_admin_errors.get(key) == message:
        return
    last_admin_errors[key] = message
    await send_admin_notice(f"GitHub 감시 오류\n{watch.repository} @ {watch.branch}\n{error}")


async def send_commit_alert(watch: WatchTarget, previous_sha: str, latest_commit) -> bool:
    channel = bot.get_channel(int(watch.channel_id))
    if channel is None:
        channel = await bot.fetch_channel(int(watch.channel_id))
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        raise RuntimeError(f"텍스트 채널을 찾지 못했습니다: {watch.channel_id}")

    compare_info = None
    if previous_sha and previous_sha != latest_commit.sha:
        session = await get_session()
        try:
            compare_info = await github.compare_commits(
                session,
                watch.repository,
                previous_sha,
                latest_commit.sha,
            )
        except Exception:
            compare_info = None

    if not should_send_alert(watch, latest_commit, compare_info):
        return False

    embed = build_commit_embed(watch, previous_sha, latest_commit, compare_info)
    await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    return True


async def poll_watches() -> dict[str, int | bool]:
    global poll_in_flight
    if poll_in_flight:
        return {
            "watch_count": len(get_all_watches()),
            "initialized_count": 0,
            "changed_count": 0,
            "error_count": 0,
            "skipped": True,
        }

    poll_in_flight = True
    result = {
        "watch_count": len(get_all_watches()),
        "initialized_count": 0,
        "changed_count": 0,
        "error_count": 0,
        "skipped": False,
    }
    try:
        session = await get_session()
        for watch in get_all_watches():
            try:
                latest_commit = await github.get_latest_commit(session, watch.repository, watch.branch)
                previous_sha = str(
                    runtime_state["branches"].get(create_watch_key(watch), {}).get("last_seen_sha", "")
                )

                if not previous_sha:
                    set_head_state(watch, latest_commit.sha)
                    result["initialized_count"] += 1
                    continue

                if previous_sha != latest_commit.sha:
                    if await send_commit_alert(watch, previous_sha, latest_commit):
                        result["changed_count"] += 1

                set_head_state(watch, latest_commit.sha)
                last_admin_errors.pop(create_watch_key(watch), None)
            except Exception as error:
                logger.exception("watch poll failed for %s @ %s", watch.repository, watch.branch)
                result["error_count"] += 1
                await announce_watch_error(watch, error)
    finally:
        save_runtime_state(settings.state_file, runtime_state)
        poll_in_flight = False
    return result


async def sync_application_commands() -> None:
    try:
        global_synced = await bot.tree.sync()
        logger.info("Synced %s global app commands", len(global_synced))
        if settings.guild_id:
            guild = discord.Object(id=int(settings.guild_id))
            bot.tree.copy_global_to(guild=guild)
            guild_synced = await bot.tree.sync(guild=guild)
            logger.info("Synced %s guild app commands", len(guild_synced))
    except Exception:
        logger.exception("failed to sync application commands")


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s", bot.user)
    await sync_application_commands()
    if settings.startup_notify:
        await send_admin_notice(build_startup_text(get_all_watches(), settings.poll_interval_ms))
    if not watch_loop.is_running():
        watch_loop.start()


@tasks.loop(seconds=max(settings.poll_interval_ms / 1000.0, 10.0))
async def watch_loop() -> None:
    await poll_watches()


@watch_loop.before_loop
async def before_watch_loop() -> None:
    await bot.wait_until_ready()


@bot.group(name="watch", invoke_without_command=True)
async def watch_group(ctx: commands.Context[commands.Bot]) -> None:
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return
    await reply(ctx, build_help_text(settings.command_prefix))


@watch_group.command(name="list")
async def watch_list(
    ctx: commands.Context[commands.Bot],
    repository: str | None = None,
    branch: str | None = None,
    user: str | None = None,
) -> None:
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return
    try:
        normalized_repositories = normalize_repository_filters(repository)
        normalized_branches = normalize_branch_filters(branch)
        normalized_users = normalize_user_filters(user)
    except ValueError as error:
        await reply(ctx, str(error))
        return

    watches = filter_watches(get_visible_watches(ctx.guild), normalized_repositories, normalized_branches, normalized_users)
    await reply(ctx, build_list_text(watches, normalized_repositories, normalized_branches, normalized_users))


@watch_group.command(name="branches")
async def watch_branches(
    ctx: commands.Context[commands.Bot],
    repository: str | None = None,
    branch: str | None = None,
    user: str | None = None,
) -> None:
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    try:
        normalized_branches = normalize_branch_filters(branch)
        normalized_users = normalize_user_filters(user)
    except ValueError as error:
        await reply(ctx, str(error))
        return

    visible_watches = get_visible_watches(ctx.guild)
    if not repository or repository.strip() == "*":
        watches = filter_watches(visible_watches, ("*",), normalized_branches, normalized_users)
        await reply(ctx, build_branch_list_text(watches, None, normalized_branches, normalized_users))
        return

    try:
        normalized_repositories = normalize_repository_targets(repository, allow_wildcard=False)
        text = await build_repository_branch_catalogs(
            normalized_repositories,
            normalized_branches,
            normalized_users,
            visible_watches,
        )
    except Exception as error:
        await reply(ctx, str(error))
        return

    await reply(ctx, text)


@watch_group.command(name="check")
async def watch_check(ctx: commands.Context[commands.Bot]) -> None:
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return
    result = await poll_watches()
    await reply(ctx, build_poll_summary_text(result))


@watch_group.command(name="add")
async def watch_add(
    ctx: commands.Context[commands.Bot],
    repository: str,
    branch: str,
    *extra: str,
) -> None:
    global saved_watches
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    try:
        normalized_repositories = normalize_repository_targets(repository, allow_wildcard=False)
        normalized_branches = normalize_branch_targets(branch, allow_wildcard=False)
        normalized_users, target_channel = parse_watch_extra_arguments(ctx, extra)
    except ValueError as error:
        await reply(ctx, str(error))
        return

    requested_watches = build_watch_targets(
        normalized_repositories,
        normalized_branches,
        normalized_users,
        str(target_channel.id),
    )
    existing_keys = {create_watch_key(item) for item in get_all_watches()}
    existing_watches = [watch for watch in requested_watches if create_watch_key(watch) in existing_keys]
    new_watches = [watch for watch in requested_watches if create_watch_key(watch) not in existing_keys]

    if not new_watches:
        await reply(ctx, build_watch_batch_added_text([], {}, existing_watches))
        return

    latest_shas = await bootstrap_watches(new_watches)
    saved_watches = dedupe_watches([*saved_watches, *new_watches])
    save_persisted_watches(settings.watch_file, saved_watches)
    await reply(ctx, build_watch_batch_added_text(new_watches, latest_shas, existing_watches))


@watch_group.command(name="remove")
async def watch_remove(
    ctx: commands.Context[commands.Bot],
    repository: str,
    branch: str,
    *extra: str,
) -> None:
    global saved_watches
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    try:
        normalized_repositories = normalize_repository_targets(repository, allow_wildcard=False)
        normalized_branches = normalize_branch_targets(branch, allow_wildcard=False)
        normalized_users, target_channel = parse_watch_extra_arguments(ctx, extra)
    except ValueError as error:
        await reply(ctx, str(error))
        return

    requested_watches = build_watch_targets(
        normalized_repositories,
        normalized_branches,
        normalized_users,
        str(target_channel.id),
    )
    startup_keys = {create_watch_key(item) for item in settings.startup_watches}
    saved_keys = {create_watch_key(item) for item in saved_watches}
    locked_watches = [watch for watch in requested_watches if create_watch_key(watch) in startup_keys]
    removed_watches = [watch for watch in requested_watches if create_watch_key(watch) in saved_keys]
    missing_watches = [
        watch
        for watch in requested_watches
        if create_watch_key(watch) not in startup_keys and create_watch_key(watch) not in saved_keys
    ]

    removed_keys = {create_watch_key(watch) for watch in removed_watches}
    saved_watches = [item for item in saved_watches if create_watch_key(item) not in removed_keys]
    for watch in removed_watches:
        runtime_state["branches"].pop(create_watch_key(watch), None)
    save_persisted_watches(settings.watch_file, saved_watches)
    save_runtime_state(settings.state_file, runtime_state)
    await reply(ctx, build_watch_batch_removed_text(removed_watches, missing_watches, locked_watches))


@watch_group.command(name="test")
async def watch_test(
    ctx: commands.Context[commands.Bot],
    channel: discord.TextChannel | None = None,
) -> None:
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    target_channel = channel or ctx.channel
    watch = WatchTarget(
        repository="rupria/rupria_tools_bot_etc",
        branch="main",
        channel_id=str(target_channel.id),
        user="rupria",
    )
    embed = build_commit_embed(
        watch,
        "1234567oldsha1234567oldsha1234567oldsha",
        github.make_demo_commit(),
        github.make_demo_compare(),
    )
    await target_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    await reply(ctx, f"테스트 알림을 <#{target_channel.id}> 채널로 전송했습니다.")


@bot.tree.command(name="github_watches", description="현재 감시 설정을 조회합니다.")
@app_commands.describe(
    repository="owner/repo 형식 또는 *. 여러 개는 쉼표로 구분합니다.",
    branch="브랜치명 또는 *. 여러 개는 쉼표로 구분합니다.",
    user="GitHub 사용자명 또는 *. 여러 개는 쉼표로 구분합니다.",
)
async def github_watches_command(
    interaction: discord.Interaction,
    repository: str = "*",
    branch: str = "*",
    user: str = "*",
) -> None:
    if not is_interaction_authorized(interaction):
        await reply_interaction(interaction, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    try:
        normalized_repositories = normalize_repository_filters(repository)
        normalized_branches = normalize_branch_filters(branch)
        normalized_users = normalize_user_filters(user)
    except ValueError as error:
        await reply_interaction(interaction, str(error))
        return

    watches = filter_watches(
        get_visible_watches(interaction.guild),
        normalized_repositories,
        normalized_branches,
        normalized_users,
    )
    await reply_interaction(
        interaction,
        build_list_text(watches, normalized_repositories, normalized_branches, normalized_users),
    )


@bot.tree.command(name="github_branches", description="저장소의 GitHub 브랜치와 감시 연결 상태를 조회합니다.")
@app_commands.describe(
    repository="owner/repo 형식. 여러 개는 쉼표로 구분합니다.",
    branch="브랜치명 또는 *. 여러 개는 쉼표로 구분합니다.",
    user="GitHub 사용자명 또는 *. 여러 개는 쉼표로 구분합니다.",
)
async def github_branches_command(
    interaction: discord.Interaction,
    repository: str,
    branch: str = "*",
    user: str = "*",
) -> None:
    if not is_interaction_authorized(interaction):
        await reply_interaction(interaction, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    try:
        normalized_repositories = normalize_repository_targets(repository, allow_wildcard=False)
        normalized_branches = normalize_branch_filters(branch)
        normalized_users = normalize_user_filters(user)
    except ValueError as error:
        await reply_interaction(interaction, str(error))
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        text = await build_repository_branch_catalogs(
            normalized_repositories,
            normalized_branches,
            normalized_users,
            get_visible_watches(interaction.guild),
        )
    except Exception as error:
        await reply_interaction(interaction, str(error))
        return

    await reply_interaction(interaction, text)


@bot.tree.command(name="github_watch", description="GitHub 저장소의 push 알림을 현재 채널에 등록합니다.")
@app_commands.describe(
    repository="owner/repo 형식. 여러 개는 쉼표로 구분합니다.",
    branch="실제 감시할 브랜치명. 여러 개는 쉼표로 구분합니다.",
    user="GitHub 사용자명 또는 *. 여러 개는 쉼표로 구분합니다.",
    channel="비워두면 현재 채널을 사용합니다.",
)
async def github_watch_command(
    interaction: discord.Interaction,
    repository: str,
    branch: str,
    user: str = "*",
    channel: discord.TextChannel | None = None,
) -> None:
    global saved_watches
    if not is_interaction_authorized(interaction):
        await reply_interaction(interaction, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    if channel is None and not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
        await reply_interaction(interaction, "텍스트 채널 또는 스레드에서만 감시를 등록할 수 있습니다.")
        return

    try:
        normalized_repositories = normalize_repository_targets(repository, allow_wildcard=False)
        normalized_branches = normalize_branch_targets(branch, allow_wildcard=False)
        normalized_users = normalize_user_filters(user)
    except ValueError as error:
        await reply_interaction(interaction, str(error))
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
        await reply_interaction(interaction, "텍스트 채널 또는 스레드만 감시 채널로 사용할 수 있습니다.")
        return

    requested_watches = build_watch_targets(
        normalized_repositories,
        normalized_branches,
        normalized_users,
        str(target_channel.id),
    )
    existing_keys = {create_watch_key(item) for item in get_all_watches()}
    existing_watches = [watch for watch in requested_watches if create_watch_key(watch) in existing_keys]
    new_watches = [watch for watch in requested_watches if create_watch_key(watch) not in existing_keys]

    await interaction.response.defer(ephemeral=True, thinking=True)
    if not new_watches:
        await reply_interaction(interaction, build_watch_batch_added_text([], {}, existing_watches))
        return

    latest_shas = await bootstrap_watches(new_watches)
    saved_watches = dedupe_watches([*saved_watches, *new_watches])
    save_persisted_watches(settings.watch_file, saved_watches)
    await reply_interaction(interaction, build_watch_batch_added_text(new_watches, latest_shas, existing_watches))


@bot.tree.command(name="github_unwatch", description="현재 채널에서 GitHub 저장소 감시를 해제합니다.")
@app_commands.describe(
    repository="owner/repo 형식. 여러 개는 쉼표로 구분합니다.",
    branch="제거할 브랜치명. 여러 개는 쉼표로 구분합니다.",
    user="GitHub 사용자명 또는 *. 여러 개는 쉼표로 구분합니다.",
    channel="비워두면 현재 채널을 사용합니다.",
)
async def github_unwatch_command(
    interaction: discord.Interaction,
    repository: str,
    branch: str,
    user: str = "*",
    channel: discord.TextChannel | None = None,
) -> None:
    global saved_watches
    if not is_interaction_authorized(interaction):
        await reply_interaction(interaction, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    if channel is None and not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
        await reply_interaction(interaction, "텍스트 채널 또는 스레드에서만 감시를 제거할 수 있습니다.")
        return

    try:
        normalized_repositories = normalize_repository_targets(repository, allow_wildcard=False)
        normalized_branches = normalize_branch_targets(branch, allow_wildcard=False)
        normalized_users = normalize_user_filters(user)
    except ValueError as error:
        await reply_interaction(interaction, str(error))
        return

    target_channel = channel or interaction.channel
    if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
        await reply_interaction(interaction, "텍스트 채널 또는 스레드만 감시 채널로 사용할 수 있습니다.")
        return

    requested_watches = build_watch_targets(
        normalized_repositories,
        normalized_branches,
        normalized_users,
        str(target_channel.id),
    )
    startup_keys = {create_watch_key(item) for item in settings.startup_watches}
    saved_keys = {create_watch_key(item) for item in saved_watches}
    locked_watches = [watch for watch in requested_watches if create_watch_key(watch) in startup_keys]
    removed_watches = [watch for watch in requested_watches if create_watch_key(watch) in saved_keys]
    missing_watches = [
        watch
        for watch in requested_watches
        if create_watch_key(watch) not in startup_keys and create_watch_key(watch) not in saved_keys
    ]

    removed_keys = {create_watch_key(watch) for watch in removed_watches}
    saved_watches = [item for item in saved_watches if create_watch_key(item) not in removed_keys]
    for watch in removed_watches:
        runtime_state["branches"].pop(create_watch_key(watch), None)
    save_persisted_watches(settings.watch_file, saved_watches)
    save_runtime_state(settings.state_file, runtime_state)
    await reply_interaction(interaction, build_watch_batch_removed_text(removed_watches, missing_watches, locked_watches))


@watch_group.error
async def watch_group_error(
    ctx: commands.Context[commands.Bot],
    error: commands.CommandError,
) -> None:
    if isinstance(error, commands.MissingRequiredArgument):
        await reply(ctx, build_help_text(settings.command_prefix))
        return
    if isinstance(error, commands.BadArgument):
        await reply(ctx, "입력 형식을 확인해 주세요. 채널은 멘션 형식을 권장합니다.")
        return
    raise error


def main() -> None:
    bot.run(settings.bot_token, log_handler=None)


if __name__ == "__main__":
    main()
