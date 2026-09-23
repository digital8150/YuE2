"""Publishing, artist/album CMS, charts and ComfyUI MP3 remix contracts."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from yue2_app.audio_metadata import prompt_from_mp3, recipe_from_prompt
from yue2_app.repository import Repository
from yue2_app.server import create_app


def syncsafe(value: int) -> bytes:
    return bytes(((value >> 21) & 127, (value >> 14) & 127, (value >> 7) & 127, value & 127))


def tagged_mp3(graph: dict) -> bytes:
    payload = b"\x03prompt\0" + json.dumps(graph).encode() + b"\0"
    frame = b"TXXX" + syncsafe(len(payload)) + b"\0\0" + payload
    return b"ID3\x04\0\0" + syncsafe(len(frame)) + frame + b"\xff\xfb"


class FakeStream:
    def __init__(self, data: bytes):
        self.content = self
        self.data = data
        self.status = 200
        self.headers = {"Content-Type": "audio/mpeg"}

    async def read(self, amount: int):
        return self.data[:amount]

    async def iter_chunked(self, amount: int):
        yield self.data

    def release(self):
        pass


class FakeComfy:
    def __init__(self, data: bytes):
        self.data = data

    async def start(self): pass
    async def close(self): pass
    async def system_stats(self): return {}
    async def inspect_prompt(self, prompt_id): return None
    async def open_view(self, filename, subfolder, output_type, *, range_header=None):
        return FakeStream(self.data)


class LibraryEcosystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.directory.name) / "studio.sqlite3")
        self.graph = {
            "2": {"class_type": "SeedNode", "inputs": {"seed": 987}},
            "3": {"class_type": "YuE2GenerateABC", "inputs": {"temperature": 0.7, "top_p": 0.8,
                "top_k": 30, "repetition_penalty": 1.005, "penalty_window": 100}},
            "4": {"class_type": "YuE2GenerateMusic", "inputs": {"style": "dream pop", "lyrics": "hello",
                "mode": "full", "max_duration": 120, "temperature": 1.1,
                "top_p": 0.95, "top_k": 100, "repetition_penalty": 1.2}},
        }
        self.app = create_app(repository=self.repo, comfy_client=FakeComfy(tagged_mp3(self.graph)))
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.admin = self.app["auth"].create_initial_admin("admin", "관리자", "strong-password-123")
        login = await self.client.post("/api/auth/login", json={"username": "admin", "password": "strong-password-123"})
        self.csrf = (await login.json())["csrf_token"]
        self.repo.create_job(job_id="song-1", prompt_id=None, mode="original", title="Studio draft",
                             style="dream pop", lyrics="hello", seed=987, settings={},
                             creator_id=self.admin.id, creator_name="관리자 (@admin)", status="completed")
        self.repo.set_output("song-1", filename="song.mp3")

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    @staticmethod
    def form(**fields):
        form = FormData()
        for name, value in fields.items():
            form.add_field(name, value, content_type="text/plain")
        return form

    async def test_guests_can_browse_only_published_library(self):
        album_response = await self.client.post(
            "/api/albums", data=self.form(title="Open album"), headers={"X-Yue2-CSRF": self.csrf})
        album_id = (await album_response.json())["id"]
        published = await self.client.post(
            "/api/tracks/song-1/publish", data=self.form(title="Open song", album_id=album_id),
            headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(published.status, 200)
        self.client.session.cookie_jar.clear()

        for path in ("/api/library", "/api/library/discover", "/api/library/charts",
                     "/api/library/tracks/song-1", f"/api/artists/{self.admin.id}",
                     f"/api/albums/{album_id}", "/api/tracks/song-1/audio"):
            response = await self.client.get(path)
            self.assertEqual(response.status, 200, path)
            await response.read()
        detail = await (await self.client.get(f"/api/artists/{self.admin.id}")).json()
        self.assertFalse(detail["is_mine"])
        self.assertEqual([track["title"] for track in detail["tracks"]], ["Open song"])

        self.assertEqual((await self.client.get("/api/jobs")).status, 401)
        self.assertEqual((await self.client.get("/api/artists/mine")).status, 401)
        self.assertEqual((await self.client.get("/api/albums?mine=1")).status, 401)
        self.assertEqual((await self.client.post("/api/tracks/song-1/play")).status, 401)
        self.repo.unpublish("song-1", self.admin.id)
        self.assertEqual((await self.client.get("/api/library/tracks/song-1")).status, 404)
        self.assertEqual((await self.client.get("/api/tracks/song-1/audio")).status, 404)

    async def test_artist_album_single_chart_and_remix(self):
        self.assertEqual(await (await self.client.get("/api/library")).json(), [])
        self.assertEqual((await self.client.get("/api/tracks/song-1/recipe")).status, 404)

        artist = await self.client.post("/api/artists/me", data=self.form(name="Blue Room", bio="Bedroom music"),
                                        headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(artist.status, 200, await artist.text())
        self.assertEqual((await artist.json())["name"], "Blue Room")

        album = await self.client.post("/api/albums", data=self.form(title="Night Sky", description="First album"),
                                       headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(album.status, 201, await album.text())
        album_id = (await album.json())["id"]
        self.assertEqual(await (await self.client.get("/api/albums")).json(), [])

        cover = io.BytesIO()
        Image.new("RGB", (32, 32), "blue").save(cover, format="PNG")
        form = self.form(title="First Single", album_id=album_id)
        form.add_field("cover", io.BytesIO(cover.getvalue()), filename="cover.png", content_type="image/png")
        published = await self.client.post("/api/tracks/song-1/publish", data=form,
                                           headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(published.status, 200, await published.text())
        song = (await published.json())
        self.assertEqual((song["title"], song["creator"], song["album_id"]),
                         ("First Single", "Blue Room", album_id))
        self.assertNotIn("settings", song)
        self.assertEqual((await (await self.client.get("/api/library/tracks/song-1")).json())["title"], "First Single")
        self.assertEqual(self.repo.get_job("song-1").title, "Studio draft")
        self.assertEqual((await self.client.get(song["cover_url"])).status, 200)

        discover = await (await self.client.get("/api/library/discover")).json()
        self.assertEqual(discover["albums"][0]["id"], album_id)
        self.assertEqual(discover["artists"][0]["name"], "Blue Room")
        self.assertEqual((await (await self.client.get(f"/api/albums/{album_id}")).json())["tracks"][0]["id"], "song-1")
        self.assertEqual((await (await self.client.get(f"/api/artists/{self.admin.id}")).json())["tracks"][0]["id"], "song-1")

        recipe = await (await self.client.get("/api/tracks/song-1/recipe")).json()
        self.assertEqual(recipe["style"], "dream pop")
        self.assertEqual(recipe["seed"], 987)
        self.assertEqual(recipe["settings"]["plan_temperature"], 0.7)
        self.assertEqual(recipe["title"], "First Single")

        play = await self.client.post("/api/tracks/song-1/play", headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual((await play.json())["play_count"], 1)
        self.assertEqual((await (await self.client.get("/api/library/charts")).json())[0]["play_count"], 1)

        unpublished = await self.client.delete("/api/tracks/song-1/publish", headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(unpublished.status, 200)
        self.assertEqual(await (await self.client.get("/api/library")).json(), [])
        self.assertEqual((await self.client.get("/api/tracks/song-1/recipe")).status, 404)

    async def test_private_work_stays_with_its_creator(self):
        self.app["auth"].create_user("member", "다른 사용자", "member-password-123", status="approved")
        login = await self.client.post("/api/auth/login", json={"username": "member", "password": "member-password-123"})
        csrf = (await login.json())["csrf_token"]
        self.assertEqual(await (await self.client.get("/api/jobs")).json(), [])
        self.assertEqual((await self.client.get("/api/jobs/song-1")).status, 404)
        self.assertEqual((await self.client.get("/api/tracks/song-1/audio")).status, 404)
        self.assertEqual((await self.client.get("/api/tracks/song-1/recipe")).status, 404)
        denied = await self.client.post("/api/tracks/song-1/publish", data=self.form(title="Taken"),
                                        headers={"X-Yue2-CSRF": csrf})
        self.assertEqual(denied.status, 404)

    async def test_multiple_artists_keep_tracks_albums_and_permissions_separate(self):
        primary = await (await self.client.get("/api/artists/mine")).json()
        self.assertEqual([item["id"] for item in primary], [self.admin.id])
        identities = []
        for name in ("Blue Room", "Night Signal"):
            response = await self.client.post("/api/artists", data=self.form(name=name, bio=f"{name} bio"),
                                              headers={"X-Yue2-CSRF": self.csrf})
            self.assertEqual(response.status, 201, await response.text())
            identities.append(await response.json())
        first, second = identities
        self.assertNotEqual(first["id"], second["id"])
        edited = await self.client.post(f"/api/artists/{second['id']}",
            data=self.form(name="Night Signal", bio="A different persona"),
            headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(edited.status, 200, await edited.text())
        self.assertEqual((await edited.json())["bio"], "A different persona")
        self.assertEqual({item["name"] for item in await (await self.client.get("/api/artists/mine")).json()},
                         {"관리자", "Blue Room", "Night Signal"})

        first_album_response = await self.client.post("/api/albums",
            data=self.form(title="Blue Album", artist_id=str(first["id"])), headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(first_album_response.status, 201, await first_album_response.text())
        first_album = await first_album_response.json()
        self.assertEqual(first_album["artist_id"], first["id"])
        mismatch = await self.client.post("/api/tracks/song-1/publish",
            data=self.form(title="Wrong artist", artist_id=str(second["id"]), album_id=first_album["id"]),
            headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(mismatch.status, 400)

        first_song = await self.client.post("/api/tracks/song-1/publish",
            data=self.form(title="Blue Single", artist_id=str(first["id"]), album_id=first_album["id"]),
            headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(first_song.status, 200, await first_song.text())
        self.assertEqual((await first_song.json())["creator"], "Blue Room")
        self.repo.create_job(job_id="song-2", prompt_id=None, mode="original", title="Second draft",
                             style="electronic", lyrics="", seed=4, settings={}, creator_id=self.admin.id,
                             creator_name="관리자 (@admin)", status="completed")
        self.repo.set_output("song-2", filename="second.mp3")
        second_song = await self.client.post("/api/tracks/song-2/publish",
            data=self.form(title="Night Single", artist_id=str(second["id"])),
            headers={"X-Yue2-CSRF": self.csrf})
        self.assertEqual(second_song.status, 200, await second_song.text())
        self.assertEqual((await second_song.json())["creator"], "Night Signal")
        first_page = await (await self.client.get(f"/api/artists/{first['id']}")).json()
        second_page = await (await self.client.get(f"/api/artists/{second['id']}")).json()
        self.assertEqual([item["id"] for item in first_page["tracks"]], ["song-1"])
        self.assertEqual([item["id"] for item in second_page["tracks"]], ["song-2"])
        self.assertEqual([item["id"] for item in first_page["albums"]], [first_album["id"]])
        self.assertEqual(second_page["albums"], [])

        self.app["auth"].create_user("member", "다른 사용자", "member-password-123", status="approved")
        login = await self.client.post("/api/auth/login", json={"username": "member", "password": "member-password-123"})
        csrf = (await login.json())["csrf_token"]
        denied_edit = await self.client.post(f"/api/artists/{first['id']}",
            data=self.form(name="Taken"), headers={"X-Yue2-CSRF": csrf})
        self.assertEqual(denied_edit.status, 404)
        denied_album = await self.client.post("/api/albums",
            data=self.form(title="Taken", artist_id=str(first["id"])), headers={"X-Yue2-CSRF": csrf})
        self.assertEqual(denied_album.status, 400)
        self.assertEqual((await (await self.client.get(f"/api/artists/{first['id']}")).json())["is_mine"], False)

    def test_mp3_tag_extraction(self):
        graph = prompt_from_mp3(tagged_mp3(self.graph))
        self.assertEqual(recipe_from_prompt(graph)["seed"], 987)
        self.assertIsNone(prompt_from_mp3(b"not an mp3"))


if __name__ == "__main__":
    unittest.main()
