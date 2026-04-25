import logging
import re
from uuid import uuid4

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import ContextTypes

from handlers import READ_CB_PREFIX

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_query(raw: str):
    """
    Format:  @username_search [message text]
             user_id          [message text]

    First token is the recipient search term.
    Everything after the first whitespace is the message.
    Returns (message, search_type, search_term) or (None, None, None).
    """
    raw = raw.strip()
    if not raw:
        return None, None, None

    # parts = raw.split(None, 1)
    # first = parts[0]
    # message = parts[1].strip() if len(parts) > 1 else None
    parts = raw.rsplit(None, 1)

    first = parts[1]
    message = parts[0].strip() if len(parts) > 1 else None

    if first.startswith("@"):
        return message, "username", first[1:]   # search_term may be ""

    if re.match(r"^\d{3,}$", first):
        return message, "user_id", first

    return None, None, None


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _row_label(row: dict) -> str:
    name = (row.get("first_name") or "").strip()
    uname = row.get("username")
    if name and uname:
        # return f"{name} (@{uname})"
        return f"{name}"
    if name:
        # return f"{name} · ID {row['user_id']}"
        return f"{name}"
    if uname:
        return f"@{uname}"
    return f"İstifadəçi {row['user_id']}"


def _sender_label(user) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name or f"İstifadəçi {user.id}"


def _hint(title: str, description: str) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=str(uuid4()),
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(title),
    )


def _read_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔒 Oxu", callback_data=f"{READ_CB_PREFIX}{token}")
    ]])


def _whisper_card(token: str, recipient_label: str, preview: str) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=token,
        title=f"🤫 {recipient_label} üçün pıçılda",
        description=preview,
        reply_markup=_read_keyboard(token),
        input_message_content=InputTextMessageContent(
           f"🔒 *{recipient_label} üçün gizli mesaj*\n_Açmaq üçün 🔒 Oxu düyməsinə toxun._",
            parse_mode="Markdown",
        ),
    )


# ---------------------------------------------------------------------------
# Inline query handler
# ---------------------------------------------------------------------------

async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender = update.inline_query.from_user
    raw = update.inline_query.query
    service = context.bot_data["service"]
    rate_limiter = context.bot_data["rate_limiter"]

    await service.register_user(sender.id, sender.username, sender.first_name, None)

    # ── Empty query ────────────────────────────────────────────────────────
    if not raw.strip():
        await update.inline_query.answer(
            [_hint(
                "🔍 Alıcı tapmaq üçün @username yada id yazın"
                "Nümunə: Salam, mənə zəng et! @alice yada 123456789",
            )],
            cache_time=0,
        )
        return

    message, search_type, search_term = _parse_query(raw)

    # ── First token is not @... or digits ──────────────────────────────────
    if search_term is None:
        await update.inline_query.answer(
            [_hint(
                "🤫 @username və ya istifadəçi ID-si ilə bitirin mesajı"
                "Nümunə: Salam, mənə zəng et! (@alice yada 123456789)",
            )],
            cache_time=0,
        )
        return

    # ── Search DB ──────────────────────────────────────────────────────────
    matches = await service.search_users(search_type, search_term, exclude_id=sender.id)

    # ── Bare @ with nobody in DB ───────────────────────────────────────────
    if not matches and not search_term:
        await update.inline_query.answer(
            [_hint(
                "❌ Qeydiyyatdan keçmiş istifadəçi tapılmadı",
                "Alıcılardan əvvəlcə botu /start etmələrini xahiş edin.",
            )],
            cache_time=0,
        )
        return

    # ── Specific tag/ID typed but not in DB ────────────────────────────────
    # Still allow sending — recipient identified by @username or raw ID.
    # When they click Read, their real user_id is captured and registered.
    if not matches:
        if search_type == "username":
            recipient_label = f"@{search_term}"
            tuid, tuname = None, search_term
        else:
            recipient_label = f"istifadəçi {search_term}"
            tuid, tuname = int(search_term), None

        if not message:
            await update.inline_query.answer(
                [_hint(
                    f"👤 {recipient_label} — hələ qeydiyyatdan keçməyib",
                    "Mesajı göndərmək üçün istifadəçi adından əvvəl yazın",
                )],
                cache_time=0,
            )
            return

        if not rate_limiter.is_allowed(sender.id):
            retry = int(rate_limiter.retry_after(sender.id))
            await update.inline_query.answer(
                [_hint("⏳ Bir az yavaşla!", f"{retry} saniyədən sonra yenidən cəhd edin.")], cache_time=0
            )
            return

        token = service.make_token()
        await service.commit(
            token=token,
            sender_id=sender.id,
            sender_label=_sender_label(sender),
            message_text=message,
            target_user_id=tuid,
            target_username=tuname,
            target_name=None,   # unregistered — name unknown until they click Read
        )
        preview = message if len(message) <= 60 else message[:57] + "…"
        await update.inline_query.answer(
            [_whisper_card(token, recipient_label, preview)],
            cache_time=0,
        )
        return

    # ── Found users but no message typed yet ───────────────────────────────
    if not message:
        results = []
        for match in matches:
            label = _row_label(match)
            results.append(InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"👤 {label}",
                description="✏️ Pıçıltı göndərmək üçün mesajı yazmağa davam edin",
                input_message_content=InputTextMessageContent(
                    f"{label} üçün pıçıldamaq üçün mesajı inline sahəyə əlavə edin."
                ),
            ))
        await update.inline_query.answer(results, cache_time=0)
        return

    # ── Rate limit ─────────────────────────────────────────────────────────
    if not rate_limiter.is_allowed(sender.id):
        retry = int(rate_limiter.retry_after(sender.id))
        await update.inline_query.answer(
            [_hint("⏳ Bir az yavaşla!", f"Həddindən artıq pıçıltı. {retry} saniyədən sonra yenidən cəhd edin.")],
            cache_time=0,
        )
        return

    # ── Commit whispers to DB immediately and return selectable cards ───────
    # Saving here (not in chosen_inline_result) guarantees the token exists in
    # the DB before anyone can tap the Read button, regardless of whether
    # BotFather's Inline Feedback is enabled.
    sender_lbl = _sender_label(sender)
    preview = message if len(message) <= 60 else message[:57] + "…"
    results = []

    for match in matches:
        token = service.make_token()
        recipient_label = _row_label(match)

        await service.commit(
            token=token,
            sender_id=sender.id,
            sender_label=sender_lbl,
            message_text=message,
            target_user_id=match["user_id"],
            target_username=match.get("username"),
            target_name=match.get("first_name") or None,
        )
        results.append(_whisper_card(token, recipient_label, preview))
        logger.info(
           "Pıçıltı hazırdır — token=%.8s… hədəf=%s",
            token, match["user_id"],
        )

    await update.inline_query.answer(results, cache_time=0)
