from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    service = context.bot_data["service"]
    await service.register_user(user.id, user.username, user.first_name, update.effective_chat.id)

    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(
       f"👋 Salam {user.first_name}! Mən *Whisper Bot* 🤫\n\n",
       "Seçdiyin alıcıdan başqa heç kimin görə bilməyəcəyi gizli mesaj göndər.\n\n",
       "*İstifadə qaydası* (istənilən qrup və çatda işləyir):\n",
       f"1️⃣ Məni tag et: `@{bot_username}`\n",
       "2️⃣ Alıcını yaz: `@alice` — kontakt siyahısı açılacaq\n",
       "3️⃣ Mesajını yaz: `@alice Salam, mənə zəng et!`\n",
       "4️⃣ Siyahıdan şəxsi seç → pıçıltı möhürlənir 🔒\n\n",
       "🔒 *Alıcı* Oxu düyməsinə basır → mesaj açılır, düymə silinir.\n",
       "👁 *Göndərən* Oxu düyməsinə basır → açmadan statusa baxır.\n",
       "🚫 *Digərləri* → bunun onlar üçün olmadığı bildirilir.\n\n",
       "Mesajlar 7 gün sonra avtomatik silinir.",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(
        "🤫 *Whisper Bot — Kömək*\n\n",
        "*Format:*\n",
        f"`@{bot_username} Mesajınız @istifadəçi_adı`\n",
        f"`@{bot_username} Mesajınız user_id`\n\n",
        "İstifadəçi adından əvvəl mesajı əlavə edin.\n\n",
        "Sonra `@istifadəçi_adı` yazın — uyğun kontaktlar dərhal görünəcək.,sonra göndərmək üçün kontaktı seçin.\n",
        "Yalnız göstərilən alıcı mesajı aça bilər. Mesajlar 7 gün sonra silinir.",
        parse_mode="Markdown",
    )
