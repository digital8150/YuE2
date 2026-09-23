"""SQLite persistence for YuE2 generation jobs.

The web layer deliberately keeps the database model small.  Backend prompt and
output metadata are stored so that a completed track can be served later, but
they are never exposed by the public serialization helper in ``server.py``.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp suitable for SQLite text storage."""

    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Job:
    """A persisted generation job.

    ``prompt_id`` and output fields are intentionally part of the private
    record.  The API's public projection omits them to avoid leaking ComfyUI
    implementation details.
    """

    id: str
    prompt_id: str | None
    mode: str
    title: str | None
    style: str
    lyrics: str
    created_at: str
    updated_at: str
    status: str
    seed: int
    settings: dict[str, Any]
    source_filename: str | None
    creator_id: int | None
    creator_name: str | None
    output_filename: str | None
    output_subfolder: str | None
    output_type: str | None
    error: str | None


class Repository:
    """Small synchronous SQLite repository used by the aiohttp handlers."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else Path(__file__).parent / "data" / "yue2.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    prompt_id TEXT UNIQUE,
                    mode TEXT NOT NULL CHECK (mode IN ('original', 'cover')),
                    title TEXT,
                    style TEXT NOT NULL,
                    lyrics TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
                    seed INTEGER NOT NULL,
                    settings TEXT NOT NULL,
                    source_filename TEXT,
                    creator_id INTEGER,
                    creator_name TEXT,
                    output_filename TEXT,
                    output_subfolder TEXT,
                    output_type TEXT,
                    error TEXT
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "creator_id" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN creator_id INTEGER")
            if "creator_name" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN creator_name TEXT")
            schema = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'jobs'").fetchone()[0]
            if "'cancelled'" not in schema:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ALTER TABLE jobs RENAME TO jobs_old")
                connection.execute("""CREATE TABLE jobs (
                    id TEXT PRIMARY KEY, prompt_id TEXT UNIQUE, mode TEXT NOT NULL CHECK (mode IN ('original', 'cover')),
                    title TEXT, style TEXT NOT NULL, lyrics TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
                    seed INTEGER NOT NULL, settings TEXT NOT NULL, source_filename TEXT,
                    creator_id INTEGER, creator_name TEXT, output_filename TEXT,
                    output_subfolder TEXT, output_type TEXT, error TEXT
                )""")
                connection.execute("""INSERT INTO jobs (
                    id, prompt_id, mode, title, style, lyrics, created_at, updated_at,
                    status, seed, settings, source_filename, creator_id, creator_name,
                    output_filename, output_subfolder, output_type, error)
                    SELECT id, prompt_id, mode, title, style, lyrics, created_at, updated_at,
                    status, seed, settings, source_filename, creator_id, creator_name,
                    output_filename, output_subfolder, output_type, error FROM jobs_old""")
                connection.execute("DROP TABLE jobs_old")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_mode ON jobs(mode)")

    @staticmethod
    def _from_row(row: sqlite3.Row | None) -> Job | None:
        if row is None:
            return None
        try:
            settings = json.loads(row["settings"])
        except (TypeError, ValueError, json.JSONDecodeError):
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        return Job(
            id=str(row["id"]),
            prompt_id=row["prompt_id"],
            mode=str(row["mode"]),
            title=row["title"],
            style=str(row["style"]),
            lyrics=str(row["lyrics"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            status=str(row["status"]),
            seed=int(row["seed"]),
            settings=settings,
            source_filename=row["source_filename"],
            creator_id=row["creator_id"],
            creator_name=row["creator_name"],
            output_filename=row["output_filename"],
            output_subfolder=row["output_subfolder"],
            output_type=row["output_type"],
            error=row["error"],
        )

    @staticmethod
    def _from_rows(rows: Iterable[sqlite3.Row]) -> list[Job]:
        result: list[Job] = []
        for row in rows:
            item = Repository._from_row(row)
            if item is not None:
                result.append(item)
        return result

    def create_job(
        self,
        *,
        job_id: str,
        prompt_id: str | None,
        mode: str,
        title: str | None,
        style: str,
        lyrics: str,
        seed: int,
        settings: dict[str, Any],
        source_filename: str | None = None,
        creator_id: int | None = None,
        creator_name: str | None = None,
        status: str = "queued",
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Job:
        """Insert a job and return the normalized record."""

        now = created_at or utc_now()
        updated = updated_at or now
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, prompt_id, mode, title, style, lyrics, created_at, updated_at,
                    status, seed, settings, source_filename, output_filename,
                    output_subfolder, output_type, error, creator_id, creator_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
                """,
                (
                    str(job_id),
                    prompt_id,
                    mode,
                    title,
                    style,
                    lyrics,
                    now,
                    updated,
                    status,
                    int(seed),
                    json.dumps(settings, ensure_ascii=False, separators=(",", ":")),
                    source_filename,
                    creator_id,
                    creator_name,
                ),
            )
        job = self.get_job(str(job_id))
        if job is None:  # pragma: no cover - guarded by the INSERT above
            raise RuntimeError("job insert did not persist")
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (str(job_id),)).fetchone()
        return self._from_row(row)

    def get_by_prompt_id(self, prompt_id: str) -> Job | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE prompt_id = ?", (str(prompt_id),)).fetchone()
        return self._from_row(row)

    def list_latest(self, limit: int = 8, offset: int = 0) -> list[Job]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        return self._from_rows(rows)

    def count_jobs(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()
        return int(row[0]) if row else 0

    def list_nonterminal(self) -> list[Job]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE status NOT IN ('completed', 'failed', 'cancelled') ORDER BY created_at ASC"
            ).fetchall()
        return self._from_rows(rows)

    def list_library(self, query: str = "", mode: str | None = None, limit: int = 100) -> list[Job]:
        limit = max(1, min(int(limit), 100))
        query = query.strip().lower()
        clauses = ["status = 'completed'"]
        values: list[Any] = []
        if query:
            clauses.append("(LOWER(COALESCE(title, '')) LIKE ? OR LOWER(style) LIKE ? OR LOWER(lyrics) LIKE ?)")
            term = f"%{query}%"
            values.extend((term, term, term))
        if mode in {"original", "cover"}:
            clauses.append("mode = ?")
            values.append(mode)
        where = " AND ".join(clauses)
        values.append(limit)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM jobs WHERE {where} ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return self._from_rows(rows)

    def set_prompt_id(self, job_id: str, prompt_id: str) -> None:
        self._update(job_id, prompt_id=str(prompt_id))

    def set_status(self, job_id: str, status: str, error: str | None = None) -> None:
        self._update(job_id, status=status, error=error)

    def set_output(
        self,
        job_id: str,
        *,
        filename: str,
        subfolder: str = "",
        output_type: str = "output",
    ) -> None:
        self._update(
            job_id,
            status="completed",
            error=None,
            output_filename=filename,
            output_subfolder=subfolder,
            output_type=output_type,
        )

    def _update(self, job_id: str, **fields: Any) -> None:
        allowed = {
            "prompt_id",
            "status",
            "error",
            "output_filename",
            "output_subfolder",
            "output_type",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"unsupported job field: {key}")
            assignments.append(f"{key} = ?")
            values.append(value)
        if not assignments:
            return
        assignments.append("updated_at = ?")
        values.append(utc_now())
        values.append(str(job_id))
        with self._connection() as connection:
            connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
                tuple(values),
            )

    def close(self) -> None:
        """Compatibility hook for application cleanup (connections are per call)."""

        return None


__all__ = ["Job", "Repository", "TERMINAL_STATUSES", "utc_now"]
