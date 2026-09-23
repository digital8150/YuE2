"""Exercise the filename sent to ComfyUI's upload endpoint."""

import unittest

from aiohttp import web
from aiohttp.test_utils import TestServer

from yue2_app.comfy_client import ComfyClient


class ComfyUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_unicode_audio_name_uses_short_ascii_upload_name(self):
        received = []

        async def upload(request):
            data = await request.post()
            file = data["image"]
            received.append((file.filename, file.file.read(), data["subfolder"]))
            return web.json_response({"name": file.filename, "subfolder": data["subfolder"], "type": "input"})

        app = web.Application()
        app.router.add_post("/upload/image", upload)
        server = TestServer(app)
        await server.start_server()
        client = ComfyClient(str(server.make_url("/")))
        try:
            filename = "너에게 전하고 싶은 마법의 말💌 " * 15 + ".m4a"
            result = await client.upload_audio(b"audio", filename)
            uploaded_name, content, subfolder = received[0]
            self.assertEqual(result["name"], uploaded_name)
            self.assertTrue(uploaded_name.endswith(".m4a"))
            self.assertLessEqual(len(uploaded_name), 40)
            self.assertTrue(uploaded_name.isascii())
            self.assertEqual(content, b"audio")
            self.assertEqual(subfolder, "yue2_uploads")
        finally:
            await client.close()
            await server.close()
