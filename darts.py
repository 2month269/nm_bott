# darts.py
import asyncio
import hashlib
import html
import logging
import random
import secrets
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

import db
import utils

logger = logging.getLogger(__name__)

router = Router()

# Константы
MAX_BET = 150_000_000  # Максимальная ставка 200кк n¢

# Кэш честности раундов Дартс в памяти
DARTS_FAIR_CACHE: dict[str, dict] = {}

# Множители
MULTIPLIERS = {
    "белый": 2.5,
    "красный": 1.97,
    "центр": 5.8,
    "мимо": 5.0
}

# Синонимы секторов
SECTOR_ALIASES = {
    "б": "белый",
    "белый": "белый",
    "бел": "белый",
    "white": "белый",
    "к": "красный",
    "красный": "красный",
    "крас": "красный",
    "red": "красный",
    "м": "мимо",
    "мимо": "мимо",
    "miss": "мимо",
    "ц": "центр",
    "центр": "центр",
    "яблочко": "центр",
    "яб": "центр",
    "center": "центр",
    "bullseye": "центр",
    "белое": "белый",
    "красное": "красный"
}

# Соответствие кубика Telegram 🎯 секторам
RESULT_MAP = {
    1: "мимо",      # Промах в стену
    2: "красный",   # Попадание во внешний красный круг
    3: "белый",     # Попадание во внешний белый круг
    4: "красный",   # Попадание во внутренний красный круг
    5: "белый",     # Попадание во внутренний белый круг
    6: "центр"      # Попадание в яблочко (центр)
}

# 🎭 Премиум эмодзи
EMOJI_TARGET = '<tg-emoji emoji-id="5429463966432643712">🎯</tg-emoji>'
EMOJI_CHECK = '<tg-emoji emoji-id="5805523262691611326">✅</tg-emoji>'
EMOJI_MONEY = '<tg-emoji emoji-id="5373174941095050893">💸</tg-emoji>'
EMOJI_WIN_MONEY = '<tg-emoji emoji-id="5373174941095050893">💰</tg-emoji>'
EMOJI_LIGHTNING = '<tg-emoji emoji-id="5989800724312101453">⚡️</tg-emoji>'
EMOJI_STOP = '<tg-emoji emoji-id="5305381957524272531">🛑</tg-emoji>'
EMOJI_CROSS = '<tg-emoji emoji-id="5454350746407419714">❌</tg-emoji>'
EMOJI_INFO = '<tg-emoji emoji-id="5467403607286502523">ℹ️</tg-emoji>'
EMOJI_GRAPH = '<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji>'
EMOJI_ROBOT = '<tg-emoji emoji-id="5350612670435313545">🤖</tg-emoji>'
EMOJI_KEY = '<tg-emoji emoji-id="5469956488351025557">🔑</tg-emoji>'


def fmt_q(val: float) -> str:
    """Форматирование чисел с разделителем '"""
    if val < 1:
        return "0"
    if abs(val - round(val)) < 1e-9:
        return f"{int(val):,}".replace(",", "'")
    return f"{val:,.2f}".replace(",", "'")


def is_darts_win(target: str, actual_sector: str) -> bool:
    """
    Проверка победы.
    ВАЖНО: Если игрок поставил на КРАСНЫЙ, а выпал ЦЕНТР — это тоже считается ПОБЕДОЙ!
    """
    if target == actual_sector:
        return True
    if target == "красный" and actual_sector == "центр":
        return True
    return False


def parse_bet_and_target(parts: list[str], user_balance: float):
    """
    Универсальный парсер: понимает все виды ставок ('все', 'пол', '100', '5к', '1.5кк')
    и сектор ('к', 'красный', 'ц', 'мимо') в ЛЮБОМ порядке слов.
    """
    args = parts[1:]
    if not args:
        return None, "центр"

    bet = None
    target = "центр"

    target_found = False
    bet_found = False

    for arg in args:
        arg_low = arg.lower().strip()

        # Ищем сектор
        if not target_found and arg_low in SECTOR_ALIASES:
            target = SECTOR_ALIASES[arg_low]
            target_found = True
            continue

        # Ищем сумму ставки
        if not bet_found:
            if arg_low in ["все", "всё", "all", "allin", "вабанк", "ва-банк"]:
                bet = round(user_balance, 2)
                bet_found = True
                continue
            elif arg_low in ["пол", "половина", "half"]:
                bet = round(user_balance / 2, 2)
                bet_found = True
                continue
            else:
                try:
                    parsed = utils.parse_bet_input(arg_low, user_balance)
                    if parsed > 0:
                        bet = parsed
                        bet_found = True
                        continue
                except Exception:
                    try:
                        parsed = utils.parse_bet_input(arg_low)
                        if parsed > 0:
                            bet = parsed
                            bet_found = True
                            continue
                    except Exception:
                        pass

    return bet, target


def create_darts_fair_game(
    user_id: int,
    user_name: str,
    bet: float,
    target: str,
    rolled_value: int,
    actual_sector: str,
    win: bool,
    win_amount: float,
    final_balance: float
) -> str:
    """Генерирует запись честности раунда (SHA-256)."""
    salt = secrets.token_hex(16)
    raw_str = f"{rolled_value}:{salt}"
    sha_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    fair_id = secrets.token_hex(8)

    DARTS_FAIR_CACHE[fair_id] = {
        "user_id": int(user_id),
        "user_name": str(user_name),
        "bet": float(bet),
        "target": str(target),
        "rolled_value": int(rolled_value),
        "actual_sector": str(actual_sector),
        "salt": str(salt),
        "raw_str": str(raw_str),
        "sha_hash": str(sha_hash),
        "win": bool(win),
        "win_amount": float(win_amount),
        "final_balance": float(final_balance),
        "multiplier": MULTIPLIERS.get(target, 1.0)
    }

    if len(DARTS_FAIR_CACHE) > 1000:
        oldest_key = next(iter(DARTS_FAIR_CACHE))
        DARTS_FAIR_CACHE.pop(oldest_key, None)

    return fair_id


def render_darts_result_text(fair_data: dict) -> str:
    """Формирует результат игры"""
    bet = fair_data["bet"]
    target = fair_data["target"]
    actual_sector = fair_data["actual_sector"]
    final_balance = fair_data["final_balance"]
    win = fair_data["win"]
    win_amount = fair_data["win_amount"]
    multiplier = fair_data["multiplier"]

    if win:
        return (
            f"{EMOJI_TARGET} <b>Дартс · Победа!</b> {EMOJI_CHECK}\n"
            f"· · · · · · · · · · · · · · · · · · · · ·\n"
            f"{EMOJI_MONEY} Ставка: <b>{fmt_q(bet)} n¢</b>\n"
            f"{EMOJI_TARGET} Выбрано: <b>{target}</b>\n"
            f"{EMOJI_WIN_MONEY} Выигрыш: <b>x{multiplier} / {fmt_q(win_amount)} n¢</b>\n"
            f"· · · · · · · · · · ·\n"
            f"{EMOJI_LIGHTNING} Выпало: <b>{actual_sector}</b>\n\n"
            f"{EMOJI_WIN_MONEY} Баланс: <b>{fmt_q(final_balance)} n¢</b>"
        )
    else:
        return (
            f"{EMOJI_STOP} <b>Дартс · Проигрыш!</b>\n"
            f"· · · · · · · · · · · · · · · · · · · · ·\n"
            f"{EMOJI_MONEY} Ставка: <b>{fmt_q(bet)} n¢</b>\n"
            f"{EMOJI_TARGET} Выбрано: <b>{target}</b>\n"
            f"· · · · · · · · · · ·\n"
            f"{EMOJI_LIGHTNING} Выпало: <b>{actual_sector}</b>\n\n"
            f"{EMOJI_WIN_MONEY} Баланс: <b>{fmt_q(final_balance)} n¢</b>"
        )


def get_finished_darts_kb(fair_id: str) -> InlineKeyboardMarkup:
    """Кнопки в конце игры: 🔄 Повторить и 🔑 Честность"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Повторить", callback_data=f"darts_repeat:{fair_id}", style="primary"),
            InlineKeyboardButton(text="🔑 Честность", callback_data=f"darts_fair:{fair_id}", style="primary")
        ]
    ])


async def send_darts_help(event, first_name: str = "Игрок"):
    """Вывод меню справки"""
    text = (
        f"<blockquote>{EMOJI_INFO} Дартс — это игра, в которой нужно попасть в центр мишени, чтобы получить максимальный множитель.\n"
        f"{EMOJI_GRAPH} Лимиты:\n"
        f"RTP: ~97%\n"
        f"Макс. множитель: x5.8\n"
        f"Макс. ставка: 200kk n¢\n"
        f"Макс. выигрыш: 1.16kkk n¢</blockquote>\n\n"
        f"{EMOJI_ROBOT} {html.escape(first_name)}, чтобы начать игру, используй команду:\n\n"
        f"{EMOJI_TARGET} <b>/darts [ставка]</b>\n\n"
        f"Пример: /darts 100\n"
        f"Пример: дартс все к"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="games_menu")]
    ])

    if isinstance(event, Message):
        await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
    elif isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


async def start_darts_logic(message: Message, bet: float, target: str, user_id: int = None, user_name: str = None):
    """Основная логика броска и расчета выигрыша"""
    if user_id is None:
        user_id = message.from_user.id
    if user_name is None:
        user_name = message.from_user.first_name if message.from_user else "Игрок"

    # Проверка максимальной ставки
    if bet > MAX_BET:
        await message.answer(
            f"{EMOJI_CROSS} <b>Максимальная ставка: {fmt_q(MAX_BET)} n¢ (200kk)!</b>",
            parse_mode="HTML"
        )
        return

    user_data = db.get_user(user_id)

    # Проверка баланса
    if user_data['balance'] < bet:
        await message.answer(
            f"{EMOJI_CROSS} <b>Недостаточно n¢ для ставки!</b>\n"
            f"Твой баланс: <b>{fmt_q(user_data['balance'])} n¢</b>",
            parse_mode="HTML"
        )
        return

    # Списание ставки
    db.update_balance(user_id, -bet)

    # Отправка анимированного дартса 🎯
    dice_msg = await message.answer_dice(emoji="🎯")
    rolled_value = dice_msg.dice.value
    actual_sector = RESULT_MAP[rolled_value]

    # Ожидание окончания анимации броска
    await asyncio.sleep(4.0)

    # Проверка на победу (с учетом того, что Центр при ставке на Красный — тоже ПОБЕДА!)
    win = is_darts_win(target, actual_sector)
    win_amount = 0.0

    if win:
        multiplier = MULTIPLIERS[target]
        win_amount = round(bet * multiplier, 2)
        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)
    else:
        db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)

    updated_user = db.get_user(user_id)
    final_balance = updated_user['balance']

    # Данные честности
    fair_id = create_darts_fair_game(
        user_id=user_id,
        user_name=user_name,
        bet=bet,
        target=target,
        rolled_value=rolled_value,
        actual_sector=actual_sector,
        win=win,
        win_amount=win_amount,
        final_balance=final_balance
    )

    fair_data = DARTS_FAIR_CACHE[fair_id]
    text = render_darts_result_text(fair_data)
    keyboard = get_finished_darts_kb(fair_id)

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("darts"))
@router.message(F.text.lower().startswith(("дартс", "дс", "/darts")))
async def darts_text_cmd(message: Message, state: FSMContext):
    """Гибкая обработка команд: дартс, /darts, дс"""
    await state.clear()
    parts = message.text.split()

    # Показ справки если без параметров
    if len(parts) == 1:
        await send_darts_help(message, message.from_user.first_name)
        return

    user = db.get_user(message.from_user.id)
    user_balance = float(user.get("balance", 0))

    # Извлекаем ставку и выбранный сектор
    bet, target_sector = parse_bet_and_target(parts, user_balance)

    # Если ставка не распарсилась
    if bet is None or bet <= 0:
        await message.answer(
            f"{EMOJI_CROSS} <b>Неверный формат ставки!</b>\n"
            f"Используй: <code>/darts [ставка] [сектор]</code> или <code>дс [сектор] [ставка]</code>\n"
            f"Примеры: <code>дс все к</code>, <code>дартс пол к</code>, <code>дс 100 мимо</code>",
            parse_mode="HTML"
        )
        return

    await start_darts_logic(message, bet, target_sector)


@router.callback_query(F.data == "darts_menu")
async def darts_menu(callback: CallbackQuery, state: FSMContext):
    """Инструкция через инлайн-кнопку"""
    await state.clear()
    await callback.answer()
    await send_darts_help(callback, callback.from_user.first_name)


# ==============================================================================
# 🔄 ПОВТОРИТЬ И 🔑 ЧЕСТНОСТЬ (Гарантированная работа)
# ==============================================================================

@router.callback_query(F.data.startswith("darts_repeat:"), StateFilter("*"))
async def darts_repeat_callback(callback: CallbackQuery, state: FSMContext):
    """Повторяет игру с той же ставкой и сектором"""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Ошибка данных.", show_alert=True)

        fair_id = parts[1]
        previous_game = DARTS_FAIR_CACHE.get(fair_id)

        if not previous_game:
            return await callback.answer("❌ Данные предыдущей игры устарели.", show_alert=True)

        if int(previous_game["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        await callback.answer()
        bet = previous_game["bet"]
        target = previous_game["target"]

        await state.clear()
        await start_darts_logic(
            message=callback.message,
            bet=bet,
            target=target,
            user_id=callback.from_user.id,
            user_name=callback.from_user.first_name
        )

    except Exception as error:
        logger.exception("Ошибка при повторе игры Дартс: %s", error)
        try:
            await callback.answer("❌ Не удалось повторить игру.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("darts_fair:"), StateFilter("*"))
async def darts_fair_callback(callback: CallbackQuery):
    """Показывает данные честности SHA-256 (редактированием сообщения)."""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Ошибка вызова.", show_alert=True)

        fair_id = parts[1]
        fair_data = DARTS_FAIR_CACHE.get(fair_id)

        if not fair_data:
            return await callback.answer("❌ Данные раунда устарели или бот был перезапущен.", show_alert=True)

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        # Отвечаем на Callback сразу!
        await callback.answer()

        raw_str = html.escape(str(fair_data["raw_str"]))
        sha_hash = html.escape(str(fair_data["sha_hash"]))
        rolled_val = fair_data["rolled_value"]
        sector = fair_data["actual_sector"]

        text = (
            f"{EMOJI_TARGET} <b>Дартс · Честность</b> {EMOJI_KEY}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔢 <b>SHA-256 Хэш:</b>\n"
            f"<code>{sha_hash}</code>\n\n"
            "🔑 <b>Результат (Raw):</b>\n"
            f"<code>{raw_str}</code>\n\n"
            "🎯 <b>Значение кубика Telegram (1-6):</b>\n"
            f"Выпало: <b>{rolled_val}</b> ({sector})\n\n"
            "<blockquote>"
            "Число перед двоеточием указывает на выпавшее значение анимированного дартса (1-6). "
            "Скопируйте строку Результата и вставьте её на любом сайте, поддерживающем SHA-256. "
            "Сгенерированный хэш точно совпадёт с Хэшем раунда!"
            "</blockquote>"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"darts_fair_back:{fair_id}", style="danjer"),
                InlineKeyboardButton(text="Проверить SHA-256 🔑", url="https://emn178.github.io/online-tools/", style="success")
            ]
        ])

        msg = callback.message
        if msg:
            if msg.photo:
                await msg.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                await msg.edit_text(text=text, reply_markup=kb, parse_mode="HTML")

    except Exception as error:
        logger.exception("Ошибка в darts_fair_callback: %s", error)
        try:
            await callback.answer("❌ Не удалось открыть данные честности.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("darts_fair_back:"), StateFilter("*"))
async def darts_fair_back_callback(callback: CallbackQuery):
    """Возвращает карточку результатов в исходное сообщение."""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Неверный запрос.", show_alert=True)

        fair_id = parts[1]
        fair_data = DARTS_FAIR_CACHE.get(fair_id)

        if not fair_data:
            return await callback.answer("❌ Данные игры устарели.", show_alert=True)

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        await callback.answer()

        text = render_darts_result_text(fair_data)
        kb = get_finished_darts_kb(fair_id)

        msg = callback.message
        if msg:
            if msg.photo:
                await msg.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                await msg.edit_text(text=text, reply_markup=kb, parse_mode="HTML")

    except Exception as error:
        logger.exception("Ошибка в darts_fair_back_callback: %s", error)
        try:
            await callback.answer("❌ Не удалось вернуться к результатам.", show_alert=True)
        except Exception:
            pass
