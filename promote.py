# promote.py
import re
import time
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db

logger = logging.getLogger(__name__)
router = Router()

# ==============================================================================
# 💎 ЭМОДЗИ ДЛЯ ИНТЕРФЕЙСА (Премиум-эмодзи)
# ==============================================================================
PROMOTE_EMOJIS = {
    "user": '<tg-emoji emoji-id="5256143829672672750">👤</tg-emoji>',
    "warning": '<tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji>',
    "gem": '<tg-emoji emoji-id="5767137507879685567">💎</tg-emoji>',
    "megaphone": '<tg-emoji emoji-id="5424818078833715060">📣</tg-emoji>',
    "chat": '<tg-emoji emoji-id="5443038326535759644">💬</tg-emoji>',
    "green_dot": '<tg-emoji emoji-id="5215522595922779944">🟢</tg-emoji>',
    "red_dot": '<tg-emoji emoji-id="5398038979217989221">🔴</tg-emoji>',
    "cross": '<tg-emoji emoji-id="5454350746407419714">❌</tg-emoji>',
    "check": '<tg-emoji emoji-id="5805523262691611326">✔️</tg-emoji>',
    "book": '<tg-emoji emoji-id="5222444124698853913">📕</tg-emoji>',
    "info": '<tg-emoji emoji-id="5258503720928288433">ℹ️</tg-emoji>',
    "top": '<tg-emoji emoji-id="5463071033256848094">🔝</tg-emoji>',
    "eyes": '<tg-emoji emoji-id="5228822494730797152">👀</tg-emoji>',
    "users": '<tg-emoji emoji-id="5453957997418004470">👥</tg-emoji>',
    "couple": '<tg-emoji emoji-id="5226929552319594190">🧑‍🤝‍🧑</tg-emoji>',
    "gear": '<tg-emoji emoji-id="5341715473882955310">⚙️</tg-emoji>',
    "money": '<tg-emoji emoji-id="5463046637842608206">💰</tg-emoji>',
    "page": '<tg-emoji emoji-id="5431548685198751433">📄</tg-emoji>'
}

SPEED_TIERS = {
    "tier_standard": {
        "name": "🐢 Стандартная",
        "desc": "Награда исполнителю: 1 NMP",
        "price": 1,
        "badge": "Обычный поток"
    },
    "tier_fast": {
        "name": "⚡️ Быстрая",
        "desc": "Награда исполнителю: 3 NMP",
        "price": 3,
        "badge": "Приоритет 2х"
    },
    "tier_turbo": {
        "name": "🚀 Турбо (Максимум)",
        "desc": "Награда исполнителю: 5 NMP",
        "price": 5,
        "badge": "Топ Приоритет 🔥"
    }
}

MIN_SUBS = 10  # Минимальный заказ

class PromoteState(StatesGroup):
    waiting_for_channel = State()
    waiting_for_tier = State()
    waiting_for_quantity = State()
    waiting_for_confirm = State()
    waiting_for_page = State()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ И ПРОВЕРКИ БАНОВ/ПОДПИСОК ---

def init_promote_db():
    """Создает таблицы заказов, выполнения заданий, контроля отписок и банов"""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promote_orders (
                order_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                channel_username VARCHAR(255) NOT NULL,
                target_subs INT NOT NULL,
                current_subs INT DEFAULT 0,
                price_per_sub INT NOT NULL,
                total_price DOUBLE PRECISION NOT NULL,
                speed_name VARCHAR(50) NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promote_claims (
                order_id INT NOT NULL,
                user_id BIGINT NOT NULL,
                reward_nmp DOUBLE PRECISION NOT NULL,
                claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (order_id, user_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promote_unsub_grace (
                user_id BIGINT NOT NULL,
                order_id INT NOT NULL,
                channel_username VARCHAR(255) NOT NULL,
                reward_nmp DOUBLE PRECISION NOT NULL,
                unsub_detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                grace_until TIMESTAMP NOT NULL,
                status VARCHAR(20) DEFAULT 'grace',
                PRIMARY KEY (user_id, order_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS promote_user_bans (
                user_id BIGINT PRIMARY KEY,
                banned_until TIMESTAMP NOT NULL,
                reason TEXT
            )
        """)
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка создания таблиц promote: {e}")
    finally:
        cursor.close()
        conn.close()


def is_channel_order_exists(channel_username: str) -> bool:
    """Проверяет, существует ли уже активный или приостановленный заказ на данную ссылку/юзернейм"""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        clean_name = channel_username.replace("@", "").replace("https://t.me/", "").strip().lower()
        cursor.execute("""
            SELECT 1 FROM promote_orders 
            WHERE LOWER(REPLACE(REPLACE(channel_username, '@', ''), 'https://t.me/', '')) = %s 
              AND status IN ('active', 'paused')
            LIMIT 1
        """, (clean_name,))
        return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Ошибка проверки существования заказа для {channel_username}: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def is_user_temp_banned(user_id: int) -> tuple[bool, int]:
    """Проверяет, забанен ли пользователь за отписку. Возвращает (is_banned, remaining_seconds)"""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT EXTRACT(EPOCH FROM (banned_until - CURRENT_TIMESTAMP)) 
            FROM promote_user_bans 
            WHERE user_id = %s AND banned_until > CURRENT_TIMESTAMP
        """, (user_id,))
        row = cursor.fetchone()
        if row and row[0] > 0:
            return True, int(row[0])
        return False, 0
    finally:
        cursor.close()
        conn.close()


def apply_temp_ban(user_id: int, duration_seconds: int = 7200, reason: str = "Отписка от канала раньше 5 дней"):
    """Налагает временный бан на пользователя (по умолчанию 2 часа)"""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO promote_user_bans (user_id, banned_until, reason)
            VALUES (%s, CURRENT_TIMESTAMP + INTERVAL '2 hours', %s)
            ON CONFLICT (user_id) DO UPDATE 
            SET banned_until = CURRENT_TIMESTAMP + INTERVAL '2 hours', reason = EXCLUDED.reason
        """, (user_id, reason))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


async def process_user_subscription_checks(bot: Bot, user_id: int):
    """
    Проверяет каналы, на которые пользователь подписался за последние 5 дней.
    Если пользователь отписался:
    1. Даётся 2 часа на повторную подписку.
    2. Если по истечении 2 часов пользователь не подписался обратно:
       - Выдаётся бан на 2 часа.
       - Списывается награда NMP.
    """
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        # 1. Проверяем активные льготные периоды (grace)
        cursor.execute("""
            SELECT order_id, channel_username, reward_nmp, (grace_until <= CURRENT_TIMESTAMP) AS expired
            FROM promote_unsub_grace
            WHERE user_id = %s AND status = 'grace'
        """, (user_id,))
        graces = cursor.fetchall()
        
        for g_order_id, g_channel, g_reward, is_expired in graces:
            is_subbed = False
            try:
                cm = await bot.get_chat_member(chat_id=g_channel, user_id=user_id)
                if cm.status not in ["left", "kicked"]:
                    is_subbed = True
            except Exception:
                pass
            
            if is_subbed:
                cursor.execute("""
                    UPDATE promote_unsub_grace SET status = 'resolved' 
                    WHERE user_id = %s AND order_id = %s
                """, (user_id, g_order_id))
                conn.commit()
                try:
                    await bot.send_message(user_id, f"✅ Спасибо! Подписка на {g_channel} подтверждена. Штраф отменён.", parse_mode="HTML")
                except Exception:
                    pass
            elif is_expired:
                cursor.execute("""
                    UPDATE promote_unsub_grace SET status = 'penalized' 
                    WHERE user_id = %s AND order_id = %s
                """, (user_id, g_order_id))
                conn.commit()
                
                db.update_nmp_balance(user_id, -g_reward)
                apply_temp_ban(user_id, duration_seconds=7200, reason=f"Отписка от канала {g_channel}")
                
                try:
                    await bot.send_message(
                        user_id,
                        f"⛔ <b>ВРЕМЕННЫЙ БАН НА 2 ЧАСА!</b>\n\n"
                        f"Вы не подписались обратно на канал <b>{g_channel}</b> за отведённые 2 часа.\n"
                        f"💸 Списано: <b>-{g_reward:,.0f} NMP</b>\n"
                        f"⏳ Вы заблокированы в сервисе на 2 часа.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

        # 2. Проверяем новые отписки по заказам младше 5 дней
        cursor.execute("""
            SELECT c.order_id, o.channel_username, c.reward_nmp
            FROM promote_claims c
            JOIN promote_orders o ON c.order_id = o.order_id
            WHERE c.user_id = %s 
              AND c.claimed_at >= CURRENT_TIMESTAMP - INTERVAL '5 days'
              AND NOT EXISTS (
                  SELECT 1 FROM promote_unsub_grace g 
                  WHERE g.user_id = c.user_id AND g.order_id = c.order_id
              )
        """, (user_id,))
        recent_claims = cursor.fetchall()

        for c_order_id, c_channel, c_reward in recent_claims:
            is_subbed = True
            try:
                cm = await bot.get_chat_member(chat_id=c_channel, user_id=user_id)
                if cm.status in ["left", "kicked"]:
                    is_subbed = False
            except Exception:
                pass

            if not is_subbed:
                cursor.execute("""
                    INSERT INTO promote_unsub_grace (user_id, order_id, channel_username, reward_nmp, grace_until, status)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '2 hours', 'grace')
                    ON CONFLICT (user_id, order_id) DO NOTHING
                """, (user_id, c_order_id, c_channel, c_reward))
                conn.commit()

                try:
                    await bot.send_message(
                        user_id,
                        f"⚠️ <b>ВНИМАНИЕ! Обнаружена отписка!</b>\n\n"
                        f"Вы отписались от канала <b>{c_channel}</b> раньше чем через 5 дней!\n"
                        f"⏱ У вас есть <b>2 часа</b>, чтобы подписаться заново.\n"
                        f"Если вы не подпишетесь обратно, вам будет выдан <b>бан на 2 часа</b> и списано <b>{c_reward:,.0f} NMP</b>!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Ошибка проверки отписок пользователя {user_id}: {e}")
    finally:
        cursor.close()
        conn.close()


def create_promote_order(user_id: int, channel_username: str, target_subs: int, price_per_sub: int, total_price: float, speed_name: str) -> int:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO promote_orders (user_id, channel_username, target_subs, current_subs, price_per_sub, total_price, speed_name, status)
            VALUES (%s, %s, %s, 0, %s, %s, %s, 'active')
            RETURNING order_id
        """, (user_id, channel_username, target_subs, price_per_sub, total_price, speed_name))
        order_id = cursor.fetchone()[0]
        conn.commit()
        return order_id
    finally:
        cursor.close()
        conn.close()

def get_user_promote_orders(user_id: int) -> list:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT order_id, channel_username, target_subs, current_subs, price_per_sub, total_price, speed_name, status, TO_CHAR(created_at, 'DD.MM.YYYY HH24:MI')
            FROM promote_orders WHERE user_id = %s ORDER BY order_id DESC
        """, (user_id,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "order_id": r[0], "channel_username": r[1], "target_subs": r[2], "current_subs": r[3],
                "price_per_sub": r[4], "total_price": r[5], "speed_name": r[6], "status": r[7], "created_at": r[8]
            })
        return result
    finally:
        cursor.close()
        conn.close()

def get_active_promote_orders_paginated(user_id: int, page: int = 1, per_page: int = 5) -> tuple[list, int]:
    """Возвращает список доступных заданий с пагинацией (по 5 штук) и общее количество страниц"""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        offset = (page - 1) * per_page
        
        cursor.execute("""
            SELECT COUNT(*) FROM promote_orders o
            WHERE o.status = 'active' 
              AND o.current_subs < o.target_subs
              AND o.user_id != %s
              AND NOT EXISTS (
                  SELECT 1 FROM promote_claims c 
                  WHERE c.order_id = o.order_id AND c.user_id = %s
              )
        """, (user_id, user_id))
        total_count = cursor.fetchone()[0] or 0
        total_pages = max(1, (total_count + per_page - 1) // per_page)

        cursor.execute("""
            SELECT o.order_id, o.channel_username, o.target_subs, o.current_subs, o.price_per_sub, o.speed_name
            FROM promote_orders o
            WHERE o.status = 'active' 
              AND o.current_subs < o.target_subs
              AND o.user_id != %s
              AND NOT EXISTS (
                  SELECT 1 FROM promote_claims c 
                  WHERE c.order_id = o.order_id AND c.user_id = %s
              )
            ORDER BY o.price_per_sub DESC, o.order_id ASC
            LIMIT %s OFFSET %s
        """, (user_id, user_id, per_page, offset))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "order_id": r[0], "channel_username": r[1], "target_subs": r[2],
                "current_subs": r[3], "price_per_sub": r[4], "speed_name": r[5]
            })
        return result, total_pages
    finally:
        cursor.close()
        conn.close()

def get_completed_promote_stats(user_id: int) -> dict:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COALESCE(SUM(current_subs), 0), COALESCE(SUM(target_subs), 0)
            FROM promote_orders WHERE user_id = %s
        """, (user_id,))
        row = cursor.fetchone()
        return {"inventions": row[0], "subscribers": row[1]}
    finally:
        cursor.close()
        conn.close()

def get_promote_order_by_id(order_id: int) -> dict:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT order_id, user_id, channel_username, target_subs, current_subs, price_per_sub, total_price, speed_name, status, TO_CHAR(created_at, 'DD.MM.YYYY HH24:MI')
            FROM promote_orders WHERE order_id = %s
        """, (order_id,))
        r = cursor.fetchone()
        if not r: return None
        return {
            "order_id": r[0], "user_id": r[1], "channel_username": r[2], "target_subs": r[3],
            "current_subs": r[4], "price_per_sub": r[5], "total_price": r[6], "speed_name": r[7],
            "status": r[8], "created_at": r[9]
        }
    finally:
        cursor.close()
        conn.close()

def update_promote_order_status(order_id: int, new_status: str):
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE promote_orders SET status = %s WHERE order_id = %s", (new_status, order_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def delete_promote_order(order_id: int):
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM promote_claims WHERE order_id = %s", (order_id,))
        cursor.execute("DELETE FROM promote_orders WHERE order_id = %s", (order_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def register_promote_claim(order_id: int, user_id: int, reward_nmp: float) -> bool:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO promote_claims (order_id, user_id, reward_nmp) VALUES (%s, %s, %s)", (order_id, user_id, reward_nmp))
        cursor.execute("""
            UPDATE promote_orders 
            SET current_subs = current_subs + 1 
            WHERE order_id = %s
        """, (order_id,))

        cursor.execute("SELECT current_subs, target_subs FROM promote_orders WHERE order_id = %s", (order_id,))
        curr, targ = cursor.fetchone()
        if curr >= targ:
            cursor.execute("UPDATE promote_orders SET status = 'completed' WHERE order_id = %s", (order_id,))

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка регистрации выполнения задания: {e}")
        try: conn.rollback()
        except: pass
        return False
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# 📱 ГЛАВНОЕ МЕНЮ РЕКЛАМЫ
# ==============================================================================

@router.message(StateFilter(None), Command("promote"))
@router.message(StateFilter(None), F.text.lower().in_(["реклама", "продвижение", "раскрутка", "пиар", "задания"]))
@router.callback_query(F.data == "promote_main_menu")
async def promote_main_cmd(event, bot: Bot, state: FSMContext = None):
    if state: await state.clear()
    init_promote_db()
    
    user_id = event.from_user.id

    is_banned, rem_sec = is_user_temp_banned(user_id)
    if is_banned:
        hrs = rem_sec // 3600
        mins = (rem_sec % 3600) // 60
        secs = rem_sec % 60
        time_str = f"{hrs}ч {mins}м {secs}с" if hrs > 0 else f"{mins}м {secs}с"
        msg = f"⛔ <b>Доступ заблокирован!</b>\n\nВы получили временный бан на 2 часа за отписку от канала раньше 5 дней.\nДо окончания бана осталось: <b>{time_str}</b>"
        if isinstance(event, Message):
            return await event.answer(msg, parse_mode="HTML")
        else:
            await event.answer("⛔ Вы заблокированы на 2 часа за отписку!", show_alert=True)
            return

    await process_user_subscription_checks(bot, user_id)

    user = db.get_user(user_id)
    user_nmp = user.get("nmp_balance", 0)
    user_name = event.from_user.first_name

    text = (
        f"{PROMOTE_EMOJIS['gear']} {user_name}, что ты хочешь рекламировать?\n"
        "---------------------------------------\n"
        f"{PROMOTE_EMOJIS['warning']} Обязательно прочитай правила перед добавлением задания!\n"
        "---------------------------------------\n"
        f"{PROMOTE_EMOJIS['gem']} Баланс: {int(user_nmp):,} NMPOINT"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Продвигать канал", callback_data="promote_create_channel", style="primary")],
        [InlineKeyboardButton(text="💬 Продвигать чат/группу", callback_data="promote_create_chat", style="primary")],
        [InlineKeyboardButton(text="🎯 Задания (Заработать NMP)", callback_data="promote_tasks_page:1", style="success")],
        [InlineKeyboardButton(text="🟢 Активные", callback_data="promote_active_list", style="primary")],
        [
            InlineKeyboardButton(text="✔️ Завершённые", callback_data="promote_completed_stats", style="primary"),
            InlineKeyboardButton(text="📕 ПРАВИЛА ❗️", callback_data="promote_rules", style="danger")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start", style="primary")]
    ])

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer()
        try: await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except: await event.message.answer(text, reply_markup=kb, parse_mode="HTML")


# --- ПРАВИЛА РЕКЛАМЫ ---
@router.callback_query(F.data == "promote_rules")
async def promote_rules_callback(call: CallbackQuery):
    await call.answer()
    text = (
        f"{PROMOTE_EMOJIS['book']} <b>ПРАВИЛА СЕРВИСА РЕКЛАМЫ</b>\n"
        "---------------------------------------\n"
        "1. Запрещено рекламировать каналы с 18+, казино, мошенническими схемами и оскорблениями.\n"
        "2. Бот должен быть администратором канала/чата с правом постинга и приглашения.\n"
        "3. При отмене заказа невыплаченный остаток NMPOINT автоматически возвращается на ваш баланс.\n"
        "4. <b>Внимание:</b> за отписку от канала ранее 5 дней даётся 2 часа на повторную подписку. "
        "Если не подписаться обратно, следует <b>временный бан на 2 часа</b> и <b>списание полученных NMP</b>!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="promote_main_menu", style="primary")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ==============================================================================
# 📱 СПИСОК ЗАДАНИЙ ДЛЯ ЗАРАБОТКА (С ПАГИНАЦИЕЙ ПО 5 ШТУК И ВВОДОМ СТРАНИЦЫ)
# ==============================================================================

@router.callback_query(F.data.startswith("promote_tasks_page:"))
async def show_promote_tasks_list(call: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = call.from_user.id

    is_banned, rem_sec = is_user_temp_banned(user_id)
    if is_banned:
        await call.answer("⛔ Вы заблокированы на 2 часа за отписку!", show_alert=True)
        return

    await process_user_subscription_checks(bot, user_id)
    await call.answer()
    
    page = int(call.data.split(":")[1])
    
    tasks, total_pages = get_active_promote_orders_paginated(user_id, page=page, per_page=5)
    if page > total_pages:
        page = total_pages
        tasks, total_pages = get_active_promote_orders_paginated(user_id, page=page, per_page=5)

    user_name = call.from_user.first_name

    text = (
        f"{PROMOTE_EMOJIS['gem']} {user_name}, доступные задания для заработка:\n"
        "---------------------------------------\n"
        f"{PROMOTE_EMOJIS['info']} Подписывайтесь на каналы и получайте награду в NMP!\n\n"
        f"📄 Страница: <b>{page} из {total_pages}</b>"
    )

    buttons = []
    if not tasks:
        text += "\n\n❌ На этой странице пока нет доступных заданий."
    else:
        for t in tasks:
            ch_name = t['channel_username']
            if not ch_name.startswith("@"):
                ch_name = f"@{ch_name}"
            btn_text = f"📢 {ch_name} | +{t['price_per_sub']} NMP"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"promote_task_view:{t['order_id']}", style="primary")])

    buttons.append([InlineKeyboardButton(text=f"📄 Страница {page} (нажми для ввода)", callback_data=f"promote_tasks_input_page:{page}", style="primary")])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"promote_tasks_page:{page - 1}", style="primary"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"promote_tasks_page:{page + 1}", style="primary"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="promote_main_menu", style="primary")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("promote_tasks_input_page:"))
async def input_tasks_page_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(PromoteState.waiting_for_page)
    text = f"{PROMOTE_EMOJIS['page']} Введите номер страницы целым числом в чат:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к заданиям", callback_data="promote_tasks_page:1", style="primary")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.message(PromoteState.waiting_for_page)
async def process_tasks_page_input(message: Message, state: FSMContext, bot: Bot):
    try:
        page = int(message.text.strip())
        if page < 1:
            page = 1
    except ValueError:
        await message.reply("Введите корректное число!", parse_mode="HTML")
        return

    await state.clear()
    fake_call = CallbackQuery(id="0", from_user=message.from_user, chat_instance="0", message=message, data=f"promote_tasks_page:{page}")
    await show_promote_tasks_list(fake_call, bot, state)


# --- КАРТОЧКА ЗАДАНИЯ И ПРОВЕРКА ПОДПИСКИ ---

@router.callback_query(F.data.startswith("promote_task_view:"))
async def view_promote_task(call: CallbackQuery, state: FSMContext):
    await call.answer()
    order_id = int(call.data.split(":")[1])
    order = get_promote_order_by_id(order_id)

    if not order or order["status"] != "active" or order["current_subs"] >= order["target_subs"]:
        await call.answer("❌ Это задание больше неактивно или уже выполнено!", show_alert=True)
        fake_call = CallbackQuery(id="0", from_user=call.from_user, chat_instance="0", message=call.message, data="promote_tasks_page:1")
        await show_promote_tasks_list(fake_call, call.bot, state)
        return

    clean_channel = order["channel_username"].replace("@", "")
    channel_link = f"https://t.me/{clean_channel}"
    safe_channel = order['channel_username']

    text = (
        f"{PROMOTE_EMOJIS['gem']} <b>ЗАДАНИЕ: ПОДПИСКА НА КАНАЛ</b>\n"
        "---------------------------------------\n\n"
        f"{PROMOTE_EMOJIS['megaphone']} <b>Канал:</b> <code>{safe_channel}</code>\n"
        f"{PROMOTE_EMOJIS['money']} <b>Награда:</b> <code>+{order['price_per_sub']} NMP</code>\n\n"
        "<b>ИНСТРУКЦИЯ:</b>\n"
        "1. Перейдите по кнопке в канал ниже и <b>подпишитесь</b>.\n"
        "2. Вернитесь в бота и нажмите <b>«Проверить подписку»</b>.\n"
        "3. Бот моментально зачислит NMP на ваш баланс!\n\n"
        "⚠️ <i>Не отписывайтесь в течение 5 дней, иначе награда аннулируется и будет выдан бан на 2 часа!</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_link)],
        [InlineKeyboardButton(text="✔️ Проверить подписку", callback_data=f"promote_task_check:{order_id}", style="success")],
        [InlineKeyboardButton(text="⬅️ Назад к заданиям", callback_data="promote_tasks_page:1", style="primary")]
    ])

    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("promote_task_check:"))
async def check_promote_task(call: CallbackQuery, bot: Bot, state: FSMContext):
    order_id = int(call.data.split(":")[1])
    user_id = call.from_user.id

    is_banned, _ = is_user_temp_banned(user_id)
    if is_banned:
        await call.answer("⛔ Вы заблокированы на 2 часа за отписку!", show_alert=True)
        return

    order = get_promote_order_by_id(order_id)
    if not order or order["status"] != "active":
        await call.answer("❌ Задание неактивно!", show_alert=True)
        return

    channel_username = order["channel_username"]
    reward_nmp = float(order["price_per_sub"])

    try:
        chat_member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        if chat_member.status in ["left", "kicked"]:
            await call.answer("❌ Вы ещё не подписались на канал! Подпишитесь и нажмите проверить снова.", show_alert=True)
            return
    except Exception as e:
        logger.error(f"Ошибка проверки подписки в {channel_username}: {e}")
        pass

    success = register_promote_claim(order_id, user_id, reward_nmp)
    if not success:
        await call.answer("❌ Вы уже получали награду за этот канал!", show_alert=True)
        return

    db.update_nmp_balance(user_id, reward_nmp)
    await call.answer(f"🎉 Вы успешно подписались и получили +{reward_nmp:,.0f} NMP!", show_alert=True)

    # 1. Удаляем текущее сообщение с заданием
    try:
        await call.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с заданием: {e}")

    # 2. Формируем новое сообщение с текстом благодарности и новым списком оставшихся заданий
    page = 1
    tasks, total_pages = get_active_promote_orders_paginated(user_id, page=page, per_page=5)
    user_name = call.from_user.first_name

    text = (
        f"{PROMOTE_EMOJIS['check']} Спасибо за подписку!\n"
        "---------------------------------------\n"
        f"{PROMOTE_EMOJIS['gem']} {user_name}, доступные задания для заработка:\n"
        "---------------------------------------\n"
        f"{PROMOTE_EMOJIS['info']} Подписывайтесь на каналы и получайте награду в NMP!\n\n"
        f"📄 Страница: <b>{page} из {total_pages}</b>"
    )

    buttons = []
    if not tasks:
        text += "\n\n❌ На этой странице пока нет доступных заданий."
    else:
        for t in tasks:
            ch_name = t['channel_username']
            if not ch_name.startswith("@"):
                ch_name = f"@{ch_name}"
            btn_text = f"📢 {ch_name} | +{t['price_per_sub']} NMP"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"promote_task_view:{t['order_id']}", style="primary")])

    buttons.append([InlineKeyboardButton(text=f"📄 Страница {page} (нажми для ввода)", callback_data=f"promote_tasks_input_page:{page}", style="primary")])
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"promote_tasks_page:{page - 1}", style="primary"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"promote_tasks_page:{page + 1}", style="primary"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="promote_main_menu", style="primary")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await bot.send_message(chat_id=call.message.chat.id, text=text, reply_markup=kb, parse_mode="HTML")


# ==============================================================================
# 📱 ВЫБОР ЦЕНЫ ЗА 1 ВСТУПЛЕНИЕ
# ==============================================================================

@router.callback_query(F.data.in_(["promote_create_channel", "promote_create_chat"]))
async def promote_create_type(call: CallbackQuery, state: FSMContext):
    await call.answer()
    res_type = "канал" if "channel" in call.data else "чат"
    await state.update_data(res_type=res_type)
    
    user_name = call.from_user.first_name
    
    text = (
        f"{PROMOTE_EMOJIS['user']} {user_name}, напиши цену за 1 вступление!\n"
        "---------------------------------------\n"
        f"{PROMOTE_EMOJIS['warning']} Минимальная цена - 1 NMPOINT!\n\n"
        "<blockquote>"
        f"{PROMOTE_EMOJIS['top']} Чем выше цена за подписчика — тем выше будет в списке твое задание!"
        "</blockquote>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 NMP", callback_data="promote_price:1", style="primary"),
            InlineKeyboardButton(text="3 NMP", callback_data="promote_price:3", style="primary"),
            InlineKeyboardButton(text="5 NMP", callback_data="promote_price:5", style="success")
        ],
        [InlineKeyboardButton(text="⬅️ назад", callback_data="promote_main_menu", style="primary")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("promote_price:"))
async def promote_price_selected(call: CallbackQuery, state: FSMContext):
    await call.answer()
    price = int(call.data.split(":")[1])
    await state.update_data(price_per_sub=price)
    await state.set_state(PromoteState.waiting_for_channel)

    text = (
        f"{PROMOTE_EMOJIS['user']} Введите ссылку на ваш публичный канал/группу или `@username`:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="promote_main_menu", style="primary")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.message(PromoteState.waiting_for_channel)
async def process_channel_link(message: Message, state: FSMContext):
    raw = message.text.strip()
    clean = raw.replace("https://t.me/", "").replace("@", "").strip().split("/")[0]

    if not clean or not re.match(r'^[a-zA-Z0-9_]+$', clean):
        await message.reply(f"{PROMOTE_EMOJIS['cross']} Некорректный username. Попробуйте снова:", parse_mode="HTML")
        return

    channel_username = f"@{clean}"

    # Проверка на наличие уже существующего активного заказа на данный канал/чат
    if is_channel_order_exists(channel_username):
        await message.reply(f"{PROMOTE_EMOJIS['cross']} Задание для данного канала/чата уже выставлено и находится в списке!", parse_mode="HTML")
        return

    await state.update_data(channel_username=channel_username)
    await state.set_state(PromoteState.waiting_for_quantity)

    text = f"{PROMOTE_EMOJIS['user']} Укажите количество подписчиков (минимум {MIN_SUBS}):"
    await message.reply(text, parse_mode="HTML")


@router.message(PromoteState.waiting_for_quantity)
async def process_quantity_input(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        if qty < MIN_SUBS:
            await message.reply(f"Минимум {MIN_SUBS} подписчиков!", parse_mode="HTML")
            return
        
        data = await state.get_data()
        total_price = qty * data["price_per_sub"]
        
        user = db.get_user(message.from_user.id)
        if user.get("nmp_balance", 0) < total_price:
            await message.reply(f"{PROMOTE_EMOJIS['cross']} Недостаточно NMP на балансе!", parse_mode="HTML")
            return

        db.update_nmp_balance(message.from_user.id, -total_price)
        order_id = create_promote_order(
            message.from_user.id, 
            data["channel_username"], 
            qty, 
            data["price_per_sub"], 
            total_price, 
            data["res_type"]
        )
        await state.clear()

        bot_info = await message.bot.get_me()
        admin_url = f"https://t.me/{bot_info.username}?startchannel=bot&admin=post_messages+invite_users"

        text = (
            f"🎉 Заказ #{order_id} для {data['channel_username']} успешно запущен!\n\n"
            f"⚠️ Обязательно добавьте бота в администраторы канала/чата с правом приглашения пользователей!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Добавить в админы", url=admin_url)],
            [InlineKeyboardButton(text="🏠 В меню рекламы", callback_data="promote_main_menu", style="primary")]
        ])
        await message.reply(text, reply_markup=kb, parse_mode="HTML")

    except ValueError:
        await message.reply("Введите число!", parse_mode="HTML")


# ==============================================================================
# 📱 АКТИВНЫЕ ЗАДАЧИ
# ==============================================================================

@router.callback_query(F.data == "promote_active_list")
async def promote_active_list_callback(call: CallbackQuery):
    await call.answer()
    user_name = call.from_user.first_name
    orders = get_user_promote_orders(call.from_user.id)
    active_orders = [o for o in orders if o["status"] in ["active", "paused"]]

    text = (
        f"{PROMOTE_EMOJIS['gear']} {user_name}, здесь можно включить и выключить задачи!\n"
        "---------------------------------------\n"
        f"{PROMOTE_EMOJIS['green_dot']} - вкл. / {PROMOTE_EMOJIS['red_dot']} - выкл. / {PROMOTE_EMOJIS['cross']} - удалить.\n\n"
        "<blockquote>"
        f"{PROMOTE_EMOJIS['info']} Значок показывает статус задания | юзернейм вашего канала/чата | сделано / цель. Если вы удалите задание, остаток NMP будет возвращен на баланс."
        "</blockquote>"
    )

    buttons = []
    for o in active_orders:
        status_icon = "🟢" if o["status"] == "active" else "🔴"
        ch_username = o['channel_username']
        if not ch_username.startswith("@") and not ch_username.startswith("http"):
            ch_username = f"@{ch_username}"

        btn_label = f"{status_icon} | {ch_username} | {o['current_subs']}/{o['target_subs']}"
        buttons.append([
            InlineKeyboardButton(text=btn_label, callback_data=f"promote_view_single:{o['order_id']}", style="primary"),
            InlineKeyboardButton(text="❌", callback_data=f"promote_delete:{o['order_id']}", style="danger")
        ])

    buttons.append([InlineKeyboardButton(text="⬅️ назад", callback_data="promote_main_menu", style="primary")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("promote_delete:"))
async def promote_delete_order(call: CallbackQuery):
    order_id = int(call.data.split(":")[1])
    order = get_promote_order_by_id(order_id)
    if order and order["user_id"] == call.from_user.id and order["status"] != "completed":
        unfulfilled = max(0, order["target_subs"] - order["current_subs"])
        refund = unfulfilled * order["price_per_sub"]
        if refund > 0:
            db.update_nmp_balance(order["user_id"], refund)
        delete_promote_order(order_id)
        await call.answer(f"✅ Задание удалено! Возвращено {refund} NMP", show_alert=True)
    await promote_active_list_callback(call)


@router.callback_query(F.data.startswith("promote_view_single:"))
async def promote_view_single(call: CallbackQuery):
    order_id = int(call.data.split(":")[1])
    order = get_promote_order_by_id(order_id)
    if not order:
        await call.answer("Не найдено", show_alert=True)
        return
    
    new_status = "paused" if order["status"] == "active" else "active"
    update_promote_order_status(order_id, new_status)
    await call.answer(f"Статус изменен на: {new_status}")
    await promote_active_list_callback(call)


# --- ЗАВЕРШЁННЫЕ ЗАДАЧИ ---

@router.callback_query(F.data == "promote_completed_stats")
async def promote_completed_stats_callback(call: CallbackQuery):
    await call.answer()
    user_name = call.from_user.first_name
    stats = get_completed_promote_stats(call.from_user.id)

    text = (
        f"{PROMOTE_EMOJIS['check']} {user_name}, твои завершенные задачи:\n"
        "---------------------------------------\n"
        f"{PROMOTE_EMOJIS['eyes']} Показов: 0\n"
        f"{PROMOTE_EMOJIS['users']} Подписчиков: {stats['subscribers']:,}\n"
        f"{PROMOTE_EMOJIS['couple']} Вступлений: {stats['inventions']:,}\n"
        "---------------------------------------\n"
        "<blockquote>"
        f"{PROMOTE_EMOJIS['info']} Данная статистика показывает все задания за все время."
        "</blockquote>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="promote_main_menu", style="primary")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
