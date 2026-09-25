from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
bot_main = importlib.import_module("main")


GUILD_ID = "12345678901234567"


def signature_for(payload: bytes, repository: str) -> str:
    secret = bot_main.derive_repository_secret("master-secret", repository, GUILD_ID)
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


class WebhookHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.original_settings = bot_main.settings
        self.original_runtime_state = bot_main.runtime_state
        self.original_queue = bot_main.webhook_queue
        self.temp_dir = tempfile.TemporaryDirectory()
        bot_main.settings = replace(
            bot_main.settings,
            webhook_master_secret="master-secret",
            state_file=Path(self.temp_dir.name) / "runtime-state.json",
        )
        bot_main.runtime_state = {"version": 2, "branches": {}, "webhooks": {}, "deliveries": {}}
        bot_main.webhook_queue = asyncio.Queue(maxsize=10)
        bot_main.queued_delivery_ids.clear()

        app = web.Application()
        app.router.add_post("/webhooks/github/{guild_id}", bot_main.github_webhook_handler)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        bot_main.settings = self.original_settings
        bot_main.runtime_state = self.original_runtime_state
        bot_main.webhook_queue = self.original_queue
        bot_main.queued_delivery_ids.clear()
        self.temp_dir.cleanup()

    async def test_ping_verifies_signature_and_records_connection(self) -> None:
        payload = json.dumps({"repository": {"full_name": "rupria/gitproject"}}).encode("utf-8")
        response = await self.client.post(
            f"/webhooks/github/{GUILD_ID}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "delivery-ping",
                "X-Hub-Signature-256": signature_for(payload, "rupria/gitproject"),
            },
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(
            bot_main.runtime_state["webhooks"][f"{GUILD_ID}:rupria/gitproject"]["last_status"],
            "connected",
        )

    async def test_invalid_signature_is_rejected(self) -> None:
        payload = json.dumps({"repository": {"full_name": "rupria/gitproject"}}).encode("utf-8")
        response = await self.client.post(
            f"/webhooks/github/{GUILD_ID}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "delivery-invalid",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
        self.assertEqual(response.status, 401)


if __name__ == "__main__":
    unittest.main()
