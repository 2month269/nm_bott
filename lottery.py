import json
import logging
import time
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

import db

logger = logging.getLogger(__name__)
router = Router()

# 📌 ССЫЛКА НА ВАШ VERCEL ВЕБ-АПП
LOTTERY_WEBAPP_URL = "https://lottery-red-six.vercel.app/"

# =====================================================================
# 🎭 ПРЕМИУМ-ЭМОДЗИ
# =====================================================================
EMOJI_LOTTERY_ID = "5463172695132745432"
EMOJI_GIFT_ID = "5226431245918942763"
EMOJI_BOOM_ID = "5226813248900187912"
EMOJI_MONEY_ID = "5463046637842608206"
EMOJI_CARD_ID = "5472250091332993630"
EMOJI_TIME_ID = "5467583879948803288"


def make_emoji(emoji_id: str, fallback: str) -> str:
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


EMOJI_LOTTERY = make_emoji(EMOJI_LOTTERY_ID, "📦")
EMOJI_GIFT = make_emoji(EMOJI_GIFT_ID, "🎁")
EMOJI_BOOM = make_emoji(EMOJI_BOOM_ID, "💥")
EMOJI_MONEY = make_emoji(EMOJI_MONEY_ID, "💰")
EMOJI_CARD = make_emoji(EMOJI_CARD_ID, "💳")
EMOJI_TIME = make_emoji(EMOJI_TIME_ID, "⏳")


def fmt_ncoin(value: float) -> str:
    value = float(value or 0)
    if value < 1:
        return "0"
    if abs(value - round(value)) < 1e-9:
        return f"{int(value):,}".replace(",", "'")
    return f"{value:,.2f}".replace(",", "'")


# =====================================================================
# 🛠 ПРЯМАЯ НАДЁЖНАЯ РАБОТА С БАЗОЙ ДАННЫХ ДЛЯ КУЛДАУНА
# =====================================================================

def get_last_lottery_time_direct(user_id: int) -> int:
    """Прямой запрос к базе данных без посредников"""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        # 1. Проверяем/создаем колонку в БД автоматически
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_lottery_time BIGINT DEFAULT 0;")
        conn.commit()

        # 2. Читаем время последнего запуска
        cursor.execute("SELECT last_lottery_time FROM users WHERE user_id = %s;", (user_id,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return 0
    except Exception as e:
        logger.error(f"Ошибка получения last_lottery_time: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()


def set_last_lottery_time_direct(user_id: int, timestamp: int):
    """Прямая запись времени кулдауна в базу данных"""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_lottery_time BIGINT DEFAULT 0;")
        cursor.execute("UPDATE users SET last_lottery_time = %s WHERE user_id = %s;", (timestamp, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка записи last_lottery_time: {e}")
    finally:
        cursor.close()
        conn.close()


# =====================================================================
# 🎮 ОСНОВНАЯ ЛОГИКА
# =====================================================================

@router.message(Command("lottery"))
@router.message(F.text.lower().in_(["лотерея", "лото", "/lottery"]))
async def lottery_start_cmd(message: Message, state: FSMContext, bot: Bot):
    await state.clear()

    # 1. Проверка на работу в группах
    if message.chat.type in ["group", "supergroup"]:
        bot_info = await bot.get_me()
        bot_url = f"https://t.me/{bot_info.username}?lottery=lottery"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💬 Перейти в бота", url=bot_url)]
            ]
        )
        return await message.answer(
            "⚠️ <b>Эта функция доступна только в личных сообщениях с ботом!</b>",
            reply_markup=kb,
            parse_mode="HTML",
        )

    # 2. Прямая проверка времени из БД
    user_id = message.from_user.id
    current_time = int(time.time())
    last_time = get_last_lottery_time_direct(user_id)
    cooldown = 43200  # 12 часов (43 200 секунд)

    if current_time - last_time < cooldown:
        left = cooldown - (current_time - last_time)
        hours = left // 3600
        minutes = (left % 3600) // 60
        return await message.answer(
            f"<blockquote>{EMOJI_TIME} <b>Лотерея перезаряжается!</b>\n"
            f"Следующая бесплатная попытка будет доступна через: <b>{hours}ч {minutes}м</b>.</blockquote>",
            parse_mode="HTML",
        )

    # Клавиатура с кнопкой WebApp
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🎰 Испытать удачу (Web App)",
                    web_app=WebAppInfo(url=LOTTERY_WEBAPP_URL),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    text = (
        f"{EMOJI_LOTTERY} <b>Бесплатная Лотерея nCoin</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Нажмите на кнопку ниже, чтобы открыть таинственную сумку!\n\n"
        f"🎁 <b>Возможные сокровища:</b>\n"
        f"├ 🪙 Награда: <b>10'000 – 25'000 n¢</b>\n"
        f"├ 🔥 Джекпот: <b>35'000 – 79'999 n¢</b>\n"
        f"└ 💥 Ловушка: <b>0 n¢ (Бомба)</b>\n\n"
        f"<i>⚠️ Бесплатная попытка выдается 1 раз в 12 часов!</i>"
    )

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.web_app_data)
async def process_web_app_lottery_data(message: Message):
    """Принимает зашифрованные данные из WebApp браузера"""
    user_id = message.from_user.id
    current_time = int(time.time())
    last_time = get_last_lottery_time_direct(user_id)
    cooldown = 43200  # 12 часов

    # Удаляем Reply-кнопку
    remove_kb_msg = await message.answer(
        "⚡️ Данные лотереи обработаны...", reply_markup=ReplyKeyboardRemove()
    )
    try:
        await remove_kb_msg.delete()
    except Exception:
        pass

    # Строгая проверка кулдауна при получении ответа от WebApp
    if current_time - last_time < cooldown:
        return await message.answer("❌ Вы уже использовали попытку в эти 12 часов!")

    try:
        data = json.loads(message.web_app_data.data)
        amount = int(data.get("amount", 0))
        is_win = bool(data.get("win", False))
    except Exception as e:
        logger.error("Ошибка парсинга WebApp данных лотереи: %s", e)
        return await message.answer("❌ Ошибка обработки результатов лотереи.")

    # ПРЯМАЯ ЗАПИСЬ КУЛДАУНА В БД СРАЗУ ПОСЛЕ ОТКРЫТИЯ СУМКИ
    set_last_lottery_time_direct(user_id, current_time)

    # При проигрыше
    if not is_win or amount <= 0:
        return await message.answer(
            f"<blockquote>{EMOJI_BOOM} <b>В сумке оказалась БОМБА!</b>\n"
            f"Удача улыбнется в следующий раз. Возвращайтесь через 12 часов!</blockquote>",
            parse_mode="HTML",
        )

    # При выигрыше создаем кнопку забора
    text = (
        f"{EMOJI_GIFT} <b>Лотерейная Сумка Открыта!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Вы нашли внутри: <b>{fmt_ncoin(amount)} nCoin</b>!\n\n"
        f"Нажмите на кнопку ниже, чтобы забрать выигрыш на баланс 👇"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Забрать {fmt_ncoin(amount)} n¢ 💎",
                    callback_data=f"lottery_claim_reward:{amount}",
                )
            ]
        ]
    )

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("lottery_claim_reward:"))
async def lottery_claim_reward_callback(callback: CallbackQuery):
    """Начисление награды на баланс пользователя"""
    user_id = callback.from_user.id

    try:
        amount = float(callback.data.split(":")[1])
    except Exception:
        return await callback.answer("❌ Ошибка данных выигрыша.", show_alert=True)

    # Начисляем средства
    db.update_balance(user_id, amount)

    updated_user = db.get_user(user_id)
    final_balance = float(updated_user.get("balance", 0))

    await callback.answer(f"🎉 Зачислено +{fmt_ncoin(amount)} n¢!", show_alert=True)

    text = (
        f"✅ <b>Лотерея успешно получена!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_MONEY} Начислено: <b>+{fmt_ncoin(amount)} n¢</b>\n"
        f"{EMOJI_CARD} Ваш баланс: <b>{fmt_ncoin(final_balance)} n¢</b>\n\n"
        f"<i>Возвращайтесь через 12 часов за новым призом!</i>"
    )

    await callback.message.edit_text(text, parse_mode="HTML")
