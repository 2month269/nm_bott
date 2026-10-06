import asyncio
import hashlib
import secrets
import html
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import db
import utils

router = Router()

DICE_ROUNDS: dict[str, dict] = {}

MAX_DICE_BET = 250_000_000.0

def pe(emoji_id: str, fallback: str) -> str:
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback

PE_DICE = pe("5467538555158943525", "🎲")
PE_PARTY = pe("5989848973974704652", "🎉")
PE_CHECK = pe("5805523262691611326", "✅")
PE_CROSS = pe("5420323339723881652", "❌")
PE_MONEY = pe("5201873447554145566", "💸")
PE_CASH = pe("5453901475648390219", "💰")
PE_LIGHTNING = pe("5226929552319594190", "⚡")
PE_PACKAGE = pe("5463137996091962323", "📦")
PE_LOCK = pe("5368324170671202286", "🔐")
PE_UP_TRIANGLE = pe("5463122435425448565", "🔺")
PE_DOWN_TRIANGLE = pe("5447183459602669338", "🔻")
PE_CHART = pe("5368324170671202286", "📊")
PE_CARD = pe("6280364500361155698", "💳")
PE_WRITE = pe("5197269100878907942", "✍️")
PE_TARGET = pe("5350612670435313545", "🎯")

PREDICTIONS = {
    "больше": {"type": "greater", "name": f"больше 3 {PE_UP_TRIANGLE}", "mult": 1.94, "wins": [4, 5, 6]},
    "б": {"type": "greater", "name": f"больше 3 {PE_UP_TRIANGLE}", "mult": 1.94, "wins": [4, 5, 6]},
    "меньше": {"type": "less", "name": f"меньше 3 {PE_DOWN_TRIANGLE}", "mult": 2.90, "wins": [1, 2]},
    "м": {"type": "less", "name": f"меньше 3 {PE_DOWN_TRIANGLE}", "mult": 2.90, "wins": [1, 2]},
    "равно": {"type": "equal", "name": "равно 3", "mult": 5.80, "wins": [3]},
    "р": {"type": "equal", "name": "равно 3", "mult": 5.80, "wins": [3]},
    "чет": {"type": "even", "name": "четное", "mult": 1.94, "wins": [2, 4, 6]},
    "чёт": {"type": "even", "name": "четное", "mult": 1.94, "wins": [2, 4, 6]},
    "четное": {"type": "even", "name": "четное", "mult": 1.94, "wins": [2, 4, 6]},
    "чётное": {"type": "even", "name": "четное", "mult": 1.94, "wins": [2, 4, 6]},
    "нечет": {"type": "odd", "name": "нечетное", "mult": 1.94, "wins": [1, 3, 5]},
    "нечёт": {"type": "odd", "name": "нечетное", "mult": 1.94, "wins": [1, 3, 5]},
    "нечетное": {"type": "odd", "name": "нечетное", "mult": 1.94, "wins": [1, 3, 5]},
    "нечётное": {"type": "odd", "name": "нечетное", "mult": 1.94, "wins": [1, 3, 5]},
}

for num in range(1, 7):
    PREDICTIONS[str(num)] = {
        "type": "exact",
        "name": f"число {num}",
        "mult": 5.80,
        "wins": [num]
    }


def fmt_d(val: float) -> str:
    """Форматирует число с разделителем-апострофом: 10000 -> 10'000"""
    val = float(val or 0)
    if abs(val - round(val)) < 1e-9:
        return f"{int(val):,}".replace(",", "'")
    return f"{val:,.2f}".replace(",", "'")


def parse_prediction(pred_raw: str):
    """Распознает исход ставки и возвращает конфигурацию"""
    cleaned = str(pred_raw).strip().lower().replace("ё", "е")
    if cleaned in PREDICTIONS:
        return PREDICTIONS[cleaned], cleaned
    raw_clean = str(pred_raw).strip().lower()
    if raw_clean in PREDICTIONS:
        return PREDICTIONS[raw_clean], raw_clean
    return None, None


def get_dice_kb(round_id: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру результатов. Повтор игры и честность полностью убраны."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎲 Новая ставка",
                callback_data="dice_menu",
                style="success"
            )
        ]
    ])


async def start_dice_game(bot: Bot, chat_id: int, user_id: int, bet: float, choice_raw: str, reply_to_message_id: int = None):
    """
    Универсальная функция запуска кубика.
    user_id передается явно — исключает сбои баланса.
    reply_to_message_id обеспечивает ответ с цитатой.
    """
    if bet > MAX_DICE_BET:
        await bot.send_message(
            chat_id,
            f"{PE_CROSS} <b>Максимальная ставка:</b> <b>{fmt_d(MAX_DICE_BET)} m¢</b> (300кк)!",
            reply_to_message_id=reply_to_message_id,
            parse_mode="HTML"
        )
        return

    user = await asyncio.to_thread(db.get_user, user_id)
    user_balance = float(user.get("balance", 0) or 0)

    if user_balance < bet:
        await bot.send_message(
            chat_id,
            f"{PE_CROSS} <b>Недостаточно m¢!</b>\n"
            f"Твой баланс: <b>{fmt_d(user_balance)} m¢</b>",
            reply_to_message_id=reply_to_message_id,
            parse_mode="HTML"
        )
        return

    rule, norm_choice = parse_prediction(choice_raw)
    if not rule:
        await bot.send_message(
            chat_id,
            f"{PE_CROSS} <b>Неверный исход!</b>\n"
            "Доступно: <code>1-6</code>, <code>больше</code> (<code>б</code>), <code>меньше</code> (<code>м</code>), "
            "<code>равно</code> (<code>р</code>), <code>чет</code>, <code>нечет</code>",
            reply_to_message_id=reply_to_message_id,
            parse_mode="HTML"
        )
        return

    # Генерация хэша честности до броска
    server_seed = secrets.token_hex(24)
    sha_hash = hashlib.sha256(f"{server_seed}:{user_id}:{bet}:{norm_choice}".encode("utf-8")).hexdigest()
    round_id = secrets.token_hex(8)

    # Списываем баланс (в отдельном потоке, не блокируя event loop)
    await asyncio.to_thread(db.update_balance, user_id, -bet)

    # Бросок анимированного кубика Telegram
    dice_msg = await bot.send_dice(chat_id, emoji="🎲")
    result_val = int(dice_msg.dice.value)

    # Сохраняем раунд
    DICE_ROUNDS[round_id] = {
        "user_id": user_id,
        "bet": bet,
        "choice_raw": norm_choice,
        "rule_name": rule["name"],
        "mult": rule["mult"],
        "result_val": result_val,
        "server_seed": server_seed,
        "sha_hash": sha_hash
    }

    # Оптимальная задержка до окончания анимации
    await asyncio.sleep(2.5)

    is_win = result_val in rule["wins"]
    mult_str = f"x{rule['mult']:.2f}".replace(".", ",")

    if is_win:
        win_amount = round(bet * rule["mult"], 2)
        await asyncio.to_thread(db.update_balance, user_id, win_amount)
        await asyncio.to_thread(db.add_stats, user_id, is_lost=False, bet_amount=bet, win_amount=win_amount, game_name="dice")
        
        # ТОЧНЫЙ ТЕКСТ ПОБЕДЫ, КАК НА СКРИНШОТАХ
        text = (
            f"{PE_PARTY} <b>Кубик · Победа!</b> {PE_CHECK}\n"
            "· · · · · · · · · · · · · · · · · · · · ·\n"
            f"{PE_MONEY} <b>Ставка:</b> {fmt_d(bet)} m¢\n"
            f"{PE_DICE} <b>Выбрано:</b> {rule['name']}\n"
            f"{PE_CASH} <b>Выигрыш:</b> {mult_str} / {fmt_d(win_amount)} m¢\n\n"
            f"<blockquote>{PE_LIGHTNING} Выпало: <code>{result_val}</code></blockquote>"
        )
    else:
        await asyncio.to_thread(db.add_stats, user_id, is_lost=True, lost_amount=bet, bet_amount=bet, game_name="dice")
        
        # ТОЧНЫЙ ТЕКСТ ПРОИГРЫША, КАК НА СКРИНШОТАХ
        text = (
            f"{PE_PACKAGE} <b>Кубик · Проигрыш!</b>\n"
            "· · · · · · · · · · · · · · · · · · · · ·\n"
            f"{PE_MONEY} <b>Ставка:</b> {fmt_d(bet)} m¢\n"
            f"{PE_DICE} <b>Выбрано:</b> {rule['name']}\n\n"
            f"<blockquote>{PE_LIGHTNING} Выпало: <code>{result_val}</code></blockquote>"
        )

    # Отправка с ответом на исходное сообщение пользователя
    target_reply_id = reply_to_message_id or dice_msg.message_id
    try:
        await bot.send_message(
            chat_id,
            text,
            reply_to_message_id=target_reply_id,
            reply_markup=get_dice_kb(round_id),
            parse_mode="HTML"
        )
    except Exception:
        # Fallback без HTML разметки, если клиент не поддерживает теги
        clean_text = (
            text.replace("<b>", "")
                .replace("</b>", "")
                .replace("<blockquote>", "")
                .replace("</blockquote>", "")
                .replace("<code>", "")
                .replace("</code>", "")
        )
        await bot.send_message(
            chat_id,
            clean_text,
            reply_to_message_id=target_reply_id,
            reply_markup=get_dice_kb(round_id)
        )


@router.callback_query(F.data == "dice_menu")
async def dice_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await asyncio.to_thread(db.get_user, callback.from_user.id)
    text = (
        f"{PE_DICE} <b>Кубик (Dice)</b> {PE_DICE}\n\n"
        "Угадай, какое число или диапазон выпадет на кубике!\n\n"
        f"{PE_CHART} <b>Варианты ставок:</b>\n"
        f"• <code>больше</code> или <code>б</code> — числа 4, 5, 6 (x1.94)\n"
        f"• <code>меньше</code> или <code>м</code> — числа 1, 2 (x2.90)\n"
        f"• <code>равно</code> или <code>р</code> — ровно 3 (x5.80)\n"
        f"• <code>чет</code> / <code>нечет</code> — чётное / нечётное (x1.94)\n"
        f"• <code>1-6</code> — точное число (x5.80)\n\n"
        f"{PE_CARD} Твой баланс: <b>{fmt_d(user.get('balance', 0))} m¢</b>\n"
        f"{PE_CROSS} Максимальная ставка: <b>{fmt_d(MAX_DICE_BET)} m¢</b> (300кк)\n\n"
        f"{PE_WRITE} <b>Формат команды в чате:</b>\n"
        "<code>кубик &lt;ставка&gt; &lt;исход&gt;</code>\n"
        "<i>Примеры:</i>\n"
        "• <code>кубик 10к чет</code>\n"
        "• <code>кубик 10к больше</code>\n"
        "• <code>кубик 100 б</code>\n"
        "• <code>кубик все б</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="games_menu", style="danger")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text.lower().startswith("кубик"))
async def dice_text_cmd(message: Message, state: FSMContext):
    await state.clear()
    parts = message.text.lower().split()
    if len(parts) != 3:
        await message.answer(
            f"{PE_CROSS} <b>Используйте:</b> <code>кубик &lt;ставка&gt; &lt;исход&gt;</code>\n"
            "<i>Например:</i> <code>кубик 10к чет</code> или <code>кубик 100 б</code> или <code>кубик все б</code>",
            parse_mode="HTML"
        )
        return

    user_id = message.from_user.id
    user = await asyncio.to_thread(db.get_user, user_id)
    bet = utils.parse_bet_input(parts[1], user.get("balance", 0))

    if bet <= 0:
        await message.answer(f"{PE_CROSS} <b>Неверный формат ставки!</b>", parse_mode="HTML")
        return

    if bet > MAX_DICE_BET:
        await message.answer(
            f"{PE_CROSS} <b>Максимальная ставка:</b> <b>{fmt_d(MAX_DICE_BET)} m¢</b> (300кк)!",
            parse_mode="HTML"
        )
        return

    choice_raw = parts[2]
    await start_dice_game(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=user_id,
        bet=bet,
        choice_raw=choice_raw,
        reply_to_message_id=message.message_id
    )
