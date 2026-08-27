from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

if os.name == "nt":
    import msvcrt


POLL_SECONDS = 1.0
GITHUB_URL_PATTERN = re.compile(r"https://github\.com/[^\s<>()\[\]\"']+")


@dataclass(frozen=True)
class SessionMapping:
    session_id: str
    thread_name: str
    discord_channel_id: str
    repository_label: str
    branch_label: str


@dataclass(frozen=True)
class Completion:
    session_id: str
    thread_name: str
    discord_channel_id: str
    repository_label: str
    branch_label: str
    completed_at: datetime
    elapsed_seconds: float | None
    git_links: tuple[str, ...] = ()


def read_json(
    path: Path,
    *,
    retries: int = 5,
    delay_seconds: float = 0.1,
) -> dict[str, Any]:
    last_error: json.JSONDecodeError | OSError | None = None
    for attempt in range(retries):
        try:
            raw_text = path.read_text(encoding="utf-8").strip()
            if not raw_text:
                raise json.JSONDecodeError("empty JSON document", "", 0)
            return json.loads(raw_text)
        except (json.JSONDecodeError, OSError) as exc:
            last_error = exc
            if attempt == retries - 1:
                raise
            time.sleep(delay_seconds)
    assert last_error is not None
    raise last_error


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_elapsed(seconds: float | None) -> str:
    if seconds is None:
        return "측정되지 않음"
    rounded = max(0, int(round(seconds)))
    minutes, remaining = divmod(rounded, 60)
    if minutes:
        return f"{minutes}분 {remaining}초"
    return f"{remaining}초"


def completion_message(completion: Completion) -> str:
    discord_timestamp = int(completion.completed_at.timestamp())
    lines = [
        "✅ **Codex 작업 완료**",
        f"저장소: {completion.repository_label}",
        f"담당: {completion.thread_name}",
        f"요청 채널: <#{completion.discord_channel_id}>",
        f"소요 시간: {format_elapsed(completion.elapsed_seconds)}",
        f"완료 시각: <t:{discord_timestamp}:T>",
    ]
    if completion.branch_label:
        lines.insert(2, f"브랜치: {completion.branch_label}")
    for index, link in enumerate(completion.git_links, start=1):
        label = "Git 링크" if len(completion.git_links) == 1 else f"Git 링크 {index}"
        lines.append(f"{label}: <{link}>")
    return "\n".join(lines)


def extract_github_links(message: str) -> tuple[str, ...]:
    links: list[str] = []
    for match in GITHUB_URL_PATTERN.findall(message):
        link = match.rstrip(".,;:!?`")
        if link not in links:
            links.append(link)
        if len(links) == 3:
            break
    return tuple(links)


def load_mappings(state_path: Path) -> dict[str, SessionMapping]:
    state = read_json(state_path)
    mappings: dict[str, SessionMapping] = {}
    for channel in state.get("sessionChannels", []):
        session_id = channel.get("codexSessionId")
        discord_channel_id = channel.get("discordChannelId")
        if not isinstance(session_id, str) or not isinstance(discord_channel_id, str):
            continue
        repository_label = str(
            channel.get("repositoryLabel")
            or channel.get("workspaceDisplayName")
            or Path(str(channel.get("workspaceRoot") or "")).name
            or "unknown-repository"
        )
        branch_label = str(channel.get("branchLabel") or "")
        mappings[session_id] = SessionMapping(
            session_id=session_id,
            thread_name=str(channel.get("threadName") or session_id),
            discord_channel_id=discord_channel_id,
            repository_label=repository_label,
            branch_label=branch_label,
        )
    return mappings


def find_rollouts(codex_home: Path, session_ids: set[str]) -> dict[str, Path]:
    session_root = codex_home / "sessions"
    found: dict[str, Path] = {}
    if not session_root.exists():
        return found
    for session_id in session_ids:
        candidates = list(session_root.rglob(f"*{session_id}*.jsonl"))
        if candidates:
            found[session_id] = max(candidates, key=lambda item: item.stat().st_mtime_ns)
    return found


def read_complete_lines(path: Path, offset: int) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    with path.open("rb") as stream:
        stream.seek(offset)
        position = offset
        for raw_line in stream:
            if not raw_line.endswith(b"\n"):
                break
            position += len(raw_line)
            try:
                events.append(json.loads(raw_line.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
    return events, position


def collect_completions(
    session_id: str,
    mapping: SessionMapping,
    events: list[dict[str, Any]],
    active_turns: dict[str, datetime],
    active_git_links: dict[str, tuple[str, ...]],
) -> list[Completion]:
    completions: list[Completion] = []
    for event in events:
        if event.get("type") != "event_msg":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        event_type = payload.get("type")
        timestamp_text = event.get("timestamp")
        if not isinstance(timestamp_text, str):
            continue
        timestamp = parse_timestamp(timestamp_text)
        if event_type == "task_started":
            active_turns[session_id] = timestamp
            active_git_links.pop(session_id, None)
        elif event_type == "agent_message" and payload.get("phase") == "final_answer":
            message = payload.get("message")
            if isinstance(message, str):
                active_git_links[session_id] = extract_github_links(message)
        elif event_type == "task_complete":
            started_at = active_turns.pop(session_id, None)
            elapsed = (timestamp - started_at).total_seconds() if started_at else None
            completions.append(
                Completion(
                    session_id=session_id,
                    thread_name=mapping.thread_name,
                    discord_channel_id=mapping.discord_channel_id,
                    repository_label=mapping.repository_label,
                    branch_label=mapping.branch_label,
                    completed_at=timestamp,
                    elapsed_seconds=elapsed,
                    git_links=active_git_links.pop(session_id, ()),
                )
            )
    return completions


def send_discord_message(token: str, channel_id: str, content: str) -> None:
    request = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=json.dumps(
            {
                "content": content,
                "allowed_mentions": {"parse": []},
            }
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "codex-discord-completion-alert/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status not in (200, 201):
            raise RuntimeError(f"Discord returned HTTP {response.status}")


def acquire_singleton(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+b")
    if os.name != "nt":
        return lock_file
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"1")
        lock_file.flush()
    lock_file.seek(0)
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        raise SystemExit("completion alert monitor is already running")
    return lock_file


def parse_routes(values: list[str]) -> dict[str, str]:
    routes: dict[str, str] = {}
    for value in values:
        source_channel_id, separator, destination_channel_id = value.partition(":")
        if not separator or not source_channel_id or not destination_channel_id:
            raise ValueError(f"invalid route: {value}")
        routes[source_channel_id] = destination_channel_id
    return routes


def monitor(project_root: Path, alert_routes: dict[str, str]) -> None:
    connect_dir = project_root / ".connect"
    config_path = connect_dir / "config.json"
    state_path = connect_dir / "state.json"
    offsets_path = connect_dir / "completion-alert-offsets.json"
    singleton = acquire_singleton(connect_dir / "completion-alert.lock")

    config = read_json(config_path)
    token = str(config["discord"]["token"])
    codex_home = Path(config["direct"]["codexHome"])
    offsets_data = read_json(offsets_path) if offsets_path.exists() else {"version": 1, "offsets": {}}
    offsets: dict[str, int] = {
        str(key): int(value) for key, value in offsets_data.get("offsets", {}).items()
    }
    active_turns: dict[str, datetime] = {}
    active_git_links: dict[str, tuple[str, ...]] = {}
    initialized_paths: set[str] = set(offsets)

    route_summary = ", ".join(
        f"{source}->{destination}"
        for source, destination in alert_routes.items()
    )
    print(f"Completion alert monitor ready for routes {route_summary}", flush=True)
    try:
        while True:
            mappings = load_mappings(state_path)
            rollouts = find_rollouts(codex_home, set(mappings))
            offsets_changed = False

            for session_id, rollout_path in rollouts.items():
                path_key = str(rollout_path)
                if path_key not in initialized_paths:
                    offsets[path_key] = rollout_path.stat().st_size
                    initialized_paths.add(path_key)
                    offsets_changed = True
                    continue

                current_offset = offsets.get(path_key, 0)
                events, next_offset = read_complete_lines(rollout_path, current_offset)
                if next_offset != current_offset:
                    offsets[path_key] = next_offset
                    offsets_changed = True

                for completion in collect_completions(
                    session_id,
                    mappings[session_id],
                    events,
                    active_turns,
                    active_git_links,
                ):
                    alert_channel_id = alert_routes.get(completion.discord_channel_id)
                    if alert_channel_id:
                        send_discord_message(
                            token,
                            alert_channel_id,
                            completion_message(completion),
                        )
                        print(
                            f"Completion alert sent for {completion.session_id} "
                            f"to {alert_channel_id} "
                            f"({format_elapsed(completion.elapsed_seconds)})",
                            flush=True,
                        )

            if offsets_changed:
                write_json_atomic(offsets_path, {"version": 1, "offsets": offsets})
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        pass
    except urllib.error.HTTPError as error:
        print(f"Discord completion alert failed: HTTP {error.code}", file=sys.stderr, flush=True)
        raise
    finally:
        singleton.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Discord alerts for completed Codex tasks")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument(
        "--route",
        action="append",
        required=True,
        metavar="SOURCE_CHANNEL_ID:DESTINATION_CHANNEL_ID",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    monitor(arguments.project_root.resolve(), parse_routes(arguments.route))
