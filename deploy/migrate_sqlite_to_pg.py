"""One-time, guarded migration of existing Studio accounts and library data."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yue2_app.pg_store import PostgresAuthStore, PostgresRepository


TABLES = ("users", "sessions", "invite_codes", "artist_profiles", "albums", "jobs")


def main() -> None:
    dsn = os.environ.get("YUE2_DATABASE_URL")
    if not dsn:
        env_path = Path(__file__).resolve().parents[1] / "secrets" / "studio.env"
        dsn = next(line.split("=", 1)[1] for line in env_path.read_text().splitlines()
                   if line.startswith("YUE2_DATABASE_URL="))
    source_path = Path(__file__).resolve().parents[1] / "yue2_app" / "data" / "yue2.sqlite3"
    if not source_path.is_file():
        raise RuntimeError("source SQLite database missing")
    PostgresRepository(dsn, source_path.parent)
    PostgresAuthStore(dsn, source_path)
    with sqlite3.connect(source_path) as source, psycopg.connect(dsn) as target:
        source.row_factory = sqlite3.Row
        for table in TABLES:
            existing = target.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
            if existing:
                raise RuntimeError(f"destination table {table} is not empty")
        for table in TABLES:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                print(table, 0)
                continue
            names = list(rows[0].keys())
            statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(", ").join(map(sql.Identifier, names)),
                sql.SQL(", ").join(sql.Placeholder() for _ in names),
            )
            with target.cursor() as cursor:
                cursor.executemany(statement, [tuple(row[name] for name in names) for row in rows])
            print(table, len(rows))
        target.execute("SELECT setval(pg_get_serial_sequence('users','id'), GREATEST(COALESCE(MAX(id),0),1), MAX(id) IS NOT NULL) FROM users")
        for table in TABLES:
            source_count = source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            target_count = target.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
            if source_count != target_count:
                raise RuntimeError(f"row count mismatch in {table}")
    print("Migration verified")


if __name__ == "__main__":
    main()
