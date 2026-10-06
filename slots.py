# slots.py
import asyncio
import random
import html
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext  # <-- ВОТ ЭТУ СТРОЧКУ НАДО ДОБАВИТЬ!
import db
import utils

logger = logging.getLogger(__name__)
router = Router()

EMOJI_PREMIUM_SLOTS = '<tg-emoji emoji-id="5335044092592142723">🎰</tg-emoji>'
EMOJI_PREMIUM_SLOTT = '<tg-emoji emoji-id="5201873447554145566">💸</tg-emoji>'
EMOJI_PREMIUM_SLOTU = '<tg-emoji emoji-id="5276032951342088188">💥</tg-emoji>'
EMOJI_PREMIUM_SLO = '<tg-emoji emoji-id="5278276646552503661">🏆</tg-emoji>'
EMOJI_PREMIUM_SO = '<tg-emoji emoji-id="5461151367559141950">🎉</tg-emoji>'

def _emoji_tag_valid(tag: str) -> bool:
    return 'emoji-id="' in tag and tag.split('emoji-id="', 1)[1].split('"', 1)[0].isdigit()

def safe_html_emoji(tag: str, fallback: str) -> str:
    return tag if _emoji_tag_valid(tag) else fallback

SLOTS_EMOJI = safe_html_emoji(EMOJI_PREMIUM_SLOTS, "🎰")

def parse_slot_value(value: int) -> tuple[str, str, str]:
    """
    Правильный математический расчет символов для дайса слотов (🎰) в Telegram.
    Значение value от 1 до 64. Всего 4 символа на барабан.
    """
    # Стандартные символы Telegram Slot Machine:
    # 0 - BAR, 1 - Виноград (🍇), 2 - Лимон (🍋), 3 - Семерка (7️⃣)
    symbols = ["BAR", "🍇", "🍋", "7️⃣"]
    
    # Приводим к диапазону 0-63
    v = value - 1
    
    # Математический разбор 64 комбинаций (4 в кубе)
    # Порядок: левый, средний, правый
    s1 = symbols[v % 4]          # Левый барабан
    s2 = symbols[(v // 4) % 4]   # Средний барабан
    s3 = symbols[(v // 16) % 4]  # Правый барабан
    
    return s1, s2, s3


@router.message(Command("slots"))
@router.message(F.text.lower().startswith(("слоты", "слот")))
async def play_slots(message: Message, bot: Bot):
    args = message.text.split()
    
    if len(args) < 2:
        user_link = f'<a href="tg://user?id={message.from_user.id}"><b>{html.escape(message.from_user.first_name or "Игрок")}</b></a>'
        
        help_text = (
            f"<blockquote>ℹ️ <b>Слоты</b> — это игра, где цель выбить три одинаковых символа на барабанах.\n\n"
            f"📊 <b>Лимиты:</b>\n"
            f"• RTP: ~97%\n"
            f"• Макс. множитель: x15.5\n"
            f"• Макс. ставка: 300kk n¢\n"
            f"• Макс. выигрыш: 3kkk n¢</blockquote>\n\n"
            f"{user_link}, чтобы начать игру, используй команду:\n\n"
            f"{SLOTS_EMOJI} <code>/slots [ставка]</code>\n\n"
            f"Пример: <code>/slots 100</code>\n"
            f"Пример: <code>слоты 100</code>"
        )
        await message.answer(help_text, parse_mode="HTML")
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    try:
        bet = utils.parse_bet_input(args[1], user["balance"])
    except (TypeError, ValueError):
        await message.reply("❌ <b>Некорректная ставка!</b> Введите число или 'все'.", parse_mode="HTML")
        return

    if bet <= 0:
        await message.reply("❌ <b>Ставка должна быть больше 0!</b>", parse_mode="HTML")
        return

    if user["balance"] < bet:
        await message.reply(f"❌ <b>Недостаточно nCoin!</b> Твой баланс: <b>{int(user['balance']):,} nCoin</b>", parse_mode="HTML")
        return

    # Списываем ставку
    db.update_balance(user_id, -bet)

    # Отправляем анимационный кубик слотов
    dice_msg = await message.answer_dice(emoji="🎰")
    dice_val = dice_msg.dice.value

    # Ждем завершения анимации
    await asyncio.sleep(3.0)

    # Расшифровываем выпавшие символы
    s1, s2, s3 = parse_slot_value(dice_val)

    # Логика выигрыша
    multiplier = 0.0
    if s1 == s2 == s3:
        if s1 == "7️⃣":
            multiplier = 15.5
        elif s1 == "BAR":
            multiplier = 12.0
        else:
            multiplier = 8.0
    elif s1 == s2 or s2 == s3 or s1 == s3:
        # Небольшой выигрыш за пару одинаковых
        multiplier = 1.3

    user_name = html.escape(message.from_user.first_name or "Игрок")
    user_link = f'<a href="tg://user?id={user_id}"><b>{user_name}</b></a>'

    if multiplier > 0:
        win_amount = int(bet * multiplier)
        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet, game_name="slots", win_amount=win_amount)

        result_text = (
            f"{user_link}\n"
            f"{EMOJI_PREMIUM_SO} <b>Слоты · Выигрыш! (x{multiplier})</b>\n"
            f"⠀\n"
            f"{EMOJI_PREMIUM_SLOTT} <b>Ставка:</b> {int(bet):,} n¢\n"
            f"{EMOJI_PREMIUM_SLO} <b>Выигрыш:</b> +{win_amount:,} n¢\n\n"
            f"<blockquote>{EMOJI_PREMIUM_SLOTS} <b>Результат:</b> {s1} | {s2} | {s3}</blockquote>"
        )
    else:
        db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet, game_name="slots", win_amount=0)

        result_text = (
            f"{user_link}\n"
            f"{EMOJI_PREMIUM_SLOTU} <b>Слоты · Проигрыш!</b>\n"
            f"⠀\n"
            f"{EMOJI_PREMIUM_SLOTT} <b>Ставка:</b> {int(bet):,} n¢\n\n"
            f"<blockquote>{EMOJI_PREMIUM_SLOTS} <b>Результат:</b> {s1} | {s2} | {s3}</blockquote>"
        )

    await message.reply(result_text, parse_mode="HTML")


# ==============================================================================
# 🎰 ИСПРАВЛЕНИЕ: ДОБАВЛЕН ОБРАБОТЧИК КНОПКИ ИЗ ЛОББИ (MAIN.PY)
# ==============================================================================
@router.callback_query(F.data == "slots_menu")
async def slots_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Открывает меню слотов при нажатии на кнопку в лобби игр из main.py"""
    await callback.answer()
    await state.clear()
    
    user = db.get_user(callback.from_user.id)
    balance = float(user.get("balance", 0))
    user_link = f'<a href="tg://user?id={callback.from_user.id}"><b>{html.escape(callback.from_user.first_name or "Игрок")}</b></a>'

    help_text = (
        f"<blockquote>ℹ️ <b>Слоты (Slots)</b> — это игра, где цель выбить три одинаковых символа на барабанах.\n\n"
        f"📊 <b>Лимиты:</b>\n"
        f"• RTP: ~97%\n"
        f"• Макс. множитель: x15.5\n"
        f"• Макс. ставка: 300kk n¢\n"
        f"• Макс. выигрыш: 3kkk n¢</blockquote>\n\n"
        f"{user_link}, чтобы начать игру, используй команду:\n\n"
        f"{SLOTS_EMOJI} <code>/slots [ставка]</code>\n\n"
        f"Пример: <code>/slots 100</code>\n"
        f"Пример: <code>слоты 100</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к играм", callback_data="games_page_2")]
    ])

    try:
        await callback.message.edit_text(help_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(help_text, reply_markup=kb, parse_mode="HTML")
