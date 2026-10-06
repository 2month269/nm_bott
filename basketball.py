import asyncio
import html
import logging
import time

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db
import utils

logger = logging.getLogger(__name__)
router = Router()

BASKETBALL_COOLDOWN_CACHE: dict[int, float] = {}
BASKETBALL_COOLDOWN_SECONDS = 2.0

# В кубике Telegram 🏀:
# Значения 4 и 5 — это попадание в кольцо (Hit / Score)
# Значения 1, 2 и 3 — это промах (Miss)
HIT_VALUES = {4, 5}

HIT_MULTIPLIER = 2.40
MISS_MULTIPLIER = 1.60

MAX_BET = 300_000_000.0

# ID эмодзи для tg-emoji (премиум-эмодзи)
EMOJI_INFO_ID = "5467403607286502523"
EMOJI_GRAPH_ID = "5231200819986047254"
EMOJI_ROBOT_ID = "5350612670435313545"
EMOJI_BASKET_ID = "5429463966432643712"
EMOJI_MONEY_ID = "5463046637842608206"
EMOJI_DICE_ID = "5465198403573012261"
EMOJI_WIN_ID = "5461151367559141950"
EMOJI_LOSS_ID = "5373239082136650704"
EMOJI_CHECK_ID = "5805523262691611326"
EMOJI_CARD_ID = "5472250091332993630"
EMOJI_CROSS_ID = "5454350746407419714"
EMOJI_LIGHTNING_ID = "5989800724312101453"
EMOJI_WIN_MONEY_ID = "5375312095346704820"


def make_emoji(emoji_id: str, fallback: str) -> str:
    """Безопасное создание HTML-тега премиум-эмодзи."""
    # ИСПРАВЛЕНО: &lt; и &gt; заменены на < и >, чтобы кастомные эмодзи отображались нативно
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


EMOJI_INFO = make_emoji(EMOJI_INFO_ID, "ℹ️")
EMOJI_GRAPH = make_emoji(EMOJI_GRAPH_ID, "📊")
EMOJI_ROBOT = make_emoji(EMOJI_ROBOT_ID, "🤖")
EMOJI_BASKET = make_emoji(EMOJI_BASKET_ID, "🏀")
EMOJI_MONEY = make_emoji(EMOJI_MONEY_ID, "💸")
EMOJI_DICE = make_emoji(EMOJI_DICE_ID, "🎲")
EMOJI_WIN = make_emoji(EMOJI_WIN_ID, "🥳")
EMOJI_LOSS = make_emoji(EMOJI_LOSS_ID, "😢")
EMOJI_CHECK = make_emoji(EMOJI_CHECK_ID, "✅")
EMOJI_CARD = make_emoji(EMOJI_CARD_ID, "💳")
EMOJI_CROSS = make_emoji(EMOJI_CROSS_ID, "❌")
EMOJI_LIGHTNING = make_emoji(EMOJI_LIGHTNING_ID, "⚡")
EMOJI_WIN_MONEY = make_emoji(EMOJI_WIN_MONEY_ID, "💰")


def fmt_m(value: float) -> str:
    """Форматирование чисел с апострофом ' (100 -> 100, 10000 -> 10'000)"""
    value = float(value or 0)
    if value < 1:
        return "0"
    if abs(value - round(value)) < 1e-9:
        return f"{int(value):,}".replace(",", "'")
    return f"{value:,.2f}".replace(",", "'")


def parse_basket_bet(value: str, balance: float) -> float:
    """Парсинг суммы ставки"""
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


def normalize_basket_target(value: str | None) -> str:
    """Нормализация выбора игрока (попадание / мимо)"""
    if not value:
        return ""
    value = value.lower().strip()
    if value in {"попадание", "попал", "попадет", "попадёт", "гол", "забьет", "забьёт", "hit"}:
        return "попадание"
    if value in {"мимо", "м", "miss", "промах", "не попадет", "не попадёт"}:
        return "мимо"
    return ""


def parse_basket_command(message_text: str, balance: float):
    """Разбор команды ставки и выбора исхода"""
    parts = message_text.lower().strip().split()
    if len(parts) < 2:
        return None, None

    arguments = parts[1:]
    bet = None
    target = None

    for argument in arguments:
        parsed_target = normalize_basket_target(argument)
        if parsed_target:
            target = parsed_target
            continue

        if bet is None:
            parsed_bet = parse_basket_bet(argument, balance)
            if parsed_bet > 0:
                bet = parsed_bet

    return bet, target


def render_basket_result_text(bet: float, target: str, actual_result: str, win: bool, win_amount: float) -> str:
    """Формирует точный итоговый текст карточки результата"""
    multiplier = HIT_MULTIPLIER if target == "попадание" else MISS_MULTIPLIER
    mult_str = f"{multiplier:.1f}".replace(".", ",")
    line = "· " * 21

    if win:
        return (
            f"{EMOJI_WIN} <b>Баскетбол · Победа!</b> {EMOJI_CHECK}\n"
            f"{line}\n"
            f"{EMOJI_MONEY} Ставка: {fmt_m(bet)} m¢\n"
            f"{EMOJI_DICE} Выбрано: {html.escape(target)}\n"
            f"{EMOJI_WIN_MONEY} Выигрыш: x{mult_str} / {fmt_m(win_amount)} m¢\n"
            f"{line}\n"
            f"<blockquote>{EMOJI_LIGHTNING} Итог: {html.escape(actual_result)}</blockquote>"
        )
    else:
        return (
            f"{EMOJI_LOSS} <b>Баскетбол · Проигрыш!</b>\n"
            f"{line}\n"
            f"{EMOJI_MONEY} Ставка: {fmt_m(bet)} m¢\n"
            f"{EMOJI_DICE} Выбрано: {html.escape(target)}\n"
            f"{line}\n"
            f"<blockquote>{EMOJI_LIGHTNING} Итог: {html.escape(actual_result)}</blockquote>"
        )


def get_choice_keyboard(bet: float) -> InlineKeyboardMarkup:
    """Клавиатура выбора исхода, если исход не был указан в сообщении"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏀 Попадание - x{HIT_MULTIPLIER:.1f}", callback_data=f"basket_choice:{bet}:попадание")],
        [InlineKeyboardButton(text=f"🙈 Мимо - x{MISS_MULTIPLIER:.1f}", callback_data=f"basket_choice:{bet}:мимо")],
        [InlineKeyboardButton(text="Отменить ❌", callback_data="basket_cancel")]
    ])


async def send_basket_help(message: Message):
    """Справка по игре Баскетбол"""
    user_name = html.escape(message.from_user.first_name)
    text = (
        f"<blockquote>{EMOJI_INFO} <i>Баскетбол — это игра, где нужно попасть в кольцо, чтобы получить максимальный множитель.</i>\n"
        f"{EMOJI_GRAPH} <b>Лимиты:</b>\n"
        f"RTP: ~96%\n"
        f"Макс. множитель: x{HIT_MULTIPLIER:.1f}\n"
        f"Макс. ставка: 300kk m¢\n"
        f"Макс. выигрыш: 720kk m¢</blockquote>\n\n"
        f"{EMOJI_ROBOT} <b>{user_name}</b>, чтобы начать игру, используй команду:\n\n"
        f"{EMOJI_BASKET} <b>/basketball [ставка]</b>\n\n"
        f"Пример: <code>/basketball 100</code>\n"
        f"Пример: <code>баскетбол 100</code>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("basketball"))
@router.message(F.text.lower().startswith(("баскетбол", "баск", "/basketball", "/basket")))
async def basket_command(message: Message, state: FSMContext):
    """Основной обработчик текстовых команд"""
    await state.clear()
    parts = message.text.strip().split()

    if len(parts) == 1:
        await send_basket_help(message)
        return

    user_id = message.from_user.id

    # Проверка кулдауна
    now = time.time()
    last_time = BASKETBALL_COOLDOWN_CACHE.get(user_id, 0.0)
    time_passed = now - last_time
    if time_passed < BASKETBALL_COOLDOWN_SECONDS:
        remains = round(BASKETBALL_COOLDOWN_SECONDS - time_passed, 1)
        await message.reply(
            f"⏳ <b>Подождите {remains} сек. перед следующей ставкой!</b>",
            parse_mode="HTML"
        )
        return

    user = db.get_user(user_id)
    balance = float(user.get("balance", 0))

    bet, target = parse_basket_command(message.text, balance)

    if bet is None or bet <= 0:
        await message.answer(
            f"{EMOJI_CROSS} <b>Неверный формат ставки!</b>",
            parse_mode="HTML"
        )
        return

    if bet > MAX_BET:
        await message.answer(
            f"{EMOJI_CROSS} <b>Максимальная ставка — {fmt_m(MAX_BET)} m¢!</b>",
            parse_mode="HTML"
        )
        return

    if balance < bet:
        await message.answer(
            f"{EMOJI_CROSS} <b>Недостаточно m¢ для ставки!</b>\n"
            f"{EMOJI_CARD} Баланс: <b>{fmt_m(balance)} m¢</b>",
            parse_mode="HTML"
        )
        return

    # Если исход указан прямо в команде (например: `баскетбол 100 мимо` или `баскетбол 100 попал`)
    if target in {"попадание", "мимо"}:
        BASKETBALL_COOLDOWN_CACHE[user_id] = time.time()
        await start_basket_game(message, bet, target, user_id)
    else:
        # Исход не указан — выводим клавиатуру выбора
        text = (
            f"{EMOJI_BASKET} <b>Баскетбол · выбери исход!</b>\n"
            f"{EMOJI_MONEY} Ставка: <b>{fmt_m(bet)} m¢</b>"
        )
        await message.answer(text, reply_markup=get_choice_keyboard(bet), parse_mode="HTML")


@router.callback_query(F.data.startswith("basket_choice:"))
async def basket_choice_callback(callback: CallbackQuery):
    """Обработчик выбора исхода по кнопкам"""
    try:
        parts = callback.data.split(":")
        bet = float(parts[1])
        target = parts[2]
        user_id = callback.from_user.id

        now = time.time()
        last_time = BASKETBALL_COOLDOWN_CACHE.get(user_id, 0.0)
        time_passed = now - last_time
        if time_passed < BASKETBALL_COOLDOWN_SECONDS:
            remains = round(BASKETBALL_COOLDOWN_SECONDS - time_passed, 1)
            return await callback.answer(f"⏳ Подождите {remains} сек.!", show_alert=True)

        user = db.get_user(user_id)
        balance = float(user.get("balance", 0))

        if balance < bet:
            return await callback.answer("❌ Недостаточно средств!", show_alert=True)

        BASKETBALL_COOLDOWN_CACHE[user_id] = time.time()

        # Удаляем сообщение с выбором исхода
        try:
            await callback.message.delete()
        except Exception:
            pass

        await start_basket_game(callback.message, bet, target, user_id)

    except Exception as e:
        logger.exception("Ошибка при выборе исхода баскетбола: %s", e)


@router.callback_query(F.data == "basket_cancel")
async def basket_cancel_callback(callback: CallbackQuery):
    """Отмена выбора"""
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Отменено")


# ==============================================================================
# 🎯 ИСПРАВЛЕНИЕ: ДОБАВЛЕН ОБРАБОТЧИК ДЛЯ ОТКРЫТИЯ ИГРЫ ИЗ ЛОББИ (MAIN.PY)
# ==============================================================================
@router.callback_query(F.data == "basketball_menu")
async def basketball_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Вызывается, когда игрок кликает на '🏀 Баскетбол 🏀' на 4-й странице лобби"""
    await callback.answer()
    await state.clear()
    
    user = db.get_user(callback.from_user.id)
    balance = float(user.get("balance", 0))
    user_name = html.escape(callback.from_user.first_name)

    text = (
        f"{EMOJI_BASKET} <b>Игра БАСКЕТБОЛ (Basketball)</b> {EMOJI_BASKET}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Баскетбол — это игра, где нужно угадать, попадет ли мяч в кольцо 🏀.\n\n"
        f"{EMOJI_GRAPH} <b>Параметры игры:</b>\n"
        f"• RTP: ~96%\n"
        f"• Выигрыш за Попадание: <b>x{HIT_MULTIPLIER:.2f}</b>\n"
        f"• Выигрыш за Промах (Мимо): <b>x{MISS_MULTIPLIER:.2f}</b>\n"
        f"• Максимальная ставка: 300kk m¢\n\n"
        f"✍ <b>Как играть:</b>\n"
        f"Напишите в чат: <code>баскетбол ставка</code> (например, <code>баскетбол 10к</code>) "
        f"и выберите исход кнопкой, либо укажите его сразу: <code>баскетбол 10к попал</code>.\n\n"
        f"{EMOJI_CARD} Ваш баланс: <b>{fmt_m(balance)} m¢</b>"
    )

    # Кнопка возврата обратно на 4-ю страницу лобби игр
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к играм", callback_data="games_page_4")]
    ])

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


async def start_basket_game(message: Message, bet: float, target: str, user_id: int):
    """Запуск раунда: списание баланса, анимированный кубик и отправка итогов"""
    try:
        db.update_balance(user_id, -bet)

        # Отправляем анимацию баскетбольного кубика
        dice_msg = await message.answer_dice(emoji="🏀")
        dice_value = int(dice_msg.dice.value)

        await asyncio.sleep(3.5)

        actual_result = "попадание" if dice_value in HIT_VALUES else "мимо"
        win = (actual_result == target)
        win_amount = 0.0

        if win:
            multiplier = HIT_MULTIPLIER if target == "попадание" else MISS_MULTIPLIER
            win_amount = round(bet * multiplier, 2)
            db.update_balance(user_id, win_amount)
            db.add_stats(user_id, is_lost=False, bet_amount=bet)
        else:
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)

        text = render_basket_result_text(bet, target, actual_result, win, win_amount)

        await message.answer(text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Ошибка в start_basket_game: %s", e)
        try:
            await message.answer(f"❌ Произошла ошибка в игре: {e}")
        except Exception:
            pass
