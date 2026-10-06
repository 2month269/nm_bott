import asyncio
import html
import logging
import time

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

import db
import utils

logger = logging.getLogger(__name__)
router = Router()

FOOTBALL_COOLDOWN_CACHE: dict[int, float] = {}
FOOTBALL_COOLDOWN_SECONDS = 2.0

GOAL_VALUES = {3, 4, 5}

GOAL_MULTIPLIER = 1.60
MISS_MULTIPLIER = 1.60

MAX_BET = 150_000_000.0

EMOJI_INFO_ID = "5467403607286502523"
EMOJI_GRAPH_ID = "5231200819986047254"
EMOJI_ROBOT_ID = "5350612670435313545"
EMOJI_BALL_ID = "5429463966432643712"
EMOJI_MONEY_ID = "5463046637842608206"
EMOJI_DICE_ID = "5465198403573012261"
EMOJI_GOAL_ID = "5461151367559141950"
EMOJI_MISS_ID = "5373239082136650704"
EMOJI_CHECK_ID = "5805523262691611326"
EMOJI_CARD_ID = "5472250091332993630"
EMOJI_CROSS_ID = "5454350746407419714"
EMOJI_LIGHTNING_ID = "5989800724312101453"
EMOJI_WIN_MONEY_ID = "5375312095346704820"


def make_emoji(emoji_id: str, fallback: str) -> str:
    """Безопасное создание HTML-тега премиум-эмодзи."""
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


EMOJI_INFO = make_emoji(EMOJI_INFO_ID, "ℹ️")
EMOJI_GRAPH = make_emoji(EMOJI_GRAPH_ID, "📊")
EMOJI_ROBOT = make_emoji(EMOJI_ROBOT_ID, "🤖")
EMOJI_BALL = make_emoji(EMOJI_BALL_ID, "⚽")
EMOJI_MONEY = make_emoji(EMOJI_MONEY_ID, "💸")
EMOJI_DICE = make_emoji(EMOJI_DICE_ID, "🎲")
EMOJI_GOAL = make_emoji(EMOJI_GOAL_ID, "🔥")
EMOJI_MISS = make_emoji(EMOJI_MISS_ID, "💥")
EMOJI_CHECK = make_emoji(EMOJI_CHECK_ID, "✅")
EMOJI_CARD = make_emoji(EMOJI_CARD_ID, "💳")
EMOJI_CROSS = make_emoji(EMOJI_CROSS_ID, "❌")
EMOJI_LIGHTNING = make_emoji(EMOJI_LIGHTNING_ID, "⚡")
EMOJI_WIN_MONEY = make_emoji(EMOJI_WIN_MONEY_ID, "💰")


def fmt_ncoin(value: float) -> str:
    """Форматирование чисел с апострофом ' (100 -> 100, 10000 -> 10'000)"""
    value = float(value or 0)
    if value < 1:
        return "0"
    if abs(value - round(value)) < 1e-9:
        return f"{int(value):,}".replace(",", "'")
    return f"{value:,.2f}".replace(",", "'")


def parse_football_bet(value: str, balance: float) -> float:
    """Парсинг суммы ставки, пол/половина, все/вабанк"""
    value = value.lower().strip()
    if value in {"все", "всё", "all", "allin", "all-in", "вабанк", "ва-банк"}:
        return round(float(balance), 2)
    if value in {"пол", "половина", "half"}:
        return round(float(balance) / 2, 2)
    try:
        return float(utils.parse_bet_input(value, balance))
    except Exception:
        try:
            return float(utils.parse_bet_input(value))
        except Exception:
            return -1.0


def normalize_football_target(value: str | None) -> str:
    """Нормализация выбора игрока (гол / мимо)"""
    if not value:
        return "гол"
    value = value.lower().strip()
    if value in {"гол", "г", "goal", "забьет", "забьёт", "попадание"}:
        return "гол"
    if value in {"мимо", "м", "miss", "промах", "не гол"}:
        return "мимо"
    return ""


def parse_football_command(message_text: str, balance: float):
    """Разбор команды ставки и выбора в любом порядке"""
    parts = message_text.lower().strip().split()
    if len(parts) < 2:
        return None, None

    arguments = parts[1:]
    bet = None
    target = None

    for argument in arguments:
        parsed_target = normalize_football_target(argument)
        if parsed_target:
            target = parsed_target
            continue

        if bet is None:
            parsed_bet = parse_football_bet(argument, balance)
            if parsed_bet > 0:
                bet = parsed_bet

    if target is None:
        target = "гол"

    return bet, target


def render_football_result_text(bet: float, target: str, actual_result: str, win: bool, win_amount: float) -> str:
    """Формирует итоговый текст результата игры без нижних кнопок"""
    multiplier = GOAL_MULTIPLIER if target == "гол" else MISS_MULTIPLIER
    mult_str = f"{multiplier:.1f}".replace(".", ",")
    line = "· " * 35

    if win:
        return (
            f"{EMOJI_GOAL} <b>Футбол · Победа!</b> {EMOJI_CHECK}\n"
            f"{line}\n"
            f"{EMOJI_MONEY} Ставка: <b>{fmt_ncoin(bet)} n¢</b>\n"
            f"{EMOJI_DICE} Выбрано: <b>{html.escape(target)}</b>\n"
            f"{EMOJI_WIN_MONEY} Выигрыш: <b>x{mult_str} / {fmt_ncoin(win_amount)} n¢</b>\n\n"
            f"<blockquote>{EMOJI_LIGHTNING} Итог: <b>{html.escape(actual_result)}</b></blockquote>"
        )
    else:
        return (
            f"{EMOJI_MISS} <b>Футбол · Проигрыш!</b>\n"
            f"{line}\n"
            f"{EMOJI_MONEY} Ставка: <b>{fmt_ncoin(bet)} n¢</b>\n"
            f"{EMOJI_DICE} Выбрано: <b>{html.escape(target)}</b>\n\n"
            f"<blockquote>{EMOJI_LIGHTNING} Итог: <b>{html.escape(actual_result)}</b></blockquote>"
        )


async def send_football_help(message: Message):
    """Меню справки"""
    text = (
        f"<blockquote>"
        f"{EMOJI_INFO} <i>Футбол — это игра, в которой нужно предсказать, "
        f"попадёт ли мяч в ворота или пролетит мимо, чтобы получить выигрыш.</i>\n"
        f"{EMOJI_GRAPH} <b>Лимиты:</b>\n"
        "RTP: ~96%\n"
        f"Макс. множитель: x{GOAL_MULTIPLIER:.1f}\n"
        f"Макс. ставка: {fmt_ncoin(MAX_BET)} n¢\n"
        f"Макс. выигрыш: {fmt_ncoin(MAX_BET * GOAL_MULTIPLIER)} n¢"
        f"</blockquote>\n\n"
        f"{EMOJI_ROBOT} Чтобы начать игру, используй команду:\n\n"
        f"{EMOJI_BALL} <b>/football [ставка] [гол/мимо]</b>\n\n"
        "Пример: <code>/football 100</code>\n"
        "Пример: <code>футбол 100 гол</code>\n"
        "Пример: <code>футбол пол мимо</code>\n"
        "Пример: <code>футбол все гол</code>"
    )

    await message.answer(text, parse_mode="HTML")


@router.message(Command("football"))
@router.message(F.text.lower().startswith(("футбол", "фут", "/football")))
async def football_command(message: Message):
    """Основной обработчик текстовых команд"""
    parts = message.text.strip().split()

    if len(parts) == 1:
        await send_football_help(message)
        return

    user_id = message.from_user.id

    # Проверка кулдауна (2 секунды)
    now = time.time()
    last_time = FOOTBALL_COOLDOWN_CACHE.get(user_id, 0.0)
    time_passed = now - last_time
    if time_passed < FOOTBALL_COOLDOWN_SECONDS:
        remains = round(FOOTBALL_COOLDOWN_SECONDS - time_passed, 1)
        await message.reply(
            f"⏳ <b>Подождите {remains} сек. перед следующей ставкой!</b>",
            parse_mode="HTML"
        )
        return

    user = db.get_user(user_id)
    balance = float(user.get("balance", 0))

    bet, target = parse_football_command(message.text, balance)

    if bet is None or bet <= 0:
        await message.answer(
            f"{EMOJI_CROSS} <b>Неверный формат ставки!</b>\n\n"
            "Используй:\n"
            "<code>футбол 100 гол</code>\n"
            "<code>футбол 100 мимо</code>\n"
            "<code>футбол пол гол</code>\n"
            "<code>футбол все мимо</code>",
            parse_mode="HTML"
        )
        return

    if bet > MAX_BET:
        await message.answer(
            f"{EMOJI_CROSS} <b>Максимальная ставка — {fmt_ncoin(MAX_BET)} nCoin!</b>",
            parse_mode="HTML"
        )
        return

    if target not in {"гол", "мимо"}:
        await message.answer(
            f"{EMOJI_CROSS} Укажи результат: <code>гол</code> или <code>мимо</code>.",
            parse_mode="HTML"
        )
        return

    if balance < bet:
        await message.answer(
            f"{EMOJI_CROSS} <b>Недостаточно nCoin для ставки!</b>\n"
            f"{EMOJI_CARD} Баланс: <b>{fmt_ncoin(balance)} nCoin</b>",
            parse_mode="HTML"
        )
        return

    FOOTBALL_COOLDOWN_CACHE[user_id] = time.time()
    await start_football_logic(message, bet, target, user_id)


async def start_football_logic(message: Message, bet: float, target: str, user_id: int):
    """Запуск раунда: списание баланса, анимированный кубик и отправка итогов без инлайн-кнопок"""
    try:
        db.update_balance(user_id, -bet)

        dice_msg = await message.answer_dice(emoji="⚽")
        dice_value = int(dice_msg.dice.value)

        await asyncio.sleep(3.5)

        actual_result = "гол" if dice_value in GOAL_VALUES else "мимо"
        win = (actual_result == target)
        win_amount = 0.0

        if win:
            multiplier = GOAL_MULTIPLIER if target == "гол" else MISS_MULTIPLIER
            win_amount = round(bet * multiplier, 2)
            db.update_balance(user_id, win_amount)
            db.add_stats(user_id, is_lost=False, bet_amount=bet)
        else:
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)

        text = render_football_result_text(bet, target, actual_result, win, win_amount)

        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка в start_football_logic: %s", e)
        try:
            await message.answer(f"❌ Произошла ошибка в игре: {e}")
        except Exception:
            pass
