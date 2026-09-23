"""Durable, outbound-polling dispatch for independently hosted GPU workers."""

from __future__ import annotations

import secrets
from typing import Any


class DispatchStore:
    def __init__(self, dsn: str) -> None:
        import psycopg

        self.psycopg = psycopg
        self.dsn = dsn
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS yue_dispatch (
                job_id text PRIMARY KEY, payload jsonb NOT NULL,
                status text NOT NULL DEFAULT 'queued', worker_id text,
                lease_token text, lease_until timestamptz,
                attempts integer NOT NULL DEFAULT 0, progress jsonb,
                output_filename text,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS yue_dispatch_ready ON yue_dispatch(status, created_at)")
            db.execute("ALTER TABLE yue_dispatch ADD COLUMN IF NOT EXISTS output_filename text")
            db.execute("""CREATE TABLE IF NOT EXISTS yue_workers (
                worker_id text PRIMARY KEY, device text, vram text,
                last_seen timestamptz NOT NULL DEFAULT now()
            )""")

    def _connect(self):
        return self.psycopg.connect(self.dsn)

    def enqueue(self, job_id: str, payload: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        with self._connect() as db:
            db.execute("INSERT INTO yue_dispatch(job_id, payload) VALUES (%s, %s)", (job_id, Jsonb(payload)))

    def claim(self, worker_id: str, device: str = "", vram: str = "") -> dict[str, Any] | None:
        token = secrets.token_urlsafe(32)
        with self._connect() as db:
            db.execute("""INSERT INTO yue_workers(worker_id, device, vram, last_seen)
                VALUES (%s, %s, %s, now()) ON CONFLICT(worker_id) DO UPDATE SET
                device = excluded.device, vram = excluded.vram, last_seen = now()""", (worker_id, device[:150], vram[:80]))
            row = db.execute("""WITH chosen AS (
                SELECT job_id FROM yue_dispatch
                WHERE status = 'queued' OR (status = 'running' AND lease_until < now() AND attempts < 3)
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE yue_dispatch AS d SET status = 'running', worker_id = %s,
                lease_token = %s, lease_until = now() + interval '10 minutes',
                attempts = d.attempts + 1, progress = NULL, updated_at = now()
                FROM chosen WHERE d.job_id = chosen.job_id
                RETURNING d.job_id, d.payload, d.attempts""", (worker_id, token)).fetchone()
        if row is None:
            return None
        return {"job_id": row[0], "payload": row[1], "attempts": row[2], "lease_token": token}

    def heartbeat(self, job_id: str, worker_id: str, token: str, progress: dict[str, Any] | None = None) -> bool:
        from psycopg.types.json import Jsonb

        with self._connect() as db:
            result = db.execute("""UPDATE yue_dispatch SET lease_until = now() + interval '10 minutes',
                progress = COALESCE(%s, progress), updated_at = now()
                WHERE job_id = %s AND worker_id = %s AND lease_token = %s AND status = 'running'
                AND lease_until > now()""", (Jsonb(progress) if progress is not None else None, job_id, worker_id, token))
            db.execute("UPDATE yue_workers SET last_seen = now() WHERE worker_id = %s", (worker_id,))
            return result.rowcount == 1

    def finish(self, job_id: str, worker_id: str, token: str, status: str,
               output_filename: str | None = None) -> bool:
        if status not in {"completed", "failed"}:
            raise ValueError("invalid dispatch status")
        with self._connect() as db:
            result = db.execute("""UPDATE yue_dispatch SET status = %s, lease_token = NULL,
                lease_until = NULL, output_filename = %s, updated_at = now()
                WHERE job_id = %s AND worker_id = %s
                AND lease_token = %s AND status = 'running' AND lease_until > now()""",
                (status, output_filename, job_id, worker_id, token))
            return result.rowcount == 1

    def status(self, job_id: str) -> tuple[str, str | None] | None:
        with self._connect() as db:
            row = db.execute("SELECT status, worker_id FROM yue_dispatch WHERE job_id = %s", (job_id,)).fetchone()
            return (row[0], row[1]) if row else None

    def expired(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute("""UPDATE yue_dispatch SET status = 'failed', updated_at = now()
                WHERE status = 'running' AND lease_until < now() AND attempts >= 3
                RETURNING job_id""").fetchall()
            return [row[0] for row in rows]

    def terminal(self) -> list[tuple[str, str, str | None]]:
        with self._connect() as db:
            return db.execute("""SELECT job_id, status, output_filename FROM yue_dispatch
                WHERE status IN ('completed', 'failed')""").fetchall()

    def workers(self) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute("""SELECT worker_id, device, vram FROM yue_workers
                WHERE last_seen > now() - interval '2 minutes' ORDER BY worker_id""").fetchall()
            return [{"worker_id": r[0], "device": r[1] or "", "vram": r[2] or ""} for r in rows]
