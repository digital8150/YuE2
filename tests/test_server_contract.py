"""Focused HTTP contract tests for the local Studio wrapper."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from yue2_app.repository import Repository
from yue2_app.server import create_app


class FakeComfy:
    def __init__(self) -> None:
        self.prompt = None
        self.transitions: dict[str, dict] = {}

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def system_stats(self):
        return None

    async def upload_audio(self, source, filename, *, content_type=None):
        return {"name": filename, "subfolder": "yue2_uploads", "type": "input"}

    async def queue_prompt(self, prompt, client_id):
        self.prompt = prompt
        return "prompt-new"

    async def queue(self):
        return {"queue_running": [], "queue_pending": []}

    async def inspect_prompt(self, prompt_id):
        return self.transitions.get(prompt_id)


class ServerContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = Repository(Path(self.temp_dir.name) / "test.sqlite3")
        self.comfy = FakeComfy()
        app = create_app(repository=self.repository, comfy_client=self.comfy)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.repository_auth = app["auth"]
        self.repository_auth.create_initial_admin("admin", "관리자", "strong-password-123")
        login = await self.client.post("/api/auth/login", json={"username": "admin", "password": "strong-password-123"})
        self.csrf = (await login.json())["csrf_token"]

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.temp_dir.cleanup()

    async def test_entrypoint_and_static_assets_are_served(self) -> None:
        for path, content_type in (
            ("/", "text/html"),
            ("/static/styles.css", "text/css"),
            ("/static/app.js", "javascript"),
        ):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status, 200)
                self.assertIn(content_type, response.headers.get("Content-Type", ""))
                self.assertTrue(await response.read())

    async def test_health_reports_engine_offline(self) -> None:
        response = await self.client.get("/api/health")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"app": "ok", "engine": "offline"})

    async def test_cover_uses_360_second_default(self) -> None:
        form = FormData()
        form.add_field("mode", "cover")
        form.add_field("style", "warm indie pop")
        form.add_field("audio_file", io.BytesIO(b"test-audio"), filename="reference.wav", content_type="audio/wav")
        response = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(response.status, 202, await response.text())
        music = next(node for node in self.comfy.prompt.values() if node["class_type"] == "YuE2GenerateMusic")
        self.assertEqual(music["inputs"]["max_duration"], 360.0)

    async def test_library_syncs_completed_jobs_before_listing(self) -> None:
        self.repository.create_job(
            job_id="track-1",
            prompt_id="prompt-1",
            mode="original",
            title="테스트 곡",
            style="ambient",
            lyrics="",
            seed=7,
            settings={},
        )
        self.comfy.transitions["prompt-1"] = {
            "status": "completed",
            "output": {"filename": "track.mp3", "subfolder": "yue2", "type": "output"},
        }
        response = await self.client.get("/api/library")
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertEqual([item["id"] for item in payload], ["track-1"])
        self.assertEqual(payload[0]["audio_url"], "/api/tracks/track-1/audio")

    async def test_cancelled_job_stops_showing_as_active(self) -> None:
        self.repository.create_job(
            job_id="cancelled-1", prompt_id="prompt-cancelled", mode="original",
            title="취소한 곡", style="ambient", lyrics="", seed=1, settings={}, status="running",
        )
        self.comfy.transitions["prompt-cancelled"] = {"status": "cancelled"}
        response = await self.client.get("/api/jobs")
        self.assertEqual(response.status, 200)
        job = (await response.json())[0]
        self.assertEqual(job["status"], "cancelled")
        self.assertNotIn("progress", job)
        self.assertEqual(self.repository.list_nonterminal(), [])

    async def test_queue_status_contract(self) -> None:
        self.repository.create_job(
            job_id="active-job-1", prompt_id="prompt-active-1", mode="original",
            title="생성 중인 음악", style="pop", lyrics="Hello", seed=42, settings={}, status="running",
        )
        response = await self.client.get("/api/queue")
        self.assertEqual(response.status, 200)
        data = await response.json()
        self.assertIn("summary", data)
        self.assertIn("running", data)
        self.assertIn("pending", data)
        self.assertEqual(data["summary"]["total_active"], 1)
    async def test_jobs_pagination_contract(self) -> None:
        for idx in range(15):
            self.repository.create_job(
                job_id=f"page-job-{idx:02d}", prompt_id=f"p-{idx}", mode="original",
                title=f"Song {idx}", style="pop", lyrics="", seed=idx, settings={}, status="completed",
                created_at=f"2026-03-{idx + 1:02d}T00:00:00+00:00",
            )
        # Test paged=1
        res = await self.client.get("/api/jobs?limit=5&offset=0&paged=1")
        self.assertEqual(res.status, 200)
        data = await res.json()
        self.assertEqual(len(data["items"]), 5)
        self.assertEqual(data["total"], 15)
        self.assertEqual(data["limit"], 5)
        self.assertEqual(data["offset"], 0)
        self.assertTrue(data["has_more"])

        # Test next page
        res2 = await self.client.get("/api/jobs?limit=5&offset=10&paged=1")
        self.assertEqual(res2.status, 200)
        data2 = await res2.json()
        self.assertEqual(len(data2["items"]), 5)
        self.assertFalse(data2["has_more"])

        # Test unpaged with headers
        res3 = await self.client.get("/api/jobs?limit=5&offset=0")
        self.assertEqual(res3.status, 200)
        items = await res3.json()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 5)
        self.assertEqual(res3.headers.get("X-Total-Count"), "15")
        self.assertEqual(res3.headers.get("X-Has-More"), "true")


if __name__ == "__main__":
    unittest.main()
