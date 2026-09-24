"""A worker can claim, complete, and serve a generated track over HTTP."""

import os
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from yue2_app.repository import Repository
from yue2_app.server import create_app


class MemoryDispatch:
    def __init__(self):
        self.jobs = {}

    def enqueue(self, job_id, payload):
        self.jobs[job_id] = {"payload": payload, "status": "queued"}

    def claim(self, worker_id, device="", vram=""):
        for job_id, job in self.jobs.items():
            if job["status"] == "queued":
                job.update(status="running", worker_id=worker_id, token="lease")
                return {"job_id": job_id, "payload": job["payload"], "attempts": 1, "lease_token": "lease"}
        return None

    def heartbeat(self, job_id, worker_id, token, progress=None):
        job = self.jobs.get(job_id)
        return bool(job and job["status"] == "running" and job["worker_id"] == worker_id and job["token"] == token)

    def finish(self, job_id, worker_id, token, status, output_filename=None):
        if not self.heartbeat(job_id, worker_id, token):
            return False
        self.jobs[job_id]["status"] = status
        self.jobs[job_id]["output_filename"] = output_filename
        return True

    def workers(self):
        return [{"device": "test GPU", "vram": "12GB"}]

    def expired(self):
        return []

    def terminal(self):
        return [(key, value["status"], value.get("output_filename")) for key, value in self.jobs.items()
                if value["status"] in {"completed", "failed"}]


class DistributedFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_instrumental_payload_is_normalized_for_worker(self):
        form = FormData()
        for key, value in {"mode": "original", "style": "ambient", "lyrics": "",
                           "instrumental": "true", "planning_enabled": "false"}.items():
            form.add_field(key, value)
        created = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(created.status, 202, await created.text())
        job = self.dispatch.jobs[(await created.json())["id"]]["payload"]
        self.assertEqual(job["lyrics"], "[instrumental]")
        self.assertEqual(job["style"], "Instrumental, ambient")
        self.assertTrue(job["instrumental"])
        self.assertTrue(job["settings"]["planning_enabled"] is False)
        bad = FormData()
        for key, value in {"mode": "original", "style": "ambient", "lyrics": "sing this",
                           "instrumental": "true"}.items():
            bad.add_field(key, value)
        rejected = await self.client.post("/api/generations", data=bad, headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(rejected.status, 400)

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        repo = Repository(Path(self.temp.name) / "studio.sqlite3")
        self.dispatch = MemoryDispatch()
        with patch.dict(os.environ, {"YUE2_WORKER_TOKENS": '{"test-worker":"secret"}'}):
            app = create_app(repository=repo, dispatch_store=self.dispatch)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        app["auth"].create_initial_admin("admin", "Admin", "strong-password-123")
        login = await self.client.post("/api/auth/login", json={"username": "admin", "password": "strong-password-123"})
        self.csrf = (await login.json())["csrf_token"]
        self.worker_headers = {"Authorization": "Bearer secret", "X-Yue-Worker": "test-worker"}

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def test_claim_upload_and_seek(self):
        form = FormData()
        for key, value in {"mode": "original", "style": "ambient", "lyrics": "hello",
                           "duration": "0.04", "planning_enabled": "false"}.items():
            form.add_field(key, value)
        created = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(created.status, 202, await created.text())
        job_id = (await created.json())["id"]
        denied = await self.client.post("/api/worker/claim", json={})
        self.assertEqual(denied.status, 401)
        claimed = await self.client.post("/api/worker/claim", json={"device": "test GPU"}, headers=self.worker_headers)
        self.assertEqual(claimed.status, 200)
        job = (await claimed.json())["job"]
        self.assertEqual(job["job_id"], job_id)
        self.assertEqual(job["payload"]["lyrics"], "hello")
        audio = b"ID3" + bytes(range(256)) * 8
        completed = await self.client.post(
            f"/api/worker/jobs/{job_id}/complete", data=audio,
            headers={**self.worker_headers, "X-Yue-Lease": "lease", "Content-Type": "audio/mpeg"},
        )
        self.assertEqual(completed.status, 200, await completed.text())
        response = await self.client.get(f"/api/tracks/{job_id}/audio", headers={"Range": "bytes=3-6"})
        self.assertEqual(response.status, 206)
        self.assertEqual(await response.read(), audio[3:7])

    async def test_cover_source_transfer_and_cleanup(self):
        form = FormData()
        form.add_field("mode", "cover")
        form.add_field("style", "ambient")
        form.add_field("audio_file", io.BytesIO(b"reference-audio"), filename="reference.mp3", content_type="audio/mpeg")
        created = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(created.status, 202, await created.text())
        job_id = (await created.json())["id"]
        claimed = await self.client.post("/api/worker/claim", json={}, headers=self.worker_headers)
        job = (await claimed.json())["job"]
        source = await self.client.get(job["source_url"], headers={**self.worker_headers, "X-Yue-Lease": "lease"})
        self.assertEqual(source.status, 200)
        self.assertEqual(await source.read(), b"reference-audio")
        failed = await self.client.post(f"/api/worker/jobs/{job_id}/fail",
                                        json={"lease_token": "lease"}, headers=self.worker_headers)
        self.assertEqual(failed.status, 200)
        self.assertFalse(list((Path(self.temp.name) / "sources").iterdir()))


if __name__ == "__main__":
    unittest.main()
