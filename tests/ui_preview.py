"""Isolated UI preview: python tests/ui_preview.py, then open localhost:7861.

Serves the real frontend with in-memory sample tracks and silent audio. This
never accesses the real library, generation service, or user audio files.
"""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import uuid
import wave

from aiohttp import web


STATIC = Path(__file__).resolve().parents[1] / "yue2_app" / "static"
TITLES = [
    ("새벽 두 시", "따뜻한 로파이 · 피아노 · 부드러운 드럼"),
    ("Blue after rain", "Dream pop, hazy guitars, soft vocals"),
    ("오래된 여름", "어쿠스틱 인디 팝 · 여름밤 · 기타"),
    ("Velvet moon", "Neo soul, warm bass, intimate vocals"),
    ("도시의 온도", "시티 팝 · 신스 · 그루비한 베이스"),
    ("Somewhere, again", "Ambient, cinematic strings, slow build"),
    ("빛이 머무는 곳", "잔잔한 피아노 · 스트링 · 연주곡"),
    ("Paper planes", "Indie folk, acoustic guitar, bright chorus"),
]
TRACKS = [
    {"id": f"preview-{i}", "title": title, "style": style,
     "mode": "cover" if i % 3 == 1 else "original", "status": "completed",
     "created_at": "2026-09-23T01:00:00+00:00", "lyrics": "",
     "creator": "미리보기 회원",
     "published": True, "artist_id": 1, "play_count": (8 - i) * 24,
     "audio_url": "/preview.wav", "download_url": "/preview.wav"}
    for i, (title, style) in enumerate(TITLES)
]
SOUND = BytesIO()
with wave.open(SOUND, "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(8000)
    audio.writeframes(b"\x00\x00" * 8000 * 30)


async def index(request):
    content = (STATIC / "index.html").read_text(encoding="utf-8")
    return web.Response(text=content.replace("<title>YUE STUDIO</title>",
                        "<title>YUE STUDIO · UI TEST</title>"), content_type="text/html")


async def health(request):
    return web.json_response({"app": "ok", "engine": "online"})


async def preview_user(request):
    return web.json_response({"user": {"id": 1, "username": "preview", "display_name": "미리보기 회원", "role": "member"},
                              "csrf_token": "preview-only"})


async def jobs(request):
    return web.json_response([
        {"id": "preview-running", "title": "만들고 있는 음악", "style": "Cinematic, strings",
         "mode": "original", "status": "running", "created_at": "2026-09-23T01:00:00Z"},
        {"id": "preview-failed", "title": "다시 시도할 음악", "style": "Indie pop",
         "mode": "cover", "status": "failed", "error": "미리보기용 오류 상태입니다."},
        *TRACKS[:6],
    ])


async def library(request):
    query = request.query.get("q", "").casefold()
    mode = request.query.get("mode")
    return web.json_response([track for track in TRACKS
                              if track.get("published") and query in (track["title"] + track["style"]).casefold()
                              and (not mode or track["mode"] == mode)])


async def discover(request):
    public = [track for track in TRACKS if track.get("published")]
    return web.json_response({"new_releases": public, "this_week": public, "charts": public,
                              "albums": [{"id": "preview-album", "title": "푸른 새벽", "description": "첫 번째 앨범",
                                          "artist_id": 1, "artist_name": "미리보기 회원", "track_count": 3, "cover_url": None}],
                              "artists": [{"id": 1, "name": "미리보기 회원", "bio": "음악을 만들어요",
                                           "track_count": len(TRACKS), "avatar_url": None, "banner_url": None}]})


async def charts(request):
    return web.json_response([track for track in TRACKS if track.get("published")])


async def artist(request):
    return web.json_response({"artist": {"id": 1, "name": "미리보기 회원", "bio": "음악을 만들어요",
                                         "track_count": len(TRACKS), "avatar_url": None, "banner_url": None},
                              "albums": [], "tracks": TRACKS, "is_mine": True})


async def album(request):
    return web.json_response({"album": {"id": "preview-album", "title": "푸른 새벽", "description": "첫 번째 앨범",
                                         "artist_id": 1, "artist_name": "미리보기 회원", "track_count": 3, "cover_url": None},
                              "tracks": TRACKS[:3], "is_mine": True})


async def single(request):
    return web.json_response(next((track for track in TRACKS if track["id"] == request.match_info["job_id"]), TRACKS[0]))


async def generate(request):
    fields = await request.post()
    track = {"id": str(uuid.uuid4()), "title": fields.get("title") or "UI 테스트 곡",
             "style": fields.get("style", ""), "mode": fields.get("mode", "original"),
             "lyrics": fields.get("lyrics", ""), "status": "completed",
             "created_at": datetime.now(timezone.utc).isoformat(),
             "creator": "미리보기 회원",
             "audio_url": "/preview.wav", "download_url": "/preview.wav"}
    TRACKS.insert(0, track)
    return web.json_response(track, status=202)


async def sound(request):
    data = SOUND.getvalue()
    headers = {"Accept-Ranges": "bytes"}
    if byte_range := request.headers.get("Range"):
        start, end = byte_range.removeprefix("bytes=").split("-", 1)
        start = int(start or 0)
        end = min(int(end) if end else len(data) - 1, len(data) - 1)
        if start > end:
            return web.Response(status=416, headers={"Content-Range": f"bytes */{len(data)}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        return web.Response(body=data[start:end + 1], status=206, headers=headers, content_type="audio/wav")
    return web.Response(body=data, headers=headers, content_type="audio/wav")


def main():
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_static("/static/", STATIC)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/auth/me", preview_user)
    app.router.add_get("/api/jobs", jobs)
    app.router.add_get("/api/library", library)
    app.router.add_get("/api/library/discover", discover)
    app.router.add_get("/api/library/charts", charts)
    app.router.add_get("/api/library/tracks/{job_id}", single)
    app.router.add_get("/api/artists/{artist_id}", artist)
    app.router.add_get("/api/albums/{album_id}", album)
    app.router.add_get("/api/albums", lambda request: web.json_response([]))
    app.router.add_post("/api/generations", generate)
    app.router.add_get("/preview.wav", sound)
    web.run_app(app, host="127.0.0.1", port=7861)


if __name__ == "__main__":
    main()
