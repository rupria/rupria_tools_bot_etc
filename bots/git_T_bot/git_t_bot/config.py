from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import os
import re

from dotenv import load_dotenv


REPOSITORY_PREFIX_PATTERN = re.compile(r"^(https?://github\.com/|git@github\.com:)", re.IGNORECASE)


@dataclass(frozen=True)
class WatchTarget:
    repository: str
    branch: str
    channel_id: str
    source: str = "saved"

    def normalized(self) -> "WatchTarget":
        return WatchTarget(
            repository=normalize_repository(self.repository),
            branch=normalize_branch(self.branch),
            channel_id=normalize_channel_id(self.channel_id),
            source=self.source,
        )

    def with_source(self, source: str) -> "WatchTarget":
        return replace(self, source=source)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    guild_id: str
    admin_channel_id: str
    allowed_role_ids: tuple[str, ...]
    github_token: str
    poll_interval_ms: int
    startup_watches: tuple[WatchTarget, ...]
    command_prefix: str
    startup_notify: bool
    data_dir: Path
    watch_file: Path
    state_file: Path


def parse_csv_list(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def normalize_repository(value: str) -> str:
    trimmed = value.strip().removesuffix(".git")
    if not trimmed:
        raise ValueError("저장소 이름이 비어 있습니다.")
    cleaned = REPOSITORY_PREFIX_PATTERN.sub("", trimmed)
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) != 2:
        raise ValueError(f"GitHub 저장소 형식이 아닙니다: {value}")
    return f"{parts[0]}/{parts[1]}"


def normalize_branch(value: str) -> str:
    branch = value.strip()
    if not branch:
        raise ValueError("브랜치 이름이 비어 있습니다.")
    return branch


def normalize_channel_id(value: str) -> str:
    channel_id = value.strip()
    if not re.fullmatch(r"\d{17,20}", channel_id):
        raise ValueError(f"Discord 채널 ID 형식이 아닙니다: {value}")
    return channel_id


def normalize_watch(watch: WatchTarget) -> WatchTarget:
    return watch.normalized()


def create_watch_key(watch: WatchTarget) -> str:
    normalized = normalize_watch(watch)
    return f"{normalized.repository.lower()}::{normalized.branch}::{normalized.channel_id}"


def dedupe_watches(watches: list[WatchTarget]) -> list[WatchTarget]:
    deduped: dict[str, WatchTarget] = {}
    for watch in watches:
        normalized = normalize_watch(watch)
        deduped[create_watch_key(normalized)] = normalized
    return list(deduped.values())


def parse_watch_targets(value: str) -> tuple[WatchTarget, ...]:
    if not value.strip():
        return ()
    watches: list[WatchTarget] = []
    for item in re.split(r"[\r\n,]+", value):
        stripped = item.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in stripped.split("|")]
        if len(parts) != 3:
            raise ValueError(f"WATCH_TARGETS 항목 형식이 잘못되었습니다: {item}")
        watches.append(WatchTarget(parts[0], parts[1], parts[2], source="env").normalized())
    return tuple(watches)


def parse_bool(value: str, default: bool) -> bool:
    if not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(project_root: Path) -> Settings:
    load_dotenv(project_root / ".env")

    bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN이 필요합니다.")

    admin_channel_id = os.getenv("DISCORD_ADMIN_CHANNEL_ID", "").strip()
    if admin_channel_id:
        normalize_channel_id(admin_channel_id)

    poll_interval_ms = int(os.getenv("WATCH_POLL_INTERVAL_MS", "60000"))
    if poll_interval_ms < 10000:
        raise RuntimeError("WATCH_POLL_INTERVAL_MS는 10000 이상이어야 합니다.")

    data_dir = project_root / "data"
    return Settings(
        bot_token=bot_token,
        guild_id=os.getenv("DISCORD_GUILD_ID", "").strip(),
        admin_channel_id=admin_channel_id,
        allowed_role_ids=parse_csv_list(os.getenv("DISCORD_ALLOWED_ROLE_IDS", "")),
        github_token=os.getenv("GITHUB_TOKEN", "").strip(),
        poll_interval_ms=poll_interval_ms,
        startup_watches=parse_watch_targets(os.getenv("WATCH_TARGETS", "")),
        command_prefix=os.getenv("COMMAND_PREFIX", "!").strip() or "!",
        startup_notify=parse_bool(os.getenv("STARTUP_NOTIFY", "true"), True),
        data_dir=data_dir,
        watch_file=data_dir / "watchers.json",
        state_file=data_dir / "runtime-state.json",
    )
