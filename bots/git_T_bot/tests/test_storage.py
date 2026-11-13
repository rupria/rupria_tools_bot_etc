from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from git_t_bot.storage import read_json_file, write_json_file


class StorageTests(unittest.TestCase):
    def test_write_keeps_previous_valid_copy_as_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "watchers.json"
            write_json_file(path, {"version": 1})
            write_json_file(path, {"version": 2})

            self.assertEqual(read_json_file(path, {}), {"version": 2})
            self.assertEqual(read_json_file(path.with_suffix(".json.bak"), {}), {"version": 1})
            self.assertFalse(path.with_name(".watchers.json.tmp").exists())

    def test_read_recovers_from_backup_when_primary_is_corrupt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime-state.json"
            write_json_file(path, {"version": 1, "branches": {}})
            write_json_file(path, {"version": 2, "branches": {"main": {}}})
            path.write_text("{broken", encoding="utf-8")

            self.assertEqual(read_json_file(path, {}), {"version": 1, "branches": {}})

    def test_read_returns_fallback_when_both_files_are_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "watchers.json"
            path.write_text("", encoding="utf-8")
            path.with_suffix(".json.bak").write_text("nope", encoding="utf-8")

            self.assertEqual(read_json_file(path, {"watches": []}), {"watches": []})


if __name__ == "__main__":
    unittest.main()
