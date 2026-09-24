"""Minimal asynchronous client for the local ComfyUI HTTP API."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, BinaryIO

import aiohttp


GENERIC_GENERATION_ERROR = "생성 중 문제가 발생했습니다. 다시 시도해 주세요."


class ComfyError(RuntimeError):
    """Base class for backend failures hidden from API responses."""


class ComfyUnavailable(ComfyError):
    """The local ComfyUI endpoint could not be reached or returned bad data."""


class ComfyResponseError(ComfyError):
    """A ComfyUI endpoint returned a non-success HTTP status."""

    def __init__(self, status: int) -> None:
        super().__init__("ComfyUI request failed")
        self.status = int(status)


class ComfyClient:
    """A small ``aiohttp.ClientSession`` wrapper around ComfyUI endpoints."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session
        self._owns_session = session is None
        self.timeout = timeout or aiohttp.ClientTimeout(total=8, connect=2, sock_read=8)
        self.progress: dict[str, dict[str, Any]] = {}
        self._progress_nodes: dict[str, dict[str, str]] = {}
        self._progress_samples: dict[str, deque[tuple[float, int]]] = {}
        self.event_listener = None

    async def watch_progress(self, client_id: str) -> None:
        """Receive progress for prompts submitted by this Studio session."""
        session = await self._get_session()
        ws_url = f"{self.base_url.replace('http://', 'ws://', 1).replace('https://', 'wss://', 1)}/ws"
        while True:
            try:
                async with session.ws_connect(ws_url, params={"clientId": client_id}, heartbeat=30) as socket:
                    async for message in socket:
                        if message.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            event = json.loads(message.data)
                        except (TypeError, ValueError):
                            continue
                        if isinstance(event, dict):
                            self._record_progress(event)
                            if self.event_listener is not None:
                                try:
                                    self.event_listener(event)
                                except Exception:
                                    # A Studio subscriber must not disconnect the ComfyUI feed.
                                    pass
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                pass
            await asyncio.sleep(2)

    def _record_progress(self, event: dict[str, Any]) -> None:
        data = event.get("data")
        if not isinstance(data, dict):
            return
        prompt_id = str(data.get("prompt_id") or "")
        nodes = self._progress_nodes.get(prompt_id)
        if not nodes:
            return
        node = str(data.get("node") or "")
        phase = nodes.get(node)
        if event.get("type") == "executing":
            if phase:
                self.progress[prompt_id] = {"phase": phase}
                self._progress_samples.pop(prompt_id, None)
            elif node:
                previous_phase = self.progress.get(prompt_id, {}).get("phase")
                if previous_phase in {"rendering", "finishing"}:
                    self.progress[prompt_id] = {"phase": "finishing"}
                elif previous_phase is None:
                    self.progress[prompt_id] = {"phase": "preparing"}
            return
        if event.get("type") != "progress" or not phase:
            return
        try:
            value, maximum = int(data["value"]), int(data["max"])
        except (KeyError, TypeError, ValueError):
            return
        if maximum <= 0 or value < 0:
            return
        now = time.monotonic()
        previous = self.progress.get(prompt_id, {})
        if previous.get("phase") != phase or value < previous.get("current", 0):
            self._progress_samples[prompt_id] = deque()
        samples = self._progress_samples.setdefault(prompt_id, deque())
        samples.append((now, value))
        while len(samples) > 1 and now - samples[0][0] > 5:
            samples.popleft()
        elapsed = now - samples[0][0]
        rate = (value - samples[0][1]) / elapsed if elapsed > 0 else 0
        self.progress[prompt_id] = {
            "phase": phase, "current": value, "total": maximum,
            "rate": round(max(0, rate), 3) if phase == "rendering" else
                    round(max(0, rate), 1) if phase in {"abc", "music"} else None,
        }

    def progress_for(self, prompt_id: str) -> dict[str, Any] | None:
        return self.progress.get(prompt_id)

    def clear_progress(self, prompt_id: str) -> None:
        self.progress.pop(prompt_id, None)
        self._progress_nodes.pop(prompt_id, None)
        self._progress_samples.pop(prompt_id, None)

    async def start(self) -> None:
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=self.timeout)

    async def close(self) -> None:
        if self._owns_session and self.session is not None and not self.session.closed:
            await self.session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        await self.start()
        # ``start`` always initializes an owned session when needed.
        assert self.session is not None
        return self.session

    @staticmethod
    def _is_network_error(error: BaseException) -> bool:
        return isinstance(error, (aiohttp.ClientError, asyncio.TimeoutError, OSError))

    async def system_stats(self) -> dict[str, Any] | None:
        """Return system stats when ComfyUI is reachable, otherwise ``None``."""

        session = await self._get_session()
        health_timeout = aiohttp.ClientTimeout(total=2, connect=0.5, sock_read=2)
        try:
            async with session.get(f"{self.base_url}/system_stats", timeout=health_timeout) as response:
                if response.status < 200 or response.status >= 300:
                    return None
                data = await response.json(content_type=None)
                return data if isinstance(data, dict) else {}
        except Exception as error:
            if self._is_network_error(error):
                return None
            return None

    async def upload_audio(
        self,
        source: str | Path | bytes | bytearray | BinaryIO,
        filename: str,
        *,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload an audio file to ComfyUI's input directory."""

        session = await self._get_session()
        form = aiohttp.FormData()
        source_handle: BinaryIO | None = None
        close_handle = False
        try:
            if isinstance(source, (str, Path)):
                source_handle = open(source, "rb")
                close_handle = True
                payload: Any = source_handle
            else:
                payload = source
            guessed_type = content_type or mimetypes.guess_type(filename, strict=False)[0] or "application/octet-stream"
            upload_name = f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
            form.add_field("image", payload, filename=upload_name, content_type=guessed_type)
            form.add_field("subfolder", "yue2_uploads")
            form.add_field("type", "input")
            form.add_field("overwrite", "false")
            try:
                upload_timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=120)
                async with session.post(f"{self.base_url}/upload/image", data=form, timeout=upload_timeout) as response:
                    if response.status < 200 or response.status >= 300:
                        raise ComfyResponseError(response.status)
                    data = await response.json(content_type=None)
            except ComfyResponseError:
                raise
            except Exception as error:
                if self._is_network_error(error):
                    raise ComfyUnavailable() from error
                raise ComfyUnavailable() from error
            if not isinstance(data, dict):
                raise ComfyUnavailable()
            return data
        finally:
            if close_handle and source_handle is not None:
                source_handle.close()

    async def queue_prompt(self, prompt: dict[str, Any], client_id: str) -> str:
        """Queue a prompt and return only its opaque prompt identifier."""

        session = await self._get_session()
        try:
            async with session.post(
                f"{self.base_url}/prompt",
                json={"prompt": prompt, "client_id": client_id},
                timeout=self.timeout,
            ) as response:
                if response.status < 200 or response.status >= 300:
                    raise ComfyResponseError(response.status)
                data = await response.json(content_type=None)
        except ComfyResponseError:
            raise
        except Exception as error:
            raise ComfyUnavailable() from error
        if not isinstance(data, dict) or not data.get("prompt_id"):
            raise ComfyUnavailable()
        prompt_id = str(data["prompt_id"])
        self._progress_nodes[prompt_id] = {
            node_id: phase
            for node_id, node in prompt.items()
            if (phase := {
                "YuE2GenerateABC": "abc",
                "SheetSage2AudioToABC": "sheet",
                "YuE2GenerateMusic": "music",
                "KSampler": "rendering",
            }.get(node.get("class_type")))
        }
        return prompt_id

    async def cancel_prompt(self, prompt_id: str) -> bool:
        session = await self._get_session()
        self.clear_progress(prompt_id)
        try:
            async with session.post(
                f"{self.base_url}/queue",
                json={"delete": [prompt_id]},
                timeout=self.timeout,
            ) as response:
                return response.status == 200
        except Exception:
            return False

    async def history(self, prompt_id: str) -> dict[str, Any]:
        session = await self._get_session()
        try:
            async with session.get(
                f"{self.base_url}/history/{prompt_id}", timeout=self.timeout
            ) as response:
                if response.status < 200 or response.status >= 300:
                    raise ComfyResponseError(response.status)
                data = await response.json(content_type=None)
        except ComfyResponseError:
            raise
        except Exception as error:
            raise ComfyUnavailable() from error
        if not isinstance(data, dict):
            raise ComfyUnavailable()
        return data

    async def queue(self) -> dict[str, Any]:
        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/queue", timeout=self.timeout) as response:
                if response.status < 200 or response.status >= 300:
                    raise ComfyResponseError(response.status)
                data = await response.json(content_type=None)
        except ComfyResponseError:
            raise
        except Exception as error:
            raise ComfyUnavailable() from error
        if not isinstance(data, dict):
            raise ComfyUnavailable()
        return data

    async def open_view(
        self,
        filename: str,
        subfolder: str | None = None,
        output_type: str | None = None,
        *,
        range_header: str | None = None,
    ) -> aiohttp.ClientResponse:
        """Open a ComfyUI ``/view`` response for streaming.

        The caller owns and must release the returned response.  A non-success
        status is released here and surfaced as ``ComfyResponseError``.
        """

        session = await self._get_session()
        params = {
            "filename": filename,
            "subfolder": subfolder or "",
            "type": output_type or "output",
        }
        stream_timeout = aiohttp.ClientTimeout(total=None, connect=3, sock_read=60)
        try:
            response = await session.get(
                f"{self.base_url}/view", params=params, timeout=stream_timeout,
                headers={"Range": range_header} if range_header else None,
            )
        except Exception as error:
            raise ComfyUnavailable() from error
        if response.status < 200 or response.status >= 300:
            status = response.status
            response.release()
            raise ComfyResponseError(status)
        return response

    async def inspect_prompt(self, prompt_id: str) -> dict[str, Any] | None:
        """Inspect history/queue and return a safe state transition.

        A prompt absent from both history and the queue was removed before
        completion, so the Studio can stop showing it as active.
        """

        history = await self.history(prompt_id)
        entry = history.get(prompt_id)
        if entry is None and history.get("prompt_id") == prompt_id:
            entry = history
        if isinstance(entry, dict):
            status = entry.get("status")
            status_str = ""
            completed = False
            messages: Any = None
            if isinstance(status, dict):
                status_str = str(status.get("status_str") or status.get("status") or "").lower()
                completed = bool(status.get("completed"))
                messages = status.get("messages")
            elif status is not None:
                status_str = str(status).lower()
            if self._has_execution_interrupted(messages) or status_str in {"cancelled", "canceled"}:
                return {"status": "cancelled"}
            if self._has_execution_error(messages) or status_str in {
                "error",
                "failed",
                "failure",
            }:
                return {"status": "failed", "error": GENERIC_GENERATION_ERROR}

            audio = self._first_audio(entry.get("outputs"))
            if audio is not None and (completed or status_str in {"success", "completed", "complete", "done", ""}):
                return {"status": "completed", "output": audio}
            if completed or status_str in {"success", "completed", "complete", "done"}:
                return {"status": "failed", "error": GENERIC_GENERATION_ERROR}
            return {"status": "running"}

        queue = await self.queue()
        if self._queue_contains(queue.get("queue_running"), prompt_id):
            return {"status": "running"}
        if self._queue_contains(queue.get("queue_pending"), prompt_id):
            return {"status": "queued"}
        return {"status": "cancelled"}

    @staticmethod
    def _has_execution_interrupted(messages: Any) -> bool:
        if not isinstance(messages, list):
            return False
        return any(isinstance(message, (list, tuple)) and message and str(message[0]).lower() == "execution_interrupted"
                   for message in messages)

    @staticmethod
    def _has_execution_error(messages: Any) -> bool:
        if not isinstance(messages, list):
            return False
        for message in messages:
            if isinstance(message, (list, tuple)) and message:
                if str(message[0]).lower() in {"execution_error", "error"}:
                    return True
            elif isinstance(message, str) and "execution_error" in message.lower():
                return True
        return False

    @staticmethod
    def _first_audio(outputs: Any) -> dict[str, str] | None:
        if not isinstance(outputs, dict):
            return None
        for output in outputs.values():
            if not isinstance(output, dict):
                continue
            audios = output.get("audio")
            if isinstance(audios, dict):
                audios = [audios]
            if not isinstance(audios, list):
                continue
            for audio in audios:
                if not isinstance(audio, dict) or not audio.get("filename"):
                    continue
                return {
                    "filename": str(audio["filename"]),
                    "subfolder": str(audio.get("subfolder") or ""),
                    "type": str(audio.get("type") or "output"),
                }
        return None

    @staticmethod
    def _queue_contains(entries: Any, prompt_id: str) -> bool:
        if not isinstance(entries, list):
            return False
        for entry in entries:
            if isinstance(entry, str) and entry == prompt_id:
                return True
            if isinstance(entry, (list, tuple)):
                for value in entry:
                    if isinstance(value, (str, int, float)) and str(value) == prompt_id:
                        return True
        return False


__all__ = [
    "ComfyClient",
    "ComfyError",
    "ComfyResponseError",
    "ComfyUnavailable",
    "GENERIC_GENERATION_ERROR",
]
