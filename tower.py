# tower.py
import random
import hashlib
import html
import secrets

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

import db
import utils

router = Router()
ACTIVE_TOWER_GAMES = {}  # {user_id: game_state}
TOWER_FAIR_CACHE: dict[str, dict] = {}  # Кэш честности раундов Башни

MAX_TOWER_BET = 150_000_000.0  # Максимальная ставка: 25,000,000 n¢ (25кк)

# ==============================================================================
# 👑 ПРЕМИУМ ЭМОДЗИ
# ==============================================================================
EMOJI_TOWER = '<tg-emoji emoji-id="5382239087321172481">🗼</tg-emoji>'
EMOJI_GEM = '<tg-emoji emoji-id="5767137507879685567">💎</tg-emoji>'
EMOJI_BOMB = '<tg-emoji emoji-id="5249496324105062810">💣</tg-emoji>'
EMOJI_CARD = '<tg-emoji emoji-id="6280364500361155698">💳</tg-emoji>'
EMOJI_WRITE = '<tg-emoji emoji-id="5197269100878907942">✍️</tg-emoji>'
EMOJI_CROSS = '<tg-emoji emoji-id="5454350746407419714">❌</tg-emoji>'
EMOJI_CASH = '<tg-emoji emoji-id="5453901475648390219">💵</tg-emoji>'
EMOJI_TROPHY = '<tg-emoji emoji-id="5226431245918942763">🏆</tg-emoji>'
EMOJI_UP = '<tg-emoji emoji-id="5463122435425448565">⬆️</tg-emoji>'
EMOJI_ARROW = '<tg-emoji emoji-id="5416117059207572332">➡️</tg-emoji>'
EMOJI_BOOM = '<tg-emoji emoji-id="5276032951342088188">💥</tg-emoji>'
EMOJI_BRIEFCASE = '<tg-emoji emoji-id="5368324170671202286">💼</tg-emoji>'
EMOJI_PARTY = '<tg-emoji emoji-id="5989848973974704652">🎉</tg-emoji>'
EMOJI_MONEY = '<tg-emoji emoji-id="5278467510604160626">💰</tg-emoji>'
EMOJI_CHART = '<tg-emoji emoji-id="5368324170671202286">📊</tg-emoji>'
EMOJI_KEY = '<tg-emoji emoji-id="5368324170671202286">🔑</tg-emoji>'
EMOJI_HASH = '<tg-emoji emoji-id="5368324170671202286">🔢</tg-emoji>'


class TowerState(StatesGroup):
    waiting_for_bet = State()


def calculate_tower_multiplier(mines: int, level: int) -> float:
    if level == 0:
        return 1.0
    step = 5 / (5 - mines)
    return round((step ** level) * 0.995, 2)


def generate_tower_level(mines_on_level: int) -> list:
    level = [False] * 5
    mine_indices = random.sample(range(5), mines_on_level)
    for idx in mine_indices:
        level[idx] = True
    return level


def create_tower_fair_game(user_id: int, bet: float, mines_count: int, board: list) -> str:
    """Генерирует доказательство честности раунда Башни SHA-256."""
    salt = secrets.token_hex(16)
    board_summary = []

    for lvl_idx, lvl in enumerate(board):
        mines_in_lvl = [
            c_idx
            for c_idx, is_mine in enumerate(lvl["cells"])
            if is_mine
        ]
        board_summary.append(f"L{lvl_idx}:" + ",".join(map(str, mines_in_lvl)))

    board_str = "|".join(board_summary)
    raw_str = f"tower:{mines_count}:{board_str}:{salt}"
    sha_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    fair_id = secrets.token_hex(8)

    TOWER_FAIR_CACHE[fair_id] = {
        "user_id": int(user_id),
        "bet": float(bet),
        "mines_count": int(mines_count),
        "board": board,
        "salt": salt,
        "raw_str": raw_str,
        "sha_hash": sha_hash,
        "is_win": False,
        "win_amount": 0.0,
        "current_multiplier": 1.0,
        "current_level": 0,
        "status": "lost",
    }

    if len(TOWER_FAIR_CACHE) > 1000:
        oldest_key = next(iter(TOWER_FAIR_CACHE))
        TOWER_FAIR_CACHE.pop(oldest_key, None)

    return fair_id


def render_tower_keyboard(game: dict, fair_id: str = None) -> InlineKeyboardMarkup:
    """
    Клавиатура Башни.

    Во время игры:
    - мины не показываются;
    - активные клетки текущего уровня синие;
    - доступна зелёная кнопка забора выигрыша.

    После окончания игры:
    - поле раскрывается;
    - доступны кнопки «Повторить» и «Честность».
    """
    keyboard_inline = []

    if game["status"] == "won":
        max_visible_level = min(game["current_level"] - 1, 9)
    elif game["status"] == "lost":
        max_visible_level = min(game["current_level"], 9)
    else:
        max_visible_level = min(game["current_level"], 9)

    for level_num in reversed(range(max_visible_level + 1)):
        level_data = game["board"][level_num]
        row_buttons = []

        for cell_idx, is_mine in enumerate(level_data["cells"]):
            text = "❓"
            callback_data = "tower_noop"

            if game["status"] == "playing":
                if level_num < game["current_level"]:
                    # Пройденные уровни: расположение мин скрыто
                    if level_data.get("opened_cell") == cell_idx:
                        text = "💎"
                    else:
                        text = "❓"

                elif level_num == game["current_level"]:
                    # Текущий уровень: все клетки скрыты
                    text = "❓"
                    callback_data = f"tower_click:{level_num}:{cell_idx}"

            elif game["status"] == "lost":
                # После проигрыша раскрываем поле
                if (
                    level_num == game["current_level"]
                    and level_data.get("opened_cell") == cell_idx
                ):
                    text = "💥"
                else:
                    text = "💣" if is_mine else "💎"

            elif game["status"] == "won":
                # После победы раскрываем поле
                text = "💣" if is_mine else "💎"

            button_kwargs = {
                "text": text,
                "callback_data": callback_data,
            }

            # Синие активные клетки текущего уровня
            if (
                game["status"] == "playing"
                and level_num == game["current_level"]
            ):
                button_kwargs["style"] = "primary"

            row_buttons.append(InlineKeyboardButton(**button_kwargs))

        keyboard_inline.append(row_buttons)

    # Зелёная кнопка забора выигрыша
    if game["status"] == "playing" and game["current_level"] > 0:
        keyboard_inline.append([
            InlineKeyboardButton(
                text="Забрать награду ✅",
                callback_data="tower_cashout",
                style="success",
            )
        ])

    # Кнопки после окончания игры
    elif game["status"] in ("lost", "won"):
        f_id = fair_id or game.get("fair_id")

        if f_id:
            keyboard_inline.append([
                InlineKeyboardButton(
                    text="🔄 Повторить",
                    callback_data=f"tower_repeat:{f_id}",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="🔑 Честность",
                    callback_data=f"tower_fair:{f_id}",
                    style="primary",
                ),
            ])
        else:
            keyboard_inline.append([
                InlineKeyboardButton(
                    text="🔄 Играть снова",
                    callback_data="tower_menu",
                    style="primary",
                )
            ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard_inline)


@router.callback_query(F.data == "tower_menu")
async def tower_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = db.get_user(callback.from_user.id)

    text = (
        f"{EMOJI_TOWER} <b>Башня (Tower)</b> {EMOJI_TOWER}\n\n"
        f"Открывай уровни, выбирая кристаллы {EMOJI_GEM} и обходя мины {EMOJI_BOMB}.\n\n"
        f"{EMOJI_CARD} Баланс: <b>{user['balance']:,} nCoin</b>\n\n"
        f"{EMOJI_WRITE} <b>Команды в чате:</b>\n"
        "• <code>башня 1к</code> (по умолчанию 1 мина)\n"
        "• <code>башня 1к 3</code> (3 мины на уровень)"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="games_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text.lower().startswith("башня"))
async def tower_text_cmd(message: Message, state: FSMContext):
    await state.clear()
    parts = message.text.lower().split()
    user_balance = db.get_user(message.from_user.id)["balance"]

    if len(parts) == 2:
        bet = utils.parse_bet_input(parts[1], user_balance)
        mines_count = 1
    elif len(parts) == 3:
        bet = utils.parse_bet_input(parts[1], user_balance)
        try:
            mines_count = int(parts[2])
            if not (1 <= mines_count <= 4):
                raise ValueError
        except ValueError:
            await message.answer(
                f"{EMOJI_CROSS} Мин на уровень должно быть от 1 до 4!",
                parse_mode="HTML",
            )
            return
    else:
        await message.answer(
            f"{EMOJI_CROSS} Используйте: <code>башня &lt;ставка&gt;</code> "
            "или <code>башня &lt;ставка&gt; &lt;мины&gt;</code>",
            parse_mode="HTML",
        )
        return

    if bet <= 0:
        await message.answer(
            f"{EMOJI_CROSS} Неверный формат ставки!",
            parse_mode="HTML",
        )
        return

    if bet > MAX_TOWER_BET:
        await message.answer(
            f"{EMOJI_CROSS} Максимальная ставка в Башне — <b>{MAX_TOWER_BET:,} n¢</b> (25кк)!",
            parse_mode="HTML",
        )
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)

    if user["balance"] < bet:
        await message.answer(
            f"{EMOJI_CROSS} Недостаточно nCoin! Баланс: {user['balance']:,}",
            parse_mode="HTML",
        )
        return

    db.update_balance(user_id, -bet)

    game_board = [
        {
            "cells": generate_tower_level(mines_count),
            "opened_cell": None,
        }
        for _ in range(10)
    ]

    fair_id = create_tower_fair_game(
        user_id,
        bet,
        mines_count,
        game_board,
    )

    ACTIVE_TOWER_GAMES[user_id] = {
        "bet": bet,
        "mines_count": mines_count,
        "board": game_board,
        "current_level": 0,
        "current_multiplier": 1.0,
        "status": "playing",
        "fair_id": fair_id,
    }

    game = ACTIVE_TOWER_GAMES[user_id]
    next_m_str = ""

    for lvl in range(1, 6):
        m_val = calculate_tower_multiplier(mines_count, lvl)
        next_m_str += f" {lvl} • x{m_val:.2f} {EMOJI_ARROW}"

    next_m_str += " ..."

    text = (
        f"{EMOJI_TOWER} Башня · игра идёт.\n"
        "·····················\n"
        f"{EMOJI_BOMB} Мин: {mines_count}\n"
        f"{EMOJI_CASH} Ставка: {bet:,} n¢\n"
        f"{EMOJI_TROPHY} Выигрыш: x1.00 / {bet:,} n¢\n\n"
        f"{EMOJI_UP} <b>Следующий уровень:</b>\n"
        f"|<code>{next_m_str}</code>"
    )

    await message.answer(
        text,
        reply_markup=render_tower_keyboard(game),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("tower_click:"))
async def process_tower_click(callback: CallbackQuery):
    user_id = callback.from_user.id

    if (
        user_id not in ACTIVE_TOWER_GAMES
        or ACTIVE_TOWER_GAMES[user_id]["status"] != "playing"
    ):
        await callback.answer("Игра завершена.")
        return

    game = ACTIVE_TOWER_GAMES[user_id]
    _, level_str, cell_str = callback.data.split(":")
    clicked_level = int(level_str)
    clicked_cell = int(cell_str)

    if clicked_level != game["current_level"]:
        await callback.answer(
            "❌ Нажимайте кнопки текущего активного уровня (строка с ❓)!"
        )
        return

    fair_id = game.get("fair_id")

    if game["board"][clicked_level]["cells"][clicked_cell]:
        game["board"][clicked_level]["opened_cell"] = clicked_cell
        game["status"] = "lost"

        db.add_stats(
            user_id,
            is_lost=True,
            lost_amount=game["bet"],
            bet_amount=game["bet"],
        )

        if fair_id and fair_id in TOWER_FAIR_CACHE:
            TOWER_FAIR_CACHE[fair_id].update({
                "status": "lost",
                "current_level": game["current_level"],
                "current_multiplier": game["current_multiplier"],
                "board": game["board"],
            })

        text = (
            f"{EMOJI_BOOM} <b>Башня · Проигрыш!</b>\n"
            "·····················\n"
            f"{EMOJI_BOMB} Мин: {game['mines_count']}\n"
            f"{EMOJI_CASH} Ставка: {game['bet']:,} n¢\n"
            f"{EMOJI_BRIEFCASE} Пройдено уровней: {game['current_level']} из 10\n\n"
            f"{EMOJI_CARD} Твой баланс: "
            f"<b>{db.get_user(user_id)['balance']:,} nCoin</b>"
        )

        del ACTIVE_TOWER_GAMES[user_id]
        await callback.message.edit_text(
            text,
            reply_markup=render_tower_keyboard(game, fair_id),
            parse_mode="HTML",
        )
        return

    game["board"][clicked_level]["opened_cell"] = clicked_cell
    game["current_level"] += 1
    game["current_multiplier"] = calculate_tower_multiplier(
        game["mines_count"],
        game["current_level"],
    )

    if game["current_level"] >= 10:
        win_amount = round(
            game["bet"] * game["current_multiplier"],
            2,
        )

        db.update_balance(user_id, win_amount)
        db.add_stats(
            user_id,
            is_lost=False,
            bet_amount=game["bet"],
        )
        game["status"] = "won"

        if fair_id and fair_id in TOWER_FAIR_CACHE:
            TOWER_FAIR_CACHE[fair_id].update({
                "status": "won",
                "is_win": True,
                "win_amount": win_amount,
                "current_level": game["current_level"],
                "current_multiplier": game["current_multiplier"],
                "board": game["board"],
            })

        text = (
            f"{EMOJI_PARTY} <b>Башня · Победа!</b> {EMOJI_PARTY}\n"
            f"{EMOJI_MONEY} Выигрыш: "
            f"<b>x{game['current_multiplier']:.2f}</b> / "
            f"<b>{win_amount:,} nCoin</b>\n\n"
            f"{EMOJI_CARD} Баланс: "
            f"<b>{db.get_user(user_id)['balance']:,} nCoin</b>"
        )

        del ACTIVE_TOWER_GAMES[user_id]
        await callback.message.edit_text(
            text,
            reply_markup=render_tower_keyboard(game, fair_id),
            parse_mode="HTML",
        )
        return

    cashout_win = round(
        game["bet"] * game["current_multiplier"],
        2,
    )
    next_m_str = ""

    for lvl_idx in range(1, 6):
        target_lvl = game["current_level"] + lvl_idx
        if target_lvl <= 10:
            m_val = calculate_tower_multiplier(
                game["mines_count"],
                target_lvl,
            )
            next_m_str += f" {target_lvl} • x{m_val:.2f} {EMOJI_ARROW}"

    text = (
        f"{EMOJI_TOWER} Башня · игра идёт.\n"
        "·····················\n"
        f"{EMOJI_BOMB} Мин: {game['mines_count']}\n"
        f"{EMOJI_CASH} Ставка: {game['bet']:,} n¢\n"
        f"{EMOJI_TROPHY} Выигрыш: "
        f"x{game['current_multiplier']:.2f} / {cashout_win:,} n¢\n\n"
        f"{EMOJI_UP} <b>Следующий уровень:</b>\n"
        f"|<code>{next_m_str}</code>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=render_tower_keyboard(game),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "tower_cashout")
async def tower_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id

    if (
        user_id not in ACTIVE_TOWER_GAMES
        or ACTIVE_TOWER_GAMES[user_id]["status"] != "playing"
    ):
        await callback.answer("Игра завершена.")
        return

    game = ACTIVE_TOWER_GAMES[user_id]
    fair_id = game.get("fair_id")
    win_amount = round(
        game["bet"] * game["current_multiplier"],
        2,
    )

    db.update_balance(user_id, win_amount)
    db.add_stats(
        user_id,
        is_lost=False,
        bet_amount=game["bet"],
    )
    game["status"] = "won"

    if fair_id and fair_id in TOWER_FAIR_CACHE:
        TOWER_FAIR_CACHE[fair_id].update({
            "status": "won",
            "is_win": True,
            "win_amount": win_amount,
            "current_level": game["current_level"],
            "current_multiplier": game["current_multiplier"],
            "board": game["board"],
        })

    text = (
        f"{EMOJI_MONEY} <b>Башня · Награда забрана!</b>\n"
        f"{EMOJI_CHART} Множитель: x{game['current_multiplier']:.2f}\n"
        f"{EMOJI_TROPHY} Выиграно: <b>{win_amount:,} n¢</b>\n\n"
        f"{EMOJI_CARD} Твой баланс: "
        f"<b>{db.get_user(user_id)['balance']:,} nCoin</b>"
    )

    del ACTIVE_TOWER_GAMES[user_id]
    await callback.message.edit_text(
        text,
        reply_markup=render_tower_keyboard(game, fair_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "tower_noop")
async def tower_noop(callback: CallbackQuery):
    await callback.answer()


# ==============================================================================
# 🔄 ПОВТОРИТЬ И 🔑 ЧЕСТНОСТЬ
# ============================================================================== 

@router.callback_query(
    F.data.startswith("tower_repeat:"),
    StateFilter(None),
)
async def tower_repeat_callback(callback: CallbackQuery, state: FSMContext):
    """Повторяет игру в Башню с той же ставкой и количеством мин."""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Ошибка данных.", show_alert=True)

        fair_id = parts[1]
        previous_game = TOWER_FAIR_CACHE.get(fair_id)

        if not previous_game:
            return await callback.answer(
                "❌ Данные предыдущей игры устарели.",
                show_alert=True,
            )

        if int(previous_game["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        bet = float(previous_game["bet"])
        mines_count = int(previous_game["mines_count"])

        if bet > MAX_TOWER_BET:
            return await callback.answer(
                f"❌ Ставка превышает лимит {MAX_TOWER_BET:,} n¢ (25кк)!",
                show_alert=True,
            )

        user = db.get_user(callback.from_user.id)

        if user["balance"] < bet:
            return await callback.answer(
                f"❌ Недостаточно nCoin! Баланс: {user['balance']:,}",
                show_alert=True,
            )

        db.update_balance(callback.from_user.id, -bet)

        game_board = [
            {
                "cells": generate_tower_level(mines_count),
                "opened_cell": None,
            }
            for _ in range(10)
        ]

        new_fair_id = create_tower_fair_game(
            callback.from_user.id,
            bet,
            mines_count,
            game_board,
        )

        ACTIVE_TOWER_GAMES[callback.from_user.id] = {
            "bet": bet,
            "mines_count": mines_count,
            "board": game_board,
            "current_level": 0,
            "current_multiplier": 1.0,
            "status": "playing",
            "fair_id": new_fair_id,
        }

        game = ACTIVE_TOWER_GAMES[callback.from_user.id]
        next_m_str = ""

        for lvl in range(1, 6):
            m_val = calculate_tower_multiplier(mines_count, lvl)
            next_m_str += f" {lvl} • x{m_val:.2f} {EMOJI_ARROW}"

        next_m_str += " ..."

        text = (
            f"{EMOJI_TOWER} Башня · игра идёт.\n"
            "·····················\n"
            f"{EMOJI_BOMB} Мин: {mines_count}\n"
            f"{EMOJI_CASH} Ставка: {bet:,} n¢\n"
            f"{EMOJI_TROPHY} Выигрыш: x1.00 / {bet:,} n¢\n\n"
            f"{EMOJI_UP} <b>Следующий уровень:</b>\n"
            f"|<code>{next_m_str}</code>"
        )

        await state.clear()
        await callback.message.edit_text(
            text,
            reply_markup=render_tower_keyboard(game),
            parse_mode="HTML",
        )
        await callback.answer()

    except Exception:
        try:
            await callback.answer(
                "❌ Не удалось повторить игру.",
                show_alert=True,
            )
        except Exception:
            pass


@router.callback_query(
    F.data.startswith("tower_fair:"),
    StateFilter(None),
)
async def tower_fair_callback(callback: CallbackQuery):
    """Отображает данные честности SHA-256 раунда Башни."""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Ошибка данных.", show_alert=True)

        fair_id = parts[1]
        fair_data = TOWER_FAIR_CACHE.get(fair_id)

        if not fair_data:
            return await callback.answer(
                "❌ Данные этого раунда устарели или бот был перезапущен.",
                show_alert=True,
            )

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        await callback.answer()

        raw_str = html.escape(str(fair_data["raw_str"]))
        sha_hash = html.escape(str(fair_data["sha_hash"]))
        mines_count = fair_data["mines_count"]

        board_lines = []
        for lvl_idx, lvl in enumerate(fair_data["board"]):
            cells_view = "".join(
                [EMOJI_BOMB if is_mine else EMOJI_GEM for is_mine in lvl["cells"]]
            )
            board_lines.append(
                f"Уровень {lvl_idx + 1}: <code>{cells_view}</code>"
            )

        board_preview = "\n".join(board_lines)

        text = (
            f"{EMOJI_TOWER} <b>Башня · Честность</b> {EMOJI_KEY}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{EMOJI_HASH} <b>SHA-256 Хэш раунда:</b>\n"
            f"<code>{sha_hash}</code>\n\n"
            f"{EMOJI_KEY} <b>Результат (Raw):</b>\n"
            f"<code>{raw_str}</code>\n\n"
            f"{EMOJI_BOMB} <b>Расположение мин по уровням "
            f"({mines_count} на ряд):</b>\n"
            f"{board_preview}\n\n"
            "<blockquote>"
            "Все уровни башни и мины на них генерируются до начала игры. "
            "Скопируйте строку Результата и вставьте её на любом онлайн-сканере "
            "SHA-256. Сгенерированный хэш точно совпадёт с Хэшем раунда!"
            "</blockquote>"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=f"tower_fair_back:{fair_id}",
                ),
                InlineKeyboardButton(
                    text="Проверить SHA-256 🔑",
                    url="https://emn178.github.io/online-tools/",
                ),
            ]
        ])

        if callback.message:
            await callback.message.edit_text(
                text,
                reply_markup=kb,
                parse_mode="HTML",
            )

    except Exception:
        try:
            await callback.answer(
                "❌ Не удалось открыть данные честности.",
                show_alert=True,
            )
        except Exception:
            pass


@router.callback_query(
    F.data.startswith("tower_fair_back:"),
    StateFilter(None),
)
async def tower_fair_back_callback(callback: CallbackQuery):
    """Возвращает экран с итогами завершённой игры в Башню."""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Неверный запрос.", show_alert=True)

        fair_id = parts[1]
        fair_data = TOWER_FAIR_CACHE.get(fair_id)

        if not fair_data:
            return await callback.answer("❌ Данные игры устарели.", show_alert=True)

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваша игра.", show_alert=True)

        await callback.answer()

        status = fair_data.get("status")
        bet = fair_data["bet"]
        mines_count = fair_data["mines_count"]

        if status == "won":
            win_amount = fair_data["win_amount"]
            mult = fair_data["current_multiplier"]
            text = (
                f"{EMOJI_MONEY} <b>Башня · Награда забрана!</b>\n"
                f"{EMOJI_CHART} Множитель: x{mult:.2f}\n"
                f"{EMOJI_TROPHY} Выиграно: <b>{win_amount:,} n¢</b>\n\n"
                f"{EMOJI_CARD} Твой баланс: "
                f"<b>{db.get_user(callback.from_user.id)['balance']:,} nCoin</b>"
            )
        else:
            lvl = fair_data["current_level"]
            text = (
                f"{EMOJI_BOOM} <b>Башня · Проигрыш!</b>\n"
                "·····················\n"
                f"{EMOJI_BOMB} Мин: {mines_count}\n"
                f"{EMOJI_CASH} Ставка: {bet:,} n¢\n"
                f"{EMOJI_BRIEFCASE} Пройдено уровней: {lvl} из 10\n\n"
                f"{EMOJI_CARD} Твой баланс: "
                f"<b>{db.get_user(callback.from_user.id)['balance']:,} nCoin</b>"
            )

        dummy_game = {
            "status": status,
            "current_level": fair_data["current_level"],
            "board": fair_data["board"],
        }

        kb = render_tower_keyboard(dummy_game, fair_id)

        if callback.message:
            await callback.message.edit_text(
                text,
                reply_markup=kb,
                parse_mode="HTML",
            )

    except Exception:
        try:
            await callback.answer(
                "❌ Не удалось вернуться к результатам.",
                show_alert=True,
            )
        except Exception:
            pass
