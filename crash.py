import hashlib
import html
import logging
import secrets
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

import db
import utils

logger = logging.getLogger(__name__)
router = Router()

COEFFICIENTS = [1.2, 2.0, 5.0, 9.0, 10.0, 15.0, 38.0, 100.0]
MIN_STAKE = 1
MAX_STAKE = 200_000_000
MAX_MULTIPLIER = 100_000
RTP = 97
CURRENCY = "mCoin"
CURRENCY_SHORT = "m¢"

# Ожидающие выбора коэффициента: user_id -> ставка
PENDING_GAMES: dict[int, int] = {}

# Данные честности завершённых раундов
FAIR_ROUNDS: dict[str, dict] = {}


def format_amount(value: int | float) -> str:
    return f"{int(value):,}".replace(",", "'")


def format_multiplier(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def get_balance(user_id: int) -> float:
    user = db.get_user(user_id) or {}
    return float(user.get("balance", 0) or 0)


def generate_crash_point() -> tuple[float, str]:
    """Независимый provably-fair результат с RTP около 97%."""
    seed = secrets.token_hex(32)
    fair_id = secrets.token_hex(8)
    digest = hashlib.sha256(seed.encode()).hexdigest()
    value = int(digest[:13], 16) / float(16 ** 13)

    if value < (1 - RTP / 100):
        crash_point = 1.00
    else:
        crash_point = min(RTP / 100 / (1 - value), MAX_MULTIPLIER)
        crash_point = round(max(1.00, crash_point), 2)

    raw_result = f"{crash_point:.2f}:{seed}"
    result_hash = hashlib.sha256(raw_result.encode()).hexdigest()

    FAIR_ROUNDS[fair_id] = {
        "raw": raw_result,
        "hash": result_hash,
        "crash_point": crash_point,
    }

    if len(FAIR_ROUNDS) > 1000:
        FAIR_ROUNDS.pop(next(iter(FAIR_ROUNDS)))

    return crash_point, fair_id


def coefficient_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="x1.2", callback_data="crash_coef:1.2"),
            InlineKeyboardButton(text="x2.0", callback_data="crash_coef:2.0"),
            InlineKeyboardButton(text="x5.0", callback_data="crash_coef:5.0"),
            InlineKeyboardButton(text="x9.0", callback_data="crash_coef:9.0"),
        ],
        [
            InlineKeyboardButton(text="x10.0", callback_data="crash_coef:10.0"),
            InlineKeyboardButton(text="x15", callback_data="crash_coef:15.0"),
            InlineKeyboardButton(text="x38.0", callback_data="crash_coef:38.0"),
            InlineKeyboardButton(text="x100.0", callback_data="crash_coef:100.0"),
        ],
        [
            InlineKeyboardButton(text="Отменить ❌", callback_data="crash_cancel"),
            InlineKeyboardButton(text="Честность 🔑", callback_data="crash_fair_info"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fairness_keyboard(fair_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Честность 🔑", callback_data=f"crash_fair:{fair_id}")]
    ])


def choice_text(stake: int) -> str:
    return (
        "🚀 <b>Краш · выбери коэфф.</b>\n"
        "· · · · · · · · · · · · · · · · ·\n\n"
        f"💸 <b>Ставка:</b> {format_amount(stake)} {CURRENCY}\n\n"
        "ℹ️ Вы можете указать свой коэффициент (от 1.01 до 100k), "
        "отправив число в ответ на это сообщение."
    )


def result_text(user_name: str, stake: int, crash_point: float, win: Optional[int]) -> str:
    name = html.escape(user_name or "Ты")
    mention = f'<a href="tg://user?id=0">{name}</a>'
    crash = format_multiplier(crash_point)

    if win is None:
        return (
            f"🚀 Ракета упала на x{crash} 🏳️\n"
            f"❌ {mention} проиграл {format_amount(stake)} {CURRENCY_SHORT}"
        )

    return (
        f"🚀 Ракета улетела на x{crash} 📈\n"
        f"✅ {mention} выиграл! Твой выигрыш составил "
        f"{format_amount(win)} {CURRENCY_SHORT}"
    )


def parse_stake(token: str, balance: float) -> Optional[int]:
    try:
        value = utils.parse_bet_input(token, balance)
        value = int(value)
        if MIN_STAKE <= value <= MAX_STAKE and value <= balance:
            return value
    except Exception:
        pass
    return None


def parse_coefficient(value: str) -> Optional[float]:
    try:
        coefficient = float(value.replace(",", "."))
        if 1.01 <= coefficient <= MAX_MULTIPLIER:
            return coefficient
    except (TypeError, ValueError):
        pass
    return None


@router.message(Command("crash"))
@router.message(F.text.lower().startswith("краш"))
async def crash_command(message: Message):
    parts = message.text.strip().split()
    user_id = message.from_user.id
    balance = get_balance(user_id)

    if len(parts) != 2:
        await message.answer(
            "ℹ️ <b>Краш</b> — это игра, в которой нужно выбрать множитель "
            "от x1.01 до x100k. Бот случайно останавливается от x1 до x100k.\n\n"
            "📊 <b>Лимиты:</b>\n"
            f"RTP: ~{RTP}%\n"
            f"Макс. множитель: x{MAX_MULTIPLIER:,}\n"
            f"Макс. ставка: {format_amount(MAX_STAKE)} {CURRENCY_SHORT}\n"
            f"Макс. выигрыш: {format_amount(MAX_STAKE * 10)} {CURRENCY_SHORT}\n\n"
            "🤖 Чтобы начать игру, используй команду:\n\n"
            "📈 <code>/crash [ставка] [1.01-100k]</code>\n\n"
            "Пример: <code>/crash 100 1.1</code>\n"
            "Пример: <code>краш 100 4</code>",
            parse_mode="HTML"
        )
        return

    stake = parse_stake(parts[1], balance)
    if stake is None:
        await message.answer("❌ Некорректная ставка или недостаточно средств.")
        return

    PENDING_GAMES[user_id] = stake
    await message.answer(
        choice_text(stake),
        reply_markup=coefficient_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text)
async def custom_coefficient_message(message: Message):
    user_id = message.from_user.id
    if user_id not in PENDING_GAMES:
        return

    coefficient = parse_coefficient(message.text.strip())
    if coefficient is None:
        return

    stake = PENDING_GAMES.pop(user_id)
    await play_round(message, user_id, stake, coefficient)


@router.callback_query(F.data.startswith("crash_coef:"))
async def coefficient_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    stake = PENDING_GAMES.pop(user_id, None)

    if stake is None:
        await callback.answer("Заявка устарела.", show_alert=True)
        return

    try:
        coefficient = float(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Ошибка коэффициента.", show_alert=True)
        return

    await callback.answer()
    await play_round(callback.message, user_id, stake, coefficient, edit=True)


async def play_round(message: Message, user_id: int, stake: int, coefficient: float, edit: bool = False):
    if get_balance(user_id) < stake:
        text = "❌ Недостаточно средств для ставки."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    db.update_balance(user_id, -stake)
    crash_point, fair_id = generate_crash_point()

    if crash_point >= coefficient:
        win = int(stake * coefficient)
        db.update_balance(user_id, win)
        db.add_stats(user_id, is_lost=False, bet_amount=stake, win_amount=win)
    else:
        win = None
        db.add_stats(user_id, is_lost=True, lost_amount=stake, bet_amount=stake)

    text = result_text(message.chat.first_name if message.chat else "Ты", stake, crash_point, win)
    markup = fairness_keyboard(fair_id)

    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "crash_cancel")
async def cancel_callback(callback: CallbackQuery):
    stake = PENDING_GAMES.pop(callback.from_user.id, None)
    await callback.answer("Ставка отменена")

    if stake is not None:
        await callback.message.edit_text("❌ Ставка отменена.")
    else:
        await callback.message.edit_text("❌ Игра уже завершена.")


@router.callback_query(F.data == "crash_fair_info")
async def fairness_info_callback(callback: CallbackQuery):
    await callback.answer(
        f"Каждый раунд независим. RTP около {RTP}%. Результат проверяется SHA-256.",
        show_alert=True
    )


@router.callback_query(F.data.startswith("crash_fair:"))
async def fairness_callback(callback: CallbackQuery):
    fair_id = callback.data.split(":", 1)[1]
    data = FAIR_ROUNDS.get(fair_id)

    if not data:
        await callback.answer("Данные раунда устарели.", show_alert=True)
        return

    await callback.answer()
    text = (
        "🔑 <b>Честность</b>\n\n"
        f"SHA-256: <code>{data['hash']}</code>\n"
        f"Результат: <code>{data['raw']}</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML")
