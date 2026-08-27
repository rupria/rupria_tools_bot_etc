from __future__ import annotations

import logging
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands, tasks

from git_t_bot.config import WatchTarget, create_watch_key, dedupe_watches, load_settings, normalize_repository
from git_t_bot.github_client import GitHubClient
from git_t_bot.messages import (
    build_branch_list_text,
    build_commit_embed,
    build_help_text,
    build_list_text,
    build_poll_summary_text,
    build_startup_text,
    build_watch_added_text,
    build_watch_removed_text,
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

bot = commands.Bot(command_prefix=settings.command_prefix, intents=intents, help_command=None)
github = GitHubClient(settings.github_token)
saved_watches = load_persisted_watches(settings.watch_file)
runtime_state = load_runtime_state(settings.state_file)
last_admin_errors: dict[str, str] = {}
poll_in_flight = False
http_session: aiohttp.ClientSession | None = None


def get_all_watches() -> list[WatchTarget]:
    env_watches = [watch.with_source("env") for watch in settings.startup_watches]
    file_watches = [watch.with_source("saved") for watch in saved_watches]
    return dedupe_watches([*env_watches, *file_watches])


def is_authorized(ctx: commands.Context[commands.Bot]) -> bool:
    if ctx.guild is None:
        return False
    if settings.guild_id and str(ctx.guild.id) != settings.guild_id:
        return False
    if settings.admin_channel_id and str(ctx.channel.id) != settings.admin_channel_id:
        return False
    if not settings.allowed_role_ids:
        return True
    author_roles = getattr(ctx.author, "roles", [])
    return any(str(role.id) in settings.allowed_role_ids for role in author_roles)


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


async def bootstrap_watch(watch: WatchTarget) -> str:
    session = await get_session()
    latest_commit = await github.get_latest_commit(session, watch.repository, watch.branch)
    set_head_state(watch, latest_commit.sha)
    save_runtime_state(settings.state_file, runtime_state)
    return latest_commit.sha


async def announce_watch_error(watch: WatchTarget, error: Exception) -> None:
    key = create_watch_key(watch)
    message = f"{watch.repository}@{watch.branch}: {error}"
    if last_admin_errors.get(key) == message:
        return
    last_admin_errors[key] = message
    await send_admin_notice(f"GitHub 감시 오류\n{watch.repository} @ {watch.branch}\n{error}")


async def send_commit_alert(watch: WatchTarget, previous_sha: str, latest_commit) -> None:
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

    embed = build_commit_embed(watch, previous_sha, latest_commit, compare_info)
    await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


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
                    await send_commit_alert(watch, previous_sha, latest_commit)
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


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s", bot.user)
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
async def watch_list(ctx: commands.Context[commands.Bot]) -> None:
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return
    await reply(ctx, build_list_text(get_all_watches()))


@watch_group.command(name="branches")
async def watch_branches(
    ctx: commands.Context[commands.Bot],
    repository: str | None = None,
) -> None:
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    watches = get_all_watches()
    normalized_repository = None
    if repository:
        try:
            normalized_repository = normalize_repository(repository)
        except ValueError as error:
            await reply(ctx, str(error))
            return
        watches = [
            watch
            for watch in watches
            if watch.repository.lower() == normalized_repository.lower()
        ]

    await reply(ctx, build_branch_list_text(watches, normalized_repository))


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
    channel: discord.TextChannel | None = None,
) -> None:
    global saved_watches
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    target_channel = channel or ctx.channel
    watch = WatchTarget(repository=repository, branch=branch, channel_id=str(target_channel.id))
    if any(create_watch_key(item) == create_watch_key(watch) for item in get_all_watches()):
        await reply(ctx, f"이미 감시 중입니다.\n{watch.repository} @ {watch.branch} -> <#{watch.channel_id}>")
        return

    latest_sha = await bootstrap_watch(watch)
    saved_watches = dedupe_watches([*saved_watches, watch])
    save_persisted_watches(settings.watch_file, saved_watches)
    await reply(ctx, build_watch_added_text(watch, latest_sha))


@watch_group.command(name="remove")
async def watch_remove(
    ctx: commands.Context[commands.Bot],
    repository: str,
    branch: str,
    channel: discord.TextChannel | None = None,
) -> None:
    global saved_watches
    if not is_authorized(ctx):
        await reply(ctx, "이 명령은 허용된 관리 채널과 역할에서만 사용할 수 있습니다.")
        return

    target_channel = channel or ctx.channel
    watch = WatchTarget(repository=repository, branch=branch, channel_id=str(target_channel.id))

    if any(create_watch_key(item) == create_watch_key(watch) for item in settings.startup_watches):
        await reply(ctx, "이 감시는 WATCH_TARGETS 환경변수에서 온 항목이라 채팅 명령으로 지울 수 없습니다.")
        return

    before = len(saved_watches)
    saved_watches = [item for item in saved_watches if create_watch_key(item) != create_watch_key(watch)]
    if before == len(saved_watches):
        await reply(ctx, f"일치하는 감시 대상을 찾지 못했습니다.\n{watch.repository} @ {watch.branch} -> <#{watch.channel_id}>")
        return

    runtime_state["branches"].pop(create_watch_key(watch), None)
    save_persisted_watches(settings.watch_file, saved_watches)
    save_runtime_state(settings.state_file, runtime_state)
    await reply(ctx, build_watch_removed_text(watch))


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
    )
    embed = build_commit_embed(
        watch,
        "1234567oldsha1234567oldsha1234567oldsha",
        github.make_demo_commit(),
        github.make_demo_compare(),
    )
    await target_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    await reply(ctx, f"테스트 알림을 <#{target_channel.id}> 채널로 전송했습니다.")


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
