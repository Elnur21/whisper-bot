import base64
import os

_ENABLED = os.getenv("ENCODE_MESSAGE", "false").lower() == "true"


def encode_message(text: str) -> str:
    if not _ENABLED:
        return text
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def decode_message(text: str) -> str:
    if not _ENABLED:
        return text
    try:
        return base64.b64decode(text.encode("ascii")).decode("utf-8")
    except Exception:
        # Stored before encoding was enabled — return as-is
        return text
