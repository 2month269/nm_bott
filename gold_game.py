# gold_game.py
import hashlib
import html
import logging
import random
import secrets
from typing import Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db
import utils

router = Router()
logger = logging.getLogger(__name__)

# Множители для 12 ступеней
GOLD_MULTIPLIERS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]

# Данные честности раундов игры «Золото».
# Важно: это память процесса. После перезапуска старые fair_id исчезнут.
GOLD_FAIR_CACHE: dict[str, dict] = {}


class GoldState(StatesGroup):
    playing = State()


def format_gold_num(val: float) -> str:
    """Форматирует числа игры «Золото» с разделителем '.""" 
    val = float(val or 0)

    if val >= 1_000_000_000_000:
        return f"{val / 1_000_000_000_000:.2f}kkkk nCoin"
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f}kkk nCoin"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}kk nCoin"

    return f"{int(val):,}".replace(",", "'") + " nCoin"


def create_gold_fair_game(
    path: list[str],
    user_id: int,
    bet: float,
) -> str:
    """Создаёт отдельные данные честности для конкретного раунда."""
    salt = secrets.token_hex(16)
    path_string = ":".join(path)
    raw_string = f"{path_string}:{salt}"
    sha_hash = hashlib.sha256(raw_string.encode("utf-8")).hexdigest()
    fair_id = secrets.token_hex(8)

    GOLD_FAIR_CACHE[fair_id] = {
        "user_id": int(user_id),
        "bet": float(bet),
        "path": list(path),
        "salt": salt,
        "raw_string": raw_string,
        "hash": sha_hash,
    }

    # Чтобы кеш не рос бесконечно
    if len(GOLD_FAIR_CACHE) > 1000:
        oldest_key = next(iter(GOLD_FAIR_CACHE))
        GOLD_FAIR_CACHE.pop(oldest_key, None)

    return fair_id


def get_game_kb(has_take_button: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура активной игры."""
    buttons = [
        [
            InlineKeyboardButton(text="❓", callback_data="gold_step:left", style="primary"),
            InlineKeyboardButton(text="❓", callback_data="gold_step:right", style="primary"),
        ]
    ]

    if has_take_button:
        buttons.append([
            InlineKeyboardButton(
                text="Забрать выигрыш ✅",
                callback_data="gold_take",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_finished_game_kb(fair_id: str) -> InlineKeyboardMarkup:
    """Кнопки после завершения игры."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Повторить",
                    callback_data=f"gold_repeat:{fair_id}",
                ),
                InlineKeyboardButton(
                    text="🔑 Честность",
                    callback_data=f"gold_fair:{fair_id}",
                ),
            ]
        ]
    )


def render_active_ladder(
    bet: float,
    current_level: int,
    history: list[str],
) -> str:
    """Отрисовка лестницы во время активной игры."""
    lines = []

    for lvl_idx in range(11, -1, -1):
        mult = GOLD_MULTIPLIERS[lvl_idx]
        amount_str = format_gold_num(bet * mult)

        if lvl_idx < current_level and lvl_idx < len(history):
            user_choice = history[lvl_idx]
            if user_choice == "left":
                lines.append(f"| 💰 | ❓ | {amount_str} ({mult}x)")
            else:
                lines.append(f"| ❓ | 💰 | {amount_str} ({mult}x)")
        else:
            lines.append(f"| ❓ | ❓ | {amount_str} ({mult}x)")

    return "\n".join(lines)


def render_loss_ladder(
    bet: float,
    failed_level: int,
    history: list[str],
    path: list[str],
    choice_at_failure: str,
) -> str:
    """Отрисовка лестницы после проигрыша."""
    lines = []

    for lvl_idx in range(11, -1, -1):
        mult = GOLD_MULTIPLIERS[lvl_idx]
        amount_str = format_gold_num(bet * mult)
        gold_side = path[lvl_idx]

        if lvl_idx < failed_level and lvl_idx < len(history):
            user_choice = history[lvl_idx]
            if user_choice == "left":
                lines.append(f"|💰|🧨| {amount_str} ({mult}x)")
            else:
                lines.append(f"|🧨|💰| {amount_str} ({mult}x)")

        elif lvl_idx == failed_level:
            if choice_at_failure == "left":
                lines.append(f"|💥|⚜️| {amount_str} ({mult}x)")
            else:
                lines.append(f"|⚜️|💥| {amount_str} ({mult}x)")

        else:
            if gold_side == "left":
                lines.append(f"|⚜️|🧨| {amount_str} ({mult}x)")
            else:
                lines.append(f"|🧨|⚜️| {amount_str} ({mult}x)")

    return "\n".join(lines)


async def start_gold_round(
    message: Message,
    state: FSMContext,
    user_id: int,
    bet: float,
):
    """Запускает новый раунд игры «Золото»."""
    user = db.get_user(user_id)
    balance = float(user["balance"])

    if bet <= 0:
        await message.answer("❌ Ставка должна быть больше 0 nCoin!")
        return

    if balance < bet:
        await message.answer(
            f"❌ Недостаточно средств! Ваш баланс: "
            f"<b>{format_gold_num(balance)}</b>",
            parse_mode="HTML",
        )
        return

    db.update_balance(user_id, -bet)

    secret_path = [
        random.choice(["left", "right"])
        for _ in range(12)
    ]

    fair_id = create_gold_fair_game(
        path=secret_path,
        user_id=user_id,
        bet=bet,
    )

    await state.update_data(
        bet=bet,
        level=0,
        path=secret_path,
        history=[],
        fair_id=fair_id,
    )
    await state.set_state(GoldState.playing)

    ladder_text = render_active_ladder(bet, 0, [])

    text = (
        "🌼 <b>Золото · начни игру!</b>\n"
        "·····················\n"
        f"💸 Ставка: <b>{format_gold_num(bet)}</b>\n\n"
        f"{ladder_text}"
    )

    await message.answer(
        text,
        reply_markup=get_game_kb(False),
        parse_mode="HTML",
    )


# ============================================================================== 
# СТАРТ ИГРЫ
# ============================================================================== 

@router.message(
    StateFilter(None),
    F.text,
    F.text.lower().startswith(("золото", "/gold")),
)
async def start_gold_game_cmd(message: Message, state: FSMContext):
    await state.clear()

    user_id = message.from_user.id
    user = db.get_user(user_id)
    user_balance = float(user["balance"])

    parts = message.text.strip().split()

    if len(parts) < 2:
        await message.answer(
            "🌼 <b>Игра ЗОЛОТО</b> 🌼\n"
            "·····················\n\n"
            "Пройдите 12 ступеней и заберите куш до <b>4096x</b>!\n\n"
            "✍️ <b>Команды для старта:</b>\n"
            "• <code>золото &lt;ставка&gt;</code>\n"
            "• <code>золото пол</code>\n"
            "• <code>золото все</code>\n\n"
            f"💳 Ваш баланс: <b>{format_gold_num(user_balance)}</b>",
            parse_mode="HTML",
        )
        return

    bet_raw = parts[1].lower().strip()

    if bet_raw in ["пол", "половина", "half"]:
        bet = round(user_balance / 2, 2)
    elif bet_raw in ["все", "всё", "all", "allin"]:
        bet = round(user_balance, 2)
    else:
        try:
            bet = utils.parse_bet_input(bet_raw, user_balance)
        except Exception:
            try:
                bet = utils.parse_bet_input(bet_raw)
            except Exception:
                await message.answer(
                    "❌ Ошибка ввода ставки! Введите число, <code>пол</code> или <code>все</code>.",
                    parse_mode="HTML",
                )
                return

    await start_gold_round(
        message=message,
        state=state,
        user_id=user_id,
        bet=float(bet),
    )


# ============================================================================== 
# ВЫБОР СТУПЕНИ
# ============================================================================== 

@router.callback_query(
    GoldState.playing,
    F.data.startswith("gold_step:"),
)
async def process_gold_step(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if not data:
        await callback.answer("Сессия игры завершена.", show_alert=True)
        return

    user_id = callback.from_user.id
    choice = callback.data.split(":", 1)[1]

    bet = float(data["bet"])
    current_level = int(data["level"])
    path = data["path"]
    history = list(data["history"])
    fair_id = data.get("fair_id")

    if current_level >= 12:
        await callback.answer("Игра уже завершена.", show_alert=True)
        return

    correct_choice = path[current_level]

    if choice == correct_choice:
        history.append(choice)
        new_level = current_level + 1

        if new_level == 12:
            win_amount = round(bet * GOLD_MULTIPLIERS[11], 2)

            db.update_balance(user_id, win_amount)
            db.add_stats(
                user_id,
                is_lost=False,
                bet_amount=bet,
                game_name="gold",
                win_amount=win_amount,
            )
            await state.clear()

            ladder_text = render_active_ladder(bet, 12, history)
            text = (
                "🎉 <b>Золото · Максимальный выигрыш!</b>\n"
                "·····················\n"
                f"💸 Ставка: <b>{format_gold_num(bet)}</b>\n"
                f"💰 Выигрыш: <b>x4096 / {format_gold_num(win_amount)}</b>\n\n"
                f"{ladder_text}"
            )

            await callback.message.edit_text(
                text,
                reply_markup=get_finished_game_kb(fair_id),
                parse_mode="HTML",
            )
            await callback.answer("🎉 ПОБЕДА! Вы прошли все 12 ступеней!", show_alert=True)
            return

        await state.update_data(
            level=new_level,
            history=history,
        )

        curr_mult = GOLD_MULTIPLIERS[new_level - 1]
        curr_win = round(bet * curr_mult, 2)
        ladder_text = render_active_ladder(bet, new_level, history)

        text = (
            "⚜️ <b>Золото · игра идёт</b>\n"
            "·····················\n"
            f"💸 Ставка: <b>{format_gold_num(bet)}</b>\n"
            f"💰 Выигрыш: <b>x{curr_mult} / {format_gold_num(curr_win)}</b>\n\n"
            f"{ladder_text}"
        )

        await callback.message.edit_text(
            text,
            reply_markup=get_game_kb(True),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # ПРОИГРЫШ
    db.add_stats(
        user_id,
        is_lost=True,
        lost_amount=bet,
        bet_amount=bet,
        game_name="gold",
    )
    await state.clear()

    loss_ladder_text = render_loss_ladder(
        bet,
        current_level,
        history,
        path,
        choice,
    )

    text = (
        "💥 <b>Золото · проигрыш!</b>\n"
        "·····················\n"
        f"💸 Ставка: <b>{format_gold_num(bet)}</b>\n"
        f"⚜️ Пройдено: <b>{current_level} из 12</b>\n\n"
        f"{loss_ladder_text}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_finished_game_kb(fair_id),
        parse_mode="HTML",
    )
    await callback.answer(
        "💥 Взрыв! Вы наступили на динамит.",
        show_alert=True,
    )


# ============================================================================== 
# ЗАБРАТЬ ВЫИГРЫШ
# ============================================================================== 

@router.callback_query(
    GoldState.playing,
    F.data == "gold_take",
)
async def process_gold_take(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # Проверка на наличие игры
    if not data or int(data.get("level", 0)) == 0:
        await callback.answer(
            "❌ Активная игра не найдена.",
            show_alert=True,
        )
        return

    # Очищаем состояние СРАЗУ, чтобы предотвратить двойной клик
    await state.clear()

    user_id = callback.from_user.id
    bet = float(data["bet"])
    current_level = int(data["level"])
    history = list(data["history"])
    fair_id = data.get("fair_id")

    curr_mult = GOLD_MULTIPLIERS[current_level - 1]
    win_amount = round(bet * curr_mult, 2)

    db.update_balance(user_id, win_amount)
    db.add_stats(
        user_id,
        is_lost=False,
        bet_amount=bet,
        game_name="gold",
        win_amount=win_amount,
    )

    ladder_text = render_active_ladder(bet, current_level, history)
    text = (
        "🎉 <b>Золото · выигрыш!</b>\n"
        "·····················\n"
        f"💸 Ставка: <b>{format_gold_num(bet)}</b>\n"
        f"💰 Забрано: <b>x{curr_mult} / {format_gold_num(win_amount)}</b>\n\n"
        f"{ladder_text}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_finished_game_kb(fair_id),
        parse_mode="HTML",
    )
    await callback.answer(
        f"✅ Вы успешно забрали {format_gold_num(win_amount)}!"
    )


# ============================================================================== 
# ПОВТОРИТЬ ИГРУ
# ============================================================================== 

@router.callback_query(
    F.data.startswith("gold_repeat:"),
    StateFilter("*"),
)
async def gold_repeat_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()

        fair_id = callback.data.split(":", 1)[1]
        previous_game = GOLD_FAIR_CACHE.get(fair_id)

        if not previous_game:
            await callback.answer(
                "❌ Данные предыдущей игры устарели.",
                show_alert=True,
            )
            return

        if int(previous_game["user_id"]) != int(callback.from_user.id):
            await callback.answer(
                "❌ Это не ваша игра.",
                show_alert=True,
            )
            return

        bet = float(previous_game["bet"])
        await state.clear()

        # callback.message — обычное Message, его можно передать в запуск нового раунда
        await start_gold_round(
            message=callback.message,
            state=state,
            user_id=callback.from_user.id,
            bet=bet,
        )

    except Exception as error:
        logger.exception("Ошибка повтора игры «Золото»: %s", error)
        try:
            await callback.answer(
                "❌ Не удалось повторить игру.",
                show_alert=True,
            )
        except Exception:
            pass


# ============================================================================== 
# ЧЕСТНОСТЬ РАУНДА
# ============================================================================== 

@router.callback_query(
    F.data.startswith("gold_fair:"),
    StateFilter("*"),
)
async def gold_fair_callback(callback: CallbackQuery):
    try:
        await callback.answer()

        fair_id = callback.data.split(":", 1)[1]
        fair_data = GOLD_FAIR_CACHE.get(fair_id)

        if not fair_data:
            await callback.answer(
                "❌ Данные этой игры устарели или были удалены после перезапуска бота.",
                show_alert=True,
            )
            return

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            await callback.answer(
                "❌ Это не ваша игра.",
                show_alert=True,
            )
            return

        raw_string = html.escape(str(fair_data["raw_string"]))
        sha_hash = html.escape(str(fair_data["hash"]))
        path = fair_data["path"]

        path_text = " → ".join(
            "⬅️ Лево" if side == "left" else "➡️ Право"
            for side in path
        )

        text = (
            "🌼 <b>Золото · Честность</b> 🔑\n"
            "·····················\n\n"
            "<b>SHA-256 Хэш:</b>\n"
            f"<code>{sha_hash}</code>\n\n"
            "<b>Результат:</b>\n"
            f"<code>{raw_string}</code>\n\n"
            "<b>Скрытый путь раунда:</b>\n"
            f"{path_text}\n\n"
            "<blockquote>"
            "Скопируйте строку результата и проверьте её через SHA-256. "
            "Полученный хэш должен совпасть с указанным выше."
            "</blockquote>"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data=f"gold_fair_back:{fair_id}",
                    ),
                    InlineKeyboardButton(
                        text="Проверить SHA-256 🔑",
                        url="https://emn178.github.io/online-tools/",
                    ),
                ]
            ]
        )

        if callback.message:
            await callback.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

    except Exception as error:
        logger.exception(
            "Ошибка открытия честности игры «Золото»: %s",
            error,
        )
        try:
            await callback.answer(
                "❌ Не удалось открыть данные честности.",
                show_alert=True,
            )
        except Exception:
            pass


# ============================================================================== 
# ВОЗВРАТ К ЗАВЕРШЁННОЙ ИГРЕ
# ============================================================================== 

@router.callback_query(
    F.data.startswith("gold_fair_back:"),
    StateFilter("*"),
)
async def gold_fair_back_callback(callback: CallbackQuery):
    try:
        await callback.answer()

        fair_id = callback.data.split(":", 1)[1]
        fair_data = GOLD_FAIR_CACHE.get(fair_id)

        if not fair_data:
            await callback.answer(
                "❌ Данные игры устарели.",
                show_alert=True,
            )
            return

        if int(fair_data["user_id"]) != int(callback.from_user.id):
            await callback.answer(
                "❌ Это не ваша игра.",
                show_alert=True,
            )
            return

        bet = float(fair_data["bet"])

        text = (
            "🌼 <b>Золото · раунд завершён</b>\n"
            "·····················\n\n"
            f"💸 Ставка: <b>{format_gold_num(bet)}</b>\n\n"
            "Нажмите «Честность», чтобы посмотреть данные SHA-256 раунда."
        )

        await callback.message.edit_text(
            text,
            reply_markup=get_finished_game_kb(fair_id),
            parse_mode="HTML",
        )

    except Exception as error:
        logger.exception(
            "Ошибка возврата к результату игры «Золото»: %s",
            error,
        )
        try:
            await callback.answer(
                "❌ Не удалось вернуться к результату.",
                show_alert=True,
            )
        except Exception:
            pass
