# duels.py
import asyncio
import logging
import random
import uuid
from aiogram import Router, F, Bot
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

import db
import utils

logger = logging.getLogger(__name__)

router = Router()

# Хранилище активных дуэлей в памяти
ACTIVE_DUELS = {}

# Варианты выбора
RPS_CHOICES = {
    "rock": "🪨 Камень",
    "scissors": "✂️ Ножницы",
    "paper": "📄 Бумага"
}

FIGHT_ZONES = {
    "head": "🧢 Голова",
    "body": "👕 Корпус",
    "legs": "🦵 Ноги"
}

BIG_WIN_GIF_URL = "https://media.giphy.com/media/l0HlRnAWXxn0MhOBK/giphy.gif"


def get_mode_name(mode: str) -> str:
    if mode == "rps":
        return "🪨✂️📄 Камень-Ножницы-Бумага"
    elif mode == "fight":
        return "⚔️ Бой (Голова / Корпус / Ноги)"
    return "Дуэль"


def find_user_by_username(username: str) -> dict:
    """Универсальный безопасный поиск игрока в базе по юзернейму или первому имени"""
    username = username.strip("@").strip().lower()
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT user_id, first_name 
            FROM users 
            WHERE LOWER(username) = %s OR LOWER(first_name) = %s
            LIMIT 1
        """, (username, username))
        row = cursor.fetchone()
        if row:
            return {"user_id": row[0], "first_name": row[1]}
        return None
    except Exception as e:
        logger.error(f"Ошибка find_user_by_username: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


# --- КЛАВИАТУРЫ ---

def get_lobby_kb(duel_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔️ Принять Вызов!", callback_data=f"duel_accept:{duel_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отменить Дуэль", callback_data=f"duel_cancel:{duel_id}")
        ]
    ])


def get_rps_choice_kb(duel_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для КНБ"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🪨 Камень", callback_data=f"duel_act:{duel_id}:rock"),
            InlineKeyboardButton(text="✂️ Ножницы", callback_data=f"duel_act:{duel_id}:scissors"),
            InlineKeyboardButton(text="📄 Бумага", callback_data=f"duel_act:{duel_id}:paper")
        ]
    ])


def get_fight_choice_kb(duel_id: str) -> InlineKeyboardMarkup:
    """Единая независимая клавиатура Боя (Атака и Защита доступны обоим игрокам)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔️ 🧢 Голова", callback_data=f"duel_act:{duel_id}:atk_head"),
            InlineKeyboardButton(text="⚔️ 👕 Корпус", callback_data=f"duel_act:{duel_id}:atk_body"),
            InlineKeyboardButton(text="⚔️ 🦵 Ноги", callback_data=f"duel_act:{duel_id}:atk_legs")
        ],
        [
            InlineKeyboardButton(text="🛡️ 🧢 Голова", callback_data=f"duel_act:{duel_id}:def_head"),
            InlineKeyboardButton(text="🛡️ 👕 Корпус", callback_data=f"duel_act:{duel_id}:def_body"),
            InlineKeyboardButton(text="🛡️ 🦵 Ноги", callback_data=f"duel_act:{duel_id}:def_legs")
        ]
    ])


def get_fight_status_str(choices: dict) -> str:
    """Формирует строчку статуса выбора для боя"""
    atk_st = "✅" if "attack" in choices else "⏳"
    def_st = "✅" if "defend" in choices else "⏳"
    return f"⚔️ Атака [{atk_st}] | 🛡️ Защита [{def_st}]"


def get_rps_status_str(choices: dict) -> str:
    """Формирует строчку статуса выбора для КНБ"""
    return "✅ Выбор сделан" if "rps" in choices else "⏳ Выбирает..."


# --- ОБРАБОТЧИКИ КОМАНД ---

@router.message(StateFilter(None), F.text, F.text.lower().startswith(("дуэль", "дуэлька", "/duel", "duel")))
async def handle_duel_command(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id)

    parts = message.text.strip().split()
    if len(parts) < 2:
        text = (
            "⚔️ *КИБЕР-ДУЭЛИ на nCoin* ⚔️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🤖 *Играть с Кибер-Ботом:*\n"
            "✍️ Напишите: `дуэль <ставка>` или `дуэль <ставка> <кнб/бой>`\n\n"
            "👤 *Играть с другим игроком:*\n"
            "✍️ Ответьте на сообщение игрока: `дуэль <ставка>`\n"
            "✍️ Или напишите: `дуэль <ставка> @юзернейм`\n\n"
            "🎮 *Режимы дуэли:* \n"
            "• `кнб` — Камень, Ножницы, Бумага\n"
            "• `бой` — Бой (Голова, Корпус, Ноги)"
        )
        await message.answer(text, parse_mode="Markdown")
        return

    bet_str = parts[1]
    
    # 1. Проверяем дуэль ответом на сообщение
    target_id = None
    target_name = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name or f"Игрок {target_id}"

    # 2. Парсим аргументы на режим и юзернейм
    mode = None
    target_username = None
    
    for part in parts[2:]:
        part_lower = part.lower()
        if part.startswith("@"):
            target_username = part
        elif part_lower in ["кнб", "rps", "камень"]:
            mode = "rps"
        elif part_lower in ["бой", "fight", "гкн", "голова"]:
            mode = "fight"
        else:
            target_username = part

    # Если указан юзернейм, пробуем найти игрока в БД
    if target_username and not target_id:
        found = find_user_by_username(target_username)
        if found:
            target_id = found["user_id"]
            target_name = found["first_name"] or f"@{target_username.strip('@')}"
        else:
            await message.answer(f"❌ Игрок `{target_username}` не найден в базе данных бота!")
            return

    try:
        bet = utils.parse_bet_input(bet_str, user["balance"])
    except Exception:
        try:
            bet = utils.parse_bet_input(bet_str)
        except Exception:
            await message.answer("❌ Ошибка распознавания ставки!")
            return

    if bet <= 0:
        await message.answer("❌ Ставка должна быть больше 0!")
        return

    if user["balance"] < bet:
        await message.answer(f"❌ Недостаточно nCoin! Ваш баланс: *{user['balance']:,} nCoin*", parse_mode="Markdown")
        return

    # Если режим не выбран — выводим кнопки выбора
    if not mode:
        await state.update_data(pending_bet=bet)
        if target_id:
            text = (
                f"⚔️ *Вызов игрока {target_name} на Дуэль*\n"
                f"💰 Ставка: *{bet:,} nCoin*\n\n"
                f"Выберите режим битвы 👇"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🪨✂️📄 КНБ", callback_data=f"duel_mode_select:rps:player:{target_id}"),
                    InlineKeyboardButton(text="⚔️ Бой (Г/К/Н)", callback_data=f"duel_mode_select:fight:player:{target_id}")
                ],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="duel_cancel_creation")]
            ])
        else:
            text = (
                f"🤖 *Дуэль с Кибер-Ботом*\n"
                f"💰 Ставка: *{bet:,} nCoin*\n\n"
                f"Выберите режим битвы 👇"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🪨✂️📄 КНБ", callback_data="duel_mode_select:rps:bot"),
                    InlineKeyboardButton(text="⚔️ Бой (Г/К/Н)", callback_data="duel_mode_select:fight:bot")
                ],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="duel_cancel_creation")]
            ])
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        return

    if target_id:
        await create_and_publish_player_duel(message, user_id, target_id, bet, mode)
    else:
        await create_and_start_bot_duel(message, user_id, bet, mode)


@router.callback_query(F.data.startswith("duel_mode_select:"))
async def process_mode_select(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    mode = parts[1]
    target_type = parts[2]
    
    data = await state.get_data()
    bet = data.get("pending_bet")
    await state.clear()

    if not bet:
        await callback.message.edit_text("❌ Ошибка создания дуэли. Попробуйте снова.")
        return

    await callback.message.delete()
    
    if target_type == "bot":
        await create_and_start_bot_duel(callback.message, callback.from_user.id, bet, mode)
    else:
        target_id = int(parts[3])
        await create_and_publish_player_duel(callback.message, callback.from_user.id, target_id, bet, mode)


@router.callback_query(F.data == "duel_cancel_creation")
async def cancel_creation_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Дуэль отменена.")
    await state.clear()
    await callback.message.delete()


# --- ИНИЦИАЛИЗАЦИЯ ИГРЫ С БОТОМ ---

async def create_and_start_bot_duel(message_obj: Message, user_id: int, bet: float, mode: str):
    user = db.get_user(user_id)
    if user["balance"] < bet:
        await message_obj.answer("❌ Недостаточно nCoin на балансе!")
        return

    db.update_balance(user_id, -bet)

    duel_id = "bot_" + str(uuid.uuid4())[:8]
    creator_name = message_obj.from_user.first_name or f"Игрок {user_id}"

    ACTIVE_DUELS[duel_id] = {
        "creator_id": user_id,
        "creator_name": creator_name,
        "bet": bet,
        "mode": mode,
        "opponent_id": "bot",
        "opponent_name": "🤖 Кибер-Бот",
        "status": "in_progress",
        "p1_choices": {},
        "p2_choices": {},
        "chat_id": message_obj.chat.id
    }

    mode_title = get_mode_name(mode)
    
    if mode == "rps":
        p1_status = get_rps_status_str(ACTIVE_DUELS[duel_id]["p1_choices"])
        p2_status = "🤖 Бот готов"
        text = (
            f"🪨✂️📄 *ДУЭЛЬ КНБ С БОТОМ* 🪨✂️📄\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 [{creator_name}](tg://user?id={user_id}): {p1_status}\n"
            f"🔵 🤖 Кибер-Бот: {p2_status}\n"
            f"💰 Общий банк: *{bet * 2:,} nCoin*\n\n"
            f"⚠️ Сделайте ваш выбор кнопкой ниже 👇"
        )
        kb = get_rps_choice_kb(duel_id)
    else:
        p1_status = get_fight_status_str(ACTIVE_DUELS[duel_id]["p1_choices"])
        p2_status = "🤖 Бот готов"
        text = (
            f"🥊 *БОЙ С КИБЕР-БОТОМ* 🥊\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 [{creator_name}](tg://user?id={user_id}): {p1_status}\n"
            f"🔵 🤖 Кибер-Бот: {p2_status}\n"
            f"💰 Общий банк: *{bet * 2:,} nCoin*\n\n"
            f"⚠️ Выберите 1 зону АТАКИ (верхний ряд) и 1 зону ЗАЩИТЫ (нижний ряд) 👇"
        )
        kb = get_fight_choice_kb(duel_id)

    msg = await message_obj.answer(text, reply_markup=kb, parse_mode="Markdown")
    ACTIVE_DUELS[duel_id]["msg_id"] = msg.message_id


# --- ИНИЦИАЛИЗАЦИЯ ИГРЫ С ИГРОКОМ ---

async def create_and_publish_player_duel(message_obj: Message, creator_id: int, target_id: int, bet: float, mode: str):
    user = db.get_user(creator_id)
    if user["balance"] < bet:
        await message_obj.answer("❌ Недостаточно nCoin на балансе!")
        return

    target_user = db.get_user(target_id)
    target_name = target_user.get("first_name") or f"Игрок {target_id}"

    db.update_balance(creator_id, -bet)

    duel_id = str(uuid.uuid4())[:8]
    creator_name = message_obj.from_user.first_name or f"Игрок {creator_id}"

    ACTIVE_DUELS[duel_id] = {
        "creator_id": creator_id,
        "creator_name": creator_name,
        "bet": bet,
        "mode": mode,
        "opponent_id": target_id,
        "opponent_name": target_name,
        "status": "waiting",
        "p1_choices": {},
        "p2_choices": {},
        "chat_id": message_obj.chat.id,
        "is_targeted": True
    }

    mode_title = get_mode_name(mode)
    text = (
        f"⚔️ *ВЫЗОВ НА КИБЕР-ДУЭЛЬ!* ⚔️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Отправитель: [{creator_name}](tg://user?id={creator_id})\n"
        f"🎯 Кому вызов: [{target_name}](tg://user?id={target_id})\n"
        f"🎮 Режим: *{mode_title}*\n"
        f"💰 Ставка: *{bet:,} nCoin*\n\n"
        f"⏳ [{target_name}](tg://user?id={target_id}), примите дуэль кнопкой ниже!"
    )

    msg = await message_obj.answer(text, reply_markup=get_lobby_kb(duel_id), parse_mode="Markdown")
    ACTIVE_DUELS[duel_id]["msg_id"] = msg.message_id


# --- ОТМЕНА И ПРИНЯТИЕ ---

@router.callback_query(F.data.startswith("duel_cancel:"))
async def process_cancel_duel(callback: CallbackQuery):
    duel_id = callback.data.split(":")[1]
    duel = ACTIVE_DUELS.get(duel_id)

    if not duel:
        await callback.answer("Дуэль не найдена или уже завершена!", show_alert=True)
        return

    if callback.from_user.id != duel["creator_id"]:
        await callback.answer("Только создатель может отменить дуэль!", show_alert=True)
        return

    db.update_balance(duel["creator_id"], duel["bet"])
    del ACTIVE_DUELS[duel_id]

    await callback.answer("Дуэль отменена.")
    await callback.message.edit_text("❌ *Дуэль была отменена создателем. Ставка возвращена.*", parse_mode="Markdown")


@router.callback_query(F.data.startswith("duel_accept:"))
async def process_accept_duel(callback: CallbackQuery):
    duel_id = callback.data.split(":")[1]
    duel = ACTIVE_DUELS.get(duel_id)

    if not duel:
        await callback.answer("Дуэль не найдена или уже завершена!", show_alert=True)
        return

    opponent_id = callback.from_user.id
    if duel.get("is_targeted") and opponent_id != duel["opponent_id"]:
        await callback.answer("❌ Этот вызов брошен не вам!", show_alert=True)
        return

    if opponent_id == duel["creator_id"]:
        await callback.answer("Нельзя принять собственную дуэль!", show_alert=True)
        return

    if duel["status"] != "waiting":
        await callback.answer("Дуэль уже идет или завершена!", show_alert=True)
        return

    opp_user = db.get_user(opponent_id)
    bet = duel["bet"]

    if opp_user["balance"] < bet:
        await callback.answer("У вас недостаточно nCoin для этой ставки!", show_alert=True)
        return

    db.update_balance(opponent_id, -bet)

    opponent_name = callback.from_user.first_name or f"Игрок {opponent_id}"
    duel["opponent_id"] = opponent_id
    duel["opponent_name"] = opponent_name
    duel["status"] = "in_progress"

    await callback.answer("Дуэль успешно принята!")

    mode_title = get_mode_name(duel["mode"])

    if duel["mode"] == "rps":
        p1_st = get_rps_status_str(duel["p1_choices"])
        p2_st = get_rps_status_str(duel["p2_choices"])
        text = (
            f"🥊 *БИТВА КНБ НАЧАЛАСЬ!* 🥊\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 [{duel['creator_name']}](tg://user?id={duel['creator_id']}): {p1_st}\n"
            f"🔵 [{opponent_name}](tg://user?id={opponent_id}): {p2_st}\n"
            f"💰 Общий банк: *{bet * 2:,} nCoin*\n\n"
            f"⚠️ Оба игрока, выберите свою фигуру кнопками ниже 👇"
        )
        kb = get_rps_choice_kb(duel_id)
    else:
        p1_st = get_fight_status_str(duel["p1_choices"])
        p2_st = get_fight_status_str(duel["p2_choices"])
        text = (
            f"🥊 *ПОЕДИНОК НАЧАЛСЯ!* 🥊\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 [{duel['creator_name']}](tg://user?id={duel['creator_id']}): {p1_st}\n"
            f"🔵 [{opponent_name}](tg://user?id={opponent_id}): {p2_st}\n"
            f"💰 Общий банк: *{bet * 2:,} nCoin*\n\n"
            f"⚠️ Каждый боец выбирает 1 зону АТАКИ (верхний ряд) и 1 зону ЗАЩИТЫ (нижний ряд) 👇"
        )
        kb = get_fight_choice_kb(duel_id)

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


# --- СОВЕРШЕНИЕ ХОДОВ ---

@router.callback_query(F.data.startswith("duel_act:"))
async def process_duel_action(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    duel_id = parts[1]
    action = parts[2]

    duel = ACTIVE_DUELS.get(duel_id)
    if not duel or duel["status"] != "in_progress":
        await callback.answer("Дуэль завершена или не существует!", show_alert=True)
        return

    user_id = callback.from_user.id
    if user_id != duel["creator_id"] and user_id != duel["opponent_id"]:
        await callback.answer("Вы не участвуете в этой игре!", show_alert=True)
        return

    is_creator = (user_id == duel["creator_id"])
    player_choices = duel["p1_choices"] if is_creator else duel["p2_choices"]

    # --- РЕЖИМ КНБ ---
    if duel["mode"] == "rps":
        if "rps" in player_choices:
            await callback.answer("Вы уже сделали свой выбор!", show_alert=True)
            return

        player_choices["rps"] = action
        await callback.answer(f"Ваш выбор: {RPS_CHOICES.get(action, action)}")

        if duel["opponent_id"] == "bot":
            duel["p2_choices"]["rps"] = random.choice(["rock", "scissors", "paper"])
            await animate_and_resolve_rps(callback.message, duel_id)
        else:
            p1_done = "rps" in duel["p1_choices"]
            p2_done = "rps" in duel["p2_choices"]

            if p1_done and p2_done:
                await animate_and_resolve_rps(callback.message, duel_id)
            else:
                p1_st = get_rps_status_str(duel["p1_choices"])
                p2_st = get_rps_status_str(duel["p2_choices"])
                text = (
                    f"🥊 *БИТВА КНБ В РАЗГАРЕ!* 🥊\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 [{duel['creator_name']}](tg://user?id={duel['creator_id']}): {p1_st}\n"
                    f"🔵 [{duel['opponent_name']}](tg://user?id={duel['opponent_id']}): {p2_st}\n"
                    f"💰 Общий банк: *{duel['bet'] * 2:,} nCoin*\n\n"
                    f"⏳ Второй игрок делает свой выбор..."
                )
                try:
                    await callback.message.edit_text(text, reply_markup=get_rps_choice_kb(duel_id), parse_mode="Markdown")
                except Exception: pass

    # --- РЕЖИМ БОЙ ---
    elif duel["mode"] == "fight":
        if action.startswith("atk_"):
            atk_zone = action.replace("atk_", "")
            player_choices["attack"] = atk_zone
            await callback.answer(f"⚔️ Зона Атаки выбрана: {FIGHT_ZONES[atk_zone]}")

        elif action.startswith("def_"):
            def_zone = action.replace("def_", "")
            player_choices["defend"] = def_zone
            await callback.answer(f"🛡️ Зона Защиты выбрана: {FIGHT_ZONES[def_zone]}")

        p1_ready = ("attack" in duel["p1_choices"]) and ("defend" in duel["p1_choices"])
        
        if duel["opponent_id"] == "bot":
            if p1_ready:
                duel["p2_choices"]["attack"] = random.choice(["head", "body", "legs"])
                duel["p2_choices"]["defend"] = random.choice(["head", "body", "legs"])
                await animate_and_resolve_fight(callback.message, duel_id)
            else:
                p1_st = get_fight_status_str(duel["p1_choices"])
                text = (
                    f"🥊 *БОЙ С КИБЕР-БОТОМ* 🥊\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 [{duel['creator_name']}](tg://user?id={duel['creator_id']}): {p1_st}\n"
                    f"🔵 🤖 Кибер-Бот: 🤖 Бот готов\n"
                    f"💰 Общий банк: *{duel['bet'] * 2:,} nCoin*\n\n"
                    f"Выберите 1 зону АТАКИ (верх) и 1 зону ЗАЩИТЫ (низ) 👇"
                )
                try:
                    await callback.message.edit_text(text, reply_markup=get_fight_choice_kb(duel_id), parse_mode="Markdown")
                except Exception: pass
        else:
            p2_ready = ("attack" in duel["p2_choices"]) and ("defend" in duel["p2_choices"])

            if p1_ready and p2_ready:
                await animate_and_resolve_fight(callback.message, duel_id)
            else:
                p1_st = get_fight_status_str(duel["p1_choices"])
                p2_st = get_fight_status_str(duel["p2_choices"])
                text = (
                    f"🥊 *ПОЕДИНОК В РАЗГАРЕ!* 🥊\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 [{duel['creator_name']}](tg://user?id={duel['creator_id']}): {p1_st}\n"
                    f"🔵 [{duel['opponent_name']}](tg://user?id={duel['opponent_id']}): {p2_st}\n"
                    f"💰 Общий банк: *{duel['bet'] * 2:,} nCoin*\n\n"
                    f"⚠️ Оба игрока выбирают Атаку (верхний ряд) и Защиту (нижний ряд)!"
                )
                try:
                    await callback.message.edit_text(text, reply_markup=get_fight_choice_kb(duel_id), parse_mode="Markdown")
                except Exception: pass


# --- ПОДВЕДЕНИЕ ИТОГОВ ---

async def animate_and_resolve_rps(message_obj: Message, duel_id: str):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel: return

    p1_id, p1_name = duel["creator_id"], duel["creator_name"]
    p2_id, p2_name = duel["opponent_id"], duel["opponent_name"]
    bet = duel["bet"]
    total_bank = bet * 2

    p2_display = "🤖 Кибер-Бот" if p2_id == "bot" else f"[{p2_name}](tg://user?id={p2_id})"

    frame1 = (
        f"⚡ *СХВАТКА НАЧАЛАСЬ!* ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔴 [{p1_name}](tg://user?id={p1_id}) 🪨✂️📄 🔵 {p2_display}\n\n"
        f"🌀 Игроки заносят руки... Раскачка 3... 2... 1..."
    )
    try:
        await message_obj.edit_text(frame1, parse_mode="Markdown")
    except Exception: pass
    await asyncio.sleep(1.2)

    c1 = duel["p1_choices"]["rps"]
    c2 = duel["p2_choices"]["rps"]
    str1 = RPS_CHOICES[c1]
    str2 = RPS_CHOICES[c2]

    frame2 = (
        f"🔥 *ЦУ-Е-ФА!* 🔥\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔴 [{p1_name}](tg://user?id={p1_id}) выбрал: *{str1}*\n"
        f"🔵 {p2_display} выбрал: *{str2}*\n\n"
        f"💥 Идет подсчет результатов..."
    )
    try:
        await message_obj.edit_text(frame2, parse_mode="Markdown")
    except Exception: pass
    await asyncio.sleep(1.0)

    # Логика КНБ
    if c1 == c2:
        winner = None
    elif (c1 == "rock" and c2 == "scissors") or \
         (c1 == "scissors" and c2 == "paper") or \
         (c1 == "paper" and c2 == "rock"):
        winner = p1_id
    else:
        winner = p2_id

    if winner is None:
        db.update_balance(p1_id, bet)
        if p2_id != "bot":
            db.update_balance(p2_id, bet)
        res_text = (
            f"🤝 *НИЧЬЯ В КИБЕР-ДУЭЛИ!* 🤝\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 [{p1_name}](tg://user?id={p1_id}): {str1}\n"
            f"🔵 {p2_display}: {str2}\n\n"
            f"⚖️ Элементы совпали! Ставка *{bet:,} nCoin* возвращена."
        )
    elif winner == p1_id:
        db.update_balance(p1_id, total_bank)
        db.add_stats(p1_id, is_lost=False, bet_amount=bet)
        if p2_id != "bot":
            db.add_stats(p2_id, is_lost=True, lost_amount=bet, bet_amount=bet)

        p1_user = db.get_user(p1_id)
        res_text = (
            f"🎉 *ПОБЕДА В КИБЕР-ДУЭЛИ!* 🎉\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 [{p1_name}](tg://user?id={p1_id}): {str1}\n"
            f"🔵 {p2_display}: {str2}\n\n"
            f"🏆 Победитель: [{p1_name}](tg://user?id={p1_id})\n"
            f"💰 Ваш выигрыш: *+{total_bank:,} nCoin*\n"
            f"💳 Твой баланс: *{p1_user['balance']:,} nCoin*"
        )

        if total_bank >= 100000:
            try:
                await message_obj.delete()
                await message_obj.answer_animation(
                    animation=BIG_WIN_GIF_URL,
                    caption=res_text,
                    parse_mode="Markdown"
                )
                del ACTIVE_DUELS[duel_id]
                return
            except Exception: pass

    else:
        db.add_stats(p1_id, is_lost=True, lost_amount=bet, bet_amount=bet)
        if p2_id != "bot":
            db.update_balance(p2_id, total_bank)
            db.add_stats(p2_id, is_lost=False, bet_amount=bet)

        p1_user = db.get_user(p1_id)

        if p2_id == "bot":
            res_text = (
                f"🔴 *ПРОИГРЫШ В КИБЕР-ДУЭЛИ!* 🔴\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔴 [{p1_name}](tg://user?id={p1_id}): {str1}\n"
                f"🔵 🤖 Кибер-Бот: {str2}\n\n"
                f"🤖 Победитель: *🤖 Кибер-Бот*\n"
                f"💸 Ваши потери: *-{bet:,} nCoin*\n"
                f"💳 Твой баланс: *{p1_user['balance']:,} nCoin*"
            )
        else:
            p2_user = db.get_user(p2_id)
            res_text = (
                f"🎉 *ПОБЕДА В КИБЕР-ДУЭЛИ!* 🎉\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔴 [{p1_name}](tg://user?id={p1_id}): {str1}\n"
                f"🔵 [{p2_name}](tg://user?id={p2_id}): {str2}\n\n"
                f"🏆 Победитель: [{p2_name}](tg://user?id={p2_id})\n"
                f"💰 Выигрыш: *+{total_bank:,} nCoin*"
            )

    del ACTIVE_DUELS[duel_id]
    try:
        await message_obj.edit_text(res_text, parse_mode="Markdown")
    except Exception:
        await message_obj.answer(res_text, parse_mode="Markdown")


async def animate_and_resolve_fight(message_obj: Message, duel_id: str):
    duel = ACTIVE_DUELS.get(duel_id)
    if not duel: return

    p1_id, p1_name = duel["creator_id"], duel["creator_name"]
    p2_id, p2_name = duel["opponent_id"], duel["opponent_name"]
    bet = duel["bet"]
    total_bank = bet * 2

    p1_atk, p1_def = duel["p1_choices"]["attack"], duel["p1_choices"]["defend"]
    p2_atk, p2_def = duel["p2_choices"]["attack"], duel["p2_choices"]["defend"]

    p2_display = "🤖 Кибер-Бот" if p2_id == "bot" else f"[{p2_name}](tg://user?id={p2_id})"

    frame1 = (
        f"🥊 *ГОНГ! БОЙЦЫ СХОДЯТСЯ НА РИНГЕ!* 🥊\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔴 [{p1_name}](tg://user?id={p1_id}) ⚔️ 🔵 {p2_display}\n\n"
        f"💥 Звучит гонг! Начинается обмен молниеносными ударами..."
    )
    try:
        await message_obj.edit_text(frame1, parse_mode="Markdown")
    except Exception: pass
    await asyncio.sleep(1.2)

    p1_hit = (p1_atk != p2_def)
    p2_hit = (p2_atk != p1_def)

    eff_p1 = "💥 ХЫЩ! (ПРОБИВАЕТ БЛОК!)" if p1_hit else "🛡️ ДЗЫНЬ! (ЗАБЛОКИРОВАНО!)"
    eff_p2 = "💥 ХЫЩ! (ПРОБИВАЕТ БЛОК!)" if p2_hit else "🛡️ ДЗЫНЬ! (ЗАБЛОКИРОВАНО!)"

    frame2 = (
        f"🥊 *РАЗМЕН УДАРАМИ!* 🥊\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔴 [{p1_name}](tg://user?id={p1_id}) бьёт в {FIGHT_ZONES[p1_atk]}:\n↳ {eff_p1}\n\n"
        f"🔵 {p2_display} бьёт в {FIGHT_ZONES[p2_atk]}:\n↳ {eff_p2}"
    )
    try:
        await message_obj.edit_text(frame2, parse_mode="Markdown")
    except Exception: pass
    await asyncio.sleep(1.4)

    p1_score = 1 if p1_hit else 0
    p2_score = 1 if p2_hit else 0

    log_p1 = f"Атака: {FIGHT_ZONES[p1_atk]} | Защита: {FIGHT_ZONES[p1_def]} " + ("🎯 (УДАР!)" if p1_hit else "🛡️ (БЛОК!)")
    log_p2 = f"Атака: {FIGHT_ZONES[p2_atk]} | Защита: {FIGHT_ZONES[p2_def]} " + ("🎯 (УДАР!)" if p2_hit else "🛡️ (БЛОК!)")

    if p1_score == p2_score:
        db.update_balance(p1_id, bet)
        if p2_id != "bot":
            db.update_balance(p2_id, bet)
        res_text = (
            f"🥊 *НИЧЬЯ В БОЮ!* 🤝\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 [{p1_name}](tg://user?id={p1_id}):\n↳ {log_p1}\n\n"
            f"🔵 {p2_display}:\n↳ {log_p2}\n\n"
            f"⚖️ Оба бойца показали равный результат! Ставки *{bet:,} nCoin* возвращены."
        )
    elif p1_score > p2_score:
        db.update_balance(p1_id, total_bank)
        db.add_stats(p1_id, is_lost=False, bet_amount=bet)
        if p2_id != "bot":
            db.add_stats(p2_id, is_lost=True, lost_amount=bet, bet_amount=bet)

        p1_user = db.get_user(p1_id)
        res_text = (
            f"⚔️ *ПОБЕДА В БОЮ!* 🏆\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 [{p1_name}](tg://user?id={p1_id}):\n↳ {log_p1}\n\n"
            f"🔵 {p2_display}:\n↳ {log_p2}\n\n"
            f"🎉 ЧЕМПИОН РИНГА: [{p1_name}](tg://user?id={p1_id})\n"
            f"💰 Ваш выигрыш: *+{total_bank:,} nCoin*\n"
            f"💳 Твой баланс: *{p1_user['balance']:,} nCoin*"
        )

        if total_bank >= 100000:
            try:
                await message_obj.delete()
                await message_obj.answer_animation(
                    animation=BIG_WIN_GIF_URL,
                    caption=res_text,
                    parse_mode="Markdown"
                )
                del ACTIVE_DUELS[duel_id]
                return
            except Exception: pass

    else:
        db.add_stats(p1_id, is_lost=True, lost_amount=bet, bet_amount=bet)
        if p2_id != "bot":
            db.update_balance(p2_id, total_bank)
            db.add_stats(p2_id, is_lost=False, bet_amount=bet)

        p1_user = db.get_user(p1_id)

        if p2_id == "bot":
            res_text = (
                f"🔴 *ПРОИГРЫШ В БОЮ!* 🔴\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔴 [{p1_name}](tg://user?id={p1_id}):\n↳ {log_p1}\n\n"
                f"🔵 🤖 Кибер-Бот:\n↳ {log_p2}\n\n"
                f"🤖 ЧЕМПИОН РИНГА: *🤖 Кибер-Бот*\n"
                f"💸 Ваши потери: *-{bet:,} nCoin*\n"
                f"💳 Твой баланс: *{p1_user['balance']:,} nCoin*"
            )
        else:
            res_text = (
                f"⚔️ *ПОБЕДА В БОЮ!* 🏆\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔴 [{p1_name}](tg://user?id={p1_id}):\n↳ {log_p1}\n\n"
                f"🔵 [{p2_name}](tg://user?id={p2_id}):\n↳ {log_p2}\n\n"
                f"🎉 ЧЕМПИОН РИНГА: [{p2_name}](tg://user?id={p2_id})\n"
                f"💰 Выигрыш: *+{total_bank:,} nCoin*"
            )

    del ACTIVE_DUELS[duel_id]
    try:
        await message_obj.edit_text(res_text, parse_mode="Markdown")
    except Exception:
        await message_obj.answer(res_text, parse_mode="Markdown")
