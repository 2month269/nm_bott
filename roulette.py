# roulette.py
import asyncio
import hashlib
import html
import logging
import random
import secrets
import urllib.parse
from aiogram import Bot, Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db
import utils

logger = logging.getLogger(__name__)

router = Router()

MAX_BET_LIMIT = 300_000_000  # Максимальная ставка: 300,000,000 n¢ (300кк)

GLOBAL_ROULETTE_LOG = []  # Глобальный лог последних игр
ROULETTE_FAIR_CACHE: dict[str, dict] = {}  # Кэш честности раундов рулетки в памяти

# ==============================================================================
# 🎰 СТИКЕРЫ РУЛЕТКИ (37 СЕКТОРОВ: 0..36)
# ==============================================================================
ROULETTE_STICKERS = {
    0: "CAACAgIAAxkBAAEuKjJqk2XVCThctEVKWBH1jESk6noNfAACIIMAAtJnqEhLTE5iB7xvrD0E",
    1: "CAACAgIAAxkBAAEuKjVqk2YKDB12cRUnGI2xgUvSxIiM1gACrHoAAvfOqUj907RlZmMliz0E",
    2: "CAACAgIAAxkBAAEuKjdqk2Y-nt6cS3VgHV2BVWOCUgx9QQACf3sAApR6qEhFDrGjoS582j0E",
    3: "CAACAgIAAxkBAAEuKj1qk2ZjHwJ8in4SY3kskHIpx-thTQACMnoAAlQLqUjJbZ887c092D0E",
    4: "CAACAgIAAxkBAAEuKkFqk2Z8XuI_xKTP8N8uIR4altblPgACtYEAAvDMqUj9fMCMellbqj0E",
    5: "CAACAgIAAxkBAAEuKkVqk2aZRPLQbRJkgBL_msphggfeqwAC838AArVvqUioI8rW4yItHz0E",
    6: "CAACAgIAAxkBAAEuKklqk2a0-STUoqhOeqt58ha2XBOxegACgYQAAovsqUhQW86W-I_mPz0E",
    7: "CAACAgIAAxkBAAEuKk1qk2bMXldmL-IFQO_9xhrYBA5pCwACxHoAAhPbqUg1ZnJlsBMZgT0E",
    8: "CAACAgIAAxkBAAEuKlNqk2bqrY14zk5y-feIbm9eSRuf5QACpXoAAmnuqUh4BH7Z1VXJxj0E",
    9: "CAACAgIAAxkBAAEuKllqk2cFkN_cZPyq3oe-ZP1goOYh9gACAXwAAjCZqUimI96B2e1K_j0E",
    10: "CAACAgIAAxkBAAEuKl1qk2chaZuvZ27K71pJndxShuf9IgACrXQAAtDaqEiYkYYV5svlBz0E",
    11: "CAACAgIAAxkBAAEuKmNqk2c8f2TtEVnWZxb8M3P2UCl12QACwYAAAhnroUh-neuxtS5Hjj0E",
    12: "CAACAgIAAxkBAAEuKmdqk2daymf9JOW43TLzF2eICsm1kwACEYEAAv35qUjEZH4gmSj4Xj0E",
    13: "CAACAgIAAxkBAAEuKmtqk2dyTJyUEO85VcfkVlPf2b0srAACnYcAAhE0qUjg1NZVHxYr-j0E",
    14: "CAACAgIAAxkBAAEuKm9qk2eKPU6fHnilekJ6I11PpP2nmAAC4HwAAiXMqEiSZcye_FqAxD0E",
    15: "CAACAgIAAxkBAAEuKnNqk2edcT3i9pN6lV0cFVXGJFfNxwACiYIAApZkqEhzNOStDy91Uj0E",
    16: "CAACAgIAAxkBAAEuKndqk2e0JO05YMMGrYcICD7v97BeQAACin8AAtRrqEiEvy3wQV3Y8D0E",
    17: "CAACAgIAAxkBAAEuKnlqk2fU8RSLrspUKT-aEXYfiM3NiwACG4AAAjoMqEiHSbFUVopsjj0E",
    18: "CAACAgIAAxkBAAEuKn1qk2fw4dkAAWEWoBwhwt3AA_KctYoAAgSFAAIXO6lIO4lW4pRxPg49BA",
    19: "CAACAgIAAxkBAAEuKoVqk2gV0zg4VcjYao9cmoVrYDJMvQACCXsAAiPrqEiVa46gH0ht8z0E",
    20: "CAACAgIAAxkBAAEuKolqk2gv3ggE4ICsk-up835L5IamawACV30AAtSCqEjx8T5LDBRfAAE9BA",
    21: "CAACAgIAAxkBAAEuKo1qk2hJRZobHeyPCxH_4zuXUQ7BowAC8XMAApLKqUiWIB4RwVPkSj0E",
    22: "CAACAgIAAxkBAAEuKpVqk2hyTyNJsYSpvxkQyDCrqGMrpgADgAACEDioSGDO-khlMDVfPQQ",
    23: "CAACAgIAAxkBAAEuKp1qk2jJMAwkr7Lh9uSBfTftjZqPAwAC73sAAvNVoEhOV-r7DSDuRz0E",
    24: "CAACAgIAAxkBAAEuKqFqk2jRZWZX5CEDOVIqkrCOk6zfHQACMnkAApA1qUgpf_GBbzbfpz0E",
    25: "CAACAgIAAxkBAAEuKqNqk2jVN4R6iaAFBtVyi3B-jQ4HhAAC6YAAAvrkqUhhmfV03w6ONj0E",
    26: "CAACAgIAAxkBAAEuKoNqk2gQabDKyc07uDtQOPYZYqQU9AACrH4AArvtqUiW88zR8qQ3DT0E",
    27: "CAACAgIAAxkBAAEuKq1qk2lSEsVlDRiRKASamT5Fk73aAwACi4oAAtdlqUho_doj7o8U0z0E",
    28: "CAACAgIAAxkBAAEuKrFqk2lqp9TN1s0qWJFQTO_HXnHJ1gACY34AAja6qUga8bRJcYBl1D0E",
    29: "CAACAgIAAxkBAAEuKrVqk2l8ScepnKrpxqi5-HItD4gBnQACVYcAAijdqUhZH7Px1HPDXD0E",
    30: "CAACAgIAAxkBAAEuKrlqk2mP13u2h_ej5z7u9_GYoQpQ2AACFXsAAnA5qEgRMB0nmnZjoD0E",
    31: "CAACAgIAAxkBAAEuKr1qk2mkn1lp21wEE0pDkSJ6X7RgkQACYH0AAnljqUjSRuWFxaxoRz0E",
    32: "CAACAgIAAxkBAAEuKsFqk2m2kkeV6rb9Amfx8_AeyX6O-gAC3oAAAo8dqUh-TxjbgP7mAAE9BA",
    33: "CAACAgIAAxkBAAEuKsVqk2nLgI5n5PHIiiJCvhT8CbkSSAAC_oEAAguDqEhbqBw_U8NFTT0E",
    34: "CAACAgIAAxkBAAEuKslqk2nc5DlFlXqoNNVwe9w4W7yaFQACNn8AAn54qEhq5n18sxAU3z0E",
    35: "CAACAgIAAxkBAAEuKs1qk2nu6ZxxA66FAtvx-Zv8VkkfxQACf4QAAkfTqEiSJWZ7vZJx6D0E",
    36: "CAACAgIAAxkBAAEuKtFqk2oAAZ2qKN8QJv81n3kEWMWdWLUAAtSAAAJW_qhI7eOppHKKxls9BA",
}

# ==============================================================================
# 🎭 ПРЕМИНУМ ЭМОДЗИ ДЛЯ ТЕКСТА СООБЩЕНИЙ
# ==============================================================================
EMOJI_ROULETTE = '<tg-emoji emoji-id="5226711870492126219">🎡</tg-emoji>'
EMOJI_CRYING = '<tg-emoji emoji-id="5463137996091962323">😭</tg-emoji>'
EMOJI_TADA = '<tg-emoji emoji-id="5989848973974704652">🎉</tg-emoji>'
EMOJI_MONEY = '<tg-emoji emoji-id="5373174941095050893">💸</tg-emoji>'
EMOJI_DICE = '<tg-emoji emoji-id="5350612670435313545">🎲</tg-emoji>'
EMOJI_SLOT = '<tg-emoji emoji-id="5429463966432643712">🎰</tg-emoji>'
EMOJI_GRAPH = '<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji>'
EMOJI_KEY = '<tg-emoji emoji-id="5469956488351025557">🔑</tg-emoji>'
EMOJI_CHECK = '<tg-emoji emoji-id="5805523262691611326">✅</tg-emoji>'
EMOJI_RED = '<tg-emoji emoji-id="5398038979217989221">🔴</tg-emoji>'
EMOJI_BLACK = '<tg-emoji emoji-id="6276175580102660253">⚫️</tg-emoji>'
EMOJI_GREEN = '<tg-emoji emoji-id="5280863578369311403">🟢</tg-emoji>'
EMOJI_CROSS = '<tg-emoji emoji-id="5454350746407419714">❌</tg-emoji>'
EMOJI_SCROLL = '<tg-emoji emoji-id="5388922215347534633">📜</tg-emoji>'

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}


def format_ncoin_display(value: float) -> str:
    """Форматирование чисел"""
    if value < 1:
        return "0"
    epsilon = 1e-9
    if abs(value - round(value, 2)) < epsilon:
        return f"{int(value):,}"
    else:
        return f"{value:,}"


def get_color_emoji(num: int) -> str:
    """Возвращает иконку цвета"""
    if num == 0:
        return EMOJI_GREEN
    elif num in RED_NUMBERS:
        return EMOJI_RED
    else:
        return EMOJI_BLACK


def parse_bet_choice(choice_str: str):
    """Разбор типа ставки в рулетке с поддержкой комбинированных диапазонов (например, 13-24 красный)"""
    choice = choice_str.lower().strip()
    words = choice.split()

    # ВАРИАНТ 1: Комбинированная ставка Диапазон + Цвет (например "13-24 красный", "13-24 к", "1-18 ч")
    if len(words) == 2:
        range_part, color_part = None, None
        if "-" in words[0]:
            range_part, color_part = words[0], words[1]
        elif "-" in words[1]:
            range_part, color_part = words[1], words[0]

        if range_part and color_part:
            try:
                min_val, max_val = map(int, range_part.split("-"))
                if 0 <= min_val < max_val <= 36:
                    target_set = None
                    col_name = ""
                    col_icon = ""

                    if color_part in ["к", "красное", "крас", "red"]:
                        target_set = RED_NUMBERS
                        col_name = "красный"
                        col_icon = EMOJI_RED
                    elif color_part in ["ч", "черное", "чёрное", "черн", "black"]:
                        target_set = BLACK_NUMBERS
                        col_name = "черный"
                        col_icon = EMOJI_BLACK

                    if target_set is not None:
                        matching_nums = [n for n in range(min_val, max_val + 1) if n in target_set]
                        count = len(matching_nums)
                        if count > 0:
                            multiplier = round(35.5 / count, 2)
                            label = f"{min_val}-{max_val} {col_name} {col_icon}"
                            return label, lambda n: n in matching_nums, multiplier
            except Exception:
                pass

    # ВАРИАНТ 2: Одиночные стандарты
    if choice in ["к", "красное", "крас", "red", "красный"]:
        return EMOJI_RED, lambda n: n in RED_NUMBERS, 1.97

    if choice in ["ч", "черное", "чёрное", "черн", "black", "черный", "чёрный"]:
        return EMOJI_BLACK, lambda n: n in BLACK_NUMBERS, 1.97

    if choice in ["0", "зеро", "зиро", "zero"]:
        return f"0 {EMOJI_GREEN}", lambda n: n == 0, 35.0

    if choice in ["чет", "четное", "чётное", "even", "чёт"]:
        return "Чётное 🔢", lambda n: n != 0 and n % 2 == 0, 1.97

    if choice in ["нечет", "нечетное", "нечётное", "odd", "нечёт"]:
        return "Нечётное 🔢", lambda n: n % 2 != 0, 1.97

    if choice in ["малые", "1-18", "small", "меньше", "м"]:
        return "1-18 🔲", lambda n: 1 <= n <= 18, 1.97

    if choice in ["большие", "19-36", "big", " больше", "б"]:
        return "19-36 🔲", lambda n: 19 <= n <= 36, 1.97

    if choice in ["1ряд", "1 ряд", "row1", "ряд1", "ряд 1"]:
        return "1-й ряд 🧱", lambda n: n != 0 and n % 3 == 1, 2.95

    if choice in ["2ряд", "2 ряд", "row2"]:
        return "2-й ряд 🧱", lambda n: n != 0 and n % 3 == 2, 2.95

    if choice in ["3ряд", "3 ряд", "row3"]:
        return "3-й ряд 🧱", lambda n: n != 0 and n % 3 == 0, 2.95

    # ВАРИАНТ 3: Простой диапазон чисел (например "13-24", "1-12", "25-36")
    if "-" in choice and len(words) == 1:
        try:
            parts = choice.split("-")
            min_val = int(parts[0])
            max_val = int(parts[1])

            if 0 <= min_val < max_val <= 36:
                count = max_val - min_val + 1
                multiplier = round(35.5 / count, 2)
                return (
                    f"{min_val}-{max_val} 🔲",
                    lambda n: min_val <= n <= max_val,
                    multiplier if multiplier > 0 else 2.95,
                )
        except Exception:
            pass

    # ВАРИАНТ 4: Число 0..36
    if choice.isdigit():
        val = int(choice)
        if 0 <= val <= 36:
            col = get_color_emoji(val)
            return f"{val} {col}", lambda n: n == val, 35.0

    return None


def extract_bet_and_choice(command_text: str, user_balance: float):
    """Гибкий извлекатель ставки и типа выбора из любого места команды"""
    words = command_text.strip().split()
    cmd_prefixes = ["рулетка", "рул", "/roulette"]
    filtered_words = [w for w in words if w.lower() not in cmd_prefixes]

    if not filtered_words:
        return None, None

    bet_val = -1.0
    bet_idx = -1

    # Пробуем найти слово, являющееся ставкой
    for idx, token in enumerate(filtered_words):
        try:
            b = utils.parse_bet_input(token, user_balance)
            if b > 0:
                bet_val = b
                bet_idx = idx
                break
        except Exception:
            try:
                b = utils.parse_bet_input(token)
                if b > 0:
                    bet_val = b
                    bet_idx = idx
                    break
            except Exception:
                pass

    if bet_val <= 0 or bet_idx == -1:
        return None, None

    choice_words = [w for i, w in enumerate(filtered_words) if i != bet_idx]
    choice_str = " ".join(choice_words)

    return bet_val, choice_str


def create_roulette_fair_game(
    user_id: int,
    user_name: str,
    bet: float,
    choice_str: str,
    winning_number: int,
    salt: str,
    is_win: bool,
    win_amount: float,
    multiplier: float,
    bet_label: str,
) -> str:
    """Генерирует доказательство честности для рулетки (SHA-256)."""
    raw_str = f"{winning_number}:{salt}"
    sha_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    fair_id = secrets.token_hex(8)

    ROULETTE_FAIR_CACHE[fair_id] = {
        "user_id": int(user_id),
        "user_name": str(user_name),
        "bet": float(bet),
        "choice_str": str(choice_str),
        "winning_number": int(winning_number),
        "salt": str(salt),
        "raw_str": str(raw_str),
        "sha_hash": str(sha_hash),
        "is_win": bool(is_win),
        "win_amount": float(win_amount),
        "multiplier": float(multiplier),
        "bet_label": str(bet_label),
    }

    if len(ROULETTE_FAIR_CACHE) > 1000:
        oldest_key = next(iter(ROULETTE_FAIR_CACHE))
        ROULETTE_FAIR_CACHE.pop(oldest_key, None)

    return fair_id


def render_roulette_result_text(fair_data: dict) -> str:
    """Формирует текст результата раунда рулетки."""
    user_name_esc = html.escape(fair_data["user_name"])
    winning_number = fair_data["winning_number"]
    col_emoji = get_color_emoji(winning_number)
    bet = fair_data["bet"]
    bet_label = fair_data["bet_label"]

    if fair_data["is_win"]:
        win_amount = fair_data["win_amount"]
        multiplier = fair_data["multiplier"]
        mult_str = f"{multiplier:.2f}".replace(".", ",")

        return (
            f"<b>{user_name_esc}</b>\n"
            f"{EMOJI_TADA} Рулетка · Победа! {EMOJI_CHECK}\n"
            "·······················\n"
            f"{EMOJI_MONEY} Ставка: {format_ncoin_display(bet)} n¢\n"
            f"{EMOJI_DICE} Выбрано: {bet_label}\n"
            f"{EMOJI_GRAPH} Выигрыш: х{mult_str} / {format_ncoin_display(win_amount)} n¢\n"
            "············\n"
            f"{EMOJI_SLOT} Выпало: {winning_number} {col_emoji}"
        )
    else:
        return (
            f"<b>{user_name_esc}</b>\n"
            f"{EMOJI_CRYING} Рулетка · Проигрыш!\n"
            "·······················\n"
            f"{EMOJI_MONEY} Ставка: {format_ncoin_display(bet)} n¢\n"
            f"{EMOJI_DICE} Выбрано: {bet_label}\n"
            "············\n"
            f"{EMOJI_SLOT} Выпало: {winning_number} {col_emoji}"
        )


def get_finished_roulette_kb(fair_id: str) -> InlineKeyboardMarkup:
    """Кнопки результатов: Повторить и Честность."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Повторить", callback_data=f"roulette_repeat:{fair_id}"),
                InlineKeyboardButton(text="🔑 Честность", callback_data=f"roulette_fair:{fair_id}"),
            ]
        ]
    )


# ==============================================================================
# 🎡 ГЛАВНОЕ МЕНЮ И ТЕКСТОВЫЕ КОМАНДЫ (В точности по скриншоту)
# ==============================================================================

@router.message(StateFilter(None), F.text, F.text.lower().in_(["рулетка", "рул", "/roulette", "рулетка команды"]))
async def roulette_main_intro(message: Message, state: FSMContext):
    """Показ списка команд рулетки"""
    await state.clear()

    text = (
        f"{EMOJI_SCROLL} <b>Рулетка · команды:</b>\n\n"
        f"{EMOJI_MONEY} <b>Рулетка ставки</b> – просмотр ставок.\n"
        f"{EMOJI_GREEN} <b>Рулетка запустить</b> – запуск рулетки.\n"
        f"{EMOJI_CROSS} <b>Рулетка отмена</b> – отмена ставок.\n"
        f"⚪️ <b>Рулетка лог</b> – последние 10 игр."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ назад", callback_data="games_menu")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(StateFilter(None), F.text, F.text.lower().in_(["рулетка ставки", "рулетка запустить", "рул ставки", "рул запустить"]))
async def roulette_cmd_no_bet(message: Message, state: FSMContext):
    """Обработка команд без указания суммы ставки"""
    await state.clear()
    user_name = html.escape(message.from_user.first_name)

    text = f"{EMOJI_RED} <b>{user_name}</b>, нельзя запустить игру без ставки!"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Виды ставок 🔘", callback_data="roulette_view_types")],
        [InlineKeyboardButton(text="Команды для игры 📜", callback_data="roulette_view_cmds")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(StateFilter(None), F.text, F.text.lower().in_(["рулетка отмена", "рул отмена"]))
async def roulette_cmd_cancel(message: Message, state: FSMContext):
    """Обработка отмены ставок"""
    await state.clear()
    user_name = html.escape(message.from_user.first_name)

    text = f"{EMOJI_CROSS} <b>{user_name}</b>, у тебя нет активных ставок для отмены!"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Виды ставок 🔘", callback_data="roulette_view_types")],
        [InlineKeyboardButton(text="Команды для игры 📜", callback_data="roulette_view_cmds")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "roulette_view_types")
async def roulette_view_types_callback(callback: CallbackQuery):
    """Окно 'Виды ставок'"""
    await callback.answer()
    user_name = html.escape(callback.from_user.first_name)

    text = (
        f"<b>{user_name}</b>\n"
        "🔘 <b>ВИДЫ СТАВОК В РУЛЕТКЕ:</b>\n\n"
        "🎱 <b>Ставка на определенное число:</b>\n"
        "<u>рулетка 100 7</u> (или /roulette 10 7)\n\n"
        f"{EMOJI_RED} <b>Ставка на цвет:</b>\n"
        "<u>рулетка 100 красный</u> (или рул 100 к / черный)\n\n"
        "🎯 <b>Ставка на диапазон + цвет:</b>\n"
        "<u>рулетка 20к 13-24 красный</u> (или рул 20к 13-24 к)\n\n"
        "⚖️ <b>Ставка на четность:</b>\n"
        "<u>рулетка 15 чет</u> / нечет\n\n"
        "🔢 <b>Ставка на дюжины и диапазоны:</b>\n"
        "<u>рулетка 25 1-12</u> (или 13-24, 25-36, 1-18, 19-36)\n\n"
        "🧱 <b>Ставка на ряды:</b>\n"
        "<u>рулетка 30 2ряд</u> (1ряд, 2ряд, 3ряд)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Команды для игры 📜", callback_data="roulette_view_cmds")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "roulette_view_cmds")
async def roulette_view_cmds_callback(callback: CallbackQuery):
    """Окно 'Команды для игры'"""
    await callback.answer()

    text = (
        f"{EMOJI_SCROLL} <b>Рулетка · команды:</b>\n\n"
        f"{EMOJI_MONEY} <b>Рулетка ставки</b> – просмотр ставок.\n"
        f"{EMOJI_GREEN} <b>Рулетка запустить</b> – запуск рулетки.\n"
        f"{EMOJI_CROSS} <b>Рулетка отмена</b> – отмена ставок.\n"
        f"⚪️ <b>Рулетка лог</b> – последние 10 игр."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Виды ставок 🔘", callback_data="roulette_view_types")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ==============================================================================
# 🕔 РУЛЕТКА ЛОГ (ОСТАВЛЕН БЕЗ ИЗМЕНЕНИЙ ПО ТРЕБОВАНИЮ)
# ==============================================================================

@router.message(StateFilter(None), F.text, F.text.lower().in_(["рулетка лог", "рул лог", "/roulette_log"]))
async def roulette_log_command(message: Message):
    """Показывает последние 10 игр всех игроков"""
    if not GLOBAL_ROULETTE_LOG:
        await message.answer("⚪️ <b>Рулетка · последние игры:</b>\n\nЛог игр пуст!", parse_mode="HTML")
        return

    text = "⚪️ <b>Рулетка · последние игры:</b>\n\n"

    for item in reversed(GLOBAL_ROULETTE_LOG[-10:]):
        text += f" • {item['number']} {item['num_sym']}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Закрыть ❌", callback_data="artifact_cancel")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ==============================================================================
# 🎯 ЗАПУСК ИГРЫ И ОБРАБОТКА СТАВОК
# ==============================================================================

@router.message(StateFilter(None), F.text, F.text.lower().startswith(("рулетка", "рул", "/roulette")))
async def handle_roulette_game_cmd(message: Message, state: FSMContext):
    await state.clear()
    text_raw = message.text.strip()
    text_lower = text_raw.lower()

    # Пропуск базовых команд, обработанных выше
    if text_lower in [
        "рулетка", "рул", "/roulette", "рулетка команды",
        "рулетка ставки", "рулетка запустить", "рул ставки", "рул запустить",
        "рулетка отмена", "рул отмена", "рулетка лог", "рул лог", "/roulette_log"
    ]:
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)

    # Извлекаем сумму ставки и тип выбора из команды
    bet, choice_str = extract_bet_and_choice(text_raw, user["balance"])

    if bet is None or not choice_str:
        user_name = html.escape(message.from_user.first_name)
        await message.answer(
            f"{EMOJI_RED} <b>{user_name}</b>, нельзя запустить игру без ставки!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Виды ставок 🔘", callback_data="roulette_view_types")],
                [InlineKeyboardButton(text="Команды для игры 📜", callback_data="roulette_view_cmds")]
            ]),
            parse_mode="HTML"
        )
        return

    await start_roulette_game(message, user_id, bet, choice_str, sender_name=message.from_user.first_name)


async def start_roulette_game(message_obj: Message, user_id: int, bet: float, choice_str: str, sender_name: str = "Игрок"):
    user = db.get_user(user_id)
    user_name = user.get("first_name") or sender_name

    if bet <= 0:
        await message_obj.answer(f"{EMOJI_CROSS} Ставка должна быть больше 0!", parse_mode="HTML")
        return

    if bet > MAX_BET_LIMIT:
        user_name_esc = html.escape(user_name)
        await message_obj.answer(
            f"{EMOJI_CROSS} <b>{user_name_esc}</b>, максимальная ставка — <b>{format_ncoin_display(MAX_BET_LIMIT)} n¢</b> (300кк)!",
            parse_mode="HTML"
        )
        return

    if user["balance"] < bet:
        await message_obj.answer(
            f"{EMOJI_CROSS} Недостаточно n¢! Ваш баланс: <b>{format_ncoin_display(user['balance'])} n¢</b>",
            parse_mode="HTML",
        )
        return

    parsed = parse_bet_choice(choice_str)
    if not parsed:
        user_name_esc = html.escape(user_name)
        await message_obj.answer(
            f"{EMOJI_CROSS} <b>{user_name_esc}</b>, неверный тип ставки!\nИспользуйте: <code>рулетка 100 к</code> или <code>рулетка 20к 13-24 красный</code>",
            parse_mode="HTML",
        )
        return

    bet_label, winning_check, multiplier = parsed

    # 1. Безопасное списание ставки
    try:
        db.update_balance(user_id, -bet)
    except Exception as e:
        logger.error(f"Ошибка списания ставки в рулетке: {e}")
        await message_obj.answer("❌ Ошибка базы данных при списании ставки. Попробуйте еще раз.")
        return

    # 2. Выбираем случайный сектор
    winning_number = random.randint(0, 36)
    salt = secrets.token_hex(8)

    # 3. Отправляем стикер выпавшего сектора
    sticker_file_id = ROULETTE_STICKERS.get(winning_number)
    if sticker_file_id:
        try:
            await message_obj.answer_sticker(sticker=sticker_file_id)
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.warning(f"Ошибка отправки стикера рулетки: {e}")

    # 4. Рассчитываем исход
    is_win = winning_check(winning_number)
    col_emoji = get_color_emoji(winning_number)

    if is_win:
        win_amount = round(bet * multiplier, 2)
        try:
            db.update_balance(user_id, win_amount)
            db.add_stats(user_id, is_lost=False, bet_amount=bet)
        except Exception as e:
            logger.error(f"Ошибка начисления выигрыша: {e}")
    else:
        win_amount = 0.0
        try:
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
        except Exception as e:
            logger.error(f"Ошибка сохранения проигрыша: {e}")

    # Создаем запись честности в кэше
    fair_id = create_roulette_fair_game(
        user_id=user_id,
        user_name=user_name,
        bet=bet,
        choice_str=choice_str,
        winning_number=winning_number,
        salt=salt,
        is_win=is_win,
        win_amount=win_amount,
        multiplier=multiplier,
        bet_label=bet_label,
    )

    res_text = render_roulette_result_text(ROULETTE_FAIR_CACHE[fair_id])
    kb = get_finished_roulette_kb(fair_id)

    # Сохраняем в глобальный лог
    GLOBAL_ROULETTE_LOG.append({
        "user_name": user_name,
        "number": winning_number,
        "num_sym": col_emoji,
        "bet": bet,
        "is_win": is_win,
        "win_amount": win_amount,
    })
    if len(GLOBAL_ROULETTE_LOG) > 50:
        GLOBAL_ROULETTE_LOG.pop(0)

    # 5. НАДЕЖНАЯ ОТПРАВКА С ЗАЩИТОЙ
    try:
        await message_obj.answer(res_text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки HTML результата: {e}")
        await message_obj.answer(res_text, reply_markup=kb)


# ==============================================================================
# 🔄 ПОВТОРИТЬ И 🔑 ЧЕСТНОСТЬ (Аналогично artifact_game.py и gold_game.py)
# ==============================================================================

@router.callback_query(F.data.startswith("roulette_repeat:"), StateFilter("*"))
async def roulette_repeat_start(callback: CallbackQuery, state: FSMContext):
    """Повторяет рулетку с той же ставкой и типом выбора"""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Ошибка данных.", show_alert=True)

        fair_id = parts[1]
        previous_game = ROULETTE_FAIR_CACHE.get(fair_id)

        if not previous_game:
            return await callback.answer("❌ Данные предыдущей игры устарели.", show_alert=True)

        if int(previous_game["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        await callback.answer()
        bet = previous_game["bet"]
        choice_str = previous_game["choice_str"]

        await state.clear()
        await start_roulette_game(
            message_obj=callback.message,
            user_id=callback.from_user.id,
            bet=bet,
            choice_str=choice_str,
            sender_name=callback.from_user.first_name,
        )
    except Exception as e:
        logger.error(f"Ошибка в roulette_repeat_start: {e}")
        try:
            await callback.answer("❌ Не удалось повторить игру.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("roulette_fair:"), StateFilter("*"))
async def roulette_fair_callback(callback: CallbackQuery):
    """Редактирует сообщение с результатами, показыая SHA-256 доказательство (как в gold_game.py)"""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Ошибка данных.", show_alert=True)

        fair_id = parts[1]
        fair_data = ROULETTE_FAIR_CACHE.get(fair_id)

        if not fair_data:
            return await callback.answer("❌ Данные раунда устарели или бот был перезапущен.", show_alert=True)

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        await callback.answer()

        raw_str = html.escape(str(fair_data["raw_str"]))
        sha_hash = html.escape(str(fair_data["sha_hash"]))
        winning_number = fair_data["winning_number"]
        col_emoji = get_color_emoji(winning_number)

        text = (
            f"{EMOJI_ROULETTE} <b>Рулетка · Честность</b> {EMOJI_KEY}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔢 <b>SHA-256 Хэш:</b>\n"
            f"<code>{sha_hash}</code>\n\n"
            "🔑 <b>Результат (Raw):</b>\n"
            f"<code>{raw_str}</code>\n\n"
            "🎯 <b>Выпавший сектор:</b>\n"
            f"Сектор <b>{winning_number}</b> {col_emoji}\n\n"
            "<blockquote>"
            "Число перед двоеточием указывает на выпавшее число. "
            "Скопируйте строку Результата и вставьте её на любом сайте, поддерживающем SHA-256. "
            "Сгенерированный хэш точно совпадёт с Хэшем раунда!"
            "</blockquote>"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"roulette_fair_back:{fair_id}"),
                InlineKeyboardButton(text="Проверить SHA-256 🔑", url="https://emn178.github.io/online-tools/")
            ]
        ])

        msg = callback.message
        if msg:
            await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в roulette_fair_callback: {e}")
        try:
            await callback.answer("❌ Произошла ошибка при получении честности.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("roulette_fair_back:"), StateFilter("*"))
async def roulette_fair_back_callback(callback: CallbackQuery):
    """Возвращает исходный карточку результатов рулетки"""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Неверный запрос.", show_alert=True)

        fair_id = parts[1]
        fair_data = ROULETTE_FAIR_CACHE.get(fair_id)

        if not fair_data:
            return await callback.answer("❌ Данные игры устарели.", show_alert=True)

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        await callback.answer()

        res_text = render_roulette_result_text(fair_data)
        kb = get_finished_roulette_kb(fair_id)

        msg = callback.message
        if msg:
            await msg.edit_text(res_text, reply_kb=kb, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка в roulette_fair_back_callback: {e}")
        try:
            await callback.answer("❌ Не удалось вернуться.", show_alert=True)
        except Exception as e_inner:
            logger.error(f"Вложенная ошибка: {e_inner}")
