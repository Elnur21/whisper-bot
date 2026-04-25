import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from handlers import READ_CB_PREFIX
from services.whisper import RevealStatus

logger = logging.getLogger(__name__)


async def handle_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    clicker = query.from_user
    service = context.bot_data["service"]

    token = query.data[len(READ_CB_PREFIX):]

    # ── Sender peeking at their own whisper ────────────────────────────
    whisper = await service.sender_peek(token, clicker.id)
    if whisper is not None:
        status = "✅ Already revealed." if whisper["is_revealed"] else "⏳ Not opened yet."
        await query.answer(
            # f"Your whisper:\n\n{whisper['message_text']}\n\n{status}",
            f"{whisper['message_text']}",
            show_alert=True,
        )
        return

    # ── Reveal attempt ─────────────────────────────────────────────────
    # Pass clicker's username so the service can match @username-based whispers
    # sent to users who hadn't started the bot yet.
    status, revealed = await service.reveal(
        token, clicker.id, clicker.username, clicker.first_name
    )

    if status is RevealStatus.OK:
        # Register the recipient now that we know who they are.
        # This makes them searchable in future whispers.
        await service.register_user(clicker.id, clicker.username, clicker.first_name, None)
        await query.answer(f"🤫 {revealed['message_text']}", show_alert=True)
        try:
            await query.edit_message_text(
                f"🔓 {clicker.mention_markdown()} mesaja baxdı.",
                parse_mode="Markdown",
            )
        except BadRequest as exc:
            logger.warning("Pıçıltı mesajını redaktə etmək mümkün olmadı: %s", exc)

    elif status is RevealStatus.NOT_TARGET:
        await query.answer("🚫 Bu mesaj sizin üçün deyil!", show_alert=True)

    elif status is RevealStatus.ALREADY_READ:
        await query.answer("✅ Bu mesaj artıq açılıb.", show_alert=True)

    elif status is RevealStatus.EXPIRED:
        await query.answer("⏳ Bu mesajın vaxtı bitib.", show_alert=True)
        try:
            await query.edit_message_text("⏳ Bu mesajın vaxtı bitib.")
        except BadRequest:
            pass

    elif status is RevealStatus.NOT_FOUND:
        await query.answer(
            "❓ Mesaj tapılmadı — ola bilsin silinib.", show_alert=True
        )
