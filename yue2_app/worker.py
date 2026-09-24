"""Outbound GPU worker: central Studio API <-> local ComfyUI API."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin

import aiohttp

from .comfy_client import ComfyClient
from .workflow_builder import build_workflow


class Worker:
    def __init__(self) -> None:
        self.server = os.environ["YUE2_SERVER_URL"].rstrip("/") + "/"
        if not (self.server.startswith("https://") or self.server.startswith("http://127.0.0.1:")):
            raise ValueError("YUE2_SERVER_URL must use HTTPS")
        self.worker_id = os.environ["YUE2_WORKER_ID"]
        self.token = os.environ["YUE2_WORKER_TOKEN"]
        self.comfy = ComfyClient(os.environ.get("YUE2_COMFY_URL", "http://127.0.0.1:8188"))
        self.session: aiohttp.ClientSession | None = None

    def _headers(self, lease: str | None = None) -> dict[str, str]:
        headers = {"Authorization": "Bearer " + self.token, "X-Yue-Worker": self.worker_id}
        if lease:
            headers["X-Yue-Lease"] = lease
        return headers

    def _url(self, path: str) -> str:
        return urljoin(self.server, path.lstrip("/"))

    async def _post(self, path: str, body: dict, *, lease: str | None = None) -> dict:
        assert self.session is not None
        async with self.session.post(self._url(path), json=body, headers=self._headers(lease)) as response:
            response.raise_for_status()
            return await response.json()

    async def _source(self, job: dict) -> tuple[str, str] | None:
        if not job.get("source_url"):
            return None
        assert self.session is not None
        name = str(job["payload"].get("source_filename") or "source.mp3")
        suffix = Path(name).suffix.lower()
        descriptor, path = tempfile.mkstemp(prefix="yue2-worker-", suffix=suffix)
        os.close(descriptor)
        try:
            async with self.session.get(self._url(job["source_url"]), headers=self._headers(job["lease_token"])) as response:
                response.raise_for_status()
                with open(path, "wb") as target:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        target.write(chunk)
            uploaded = await self.comfy.upload_audio(path, name)
            return str(uploaded["name"]), str(uploaded.get("subfolder") or "yue2_uploads")
        finally:
            Path(path).unlink(missing_ok=True)

    async def _heartbeat(self, job: dict, prompt_id: str | None, stop: asyncio.Event) -> None:
        last_progress: dict | None = None
        last_sent = -float("inf")
        while not stop.is_set():
            progress = self.comfy.progress_for(prompt_id) if prompt_id else None
            if progress != last_progress or time.monotonic() - last_sent >= 10:
                try:
                    await self._post("/api/worker/heartbeat", {
                        "job_id": job["job_id"], "lease_token": job["lease_token"], "progress": progress,
                    })
                    last_progress = dict(progress) if progress else None
                    last_sent = time.monotonic()
                except aiohttp.ClientResponseError as error:
                    if error.status == 409:
                        raise RuntimeError("work lease expired") from error
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    pass
            try:
                await asyncio.wait_for(stop.wait(), 2)
            except asyncio.TimeoutError:
                pass

    async def _execute(self, job: dict) -> None:
        payload = job["payload"]
        source = await self._source(job)
        settings = dict(payload["settings"])
        instrumental = bool(payload.get("instrumental", settings.pop("instrumental", False)))
        settings.pop("instrumental", None)
        graph = build_workflow(
            job_id=job["job_id"], mode=payload["mode"], style=payload["style"],
            lyrics=payload.get("lyrics") or "", instrumental=instrumental, seed=payload["seed"],
            source_filename=source[0] if source else None,
            source_subfolder=source[1] if source else "yue2_uploads",
            **settings,
        )
        client_id = str(uuid.uuid4())
        watcher = asyncio.create_task(self.comfy.watch_progress(client_id))
        prompt_id: str | None = None
        stop = asyncio.Event()
        heartbeat: asyncio.Task | None = None
        try:
            prompt_id = await self.comfy.queue_prompt(graph, client_id)
            heartbeat = asyncio.create_task(self._heartbeat(job, prompt_id, stop))
            while True:
                await asyncio.sleep(4)
                if heartbeat.done():
                    await heartbeat
                state = await self.comfy.inspect_prompt(prompt_id)
                if not state or state.get("status") in {"queued", "running"}:
                    continue
                if state.get("status") != "completed" or not state.get("output"):
                    raise RuntimeError("ComfyUI generation failed")
                output = state["output"]
                upstream = await self.comfy.open_view(
                    output["filename"], output.get("subfolder"), output.get("type"),
                )
                try:
                    assert self.session is not None
                    async with self.session.post(
                        self._url(f"/api/worker/jobs/{job['job_id']}/complete"),
                        data=upstream.content.iter_chunked(1024 * 1024),
                        headers={**self._headers(job["lease_token"]), "Content-Type": "audio/mpeg"},
                        timeout=aiohttp.ClientTimeout(total=None, connect=10, sock_read=120),
                    ) as response:
                        response.raise_for_status()
                finally:
                    upstream.release()
                return
        finally:
            stop.set()
            if heartbeat:
                await asyncio.gather(heartbeat, return_exceptions=True)
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            if prompt_id:
                self.comfy.clear_progress(prompt_id)

    async def run(self) -> None:
        await self.comfy.start()
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, connect=10, sock_read=120),
            connector=aiohttp.TCPConnector(force_close=True),
        ) as self.session:
            try:
                while True:
                    stats = await self.comfy.system_stats()
                    if stats is None:
                        print("ComfyUI offline; retrying", flush=True)
                        await asyncio.sleep(10)
                        continue
                    device = (stats.get("devices") or [{}])[0]
                    info = {"device": str(device.get("name") or "GPU"),
                            "vram": str(round(int(device.get("vram_total") or 0) / 1024**3, 1)) + "GB"}
                    try:
                        claimed = await self._post("/api/worker/claim", info)
                    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                        print(f"Studio unavailable: {type(error).__name__}", flush=True)
                        await asyncio.sleep(10)
                        continue
                    job = claimed.get("job")
                    if not job:
                        await asyncio.sleep(3)
                        continue
                    print("Starting job", job["job_id"], flush=True)
                    try:
                        await self._execute(job)
                        print("Completed job", job["job_id"], flush=True)
                    except Exception as error:
                        print("Job failed", job["job_id"], type(error).__name__, flush=True)
                        try:
                            await self._post(f"/api/worker/jobs/{job['job_id']}/fail",
                                             {"lease_token": job["lease_token"]})
                        except (aiohttp.ClientError, asyncio.TimeoutError):
                            pass
            finally:
                await self.comfy.close()


def main() -> None:
    asyncio.run(Worker().run())


if __name__ == "__main__":
    main()
