from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import db
import html
import logging
import re

logger = logging.getLogger(__name__)
router = Router()

# Премиум-эмодзи для текста сообщений.
REF_EMOJI = {
    "users": '<tg-emoji emoji-id="5453957997418004470">👥</tg-emoji>',
    "gift": '<tg-emoji emoji-id="5226431245918942763">🎁</tg-emoji>',
    "link": '<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji>',
    "money": '<tg-emoji emoji-id="5463046637842608206">💰</tg-emoji>',
    "info": '<tg-emoji emoji-id="5258503720928288433">ℹ️</tg-emoji>',
    "top": '<tg-emoji emoji-id="5463071033256848094">🔝</tg-emoji>',
    "chick": '<tg-emoji emoji-id="5228822494730797152">🐣</tg-emoji>',
    "copy": '<tg-emoji emoji-id="5431548685198751433">📋</tg-emoji>',
    "green": '<tg-emoji emoji-id="5805523262691611326">🟢</tg-emoji>',
    "wait": '<tg-emoji emoji-id="5447644880824181073">⏳</tg-emoji>',
    "trophy": '<tg-emoji emoji-id="5415865313982054942">🏆</tg-emoji>',
    "star": '<tg-emoji emoji-id="6028477497518068483">⭐</tg-emoji>',
    "bolt": '<tg-emoji emoji-id="5992366958681527437">⚡</tg-emoji>',
    "quote": '<tg-emoji emoji-id="5415842880050868843">💬</tg-emoji>',
    "back": '<tg-emoji emoji-id="5454350746407419714">❌</tg-emoji>',
}

RANK_EMOJIS = [
    '<tg-emoji emoji-id="5789828777882162072">1️⃣</tg-emoji>',
    '<tg-emoji emoji-id="5940802560578294341">2️⃣</tg-emoji>',
    '<tg-emoji emoji-id="5470123568772719703">3️⃣</tg-emoji>',
    '<tg-emoji emoji-id="6104729414883348710">4️⃣</tg-emoji>',
    '<tg-emoji emoji-id="5195234793914121879">5️⃣</tg-emoji>',
    '<tg-emoji emoji-id="5276053794818383335">6️⃣</tg-emoji>',
    '<tg-emoji emoji-id="5195021875205393428">7️⃣</tg-emoji>',
    '<tg-emoji emoji-id="5195249555716717500">8️⃣</tg-emoji>',
    '<tg-emoji emoji-id="5350836180533393550">9️⃣</tg-emoji>',
    '<tg-emoji emoji-id="5377792812622290248">🔟</tg-emoji>',
]


def remove_premium_tags(text: str) -> str:
    return re.sub(r'<tg-emoji\s+emoji-id=".*?">(.*?)</tg-emoji>', r'\1', text)


async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        err_msg = str(e)
        if "DOCUMENT_INVALID" in err_msg or "ENTITY_INVALID" in err_msg or "BAD_REQUEST" in err_msg:
            clean_text = remove_premium_tags(text)
            try:
                await callback.message.edit_text(clean_text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception as ex:
                logger.exception("Ошибка отката текста: %s", ex)
        else:
            logger.exception("Ошибка edit_text: %s", e)


async def safe_send_message(event, text: str, reply_markup=None):
    target = event if isinstance(event, Message) else event.message
    try:
        await target.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        err_msg = str(e)
        if "DOCUMENT_INVALID" in err_msg or "ENTITY_INVALID" in err_msg or "BAD_REQUEST" in err_msg:
            clean_text = remove_premium_tags(text)
            try:
                await target.answer(clean_text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception as ex:
                logger.exception("Ошибка отката сообщения: %s", ex)
        else:
            logger.exception("Ошибка отправки: %s", e)


def display_name(first_name, username, user_id: int) -> str:
    name = (first_name or "").strip()
    username = (username or "").strip().lstrip("@")

    if name and username:
        return f"{name} (@{username})"
    if name:
        return name
    if username:
        return f"@{username}"
    return f"Игрок {user_id}"


def safe_name(first_name, username, user_id: int) -> str:
    return html.escape(display_name(first_name, username, user_id))


async def render_ref_menu(event, bot: Bot):
    user_id = event.from_user.id
    user = db.get_user(user_id) or {}
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    ref_count = int(user.get("ref_count", 0) or 0)
    ref_earned = float(user.get("ref_earned", 0) or 0)

    text = (
        f"{REF_EMOJI['users']} <b>ПРИГЛАСИТЬ ДРУЗЕЙ</b>\n"
        "························\n"
        f"{REF_EMOJI['gift']} Приглашайте друзей по своей ссылке и получайте бонусы:\n"
        "• <b>100'000 nCoin</b> за каждого друга\n"
        "• <b>2%</b> от проигрыша друзей\n\n"
        f"{REF_EMOJI['link']} <b>Твоя ссылка:</b>\n"
        f"↳ <code>{html.escape(ref_link)}</code>\n\n"
        f"{REF_EMOJI['money']} <b>Уже заработано:</b>\n"
        f"↳ <b>{ref_earned:,.0f} nCoin</b>\n\n"
        f"{REF_EMOJI['users']} <b>Приглашено друзей:</b>\n"
        f"↳ <b>{ref_count} чел.</b>\n\n"
        f"{REF_EMOJI['info']} <i>Чтобы друг был зачислен, он должен сыграть хотя бы одну игру в мины или собрать бонус.</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать ссылку", callback_data="ref_copy_link")],
        [
            InlineKeyboardButton(text="🏅 Топ", callback_data="ref_top"),
            InlineKeyboardButton(text="Мои 🐣", callback_data="ref_my_friends"),
        ],
        [InlineKeyboardButton(
            text="Поделиться ➡️",
            switch_inline_query=(
                f"\nЗаходи играть в nCoin Бота со мной! "
                f"Получи 10 000 nCoin на старт: {ref_link}"
            ),
        )],
    ])

    if isinstance(event, Message):
        await safe_send_message(event, text, reply_markup=kb)
    else:
        await safe_edit_text(event, text, reply_markup=kb)


@router.message(F.text.lower().in_({"/ref", "реф", "рефералы"}))
async def ref_menu(message: Message, bot: Bot):
    await render_ref_menu(message, bot)


@router.callback_query(F.data == "ref_copy_link")
async def ref_copy_link_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    await callback.answer("Ссылка отправлена ниже")
    await safe_send_message(
        callback,
        f"{REF_EMOJI['copy']} <b>Твоя ссылка для копирования:</b>\n\n"
        f"<code>{html.escape(ref_link)}</code>"
    )


@router.callback_query(F.data == "ref_top")
async def ref_top_cb(callback: CallbackQuery):
    conn = None
    cursor = None
    current_user_id = callback.from_user.id

    try:
        conn = db.get_conn()
        cursor = conn.cursor()
        
        # Получаем топ 20 лидеров по рефералам
        cursor.execute("""
            SELECT user_id,
                   COALESCE(ref_count, 0),
                   COALESCE(ref_earned, 0),
                   first_name,
                   username
            FROM users
            WHERE COALESCE(ref_count, 0) > 0
            ORDER BY ref_count DESC, ref_earned DESC
            LIMIT 20
        """)
        rows = cursor.fetchall()

        # Получаем данные конкретного пользователя, который нажал кнопку (его позиция, рефералы и заработок)
        cursor.execute("""
            SELECT COUNT(*) + 1 
            FROM users 
            WHERE COALESCE(ref_count, 0) > (
                SELECT COALESCE(ref_count, 0) FROM users WHERE user_id = %s
            )
        """, (current_user_id,))
        user_rank_res = cursor.fetchone()
        user_rank = user_rank_res[0] if user_rank_res else 0

        current_user_data = db.get_user(current_user_id) or {}
        my_ref_count = int(current_user_data.get("ref_count", 0) or 0)
        my_first_name = current_user_data.get("first_name", "")
        my_username = current_user_data.get("username", "")
        my_display_name = (my_first_name or my_username or f"id{current_user_id}").strip()

    except Exception:
        logger.exception("Ошибка загрузки топа рефералов")
        await callback.answer("Не удалось загрузить топ.", show_alert=True)
        return
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # Формируем заголовок в стиле цитаты
    text = f"<blockquote>{REF_EMOJI['trophy']} <b>ЛИДЕРЫ ПО ДРУЗЬЯМ</b> {REF_EMOJI['users']}</blockquote>\n"
    text += "························\n"

    if not rows:
        text += "Пока здесь пусто. Будь первым!\n"
    else:
        for i, row in enumerate(rows):
            u_id, count, earned, first_name, username = row
            name = safe_name(first_name, username, u_id)
            ref_num = int(count or 0)
            
            # Эмодзи для мест 1, 2, 3 и молнии для остальных
            if i == 0:
                rank = f"{REF_EMOJI['star']}"
            elif i == 1:
                rank = f"{REF_EMOJI['star']}"
            elif i == 2:
                rank = f"{REF_EMOJI['star']}"
            else:
                rank = f"{REF_EMOJI['bolt']}"

            text += f"{rank} {i + 1}. {name} | <b>{ref_num} др.</b>\n"

        # Разделитель и блок текущего игрока снизу
    text += "························\n"
    
    # Оборачиваем строку в <blockquote>
    text += f"<blockquote><b>{user_rank}</b>. {REF_EMOJI['trophy']} <b>{html.escape(my_display_name)}</b> | <b>{my_ref_count} чел.</b></blockquote>"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="ref_back_to_menu")]
    ])

    await callback.answer()
    await safe_edit_text(callback, text, reply_markup=keyboard)


@router.callback_query(F.data == "ref_my_friends")
async def ref_my_friends_cb(callback: CallbackQuery):
    conn = None
    cursor = None

    try:
        conn = db.get_conn()
        cursor = conn.cursor()
        
        placeholder = "%s"
        try:
            cursor.execute("SELECT 1 WHERE 1 = %s", (1,))
        except Exception:
            placeholder = "?"

        cursor.execute(f"""
            SELECT user_id,
                   COALESCE(ref_bonus_claimed, 0),
                   first_name,
                   username
            FROM users
            WHERE referrer_id = {placeholder}
            ORDER BY user_id DESC
            LIMIT 20
        """, (callback.from_user.id,))
        rows = cursor.fetchall()
    except Exception:
        logger.exception("Ошибка загрузки списка друзей")
        await callback.answer("Не удалось загрузить список друзей.", show_alert=True)
        return
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    text = f"{REF_EMOJI['chick']} <b>СПИСОК ВАШИХ ДРУЗЕЙ</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"

    if not rows:
        text += "Вы ещё не пригласили друзей."
    else:
        for friend_id, qualified, first_name, username in rows:
            name = safe_name(first_name, username, friend_id)
            status = (
                f"{REF_EMOJI['green']} Активен"
                if qualified
                else f"{REF_EMOJI['wait']} Ожидает активности"
            )
            text += f"• <b>{name}</b> — {status}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="ref_back_to_menu")]
    ])

    await callback.answer()
    await safe_edit_text(callback, text, reply_markup=keyboard)


@router.callback_query(F.data == "ref_back_to_menu")
async def ref_back_to_menu_cb(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    await render_ref_menu(callback, bot)
