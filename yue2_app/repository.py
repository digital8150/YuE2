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
    artist_id: int | None
    output_filename: str | None
    output_subfolder: str | None
    output_type: str | None
    error: str | None
    published_at: str | None
    published_title: str | None
    cover_filename: str | None
    album_id: str | None
    play_count: int


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
            if "published_at" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN published_at TEXT")
            if "cover_filename" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN cover_filename TEXT")
            if "published_title" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN published_title TEXT")
            if "album_id" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN album_id TEXT")
            if "play_count" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN play_count INTEGER NOT NULL DEFAULT 0")
            if "artist_id" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN artist_id INTEGER")
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
                    output_subfolder TEXT, output_type TEXT, error TEXT,
                    published_at TEXT, cover_filename TEXT, published_title TEXT,
                    album_id TEXT, play_count INTEGER NOT NULL DEFAULT 0, artist_id INTEGER
                )""")
                connection.execute("""INSERT INTO jobs (
                    id, prompt_id, mode, title, style, lyrics, created_at, updated_at,
                    status, seed, settings, source_filename, creator_id, creator_name,
                    output_filename, output_subfolder, output_type, error, published_at, cover_filename, published_title, album_id, play_count, artist_id)
                    SELECT id, prompt_id, mode, title, style, lyrics, created_at, updated_at,
                    status, seed, settings, source_filename, creator_id, creator_name,
                    output_filename, output_subfolder, output_type, error, published_at, cover_filename, published_title, album_id, play_count, artist_id FROM jobs_old""")
                connection.execute("DROP TABLE jobs_old")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_mode ON jobs(mode)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_published ON jobs(published_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_album ON jobs(album_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_artist ON jobs(artist_id, published_at DESC)")
            connection.execute("""CREATE TABLE IF NOT EXISTS artist_profiles (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, artist_name TEXT NOT NULL, bio TEXT NOT NULL DEFAULT '',
                avatar_filename TEXT, banner_filename TEXT, updated_at TEXT NOT NULL
            )""")
            if "id" not in {row["name"] for row in connection.execute("PRAGMA table_info(artist_profiles)")}:
                connection.execute("ALTER TABLE artist_profiles RENAME TO artist_profiles_old")
                connection.execute("""CREATE TABLE artist_profiles (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, artist_name TEXT NOT NULL,
                    bio TEXT NOT NULL DEFAULT '', avatar_filename TEXT, banner_filename TEXT, updated_at TEXT NOT NULL
                )""")
                connection.execute("""INSERT INTO artist_profiles
                    (id, user_id, artist_name, bio, avatar_filename, banner_filename, updated_at)
                    SELECT user_id, user_id, artist_name, bio, avatar_filename, banner_filename, updated_at
                    FROM artist_profiles_old""")
                connection.execute("DROP TABLE artist_profiles_old")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_artists_owner ON artist_profiles(user_id)")
            connection.execute("UPDATE jobs SET artist_id = creator_id WHERE artist_id IS NULL AND published_at IS NOT NULL")
            connection.execute("""CREATE TABLE IF NOT EXISTS albums (
                id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '', cover_filename TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_albums_owner ON albums(owner_id, created_at DESC)")
            if "artist_id" not in {row["name"] for row in connection.execute("PRAGMA table_info(albums)")}:
                connection.execute("ALTER TABLE albums ADD COLUMN artist_id INTEGER")
            connection.execute("UPDATE albums SET artist_id = owner_id WHERE artist_id IS NULL")

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
            artist_id=row["artist_id"],
            output_filename=row["output_filename"],
            output_subfolder=row["output_subfolder"],
            output_type=row["output_type"],
            error=row["error"],
            published_at=row["published_at"],
            published_title=row["published_title"],
            cover_filename=row["cover_filename"],
            album_id=row["album_id"],
            play_count=int(row["play_count"] or 0),
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

    def list_latest(self, limit: int = 8, offset: int = 0, creator_id: int | None = None, *, include_legacy: bool = False) -> list[Job]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        with self._connection() as connection:
            if creator_id is None:
                rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            elif include_legacy:
                rows = connection.execute("SELECT * FROM jobs WHERE creator_id = ? OR creator_id IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?", (creator_id, limit, offset)).fetchall()
            else:
                rows = connection.execute("SELECT * FROM jobs WHERE creator_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?", (creator_id, limit, offset)).fetchall()
        return self._from_rows(rows)

    def count_jobs(self, creator_id: int | None = None, *, include_legacy: bool = False) -> int:
        with self._connection() as connection:
            if creator_id is None:
                row = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()
            else:
                sql = "SELECT COUNT(*) FROM jobs WHERE creator_id = ?"
                if include_legacy:
                    sql += " OR creator_id IS NULL"
                row = connection.execute(sql, (creator_id,)).fetchone()
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
        clauses = ["status = 'completed'", "published_at IS NOT NULL"]
        values: list[Any] = []
        if query:
            clauses.append("(LOWER(COALESCE(published_title, title, '')) LIKE ? OR LOWER(style) LIKE ? OR LOWER(lyrics) LIKE ?)")
            term = f"%{query}%"
            values.extend((term, term, term))
        if mode in {"original", "cover"}:
            clauses.append("mode = ?")
            values.append(mode)
        where = " AND ".join(clauses)
        values.append(limit)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM jobs WHERE {where} ORDER BY published_at DESC, created_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return self._from_rows(rows)

    def list_charts(self, limit: int = 20) -> list[Job]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM jobs WHERE published_at IS NOT NULL AND status = 'completed'
                   ORDER BY play_count DESC, published_at DESC LIMIT ?""", (max(1, min(limit, 100)),)
            ).fetchall()
        return self._from_rows(rows)

    def increment_play(self, job_id: str) -> int | None:
        with self._connection() as connection:
            result = connection.execute(
                "UPDATE jobs SET play_count = play_count + 1 WHERE id = ? AND published_at IS NOT NULL AND status = 'completed'", (job_id,)
            )
            if not result.rowcount:
                return None
            row = connection.execute("SELECT play_count FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return int(row[0])

    def get_artist(self, artist_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM artist_profiles WHERE id = ?", (artist_id,)).fetchone()
        return dict(row) if row else None

    def list_owned_artists(self, user_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM artist_profiles WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def create_artist(self, user_id: int, name: str, bio: str, avatar: str | None, banner: str | None) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT MIN(id) FROM artist_profiles").fetchone()
            artist_id = min(0, row[0] or 0) - 1
            connection.execute("""INSERT INTO artist_profiles
                (id, user_id, artist_name, bio, avatar_filename, banner_filename, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (artist_id, user_id, name, bio, avatar, banner, utc_now()))
        return self.get_artist(artist_id)

    def save_artist(self, user_id: int, name: str, bio: str, avatar: str | None, banner: str | None,
                    *, artist_id: int | None = None) -> dict[str, Any] | None:
        artist_id = user_id if artist_id is None else artist_id
        with self._connection() as connection:
            if artist_id != user_id and not connection.execute(
                    "SELECT 1 FROM artist_profiles WHERE id = ? AND user_id = ?", (artist_id, user_id)).fetchone():
                return None
            connection.execute("""INSERT INTO artist_profiles (id, user_id, artist_name, bio, avatar_filename, banner_filename, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET
                artist_name = excluded.artist_name, bio = excluded.bio,
                avatar_filename = COALESCE(excluded.avatar_filename, avatar_filename),
                banner_filename = COALESCE(excluded.banner_filename, banner_filename),
                updated_at = excluded.updated_at""", (artist_id, user_id, name, bio, avatar, banner, utc_now()))
        return self.get_artist(artist_id)

    def list_artists(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("""SELECT j.artist_id AS artist_id, p.artist_name, p.bio, p.avatar_filename,
                p.banner_filename, COUNT(*) AS track_count, MAX(j.published_at) AS latest_at,
                MIN(j.creator_name) AS creator_name
                FROM jobs j LEFT JOIN artist_profiles p ON p.id = j.artist_id
                WHERE j.published_at IS NOT NULL AND j.status = 'completed' AND j.artist_id IS NOT NULL
                GROUP BY j.artist_id ORDER BY latest_at DESC LIMIT ?""", (max(1, min(limit, 100)),)).fetchall()
        return [dict(row) for row in rows]

    def create_album(self, album_id: str, owner_id: int, title: str, description: str, cover: str | None,
                     *, artist_id: int | None = None) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as connection:
            connection.execute("""INSERT INTO albums
                (id, owner_id, title, description, cover_filename, created_at, updated_at, artist_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                               (album_id, owner_id, title, description, cover, now, now,
                                owner_id if artist_id is None else artist_id))
        return self.get_album(album_id)

    def get_album(self, album_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("""SELECT a.*, COUNT(j.id) AS track_count,
                MAX(j.published_at) AS published_at FROM albums a
                LEFT JOIN jobs j ON j.album_id = a.id AND j.published_at IS NOT NULL AND j.status = 'completed'
                WHERE a.id = ? GROUP BY a.id""", (album_id,)).fetchone()
        return dict(row) if row else None

    def update_album(self, album_id: str, owner_id: int, title: str, description: str, cover: str | None) -> dict[str, Any] | None:
        with self._connection() as connection:
            result = connection.execute("""UPDATE albums SET title = ?, description = ?,
                cover_filename = COALESCE(?, cover_filename), updated_at = ? WHERE id = ? AND owner_id = ?""",
                (title, description, cover, utc_now(), album_id, owner_id))
        return self.get_album(album_id) if result.rowcount else None

    def list_albums(self, *, owner_id: int | None = None, public_only: bool = True, limit: int = 50) -> list[dict[str, Any]]:
        clauses = []
        values: list[Any] = []
        if owner_id is not None:
            clauses.append("a.owner_id = ?")
            values.append(owner_id)
        if public_only:
            clauses.append("EXISTS (SELECT 1 FROM jobs published WHERE published.album_id = a.id AND published.published_at IS NOT NULL AND published.status = 'completed')")
        where = " AND ".join(clauses) or "1=1"
        values.append(max(1, min(limit, 100)))
        with self._connection() as connection:
            rows = connection.execute(f"""SELECT a.*, COUNT(j.id) AS track_count,
                MAX(j.published_at) AS published_at FROM albums a
                LEFT JOIN jobs j ON j.album_id = a.id AND j.published_at IS NOT NULL AND j.status = 'completed'
                WHERE {where} GROUP BY a.id ORDER BY COALESCE(published_at, a.created_at) DESC LIMIT ?""", values).fetchall()
        return [dict(row) for row in rows]

    def list_album_tracks(self, album_id: str) -> list[Job]:
        with self._connection() as connection:
            rows = connection.execute("""SELECT * FROM jobs WHERE album_id = ? AND published_at IS NOT NULL AND status = 'completed'
                ORDER BY published_at, created_at""", (album_id,)).fetchall()
        return self._from_rows(rows)

    def list_artist_tracks(self, artist_id: int, limit: int = 100) -> list[Job]:
        with self._connection() as connection:
            rows = connection.execute("""SELECT * FROM jobs WHERE artist_id = ? AND published_at IS NOT NULL AND status = 'completed'
                ORDER BY published_at DESC LIMIT ?""", (artist_id, max(1, min(limit, 100)))).fetchall()
        return self._from_rows(rows)

    def publish(self, job_id: str, creator_id: int, title: str, cover_filename: str | None = None, *,
                album_id: str | None = None, artist_id: int | None = None, allow_legacy: bool = False) -> Job | None:
        with self._connection() as connection:
            connection.execute(
                """UPDATE jobs SET published_title = ?, cover_filename = COALESCE(?, cover_filename), album_id = ?, artist_id = ?,
                   published_at = COALESCE(published_at, ?), updated_at = ?
                   WHERE id = ? AND (creator_id = ? OR (creator_id IS NULL AND ?))
                   AND status = 'completed' AND output_filename IS NOT NULL""",
                (title, cover_filename, album_id, creator_id if artist_id is None else artist_id,
                 utc_now(), utc_now(), job_id, creator_id, int(allow_legacy)),
            )
        return self.get_job(job_id)

    def unpublish(self, job_id: str, creator_id: int, *, allow_legacy: bool = False) -> bool:
        with self._connection() as connection:
            result = connection.execute(
                """UPDATE jobs SET published_at = NULL, updated_at = ? WHERE id = ?
                   AND (creator_id = ? OR (creator_id IS NULL AND ?)) AND published_at IS NOT NULL""",
                (utc_now(), job_id, creator_id, int(allow_legacy)),
            )
        return result.rowcount > 0

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
