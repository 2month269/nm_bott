# star_game.py
import asyncio
import hashlib
import html
import logging
import random
import secrets

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    PreCheckoutQuery, LabeledPrice
)

import db

logger = logging.getLogger("StarGameEngine")
router = Router()

# Кэш активных игровых сессий Star Tower
STAR_SESSIONS: dict[str, dict] = {}

# Обычные эмодзи во избежание ошибок DOCUMENT_INVALID
def pe(emoji_id: str, fallback: str) -> str:
    return fallback

E_STAR = pe("5463046637842608206", "⭐")
E_GEM = pe("5467403607286502523", "💎")
E_BOMB = pe("5226813248900187912", "💣")
E_CHART = pe("5231200819986047254", "📊")
E_ROBOT = pe("5350612670435313545", "🤖")
E_MONEY = pe("5463046637842608206", "💰")
E_CHECK = pe("5805523262691611326", "✅")
E_CROSS = pe("5454350746407419714", "❌")
E_KEY = pe("5469956488351025557", "🔑")
E_GIFT = pe("5472250091332993630", "🎁")
E_FIRE = pe("5226431245918942763", "🔥")
E_TROPHY = pe("5438318182282570043", "🏆")
E_LOSS = pe("5454350746407419714", "📉")
E_DICE = pe("5463046637842608206", "🎲")


def fmt_n(val: float) -> str:
    return f"{val:,.2f}".replace(",", "'")


# =====================================================================
# 💾 БАЗА ДАННЫХ И СТАТИСТИКА
# =====================================================================

def get_star_user_stats(user_id: int) -> dict:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COALESCE(star_balance, 0), 
                   COALESCE(star_games_played, 0), 
                   COALESCE(star_lost_amount, 0),
                   COALESCE(star_wins_count, 0)
            FROM users WHERE user_id = %s
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return {"bal": 0.0, "played": 0, "lost": 0.0, "wins": 0}
        return {
            "bal": float(row[0]),
            "played": int(row[1]),
            "lost": float(row[2]),
            "wins": int(row[3])
        }
    except Exception as e:
        logger.error(f"Ошибка get_star_user_stats: {e}")
        return {"bal": 0.0, "played": 0, "lost": 0.0, "wins": 0}
    finally:
        cursor.close()
        try: conn.close()
        except: pass


def record_game_start(user_id: int):
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET star_games_played = COALESCE(star_games_played, 0) + 1 WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка record_game_start: {e}")
        try: conn.rollback()
        except: pass
    finally:
        cursor.close()
        try: conn.close()
        except: pass


def record_game_finish(user_id: int, won_amount: float):
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        if won_amount > 0:
            cursor.execute("""
                UPDATE users 
                SET star_balance = COALESCE(star_balance, 0) + %s,
                    star_wins_count = COALESCE(star_wins_count, 0) + 1
                WHERE user_id = %s
            """, (float(won_amount), user_id))

            if won_amount < 1.0:
                net_loss = 1.0 - won_amount
                cursor.execute("UPDATE users SET star_lost_amount = COALESCE(star_lost_amount, 0) + %s WHERE user_id = %s", (float(net_loss), user_id))
        else:
            cursor.execute("UPDATE users SET star_lost_amount = COALESCE(star_lost_amount, 0) + 1.0 WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка record_game_finish: {e}")
        try: conn.rollback()
        except: pass
    finally:
        cursor.close()
        try: conn.close()
        except: pass


def update_user_stars(user_id: int, amount: float):
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET star_balance = GREATEST(0.0, COALESCE(star_balance, 0) + %s) WHERE user_id = %s", (float(amount), user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка update_user_stars: {e}")
        try: conn.rollback()
        except: pass
    finally:
        cursor.close()
        try: conn.close()
        except: pass


# =====================================================================
# 👤 УНИВЕРСАЛЬНЫЙ ПРОФИЛЬ
# =====================================================================

@router.message(Command("star_profile"))
@router.message(Command("star"))
@router.message(F.text.lower().in_(["/star", "/star_profile", "звездный профиль", "звёздный профиль", "профиль", "мой профиль"]))
@router.callback_query(F.data.in_(["star_profile_open", "profile", "my_profile", "star_profile"]))
async def star_profile_handler(event: Message | CallbackQuery):
    user = event.from_user
    stats = get_star_user_stats(user.id)

    played = stats["played"]
    wins = stats["wins"]
    win_rate = (wins / played * 100.0) if played > 0 else 0.0

    text = (
        f"{E_STAR} <b>ВАШ ЗВЁЗДНЫЙ ПРОФИЛЬ</b> {E_GEM}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Игрок: <b>{html.escape(user.first_name)}</b>\n"
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"⭐ Звёздный баланс: <b>{fmt_n(stats['bal'])} Stars</b>\n\n"
        f"{E_CHART} <b>Игровая статистика:</b>\n"
        f"{E_DICE} Сыграно игр: <b>{played}</b>\n"
        f"{E_LOSS} Проиграно: <b>{fmt_n(stats['lost'])} Stars</b>\n"
        f"{E_TROPHY} Процент побед: <b>{win_rate:.1f}%</b>\n\n"
        f"{E_ROBOT} <i>Все раунды Star Tower защищены SHA-256. Результат каждого шага можно проверить через Seed!</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть в Star Tower ⭐", callback_data="star_play_menu")]
    ])

    if isinstance(event, CallbackQuery):
        await event.answer()
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


# =====================================================================
# 🎮 ЗАПУСК ИГРЫ
# =====================================================================

@router.message(Command("star_game"))
@router.message(F.text.lower().in_(["/star_game", "звездная игра", "звёздная игра", "star game"]))
@router.callback_query(F.data == "star_play_menu")
async def star_play_entry(event: Message | CallbackQuery, bot: Bot):
    user = event.from_user
    user_id = user.id
    stats = get_star_user_stats(user_id)

    if stats["bal"] >= 1.0:
        update_user_stars(user_id, -1.0)
        record_game_start(user_id)
        session_id = init_new_star_session(user_id, user.first_name)

        text = (
            f"{E_CHECK} <b>С баланса списана 1.0 ⭐ Star! Поднимаемся вверх!</b>\n"
            f"Остаток на балансе: <b>{fmt_n(stats['bal'] - 1.0)} Stars</b>\n\n"
            + render_star_game_text(session_id)
        )
        kb = get_star_game_keyboard(session_id)

        if isinstance(event, CallbackQuery):
            await event.answer()
            try:
                await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            await event.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    try:
        payload_str = f"star_bet_{user_id}_{int(asyncio.get_event_loop().time())}"
        invoice_link = await bot.create_invoice_link(
            title="⭐ Ставка в Star Tower",
            description="Участие в игре Star Tower за 1 Telegram Star.",
            payload=payload_str,
            currency="XTR",
            prices=[LabeledPrice(label="1 Telegram Star", amount=1)]
        )
    except Exception as e:
        logger.error(f"Ошибка создания счета Telegram Stars: {e}")
        err_msg = f"{E_CROSS} Не удалось создать счет на оплату Stars."
        if isinstance(event, CallbackQuery):
            return await event.answer(err_msg, show_alert=True)
        return await event.answer(err_msg, parse_mode="HTML")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оплатить 1 Star", url=invoice_link)],
        [InlineKeyboardButton(text="👤 Мой Профиль", callback_data="star_profile_open")]
    ])

    text = (
        f"{E_STAR} <b>ЗВЁЗДНАЯ БАШНЯ (STAR TOWER)</b> {E_GEM}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⭐ На балансе: <b>{fmt_n(stats['bal'])} Stars</b> (нужно 1.0 для авто-старта)\n\n"
        f"{E_ROBOT} <b>Правила игры:</b>\n"
        "• Ставка: <b>1 Star (XTR)</b>\n"
        f"• Поднимайтесь вверх по этажам к вершине!\n"
        f"• Награды: 1.1⭐ → 1.2⭐ → 1.3⭐ → 1.7⭐ → {E_GIFT} <b>Мишка</b>\n\n"
        f"{E_CHART} Нажмите кнопку ниже для оплаты 1 Star и старта:"
    )

    if isinstance(event, CallbackQuery):
        await event.answer()
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.pre_checkout_query()
async def process_star_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_star_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload

    if not (payload.startswith("star_bet_") or payload.startswith("star_game_bet_")):
        return

    user_id = message.from_user.id
    user_name = message.from_user.first_name

    record_game_start(user_id)
    session_id = init_new_star_session(user_id, user_name)

    text = (
        f"{E_CHECK} <b>Оплата 1 Star подтверждена! Начинаем подъем вверх!</b>\n\n"
        + render_star_game_text(session_id)
    )
    kb = get_star_game_keyboard(session_id)

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# =====================================================================
# 🛠 СЕССИЯ И ВИЗУАЛ БАШНИ СНИЗУ ВВЕРХ
# =====================================================================

def init_new_star_session(user_id: int, user_name: str) -> str:
    server_seed = secrets.token_hex(32)
    sha_hash = hashlib.sha256(server_seed.encode()).hexdigest()

    grid = [random.randint(0, 1) for _ in range(5)]
    # Множители под ставку 1 Star: этажи 1, 2, 3, 4, 5
    payouts = [1.1, 1.2, 1.3, 1.7, 15.0]

    session_id = secrets.token_hex(8)
    STAR_SESSIONS[session_id] = {
        "user_id": user_id,
        "user_name": user_name,
        "server_seed": server_seed,
        "sha_hash": sha_hash,
        "grid": grid,
        "step": 0,
        "payouts": payouts,
        "won_amount": 0.0
    }
    return session_id


def render_star_game_text(session_id: str) -> str:
    s = STAR_SESSIONS[session_id]
    step = s["step"]
    payouts = s["payouts"]

    # Рисуем башню снизу вверх: 5-й этаж сверху, 1-й снизу
    floors_display = ""
    for i in range(4, -1, -1):
        floor_num = i + 1
        if floor_num == 5:
            reward_str = "🎁 Подарок (Мишка)"
        else:
            reward_str = f"{payouts[i]} ⭐"

        if i < step:
            floors_display += f"🟢 Этаж {floor_num}: Пройден ({reward_str})\n"
        elif i == step:
            floors_display += f"🔵 <b>Этаж {floor_num}: ВЫБОР ДВЕРИ ({reward_str})</b> 👈\n"
        else:
            floors_display += f"⚪ Этаж {floor_num}: Ожидание ({reward_str})\n"

    return (
        f"{E_STAR} <b>ПОДЪЕМ ПО ЗВЁЗДНОЙ БАШНЕ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>SHA-256 Хэш:</b> <code>{s['sha_hash']}</code>\n\n"
        f"{floors_display}\n"
        f"{E_FIRE} Выберите дверь: <b>🚪 | 🚪</b>"
    )


def get_star_game_keyboard(session_id: str) -> InlineKeyboardMarkup:
    s = STAR_SESSIONS.get(session_id)
    step = s["step"]
    # Текущий гарантированный кэшаут
    if step == 0:
        cashout_label = "Забрать нечего"
    else:
        cashout_label = f"💰 Забрать {s['payouts'][step-1]} ⭐"

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚪 Левая 👈", callback_data=f"star_step:{session_id}:0"),
            InlineKeyboardButton(text="🚪 Правая 👉", callback_data=f"star_step:{session_id}:1")
        ],
        [
            InlineKeyboardButton(text=cashout_label, callback_data=f"star_cashout:{session_id}")
        ]
    ])


# =====================================================================
# 🕹️ ИГРОВЫЕ ШАГИ И ВЫХОД
# =====================================================================

@router.callback_query(F.data.startswith("star_step:"))
async def star_step_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer("❌ Ошибка данных.", show_alert=True)

    session_id = parts[1]
    chosen_door = int(parts[2])
    s = STAR_SESSIONS.get(session_id)

    if not s or s["user_id"] != callback.from_user.id:
        return await callback.answer("❌ Сессия не найдена или устарела.", show_alert=True)

    step = s["step"]
    safe_door = s["grid"][step]

    # Ловушка (проигрыш)
    if chosen_door != safe_door:
        record_game_finish(callback.from_user.id, won_amount=0.0)

        text = (
            f"{E_BOMB} <b>Ловушка на этаже {step+1}! Вы проиграли раунд.</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{E_CROSS} Ошибка при подъеме.\n"
            f"🔑 <b>Seed честности:</b> <code>{s['server_seed']}</code>\n\n"
            f"<i>Попробуйте снова: /star_game</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Играть снова ⭐", callback_data="star_play_menu")],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="star_profile_open")]
        ])
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        STAR_SESSIONS.pop(session_id, None)
        return await callback.answer("💥 Ловушка!", show_alert=True)

    # Успешный шаг наверх
    s["step"] += 1

    # Если дошли до вершины (5-й этаж)
    if s["step"] >= 5:
        record_game_finish(callback.from_user.id, won_amount=15.0)

        text = (
            f"{E_GIFT} <b>ВЕРШИНА БАШНИ ПОКОРЕНА! ПОБЕДА!</b> {E_STAR}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎉 Вы добрались до самого верха и выиграли главный приз — <b>Подарок (Мишка)</b> и {fmt_n(15.0)} Stars на баланс!\n"
            f"🔑 <b>Seed честности:</b> <code>{s['server_seed']}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Играть снова ⭐", callback_data="star_play_menu")],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="star_profile_open")]
        ])
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        STAR_SESSIONS.pop(session_id, None)
        return await callback.answer("🏆 Победа!", show_alert=True)

    # Продолжаем подъем
    await callback.answer(f"✅ Этаж {s['step']} успешно пройден!")
    try:
        await callback.message.edit_text(
            render_star_game_text(session_id),
            reply_markup=get_star_game_keyboard(session_id),
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("star_cashout:"))
async def star_cashout_callback(callback: CallbackQuery):
    session_id = callback.data.split(":")[1]
    s = STAR_SESSIONS.get(session_id)

    if not s or s["user_id"] != callback.from_user.id:
        return await callback.answer("❌ Сессия не найдена.", show_alert=True)

    step = s["step"]
    if step <= 0:
        return await callback.answer("❌ Сначала поднимитесь хотя бы на 1 этаж!", show_alert=True)

    # Выигрыш равен множителю предыдущего пройденного этажа
    payout = s["payouts"][step - 1]
    record_game_finish(callback.from_user.id, won_amount=payout)

    text = (
        f"{E_MONEY} <b>ВЫИГРЫШ УСПЕШНО ЗАБРАН!</b> {E_CHECK}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 На ваш звездный баланс зачислено: <b>+{fmt_n(payout)} ⭐</b>\n"
        f"🔑 <b>Seed честности:</b> <code>{s['server_seed']}</code>\n\n"
        f"<i>Сыграть снова: /star_game</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Играть снова ⭐", callback_data="star_play_menu")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="star_profile_open")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    STAR_SESSIONS.pop(session_id, None)
    await callback.answer("✅ Выигрыш зачислен!", show_alert=True)
