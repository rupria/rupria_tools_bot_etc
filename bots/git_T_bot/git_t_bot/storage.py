from __future__ import annotations

import json
from pathlib import Path

from .config import WatchTarget


def ensure_data_dir(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)


def read_json_file(file_path: Path, fallback):
    if not file_path.exists():
        return fallback
    raw = file_path.read_text(encoding="utf-8").strip()
    if not raw:
        return fallback
    return json.loads(raw)


def write_json_file(file_path: Path, value) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
                }
                for watch in watches
            ],
        },
    )


def load_runtime_state(file_path: Path) -> dict:
    data = read_json_file(file_path, {"version": 1, "branches": {}})
    branches = data.get("branches", {})
    if not isinstance(branches, dict):
        branches = {}
    return {"version": 1, "branches": branches}


def save_runtime_state(file_path: Path, state: dict) -> None:
    write_json_file(file_path, state)
