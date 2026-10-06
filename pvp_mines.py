# pvp_mines.py
"""
Модуль PvP Минной Дуэли (1x1) для nCoin Bot.
Работает через Telegram Inline Query: @nmines_bot 20к 3
Сетка 5x5 (25 клеток), выбор мин от 1 до 16, комиссия 3%.
Клетки поля и кнопки с цветными стилями Telegram Bot API (primary, success, danger).
"""

import time
import random
import secrets
import html
import logging
from typing import Dict, Any, Optional

from aiogram import Router, F, Bot
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

import db
import utils

logger = logging.getLogger(__name__)
router = Router()

# ==============================================================================
# 👑 ПРЕМИУМ ЭМОДЗИ (ДЛЯ ТЕКСТА СООБЩЕНИЙ)
# ==============================================================================
PE_SWORDS    = '<tg-emoji emoji-id="5382239087321172481">⚔️</tg-emoji>'
PE_BOMB      = '<tg-emoji emoji-id="5249496324105062810">💣</tg-emoji>'
PE_GEM       = '<tg-emoji emoji-id="5467403607286502523">💎</tg-emoji>'
PE_MONEY     = '<tg-emoji emoji-id="5990147899403539264">💰</tg-emoji>'
PE_TROPHY    = '<tg-emoji emoji-id="5429463966432643712">🏆</tg-emoji>'
PE_USER      = '<tg-emoji emoji-id="5350612670435313545">👤</tg-emoji>'
PE_FIRE      = '<tg-emoji emoji-id="5429463966432643712">🔥</tg-emoji>'
PE_BOOM      = '<tg-emoji emoji-id="5465665476971471368">💥</tg-emoji>'
PE_SKULL     = '<tg-emoji emoji-id="5465665476971471368">💀</tg-emoji>'
PE_PARTY     = '<tg-emoji emoji-id="5989848973974704652">🎉</tg-emoji>'
PE_CARD      = '<tg-emoji emoji-id="6280364500361155698">💳</tg-emoji>'
PE_CHECK     = '<tg-emoji emoji-id="5805523262691611326">✅</tg-emoji>'
PE_CROSS     = '<tg-emoji emoji-id="5465665476971471368">❌</tg-emoji>'
PE_INFO      = '<tg-emoji emoji-id="5469956488351025557">ℹ️</tg-emoji>'
PE_CASH      = '<tg-emoji emoji-id="5453901475648390219">💵</tg-emoji>'

# Ограничения режима
MAX_PVP_BET = 25_000_000   # Максимальная ставка: 25кк nCoin
MIN_PVP_BET = 100          # Минимальная ставка: 100 nCoin
GRID_SIZE = 25             # 5x5
FEE_PERCENT = 0.03         # 3% комиссия проекта

# Оперативная память активных дуэлей: {duel_id: duel_data}
ACTIVE_DUELS: Dict[str, Dict[str, Any]] = {}


def fnum(number: int | float) -> str:
    """Красивое форматирование чисел с апострофом: 100000 -> 100'000"""
    return f"{int(number):,}".replace(",", "'")


def generate_pvp_board(mines_count: int) -> list:
    """Генерирует поле 5x5 (25 клеток). True = Мина, False = Кристалл."""
    board = [False] * GRID_SIZE
    mine_indices = random.sample(range(GRID_SIZE), mines_count)
    for idx in mine_indices:
        board[idx] = True
    return board


async def safe_edit_duel_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
):
    """
    Безопасное универсальное редактирование сообщения дуэли.
    Поддерживает как inline-сообщения (отправленные через Inline Query),
    так и обычные сообщения в чатах и ЛС.
    """
    try:
        if callback.inline_message_id:
            await callback.bot.edit_message_text(
                text=text,
                inline_message_id=callback.inline_message_id,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        elif callback.message:
            await callback.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения PvP дуэли: {e}")


def build_pvp_keyboard(duel: dict) -> InlineKeyboardMarkup:
    """
    Генерирует инлайн-клавиатуру 5x5.
    - В кнопках используются обычные эмодзи и цветные стили.
    - Во время игры нетронутые клетки имеют цветной стиль primary (синий).
    - Открытые кристаллы — success (зелёный).
    - Взорванная мина — danger (красный).
    """
    duel_id = duel["id"]
    status = duel["status"]
    opened = duel["opened"]
    board = duel["board"]
    exploded_idx = duel.get("exploded_idx", None)

    rows = []
    for r in range(5):
        row_btns = []
        for c in range(5):
            idx = r * 5 + c

            if status == "playing":
                if idx in opened:
                    # Уже открытая безопасная клетка
                    row_btns.append(InlineKeyboardButton(
                        text="💎",
                        callback_data="pvp_noop",
                        style="success"
                    ))
                else:
                    # Закрытая активная клетка
                    row_btns.append(InlineKeyboardButton(
                        text="❓",
                        callback_data=f"pvp_step:{duel_id}:{idx}",
                        style="primary"
                    ))

            elif status in ("finished", "cancelled"):
                # Игра окончена — вскрываем поле полностью
                if idx == exploded_idx:
                    row_btns.append(InlineKeyboardButton(
                        text="💥",
                        callback_data="pvp_noop",
                        style="danger"
                    ))
                elif board and len(board) > idx and board[idx]:
                    row_btns.append(InlineKeyboardButton(
                        text="💣",
                        callback_data="pvp_noop",
                        style="danger"
                    ))
                else:
                    row_btns.append(InlineKeyboardButton(
                        text="💎",
                        callback_data="pvp_noop",
                        style="success"
                    ))

        rows.append(row_btns)

    # Дополнительные кнопки управления под игровым полем
    if status == "waiting":
        rows = [
            [InlineKeyboardButton(
                text=f"⚔️ Принять вызов ({fnum(duel['bet'])} n¢)",
                callback_data=f"pvp_join:{duel_id}",
                style="success"
            )],
            [InlineKeyboardButton(
                text="❌ Отменить дуэль",
                callback_data=f"pvp_cancel:{duel_id}",
                style="danger"
            )]
        ]
    elif status == "finished":
        # Кнопка реванша / повтора
        bet_str = str(int(duel["bet"]))
        mines_str = str(duel["mines"])
        switch_query = f"{bet_str} {mines_str}"
        rows.append([
            InlineKeyboardButton(
                text="🔄 Бросить реванш / Новая дуэль",
                switch_inline_query=switch_query,
                style="primary"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==============================================================================
# 🎯 1. ОБРАБОТЧИК INLINE-ЗАПРОСА (@nmines_bot 20к 3)
# ==============================================================================
@router.inline_query()
async def inline_pvp_query(query: InlineQuery):
    user_id = query.from_user.id
    user = db.get_user(user_id)
    if not user:
        return

    text = query.query.strip().lower()
    parts = text.split()

    if len(parts) == 0:
        # Подсказка для игрока
        res = [
            InlineQueryResultArticle(
                id="pvp_help",
                title="⚔️ Минная Дуэль 1x1 (Поле 5x5)",
                description="Формат: @nmines_bot <ставка> <мины от 1 до 16>\nПример: @nmines_bot 20к 3",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"{PE_SWORDS} <b>МИННАЯ ДУЭЛЬ 1x1 (5x5)</b>\n\n"
                        f"{PE_INFO} <b>Как бросить вызов другу:</b>\n"
                        f"Напишите в поле ввода: <code>@{query.bot.username} 20к 3</code>\n\n"
                        f"• Первое число — ставка (от 100 до 25кк)\n"
                        f"• Второе число — количество мин на поле (от 1 до 16)"
                    ),
                    parse_mode="HTML"
                )
            )
        ]
        await query.answer(res, cache_time=1, is_personal=True)
        return

    # Парсим ставку
    bet = utils.parse_bet_input(parts[0], user["balance"])
    if bet <= 0:
        return

    # Лимиты ставки
    if bet > MAX_PVP_BET:
        bet = MAX_PVP_BET
    if bet < MIN_PVP_BET:
        bet = MIN_PVP_BET

    # Парсим количество мин (от 1 до 16, по умолчанию 3)
    mines_count = 3
    if len(parts) >= 2:
        try:
            m = int(parts[1])
            if 1 <= m <= 16:
                mines_count = m
            elif m > 16:
                mines_count = 16
            else:
                mines_count = 1
        except ValueError:
            mines_count = 3

    # Банк и комиссия
    total_bank = bet * 2
    win_pot = round(total_bank * (1.0 - FEE_PERCENT))

    duel_id = secrets.token_hex(6)
    creator_name = html.escape(query.from_user.first_name or "Игрок")

    ACTIVE_DUELS[duel_id] = {
        "id": duel_id,
        "creator_id": user_id,
        "creator_name": creator_name,
        "opponent_id": None,
        "opponent_name": None,
        "bet": bet,
        "mines": mines_count,
        "win_pot": win_pot,
        "board": [],
        "opened": [],
        "turn_user_id": None,
        "status": "waiting",
        "created_at": time.time(),
        "exploded_idx": None
    }

    duel = ACTIVE_DUELS[duel_id]

    msg_text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"│  {PE_SWORDS} <b>ВЫЗОВ НА ДУЭЛЬ!</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{PE_USER} <b>Создатель:</b> <b>{creator_name}</b>\n"
        f"{PE_MONEY} <b>Ставка с каждого:</b> <code>{fnum(bet)} n¢</code>\n"
        f"{PE_BOMB} <b>Количество мин:</b> <code>{mines_count} из 25</code> (Поле 5x5)\n"
        f"{PE_TROPHY} <b>Чистый выигрыш:</b> <code>{fnum(win_pot)} n¢</code> <i>(комиссия 3%)</i>\n\n"
        f"{PE_FIRE} <i>Тот, кто наступит на мину — теряет всё! Победитель забирает банк!</i>\n\n"
        f"👇 <b>Нажмите кнопку ниже, чтобы принять битву:</b>"
    )

    kb = build_pvp_keyboard(duel)

    res = [
        InlineQueryResultArticle(
            id=duel_id,
            title=f"⚔️ Дуэль на {fnum(bet)} n¢ ({mines_count} мин)",
            description=f"Поле 5x5 | Банк победителю: {fnum(win_pot)} n¢ (комиссия 3%)",
            input_message_content=InputTextMessageContent(
                message_text=msg_text,
                parse_mode="HTML"
            ),
            reply_markup=kb
        )
    ]

    await query.answer(res, cache_time=1, is_personal=True)


# ==============================================================================
# 🤝 2. ПРИНЯТИЕ ДУЭЛИ ВТОРИМ ИГРОКОМ
# ==============================================================================
@router.callback_query(F.data.startswith("pvp_join:"))
async def pvp_join_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    duel_id = parts[1]
    duel = ACTIVE_DUELS.get(duel_id)

    if not duel:
        return await callback.answer("❌ Дуэль устарела или уже завершена.", show_alert=True)

    if duel["status"] != "waiting":
        return await callback.answer("❌ Эта игра уже начата или отменена.", show_alert=True)

    joiner_id = callback.from_user.id
    if joiner_id == duel["creator_id"]:
        return await callback.answer("❌ Вы не можете принять собственный вызов! Подождите соперника.", show_alert=True)

    # Проверка баланса создателя
    creator = db.get_user(duel["creator_id"])
    if not creator or creator["balance"] < duel["bet"]:
        del ACTIVE_DUELS[duel_id]
        return await callback.answer("❌ У создателя дуэли недостаточно nCoin на балансе!", show_alert=True)

    # Проверка баланса оппонента
    joiner = db.get_user(joiner_id)
    if not joiner or joiner["balance"] < duel["bet"]:
        return await callback.answer(f"❌ У вас недостаточно nCoin! Нужно: {fnum(duel['bet'])} n¢", show_alert=True)

    # Списание ставок с обоих игроков
    db.update_balance(duel["creator_id"], -duel["bet"])
    db.update_balance(joiner_id, -duel["bet"])

    # Заполнение данных игры
    joiner_name = html.escape(callback.from_user.first_name or "Соперник")
    duel["opponent_id"] = joiner_id
    duel["opponent_name"] = joiner_name
    duel["status"] = "playing"
    duel["board"] = generate_pvp_board(duel["mines"])
    duel["opened"] = []

    # Случайный выбор первого хода
    duel["turn_user_id"] = random.choice([duel["creator_id"], joiner_id])
    turn_name = duel["creator_name"] if duel["turn_user_id"] == duel["creator_id"] else duel["opponent_name"]

    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"│  {PE_SWORDS} <b>ИГРА НАЧАЛАСЬ!</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"🔴 {PE_USER} <b>{duel['creator_name']}</b> ⚔️ <b>{duel['opponent_name']}</b> {PE_USER} 🔵\n"
        f"{PE_BOMB} <b>Мин на поле:</b> <code>{duel['mines']} шт.</code>\n"
        f"{PE_TROPHY} <b>Банк победителя:</b> <code>{fnum(duel['win_pot'])} n¢</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <b>СЕЙЧАС ХОДИТ:</b> <b>{turn_name}</b>\n"
        f"{PE_FIRE} <i>Выбирайте безопасную клетку и передавайте ход сопернику!</i>"
    )

    await callback.answer("⚔️ Вызов принят! Игра началась!")
    await safe_edit_duel_message(callback, text, reply_markup=build_pvp_keyboard(duel))


# ==============================================================================
# 🎮 3. ХОД В ИГРЕ (КЛИК ПО КЛЕТКЕ 5x5)
# ==============================================================================
@router.callback_query(F.data.startswith("pvp_step:"))
async def pvp_step_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    duel_id = parts[1]
    cell_idx = int(parts[2])

    duel = ACTIVE_DUELS.get(duel_id)
    if not duel or duel["status"] != "playing":
        return await callback.answer("Игра уже завершена.")

    user_id = callback.from_user.id

    # Проверка: участник ли это игры
    if user_id not in (duel["creator_id"], duel["opponent_id"]):
        return await callback.answer("👀 Вы только наблюдатель в этой дуэли!", show_alert=True)

    # Проверка очереди хода
    if user_id != duel["turn_user_id"]:
        return await callback.answer("⏳ Сейчас ход вашего соперника! Ожидайте.", show_alert=True)

    # Проверка, не открыта ли уже эта клетка
    if cell_idx in duel["opened"]:
        return await callback.answer("Эта клетка уже открыта!")

    is_mine = duel["board"][cell_idx]
    current_user_name = duel["creator_name"] if user_id == duel["creator_id"] else duel["opponent_name"]
    other_user_id = duel["opponent_id"] if user_id == duel["creator_id"] else duel["creator_id"]
    other_user_name = duel["opponent_name"] if user_id == duel["creator_id"] else duel["creator_name"]

    # ==========================
    # 💥 ВЗРЫВ НА МИНЕ (ПРОИГРЫШ)
    # ==========================
    if is_mine:
        duel["status"] = "finished"
        duel["exploded_idx"] = cell_idx

        # Начисление выигрыша выжившему победителю
        db.update_balance(other_user_id, duel["win_pot"])

        # Статистика
        db.add_stats(other_user_id, is_lost=False, bet_amount=duel["bet"])
        db.add_stats(user_id, is_lost=True, lost_amount=duel["bet"], bet_amount=duel["bet"])

        text = (
            "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            f"│  {PE_BOOM} <b>БА-БАХ! ВЗРЫВ!</b>\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{PE_SKULL} <b>{current_user_name}</b> наступил на мину и проиграл!\n\n"
            f"{PE_PARTY} <b>ПОБЕДИТЕЛЬ:</b> <b>{other_user_name}</b> {PE_TROPHY}\n"
            f"{PE_MONEY} <b>Зачислено на баланс:</b> <code>+{fnum(duel['win_pot'])} n¢</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Комиссия проекта 3% сожжена. Поле открыто ниже:</i>"
        )

        kb = build_pvp_keyboard(duel)
        del ACTIVE_DUELS[duel_id]
        await callback.answer("💥 БА-БАХ! Вы подорвались на мине!", show_alert=True)
        return await safe_edit_duel_message(callback, text, reply_markup=kb)

    # ==========================
    # 💎 ОТКРЫТ КРИСТАЛЛ (УСПЕХ)
    # ==========================
    duel["opened"].append(cell_idx)

    # Проверка на случай, если все кристаллы на поле уже открыты
    safe_cells_total = GRID_SIZE - duel["mines"]
    if len(duel["opened"]) >= safe_cells_total:
        # Ничья (все кристаллы вскрыты, мины не задеты)
        duel["status"] = "finished"
        db.update_balance(duel["creator_id"], duel["bet"])
        db.update_balance(duel["opponent_id"], duel["bet"])

        text = (
            f"{PE_CHECK} <b>НЕВЕРОЯТНО! ВСЕ КРИСТАЛЛЫ ОТКРЫТЫ!</b>\n\n"
            f"Все безопасные клетки найдены. Объявлена боевая <b>НИЧЬЯ</b>!\n"
            f"Ставки возвращены обоим игрокам по <code>{fnum(duel['bet'])} n¢</code>."
        )
        kb = build_pvp_keyboard(duel)
        del ACTIVE_DUELS[duel_id]
        return await safe_edit_duel_message(callback, text, reply_markup=kb)

    # Передача хода сопернику
    duel["turn_user_id"] = other_user_id

    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"│  {PE_SWORDS} <b>ДУЭЛЬ НАЧАЛАСЬ!</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"🔴 <b>{duel['creator_name']}</b> ⚔️ <b>{duel['opponent_name']}</b> 🔵\n"
        f"{PE_GEM} <b>Открыто кристаллов:</b> <code>{len(duel['opened'])} / {safe_cells_total}</code>\n"
        f"{PE_BOMB} <b>Мин осталось:</b> <code>{duel['mines']} шт.</code>\n"
        f"{PE_TROPHY} <b>Банк на кону:</b> <code>{fnum(duel['win_pot'])} n¢</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{PE_CHECK} <b>{current_user_name}</b> нашёл кристалл 💎!\n"
        f"👉 <b>ТЕПЕРЬ ХОДИТ:</b> <b>{other_user_name}</b>"
    )

    await callback.answer("💎 Чисто! Вы нашли кристалл!")
    await safe_edit_duel_message(callback, text, reply_markup=build_pvp_keyboard(duel))


# ==============================================================================
# ❌ 4. ОТМЕНА ДУЭЛИ (ЕСЛИ ЕЩЁ НЕ ПРИНЯЛИ)
# ==============================================================================
@router.callback_query(F.data.startswith("pvp_cancel:"))
async def pvp_cancel_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    duel_id = parts[1]
    duel = ACTIVE_DUELS.get(duel_id)

    if not duel:
        return await callback.answer("Дуэль уже не существует.")

    if duel["status"] != "waiting":
        return await callback.answer("Нельзя отменить уже начатую дуэль!", show_alert=True)

    if callback.from_user.id != duel["creator_id"]:
        return await callback.answer("Только создатель может отменить вызов!", show_alert=True)

    duel["status"] = "cancelled"
    del ACTIVE_DUELS[duel_id]

    text = (
        f"{PE_CROSS} <b>МИННАЯ ДУЭЛЬ ОТМЕНЕНА</b>\n\n"
        f"Создатель <b>{duel['creator_name']}</b> отозвал свой вызов на <code>{fnum(duel['bet'])} n¢</code>."
    )
    await callback.answer("Вызов отменён.")
    await safe_edit_duel_message(callback, text)


@router.callback_query(F.data == "pvp_noop")
async def pvp_noop_callback(callback: CallbackQuery):
    await callback.answer()
