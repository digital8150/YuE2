"""Local aiohttp web server for the YuE2 music generation app."""

from __future__ import annotations

import asyncio
import io
import json
import math
import mimetypes
import os
import hmac
import hashlib
import secrets
import random
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from aiohttp import web
from PIL import Image, ImageOps, UnidentifiedImageError

from .auth import AuthStore, SESSION_DAYS, User
from .comfy_client import (
    GENERIC_GENERATION_ERROR,
    ComfyClient,
    ComfyResponseError,
)
from .repository import Job, Repository
from .audio_metadata import prompt_from_mp3, recipe_from_prompt
from .workflow_builder import build_workflow
from .dispatch import DispatchStore


HOST = os.environ.get("YUE2_HOST", "127.0.0.1")
PORT = int(os.environ.get("YUE2_PORT", "7860"))
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
UINT63_MAX = (1 << 63) - 1
DEFAULT_DURATION = 120.0
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 0.95
DEFAULT_TOP_K = 100
DEFAULT_REPETITION_PENALTY = 1.2
DEFAULT_PLAN_TEMPERATURE = 0.7
DEFAULT_PLAN_TOP_P = 0.9
DEFAULT_PLAN_TOP_K = 30
DEFAULT_PLAN_REPETITION_PENALTY = 1.005
DEFAULT_PENALTY_WINDOW = 100
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
OFFLINE_ERROR = "생성 엔진에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
INPUT_ERROR = "입력값을 확인해 주세요."
UPLOAD_ERROR = "오디오 파일을 확인해 주세요."
_AUDIO_FIELDS = {"audio", "file", "source", "source_file"}
_SAFE_FILENAME_RE = re.compile(r"[^\w\-.가-힣 ]+", re.UNICODE)


class RequestInputError(ValueError):
    pass


@dataclass(slots=True)
class GenerationInput:
    mode: str
    title: str
    style: str
    lyrics: str
    duration: float
    seed: int
    temperature: float
    top_p: float
    top_k: int
    repetition_penalty: float
    planning_enabled: bool
    plan_temperature: float
    plan_top_p: float
    plan_top_k: int
    plan_repetition_penalty: float
    penalty_window: int
    source_filename: str | None
    source_path: str | None

    @property
    def settings(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            "duration": self.duration,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repetition_penalty": self.repetition_penalty,
        }
        if self.mode == "original":
            values.update(
                {
                    "planning_enabled": self.planning_enabled,
                    "plan_temperature": self.plan_temperature,
                    "plan_top_p": self.plan_top_p,
                    "plan_top_k": self.plan_top_k,
                    "plan_repetition_penalty": self.plan_repetition_penalty,
                    "penalty_window": self.penalty_window,
                }
            )
        return values


def _error(message: str, status: int) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RequestInputError(INPUT_ERROR)


def _parse_number(
    fields: dict[str, str],
    name: str,
    *,
    default: float | int,
    minimum: float,
    maximum: float,
    integer: bool = False,
) -> float | int:
    raw = fields.get(name)
    if raw is None or not raw.strip():
        return int(default) if integer else float(default)
    try:
        value = float(raw.strip())
    except (TypeError, ValueError) as error:
        raise RequestInputError(INPUT_ERROR) from error
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise RequestInputError(INPUT_ERROR)
    if integer:
        if not value.is_integer():
            raise RequestInputError(INPUT_ERROR)
        return int(value)
    return value


def _parse_seed(fields: dict[str, str]) -> int:
    raw = fields.get("seed")
    if raw is None or not raw.strip():
        return random.SystemRandom().randint(0, UINT63_MAX)
    try:
        value = int(raw.strip())
    except (TypeError, ValueError) as error:
        raise RequestInputError(INPUT_ERROR) from error
    if value < 0 or value > UINT63_MAX:
        raise RequestInputError(INPUT_ERROR)
    return value


def _safe_uploaded_name(filename: str) -> str:
    # ``Path.name`` strips path components supplied by a browser.  Keep the
    # original extension for ComfyUI's audio decoder while preventing path use.
    name = Path(filename.replace("\\", "/")).name
    return name or "upload"


async def _parse_generation_request(request: web.Request) -> GenerationInput:
    fields: dict[str, str] = {}
    source_filename: str | None = None
    source_path: str | None = None
    if request.content_type.lower().startswith("multipart/"):
        try:
            reader = await request.multipart()
        except Exception as error:
            raise RequestInputError(INPUT_ERROR) from error

        try:
            while True:
                part = await reader.next()
                if part is None:
                    break
                name = part.name or ""
                if part.filename:
                    if source_path is not None:
                        raise RequestInputError(UPLOAD_ERROR)
                    safe_name = _safe_uploaded_name(part.filename)
                    extension = Path(safe_name).suffix.lower()
                    if extension not in ALLOWED_AUDIO_EXTENSIONS:
                        raise RequestInputError(UPLOAD_ERROR)
                    descriptor, path = tempfile.mkstemp(prefix="yue2-upload-", suffix=extension)
                    os.close(descriptor)
                    size = 0
                    try:
                        with open(path, "wb") as target:
                            while True:
                                chunk = await part.read_chunk(1024 * 1024)
                                if not chunk:
                                    break
                                size += len(chunk)
                                if size > MAX_UPLOAD_BYTES:
                                    raise RequestInputError(UPLOAD_ERROR)
                                target.write(chunk)
                    except Exception:
                        try:
                            os.unlink(path)
                        except OSError:
                            pass
                        raise
                    source_filename = safe_name
                    source_path = path
                else:
                    try:
                        fields[name] = await part.text()
                    except Exception as error:
                        raise RequestInputError(INPUT_ERROR) from error
        except RequestInputError:
            raise
        except Exception as error:
            raise RequestInputError(INPUT_ERROR) from error
    else:
        # Browsers generally submit a multipart body, but accepting a regular
        # form body for original generations keeps the no-file endpoint usable
        # by simple clients while retaining streaming multipart uploads for
        # cover files.
        try:
            posted = await request.post()
            fields = {str(key): str(value) for key, value in posted.items() if isinstance(value, str)}
        except Exception as error:
            raise RequestInputError(INPUT_ERROR) from error

    mode_raw = fields.get("mode")
    if mode_raw is None or not mode_raw.strip():
        raise RequestInputError(INPUT_ERROR)
    mode = mode_raw.strip().lower()
    if mode not in {"original", "cover"}:
        raise RequestInputError(INPUT_ERROR)
    style = fields.get("style", "").strip()
    if not style:
        raise RequestInputError(INPUT_ERROR)
    if mode == "cover" and source_path is None:
        raise RequestInputError(UPLOAD_ERROR)
    lyrics = fields.get("lyrics", "")
    title = fields.get("title", "").strip() or ("새로운 커버" if mode == "cover" else "새로운 트랙")
    duration = float(
        _parse_number(
            fields,
            "duration",
            default=360.0 if mode == "cover" else DEFAULT_DURATION,
            minimum=0.04,
            maximum=900.0,
        )
    )
    temperature = float(
        _parse_number(fields, "temperature", default=DEFAULT_TEMPERATURE, minimum=0.0, maximum=5.0)
    )
    top_p = float(_parse_number(fields, "top_p", default=DEFAULT_TOP_P, minimum=0.01, maximum=1.0))
    top_k = int(
        _parse_number(fields, "top_k", default=DEFAULT_TOP_K, minimum=1, maximum=32768, integer=True)
    )
    repetition_penalty = float(
        _parse_number(
            fields,
            "repetition_penalty",
            default=DEFAULT_REPETITION_PENALTY,
            minimum=0.01,
            maximum=10.0,
        )
    )
    seed = _parse_seed(fields)
    if mode == "original":
        planning_enabled = _parse_bool(
            fields.get("planning_enabled", fields.get("use_plan")), True
        )
        plan_temperature = float(
            _parse_number(
                fields,
                "plan_temperature",
                default=DEFAULT_PLAN_TEMPERATURE,
                minimum=0.0,
                maximum=5.0,
            )
        )
        plan_top_p = float(
            _parse_number(fields, "plan_top_p", default=DEFAULT_PLAN_TOP_P, minimum=0.01, maximum=1.0)
        )
        plan_top_k = int(
            _parse_number(fields, "plan_top_k", default=DEFAULT_PLAN_TOP_K, minimum=1, maximum=32768, integer=True)
        )
        plan_repetition_penalty = float(
            _parse_number(
                fields,
                "plan_repetition_penalty",
                default=DEFAULT_PLAN_REPETITION_PENALTY,
                minimum=0.01,
                maximum=10.0,
            )
        )
        penalty_window = int(
            _parse_number(
                fields,
                "penalty_window",
                default=DEFAULT_PENALTY_WINDOW,
                minimum=1,
                maximum=20000,
                integer=True,
            )
        )
    else:
        planning_enabled = False
        plan_temperature = DEFAULT_PLAN_TEMPERATURE
        plan_top_p = DEFAULT_PLAN_TOP_P
        plan_top_k = DEFAULT_PLAN_TOP_K
        plan_repetition_penalty = DEFAULT_PLAN_REPETITION_PENALTY
        penalty_window = DEFAULT_PENALTY_WINDOW
    return GenerationInput(
        mode=mode,
        title=title,
        style=style,
        lyrics=lyrics,
        duration=duration,
        seed=seed,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repetition_penalty=repetition_penalty,
        planning_enabled=planning_enabled,
        plan_temperature=plan_temperature,
        plan_top_p=plan_top_p,
        plan_top_k=plan_top_k,
        plan_repetition_penalty=plan_repetition_penalty,
        penalty_window=penalty_window,
        source_filename=source_filename,
        source_path=source_path,
    )


def _public_job(job: Job, client: ComfyClient | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": job.id,
        "mode": job.mode,
        "title": job.title or ("새로운 커버" if job.mode == "cover" else "새로운 트랙"),
        "style": job.style,
        "lyrics": job.lyrics,
        "created_at": job.created_at,
        "status": job.status,
        "seed": job.seed,
        "settings": dict(job.settings),
        "source_filename": job.source_filename,
        "creator": job.creator_name or "이전 작업",
        "artist_id": job.artist_id,
        "error": job.error,
        "published": job.published_at is not None,
        "published_title": job.published_title,
        "cover_url": f"/api/tracks/{job.id}/cover" if job.published_at and job.cover_filename else None,
    }
    if job.status == "completed":
        result["audio_url"] = f"/api/tracks/{job.id}/audio"
        result["download_url"] = f"/api/tracks/{job.id}/download"
    elif job.status == "running" and job.prompt_id and client is not None:
        progress_for = getattr(client, "progress_for", None)
        progress = progress_for(job.prompt_id) if progress_for is not None else None
        if progress:
            result["progress"] = progress
    return result


def _public_library_job(job: Job, repository: Repository | None = None) -> dict[str, Any]:
    result = _public_job(job)
    result["title"] = job.published_title or result["title"]
    artist = repository.get_artist(job.artist_id) if repository and job.artist_id is not None else None
    result["creator"] = artist["artist_name"] if artist else (job.creator_name or "이전 작업").split(" (@")[0]
    result["artist_id"] = job.artist_id
    result["album_id"] = job.album_id
    result["play_count"] = job.play_count
    album = repository.get_album(job.album_id) if repository and job.album_id else None
    result["cover_url"] = (f"/api/tracks/{job.id}/cover?v={job.cover_filename}" if job.cover_filename else
                           f"/api/albums/{job.album_id}/cover?v={album['cover_filename']}" if album and album["cover_filename"] else None)
    # Generation inputs are read from the MP3 only when a listener chooses to reuse them.
    result.pop("seed", None)
    result.pop("settings", None)
    result.pop("source_filename", None)
    result.pop("published_title", None)
    return result


def _public_album(album: dict[str, Any], repository: Repository) -> dict[str, Any]:
    artist = repository.get_artist(album["artist_id"])
    tracks = repository.list_artist_tracks(album["artist_id"], 1)
    fallback = (tracks[0].creator_name or "아티스트").split(" (@")[0] if tracks else "아티스트"
    return {
        "id": album["id"], "title": album["title"], "description": album["description"],
        "artist_id": album["artist_id"], "artist_name": artist["artist_name"] if artist else fallback,
        "cover_url": f"/api/albums/{album['id']}/cover?v={album['cover_filename']}" if album["cover_filename"] else None,
        "track_count": album["track_count"], "published_at": album["published_at"],
        "created_at": album["created_at"],
    }


def _public_artist(artist_id: int, repository: Repository, fallback_name: str = "아티스트") -> dict[str, Any]:
    profile = repository.get_artist(artist_id)
    tracks = repository.list_artist_tracks(artist_id, 100)
    if profile:
        name = profile["artist_name"]
    elif tracks:
        name = (tracks[0].creator_name or fallback_name).split(" (@")[0]
    else:
        name = fallback_name
    return {
        "id": artist_id, "name": name, "bio": profile["bio"] if profile else "",
        "avatar_url": f"/api/artists/{artist_id}/avatar?v={profile['avatar_filename']}" if profile and profile["avatar_filename"] else None,
        "banner_url": f"/api/artists/{artist_id}/banner?v={profile['banner_filename']}" if profile and profile["banner_filename"] else None,
        "track_count": len(tracks),
    }


def _may_manage(job: Job, user: User) -> bool:
    return job.creator_id == user.id or user.role == "admin" and job.creator_id is None


def _may_read(job: Job, user: User | None) -> bool:
    return bool(user and _may_manage(job, user)) or (job.published_at is not None and job.status == "completed")


async def _sync_job(app: web.Application, job: Job) -> Job:
    if app.get("dispatch") is not None:
        return job
    if job.status in {"completed", "failed", "cancelled"} or not job.prompt_id:
        return job
    client: ComfyClient = app["comfy"]
    try:
        transition = await client.inspect_prompt(job.prompt_id)
    except Exception:
        # A transient ComfyUI/network failure must not move a job backwards or
        # erase output metadata.  The next request will retry the inspection.
        return job
    if not isinstance(transition, dict):
        return job
    status = transition.get("status")
    repository: Repository = app["repository"]
    try:
        if status == "completed":
            output = transition.get("output")
            if not isinstance(output, dict) or not output.get("filename"):
                return job
            repository.set_output(
                job.id,
                filename=str(output["filename"]),
                subfolder=str(output.get("subfolder") or ""),
                output_type=str(output.get("type") or "output"),
            )
            if isinstance(client, ComfyClient):
                client.clear_progress(job.prompt_id)
        elif status == "failed":
            repository.set_status(job.id, "failed", GENERIC_GENERATION_ERROR)
            if isinstance(client, ComfyClient):
                client.clear_progress(job.prompt_id)
        elif status == "cancelled":
            repository.set_status(job.id, "cancelled")
            if isinstance(client, ComfyClient):
                client.clear_progress(job.prompt_id)
        elif status in {"queued", "running"}:
            if status != job.status and not (job.status == "running" and status == "queued"):
                repository.set_status(job.id, status)
    except Exception:
        return job
    updated = repository.get_job(job.id) or job
    if updated.status != job.status:
        if updated.status in {"completed", "failed", "cancelled"}:
            app["prompt_jobs"].pop(job.prompt_id, None)
            app["pending_progress"].pop(job.id, None)
            app["last_progress"].pop(job.id, None)
        await _broadcast_job(app, updated)
    return updated


async def _sync_all(app: web.Application) -> None:
    if app.get("dispatch") is not None:
        return
    repository: Repository = app["repository"]
    for job in repository.list_nonterminal():
        await _sync_job(app, job)


async def _broadcast(app: web.Application, payload: dict[str, Any]) -> None:
    sockets = tuple(app["event_sockets"].items())
    if not sockets:
        return
    event_job = app["repository"].get_job(payload["job"]["id"]) if payload.get("type") == "job" else None
    progress_jobs = ({job_id: app["repository"].get_job(job_id) for job_id in payload["updates"]}
                     if payload.get("type") == "progress" else {})
    outgoing = []
    for socket, user in sockets:
        filtered = payload
        if payload.get("type") == "job":
            if event_job is None or not _may_manage(event_job, user):
                continue
        elif payload.get("type") == "progress":
            updates = {job_id: progress for job_id, progress in payload["updates"].items()
                       if progress_jobs[job_id] is not None and _may_manage(progress_jobs[job_id], user)}
            if not updates:
                continue
            filtered = {"type": "progress", "updates": updates}
        outgoing.append((socket, filtered))
    results = await asyncio.gather(*(socket.send_json(item) for socket, item in outgoing), return_exceptions=True)
    for (socket, _), result in zip(outgoing, results):
        if isinstance(result, Exception):
            app["event_sockets"].pop(socket, None)


async def _broadcast_job(app: web.Application, job: Job) -> None:
    await _broadcast(app, {"type": "job", "job": _public_job(job, app["comfy"])})


def _on_comfy_event(app: web.Application, event: dict[str, Any]) -> None:
    data = event.get("data")
    if not isinstance(data, dict):
        return
    prompt_id = str(data.get("prompt_id") or "")
    job_id = app["prompt_jobs"].get(prompt_id)
    if not job_id:
        return
    kind = event.get("type")
    if kind in {"progress", "executing"}:
        progress = app["comfy"].progress_for(prompt_id)
        if progress and progress != app["pending_progress"].get(job_id, app["last_progress"].get(job_id)):
            app["pending_progress"][job_id] = dict(progress)
    if kind in {"execution_start", "executing"} and data.get("node") is not None:
        job = app["repository"].get_job(job_id)
        if job is not None and job.status == "queued":
            app["repository"].set_status(job_id, "running")
            updated = app["repository"].get_job(job_id)
            if updated is not None:
                asyncio.create_task(_broadcast_job(app, updated))
    if kind in {"execution_success", "execution_error", "execution_interrupted"} or (kind == "executing" and data.get("node") is None):
        if job_id not in app["finish_tasks"]:
            task = asyncio.create_task(_sync_finished_prompt(app, job_id))
            app["finish_tasks"][job_id] = task
            task.add_done_callback(lambda _task: app["finish_tasks"].pop(job_id, None))


async def _sync_finished_prompt(app: web.Application, job_id: str) -> None:
    # ComfyUI can emit the final socket event just before history is committed.
    for delay in (0.15, 0.35, 0.75):
        await asyncio.sleep(delay)
        job = app["repository"].get_job(job_id)
        if job is None or job.status in {"completed", "failed", "cancelled"}:
            return
        updated = await _sync_job(app, job)
        if updated.status in {"completed", "failed", "cancelled"}:
            return


async def _flush_progress(app: web.Application) -> None:
    while True:
        await asyncio.sleep(0.1)
        pending = app["pending_progress"]
        if pending:
            updates = dict(pending)
            pending.clear()
            app["last_progress"].update(updates)
            await _broadcast(app, {"type": "progress", "updates": updates})


async def _reconcile_jobs(app: web.Application) -> None:
    while True:
        await asyncio.sleep(5)
        if app.get("dispatch") is not None:
            for job_id in app["dispatch"].expired():
                app["repository"].set_status(job_id, "failed", GENERIC_GENERATION_ERROR)
                _remove_source(app, job_id)
                job = app["repository"].get_job(job_id)
                if job:
                    await _broadcast_job(app, job)
            for job_id, status, output_filename in app["dispatch"].terminal():
                job = app["repository"].get_job(job_id)
                if job is None or job.status in {"completed", "failed", "cancelled"}:
                    continue
                if status == "completed":
                    filename = output_filename or job_id + ".mp3"
                    if (app["output_dir"] / filename).is_file():
                        app["repository"].set_output(job_id, filename=filename)
                else:
                    app["repository"].set_status(job_id, "failed", GENERIC_GENERATION_ERROR)
                updated = app["repository"].get_job(job_id)
                if updated:
                    await _broadcast_job(app, updated)
            continue
        for job_id in tuple(app["prompt_jobs"].values()):
            job = app["repository"].get_job(job_id)
            if job is not None:
                await _sync_job(app, job)


async def job_events(request: web.Request) -> web.StreamResponse:
    origin = request.headers.get("Origin")
    if origin:
        hosts = {request.host, request.headers.get("Host", ""), request.headers.get("X-Forwarded-Host", "")}
        allowed = {f"{scheme}://{host}" for scheme in ("http", "https") for host in hosts if host}
        public_origin = request.app.get("public_origin")
        if public_origin:
            allowed.add(public_origin)
        if origin.rstrip("/") not in allowed:
            return _error("허용되지 않은 출처입니다.", 403)
    socket = web.WebSocketResponse(heartbeat=30)
    await socket.prepare(request)
    request.app["event_sockets"][socket] = request["user"]
    try:
        async for _ in socket:
            pass
    finally:
        request.app["event_sockets"].pop(socket, None)
    return socket


async def health(request: web.Request) -> web.Response:
    if request.app.get("dispatch") is not None:
        return web.json_response({"app": "ok", "engine": "online" if request.app["dispatch"].workers() else "offline"})
    client: ComfyClient = request.app["comfy"]
    stats = await client.system_stats()
    return web.json_response({"app": "ok", "engine": "online" if stats is not None else "offline"})


def _public_user(user: User) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role}


async def _credentials(request: web.Request) -> tuple[str, str, str]:
    try:
        data = await request.json()
    except (ValueError, web.HTTPException):
        raise web.HTTPBadRequest(text="JSON 요청이 필요합니다.")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="입력값을 확인하세요.")
    return str(data.get("username", "")), str(data.get("display_name", "")), str(data.get("password", ""))


async def register(request: web.Request) -> web.Response:
    if not request.app["auth"].has_admin():
        return _error("먼저 관리자를 설정하세요.", 409)
    try:
        data = await request.json()
    except (ValueError, web.HTTPException):
        return _error("JSON 요청이 필요합니다.", 400)
    if not isinstance(data, dict):
        return _error("입력값을 확인하세요.", 400)

    username = str(data.get("username", "")).strip()
    display_name = str(data.get("display_name", "")).strip()
    password = str(data.get("password", ""))
    invite_code = str(data.get("invite_code", "")).strip()

    if not invite_code:
        return _error("초대 코드를 입력하세요.", 400)

    try:
        user = request.app["auth"].create_user(username, display_name, password, invite_code=invite_code)
    except ValueError as error:
        return _error(str(error), 400)

    token, csrf = request.app["auth"].create_session(user.id)
    response = web.json_response({"user": _public_user(user), "csrf_token": csrf, "status": "approved"}, status=201)
    secure = request.secure or request.app["secure_cookies"]
    response.set_cookie("yue2_session", token, max_age=SESSION_DAYS * 86400,
                        secure=secure, httponly=True, samesite="Strict", path="/")
    return response


async def setup_status(request: web.Request) -> web.Response:
    return web.json_response({"required": not request.app["auth"].has_admin()})


async def setup_admin(request: web.Request) -> web.Response:
    if request.app["auth"].has_admin():
        return _error("관리자가 이미 설정되었습니다.", 409)
    try:
        data = await request.json()
    except ValueError:
        return _error("입력값을 확인하세요.", 400)
    if not isinstance(data, dict) or not hmac.compare_digest(str(data.get("setup_code", "")), request.app["setup_token"]):
        return _error("설정 코드를 확인하세요.", 403)
    try:
        user = request.app["auth"].create_initial_admin(
            str(data.get("username", "")), str(data.get("display_name", "")), str(data.get("password", ""))
        )
    except ValueError as error:
        return _error(str(error), 400)
    token, csrf = request.app["auth"].create_session(user.id)
    response = web.json_response({"user": _public_user(user), "csrf_token": csrf}, status=201)
    response.set_cookie("yue2_session", token, max_age=SESSION_DAYS * 86400,
                        secure=request.secure or request.app["secure_cookies"], httponly=True, samesite="Strict", path="/")
    return response


async def login(request: web.Request) -> web.Response:
    username, _, password = await _credentials(request)
    user = request.app["auth"].authenticate(username, password)
    if user is None:
        return _error("아이디 또는 비밀번호를 확인하세요.", 401)
    if user.status != "approved":
        return _error("관리자 승인을 기다리는 계정입니다.", 403)
    token, csrf = request.app["auth"].create_session(user.id)
    response = web.json_response({"user": _public_user(user), "csrf_token": csrf})
    secure = request.secure or request.app["secure_cookies"]
    response.set_cookie("yue2_session", token, max_age=SESSION_DAYS * 86400,
                        secure=secure, httponly=True, samesite="Strict", path="/")
    return response


async def me(request: web.Request) -> web.Response:
    session = request.app["auth"].session(request.cookies.get("yue2_session", ""))
    if session is None:
        return web.json_response({"user": None, "csrf_token": ""})
    user, csrf_token = session
    return web.json_response({"user": _public_user(user), "csrf_token": csrf_token})


async def logout(request: web.Request) -> web.Response:
    request.app["auth"].delete_session(request.cookies.get("yue2_session", ""))
    response = web.json_response({"ok": True})
    response.del_cookie("yue2_session", path="/")
    return response


async def pending_users(request: web.Request) -> web.Response:
    return web.json_response([_public_user(user) for user in request.app["auth"].pending_users()])


async def review_user(request: web.Request) -> web.Response:
    try:
        user_id = int(request.match_info["user_id"])
        data = await request.json()
        status = data["status"]
    except (ValueError, KeyError, TypeError):
        return _error("입력값을 확인하세요.", 400)
    if status not in {"approved", "disabled"}:
        return _error("입력값을 확인하세요.", 400)
    if not request.app["auth"].set_status(user_id, status):
        return _error("계정을 찾을 수 없습니다.", 404)
    return web.json_response({"ok": True})


async def list_invites(request: web.Request) -> web.Response:
    invites = request.app["auth"].list_invite_codes()
    return web.json_response({"invites": invites})


async def create_invite(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except (ValueError, web.HTTPException):
        data = {}
    if not isinstance(data, dict):
        return _error("입력값을 확인하세요.", 400)

    code = str(data.get("code", "")).strip().upper()
    raw_max_uses = data.get("max_uses", 1)
    try:
        max_uses = int(raw_max_uses)
        if max_uses < 1:
            return _error("사용 횟수는 1 이상이어야 합니다.", 400)
    except (ValueError, TypeError):
        return _error("유효한 사용 횟수를 입력하세요.", 400)
    note = str(data.get("note", "")).strip()

    creator_id = request["user"].id
    try:
        new_code = request.app["auth"].create_invite_code(
            code=code or None,
            created_by=creator_id,
            max_uses=max_uses,
            note=note,
        )
    except ValueError as error:
        return _error(str(error), 400)

    return web.json_response({"ok": True, "code": new_code, "max_uses": max_uses}, status=201)


def _is_allowed_origin(request: web.Request, origin: str | None) -> bool:
    if not origin:
        return True
    origin_clean = origin.rstrip("/")

    # 1. 설정된 public_origin 확인
    public_origin = (request.app.get("public_origin") or "").rstrip("/")
    if public_origin and origin_clean == public_origin:
        return True

    try:
        origin_parts = urlsplit(origin_clean)
    except ValueError:
        return False
    origin_host = origin_parts.hostname or ""

    # 2. 로컬호스트 접근 허용
    if origin_host in {"localhost", "127.0.0.1", "::1"}:
        return True

    # 3. 요청 헤더 상의 호스트 후보들 확인 (Nginx 프록시 X-Forwarded-Host 및 Host 헤더 대응)
    forwarded_host = request.headers.get("X-Forwarded-Host", "").strip()
    host_header = request.headers.get("Host", "").strip()
    raw_hosts = {h for h in (forwarded_host, host_header, request.host) if h}

    candidate_hosts: set[str] = set()
    for h in raw_hosts:
        candidate_hosts.add(h)
        if ":" in h:
            candidate_hosts.add(h.split(":")[0])

    if origin_host in candidate_hosts:
        return True

    # 4. 프로토콜 포함 전체 origin 매칭
    for h in candidate_hosts:
        if origin_clean in {f"http://{h}", f"https://{h}"}:
            return True

    return False


@web.middleware
async def access_control(request: web.Request, handler):
    path = request.path
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("Origin")
        if origin and not _is_allowed_origin(request, origin):
            return _error("허용되지 않은 출처입니다.", 403)
        if request.headers.get("Sec-Fetch-Site") == "cross-site" and not _is_allowed_origin(request, origin):
            return _error("허용되지 않은 출처입니다.", 403)
    if not path.startswith("/api/") or path.startswith("/api/worker/") or path in {"/api/auth/register", "/api/auth/login", "/api/auth/setup-status", "/api/auth/setup", "/api/auth/me"}:
        return await handler(request)
    public_library_path = request.method in {"GET", "HEAD"} and (
        path in {"/api/library", "/api/library/discover", "/api/library/charts"}
        or re.fullmatch(r"/api/library/tracks/[^/]+", path)
        or (path != "/api/artists/mine" and re.fullmatch(r"/api/artists/[^/]+(?:/avatar|/banner)?", path))
        or re.fullmatch(r"/api/albums/[^/]+(?:/cover)?", path)
        or re.fullmatch(r"/api/tracks/[^/]+/(?:cover|audio|download)", path)
    )
    session = request.app["auth"].session(request.cookies.get("yue2_session", ""))
    if session is None:
        if public_library_path:
            return await handler(request)
        return _error("로그인이 필요합니다.", 401)
    request["user"], request["csrf_token"] = session
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("X-Yue2-CSRF", "")
        if not hmac.compare_digest(supplied, request["csrf_token"]):
            return _error("요청을 다시 시도하세요.", 403)
    if path.startswith("/api/admin/") and request["user"].role != "admin":
        return _error("관리자만 접근할 수 있습니다.", 403)
    return await handler(request)


async def create_generation(request: web.Request) -> web.Response:
    try:
        generation = await _parse_generation_request(request)
    except RequestInputError as error:
        return _error(str(error) or INPUT_ERROR, 400)

    if request.app.get("dispatch") is not None:
        return await _create_distributed_generation(request, generation)

    job_id = str(uuid.uuid4())
    upload_result: dict[str, Any] | None = None
    client: ComfyClient = request.app["comfy"]
    try:
        source_name = generation.source_filename
        source_subfolder = "yue2_uploads"
        source_type = "input"
        if generation.mode == "cover":
            assert generation.source_path is not None
            upload_result = await client.upload_audio(generation.source_path, generation.source_filename or "upload")
            source_name = str(upload_result.get("name") or generation.source_filename or "upload")
            source_subfolder = str(upload_result.get("subfolder") or "yue2_uploads")
            source_type = str(upload_result.get("type") or "input")
        workflow = build_workflow(
            job_id=job_id,
            mode=generation.mode,
            style=generation.style,
            lyrics=generation.lyrics,
            duration=generation.duration,
            seed=generation.seed,
            temperature=generation.temperature,
            top_p=generation.top_p,
            top_k=generation.top_k,
            repetition_penalty=generation.repetition_penalty,
            planning_enabled=generation.planning_enabled,
            plan_temperature=generation.plan_temperature,
            plan_top_p=generation.plan_top_p,
            plan_top_k=generation.plan_top_k,
            plan_repetition_penalty=generation.plan_repetition_penalty,
            penalty_window=generation.penalty_window,
            source_filename=source_name if generation.mode == "cover" else None,
            source_subfolder=source_subfolder,
            source_type=source_type,
        )
        prompt_id = await client.queue_prompt(workflow, request.app["client_id"])
    except Exception:
        return _error(OFFLINE_ERROR, 503)
    finally:
        if generation.source_path:
            try:
                os.unlink(generation.source_path)
            except OSError:
                pass

    repository: Repository = request.app["repository"]
    try:
        job = repository.create_job(
            job_id=job_id,
            prompt_id=prompt_id,
            mode=generation.mode,
            title=generation.title,
            style=generation.style,
            lyrics=generation.lyrics,
            seed=generation.seed,
            settings=generation.settings,
            source_filename=generation.source_filename,
            creator_id=request["user"].id,
            creator_name=f"{request['user'].display_name} (@{request['user'].username})",
        )
    except Exception:
        return _error("요청을 저장하지 못했습니다. 다시 시도해 주세요.", 500)
    request.app["prompt_jobs"][prompt_id] = job.id
    await _broadcast_job(request.app, job)
    return web.json_response(_public_job(job, client), status=202)


async def _create_distributed_generation(request: web.Request, generation: GenerationInput) -> web.Response:
    app = request.app
    job_id = str(uuid.uuid4())
    source_name = None
    if generation.source_path:
        source_name = job_id + Path(generation.source_filename or "source.mp3").suffix.lower()
        try:
            os.replace(generation.source_path, app["source_dir"] / source_name)
        except OSError:
            Path(generation.source_path).unlink(missing_ok=True)
            return _error(OFFLINE_ERROR, 500)
    try:
        job = app["repository"].create_job(
            job_id=job_id, prompt_id=None, mode=generation.mode, title=generation.title,
            style=generation.style, lyrics=generation.lyrics, seed=generation.seed,
            settings=generation.settings, source_filename=generation.source_filename,
            creator_id=request["user"].id,
            creator_name=f"{request['user'].display_name} (@{request['user'].username})",
        )
        app["dispatch"].enqueue(job_id, {
            "mode": generation.mode, "style": generation.style, "lyrics": generation.lyrics,
            "seed": generation.seed, "settings": generation.settings,
            "source_filename": generation.source_filename, "source_name": source_name,
        })
    except Exception:
        if source_name:
            (app["source_dir"] / source_name).unlink(missing_ok=True)
        try:
            app["repository"].set_status(job_id, "failed", GENERIC_GENERATION_ERROR)
        except Exception:
            pass
        return _error(OFFLINE_ERROR, 503)
    await _broadcast_job(app, job)
    return web.json_response(_public_job(job), status=202)


def _worker_identity(request: web.Request) -> str | None:
    worker_id = request.headers.get("X-Yue-Worker", "")
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    expected = request.app["worker_tokens"].get(worker_id)
    if not expected or not hmac.compare_digest(token, expected):
        return None
    return worker_id


def _remove_source(app: web.Application, job_id: str) -> None:
    try:
        uuid.UUID(job_id)
    except ValueError:
        return
    for path in app["source_dir"].glob(job_id + ".*"):
        path.unlink(missing_ok=True)


async def worker_claim(request: web.Request) -> web.Response:
    worker_id = _worker_identity(request)
    if worker_id is None:
        return _error("Unauthorized worker", 401)
    try:
        info = await request.json()
    except Exception:
        info = {}
    if not isinstance(info, dict):
        info = {}
    claimed = request.app["dispatch"].claim(worker_id, str(info.get("device") or ""), str(info.get("vram") or ""))
    if claimed is None:
        return web.json_response({"job": None})
    request.app["repository"].set_status(claimed["job_id"], "running")
    job = request.app["repository"].get_job(claimed["job_id"])
    if job:
        await _broadcast_job(request.app, job)
    claimed["source_url"] = f"/api/worker/jobs/{claimed['job_id']}/source" if claimed["payload"].get("source_name") else None
    return web.json_response({"job": claimed})


async def worker_source(request: web.Request) -> web.StreamResponse:
    worker_id = _worker_identity(request)
    if worker_id is None:
        return _error("Unauthorized worker", 401)
    job_id = request.match_info["job_id"]
    token = request.headers.get("X-Yue-Lease", "")
    if not request.app["dispatch"].heartbeat(job_id, worker_id, token):
        return _error("Expired lease", 409)
    path = next(request.app["source_dir"].glob(job_id + ".*"), None)
    if path is None or not path.is_file():
        return _error("Source missing", 404)
    return web.FileResponse(path)


async def worker_heartbeat(request: web.Request) -> web.Response:
    worker_id = _worker_identity(request)
    if worker_id is None:
        return _error("Unauthorized worker", 401)
    try:
        data = await request.json()
    except Exception:
        return _error("Invalid progress", 400)
    job_id = str(data.get("job_id") or "")
    token = str(data.get("lease_token") or "")
    progress = data.get("progress")
    if progress is not None and not isinstance(progress, dict):
        return _error("Invalid progress", 400)
    if not request.app["dispatch"].heartbeat(job_id, worker_id, token, progress):
        return _error("Expired lease", 409)
    if progress:
        request.app["pending_progress"][job_id] = progress
    return web.json_response({"ok": True})


async def worker_complete(request: web.Request) -> web.Response:
    worker_id = _worker_identity(request)
    if worker_id is None:
        return _error("Unauthorized worker", 401)
    job_id = request.match_info["job_id"]
    token = request.headers.get("X-Yue-Lease", "")
    if not request.app["dispatch"].heartbeat(job_id, worker_id, token):
        return _error("Expired lease", 409)
    filename = job_id + "_" + hashlib.sha256(token.encode()).hexdigest()[:16] + ".mp3"
    temporary = request.app["output_dir"] / (filename + "." + uuid.uuid4().hex + ".part")
    size = 0
    try:
        with temporary.open("wb") as output:
            async for chunk in request.content.iter_chunked(1024 * 1024):
                size += len(chunk)
                if size > 256 * 1024 * 1024:
                    return _error("Output too large", 413)
                output.write(chunk)
        if size < 1024:
            return _error("Empty output", 400)
        if not request.app["dispatch"].heartbeat(job_id, worker_id, token):
            return _error("Expired lease", 409)
        os.replace(temporary, request.app["output_dir"] / filename)
        if not request.app["dispatch"].finish(job_id, worker_id, token, "completed", filename):
            (request.app["output_dir"] / filename).unlink(missing_ok=True)
            return _error("Expired lease", 409)
        request.app["repository"].set_output(job_id, filename=filename)
        _remove_source(request.app, job_id)
        job = request.app["repository"].get_job(job_id)
        if job:
            await _broadcast_job(request.app, job)
        return web.json_response({"ok": True})
    finally:
        temporary.unlink(missing_ok=True)


async def worker_fail(request: web.Request) -> web.Response:
    worker_id = _worker_identity(request)
    if worker_id is None:
        return _error("Unauthorized worker", 401)
    job_id = request.match_info["job_id"]
    try:
        data = await request.json()
    except Exception:
        return _error("Invalid failure report", 400)
    token = str(data.get("lease_token") or "")
    if not request.app["dispatch"].finish(job_id, worker_id, token, "failed"):
        return _error("Expired lease", 409)
    request.app["repository"].set_status(job_id, "failed", GENERIC_GENERATION_ERROR)
    _remove_source(request.app, job_id)
    job = request.app["repository"].get_job(job_id)
    if job:
        await _broadcast_job(request.app, job)
    return web.json_response({"ok": True})


async def list_jobs(request: web.Request) -> web.Response:
    await _sync_all(request.app)
    raw_limit = request.query.get("limit", "20")
    raw_offset = request.query.get("offset", "0")
    try:
        limit = int(raw_limit)
        offset = int(raw_offset)
    except ValueError:
        return _error(INPUT_ERROR, 400)
    if limit < 1 or limit > 200:
        return _error(INPUT_ERROR, 400)
    if offset < 0:
        return _error(INPUT_ERROR, 400)
    repository: Repository = request.app["repository"]
    creator_id = request["user"].id
    include_legacy = request["user"].role == "admin"
    jobs = repository.list_latest(limit=limit, offset=offset, creator_id=creator_id, include_legacy=include_legacy)
    total = repository.count_jobs(creator_id=creator_id, include_legacy=include_legacy)
    has_more = (offset + len(jobs)) < total

    public_jobs = [_public_job(job, request.app["comfy"]) for job in jobs]

    if request.query.get("paged") in {"1", "true"}:
        return web.json_response({
            "items": public_jobs,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
        })

    return web.json_response(
        public_jobs,
        headers={
            "X-Total-Count": str(total),
            "X-Offset": str(offset),
            "X-Limit": str(limit),
            "X-Has-More": "true" if has_more else "false",
        },
    )


async def get_queue_status(request: web.Request) -> web.Response:
    await _sync_all(request.app)
    repository: Repository = request.app["repository"]
    client: ComfyClient = request.app["comfy"]
    current_user = request.get("user")
    current_user_id = current_user.id if current_user else None

    queue_data: dict[str, Any] = {}
    try:
        queue_func = getattr(client, "queue", None)
        if request.app.get("dispatch") is None and callable(queue_func):
            queue_data = await queue_func() or {}
    except Exception:
        queue_data = {}

    comfy_running = queue_data.get("queue_running") or []
    comfy_pending = queue_data.get("queue_pending") or []

    running_prompt_ids = set()
    for item in comfy_running:
        if isinstance(item, (list, tuple)) and len(item) > 1:
            running_prompt_ids.add(str(item[1]))

    pending_prompt_ids: list[str] = []
    for item in comfy_pending:
        if isinstance(item, (list, tuple)) and len(item) > 1:
            pending_prompt_ids.append(str(item[1]))

    active_jobs = repository.list_nonterminal()
    running_list: list[dict[str, Any]] = []
    pending_list: list[dict[str, Any]] = []

    for job in active_jobs:
        if not _may_manage(job, current_user):
            continue
        pub = _public_job(job, client)
        pub["is_mine"] = bool(current_user_id and job.creator_id == current_user_id)
        if job.status == "running" or (job.prompt_id and job.prompt_id in running_prompt_ids):
            running_list.append(pub)
        else:
            pending_list.append(pub)

    def pending_sort_key(item: dict[str, Any]) -> int:
        pid = item.get("prompt_id")
        if pid and pid in pending_prompt_ids:
            return pending_prompt_ids.index(pid)
        return 999999

    pending_list.sort(key=pending_sort_key)
    for idx, item in enumerate(pending_list, start=1):
        item["position"] = idx

    system_stats = None
    engine_status = "offline"
    try:
        stats_func = getattr(client, "system_stats", None)
        if request.app.get("dispatch") is None and callable(stats_func):
            system_stats = await stats_func()
            if system_stats is not None:
                engine_status = "busy" if (running_list or pending_list) else "idle"
    except Exception:
        system_stats = None

    device_name = ""
    vram_summary = ""
    if isinstance(system_stats, dict):
        devices = system_stats.get("devices") or []
        if isinstance(devices, list) and devices:
            dev = devices[0]
            if isinstance(dev, dict):
                device_name = str(dev.get("name") or "")
                free = dev.get("vram_free")
                total = dev.get("vram_total")
                if free is not None and total is not None:
                    vram_summary = f"{round(free / (1024**3), 1)}GB / {round(total / (1024**3), 1)}GB"

    workers = request.app["dispatch"].workers() if request.app.get("dispatch") is not None else []
    if workers:
        engine_status = "busy" if running_list else "idle"
        device_name = workers[0]["device"]
        vram_summary = workers[0]["vram"]

    recent_jobs = [
        _public_job(j, client)
        for j in repository.list_latest(6, creator_id=current_user_id, include_legacy=current_user.role == "admin")
        if j.status in {"completed", "failed", "cancelled"}
    ]

    return web.json_response({
        "engine": {
            "status": engine_status,
            "device": device_name,
            "vram": vram_summary,
        },
        "summary": {
            "running_count": len(running_list),
            "pending_count": len(pending_list),
            "total_active": len(running_list) + len(pending_list),
            "is_busy": len(running_list) > 0 or len(pending_list) > 0,
        },
        "running": running_list,
        "pending": pending_list,
        "recent": recent_jobs,
    })


async def get_job(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    job = repository.get_job(request.match_info["job_id"])
    if job is None or not _may_read(job, request["user"]):
        return _error("작업을 찾을 수 없습니다.", 404)
    job = await _sync_job(request.app, job)
    return web.json_response(_public_job(job, request.app["comfy"]) if _may_manage(job, request["user"]) else _public_library_job(job, repository))


async def library(request: web.Request) -> web.Response:
    await _sync_all(request.app)
    mode = request.query.get("mode")
    if mode and mode not in {"original", "cover"}:
        return _error(INPUT_ERROR, 400)
    raw_limit = request.query.get("limit", "100")
    try:
        limit = int(raw_limit)
    except ValueError:
        return _error(INPUT_ERROR, 400)
    if limit < 1 or limit > 100:
        return _error(INPUT_ERROR, 400)
    repository: Repository = request.app["repository"]
    jobs = repository.list_library(request.query.get("q", ""), mode, limit)
    return web.json_response([_public_library_job(job, repository) for job in jobs])


async def publish_track(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    job = repository.get_job(request.match_info["job_id"])
    if job is None or not _may_manage(job, request["user"]):
        return _error("작업을 찾을 수 없습니다.", 404)
    job = await _sync_job(request.app, job)
    if job.status != "completed" or not job.output_filename:
        return _error("완료된 음악만 공개할 수 있습니다.", 409)
    try:
        texts, images = await _cms_form(request, {"title", "album_id", "artist_id"}, {"cover"})
    except ValueError as error:
        return _error(str(error), 400)
    title = texts.get("title", "")
    album_id = texts.get("album_id") or None
    try:
        artist_id = int(texts.get("artist_id") or job.artist_id or request["user"].id)
    except ValueError:
        return _error("내 아티스트를 선택해 주세요.", 400)
    artist = repository.get_artist(artist_id)
    if artist is None and artist_id == request["user"].id:
        artist = repository.save_artist(artist_id, request["user"].display_name, "", None, None)
    if artist is None or artist["user_id"] != request["user"].id:
        return _error("내 아티스트를 선택해 주세요.", 400)
    if not title or len(title) > 120:
        return _error("제목은 1~120자로 입력해 주세요.", 400)
    if album_id:
        album = repository.get_album(album_id)
        if album is None or album["owner_id"] != request["user"].id or album["artist_id"] != artist_id:
            return _error("내 앨범을 선택해 주세요.", 400)
    cover_name: str | None = None
    if images.get("cover"):
        try:
            cover_name = _store_cms_image(request.app, images["cover"], 1200)
        except ValueError as error:
            return _error(str(error), 400)
    updated = repository.publish(job.id, request["user"].id, title, cover_name,
                                 album_id=album_id, artist_id=artist_id,
                                 allow_legacy=request["user"].role == "admin")
    if updated is None or updated.published_at is None:
        if cover_name:
            (request.app["cover_dir"] / cover_name).unlink(missing_ok=True)
        return _error("음악을 공개하지 못했습니다.", 409)
    if cover_name and job.cover_filename and job.cover_filename != cover_name:
        (request.app["cover_dir"] / job.cover_filename).unlink(missing_ok=True)
    return web.json_response(_public_library_job(updated, repository))


async def unpublish_track(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    job = repository.get_job(request.match_info["job_id"])
    if job is None or not _may_manage(job, request["user"]):
        return _error("작업을 찾을 수 없습니다.", 404)
    if not repository.unpublish(job.id, request["user"].id, allow_legacy=request["user"].role == "admin"):
        return _error("공개된 음악이 아닙니다.", 409)
    return web.json_response(_public_job(repository.get_job(job.id)))


async def track_cover(request: web.Request) -> web.StreamResponse:
    job = request.app["repository"].get_job(request.match_info["job_id"])
    if job is None or not job.published_at or job.status != "completed" or not job.cover_filename:
        return _error("표지를 찾을 수 없습니다.", 404)
    path = request.app["cover_dir"] / job.cover_filename
    if not path.is_file():
        return _error("표지를 찾을 수 없습니다.", 404)
    return web.FileResponse(path, headers={"Content-Type": "image/jpeg"})


async def track_recipe(request: web.Request) -> web.Response:
    job = request.app["repository"].get_job(request.match_info["job_id"])
    if job is None or not job.published_at or job.status != "completed" or not job.output_filename:
        return _error("공개된 음악을 찾을 수 없습니다.", 404)
    if request.app.get("dispatch") is not None:
        path = request.app["output_dir"] / Path(job.output_filename).name
        if not path.is_file():
            return _error(OFFLINE_ERROR, 502)
        with path.open("rb") as audio:
            data = audio.read(4 * 1024 * 1024)
        graph = prompt_from_mp3(data)
        recipe = recipe_from_prompt(graph) if graph else None
        if recipe is None:
            return _error("Recipe not found", 422)
        recipe["title"] = job.published_title or job.title or ""
        return web.json_response(recipe)
    try:
        upstream = await request.app["comfy"].open_view(
            job.output_filename, job.output_subfolder, job.output_type,
            range_header="bytes=0-4194303",
        )
        try:
            data = await upstream.content.read(4 * 1024 * 1024)
        finally:
            upstream.release()
    except Exception:
        return _error(OFFLINE_ERROR, 502)
    graph = prompt_from_mp3(data)
    recipe = recipe_from_prompt(graph) if graph else None
    if recipe is None:
        return _error("이 파일에서 생성 정보를 읽을 수 없습니다.", 422)
    recipe["title"] = job.published_title or job.title or ""
    return web.json_response(recipe)


def _store_cms_image(app: web.Application, data: bytes, max_side: int = 1600) -> str:
    if not data or len(data) > 5 * 1024 * 1024:
        raise ValueError("이미지는 5MB 이하여야 합니다.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or image.width > 4000 or image.height > 4000:
                raise ValueError("JPG, PNG, WebP 이미지를 선택해 주세요.")
            image.load()
            layer = ImageOps.exif_transpose(image).convert("RGBA")
            background = Image.new("RGBA", layer.size, "#292332")
            clean = Image.alpha_composite(background, layer).convert("RGB")
            clean.thumbnail((max_side, max_side))
            name = f"{uuid.uuid4().hex}.jpg"
            clean.save(app["cover_dir"] / name, "JPEG", quality=90)
            return name
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("이미지를 읽을 수 없습니다.") from error


async def _cms_form(request: web.Request, text_fields: set[str], image_fields: set[str]) -> tuple[dict[str, str], dict[str, bytes]]:
    if not request.content_type.startswith("multipart/"):
        raise ValueError(INPUT_ERROR)
    reader = await request.multipart()
    texts: dict[str, str] = {}
    images: dict[str, bytes] = {}
    async for part in reader:
        if part.name in text_fields:
            texts[part.name] = (await part.text()).strip()
        elif part.name in image_fields:
            chunks: list[bytes] = []
            total = 0
            while chunk := await part.read_chunk():
                total += len(chunk)
                if total > 5 * 1024 * 1024:
                    raise ValueError("이미지는 5MB 이하여야 합니다.")
                chunks.append(chunk)
            images[part.name] = b"".join(chunks)
    return texts, images


async def library_discover(request: web.Request) -> web.Response:
    await _sync_all(request.app)
    repository: Repository = request.app["repository"]
    latest = repository.list_library(limit=18)
    albums = repository.list_albums(limit=12)
    artists = repository.list_artists(limit=12)
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    this_week = [job for job in latest if job.published_at and datetime.fromisoformat(job.published_at) >= week_start]
    return web.json_response({
        "new_releases": [_public_library_job(job, repository) for job in latest[:12]],
        "this_week": [_public_library_job(job, repository) for job in this_week[:12]],
        "charts": [_public_library_job(job, repository) for job in repository.list_charts(12)],
        "albums": [_public_album(album, repository) for album in albums],
        "artists": [_public_artist(artist["artist_id"], repository, (artist["creator_name"] or "아티스트").split(" (@")[0]) for artist in artists],
    })


async def library_charts(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    return web.json_response([_public_library_job(job, repository) for job in repository.list_charts()])


async def single_page(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    job = repository.get_job(request.match_info["job_id"])
    if job is None or not job.published_at or job.status != "completed":
        return _error("공개된 음악을 찾을 수 없습니다.", 404)
    return web.json_response(_public_library_job(job, repository))


async def artist_page(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    try:
        artist_id = int(request.match_info["artist_id"])
    except ValueError:
        return _error(INPUT_ERROR, 400)
    tracks = repository.list_artist_tracks(artist_id)
    profile = repository.get_artist(artist_id)
    user = request.get("user")
    is_mine = bool(profile and user and profile["user_id"] == user.id)
    if not tracks and not is_mine:
        return _error("아티스트를 찾을 수 없습니다.", 404)
    albums = [album for album in repository.list_albums(owner_id=profile["user_id"] if profile else None)
              if album["artist_id"] == artist_id]
    return web.json_response({
        "artist": _public_artist(artist_id, repository, user.display_name if user else "아티스트"),
        "albums": [_public_album(album, repository) for album in albums],
        "tracks": [_public_library_job(job, repository) for job in tracks],
        "is_mine": is_mine,
    })


async def save_artist(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    raw_id = request.match_info.get("artist_id")
    creating = request.path == "/api/artists"
    try:
        artist_id = None if creating else int(raw_id) if raw_id is not None else request["user"].id
    except ValueError:
        return _error(INPUT_ERROR, 400)
    old = repository.get_artist(artist_id) if artist_id is not None else None
    if artist_id is not None and artist_id != request["user"].id and (
            old is None or old["user_id"] != request["user"].id):
        return _error("아티스트를 찾을 수 없습니다.", 404)
    try:
        texts, images = await _cms_form(request, {"name", "bio"}, {"avatar", "banner"})
        name = texts.get("name", "").strip()
        bio = texts.get("bio", "")
        if not 1 <= len(name) <= 60 or len(bio) > 1000:
            raise ValueError("아티스트 이름은 1~60자, 소개는 1,000자 이내로 입력해 주세요.")
        avatar = _store_cms_image(request.app, images["avatar"], 800) if images.get("avatar") else None
        banner = _store_cms_image(request.app, images["banner"], 1800) if images.get("banner") else None
    except ValueError as error:
        return _error(str(error), 400)
    if creating:
        saved = repository.create_artist(request["user"].id, name, bio, avatar, banner)
    else:
        saved = repository.save_artist(request["user"].id, name, bio, avatar, banner, artist_id=artist_id)
    for field, replacement in (("avatar_filename", avatar), ("banner_filename", banner)):
        if old and old[field] and replacement:
            (request.app["cover_dir"] / old[field]).unlink(missing_ok=True)
    return web.json_response(_public_artist(saved["id"], repository, request["user"].display_name),
                             status=201 if creating else 200)


async def my_artists(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    user = request["user"]
    if repository.get_artist(user.id) is None:
        previous = repository.list_artist_tracks(user.id, 1)
        name = (previous[0].creator_name or user.display_name).split(" (@")[0] if previous else user.display_name
        repository.save_artist(user.id, name, "", None, None)
    return web.json_response([_public_artist(profile["id"], repository)
                              for profile in repository.list_owned_artists(user.id)])


async def artist_image(request: web.Request) -> web.StreamResponse:
    repository: Repository = request.app["repository"]
    try:
        artist_id = int(request.match_info["artist_id"])
    except ValueError:
        return _error(INPUT_ERROR, 400)
    profile = repository.get_artist(artist_id)
    tracks = repository.list_artist_tracks(artist_id, 1)
    field = "avatar_filename" if request.match_info["kind"] == "avatar" else "banner_filename"
    user = request.get("user")
    if not profile or not profile[field] or (not tracks and (not user or profile["user_id"] != user.id)):
        return _error("이미지를 찾을 수 없습니다.", 404)
    path = request.app["cover_dir"] / profile[field]
    if not path.is_file():
        return _error("이미지를 찾을 수 없습니다.", 404)
    return web.FileResponse(path, headers={"Content-Type": "image/jpeg"})


async def list_albums(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    mine = request.query.get("mine") == "1"
    albums = repository.list_albums(owner_id=request["user"].id if mine else None, public_only=not mine)
    return web.json_response([_public_album(album, repository) for album in albums])


async def create_album(request: web.Request) -> web.Response:
    try:
        texts, images = await _cms_form(request, {"title", "description", "artist_id"}, {"cover"})
        title, description = texts.get("title", ""), texts.get("description", "")
        artist_id = int(texts.get("artist_id") or request["user"].id)
        if not 1 <= len(title) <= 120 or len(description) > 1000:
            raise ValueError("앨범 제목은 1~120자, 설명은 1,000자 이내로 입력해 주세요.")
        cover = _store_cms_image(request.app, images["cover"]) if images.get("cover") else None
    except ValueError as error:
        return _error(str(error), 400)
    repository: Repository = request.app["repository"]
    artist = repository.get_artist(artist_id)
    if artist is None and artist_id == request["user"].id:
        artist = repository.save_artist(artist_id, request["user"].display_name, "", None, None)
    if artist is None or artist["user_id"] != request["user"].id:
        if cover:
            (request.app["cover_dir"] / cover).unlink(missing_ok=True)
        return _error("내 아티스트를 선택해 주세요.", 400)
    album = repository.create_album(str(uuid.uuid4()), request["user"].id, title, description, cover,
                                    artist_id=artist_id)
    return web.json_response(_public_album(album, repository), status=201)


async def update_album(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    old = repository.get_album(request.match_info["album_id"])
    if old is None or old["owner_id"] != request["user"].id:
        return _error("앨범을 찾을 수 없습니다.", 404)
    try:
        texts, images = await _cms_form(request, {"title", "description"}, {"cover"})
        title, description = texts.get("title", ""), texts.get("description", "")
        if not 1 <= len(title) <= 120 or len(description) > 1000:
            raise ValueError("앨범 제목은 1~120자, 설명은 1,000자 이내로 입력해 주세요.")
        cover = _store_cms_image(request.app, images["cover"]) if images.get("cover") else None
    except ValueError as error:
        return _error(str(error), 400)
    album = repository.update_album(old["id"], request["user"].id, title, description, cover)
    if cover and old["cover_filename"]:
        (request.app["cover_dir"] / old["cover_filename"]).unlink(missing_ok=True)
    return web.json_response(_public_album(album, repository))


async def album_page(request: web.Request) -> web.Response:
    repository: Repository = request.app["repository"]
    album = repository.get_album(request.match_info["album_id"])
    user = request.get("user")
    if album is None or (album["track_count"] == 0 and (not user or album["owner_id"] != user.id)):
        return _error("앨범을 찾을 수 없습니다.", 404)
    return web.json_response({
        "album": _public_album(album, repository),
        "tracks": [_public_library_job(job, repository) for job in repository.list_album_tracks(album["id"])],
        "is_mine": bool(user and album["owner_id"] == user.id),
    })


async def album_cover(request: web.Request) -> web.StreamResponse:
    album = request.app["repository"].get_album(request.match_info["album_id"])
    user = request.get("user")
    if album is None or not album["cover_filename"] or (album["track_count"] == 0 and (not user or album["owner_id"] != user.id)):
        return _error("표지를 찾을 수 없습니다.", 404)
    path = request.app["cover_dir"] / album["cover_filename"]
    if not path.is_file():
        return _error("표지를 찾을 수 없습니다.", 404)
    return web.FileResponse(path, headers={"Content-Type": "image/jpeg"})


async def record_play(request: web.Request) -> web.Response:
    plays = request.app["repository"].increment_play(request.match_info["job_id"])
    if plays is None:
        return _error("공개된 음악을 찾을 수 없습니다.", 404)
    return web.json_response({"play_count": plays})


def _sanitize_download_name(title: str | None) -> str:
    value = (title or "track").strip()
    value = _SAFE_FILENAME_RE.sub("_", value).strip(" .") or "track"
    return f"{value}.mp3"


async def _track_response(request: web.Request, download: bool) -> web.StreamResponse:
    repository: Repository = request.app["repository"]
    job = repository.get_job(request.match_info["job_id"])
    if job is None or not _may_read(job, request.get("user")):
        return _error("트랙을 찾을 수 없습니다.", 404)
    job = await _sync_job(request.app, job)
    if job.status != "completed" or not job.output_filename:
        return _error("트랙을 찾을 수 없습니다.", 404)
    if request.app.get("dispatch") is not None:
        path = request.app["output_dir"] / Path(job.output_filename).name
        if not path.is_file():
            return _error("Audio missing", 404)
        headers = {"Content-Type": "audio/mpeg"}
        if download:
            download_name = _sanitize_download_name(job.published_title if job.published_at else job.title)
            ascii_stem = download_name[:-4].encode("ascii", "ignore").decode("ascii").strip(" ._")
            headers["Content-Disposition"] = (
                f'attachment; filename="{ascii_stem or "track"}.mp3"; filename*=UTF-8\'\'{quote(download_name)}'
            )
        return web.FileResponse(path, headers=headers)
    client: ComfyClient = request.app["comfy"]
    try:
        upstream = await client.open_view(
            job.output_filename, job.output_subfolder, job.output_type,
            range_header=request.headers.get("Range"),
        )
    except ComfyResponseError as error:
        if error.status == 416:
            return _error("재생 범위를 벗어났습니다.", 416)
        return _error("트랙을 찾을 수 없습니다." if error.status == 404 else OFFLINE_ERROR, 404 if error.status == 404 else 502)
    except Exception:
        return _error(OFFLINE_ERROR, 502)

    content_type = mimetypes.guess_type(job.output_filename, strict=False)[0] or upstream.headers.get(
        "Content-Type", "audio/mpeg"
    )
    headers: dict[str, str] = {
        "Content-Type": content_type,
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length",
    }
    if upstream.headers.get("Content-Length"):
        headers["Content-Length"] = upstream.headers["Content-Length"]
    for name in ("Accept-Ranges", "Content-Range"):
        if upstream.headers.get(name):
            headers[name] = upstream.headers[name]
    if download:
        download_name = _sanitize_download_name(job.published_title if job.published_at else job.title)
        ascii_stem = download_name[:-4].encode("ascii", "ignore").decode("ascii").strip(" ._")
        ascii_name = f"{ascii_stem or 'track'}.mp3"
        headers["Content-Disposition"] = (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(download_name)}'
        )
    response = web.StreamResponse(status=upstream.status, headers=headers)
    try:
        await response.prepare(request)
        async for chunk in upstream.content.iter_chunked(1024 * 1024):
            await response.write(chunk)
        await response.write_eof()
    except asyncio.CancelledError:
        raise
    except ConnectionError:
        # The client may disconnect while a long generated track is streaming.
        pass
    finally:
        upstream.release()
    return response


async def track_audio(request: web.Request) -> web.StreamResponse:
    return await _track_response(request, False)


async def track_download(request: web.Request) -> web.StreamResponse:
    return await _track_response(request, True)


async def static_fallback(request: web.Request) -> web.StreamResponse:
    if request.path == "/api" or request.path.startswith("/api/"):
        raise web.HTTPNotFound()
    root = Path(request.app["static_dir"])
    try:
        root = root.resolve()
    except OSError:
        raise web.HTTPNotFound()
    relative = request.match_info.get("path", "")
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise web.HTTPNotFound()
    if target.is_file():
        return web.FileResponse(target)
    index = root / "index.html"
    accepts_html = "text/html" in request.headers.get("Accept", "")
    has_extension = bool(Path(relative).suffix)
    if index.is_file() and (not relative or accepts_html or not has_extension):
        return web.FileResponse(index)
    raise web.HTTPNotFound()


def create_app(
    *,
    db_path: str | Path | None = None,
    comfy_url: str = "http://127.0.0.1:8188",
    repository: Repository | None = None,
    comfy_client: ComfyClient | None = None,
    static_dir: str | Path | None = None,
    auth_store: AuthStore | None = None,
    setup_token: str | None = None,
    dispatch_store: DispatchStore | None = None,
) -> web.Application:
    app = web.Application(client_max_size=MAX_UPLOAD_BYTES + 4 * 1024 * 1024, middlewares=[access_control])
    database_url = os.environ.get("YUE2_DATABASE_URL")
    if database_url and repository is None:
        from .pg_store import PostgresRepository

        repository = PostgresRepository(database_url, Path(__file__).parent / "data")
    if database_url and auth_store is None:
        from .pg_store import PostgresAuthStore

        auth_store = PostgresAuthStore(database_url, Path(__file__).parent / "data" / "yue2.sqlite3")
    app["repository"] = repository or Repository(db_path)
    app["auth"] = auth_store or AuthStore(app["repository"].path)
    app["setup_token"] = setup_token or os.environ.get("YUE2_SETUP_TOKEN") or secrets.token_urlsafe(24)
    app["secure_cookies"] = os.environ.get("YUE2_SECURE_COOKIES") == "1"
    app["public_origin"] = os.environ.get("YUE2_PUBLIC_ORIGIN", "").rstrip("/")
    app["comfy"] = comfy_client or ComfyClient(comfy_url)
    dispatch_dsn = os.environ.get("YUE2_DISPATCH_DSN")
    app["dispatch"] = dispatch_store or (DispatchStore(dispatch_dsn) if dispatch_dsn else None)
    app["worker_tokens"] = json.loads(os.environ.get("YUE2_WORKER_TOKENS", "{}"))
    app["client_id"] = str(uuid.uuid4())
    app["event_sockets"] = {}
    app["pending_progress"] = {}
    app["last_progress"] = {}
    app["prompt_jobs"] = {}
    app["finish_tasks"] = {}
    app["static_dir"] = Path(static_dir) if static_dir is not None else Path(__file__).parent / "static"
    app["cover_dir"] = app["repository"].path.parent / "covers"
    app["cover_dir"].mkdir(parents=True, exist_ok=True)
    app["source_dir"] = app["repository"].path.parent / "sources"
    app["output_dir"] = app["repository"].path.parent / "outputs"
    app["source_dir"].mkdir(parents=True, exist_ok=True)
    app["output_dir"].mkdir(parents=True, exist_ok=True)

    app.router.add_get("/api/health", health)
    if app["dispatch"] is not None:
        app.router.add_post("/api/worker/claim", worker_claim)
        app.router.add_get("/api/worker/jobs/{job_id}/source", worker_source)
        app.router.add_post("/api/worker/heartbeat", worker_heartbeat)
        app.router.add_post("/api/worker/jobs/{job_id}/complete", worker_complete)
        app.router.add_post("/api/worker/jobs/{job_id}/fail", worker_fail)
    app.router.add_post("/api/auth/register", register)
    app.router.add_get("/api/auth/setup-status", setup_status)
    app.router.add_post("/api/auth/setup", setup_admin)
    app.router.add_post("/api/auth/login", login)
    app.router.add_get("/api/auth/me", me)
    app.router.add_post("/api/auth/logout", logout)
    app.router.add_get("/api/admin/pending", pending_users)
    app.router.add_post("/api/admin/users/{user_id}", review_user)
    app.router.add_get("/api/admin/invites", list_invites)
    app.router.add_post("/api/admin/invites", create_invite)
    app.router.add_post("/api/generations", create_generation)
    app.router.add_get("/api/jobs", list_jobs)
    app.router.add_get("/api/events", job_events)
    app.router.add_get("/api/jobs/{job_id}", get_job)
    app.router.add_get("/api/queue", get_queue_status)
    app.router.add_get("/api/library", library)
    app.router.add_get("/api/library/discover", library_discover)
    app.router.add_get("/api/library/charts", library_charts)
    app.router.add_get("/api/library/tracks/{job_id}", single_page)
    app.router.add_get("/api/artists/mine", my_artists)
    app.router.add_post("/api/artists", save_artist)
    app.router.add_post("/api/artists/me", save_artist)
    app.router.add_post("/api/artists/{artist_id}", save_artist)
    app.router.add_get("/api/artists/{artist_id}", artist_page)
    app.router.add_get("/api/artists/{artist_id}/{kind:avatar|banner}", artist_image)
    app.router.add_get("/api/albums", list_albums)
    app.router.add_post("/api/albums", create_album)
    app.router.add_get("/api/albums/{album_id}", album_page)
    app.router.add_post("/api/albums/{album_id}", update_album)
    app.router.add_get("/api/albums/{album_id}/cover", album_cover)
    app.router.add_post("/api/tracks/{job_id}/publish", publish_track)
    app.router.add_delete("/api/tracks/{job_id}/publish", unpublish_track)
    app.router.add_get("/api/tracks/{job_id}/cover", track_cover)
    app.router.add_get("/api/tracks/{job_id}/recipe", track_recipe)
    app.router.add_post("/api/tracks/{job_id}/play", record_play)
    app.router.add_get("/api/tracks/{job_id}/audio", track_audio)
    app.router.add_get("/api/tracks/{job_id}/download", track_download)
    app.router.add_static("/static/", path=app["static_dir"], name="static")
    app.router.add_get("/{path:.*}", static_fallback)

    async def startup(application: web.Application) -> None:
        client = application["comfy"]
        if application.get("dispatch") is not None:
            application["progress_flush_task"] = asyncio.create_task(_flush_progress(application))
            application["reconcile_task"] = asyncio.create_task(_reconcile_jobs(application))
            return
        application["prompt_jobs"].update(
            {job.prompt_id: job.id for job in application["repository"].list_nonterminal() if job.prompt_id}
        )
        if isinstance(client, ComfyClient):
            client.event_listener = lambda event: _on_comfy_event(application, event)
        start = getattr(client, "start", None)
        if start is not None:
            await start()
        watch_progress = getattr(client, "watch_progress", None)
        if watch_progress is not None:
            application["progress_task"] = asyncio.create_task(watch_progress(application["client_id"]))
        application["progress_flush_task"] = asyncio.create_task(_flush_progress(application))
        application["reconcile_task"] = asyncio.create_task(_reconcile_jobs(application))

    async def cleanup(application: web.Application) -> None:
        for task_name in ("progress_task", "progress_flush_task", "reconcile_task"):
            progress_task = application.get(task_name)
            if progress_task is None:
                continue
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
        finish_tasks = tuple(application["finish_tasks"].values())
        for task in finish_tasks:
            task.cancel()
        if finish_tasks:
            await asyncio.gather(*finish_tasks, return_exceptions=True)
        sockets = tuple(application["event_sockets"])
        if sockets:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*(socket.close() for socket in sockets), return_exceptions=True),
                    timeout=5,
                )
            except asyncio.TimeoutError:
                pass
        client = application["comfy"]
        if isinstance(client, ComfyClient):
            client.event_listener = None
        close = getattr(client, "close", None)
        if close is not None:
            await close()
        repository_obj = application["repository"]
        repository_close = getattr(repository_obj, "close", None)
        if repository_close is not None:
            repository_close()

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


def main() -> None:
    app = create_app()
    if not app["auth"].has_admin():
        print(f"\nYUE STUDIO 최초 관리자 설정 코드: {app['setup_token']}\n", flush=True)
    web.run_app(app, host=HOST, port=PORT, shutdown_timeout=5)


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["HOST", "PORT", "create_app", "main"]
