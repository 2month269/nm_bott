#pyramid_game.py
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

ACTIVE_PYRAMID_GAMES = {}  # {user_id: game_state}
PYRAMID_FAIR_CACHE: dict[str, dict] = {}  # Кэш честности раундов (SHA-256)

# ==============================================================================
# 🎭 ПРЕМИУМ-ЭМОДЗИ ДЛЯ ТЕКСТА СООБЩЕНИЙ (ВЕРХНИЙ БЛОК)
# ==============================================================================
# Вставьте ваши emoji-id внутрь тегов <tg-emoji emoji-id="...">
EMOJI_INFO = '<tg-emoji emoji-id="5467403607286502523">ℹ️</tg-emoji>'
EMOJI_GRAPH = '<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji>'
EMOJI_ROBOT = '<tg-emoji emoji-id="5350612670435313545">🤖</tg-emoji>'
EMOJI_RUNNER = '<tg-emoji emoji-id="5989800724312101453">🏃‍♂️</tg-emoji>'
EMOJI_DOOR = '<tg-emoji emoji-id="5465198403573012261">🚪</tg-emoji>'
EMOJI_MONEY = '<tg-emoji emoji-id="5463046637842608206">💸</tg-emoji>'
EMOJI_WIN_MONEY = '<tg-emoji emoji-id="5463046637842608206">💰</tg-emoji>'
EMOJI_CHART = '<tg-emoji emoji-id="5429463966432643712">📈</tg-emoji>'
EMOJI_TOP = '<tg-emoji emoji-id="5226431245918942763">🔝</tg-emoji>'
EMOJI_CHECK = '<tg-emoji emoji-id="5805523262691611326">☑️</tg-emoji>'
EMOJI_WIN_CHECK = '<tg-emoji emoji-id="5805523262691611326">✅</tg-emoji>'
EMOJI_PARTY = '<tg-emoji emoji-id="5226431245918942763">🎉</tg-emoji>'
EMOJI_SAD = '<tg-emoji emoji-id="5226813248900187912">😱</tg-emoji>'
EMOJI_KEY = '<tg-emoji emoji-id="5469956488351025557">🔑</tg-emoji>'
EMOJI_CROSS = '<tg-emoji emoji-id="5454350746407419714">❌</tg-emoji>'
EMOJI_CARD = '<tg-emoji emoji-id="5472250091332993630">💳</tg-emoji>'

# Иконки прогресса уровня (12 этапов подъема)
LEVEL_ICONS = {
    0: "🚪",
    1: "🏚️",
    2: "🛖",
    3: "🏠",
    4: "🏡",
    5: "🏢",
    6: "🏛️",
    7: "🏰",
    8: "🕌",
    9: "⛩️",
    10: "🗿",
    11: "👑",
    12: "👑"
}


def fmt_q(val: float) -> str:
    """Форматирование чисел с апострофом ' (например: 10'000, 23'200)"""
    if val < 1:
        return "0"
    if abs(val - round(val)) < 1e-9:
        return f"{int(val):,}".replace(",", "'")
    return f"{val:,.2f}".replace(",", "'")


def calculate_pyramid_multiplier(safe_doors: int, level: int) -> float:
    """
    Расчет коэффициента выигрыша:
    - 4 двери в каждом ряду
    - safe_doors: количество безопасных дверей (1, 2 или 3)
    - RTP: ~98%
    """
    if level == 0:
        return 1.0
    step = 4.0 / float(safe_doors)
    return round((step ** level) * 0.98, 2)


def generate_pyramid_board(safe_doors_count: int) -> list:
    """Генерирует 12 уровней. Каждый уровень имеет 4 двери (True = Выигрыш⭐, False = Ловушка💀)"""
    board = []
    for _ in range(12):
        level = [False] * 4
        safe_indices = random.sample(range(4), safe_doors_count)
        for idx in safe_indices:
            level[idx] = True
        board.append({"cells": level, "opened_cell": None})
    return board


def create_pyramid_fair_game(user_id: int, bet: float, safe_doors: int, board: list) -> str:
    """Создает запись честности раунда (SHA-256)"""
    salt = secrets.token_hex(16)
    board_summary = []
    for lvl_idx, lvl in enumerate(board):
        safe_in_lvl = [c_idx for c_idx, is_safe in enumerate(lvl["cells"]) if is_safe]
        board_summary.append(f"L{lvl_idx}:" + ",".join(map(str, safe_in_lvl)))

    board_str = "|".join(board_summary)
    raw_str = f"pyramid:{safe_doors}:{board_str}:{salt}"
    sha_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    fair_id = secrets.token_hex(8)

    PYRAMID_FAIR_CACHE[fair_id] = {
        "user_id": int(user_id),
        "bet": float(bet),
        "safe_doors": int(safe_doors),
        "board": board,
        "salt": str(salt),
        "raw_str": str(raw_str),
        "sha_hash": str(sha_hash),
        "is_win": False,
        "win_amount": 0.0,
        "current_multiplier": 1.0,
        "current_level": 0,
        "status": "lost"
    }

    if len(PYRAMID_FAIR_CACHE) > 1000:
        oldest_key = next(iter(PYRAMID_FAIR_CACHE))
        PYRAMID_FAIR_CACHE.pop(oldest_key, None)

    return fair_id


def render_next_pyramid_levels_str(safe_doors: int, current_level: int) -> str:
    """Формирует подпись следующего уровня с иконками"""
    parts = []
    for i in range(1, 6):
        lvl = current_level + i
        if lvl <= 12:
            mult = calculate_pyramid_multiplier(safe_doors, lvl)
            icon = LEVEL_ICONS.get(lvl, "🚪")
            parts.append(f"x{mult:.2f} {icon}")
    return " ➡️ ".join(parts) + " ➡️ ..."


def render_pyramid_keyboard(game: dict, fair_id: str = None) -> InlineKeyboardMarkup:
    """
    Формирует сетку 2х2 из 4 дверей на текущем уровне.
    В инлайн-кнопках используются ТОЛЬКО стандартные эмодзи.
    """
    keyboard = []
    status = game["status"]
    current_level = game["current_level"]
    safe_doors = game["safe_doors"]

    if status == "playing":
        icon = LEVEL_ICONS.get(current_level, "🚪")
        # 4 двери в виде сетки 2x2
        keyboard.append([
            InlineKeyboardButton(text=icon, callback_data=f"pyramid_click:{current_level}:0"),
            InlineKeyboardButton(text=icon, callback_data=f"pyramid_click:{current_level}:1")
        ])
        keyboard.append([
            InlineKeyboardButton(text=icon, callback_data=f"pyramid_click:{current_level}:2"),
            InlineKeyboardButton(text=icon, callback_data=f"pyramid_click:{current_level}:3")
        ])

        if current_level == 0:
            # На старте (уровень 0) выводятся кнопки Честность и Отменить
            f_id = fair_id or game.get("fair_id")
            keyboard.append([
                InlineKeyboardButton(text="Честность 🔑", callback_data=f"pyramid_fair:{f_id}", style="success"),
                InlineKeyboardButton(text="Отменить ❌", callback_data="pyramid_cancel", style="danger")
            ])
        else:
            # Во время игры со 2-го хода -> «Забрать награду ✅»
            keyboard.append([
                InlineKeyboardButton(text="Забрать награду ✅", callback_data="pyramid_cashout", style="success")
            ])

    elif status == "lost":
        # При проигрыше показываем 4 двери раскрытого уровня (⭐ и 💀)
        level_data = game["board"][current_level]
        row1, row2 = [], []

        for idx, is_safe in enumerate(level_data["cells"]):
            btn_text = "⭐" if is_safe else "💀"
            btn = InlineKeyboardButton(text=btn_text, callback_data="pyramid_noop")
            if idx < 2:
                row1.append(btn)
            else:
                row2.append(btn)

        keyboard.append(row1)
        keyboard.append(row2)

        f_id = fair_id or game.get("fair_id")
        keyboard.append([
            InlineKeyboardButton(text="🔄 Повторить", callback_data=f"pyramid_repeat:{f_id}", style="primary"),
            InlineKeyboardButton(text="🔑 Честность", callback_data=f"pyramid_fair:{f_id}", style="success")
        ])

    elif status == "won":
        # При победе или кэшауте
        f_id = fair_id or game.get("fair_id")
        keyboard.append([
            InlineKeyboardButton(text="🔄 Повторить", callback_data=f"pyramid_repeat:{f_id}", style="primary"),
            InlineKeyboardButton(text="🔑 Честность", callback_data=f"pyramid_fair:{f_id}", style="success")
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(Command("pyramid"))
@router.message(F.text.lower().in_(["пирамида", "/pyramid"]))
async def pyramid_help_cmd(message: Message, state: FSMContext):
    """Вывод справки по игре Пирамида"""
    await state.clear()
    first_name = html.escape(message.from_user.first_name)

    text = (
        f"<blockquote>{EMOJI_INFO} Пирамида — это игра, где в каждом раунде перед вами 4 двери. Выберите одну и поднимайтесь всё выше: "
        f"от заброшенной развалюхи до священной вершины. Дойдите до вершины и заберите максимум. "
        f"Чем меньше доступных дверей, тем выше выигрыш.\n"
        f"{EMOJI_GRAPH} Лимиты:\n"
        f"RTP: ~98%\n"
        f"Макс. множитель: x16,441,671\n"
        f"Макс. ставка: 250kk n¢\n"
        f"Макс. выигрыш: 1.50kkk n¢</blockquote>\n\n"
        f"{EMOJI_ROBOT} <b>{first_name}</b>, чтобы начать игру, используй команду:\n\n"
        f"{EMOJI_RUNNER} <b>/pyramid [ставка] [1-3]</b>\n\n"
        f"Пример: /pyramid 100 1\n"
        f"Пример: пирамида 100"
    )

    await message.answer(text, parse_mode="HTML")


@router.message(StateFilter(None), F.text, F.text.lower().startswith(("пирамида", "/pyramid")))
async def start_pyramid_game_cmd(message: Message, state: FSMContext):
    """Запуск игры по команде"""
    await state.clear()
    parts = message.text.lower().split()

    if len(parts) == 1:
        return await pyramid_help_cmd(message, state)

    user_id = message.from_user.id
    user = db.get_user(user_id)
    user_balance = float(user.get("balance", 0))

    bet = None
    safe_doors = 3  # По умолчанию 3 безопасные двери (1 ловушка)

    try:
        bet = utils.parse_bet_input(parts[1], user_balance)
    except Exception:
        try:
            bet = utils.parse_bet_input(parts[1])
        except Exception:
            bet = None

    if len(parts) >= 3:
        try:
            d = int(parts[2])
            if d in [1, 2, 3]:
                safe_doors = d
            else:
                return await message.answer(f"{EMOJI_CROSS} Количество верных дверей должно быть от 1 до 3!", parse_mode="HTML")
        except ValueError:
            pass

    if bet is None or bet <= 0:
        return await message.answer(f"{EMOJI_CROSS} Неверный формат ставки!", parse_mode="HTML")

    if user_balance < bet:
        return await message.answer(
            f"{EMOJI_CROSS} Недостаточно n¢! Ваш баланс: <b>{fmt_q(user_balance)} n¢</b>",
            parse_mode="HTML"
        )

    if user_id in ACTIVE_PYRAMID_GAMES:
        return await message.answer(f"{EMOJI_CROSS} У вас уже запущена игра в пирамиду! Завершите её.")

    await start_pyramid_round(message, user_id, bet, safe_doors)


async def start_pyramid_round(event, user_id: int, bet: float, safe_doors: int):
    """Инициализация раунда и списание баланса"""
    db.update_balance(user_id, -bet)

    board = generate_pyramid_board(safe_doors)
    fair_id = create_pyramid_fair_game(user_id, bet, safe_doors, board)

    ACTIVE_PYRAMID_GAMES[user_id] = {
        "bet": bet,
        "safe_doors": safe_doors,
        "board": board,
        "current_level": 0,
        "current_multiplier": 1.0,
        "status": "playing",
        "fair_id": fair_id
    }

    game = ACTIVE_PYRAMID_GAMES[user_id]
    next_m_str = render_next_pyramid_levels_str(safe_doors, 0)

    text = (
        f"{EMOJI_RUNNER} <b>Пирамида · начни путь!</b>\n"
        "·····················\n"
        f"{EMOJI_DOOR} Двери: {safe_doors}\n"
        f"{EMOJI_MONEY} Ставка: {fmt_q(bet)} n¢\n\n"
        f"{EMOJI_CHART} <b>Следующий уровень:</b>\n"
        f"| <code>{next_m_str}</code>"
    )

    kb = render_pyramid_keyboard(game, fair_id)

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    elif isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ==============================================================================
# 🕹 ИГРОВОЙ ПРОЦЕСС
# ==============================================================================

@router.callback_query(F.data.startswith("pyramid_click:"))
async def process_pyramid_click(callback: CallbackQuery):
    """Обработка выбора двери"""
    user_id = callback.from_user.id
    game = ACTIVE_PYRAMID_GAMES.get(user_id)

    if not game or game["status"] != "playing":
        await callback.answer("Игра завершена.")
        return

    _, level_str, cell_str = callback.data.split(":")
    clicked_level = int(level_str)
    clicked_cell = int(cell_str)

    if clicked_level != game["current_level"]:
        await callback.answer(f"{EMOJI_CROSS} Выбирайте двери текущего уровня!", show_alert=True)
        return

    fair_id = game["fair_id"]
    is_safe = game["board"][clicked_level]["cells"][clicked_cell]

    # ПОДРЫВ / ЛОВУШКА (ПРОИГРЫШ)
    if not is_safe:
        game["board"][clicked_level]["opened_cell"] = clicked_cell
        game["status"] = "lost"

        db.add_stats(user_id, is_lost=True, lost_amount=game["bet"], bet_amount=game["bet"])

        if fair_id in PYRAMID_FAIR_CACHE:
            PYRAMID_FAIR_CACHE[fair_id].update({
                "status": "lost",
                "current_level": game["current_level"],
                "board": game["board"]
            })

        cashout_win = round(game["bet"] * game["current_multiplier"], 2)
        mult_str = f"{game['current_multiplier']:.2f}".replace(".", ",")

        text = (
            f"{EMOJI_SAD} <b>Пирамида · Проигрыш!</b>\n"
            "·····················\n"
            f"{EMOJI_DOOR} Двери: {game['safe_doors']}\n"
            f"{EMOJI_MONEY} Ставка: {fmt_q(game['bet'])} n¢\n"
            f"{EMOJI_TOP} Пройдено: {game['current_level']} из 12\n\n"
            f"{EMOJI_CHECK} Мог забрать: x{mult_str} / {fmt_q(cashout_win)} n¢"
        )

        kb = render_pyramid_keyboard(game, fair_id)
        ACTIVE_PYRAMID_GAMES.pop(user_id, None)

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    # УСПЕШНЫЙ ШАГ ВВЕРХ
    game["board"][clicked_level]["opened_cell"] = clicked_cell
    game["current_level"] += 1
    game["current_multiplier"] = calculate_pyramid_multiplier(game["safe_doors"], game["current_level"])

    # ПОЛНАЯ ПОБЕДА (Достигнута вершина 12 уровней)
    if game["current_level"] >= 12:
        win_amount = round(game["bet"] * game["current_multiplier"], 2)
        game["status"] = "won"

        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=game["bet"])

        if fair_id in PYRAMID_FAIR_CACHE:
            PYRAMID_FAIR_CACHE[fair_id].update({
                "status": "won",
                "is_win": True,
                "win_amount": win_amount,
                "current_multiplier": game["current_multiplier"],
                "current_level": 12,
                "board": game["board"]
            })

        mult_str = f"{game['current_multiplier']:.2f}".replace(".", ",")
        text = (
            f"{EMOJI_PARTY} <b>Пирамида · Победа!</b> {EMOJI_WIN_CHECK}\n"
            "·····················\n"
            f"{EMOJI_DOOR} Двери: {game['safe_doors']}\n"
            f"{EMOJI_MONEY} Ставка: {fmt_q(game['bet'])} n¢\n"
            f"{EMOJI_TOP} Пройдено: 12 из 12\n\n"
            f"{EMOJI_WIN_MONEY} Выигрыш: x{mult_str} / <b>{fmt_q(win_amount)} n¢</b>"
        )

        kb = render_pyramid_keyboard(game, fair_id)
        ACTIVE_PYRAMID_GAMES.pop(user_id, None)

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    # ИГРА ПРОДОЛЖАЕТСЯ
    cashout_win = round(game["bet"] * game["current_multiplier"], 2)
    next_m_str = render_next_pyramid_levels_str(game["safe_doors"], game["current_level"])
    mult_str = f"{game['current_multiplier']:.2f}".replace(".", ",")

    text = (
        f"{EMOJI_RUNNER} <b>Пирамида · игра идёт.</b>\n"
        "·····················\n"
        f"{EMOJI_DOOR} Двери: {game['safe_doors']}\n"
        f"{EMOJI_MONEY} Ставка: {fmt_q(game['bet'])} n¢\n"
        f"{EMOJI_WIN_MONEY} Выигрыш: x{mult_str} / {fmt_q(cashout_win)} n¢\n\n"
        f"{EMOJI_CHART} <b>Следующий уровень:</b>\n"
        f"| <code>{next_m_str}</code>"
    )

    kb = render_pyramid_keyboard(game)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "pyramid_cashout")
async def process_pyramid_cashout(callback: CallbackQuery):
    """Забор набранной награды"""
    user_id = callback.from_user.id
    game = ACTIVE_PYRAMID_GAMES.pop(user_id, None)

    if not game or game["status"] != "playing":
        await callback.answer("Игра завершена.")
        return

    fair_id = game["fair_id"]
    win_amount = round(game["bet"] * game["current_multiplier"], 2)
    game["status"] = "won"

    db.update_balance(user_id, win_amount)
    db.add_stats(user_id, is_lost=False, bet_amount=game["bet"])

    if fair_id in PYRAMID_FAIR_CACHE:
        PYRAMID_FAIR_CACHE[fair_id].update({
            "status": "won",
            "is_win": True,
            "win_amount": win_amount,
            "current_multiplier": game["current_multiplier"],
            "current_level": game["current_level"],
            "board": game["board"]
        })

    mult_str = f"{game['current_multiplier']:.2f}".replace(".", ",")
    text = (
        f"{EMOJI_PARTY} <b>Пирамида · Награда забрана!</b> {EMOJI_WIN_CHECK}\n"
        "·····················\n"
        f"{EMOJI_DOOR} Двери: {game['safe_doors']}\n"
        f"{EMOJI_MONEY} Ставка: {fmt_m(game['bet'])} n¢\n"
        f"{EMOJI_TOP} Пройдено: {game['current_level']} из 12\n\n"
        f"{EMOJI_WIN_MONEY} Выигрыш: x{mult_str} / <b>{fmt_q(win_amount)} n¢</b>"
    )

    kb = render_pyramid_keyboard(game, fair_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "pyramid_cancel")
async def process_pyramid_cancel(callback: CallbackQuery):
    """Отмена раунда до первого хода (с возвратом полной ставки)"""
    user_id = callback.from_user.id
    game = ACTIVE_PYRAMID_GAMES.pop(user_id, None)

    if not game or game["current_level"] > 0:
        await callback.answer("Отменить можно только до первого хода!", show_alert=True)
        return

    db.update_balance(user_id, game["bet"])
    await callback.answer("Игра отменена, ставка возвращена.")
    await callback.message.delete()


@router.callback_query(F.data == "pyramid_noop")
async def pyramid_noop(callback: CallbackQuery):
    await callback.answer()


# ==============================================================================
# 🔄 ПОВТОРИТЬ И 🔑 ЧЕСТНОСТЬ
# ==============================================================================

@router.callback_query(F.data.startswith("pyramid_repeat:"), StateFilter("*"))
async def pyramid_repeat_callback(callback: CallbackQuery, state: FSMContext):
    """Повтор раунда с той же ставкой и количеством верных дверей"""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer(f"{EMOJI_CROSS} Ошибка данных.", show_alert=True)

        fair_id = parts[1]
        previous_game = PYRAMID_FAIR_CACHE.get(fair_id)

        if not previous_game:
            return await callback.answer(f"{EMOJI_CROSS} Данные предыдущей игры устарели.", show_alert=True)

        if int(previous_game["user_id"]) != int(callback.from_user.id):
            return await callback.answer(f"{EMOJI_CROSS} Это не ваша игра.", show_alert=True)

        bet = float(previous_game["bet"])
        safe_doors = int(previous_game["safe_doors"])

        user = db.get_user(callback.from_user.id)
        if float(user.get("balance", 0)) < bet:
            return await callback.answer("❌ Недостаточно n¢! Ваш баланс: {fmt_q(user.get('balance', 0))} n¢", show_alert=True)

        await state.clear()
        await callback.answer()
        await start_pyramid_round(callback, callback.from_user.id, bet, safe_doors)

    except Exception as error:
        logger.exception("Ошибка повтора Пирамида: %s", error)
        try:
            await callback.answer(f"{EMOJI_CROSS} Не удалось повторить игру.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("pyramid_fair:"), StateFilter("*"))
async def pyramid_fair_callback(callback: CallbackQuery):
    """Просмотр хэша SHA-256 и расположения безопасных дверей/ловушек"""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer(f"{EMOJI_CROSS} Ошибка вызова.", show_alert=True)

        fair_id = parts[1]
        fair_data = PYRAMID_FAIR_CACHE.get(fair_id)

        if not fair_data:
            return await callback.answer(f"{EMOJI_CROSS} Данные раунда устарели или бот был перезапущен.", show_alert=True)

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            return await callback.answer(f"{EMOJI_CROSS} Это не ваша игра.", show_alert=True)

        await callback.answer()

        raw_str = html.escape(str(fair_data["raw_str"]))
        sha_hash = html.escape(str(fair_data["sha_hash"]))
        safe_doors = fair_data["safe_doors"]

        board_lines = []
        for lvl_idx, lvl in enumerate(fair_data["board"]):
            row_str = "".join(["⭐" if is_safe else "💀" for is_safe in lvl["cells"]])
            board_lines.append(f"Уровень {lvl_idx + 1:2d}: <code>{row_str}</code>")

        board_preview = "\n".join(board_lines)

        text = (
            f"{EMOJI_RUNNER} <b>Пирамида · Честность</b> {EMOJI_KEY}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔢 <b>SHA-256 Хэш раунда:</b>\n"
            f"<code>{sha_hash}</code>\n\n"
            "🔑 <b>Результат (Raw):</b>\n"
            f"<code>{raw_str}</code>\n\n"
            f"{EMOJI_DOOR} <b>Карта дверей по 12 уровням (безопасных дверей: {safe_doors}):</b>\n"
            f"{board_preview}\n\n"
            "<blockquote>"
            "Расположение всех верных дверей на 12 уровнях генерируется до первого хода. "
            "Скопируйте строку Результата и вставьте её на любом онлайн-сканере SHA-256. "
            "Сгенерированный хэш точно совпадёт с Хэшем раунда!"
            "</blockquote>"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"pyramid_fair_back:{fair_id}"),
                InlineKeyboardButton(text="Проверить SHA-256 🔑", url="https://emn178.github.io/online-tools/")
            ]
        ])

        if callback.message:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    except Exception as error:
        logger.exception("Ошибка честности Пирамида: %s", error)
        try:
            await callback.answer("❌ Не удалось открыть данные честности.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("pyramid_fair_back:"), StateFilter("*"))
async def pyramid_fair_back_callback(callback: CallbackQuery):
    """Возврат к исходной карточке с результатами игры"""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Неверный запрос.", show_alert=True)

        fair_id = parts[1]
        fair_data = PYRAMID_FAIR_CACHE.get(fair_id)

        if not fair_data:
            return await callback.answer("❌ Данные игры устарели.", show_alert=True)

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        await callback.answer()

        status = fair_data.get("status")
        bet = fair_data["bet"]
        safe_doors = fair_data["safe_doors"]

        if status == "won":
            win_amount = fair_data["win_amount"]
            mult_str = f"{fair_data['current_multiplier']:.2f}".replace(".", ",")
            text = (
                f"{EMOJI_PARTY} <b>Пирамида · Награда забрана!</b> {EMOJI_WIN_CHECK}\n"
                "·····················\n"
                f"{EMOJI_DOOR} Двери: {safe_doors}\n"
                f"{EMOJI_MONEY} Ставка: {fmt_q(bet)} n¢\n"
                f"{EMOJI_TOP} Пройдено: {fair_data['current_level']} из 12\n\n"
                f"{EMOJI_WIN_MONEY} Выигрыш: x{mult_str} / <b>{fmt_q(win_amount)} n¢</b>"
            )
        elif status == "playing":
            next_m_str = render_next_pyramid_levels_str(safe_doors, fair_data['current_level'])
            text = (
                f"{EMOJI_RUNNER} <b>Пирамида · начни путь!</b>\n"
                "·····················\n"
                f"{EMOJI_DOOR} Двери: {safe_doors}\n"
                f"{EMOJI_MONEY} Ставка: {fmt_q(bet)} n¢\n\n"
                f"{EMOJI_CHART} <b>Следующий уровень:</b>\n"
                f"| <code>{next_m_str}</code>"
            )
        else:
            cashout_win = round(bet * fair_data["current_multiplier"], 2)
            mult_str = f"{fair_data['current_multiplier']:.2f}".replace(".", ",")
            text = (
                f"{EMOJI_SAD} <b>Пирамида · Проигрыш!</b>\n"
                "·····················\n"
                f"{EMOJI_DOOR} Двери: {safe_doors}\n"
                f"{EMOJI_MONEY} Ставка: {fmt_q(bet)} n¢\n"
                f"{EMOJI_TOP} Пройдено: {fair_data['current_level']} из 12\n\n"
                f"{EMOJI_CHECK} Мог забрать: x{mult_str} / {fmt_q(cashout_win)} n¢"
            )

        dummy_game = {
            "status": status,
            "current_level": fair_data["current_level"],
            "board": fair_data["board"],
            "safe_doors": safe_doors,
            "fair_id": fair_id
        }

        kb = render_pyramid_keyboard(dummy_game, fair_id)

        if callback.message:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

    except Exception as error:
        logger.exception("Ошибка возврата в Пирамиде: %s", error)
        try:
            await callback.answer("❌ Не удалось вернуться.", show_alert=True)
        except Exception:
            pass
