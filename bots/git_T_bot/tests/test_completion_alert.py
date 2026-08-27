from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "completion_alert.py"
SPEC = importlib.util.spec_from_file_location("completion_alert", MODULE_PATH)
assert SPEC and SPEC.loader
completion_alert = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = completion_alert
SPEC.loader.exec_module(completion_alert)


class CompletionAlertTests(unittest.TestCase):
    def test_read_complete_lines_ignores_partial_json(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            rollout = Path(directory) / "rollout.jsonl"
            complete = json.dumps({"type": "event_msg", "payload": {"type": "task_started"}})
            rollout.write_bytes((complete + "\n" + '{"type":').encode("utf-8"))

            events, offset = completion_alert.read_complete_lines(rollout, 0)

            self.assertEqual(len(events), 1)
            self.assertEqual(offset, len((complete + "\n").encode("utf-8")))

    def test_collects_completion_and_elapsed_time(self) -> None:
        mapping = completion_alert.SessionMapping(
            "session-1",
            "기획",
            "123456789012345678",
            "rupria/rupria_tools_bot_etc",
            "main",
        )
        events = [
            {
                "timestamp": "2026-08-07T01:00:00Z",
                "type": "event_msg",
                "payload": {"type": "task_started"},
            },
            {
                "timestamp": "2026-08-07T01:01:05Z",
                "type": "event_msg",
                "payload": {"type": "task_complete"},
            },
        ]

        results = completion_alert.collect_completions("session-1", mapping, events, {}, {})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].elapsed_seconds, 65)
        self.assertIn("1분 5초", completion_alert.completion_message(results[0]))
        self.assertIn("<#123456789012345678>", completion_alert.completion_message(results[0]))
        self.assertIn("저장소: rupria/rupria_tools_bot_etc", completion_alert.completion_message(results[0]))
        self.assertIn("브랜치: main", completion_alert.completion_message(results[0]))

    def test_formats_unknown_duration(self) -> None:
        completion = completion_alert.Completion(
            session_id="session-1",
            thread_name="QA·PM",
            discord_channel_id="123456789012345678",
            repository_label="rupria/rupria_tools_bot_etc",
            branch_label="",
            completed_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
            elapsed_seconds=None,
        )

        self.assertIn("측정되지 않음", completion_alert.completion_message(completion))

    def test_includes_github_links_from_final_answer(self) -> None:
        mapping = completion_alert.SessionMapping(
            "session-1",
            "아트",
            "123456789012345678",
            "rupria/rupria_tools_bot_etc",
            "feature/git-t-bot",
        )
        events = [
            {
                "timestamp": "2026-08-07T01:00:00Z",
                "type": "event_msg",
                "payload": {"type": "task_started"},
            },
            {
                "timestamp": "2026-08-07T01:02:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "완료: https://github.com/example/project/pull/12",
                },
            },
            {
                "timestamp": "2026-08-07T01:02:01Z",
                "type": "event_msg",
                "payload": {"type": "task_complete"},
            },
        ]

        results = completion_alert.collect_completions("session-1", mapping, events, {}, {})

        self.assertEqual(results[0].git_links, ("https://github.com/example/project/pull/12",))
        self.assertIn("Git 링크: <https://github.com/example/project/pull/12>", completion_alert.completion_message(results[0]))

    def test_parses_channel_specific_routes(self) -> None:
        routes = completion_alert.parse_routes(
            ["11111111111111111:22222222222222222", "33333333333333333:44444444444444444"]
        )

        self.assertEqual(routes["11111111111111111"], "22222222222222222")
        self.assertEqual(routes["33333333333333333"], "44444444444444444")

    def test_read_json_retries_when_state_file_is_temporarily_empty(self) -> None:
        path = Path("ignored.json")
        with patch.object(
            Path,
            "read_text",
            side_effect=["", "", '{"sessionChannels": []}'],
        ):
            with patch.object(completion_alert.time, "sleep", return_value=None):
                result = completion_alert.read_json(path)

        self.assertEqual(result, {"sessionChannels": []})

    def test_load_mappings_reads_repository_and_branch_labels(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "sessionChannels": [
                            {
                                "codexSessionId": "session-1",
                                "threadName": "repo@dev · 프로그래머",
                                "discordChannelId": "123456789012345678",
                                "repositoryLabel": "rupria/rupria_tools_bot_etc",
                                "branchLabel": "dev",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            mappings = completion_alert.load_mappings(state_path)

        self.assertEqual(mappings["session-1"].repository_label, "rupria/rupria_tools_bot_etc")
        self.assertEqual(mappings["session-1"].branch_label, "dev")


if __name__ == "__main__":
    unittest.main()
