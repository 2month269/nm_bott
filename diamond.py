# diamond.py
import asyncio
import html
import logging
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

import db
import utils

logger = logging.getLogger(__name__)

router = Router()

ACTIVE_DIAMOND_GAMES = {}  # {user_id: game_state}

EMOJI_INFO = '<tg-emoji emoji-id="5467403607286502523">ℹ️</tg-emoji>'
EMOJI_GRAPH = '<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji>'
EMOJI_ROBOT = '<tg-emoji emoji-id="5350612670435313545">🤖</tg-emoji>'
EMOJI_DIAMOND = '<tg-emoji emoji-id="5767137507879685567">💎</tg-emoji>'
EMOJI_CLOVER = '<tg-emoji emoji-id="5767137507879685567">☘️</tg-emoji>'
EMOJI_MINE = '<tg-emoji emoji-id="5249496324105062810">🧨</tg-emoji>'
EMOJI_MONEY = '<tg-emoji emoji-id="5463046637842608206">💸</tg-emoji>'
EMOJI_LADDER = '<tg-emoji emoji-id="5465198403573012261">🪜</tg-emoji>'
EMOJI_CHECK = '<tg-emoji emoji-id="5805523262691611326">✅</tg-emoji>'
EMOJI_BAG = '<tg-emoji emoji-id="5463046637842608206">💰</tg-emoji>'
EMOJI_PARTY = '<tg-emoji emoji-id="5226431245918942763">🎉</tg-emoji>'
EMOJI_BOOM = '<tg-emoji emoji-id="5226813248900187912">💥</tg-emoji>'
EMOJI_CROSS = '<tg-emoji emoji-id="5454350746407419714">❌</tg-emoji>'
EMOJI_CARD = '<tg-emoji emoji-id="5472250091332993630">💳</tg-emoji>'
EMOJI_ARROW = '<tg-emoji emoji-id="5462881955911584183">➡️</tg-emoji>'


def fmt_m(val: float) -> str:
    """Форматирование чисел с разделителем ' (например: 10'000, 49'100)"""
    if val < 1:
        return "0"
    if abs(val - round(val)) < 1e-9:
        return f"{int(val):,}".replace(",", "'")
    return f"{val:,.2f}".replace(",", "'")


def calculate_diamond_multiplier(mines: int, level: int) -> float:
    """Расчет коэффициента выигрыша (16 уровней, 3 ячейки)"""
    if level == 0:
        return 1.0
    step = 3.0 / (3.0 - mines)
    return round((step ** level) * 0.97, 2)


def generate_diamond_level(mines_count: int) -> list:
    """Генерирует 1 ряд из 3 ячеек (True = мина, False = алмаз/безопасно)"""
    level = [False] * 3
    mine_indices = random.sample(range(3), mines_count)
    for idx in mine_indices:
        level[idx] = True
    return level


def render_diamond_keyboard(game: dict) -> InlineKeyboardMarkup:
    """
    Генерирует клавиатуру ячеек.
    В inline-кнопках используются только обычные emoji без HTML-тегов.
    """
    keyboard_inline = []
    status = game["status"]
    current_level = game["current_level"]

    if status == "playing":
        visible_levels = range(current_level + 1)
    elif status == "lost":
        visible_levels = range(current_level + 1)
    else:
        visible_levels = range(max(1, current_level))

    for level_num in visible_levels:
        level_data = game["board"][level_num]
        row_buttons = []

        for cell_idx, is_mine in enumerate(level_data["cells"]):
            btn_text = "❓"
            callback_data = f"diamond_click:{level_num}:{cell_idx}"

            if status == "playing":
                if level_num < current_level:
                    if level_data.get("opened_cell") == cell_idx:
                        btn_text = "🔹"
                    else:
                        btn_text = "❓"
                    callback_data = "diamond_noop"
                elif level_num == current_level:
                    btn_text = "❓"
                    callback_data = f"diamond_click:{level_num}:{cell_idx}"

            elif status == "lost":
                if level_num == current_level and level_data.get("opened_cell") == cell_idx:
                    btn_text = "🧨"
                elif is_mine:
                    btn_text = "🧨"
                else:
                    if level_data.get("opened_cell") == cell_idx:
                        btn_text = "🔹"
                    else:
                        btn_text = "💰"
                callback_data = "diamond_noop"

            elif status == "won":
                if is_mine:
                    btn_text = "🧨"
                elif level_data.get("opened_cell") == cell_idx:
                    btn_text = "🔹"
                else:
                    btn_text = "💰"
                callback_data = "diamond_noop"

            row_buttons.append(
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=callback_data
                )
            )

        keyboard_inline.append(row_buttons)

    # Забрать выигрыш доступно только во время активной игры
    if status == "playing" and current_level > 0:
        keyboard_inline.append([
            InlineKeyboardButton(
                text="Забрать выигрыш ✅",
                callback_data="diamond_cashout"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_inline)


def render_next_levels_str(mines_count: int, current_level: int) -> str:
    """Формирует строку со следующими коэффициентами"""
    parts = []
    for i in range(1, 6):
        lvl = current_level + i
        if lvl <= 16:
            mult = calculate_diamond_multiplier(mines_count, lvl)
            parts.append(f"{lvl} • x{mult:.2f}")
    return " ➡️ ".join(parts) + " ➡️ ..."


# ==============================================================================
# 🎯 СПРАВКА И СТАРТ ИГРЫ
# ==============================================================================

@router.message(Command("diamond"))
@router.message(F.text.lower().in_(["алмазы", "алмаз", "/diamond"]))
async def diamond_help_cmd(message: Message, state: FSMContext):
    """Вывод меню справки"""
    await state.clear()
    first_name = html.escape(message.from_user.first_name)

    text = (
        f"<blockquote>{EMOJI_INFO} Алмазная лихорадка — это игра, в которой необходимо угадать, в какой ячейке спрятан алмаз. "
        f"Вам нужно открывать по одной ячейке на каждом из 16 уровней, чтобы найти алмаз.\n"
        f"{EMOJI_GRAPH} Лимиты:\n"
        f"RTP: ~97%\n"
        f"Макс. множитель: x41,755,319\n"
        f"Макс. ставка: 250kk m¢\n"
        f"Макс. выигрыш: 2kkk m¢</blockquote>\n\n"
        f"{EMOJI_ROBOT} <b>{first_name}</b>, чтобы начать игру, используй команду:\n\n"
        f"{EMOJI_DIAMOND} <b>/diamond [ставка] [мины 1-2]</b>\n\n"
        f"Пример: /diamond 100 2\n"
        f"Пример: алмазы 100"
    )

    await message.answer(text, parse_mode="HTML")


@router.message(StateFilter(None), F.text, F.text.lower().startswith(("алмазы", "алмаз", "/diamond")))
async def start_diamond_game_cmd(message: Message, state: FSMContext):
    """Старт раунда по команде"""
    await state.clear()
    parts = message.text.lower().split()

    if len(parts) == 1:
        return await diamond_help_cmd(message, state)

    user_id = message.from_user.id
    user = db.get_user(user_id)
    user_balance = float(user.get("balance", 0))

    bet = None
    mines_count = 1

    try:
        bet = utils.parse_bet_input(parts[1], user_balance)
    except Exception:
        try:
            bet = utils.parse_bet_input(parts[1])
        except Exception:
            bet = None

    if len(parts) >= 3:
        try:
            m = int(parts[2])
            if m in [1, 2]:
                mines_count = m
            else:
                return await message.answer(
                    f"{EMOJI_CROSS} Мин на уровень должно быть 1 или 2!",
                    parse_mode="HTML"
                )
        except ValueError:
            pass

    if bet is None or bet <= 0:
        return await message.answer(
            f"{EMOJI_CROSS} Неверный формат ставки!",
            parse_mode="HTML"
        )

    if user_balance < bet:
        return await message.answer(
            f"{EMOJI_CROSS} Недостаточно m¢! Ваш баланс: "
            f"<b>{fmt_m(user_balance)} m¢</b>",
            parse_mode="HTML"
        )

    if user_id in ACTIVE_DIAMOND_GAMES:
        return await message.answer(
            "❌ У вас уже запущена игра в алмазы! Завершите её."
        )

    await start_diamond_round(message, user_id, bet, mines_count)


async def start_diamond_round(event, user_id: int, bet: float, mines_count: int):
    """Инициализация игрового поля и списывание баланса"""
    db.update_balance(user_id, -bet)

    board = []
    for _ in range(16):
        board.append({
            "cells": generate_diamond_level(mines_count),
            "opened_cell": None
        })

    ACTIVE_DIAMOND_GAMES[user_id] = {
        "bet": bet,
        "mines_count": mines_count,
        "board": board,
        "current_level": 0,
        "current_multiplier": 1.0,
        "status": "playing"
    }

    game = ACTIVE_DIAMOND_GAMES[user_id]
    next_m_str = render_next_levels_str(mines_count, 0)

    text = (
        f"{EMOJI_CLOVER} <b>Алмазы · начни игру!</b>\n"
        "⠀\n"
        f"{EMOJI_MINE} Мин: {mines_count}\n"
        f"{EMOJI_MONEY} Ставка: {fmt_m(bet)} m¢\n\n"
        f"{EMOJI_LADDER} <b>Следующий ряд:</b>\n"
        f"| <code>{next_m_str}</code>"
    )

    await event.answer(
        text,
        reply_markup=render_diamond_keyboard(game),
        parse_mode="HTML"
    )


# ==============================================================================
# 🕹 ИГРОВОЙ ПРОЦЕСС
# ==============================================================================

@router.callback_query(F.data.startswith("diamond_click:"))
async def process_diamond_click(callback: CallbackQuery):
    """Обработка нажатия на ячейку ряда"""
    user_id = callback.from_user.id
    game = ACTIVE_DIAMOND_GAMES.get(user_id)

    if not game or game["status"] != "playing":
        await callback.answer("Игра завершена.")
        return

    _, level_str, cell_str = callback.data.split(":")
    clicked_level = int(level_str)
    clicked_cell = int(cell_str)

    if clicked_level != game["current_level"]:
        await callback.answer(
            "❌ Нажимайте ячейки текущего уровня!",
            show_alert=True
        )
        return

    is_mine = game["board"][clicked_level]["cells"][clicked_cell]

    # ПОДРЫВ НА МИНЕ
    if is_mine:
        game["board"][clicked_level]["opened_cell"] = clicked_cell
        game["status"] = "lost"

        db.add_stats(
            user_id,
            is_lost=True,
            lost_amount=game["bet"],
            bet_amount=game["bet"]
        )
        user_updated = db.get_user(user_id)

        text = (
            f"{EMOJI_BOOM} <b>Алмазы · Проигрыш!</b>\n"
            "⠀\n"
            f"{EMOJI_MINE} Мин: {game['mines_count']}\n"
            f"{EMOJI_MONEY} Ставка: {fmt_m(game['bet'])} m¢\n"
            f"{EMOJI_LADDER} Пройдено: {game['current_level']} из 16\n\n"
            f"{EMOJI_CARD} Баланс: <b>{fmt_m(user_updated['balance'])} m¢</b>"
        )

        kb = render_diamond_keyboard(game)
        ACTIVE_DIAMOND_GAMES.pop(user_id, None)

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    # УСПЕШНЫЙ ХОД
    game["board"][clicked_level]["opened_cell"] = clicked_cell
    game["current_level"] += 1
    game["current_multiplier"] = calculate_diamond_multiplier(
        game["mines_count"],
        game["current_level"]
    )

    # ПОЛНАЯ ПОБЕДА
    if game["current_level"] >= 16:
        win_amount = round(game["bet"] * game["current_multiplier"], 2)
        game["status"] = "won"

        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=game["bet"])

        mult_str = f"{game['current_multiplier']:.2f}".replace(".", ",")
        text = (
            f"{EMOJI_PARTY} <b>Алмазы · Победа!</b> {EMOJI_CHECK}\n"
            "⠀\n"
            f"{EMOJI_MINE} Мин: {game['mines_count']}\n"
            f"{EMOJI_MONEY} Ставка: {fmt_m(game['bet'])} m¢\n"
            f"{EMOJI_LADDER} Пройдено: 16 из 16\n\n"
            f"{EMOJI_BAG} Выигрыш: x{mult_str} / <b>{fmt_m(win_amount)} m¢</b>"
        )

        kb = render_diamond_keyboard(game)
        ACTIVE_DIAMOND_GAMES.pop(user_id, None)

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    # ИГРА ПРОДОЛЖАЕТСЯ
    cashout_win = round(game["bet"] * game["current_multiplier"], 2)
    next_m_str = render_next_levels_str(
        game["mines_count"],
        game["current_level"]
    )
    mult_str = f"{game['current_multiplier']:.2f}".replace(".", ",")

    text = (
        f"{EMOJI_DIAMOND} <b>Алмазы · игра идёт!</b>\n"
        "⠀\n"
        f"{EMOJI_MINE} Мин: {game['mines_count']}\n"
        f"{EMOJI_MONEY} Ставка: {fmt_m(game['bet'])} m¢\n"
        f"{EMOJI_GRAPH} Выигрыш: x{mult_str} / {fmt_m(cashout_win)} m¢\n\n"
        f"{EMOJI_LADDER} <b>Следующий ряд:</b>\n"
        f"| <code>{next_m_str}</code>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=render_diamond_keyboard(game),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "diamond_cashout")
async def process_diamond_cashout(callback: CallbackQuery):
    """Забор выигрыша игроком"""
    user_id = callback.from_user.id
    game = ACTIVE_DIAMOND_GAMES.pop(user_id, None)

    if not game or game["status"] != "playing":
        await callback.answer("Игра завершена.")
        return

    win_amount = round(game["bet"] * game["current_multiplier"], 2)
    game["status"] = "won"

    db.update_balance(user_id, win_amount)
    db.add_stats(user_id, is_lost=False, bet_amount=game["bet"])

    mult_str = f"{game['current_multiplier']:.2f}".replace(".", ",")
    text = (
        f"{EMOJI_PARTY} <b>Алмазы · Победа!</b> {EMOJI_CHECK}\n"
        "⠀\n"
        f"{EMOJI_MINE} Мин: {game['mines_count']}\n"
        f"{EMOJI_MONEY} Ставка: {fmt_m(game['bet'])} m¢\n"
        f"{EMOJI_LADDER} Пройдено: {game['current_level']} из 16\n\n"
        f"{EMOJI_BAG} Выигрыш: x{mult_str} / <b>{fmt_m(win_amount)} m¢</b>"
    )

    kb = render_diamond_keyboard(game)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "diamond_noop")
async def diamond_noop(callback: CallbackQuery):
    await callback.answer()
