import asyncio
import logging
import random
from aiogram import Bot, Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import db
import utils

logger = logging.getLogger(__name__)

router = Router()

MAX_BET = 300_000_000  # Максимальный лимит ставки: 300кк (300 000 000)


class OchkoStates(StatesGroup):
    playing = State()


# Колода карт и их масти
SUITS = ["♠️", "♥️", "♦️", "♣️"]
CARD_RANKS = {
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 2,
    "Q": 3,
    "K": 4,
    "A": 11,
}


def format_ncoin_display(value: float) -> str:
    """Вспомогательное форматирование чисел"""
    if value < 1:
        return "0"
    epsilon = 1e-9
    if abs(value - round(value, 2)) < epsilon:
        return f"{int(value):,}"
    else:
        return f"{value:,}"


def create_deck():
    """Создает и перемешивает колоду из 36 карт"""
    deck = []
    for suit in SUITS:
        for rank in CARD_RANKS.keys():
            deck.append((rank, suit))
    random.shuffle(deck)
    return deck


def calculate_points(hand):
    """Считает очки в руке с учетом тузов"""
    total = 0
    aces = 0

    # Проверка на Золотое Очко (два туза при первой сдаче из 2 карт)
    if len(hand) == 2 and hand[0][0] == "A" and hand[1][0] == "A":
        return 21, True  # Золотое очко!

    for rank, _ in hand:
        val = CARD_RANKS[rank]
        if rank == "A":
            aces += 1
        total += val

    # Оптимизация тузов (если перебор, туз считается как 1)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1

    return total, False


def format_hand(hand, hide_second=False):
    """Красиво форматирует карты в руке"""
    if hide_second:
        return f"{hand[0][0]}{hand[0][1]} 🎴"

    res = []
    for rank, suit in hand:
        res.append(f"{rank}{suit}")
    return " ".join(res)


def get_dealer_visible_points(dealer_hand):
    """Считает очко первой видимой карты дилера"""
    first_card_rank = dealer_hand[0][0]
    return CARD_RANKS[first_card_rank]


def get_game_kb(user_id: int, can_double=True) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру игры с привязкой user_id для защиты от нажатий другими игроками"""
    buttons = [
        [
            InlineKeyboardButton(
                text="🃏 Взять карту", callback_data=f"ochko_hit:{user_id}"
            ),
            InlineKeyboardButton(
                text="🛑 Хватит", callback_data=f"ochko_stand:{user_id}"
            ),
        ]
    ]
    if can_double:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔥 Удвоить (x2)", callback_data=f"ochko_double:{user_id}"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def safe_edit_or_resend(callback: CallbackQuery, text: str, reply_markup=None, parse_mode="Markdown"):
    """Безопасное редактирование сообщений в игре"""
    try:
        if callback.message and callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"Ошибка редактирования сообщения в Ochko, отправляем новое: {e}")
        try:
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass


@router.callback_query(F.data == "ochko_menu_inline")
async def ochko_menu_inline_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    user = db.get_user(callback.from_user.id)
    text = (
        "🎴 *Игра 21 / ОЧКО против Дилера* 🎴\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Наберите больше очков, чем дилер, но не более 21!\n\n"
        "🃏 *Достоинства карт:*\n"
        "• 6–10 = по номиналу\n"
        "• J (Валет) = 2 | Q (Дама) = 3 | K (Король) = 4\n"
        "• A (Туз) = 11 (или 1 при переборе)\n"
        "🌟 *«Золотое Очко»* (два туза сразу) = Мгновенная победа!\n\n"
        f"💳 Твой баланс: *{format_ncoin_display(user['balance'])} nCoin*\n"
        f"⚠️ Максимальная ставка: *{format_ncoin_display(MAX_BET)} nCoin* (300кк)\n\n"
        "✍️ *Для запуска напишите:* `очко <ставка>` или `21 <ставка>`\n"
        "Например: `очко 10к` или `21 все`"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ 1k", callback_data="ochko_quick:1000"
                ),
                InlineKeyboardButton(
                    text="⚡ 5k", callback_data="ochko_quick:5000"
                ),
                InlineKeyboardButton(
                    text="⚡ 10k", callback_data="ochko_quick:10000"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад в меню", callback_data="games_menu"
                )
            ],
        ]
    )
    await safe_edit_or_resend(callback, text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("ochko_quick:"))
async def quick_start_ochko(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bet = float(callback.data.split(":")[1])
    await start_ochko_game(
        callback.message, state, callback.from_user.id, bet, is_callback=True
    )


@router.message(
    StateFilter(None), F.text, F.text.lower().startswith(("очко", "21"))
)
async def handle_ochko_commands(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id)

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer(
            "🎴 *Игра 21 / ОЧКО* 🎴\n\n"
            "✍️ *Использование:* `очко <ставка>` или `21 <ставка>`\n"
            "Например: `очко 5000` или `21 все`\n"
            f"⚠️ Максимальная ставка: *{format_ncoin_display(MAX_BET)} nCoin* (300кк)",
            parse_mode="Markdown",
        )
        return

    bet_str = parts[1]
    try:
        bet = utils.parse_bet_input(bet_str, user["balance"])
    except Exception:
        try:
            bet = utils.parse_bet_input(bet_str)
        except Exception:
            await message.answer("❌ Ошибка распознавания ставки!")
            return

    await start_ochko_game(message, state, user_id, bet, is_callback=False)


async def start_ochko_game(
    message_obj: Message,
    state: FSMContext,
    user_id: int,
    bet: float,
    is_callback: bool = False,
):
    user = db.get_user(user_id)

    if bet <= 0:
        await message_obj.answer("❌ Ставка должна быть больше 0!")
        return

    if bet > MAX_BET:
        await message_obj.answer(
            f"❌ Максимальная ставка — *{format_ncoin_display(MAX_BET)} nCoin* (300кк)!",
            parse_mode="Markdown",
        )
        return

    if user["balance"] < bet:
        await message_obj.answer(
            f"❌ Недостаточно nCoin! Ваш баланс: *{format_ncoin_display(user['balance'])} nCoin*",
            parse_mode="Markdown",
        )
        return

    # Списываем ставку
    db.update_balance(user_id, -bet)

    # Создаем колоду и раздаем карты
    deck = create_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    p_points, p_golden = calculate_points(player_hand)

    await state.update_data(
        bet=bet,
        deck=deck,
        player_hand=player_hand,
        dealer_hand=dealer_hand,
        user_id=user_id,
    )
    await state.set_state(OchkoStates.playing)

    # Проверка на моментальное Золотое Очко при раздаче
    if p_golden:
        win_amount = round(bet * 3.0, 2)
        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)
        await state.clear()

        text = (
            "🌟 *ЗОЛОТОЕ ОЧКО! МГНОВЕННАЯ ПОБЕДА!* 🌟\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🃏 Ваши карты: `{format_hand(player_hand)}` (два Туза!)\n"
            f"💰 Супер-Выигрыш (x3): *+{format_ncoin_display(win_amount)} nCoin*\n\n"
            f"💳 Ваш баланс: *{format_ncoin_display(db.get_user(user_id)['balance'])} nCoin*"
        )
        await message_obj.answer(text, parse_mode="Markdown")
        return

    dealer_vis_pts = get_dealer_visible_points(dealer_hand)

    text = (
        "🎴 *ИГРА 21 (ОЧКО)* 🎴\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤵 *Дилер:* `{format_hand(dealer_hand, hide_second=True)}` (*{dealer_vis_pts}+? оч.*)\n"
        f"👤 *Ваши карты:* `{format_hand(player_hand)}` (*{p_points} оч.*)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Ставка: *{format_ncoin_display(bet)} nCoin*\n\n"
        "👇 Ваш ход! Возьмите карту или нажмите **Хватит**."
    )

    await message_obj.answer(
        text, reply_markup=get_game_kb(user_id, can_double=True), parse_mode="Markdown"
    )


# --- ВЗЯТЬ КАРТУ (HIT) ---
@router.callback_query(F.data.startswith("ochko_hit:"))
async def ochko_hit_callback(callback: CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split(":")[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("❌ Это не ваша игра!", show_alert=True)
        return

    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id or user_id != callback.from_user.id:
        await callback.answer("❌ Игра уже завершена!", show_alert=True)
        return

    await callback.answer("🃏 Вы взяли карту!")

    deck = data.get("deck")
    player_hand = data.get("player_hand")
    dealer_hand = data.get("dealer_hand")
    bet = data.get("bet")

    # Берем карту из колоды
    new_card = deck.pop()
    player_hand.append(new_card)

    p_points, _ = calculate_points(player_hand)
    await state.update_data(deck=deck, player_hand=player_hand)

    # Проверка на перебор игрока
    if p_points > 21:
        db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
        await state.clear()

        d_points, _ = calculate_points(dealer_hand)
        text = (
            "💥 *ПЕРЕБОР! ВЫ ПРОИГРАЛИ!* 💥\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Ваши карты: `{format_hand(player_hand)}` (*{p_points} очков!*)\n"
            f"🤵 Карты дилера: `{format_hand(dealer_hand)}` (*{d_points} оч.*)\n\n"
            f"💸 Потеря ставки: *-{format_ncoin_display(bet)} nCoin*\n"
            f"💳 Ваш баланс: *{format_ncoin_display(db.get_user(user_id)['balance'])} nCoin*"
        )
        await safe_edit_or_resend(callback, text, parse_mode="Markdown")
        return

    # Если ровно 21 — авто-хватит
    if p_points == 21:
        await finish_ochko_game(callback, state)
        return

    dealer_vis_pts = get_dealer_visible_points(dealer_hand)
    text = (
        "🎴 *ИГРА 21 (ОЧКО)* 🎴\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤵 *Дилер:* `{format_hand(dealer_hand, hide_second=True)}` (*{dealer_vis_pts}+? оч.*)\n"
        f"👤 *Ваши карты:* `{format_hand(player_hand)}` (*{p_points} оч.*)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Ставка: *{format_ncoin_display(bet)} nCoin*\n\n"
        "👇 Ваш ход! Возьмите еще карту или остановитесь."
    )
    await safe_edit_or_resend(
        callback, text, reply_markup=get_game_kb(user_id, can_double=False), parse_mode="Markdown"
    )


# --- УДВОИТЬ СТАВКУ (DOUBLE) ---
@router.callback_query(F.data.startswith("ochko_double:"))
async def ochko_double_callback(callback: CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split(":")[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("❌ Это не ваша игра!", show_alert=True)
        return

    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id or user_id != callback.from_user.id:
        await callback.answer("❌ Игра уже завершена!", show_alert=True)
        return

    bet = data.get("bet")
    user = db.get_user(user_id)

    if user["balance"] < bet:
        await callback.answer(
            "❌ Недостаточно средств для удвоения!", show_alert=True
        )
        return

    await callback.answer("🔥 Ставка удвоена!")

    # Досписываем ставку
    db.update_balance(user_id, -bet)
    new_bet = bet * 2

    deck = data.get("deck")
    player_hand = data.get("player_hand")

    player_hand.append(deck.pop())
    p_points, _ = calculate_points(player_hand)

    await state.update_data(
        bet=new_bet, deck=deck, player_hand=player_hand
    )

    if p_points > 21:
        dealer_hand = data.get("dealer_hand")
        db.add_stats(
            user_id, is_lost=True, lost_amount=new_bet, bet_amount=new_bet
        )
        await state.clear()

        d_points, _ = calculate_points(dealer_hand)
        text = (
            "💥 *ПЕРЕБОР ПОСЛЕ УДВОЕНИЯ!* 💥\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Ваши карты: `{format_hand(player_hand)}` (*{p_points} очков!*)\n"
            f"🤵 Карты дилера: `{format_hand(dealer_hand)}` (*{d_points} оч.*)\n\n"
            f"💸 Удвоенная потеря: *-{format_ncoin_display(new_bet)} nCoin*\n"
            f"💳 Ваш баланс: *{format_ncoin_display(db.get_user(user_id)['balance'])} nCoin*"
        )
        await safe_edit_or_resend(callback, text, parse_mode="Markdown")
        return

    await finish_ochko_game(callback, state)


# --- ХВАТИТ / ХОД ДИЛЕРА (STAND) ---
@router.callback_query(F.data.startswith("ochko_stand:"))
async def ochko_stand_callback(callback: CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split(":")[1])

    if callback.from_user.id != target_user_id:
        await callback.answer("❌ Это не ваша игра!", show_alert=True)
        return

    data = await state.get_data()
    if not data.get("user_id"):
        await callback.answer("❌ Игра уже завершена!", show_alert=True)
        return

    await callback.answer("🛑 Вы остановились. Ход дилера...")
    await finish_ochko_game(callback, state)


async def finish_ochko_game(callback: CallbackQuery, state: FSMContext):
    """Добор карт дилером и расчет итогов"""
    data = await state.get_data()
    user_id = data.get("user_id")
    bet = data.get("bet")
    deck = data.get("deck")
    player_hand = data.get("player_hand")
    dealer_hand = data.get("dealer_hand")

    if not user_id:
        return

    p_points, _ = calculate_points(player_hand)

    # Добор дилера (дилер берет пока < 17)
    d_points, _ = calculate_points(dealer_hand)
    while d_points < 17:
        dealer_hand.append(deck.pop())
        d_points, _ = calculate_points(dealer_hand)

    await state.clear()

    # Сравнение результатов
    if d_points > 21:
        # Дилер перебрал -> Победа игрока
        win_amount = round(bet * 2.0, 2)
        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)

        result_text = (
            "🎉 *ВЫ ВЫИГРАЛИ! ДИЛЕР ПЕРЕБРАЛ!* 🎉\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Ваши карты: `{format_hand(player_hand)}` (*{p_points} оч.*)\n"
            f"🤵 Карты дилера: `{format_hand(dealer_hand)}` (*{d_points} оч.* — Перебор! 💥)\n\n"
            f"💰 Ваш выигрыш (x2): *+{format_ncoin_display(win_amount)} nCoin*\n"
            f"💳 Ваш баланс: *{format_ncoin_display(db.get_user(user_id)['balance'])} nCoin*"
        )
    elif p_points > d_points:
        # У игрока больше очков -> Победа
        win_amount = round(bet * 2.0, 2)
        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)

        result_text = (
            "🎉 *ПОБЕДА! ВЫ ОБОШЛИ ДИЛЕРА!* 🎉\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Ваши карты: `{format_hand(player_hand)}` (*{p_points} оч.*)\n"
            f"🤵 Карты дилера: `{format_hand(dealer_hand)}` (*{d_points} оч.*)\n\n"
            f"💰 Ваш выигрыш (x2): *+{format_ncoin_display(win_amount)} nCoin*\n"
            f"💳 Ваш баланс: *{format_ncoin_display(db.get_user(user_id)['balance'])} nCoin*"
        )
    elif p_points == d_points:
        # Ничья (Возврат ставки)
        db.update_balance(user_id, bet)

        result_text = (
            "🤝 *НИЧЬЯ!* 🤝\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Ваши карты: `{format_hand(player_hand)}` (*{p_points} оч.*)\n"
            f"🤵 Карты дилера: `{format_hand(dealer_hand)}` (*{d_points} оч.*)\n\n"
            f"🔄 Ставка возвращена: *{format_ncoin_display(bet)} nCoin*\n"
            f"💳 Ваш баланс: *{format_ncoin_display(db.get_user(user_id)['balance'])} nCoin*"
        )
    else:
        # У дилера больше очков -> Проигрыш
        db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)

        result_text = (
            "🔴 *ДИЛЕР ВЫИГРАЛ!* 🔴\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Ваши карты: `{format_hand(player_hand)}` (*{p_points} оч.*)\n"
            f"🤵 Карты дилера: `{format_hand(dealer_hand)}` (*{d_points} оч.*)\n\n"
            f"💸 Потеря ставки: *-{format_ncoin_display(bet)} nCoin*\n"
            f"💳 Ваш баланс: *{format_ncoin_display(db.get_user(user_id)['balance'])} nCoin*"
        )

    await safe_edit_or_resend(callback, result_text, parse_mode="Markdown")
