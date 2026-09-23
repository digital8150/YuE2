"""Local aiohttp web server for the YuE2 music generation app."""

from __future__ import annotations

import asyncio
import math
import mimetypes
import os
import hmac
import secrets
import random
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from aiohttp import web

from .auth import AuthStore, SESSION_DAYS, User
from .comfy_client import (
    GENERIC_GENERATION_ERROR,
    ComfyClient,
    ComfyResponseError,
)
from .repository import Job, Repository
from .workflow_builder import build_workflow


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
        "error": job.error,
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


async def _sync_job(app: web.Application, job: Job) -> Job:
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
            repository.set_status(job.id, status)
    except Exception:
        return job
    return repository.get_job(job.id) or job


async def _sync_all(app: web.Application) -> None:
    repository: Repository = app["repository"]
    for job in repository.list_nonterminal():
        await _sync_job(app, job)


async def health(request: web.Request) -> web.Response:
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
    return web.json_response({"user": _public_user(request["user"]), "csrf_token": request["csrf_token"]})


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
    if not path.startswith("/api/") or path in {"/api/auth/register", "/api/auth/login", "/api/auth/setup-status", "/api/auth/setup"}:
        return await handler(request)
    session = request.app["auth"].session(request.cookies.get("yue2_session", ""))
    if session is None:
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
    return web.json_response(_public_job(job, client), status=202)


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
    jobs = repository.list_latest(limit=limit, offset=offset)
    total = repository.count_jobs()
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
        if callable(queue_func):
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
        if callable(stats_func):
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

    recent_jobs = [
        _public_job(j, client)
        for j in repository.list_latest(6)
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
    if job is None:
        return _error("작업을 찾을 수 없습니다.", 404)
    job = await _sync_job(request.app, job)
    return web.json_response(_public_job(job, request.app["comfy"]))


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
    return web.json_response([_public_job(job) for job in jobs])


def _sanitize_download_name(title: str | None) -> str:
    value = (title or "track").strip()
    value = _SAFE_FILENAME_RE.sub("_", value).strip(" .") or "track"
    return f"{value}.mp3"


async def _track_response(request: web.Request, download: bool) -> web.StreamResponse:
    repository: Repository = request.app["repository"]
    job = repository.get_job(request.match_info["job_id"])
    if job is None:
        return _error("트랙을 찾을 수 없습니다.", 404)
    job = await _sync_job(request.app, job)
    if job.status != "completed" or not job.output_filename:
        return _error("트랙을 찾을 수 없습니다.", 404)
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
        download_name = _sanitize_download_name(job.title)
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
) -> web.Application:
    app = web.Application(client_max_size=MAX_UPLOAD_BYTES + 4 * 1024 * 1024, middlewares=[access_control])
    app["repository"] = repository or Repository(db_path)
    app["auth"] = auth_store or AuthStore(app["repository"].path)
    app["setup_token"] = setup_token or os.environ.get("YUE2_SETUP_TOKEN") or secrets.token_urlsafe(24)
    app["secure_cookies"] = os.environ.get("YUE2_SECURE_COOKIES") == "1"
    app["public_origin"] = os.environ.get("YUE2_PUBLIC_ORIGIN", "").rstrip("/")
    app["comfy"] = comfy_client or ComfyClient(comfy_url)
    app["client_id"] = str(uuid.uuid4())
    app["static_dir"] = Path(static_dir) if static_dir is not None else Path(__file__).parent / "static"

    app.router.add_get("/api/health", health)
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
    app.router.add_get("/api/jobs/{job_id}", get_job)
    app.router.add_get("/api/queue", get_queue_status)
    app.router.add_get("/api/library", library)
    app.router.add_get("/api/tracks/{job_id}/audio", track_audio)
    app.router.add_get("/api/tracks/{job_id}/download", track_download)
    app.router.add_static("/static/", path=app["static_dir"], name="static")
    app.router.add_get("/{path:.*}", static_fallback)

    async def startup(application: web.Application) -> None:
        client = application["comfy"]
        start = getattr(client, "start", None)
        if start is not None:
            await start()
        watch_progress = getattr(client, "watch_progress", None)
        if watch_progress is not None:
            application["progress_task"] = asyncio.create_task(watch_progress(application["client_id"]))

    async def cleanup(application: web.Application) -> None:
        progress_task = application.get("progress_task")
        if progress_task is not None:
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
        client = application["comfy"]
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
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["HOST", "PORT", "create_app", "main"]
