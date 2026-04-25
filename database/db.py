import logging
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    chat_id     INTEGER,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username
    ON users(username);

CREATE TABLE IF NOT EXISTS whispers (
    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    token           TEXT     NOT NULL UNIQUE,
    sender_id       INTEGER  NOT NULL,
    sender_label    TEXT     NOT NULL,
    target_user_id  INTEGER,              -- NULL when target hasn't started the bot yet
    target_username TEXT,                 -- @username fallback when user_id is unknown
    target_name     TEXT,                 -- display name of the target (NULL if unknown)
    message_text    TEXT     NOT NULL,
    is_revealed     INTEGER  NOT NULL DEFAULT 0 CHECK(is_revealed IN (0, 1)),
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_whispers_token
    ON whispers(token);
CREATE INDEX IF NOT EXISTS idx_whispers_target
    ON whispers(target_user_id);
CREATE INDEX IF NOT EXISTS idx_whispers_expires
    ON whispers(expires_at) WHERE expires_at IS NOT NULL;
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._drop_incompatible_tables()
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        logger.info("Database ready: %s", self.db_path)

    async def _drop_incompatible_tables(self) -> None:
        """
        Detect schema mismatches and migrate before the DDL runs.
        - whispers table: incompatible (drop & recreate — no real data yet)
        - users table:    additive change (ALTER TABLE to preserve existing users)
        """
        # whispers: drop if token or target_username column is missing
        try:
            await self._conn.execute(
                "SELECT token, target_username FROM whispers LIMIT 0"
            )
        except aiosqlite.OperationalError:
            logger.warning("Incompatible whispers schema — dropping and recreating")
            await self._conn.execute("DROP TABLE IF EXISTS whispers")
            await self._conn.commit()

        # whispers: target_name is a new nullable column — add without recreating
        try:
            await self._conn.execute("SELECT target_name FROM whispers LIMIT 0")
        except aiosqlite.OperationalError:
            logger.warning("Adding missing target_name column to whispers table")
            await self._conn.execute(
                "ALTER TABLE whispers ADD COLUMN target_name TEXT"
            )
            await self._conn.commit()

        # users: old schema has no `updated_at` column → add it non-destructively.
        # SQLite ALTER TABLE cannot use non-constant defaults (CURRENT_TIMESTAMP),
        # so we allow NULL here; the upsert always writes CURRENT_TIMESTAMP anyway.
        try:
            await self._conn.execute("SELECT updated_at FROM users LIMIT 0")
        except aiosqlite.OperationalError:
            logger.warning("Adding missing updated_at column to users table")
            await self._conn.execute(
                "ALTER TABLE users ADD COLUMN updated_at TIMESTAMP"
            )
            await self._conn.commit()

        # users: old schema has no `first_name` column → add it non-destructively
        try:
            await self._conn.execute("SELECT first_name FROM users LIMIT 0")
        except aiosqlite.OperationalError:
            logger.warning("Adding missing first_name column to users table")
            await self._conn.execute(
                "ALTER TABLE users ADD COLUMN first_name TEXT"
            )
            await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            logger.info("Database connection closed")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() was never awaited")
        return self._conn
