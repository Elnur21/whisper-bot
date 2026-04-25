import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
DB_PATH: str = os.getenv("DB_PATH", "whisper.db")

# Chat/channel that receives a copy of every committed whisper (0 = disabled)
NOTIFY_CHANNEL_ID: int = int(os.getenv("NOTIFY_CHANNEL_ID", "0"))

# Whispers are auto-expired after this many days
WHISPER_TTL_DAYS: int = int(os.getenv("WHISPER_TTL_DAYS", "7"))

# Per-user rate limit: max N whispers per window (seconds)
RATE_LIMIT_MAX: int = int(os.getenv("RATE_LIMIT_MAX", "5"))
RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# How often the background cleanup job runs (seconds)
CLEANUP_INTERVAL: int = int(os.getenv("CLEANUP_INTERVAL", "3600"))
