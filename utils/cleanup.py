import asyncio
import logging

from database.repository import WhisperRepository

logger = logging.getLogger(__name__)


async def run_cleanup(repo: WhisperRepository, interval: int = 3600) -> None:
    """Background task: periodically hard-delete expired whispers."""
    while True:
        await asyncio.sleep(interval)
        try:
            count = await repo.delete_expired()
            if count:
                logger.info("Cleanup: removed %d expired whisper(s)", count)
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
            raise
        except Exception:
            logger.exception("Cleanup task error — will retry next cycle")
