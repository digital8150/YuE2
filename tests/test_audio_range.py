"""Exercise seeking through the real HTTP client and Studio streaming route."""

import tempfile
import unittest
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from yue2_app.comfy_client import ComfyClient
from yue2_app.repository import Repository
from yue2_app.server import create_app


class AudioRangeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        audio = Path(self.temp.name) / "audio.mp3"
        audio.write_bytes(b"0123456789")
        self.ranges = []

        async def view(request):
            self.ranges.append(request.headers.get("Range"))
            return web.FileResponse(audio)

        upstream = web.Application()
        upstream.router.add_get("/view", view)
        self.upstream = TestServer(upstream)
        await self.upstream.start_server()
        repository = Repository(Path(self.temp.name) / "library.sqlite3")
        repository.create_job(job_id="track", prompt_id="prompt", mode="original",
                              title="테스트 음악", style="ambient", lyrics="", seed=1, settings={})
        repository.set_output("track", filename="audio.mp3", subfolder="", output_type="output")
        app = create_app(repository=repository, comfy_client=ComfyClient(str(self.upstream.make_url("/"))))
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        app["auth"].create_initial_admin("admin", "관리자", "strong-password-123")
        await self.client.post("/api/auth/login", json={"username": "admin", "password": "strong-password-123"})

    async def asyncTearDown(self):
        await self.client.close()
        await self.upstream.close()
        self.temp.cleanup()

    async def test_full_audio_and_download_keep_content(self):
        for endpoint in ("audio", "download"):
            response = await self.client.get(f"/api/tracks/track/{endpoint}")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Accept-Ranges"], "bytes")
            self.assertEqual(await response.read(), b"0123456789")
            if endpoint == "download":
                self.assertIn("attachment", response.headers["Content-Disposition"])

    async def test_seek_preserves_range_status_headers_and_bytes(self):
        response = await self.client.get("/api/tracks/track/audio", headers={"Range": "bytes=3-6"})
        self.assertEqual(self.ranges[-1], "bytes=3-6")
        self.assertEqual(response.status, 206)
        self.assertEqual(response.headers["Content-Range"], "bytes 3-6/10")
        self.assertEqual(response.headers["Content-Length"], "4")
        self.assertEqual(await response.read(), b"3456")

    async def test_out_of_bounds_seek_is_not_reported_as_engine_failure(self):
        response = await self.client.get("/api/tracks/track/audio", headers={"Range": "bytes=100-"})
        self.assertEqual(response.status, 416)


if __name__ == "__main__":
    unittest.main()
