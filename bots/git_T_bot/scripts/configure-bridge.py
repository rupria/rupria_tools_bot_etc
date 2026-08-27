from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
CONNECT_DIR = PROJECT_ROOT / ".connect"
CONFIG_PATH = CONNECT_DIR / "config.json"
STATE_PATH = CONNECT_DIR / "state.json"
SNOWFLAKE = re.compile(r"^[0-9]{17,20}$")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    # Runtime environment variables override file values so hosted environments
    # such as DisHost can inject secrets without a committed .env file.
    for key, value in os.environ.items():
        if key.startswith(("DISCORD_", "CODEX_")):
            values[key] = value.strip()

    if not values:
        raise SystemExit(
            f"설정 값을 찾지 못했습니다. {path} 파일을 만들거나 "
            "DISCORD_/CODEX_ 환경변수를 설정하세요."
        )
    return values


def required(values: dict[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise SystemExit(f".env의 {key} 값을 입력하세요.")
    return value


def optional(values: dict[str, str], key: str, default: str = "") -> str:
    return values.get(key, default).strip()


def snowflake(values: dict[str, str], key: str) -> str:
    value = required(values, key)
    if not SNOWFLAKE.fullmatch(value):
        raise SystemExit(f"{key}는 Discord 개발자 모드에서 복사한 숫자 ID여야 합니다.")
    return value


def git_output(workspace_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def parse_repository_label(remote_url: str) -> str | None:
    cleaned = remote_url.strip().rstrip("/").removesuffix(".git")
    if "github.com/" in cleaned:
        tail = cleaned.split("github.com/", 1)[1]
        parts = [part for part in tail.split("/") if part]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    if ":" in cleaned and "@" in cleaned:
        tail = cleaned.rsplit(":", 1)[-1]
        parts = [part for part in tail.split("/") if part]
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
    return None


def detect_repository_label(values: dict[str, str], workspace_root: Path) -> str:
    explicit = optional(values, "CODEX_REPOSITORY_LABEL")
    if explicit:
        return explicit
    remote = git_output(workspace_root, "remote", "get-url", "origin")
    if remote:
        parsed = parse_repository_label(remote)
        if parsed:
            return parsed
    return workspace_root.name


def detect_branch_label(values: dict[str, str], workspace_root: Path) -> str:
    explicit = optional(values, "CODEX_BRANCH_LABEL")
    if explicit:
        return explicit
    for args in (
        ("rev-parse", "--abbrev-ref", "HEAD"),
        ("branch", "--show-current"),
    ):
        branch = git_output(workspace_root, *args)
        if branch and branch != "HEAD":
            return branch
    return ""


def slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "codex-bot"


def build_thread_prefix(
    values: dict[str, str],
    repository_label: str,
    branch_label: str,
) -> str:
    explicit = optional(values, "CODEX_THREAD_PREFIX")
    if explicit:
        return explicit
    if branch_label:
        return f"{repository_label}@{branch_label}"
    return repository_label


def combine_thread_name(prefix: str, role_name: str) -> str:
    if not prefix:
        return role_name
    return f"{prefix} · {role_name}"


def build_session_channel(
    *,
    session_id: str,
    role_name: str,
    channel_id: str,
    channel_name: str,
    workspace_root: str,
    workspace_id: str,
    workspace_display_name: str,
    computer_id: str,
    repository_label: str,
    branch_label: str,
    thread_prefix: str,
    now: str,
) -> dict[str, object]:
    return {
        "codexSessionId": session_id,
        "threadName": combine_thread_name(thread_prefix, role_name),
        "roleName": role_name,
        "updatedAt": now,
        "cwd": workspace_root,
        "workspaceRoot": workspace_root,
        "workspaceDisplayName": workspace_display_name,
        "repositoryLabel": repository_label,
        "branchLabel": branch_label,
        "threadPrefix": thread_prefix,
        "discordCategoryId": None,
        "discordChannelId": channel_id,
        "channelName": channel_name,
        "computerId": computer_id,
        "workspaceId": workspace_id,
        "contextPostedAt": now,
        "lastTranscriptMessageKey": None,
        "lastTranscriptSyncedAt": None,
        "lastTranscriptDiscordMessageId": None,
    }


def merge_session_channels(
    existing_channels: list[object],
    desired_channels: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    merged_channels: list[dict[str, object]] = []
    existing_by_channel_id: dict[str, dict[str, object]] = {}

    for item in existing_channels:
        if not isinstance(item, dict):
            continue
        channel_id = str(item.get("discordChannelId") or "")
        if channel_id:
            existing_by_channel_id[channel_id] = item

    changed = 0
    desired_ids = {str(item["discordChannelId"]) for item in desired_channels}

    for desired in desired_channels:
        channel_id = str(desired["discordChannelId"])
        existing = existing_by_channel_id.get(channel_id)
        if existing is None:
            merged_channels.append(desired)
            changed += 1
            continue

        merged = dict(existing)
        merged.update(desired)

        if existing.get("cwd"):
            merged["cwd"] = existing["cwd"]
        for key in (
            "lastTranscriptMessageKey",
            "lastTranscriptSyncedAt",
            "lastTranscriptDiscordMessageId",
        ):
            if key in existing:
                merged[key] = existing[key]

        if merged != existing:
            changed += 1
        merged_channels.append(merged)

    for item in existing_channels:
        if not isinstance(item, dict):
            continue
        channel_id = str(item.get("discordChannelId") or "")
        if channel_id and channel_id in desired_ids:
            continue
        merged_channels.append(item)

    return merged_channels, changed


def main() -> None:
    values = load_env(ENV_PATH)
    token = required(values, "DISCORD_BOT_TOKEN")
    guild_id = snowflake(values, "DISCORD_GUILD_ID")
    admin_channel_id = snowflake(values, "DISCORD_ADMIN_CHANNEL_ID")
    role_ids = [item.strip() for item in required(values, "DISCORD_ALLOWED_ROLE_IDS").split(",") if item.strip()]
    if not role_ids or any(not SNOWFLAKE.fullmatch(item) for item in role_ids):
        raise SystemExit("DISCORD_ALLOWED_ROLE_IDS에는 쉼표로 구분한 Discord 역할 ID만 입력하세요.")

    workspace_root = required(values, "CODEX_WORKSPACE_ROOT")
    codex_home = required(values, "CODEX_HOME")
    timeout_ms = int(values.get("CODEX_TIMEOUT_MS", "900000"))
    workspace_root_path = Path(workspace_root)

    repository_label = detect_repository_label(values, workspace_root_path)
    branch_label = detect_branch_label(values, workspace_root_path)
    thread_prefix = build_thread_prefix(values, repository_label, branch_label)
    workspace_display_name = optional(values, "CODEX_WORKSPACE_DISPLAY_NAME", repository_label)
    instance_slug = optional(values, "CODEX_INSTANCE_SLUG", slugify(workspace_display_name))
    computer_id = optional(values, "CODEX_COMPUTER_ID", f"{instance_slug}-pc")
    computer_display_name = optional(values, "CODEX_COMPUTER_DISPLAY_NAME", f"{workspace_display_name} PC")
    workspace_id = f"{computer_id}:{workspace_root}"
    now = datetime.now(timezone.utc).isoformat()

    mappings = [
        ("QA·PM", "qa", "CODEX_QA_PM_SESSION_ID", "DISCORD_QA_PM_CHANNEL_ID"),
        ("총괄", "전체", "CODEX_LEAD_SESSION_ID", "DISCORD_LEAD_CHANNEL_ID"),
        ("프로그래머", "프로그래밍", "CODEX_PROGRAMMER_SESSION_ID", "DISCORD_PROGRAMMER_CHANNEL_ID"),
        ("기획", "기획", "CODEX_PLANNER_SESSION_ID", "DISCORD_PLANNER_CHANNEL_ID"),
        ("아트", "아트", "CODEX_ART_SESSION_ID", "DISCORD_ART_CHANNEL_ID"),
    ]

    session_channels = []
    for role_name, channel_name, session_key, channel_key in mappings:
        session_channels.append(
            build_session_channel(
                session_id=required(values, session_key),
                role_name=role_name,
                channel_id=snowflake(values, channel_key),
                channel_name=channel_name,
                workspace_root=workspace_root,
                workspace_id=workspace_id,
                workspace_display_name=workspace_display_name,
                computer_id=computer_id,
                repository_label=repository_label,
                branch_label=branch_label,
                thread_prefix=thread_prefix,
                now=now,
            )
        )

    config = {
        "mode": "direct",
        "discord": {
            "token": token,
            "guildId": guild_id,
            "allowedRoleIds": role_ids,
        },
        "direct": {
            "computerId": computer_id,
            "computerDisplayName": computer_display_name,
            "workspaceId": workspace_id,
            "workspaceRoot": workspace_root,
            "initialCwd": workspace_root,
            "workspaceDisplayName": workspace_display_name,
            "repositoryLabel": repository_label,
            "branchLabel": branch_label,
            "threadPrefix": thread_prefix,
            "channelId": admin_channel_id,
            "channelMode": "shell-admin",
            "timeoutMs": timeout_ms,
            "codexHome": codex_home,
        },
    }

    state = {
        "version": 1,
        "transcriptSyncMode": "realtime",
        "archivedCodexSessionIds": [],
        "workspaces": [],
        "sessionChannels": session_channels,
        "scheduledCommands": [],
    }

    CONNECT_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if STATE_PATH.exists():
        existing_state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        existing_channels = existing_state.setdefault("sessionChannels", [])
        merged_channels, changed = merge_session_channels(existing_channels, session_channels)
        existing_state["sessionChannels"] = merged_channels
        STATE_PATH.write_text(
            json.dumps(existing_state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"기존 상태를 보존하면서 역할 채널 {changed}개를 갱신했습니다: {STATE_PATH}")
    else:
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"역할별 채널 매핑을 생성했습니다: {STATE_PATH}")

    print(f"보안 설정을 생성했습니다: {CONFIG_PATH}")
    print(f"저장소 라벨: {repository_label}")
    if branch_label:
        print(f"브랜치 라벨: {branch_label}")
    print("봇 토큰은 출력하지 않았습니다.")


if __name__ == "__main__":
    main()
