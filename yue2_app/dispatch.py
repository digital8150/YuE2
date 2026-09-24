"""Durable, outbound-polling dispatch for independently hosted GPU workers."""

from __future__ import annotations

import secrets
import hashlib
import hmac
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
            db.execute("""CREATE TABLE IF NOT EXISTS yue_worker_credentials (
                worker_id text PRIMARY KEY, owner_id bigint NOT NULL,
                name text NOT NULL, token_hash text NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                revoked_at timestamptz
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS yue_worker_credentials_owner ON yue_worker_credentials(owner_id)")

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
                WHERE (status = 'queued' OR (status = 'running' AND lease_until < now() AND attempts < 3))
                AND NOT EXISTS (SELECT 1 FROM yue_dispatch active
                    WHERE active.worker_id = %s AND active.status = 'running' AND active.lease_until > now())
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE yue_dispatch AS d SET status = 'running', worker_id = %s,
                lease_token = %s, lease_until = now() + interval '60 seconds',
                attempts = d.attempts + 1, progress = NULL, updated_at = now()
                FROM chosen WHERE d.job_id = chosen.job_id
                RETURNING d.job_id, d.payload, d.attempts""", (worker_id, worker_id, token)).fetchone()
        if row is None:
            return None
        return {"job_id": row[0], "payload": row[1], "attempts": row[2], "lease_token": token}

    def heartbeat(self, job_id: str, worker_id: str, token: str, progress: dict[str, Any] | None = None) -> bool:
        from psycopg.types.json import Jsonb

        with self._connect() as db:
            result = db.execute("""UPDATE yue_dispatch SET lease_until = now() + interval '60 seconds',
                progress = COALESCE(%s, progress), updated_at = now()
                WHERE job_id = %s AND worker_id = %s AND lease_token = %s AND status = 'running'
                AND lease_until > now()""", (Jsonb(progress) if progress is not None else None, job_id, worker_id, token))
            db.execute("UPDATE yue_workers SET last_seen = now() WHERE worker_id = %s", (worker_id,))
            return result.rowcount == 1

    def cancel(self, job_id: str) -> bool:
        with self._connect() as db:
            result = db.execute("""UPDATE yue_dispatch SET status = 'cancelled', updated_at = now()
                WHERE job_id = %s AND status = 'queued'""", (job_id,))
            return result.rowcount == 1

    def requeue(self, job_id: str, worker_id: str, token: str) -> tuple[bool, str]:
        with self._connect() as db:
            row = db.execute("""SELECT attempts FROM yue_dispatch
                WHERE job_id = %s AND worker_id = %s AND lease_token = %s
                AND status = 'running' AND lease_until > now()""", (job_id, worker_id, token)).fetchone()
            if row is None:
                return False, "invalid"
            attempts = row[0]
            if attempts < 3:
                db.execute("""UPDATE yue_dispatch SET status = 'queued', worker_id = NULL,
                    lease_token = NULL, lease_until = NULL, progress = NULL, updated_at = now()
                    WHERE job_id = %s""", (job_id,))
                return True, "requeued"
            else:
                db.execute("""UPDATE yue_dispatch SET status = 'failed', worker_id = NULL,
                    lease_token = NULL, lease_until = NULL, updated_at = now()
                    WHERE job_id = %s""", (job_id,))
                return True, "failed"

    def requeue_stale(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute("""UPDATE yue_dispatch SET status = 'queued',
                worker_id = NULL, lease_token = NULL, lease_until = NULL, progress = NULL, updated_at = now()
                WHERE status = 'running' AND lease_until < now() AND attempts < 3
                RETURNING job_id""").fetchall()
            return [row[0] for row in rows]

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
            rows = db.execute("""UPDATE yue_dispatch SET status = 'failed',
                lease_token = NULL, lease_until = NULL, updated_at = now()
                WHERE status = 'running' AND lease_until < now() AND attempts >= 3
                RETURNING job_id""").fetchall()
            return [row[0] for row in rows]

    def terminal(self) -> list[tuple[str, str, str | None]]:
        with self._connect() as db:
            return db.execute("""SELECT job_id, status, output_filename FROM yue_dispatch
                WHERE status IN ('completed', 'failed', 'cancelled')""").fetchall()

    def workers(self) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute("""SELECT w.worker_id, COALESCE(c.name, w.worker_id), w.device, w.vram,
                d.job_id, d.progress FROM yue_workers w
                LEFT JOIN yue_worker_credentials c ON c.worker_id = w.worker_id
                LEFT JOIN LATERAL (SELECT job_id, progress FROM yue_dispatch
                    WHERE worker_id = w.worker_id AND status = 'running' AND lease_until > now()
                    ORDER BY updated_at DESC LIMIT 1) d ON true
                WHERE w.last_seen > now() - interval '45 seconds'
                    AND (c.worker_id IS NULL OR c.revoked_at IS NULL)
                ORDER BY c.name NULLS LAST, w.worker_id""").fetchall()
            return [{"worker_id": r[0], "name": r[1], "device": r[2] or "",
                     "vram": r[3] or "", "status": "busy" if r[4] else "idle",
                     "progress": r[5] if r[4] else None} for r in rows]

    def progress_for_jobs(self, job_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not job_ids:
            return {}
        with self._connect() as db:
            rows = db.execute("""SELECT job_id, progress FROM yue_dispatch
                WHERE job_id = ANY(%s) AND status = 'running'
                    AND lease_until > now() AND progress IS NOT NULL""", (job_ids,)).fetchall()
        return {job_id: progress for job_id, progress in rows}

    def create_credential(self, owner_id: int, name: str) -> dict[str, str]:
        worker_id = "gpu-" + secrets.token_hex(12)
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as db:
            db.execute("""INSERT INTO yue_worker_credentials(worker_id, owner_id, name, token_hash)
                VALUES (%s, %s, %s, %s)""", (worker_id, owner_id, name, digest))
        return {"worker_id": worker_id, "name": name, "token": token}

    def authenticate(self, worker_id: str, token: str) -> bool:
        if not worker_id or not token:
            return False
        with self._connect() as db:
            row = db.execute("""SELECT token_hash FROM yue_worker_credentials
                WHERE worker_id = %s AND revoked_at IS NULL""", (worker_id,)).fetchone()
        return bool(row and hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), row[0]))

    def credentials(self, owner_id: int) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute("""SELECT worker_id, name FROM yue_worker_credentials
                WHERE owner_id = %s AND revoked_at IS NULL ORDER BY created_at DESC""", (owner_id,)).fetchall()
        return [{"worker_id": row[0], "name": row[1]} for row in rows]

    def revoke_credential(self, owner_id: int, worker_id: str) -> bool:
        with self._connect() as db:
            result = db.execute("""UPDATE yue_worker_credentials SET revoked_at = now()
                WHERE owner_id = %s AND worker_id = %s AND revoked_at IS NULL""", (owner_id, worker_id))
            return result.rowcount == 1
