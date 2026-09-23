"""Authenticated, incremental generation updates over the Studio WebSocket."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from aiohttp import WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer

from yue2_app.repository import Repository
from yue2_app.server import _on_comfy_event, create_app


class FakeComfy:
    def __init__(self) -> None:
        self.progress = {}
        self.transitions = {}

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def queue_prompt(self, prompt, client_id):
        return "prompt-realtime"

    async def inspect_prompt(self, prompt_id):
        return self.transitions.get(prompt_id)

    async def queue(self):
        return {"queue_running": [[0, "prompt-realtime"]], "queue_pending": []}

    async def system_stats(self):
        return None

    def progress_for(self, prompt_id):
        return self.progress.get(prompt_id)


class RealtimeEventTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.repository = Repository(Path(self.directory.name) / "test.sqlite3")
        self.comfy = FakeComfy()
        self.app = create_app(repository=self.repository, comfy_client=self.comfy)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.app["auth"].create_initial_admin("admin", "Admin", "strong-password-123")

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.directory.cleanup()

    async def login(self) -> str:
        response = await self.client.post(
            "/api/auth/login", json={"username": "admin", "password": "strong-password-123"}
        )
        return (await response.json())["csrf_token"]

    async def test_websocket_requires_session_and_rejects_foreign_origin(self) -> None:
        with self.assertRaises(WSServerHandshakeError) as error:
            await self.client.ws_connect("/api/events")
        self.assertEqual(error.exception.status, 401)

        await self.login()
        with self.assertRaises(WSServerHandshakeError) as error:
            await self.client.ws_connect("/api/events", headers={"Origin": "https://evil.example"})
        self.assertEqual(error.exception.status, 403)
        with self.assertRaises(WSServerHandshakeError) as error:
            await self.client.ws_connect("/api/events", headers={"Origin": "http://localhost:9999"})
        self.assertEqual(error.exception.status, 403)

    async def test_job_lifecycle_and_latest_progress_are_pushed(self) -> None:
        csrf = await self.login()
        async with self.client.ws_connect("/api/events") as socket:
            created = await self.client.post(
                "/api/generations",
                data={"mode": "original", "title": "Live song", "style": "ambient"},
                headers={"X-Yue2-CSRF": csrf},
            )
            self.assertEqual(created.status, 202)
            job_id = (await created.json())["id"]
            event = await asyncio.wait_for(socket.receive_json(), timeout=2)
            self.assertEqual((event["type"], event["job"]["id"]), ("job", job_id))

            _on_comfy_event(self.app, {
                "type": "executing", "data": {"prompt_id": "prompt-realtime", "node": "4"},
            })
            event = await asyncio.wait_for(socket.receive_json(), timeout=2)
            self.assertEqual(event["job"]["status"], "running")

            for current in range(20):
                self.comfy.progress["prompt-realtime"] = {
                    "phase": "music", "current": current, "total": 100, "rate": 10.0,
                }
                _on_comfy_event(self.app, {
                    "type": "progress", "data": {"prompt_id": "prompt-realtime"},
                })
            event = await asyncio.wait_for(socket.receive_json(), timeout=2)
            self.assertEqual(event, {
                "type": "progress",
                "updates": {job_id: {"phase": "music", "current": 19, "total": 100, "rate": 10.0}},
            })

            self.comfy.transitions["prompt-realtime"] = {
                "status": "completed",
                "output": {"filename": "song.mp3", "subfolder": "yue2", "type": "output"},
            }
            response = await self.client.get(f"/api/jobs/{job_id}")
            self.assertEqual(response.status, 200)
            event = await asyncio.wait_for(socket.receive_json(), timeout=2)
            self.assertEqual(event["job"]["status"], "completed")
            self.assertEqual(event["job"]["audio_url"], f"/api/tracks/{job_id}/audio")
