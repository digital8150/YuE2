"""Account onboarding and shared library access via invite codes."""

import tempfile
import unittest
from pathlib import Path

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from yue2_app.repository import Repository
from yue2_app.server import create_app


class FakeComfy:
    async def start(self): pass
    async def close(self): pass
    async def system_stats(self): return {}
    async def queue_prompt(self, prompt, client_id): return "prompt-1"
    async def inspect_prompt(self, prompt_id): return None


class AuthFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.temp.name) / "studio.sqlite3")
        self.app = create_app(repository=self.repo, comfy_client=FakeComfy(), setup_token="setup-secret")
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def test_sessions_survive_another_login_and_logout_independently(self):
        anonymous = await self.client.get("/api/auth/me")
        self.assertEqual(anonymous.status, 200)
        self.assertEqual((await anonymous.json())["user"], None)
        self.assertEqual((await self.client.get("/api/queue")).status, 401)

        auth = self.app["auth"]
        admin = auth.create_initial_admin("captain", "Captain", "first-password-123")
        first_token, first_csrf = auth.create_session(admin.id)
        second_token, _ = auth.create_session(admin.id)
        first_cookie = {"Cookie": f"yue2_session={first_token}"}
        second_cookie = {"Cookie": f"yue2_session={second_token}"}

        for cookie in (first_cookie, second_cookie):
            response = await self.client.get("/api/auth/me", headers=cookie)
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())["user"]["username"], "captain")
            self.assertEqual((await self.client.get("/api/queue", headers=cookie)).status, 200)

        logout = await self.client.post(
            "/api/auth/logout", headers={**first_cookie, "X-Yue2-CSRF": first_csrf}
        )
        self.assertEqual(logout.status, 200)
        self.assertIsNone((await (await self.client.get("/api/auth/me", headers=first_cookie)).json())["user"])
        self.assertEqual((await self.client.get("/api/queue", headers=second_cookie)).status, 200)

    async def test_invite_code_onboarding_and_shared_attribution(self):
        self.assertEqual((await self.client.get("/api/auth/setup-status")).status, 200)
        self.assertEqual(await (await self.client.get("/api/library")).json(), [])
        self.assertEqual((await self.client.get("/api/jobs")).status, 401)
        admin_data = {"username": "captain", "display_name": "회장", "password": "first-password-123", "setup_code": "wrong"}
        self.assertEqual((await self.client.post("/api/auth/setup", json=admin_data)).status, 403)
        admin_data["setup_code"] = "setup-secret"
        setup = await self.client.post("/api/auth/setup", json=admin_data)
        self.assertEqual(setup.status, 201)
        admin_csrf = (await setup.json())["csrf_token"]
        self.assertEqual((await self.client.post("/api/auth/setup", json=admin_data)).status, 409)

        # Admin lists default invites (seeded with YUE-WELCOME)
        invites_res = await self.client.get("/api/admin/invites")
        self.assertEqual(invites_res.status, 200)
        invites = (await invites_res.json())["invites"]
        self.assertTrue(any(inv["code"] == "YUE-WELCOME" for inv in invites))

        # Admin generates a dedicated 1-use invite code
        create_inv = await self.client.post(
            "/api/admin/invites",
            json={"code": "CLUB-2026", "max_uses": 1, "note": "신입 부원용"},
            headers={"X-Yue2-CSRF": admin_csrf},
        )
        self.assertEqual(create_inv.status, 201)
        self.assertEqual((await create_inv.json())["code"], "CLUB-2026")

        # Member attempts registration without invite code -> 400
        member = {"username": "member1", "display_name": "동아리원", "password": "member-password-123"}
        signup_no_code = await self.client.post("/api/auth/register", json=member)
        self.assertEqual(signup_no_code.status, 400)

        # Member attempts registration with invalid invite code -> 400
        member_bad = {**member, "invite_code": "INVALID-CODE"}
        signup_bad_code = await self.client.post("/api/auth/register", json=member_bad)
        self.assertEqual(signup_bad_code.status, 400)

        # Member registers with the valid invite code -> 201 and immediately approved
        member_good = {**member, "invite_code": "club-2026"}  # Case-insensitive
        signup = await self.client.post("/api/auth/register", json=member_good)
        self.assertEqual(signup.status, 201)
        signup_data = await signup.json()
        self.assertEqual(signup_data["status"], "approved")

        # Exhausted invite code cannot be reused if max_uses exceeded
        member2 = {"username": "member2", "display_name": "다른부원", "password": "member-password-123", "invite_code": "CLUB-2026"}
        signup2 = await self.client.post("/api/auth/register", json=member2)
        self.assertEqual(signup2.status, 400)

        # Member logs in and verifies immediate approval
        login = await self.client.post("/api/auth/login", json=member)
        self.assertEqual(login.status, 200)
        member_csrf = (await login.json())["csrf_token"]

        # Member cannot access admin invite management
        self.assertEqual((await self.client.get("/api/admin/invites")).status, 403)

        # Member generates music
        form = {"mode": "original", "style": "ambient", "title": "공유 곡"}
        self.assertEqual((await self.client.post("/api/generations", data=form)).status, 403)
        created = await self.client.post("/api/generations", data=form, headers={"X-Yue2-CSRF": member_csrf})
        self.assertEqual(created.status, 202, await created.text())
        job = await created.json()
        self.assertEqual(job["creator"], "동아리원 (@member1)")
        self.repo.set_output(job["id"], filename="song.mp3")
        library = await (await self.client.get("/api/library")).json()
        self.assertEqual(library, [])
        publish = FormData()
        publish.add_field("title", "공유 곡", content_type="text/plain")
        response = await self.client.post(f"/api/tracks/{job['id']}/publish", data=publish,
                                          headers={"X-Yue2-CSRF": member_csrf})
        self.assertEqual(response.status, 200, await response.text())
        library = await (await self.client.get("/api/library")).json()
        self.assertEqual(library[0]["creator"], "동아리원")

        # Member logs out
        self.assertEqual((await self.client.post("/api/auth/logout", headers={"X-Yue2-CSRF": member_csrf})).status, 200)
        self.assertEqual((await (await self.client.get("/api/library")).json())[0]["creator"], "동아리원")
        self.assertEqual((await self.client.get("/api/jobs")).status, 401)


if __name__ == "__main__":
    unittest.main()
