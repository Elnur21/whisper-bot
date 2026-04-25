import logging
from datetime import datetime
from typing import Optional

from database.db import Database

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        chat_id: Optional[int],
    ) -> None:
        await self._db.conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, chat_id, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = COALESCE(excluded.username,   username),
                first_name = COALESCE(excluded.first_name, first_name),
                chat_id    = COALESCE(excluded.chat_id,    chat_id),
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, username.lower() if username else None, first_name, chat_id),
        )
        await self._db.conn.commit()

    async def search_by_username(self, prefix: str, limit: int = 8) -> list[dict]:
        async with self._db.conn.execute(
            "SELECT user_id, username, first_name FROM users "
            "WHERE username LIKE ? LIMIT ?",
            (f"{prefix.lower()}%", limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def search_by_id(self, prefix: str, limit: int = 8) -> list[dict]:
        async with self._db.conn.execute(
            "SELECT user_id, username, first_name FROM users "
            "WHERE CAST(user_id AS TEXT) LIKE ? LIMIT ?",
            (f"{prefix}%", limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


class WhisperRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        token: str,
        sender_id: int,
        sender_label: str,
        message_text: str,
        expires_at: Optional[datetime] = None,
        target_user_id: Optional[int] = None,
        target_username: Optional[str] = None,
        target_name: Optional[str] = None,
    ) -> int:
        expires_iso = expires_at.isoformat() if expires_at else None
        async with self._db.conn.execute(
            """
            INSERT INTO whispers
                (token, sender_id, sender_label, target_user_id, target_username,
                 target_name, message_text, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token, sender_id, sender_label, target_user_id,
                target_username.lower() if target_username else None,
                target_name,
                message_text, expires_iso,
            ),
        ) as cur:
            row_id = cur.lastrowid
        await self._db.conn.commit()
        return row_id

    async def update_target_user_id(
        self, token: str, user_id: int, name: Optional[str] = None
    ) -> None:
        """Once a username-targeted whisper is revealed, lock in the real user_id and name."""
        await self._db.conn.execute(
            """UPDATE whispers
               SET target_user_id  = ?,
                   target_username = NULL,
                   target_name     = COALESCE(?, target_name)
               WHERE token = ?""",
            (user_id, name, token),
        )
        await self._db.conn.commit()

    async def get_by_token(self, token: str) -> Optional[dict]:
        async with self._db.conn.execute(
            "SELECT * FROM whispers WHERE token = ?", (token,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def reveal(self, token: str) -> bool:
        """
        Atomic reveal: sets is_revealed=1 only if currently 0 and not expired.
        Returns True exactly once — the request that actually flipped the flag.
        """
        async with self._db.conn.execute(
            """
            UPDATE whispers SET is_revealed = 1
            WHERE token     = ?
              AND is_revealed = 0
              AND (expires_at IS NULL OR expires_at > datetime('now'))
            """,
            (token,),
        ) as cur:
            changed = cur.rowcount
        await self._db.conn.commit()
        return changed == 1

    async def delete_expired(self) -> int:
        async with self._db.conn.execute(
            "DELETE FROM whispers "
            "WHERE expires_at IS NOT NULL AND expires_at <= datetime('now')"
        ) as cur:
            count = cur.rowcount
        await self._db.conn.commit()
        return count
