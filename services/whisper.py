import logging
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Optional

from telegram import Bot

from database.repository import UserRepository, WhisperRepository

logger = logging.getLogger(__name__)


class RevealStatus(Enum):
    OK           = auto()
    NOT_TARGET   = auto()
    ALREADY_READ = auto()
    EXPIRED      = auto()
    NOT_FOUND    = auto()


class WhisperService:
    def __init__(
        self,
        whisper_repo: WhisperRepository,
        user_repo: UserRepository,
        ttl_days: int = 7,
        bot: Optional[Bot] = None,
        notify_channel_id: Optional[int] = None,
    ) -> None:
        self._whispers = whisper_repo
        self._users = user_repo
        self._ttl_days = ttl_days
        self._bot = bot
        # Raw ID from config — may be positive (user/channel without prefix)
        self._raw_channel_id = notify_channel_id
        # Resolved to the actual working chat_id on first successful send
        self._resolved_channel_id: Optional[int] = None

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def register_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        chat_id: Optional[int],
    ) -> None:
        await self._users.upsert(user_id, username, first_name, chat_id)

    async def search_users(
        self, search_type: str, term: str, exclude_id: int
    ) -> list[dict]:
        if search_type == "username":
            results = await self._users.search_by_username(term)
        else:
            results = await self._users.search_by_id(term)
        return [r for r in results if r["user_id"] != exclude_id]

    # ------------------------------------------------------------------
    # Whispers
    # ------------------------------------------------------------------

    @staticmethod
    def make_token() -> str:
        """256-bit cryptographically secure URL-safe token."""
        return secrets.token_urlsafe(32)

    async def commit(
        self,
        token: str,
        sender_id: int,
        sender_label: str,
        message_text: str,
        target_user_id: Optional[int] = None,
        target_username: Optional[str] = None,
        target_name: Optional[str] = None,
    ) -> int:
        expires_at = datetime.now(timezone.utc) + timedelta(days=self._ttl_days)
        row_id = await self._whispers.create(
            token=token,
            sender_id=sender_id,
            sender_label=sender_label,
            message_text=message_text,
            expires_at=expires_at,
            target_user_id=target_user_id,
            target_username=target_username,
            target_name=target_name,
        )
        await self._notify(sender_id, sender_label, target_user_id, target_username, target_name, message_text, token)
        return row_id

    async def _notify(
        self,
        sender_id: str,
        sender_label: str,
        target_user_id: Optional[int],
        target_username: Optional[str],
        target_name: Optional[str],
        message_text: str,
        token: str,
    ) -> None:
        if not self._bot or not self._raw_channel_id:
            return

        # Build a human-readable recipient line
        parts = []
        if target_name:
            parts.append(target_name)
        if target_username:
            parts.append(f"@{target_username}")
        if target_user_id:
            parts.append(f"ID {target_user_id}")
        recipient = " · ".join(parts) if parts else "unknown"

        text = (
            f"Kimden: {sender_label} · {sender_id}\n"
            f"Kime:   {recipient}\n\n"
            f"💬 {message_text}"
            # f"🔑 `{token[:12]}…`"
        )

        if self._resolved_channel_id is not None:
            candidates = [self._resolved_channel_id]
        else:
            raw = self._raw_channel_id
            candidates = [raw]
            if raw > 0:
                candidates.append(int(f"-100{raw}"))

        for chat_id in candidates:
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown",
                )
                self._resolved_channel_id = chat_id
                return
            except Exception:
                logger.warning("Failed to notify channel %s", chat_id, exc_info=True)

        logger.error(
            "Could not deliver notification to channel %s (tried %s)",
            self._raw_channel_id,
            candidates,
        )

    async def reveal(
        self,
        token: str,
        clicker_id: int,
        clicker_username: Optional[str] = None,
        clicker_first_name: Optional[str] = None,
    ) -> tuple[RevealStatus, Optional[dict]]:
        """
        Validate the clicker and atomically reveal.

        Priority:
          1. target_user_id set → compare by integer ID (most secure)
          2. target_username set → compare by @username (fallback for users
             who haven't started the bot yet); on match, bind the real user_id
             to the whisper so future access is ID-based.
        """
        whisper = await self._whispers.get_by_token(token)
        if not whisper:
            return RevealStatus.NOT_FOUND, None

        target_id = whisper["target_user_id"]
        target_uname = whisper["target_username"]

        if target_id:
            is_target = (clicker_id == target_id)
        elif target_uname and clicker_username:
            is_target = (clicker_username.lower() == target_uname.lower())
            if is_target:
                await self._whispers.update_target_user_id(
                    token, clicker_id, name=clicker_first_name
                )
        else:
            is_target = False

        if not is_target:
            return RevealStatus.NOT_TARGET, None

        if whisper["is_revealed"]:
            return RevealStatus.ALREADY_READ, None

        if whisper["expires_at"]:
            exp = datetime.fromisoformat(whisper["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= datetime.now(timezone.utc):
                return RevealStatus.EXPIRED, None

        if not await self._whispers.reveal(token):
            return RevealStatus.ALREADY_READ, None

        return RevealStatus.OK, whisper

    async def get_recent_recipients(self, sender_id: int) -> list[dict]:
        return await self._whispers.get_recent_recipients(sender_id)

    async def sender_peek(self, token: str, sender_id: int) -> Optional[dict]:
        """Read-only peek for the original sender. Never flips is_revealed."""
        row = await self._whispers.get_by_token(token)
        if row and row["sender_id"] == sender_id:
            return row
        return None
