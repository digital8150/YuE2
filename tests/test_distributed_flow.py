"""A worker can claim, complete, and serve a generated track over HTTP."""

import os
import io
import tempfile
import secrets
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
        self.records = {}
        self.connected = {}

    def enqueue(self, job_id, payload):
        self.jobs[job_id] = {"payload": payload, "status": "queued"}

    def claim(self, worker_id, device="", vram=""):
        self.connected[worker_id] = {"worker_id": worker_id, "name": self.records.get(worker_id, {}).get("name", worker_id),
                                     "device": device, "vram": vram, "status": "idle", "progress": None}
        for job_id, job in self.jobs.items():
            if job["status"] == "queued" or (job["status"] == "running" and job.get("stale") and job.get("attempts", 0) < 3):
                attempts = job.get("attempts", 0) + 1
                job.update(status="running", worker_id=worker_id, token="lease", attempts=attempts, stale=False)
                self.connected[worker_id]["status"] = "busy"
                return {"job_id": job_id, "payload": job["payload"], "attempts": attempts, "lease_token": "lease"}
        return None

    def heartbeat(self, job_id, worker_id, token, progress=None):
        job = self.jobs.get(job_id)
        valid = bool(job and job["status"] == "running" and job["worker_id"] == worker_id and job["token"] == token)
        if valid and worker_id in self.connected:
            self.connected[worker_id]["progress"] = progress
            if progress is not None:
                job["progress"] = progress
        return valid

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if job and job["status"] == "queued":
            job["status"] = "cancelled"
            return True
        return False

    def requeue(self, job_id, worker_id, token):
        if not self.heartbeat(job_id, worker_id, token):
            return False, "invalid"
        job = self.jobs[job_id]
        attempts = job.get("attempts", 1)
        if worker_id in self.connected:
            self.connected[worker_id].update(status="idle", progress=None)
        if attempts < 3:
            job.update(status="queued", worker_id=None, token=None, progress=None)
            return True, "requeued"
        else:
            job.update(status="failed", worker_id=None, token=None, progress=None)
            return True, "failed"

    def requeue_stale(self):
        requeued = []
        for job_id, job in self.jobs.items():
            if job.get("status") == "running" and job.get("stale") and job.get("attempts", 1) < 3:
                worker_id = job.get("worker_id")
                if worker_id and worker_id in self.connected:
                    self.connected[worker_id].update(status="idle", progress=None)
                job.update(status="queued", worker_id=None, token=None, progress=None, stale=False)
                requeued.append(job_id)
        return requeued

    def finish(self, job_id, worker_id, token, status, output_filename=None):
        if not self.heartbeat(job_id, worker_id, token):
            return False
        self.jobs[job_id]["status"] = status
        self.jobs[job_id]["output_filename"] = output_filename
        if worker_id in self.connected:
            self.connected[worker_id].update(status="idle", progress=None)
        return True

    def status(self, job_id):
        job = self.jobs.get(job_id)
        return (job["status"], job.get("worker_id")) if job else None

    def workers(self):
        return list(self.connected.values())

    def progress_for_jobs(self, job_ids):
        return {job_id: self.jobs[job_id]["progress"] for job_id in job_ids
                if job_id in self.jobs and self.jobs[job_id]["status"] == "running"
                and self.jobs[job_id].get("progress")}

    def create_credential(self, owner_id, name):
        worker_id = "gpu-" + secrets.token_hex(12)
        token = secrets.token_urlsafe(32)
        self.records[worker_id] = {"owner_id": owner_id, "name": name, "token": token}
        return {"worker_id": worker_id, "name": name, "token": token}

    def authenticate(self, worker_id, token):
        record = self.records.get(worker_id)
        return bool(record and record["token"] == token)

    def credentials(self, owner_id):
        return [{"worker_id": key, "name": value["name"]} for key, value in self.records.items()
                if value["owner_id"] == owner_id]

    def revoke_credential(self, owner_id, worker_id):
        record = self.records.get(worker_id)
        if not record or record["owner_id"] != owner_id:
            return False
        del self.records[worker_id]
        self.connected.pop(worker_id, None)
        return True

    def expired(self):
        failed = []
        for job_id, job in self.jobs.items():
            if job.get("status") == "running" and job.get("stale") and job.get("attempts", 1) >= 3:
                worker_id = job.get("worker_id")
                if worker_id and worker_id in self.connected:
                    self.connected[worker_id].update(status="idle", progress=None)
                job.update(status="failed", worker_id=None, token=None, progress=None, stale=False)
                failed.append(job_id)
        return failed

    def terminal(self):
        return [(key, value["status"], value.get("output_filename")) for key, value in self.jobs.items()
                if value["status"] in {"completed", "failed", "cancelled"}]


class DistributedFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_numbered_instrumental_sections_are_accepted(self):
        form = FormData()
        form.add_field("mode", "original")
        form.add_field("style", "EDM, 128 BPM, Korean traditional instruments")
        form.add_field("instrumental", "true")
        form.add_field("duration", "150")
        form.add_field("lyrics", "[Intro 0:00-0:05]\n[Verse 0:05-0:30]\n[Chorus 0:30-1:00]\n"
                       "[Verse 1 1:00-1:25]\n[Chorus 1 1:25-1:50]\n[Outro 1:50-2:00]")
        created = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(created.status, 202, await created.text())
        job = self.dispatch.jobs[(await created.json())["id"]]["payload"]
        self.assertIn("[verse 1:00-1:25]", job["lyrics"])
        self.assertNotIn("[verse 1 ", job["lyrics"])

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

    async def test_member_can_register_monitor_and_revoke_own_worker(self):
        auth = self.client.server.app["auth"]
        auth.create_user("member1", "Member", "strong-password-123", status="approved")
        login = await self.client.post("/api/auth/login", json={"username": "member1", "password": "strong-password-123"})
        member_csrf = (await login.json())["csrf_token"]
        denied = await self.client.post("/api/my/workers", json={"name": "My GPU"})
        self.assertEqual(denied.status, 403)
        created = await self.client.post("/api/my/workers", json={"name": "My GPU"},
                                         headers={"X-Yue2-CSRF": member_csrf})
        self.assertEqual(created.status, 201, await created.text())
        self.assertEqual(created.headers.get("Cache-Control"), "no-store")
        credential = await created.json()
        headers = {"Authorization": "Bearer " + credential["token"], "X-Yue-Worker": credential["worker_id"]}
        listed = await self.client.get("/api/my/workers")
        self.assertEqual((await listed.json())["workers"], [{"worker_id": credential["worker_id"],
                                                             "name": "My GPU", "connection": "offline"}])
        connected = await self.client.post("/api/worker/claim", json={"device": "RTX", "vram": "12GB"}, headers=headers)
        self.assertEqual(connected.status, 200)
        queue = await self.client.get("/api/queue")
        worker = (await queue.json())["workers"][0]
        self.assertEqual((worker["name"], worker["status"]), ("My GPU", "idle"))

        form = FormData()
        form.add_field("mode", "original")
        form.add_field("style", "ambient")
        form.add_field("lyrics", "hello")
        form.add_field("planning_enabled", "false")
        created_job = await self.client.post("/api/generations", data=form,
                                             headers={"X-Yue2-CSRF": member_csrf})
        self.assertEqual(created_job.status, 202, await created_job.text())
        job_id = (await created_job.json())["id"]
        claimed = await self.client.post("/api/worker/claim", json={"device": "RTX", "vram": "12GB"}, headers=headers)
        self.assertEqual((await claimed.json())["job"]["job_id"], job_id)
        heartbeat = await self.client.post("/api/worker/heartbeat", json={
            "job_id": job_id, "lease_token": "lease", "progress": {"phase": "music", "rate": 12.5}}, headers=headers)
        self.assertEqual(heartbeat.status, 200)
        queue = await self.client.get("/api/queue")
        queue_data = await queue.json()
        worker = queue_data["workers"][0]
        self.assertEqual((worker["status"], worker["progress"]), ("busy", {"phase": "music", "rate": 12.5}))
        self.assertEqual(queue_data["running"][0]["progress"], {"phase": "music", "rate": 12.5})
        jobs = await self.client.get("/api/jobs")
        self.assertEqual((await jobs.json())[0]["progress"], {"phase": "music", "rate": 12.5})
        detail = await self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual((await detail.json())["progress"], {"phase": "music", "rate": 12.5})

        auth.create_user("member2", "Other", "strong-password-123", status="approved")
        other_login = await self.client.post("/api/auth/login", json={"username": "member2", "password": "strong-password-123"})
        other_csrf = (await other_login.json())["csrf_token"]
        forbidden = await self.client.delete(f"/api/my/workers/{credential['worker_id']}",
                                              headers={"X-Yue2-CSRF": other_csrf})
        self.assertEqual(forbidden.status, 404)
        member_login = await self.client.post("/api/auth/login", json={"username": "member1", "password": "strong-password-123"})
        member_csrf = (await member_login.json())["csrf_token"]
        revoked = await self.client.delete(f"/api/my/workers/{credential['worker_id']}",
                                            headers={"X-Yue2-CSRF": member_csrf})
        self.assertEqual(revoked.status, 200)
        rejected = await self.client.post("/api/worker/claim", json={}, headers=headers)
        self.assertEqual(rejected.status, 401)

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

    async def test_user_can_cancel_queued_generation_but_not_running(self):
        auth = self.client.server.app["auth"]
        auth.create_user("user1", "User 1", "strong-password-123", status="approved")
        auth.create_user("user2", "User 2", "strong-password-123", status="approved")
        
        # 1. user1 logs in and creates job
        login1 = await self.client.post("/api/auth/login", json={"username": "user1", "password": "strong-password-123"})
        csrf1 = (await login1.json())["csrf_token"]
        form = FormData()
        form.add_field("mode", "original")
        form.add_field("style", "ambient")
        form.add_field("lyrics", "cancel me")
        form.add_field("planning_enabled", "false")
        res = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": csrf1})
        self.assertEqual(res.status, 202)
        job_id = (await res.json())["id"]

        # 2. user2 logs in, cannot cancel user1's job
        login2 = await self.client.post("/api/auth/login", json={"username": "user2", "password": "strong-password-123"})
        csrf2 = (await login2.json())["csrf_token"]
        forbidden = await self.client.post(f"/api/jobs/{job_id}/cancel", headers={"X-Yue2-CSRF": csrf2})
        self.assertEqual(forbidden.status, 403)

        # 3. user1 logs back in, successfully cancels queued job
        login1 = await self.client.post("/api/auth/login", json={"username": "user1", "password": "strong-password-123"})
        csrf1 = (await login1.json())["csrf_token"]
        cancelled = await self.client.post(f"/api/jobs/{job_id}/cancel", headers={"X-Yue2-CSRF": csrf1})
        self.assertEqual(cancelled.status, 200)
        self.assertEqual((await cancelled.json())["status"], "cancelled")
        self.assertEqual(self.dispatch.jobs[job_id]["status"], "cancelled")

        # 4. Cannot cancel already cancelled job
        repeat = await self.client.post(f"/api/jobs/{job_id}/cancel", headers={"X-Yue2-CSRF": csrf1})
        self.assertEqual(repeat.status, 400)

        # 5. Create another job and claim it -> running job cannot be cancelled
        res2 = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": csrf1})
        job_id2 = (await res2.json())["id"]
        claimed = await self.client.post("/api/worker/claim", json={}, headers=self.worker_headers)
        self.assertEqual(claimed.status, 200)
        self.assertEqual((await claimed.json())["job"]["job_id"], job_id2)

        running_cancel = await self.client.post(f"/api/jobs/{job_id2}/cancel", headers={"X-Yue2-CSRF": csrf1})
        self.assertEqual(running_cancel.status, 409)
        self.assertIn("진행 중인 작업은 취소할 수 없습니다", (await running_cancel.json())["error"])

    async def test_worker_explicit_interruption_requeues_job(self):
        form = FormData()
        form.add_field("mode", "original")
        form.add_field("style", "ambient")
        form.add_field("lyrics", "retry me")
        form.add_field("planning_enabled", "false")
        res = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": self.csrf})
        job_id = (await res.json())["id"]

        # Claim 1
        claimed = await self.client.post("/api/worker/claim", json={}, headers=self.worker_headers)
        self.assertEqual((await claimed.json())["job"]["job_id"], job_id)

        # Explicit failure with requeue=True
        interrupted = await self.client.post(f"/api/worker/jobs/{job_id}/fail",
                                             json={"lease_token": "lease", "requeue": True},
                                             headers=self.worker_headers)
        self.assertEqual(interrupted.status, 200)
        self.assertEqual((await interrupted.json())["status"], "queued")

        # Job in repo and dispatch should be queued
        job_info = await self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual((await job_info.json())["status"], "queued")
        self.assertEqual(self.dispatch.jobs[job_id]["status"], "queued")

        # Claim 2 - worker should be able to claim it again
        claimed2 = await self.client.post("/api/worker/claim", json={}, headers=self.worker_headers)
        self.assertEqual((await claimed2.json())["job"]["job_id"], job_id)
        self.assertEqual((await claimed2.json())["job"]["attempts"], 2)

        # Requeue again via dedicated requeue endpoint
        requeued2 = await self.client.post(f"/api/worker/jobs/{job_id}/requeue",
                                           json={"lease_token": "lease"},
                                           headers=self.worker_headers)
        self.assertEqual(requeued2.status, 200)
        self.assertEqual((await requeued2.json())["status"], "queued")

        # Claim 3 - 3rd attempt
        claimed3 = await self.client.post("/api/worker/claim", json={}, headers=self.worker_headers)
        self.assertEqual((await claimed3.json())["job"]["job_id"], job_id)
        self.assertEqual((await claimed3.json())["job"]["attempts"], 3)

        # 3rd failure with requeue=True should become permanent failure
        final_fail = await self.client.post(f"/api/worker/jobs/{job_id}/fail",
                                            json={"lease_token": "lease", "requeue": True},
                                            headers=self.worker_headers)
        self.assertEqual(final_fail.status, 200)
        self.assertEqual((await final_fail.json())["status"], "failed")
        job_info3 = await self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual((await job_info3.json())["status"], "failed")

    async def test_dead_worker_heartbeat_timeout_requeues_job(self):
        form = FormData()
        form.add_field("mode", "original")
        form.add_field("style", "ambient")
        form.add_field("lyrics", "stale worker")
        form.add_field("planning_enabled", "false")
        res = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": self.csrf})
        job_id = (await res.json())["id"]

        # Worker claims job
        claimed = await self.client.post("/api/worker/claim", json={}, headers=self.worker_headers)
        self.assertEqual((await claimed.json())["job"]["job_id"], job_id)

        # Worker dies without heartbeat (stale)
        self.dispatch.jobs[job_id]["stale"] = True

        # Reconcile triggers requeue_stale
        requeued = self.dispatch.requeue_stale()
        self.assertEqual(requeued, [job_id])
        self.assertEqual(self.dispatch.jobs[job_id]["status"], "queued")

        # Sync repository and check status
        self.client.server.app["repository"].set_status(job_id, "queued")
        job_info = await self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual((await job_info.json())["status"], "queued")


if __name__ == "__main__":
    unittest.main()
