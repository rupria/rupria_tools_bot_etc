from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil

from .config import WatchTarget


logger = logging.getLogger("git_t_bot.storage")


def ensure_data_dir(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)


def parse_json_file(file_path: Path):
    raw = file_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise json.JSONDecodeError("empty JSON file", raw, 0)
    return json.loads(raw)


def read_json_file(file_path: Path, fallback):
    backup_path = file_path.with_suffix(f"{file_path.suffix}.bak")
    for candidate in (file_path, backup_path):
        if not candidate.exists():
            continue
        try:
            return parse_json_file(candidate)
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("failed to read %s: %s", candidate, error)
    return fallback


def write_json_file(file_path: Path, value) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = file_path.with_suffix(f"{file_path.suffix}.bak")
    temp_path = file_path.with_name(f".{file_path.name}.tmp")
    serialized = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        if file_path.exists():
            try:
                parse_json_file(file_path)
            except (OSError, json.JSONDecodeError):
                logger.warning("skipped backup of invalid JSON file %s", file_path)
            else:
                shutil.copy2(file_path, backup_path)
        os.replace(temp_path, file_path)
    finally:
        temp_path.unlink(missing_ok=True)


def load_persisted_watches(file_path: Path) -> list[WatchTarget]:
    data = read_json_file(file_path, {"version": 1, "watches": []})
    return [WatchTarget(**item).normalized() for item in data.get("watches", [])]


def save_persisted_watches(file_path: Path, watches: list[WatchTarget]) -> None:
    write_json_file(
        file_path,
        {
            "version": 1,
            "watches": [
                {
                    "repository": watch.repository,
                    "branch": watch.branch,
                    "channel_id": watch.channel_id,
                    "source": watch.source,
                    "user": watch.user,
                }
                for watch in watches
            ],
        },
    )


def load_runtime_state(file_path: Path) -> dict:
    data = read_json_file(file_path, {"version": 1, "branches": {}, "deliveries": []})
    branches = data.get("branches", {})
    if not isinstance(branches, dict):
        branches = {}
    deliveries = data.get("deliveries", [])
    if not isinstance(deliveries, list):
        deliveries = []
    return {"version": 1, "branches": branches, "deliveries": deliveries[-100:]}


def save_runtime_state(file_path: Path, state: dict) -> None:
    write_json_file(file_path, state)
