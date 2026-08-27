from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "configure-bridge.py"
SPEC = importlib.util.spec_from_file_location("configure_bridge", MODULE_PATH)
assert SPEC and SPEC.loader
configure_bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = configure_bridge
SPEC.loader.exec_module(configure_bridge)


class ConfigureBridgeTests(unittest.TestCase):
    def test_parse_repository_label_from_https_remote(self) -> None:
        value = configure_bridge.parse_repository_label(
            "https://github.com/rupria/rupria_tools_bot_etc.git"
        )
        self.assertEqual(value, "rupria/rupria_tools_bot_etc")

    def test_build_thread_prefix_includes_branch_by_default(self) -> None:
        prefix = configure_bridge.build_thread_prefix(
            {},
            "rupria/rupria_tools_bot_etc",
            "main",
        )
        self.assertEqual(prefix, "rupria/rupria_tools_bot_etc@main")

    def test_merge_session_channels_updates_repository_metadata_and_preserves_cwd(self) -> None:
        existing = [
            {
                "discordChannelId": "123",
                "threadName": "old repo · QA·PM",
                "cwd": "D:\\custom\\cwd",
                "lastTranscriptMessageKey": "keep-me",
            }
        ]
        desired = [
            {
                "discordChannelId": "123",
                "threadName": "new repo@dev · QA·PM",
                "cwd": "C:\\repo",
                "repositoryLabel": "rupria/rupria_tools_bot_etc",
                "branchLabel": "dev",
                "threadPrefix": "new repo@dev",
            }
        ]

        merged, changed = configure_bridge.merge_session_channels(existing, desired)

        self.assertEqual(changed, 1)
        self.assertEqual(merged[0]["cwd"], "D:\\custom\\cwd")
        self.assertEqual(merged[0]["repositoryLabel"], "rupria/rupria_tools_bot_etc")
        self.assertEqual(merged[0]["branchLabel"], "dev")
        self.assertEqual(merged[0]["lastTranscriptMessageKey"], "keep-me")

    def test_detect_repository_label_falls_back_to_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "git_t_bot"
            path.mkdir()
            value = configure_bridge.detect_repository_label({}, path)
        self.assertEqual(value, "git_t_bot")

    def test_detect_branch_label_falls_back_to_show_current_for_unborn_head(self) -> None:
        with mock.patch.object(
            configure_bridge,
            "git_output",
            side_effect=[None, "main"],
        ) as mocked_git_output:
            value = configure_bridge.detect_branch_label({}, Path("C:/repo"))

        self.assertEqual(value, "main")
        self.assertEqual(mocked_git_output.call_count, 2)

    def test_load_env_reads_runtime_environment_without_file(self) -> None:
        missing = Path("C:/missing/.env")
        with mock.patch.object(Path, "exists", return_value=False):
            with mock.patch.dict(
                configure_bridge.os.environ,
                {
                    "DISCORD_BOT_TOKEN": "token",
                    "CODEX_WORKSPACE_ROOT": "C:/repo",
                },
                clear=True,
            ):
                values = configure_bridge.load_env(missing)

        self.assertEqual(values["DISCORD_BOT_TOKEN"], "token")
        self.assertEqual(values["CODEX_WORKSPACE_ROOT"], "C:/repo")


if __name__ == "__main__":
    unittest.main()
