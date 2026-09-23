"""Small account and session store for the shared Studio."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SESSION_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_invite_code() -> str:
    chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    part1 = "".join(secrets.choice(chars) for _ in range(4))
    part2 = "".join(secrets.choice(chars) for _ in range(4))
    return f"YUE-{part1}-{part2}"


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024)
    return f"scrypt:32768:8:1:{salt.hex()}:{digest.hex()}"


def _check_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt, digest = stored.split(":")
        if algorithm != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(candidate, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    role: str
    status: str


class AuthStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'member')),
                    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'disabled')),
                    created_at TEXT NOT NULL,
                    failed_logins INTEGER NOT NULL DEFAULT 0,
                    locked_until TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    csrf_token TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS invite_codes (
                    code TEXT PRIMARY KEY COLLATE NOCASE,
                    created_by INTEGER REFERENCES users(id),
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    uses INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    note TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 30000")
        return db

    @contextmanager
    def _connection(self):
        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _user(row: sqlite3.Row) -> User:
        return User(row["id"], row["username"], row["display_name"], row["role"], row["status"])

    def has_admin(self) -> bool:
        with self._connection() as db:
            return db.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone() is not None

    def create_invite_code(
        self,
        code: str | None = None,
        *,
        created_by: int | None = None,
        max_uses: int = 1,
        note: str = "",
    ) -> str:
        clean_code = (code.strip().upper() if code else _generate_invite_code())
        if not (4 <= len(clean_code) <= 32):
            raise ValueError("초대 코드는 4~32자여야 합니다.")
        with self._connection() as db:
            try:
                db.execute(
                    "INSERT INTO invite_codes (code, created_by, max_uses, uses, created_at, note) VALUES (?, ?, ?, 0, ?, ?)",
                    (clean_code, created_by, max(1, int(max_uses)), _now().isoformat(), note.strip()),
                )
            except sqlite3.IntegrityError:
                raise ValueError("이미 존재하는 초대 코드입니다.")
        return clean_code

    def validate_and_consume_invite(self, code: str) -> bool:
        clean_code = code.strip().upper()
        if not clean_code:
            return False
        env_code = (os.environ.get("YUE2_INVITE_CODE") or "").strip().upper()
        if env_code and hmac.compare_digest(clean_code, env_code):
            return True
        with self._connection() as db:
            row = db.execute(
                "SELECT code, max_uses, uses FROM invite_codes WHERE code = ? COLLATE NOCASE",
                (clean_code,),
            ).fetchone()
            if row is None:
                return False
            if row["uses"] >= row["max_uses"]:
                return False
            db.execute(
                "UPDATE invite_codes SET uses = uses + 1 WHERE code = ? COLLATE NOCASE",
                (clean_code,),
            )
            return True

    def list_invite_codes(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                """SELECT i.code, i.max_uses, i.uses, i.created_at, i.note, u.username as creator
                   FROM invite_codes i
                   LEFT JOIN users u ON u.id = i.created_by
                   ORDER BY i.created_at DESC"""
            ).fetchall()
            return [
                {
                    "code": row["code"],
                    "max_uses": row["max_uses"],
                    "uses": row["uses"],
                    "remaining": max(0, row["max_uses"] - row["uses"]),
                    "created_at": row["created_at"],
                    "note": row["note"] or "",
                    "creator": row["creator"] or "시스템",
                }
                for row in rows
            ]

    def create_user(
        self,
        username: str,
        display_name: str,
        password: str,
        *,
        invite_code: str | None = None,
        admin: bool = False,
        status: str | None = None,
    ) -> User:
        username = username.strip().lower()
        display_name = display_name.strip()
        if not (3 <= len(username) <= 32) or not all(c.isascii() and (c.isalnum() or c in "_-") for c in username):
            raise ValueError("아이디는 영문·숫자·_·- 3~32자로 입력하세요.")
        if not (1 <= len(display_name) <= 40):
            raise ValueError("이름은 1~40자로 입력하세요.")
        if not (12 <= len(password) <= 256):
            raise ValueError("비밀번호는 12~256자로 입력하세요.")

        if admin:
            user_status = "approved"
        elif invite_code:
            if not self.validate_and_consume_invite(invite_code):
                raise ValueError("초대 코드가 올바르지 않거나 이미 모두 사용되었습니다.")
            user_status = "approved"
        elif status:
            user_status = status
        else:
            raise ValueError("초대 코드를 입력하세요.")

        password_hash = _hash_password(password)
        with self._connection() as db:
            try:
                cursor = db.execute(
                    "INSERT INTO users(username, display_name, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (username, display_name, password_hash, "admin" if admin else "member", user_status, _now().isoformat()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("이미 사용 중인 아이디입니다.") from error
            return User(cursor.lastrowid, username, display_name, "admin" if admin else "member", user_status)

    def create_initial_admin(self, username: str, display_name: str, password: str) -> User:
        username = username.strip().lower()
        display_name = display_name.strip()
        if not (3 <= len(username) <= 32) or not all(c.isascii() and (c.isalnum() or c in "_-") for c in username):
            raise ValueError("아이디는 영문·숫자·_·- 3~32자로 입력하세요.")
        if not (1 <= len(display_name) <= 40):
            raise ValueError("이름은 1~40자로 입력하세요.")
        if not (12 <= len(password) <= 256):
            raise ValueError("비밀번호는 12~256자로 입력하세요.")
        password_hash = _hash_password(password)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone():
                raise ValueError("관리자가 이미 설정되었습니다.")
            try:
                cursor = db.execute(
                    "INSERT INTO users(username, display_name, password_hash, role, status, created_at) VALUES (?, ?, ?, 'admin', 'approved', ?)",
                    (username, display_name, password_hash, _now().isoformat()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("이미 사용 중인 아이디입니다.") from error
            admin_user = User(cursor.lastrowid, username, display_name, "admin", "approved")

        # Automatically issue an initial invite code for the admin
        try:
            self.create_invite_code(code="YUE-WELCOME", created_by=admin_user.id, max_uses=10, note="초기 환영 초대 코드")
        except Exception:
            pass

        return admin_user

    def authenticate(self, username: str, password: str) -> User | None:
        with self._connection() as db:
            row = db.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)).fetchone()
            if row is None:
                return None
            if row["locked_until"] and row["locked_until"] > _now().isoformat():
                return None
            if not _check_password(password, row["password_hash"]):
                failures = row["failed_logins"] + 1
                lock = (_now() + timedelta(minutes=15)).isoformat() if failures >= 5 else None
                db.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?", (failures, lock, row["id"]))
                return None
            db.execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (row["id"],))
            return self._user(row)

    def create_session(self, user_id: int) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with self._connection() as db:
            db.execute("DELETE FROM sessions WHERE user_id = ? OR expires_at <= ?", (user_id, _now().isoformat()))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                       (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, (_now() + timedelta(days=SESSION_DAYS)).isoformat()))
        return token, csrf

    def session(self, token: str) -> tuple[User, str] | None:
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._connection() as db:
            row = db.execute("""SELECT users.*, sessions.csrf_token FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?""", (digest, _now().isoformat())).fetchone()
            if row is None or row["status"] != "approved":
                return None
            return self._user(row), row["csrf_token"]

    def delete_session(self, token: str) -> None:
        with self._connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))

    def pending_users(self) -> list[User]:
        with self._connection() as db:
            return [self._user(row) for row in db.execute("SELECT * FROM users WHERE status = 'pending' ORDER BY created_at")]

    def set_status(self, user_id: int, status: str) -> bool:
        if status not in {"approved", "disabled"}:
            raise ValueError("invalid status")
        with self._connection() as db:
            cursor = db.execute("UPDATE users SET status = ? WHERE id = ? AND role = 'member'", (status, user_id))
            if status == "disabled":
                db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            return cursor.rowcount > 0
