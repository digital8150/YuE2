"""PostgreSQL storage for Studio accounts and library metadata.

The small connection adapter preserves the existing repository API while the
single-server SQLite installation remains available for local development.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from .auth import AuthStore
from .repository import Repository


class _Row(Mapping):
    def __init__(self, data: dict[str, Any]):
        self.data = data

    def __getitem__(self, key):
        return list(self.data.values())[key] if isinstance(key, int) else self.data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)


class _Result:
    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = lastrowid

    def fetchone(self):
        row = self.cursor.fetchone()
        return _Row(row) if row is not None else None

    def fetchall(self):
        return [_Row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return (_Row(row) for row in self.cursor)


class _Connection:
    def __init__(self, dsn: str):
        self.db = psycopg.connect(dsn, row_factory=dict_row)

    def execute(self, sql: str, values=()):
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            return None
        sql = re.sub(r"\s+COLLATE\s+NOCASE\b", "", sql, flags=re.IGNORECASE)
        sql = sql.replace("?", "%s")
        user_insert = bool(re.match(r"\s*INSERT\s+INTO\s+users\b", sql, re.IGNORECASE))
        if user_insert:
            sql += " RETURNING id"
        try:
            cursor = self.db.execute(sql, values)
            lastrowid = cursor.fetchone()["id"] if user_insert else None
            return _Result(cursor, lastrowid)
        except psycopg.errors.UniqueViolation as error:
            raise sqlite3.IntegrityError(str(error)) from error

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        if error_type is None:
            self.db.commit()
        else:
            self.db.rollback()


class PostgresRepository(Repository):
    def __init__(self, dsn: str, data_dir: str | Path):
        self.dsn = dsn
        self.path = Path(data_dir) / "yue2.sqlite3"  # compatibility: media directory only
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        return _Connection(self.dsn)

    def _initialize(self):
        with self._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id text PRIMARY KEY, prompt_id text UNIQUE,
                mode text NOT NULL CHECK(mode IN ('original','cover')),
                title text, style text NOT NULL, lyrics text NOT NULL DEFAULT '',
                created_at text NOT NULL, updated_at text NOT NULL,
                status text NOT NULL CHECK(status IN ('queued','running','completed','failed','cancelled')),
                seed bigint NOT NULL, settings text NOT NULL, source_filename text,
                creator_id bigint, creator_name text, output_filename text,
                output_subfolder text, output_type text, error text,
                published_at text, cover_filename text, published_title text,
                album_id text, play_count bigint NOT NULL DEFAULT 0, artist_id bigint
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_yue_jobs_created ON jobs(created_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_yue_jobs_status ON jobs(status)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_yue_jobs_published ON jobs(published_at DESC)")
            db.execute("""CREATE TABLE IF NOT EXISTS artist_profiles (
                id bigint PRIMARY KEY, user_id bigint NOT NULL, artist_name text NOT NULL,
                bio text NOT NULL DEFAULT '', avatar_filename text, banner_filename text,
                updated_at text NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_yue_artists_owner ON artist_profiles(user_id)")
            db.execute("""CREATE TABLE IF NOT EXISTS albums (
                id text PRIMARY KEY, owner_id bigint NOT NULL, title text NOT NULL,
                description text NOT NULL, cover_filename text,
                created_at text NOT NULL, updated_at text NOT NULL, artist_id bigint
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_yue_albums_owner ON albums(owner_id, created_at DESC)")

    def list_artists(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute("""SELECT j.artist_id AS artist_id,
                MIN(p.artist_name) AS artist_name, MIN(p.bio) AS bio,
                MIN(p.avatar_filename) AS avatar_filename, MIN(p.banner_filename) AS banner_filename,
                COUNT(*) AS track_count, MAX(j.published_at) AS latest_at,
                MIN(j.creator_name) AS creator_name
                FROM jobs j LEFT JOIN artist_profiles p ON p.id = j.artist_id
                WHERE j.published_at IS NOT NULL AND j.status = 'completed' AND j.artist_id IS NOT NULL
                GROUP BY j.artist_id ORDER BY latest_at DESC LIMIT %s""",
                (max(1, min(limit, 100)),)).fetchall()
        return [dict(row) for row in rows]


class PostgresAuthStore(AuthStore):
    def __init__(self, dsn: str, path: str | Path):
        self.dsn = dsn
        self.path = Path(path)
        with self._connection() as db:
            db.execute("CREATE EXTENSION IF NOT EXISTS citext")
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                username citext NOT NULL UNIQUE, display_name text NOT NULL,
                password_hash text NOT NULL, role text NOT NULL CHECK(role IN ('admin','member')),
                status text NOT NULL CHECK(status IN ('pending','approved','disabled')),
                created_at text NOT NULL, failed_logins integer NOT NULL DEFAULT 0,
                locked_until text
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                token_hash text PRIMARY KEY, user_id bigint NOT NULL REFERENCES users(id),
                csrf_token text NOT NULL, expires_at text NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS invite_codes (
                code citext PRIMARY KEY, created_by bigint REFERENCES users(id),
                max_uses integer NOT NULL DEFAULT 1, uses integer NOT NULL DEFAULT 0,
                created_at text NOT NULL, note text
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_yue_sessions_user ON sessions(user_id)")

    def _connect(self):
        return _Connection(self.dsn)
