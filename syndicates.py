# syndicates.py
"""Модуль «Синдикаты: война за районы».

Важно: таблицы создаются через init_syndicate_db() явно при старте приложения.
В main.py после db.init_db() вызовите:
    import syndicates
    syndicates.init_syndicate_db()
и подключите syndicates.router.
"""

import asyncio
import html
import logging
import math
import random
import time
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

import db
import utils

logger = logging.getLogger(__name__)
router = Router()

# ==============================================================================
# PREMIUM EMOJI (ИСПОЛЬЗУЮТСЯ ТОЛЬКО В ТЕКСТЕ СООБЩЕНИЙ)
# ==============================================================================
PREMIUM_EMOJIS = {
    "boss": ('<tg-emoji emoji-id="5769547529993588669">👑</tg-emoji>', "👑"),
    "city": ('<tg-emoji emoji-id="5307960277931667927">🏙️</tg-emoji>', "🏙️"),
    "district": ('<tg-emoji emoji-id="5278702045883292456">🏬</tg-emoji>', "🏬"),
    "war": ('<tg-emoji emoji-id="5463277406435422003">⚔️</tg-emoji>', "⚔️"),
    "shield": ('<tg-emoji emoji-id="5465154440287757794">🛡️</tg-emoji>', "🛡️"),
    "vault": ('<tg-emoji emoji-id="5463046637842608206">💰</tg-emoji>', "💰"),
    "chart": ('<tg-emoji emoji-id="5429463966432643712">📈</tg-emoji>', "📈"),
    "win": ('<tg-emoji emoji-id="5226431245918942763">🎉</tg-emoji>', "🎉"),
    "card": ('<tg-emoji emoji-id="5472250091332993630">💳</tg-emoji>', "💳"),
    "power": ('<tg-emoji emoji-id="5226813248900187912">💥</tg-emoji>', "💥"),
    "gamepad": ('<tg-emoji emoji-id="5350612670435313545">🕹</tg-emoji>', "🕹"),
    "point": ('<tg-emoji emoji-id="5465198403573012261">👉</tg-emoji>', "👉"),
    "arrow": ('<tg-emoji emoji-id="5462881955911584183">➡️</tg-emoji>', "➡️"),
    "fire": ('<tg-emoji emoji-id="5226431245918942763">🔥</tg-emoji>', "🔥"),
}


def pe(key: str) -> str:
    value, fallback = PREMIUM_EMOJIS.get(key, ("", ""))
    if not value or "ВСТАВЬ_ID" in value:
        return fallback
    return value


# ==============================================================================
# НАСТРОЙКИ
# ==============================================================================
CREATE_SYNDICATE_PRICE = 7_000_000
BASE_MEMBER_LIMIT = 15
ATTACK_COOLDOWN = 1_800          # 30 минут на одного игрока
INCOME_INTERVAL = 3_600          # начисление раз в час
MAX_SYNDICATE_LEVEL = 10         # Лимит уровня клана: 10
MEMBERS_PER_PAGE = 5             # 5 участников на страницу при передаче клана
SYNDICATE_IMAGE = "https://i.ibb.co/ycLT7btH/IMG-20260828-182918-517.jpg"

DISTRICTS_DATA = {
    1: {"name": "Заброшенная Промзона", "cost": 100_000, "income": 20_000, "min_lvl": 1, "defense": 1_500},
    2: {"name": "Подпольное Казино", "cost": 500_000, "income": 100_000, "min_lvl": 1, "defense": 2_000},
    3: {"name": "Морской Торговый Порт", "cost": 2_000_000, "income": 450_000, "min_lvl": 2, "defense": 3_000},
    4: {"name": "Крипто-Биржа NMP", "cost": 10_000_000, "income": 2_000_000, "min_lvl": 3, "defense": 4_500},
    5: {"name": "NM Cyber Tower", "cost": 50_000_000, "income": 10_000_000, "min_lvl": 4, "defense": 7_000},
}


class SyndicateState(StatesGroup):
    waiting_for_name = State()
    waiting_for_deposit = State()
    waiting_for_kick_id = State()
    waiting_for_broadcast = State()


# ==============================================================================
# БАЗА ДАННЫХ
# ==============================================================================

def init_syndicate_db() -> None:
    """Создаёт таблицы и безопасно добавляет недостающие поля."""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS syndicates (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                boss_id BIGINT UNIQUE NOT NULL,
                vault_balance DOUBLE PRECISION DEFAULT 0,
                level INT DEFAULT 1,
                rating_points INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS syndicate_members (
                user_id BIGINT PRIMARY KEY,
                syndicate_id INT REFERENCES syndicates(id) ON DELETE CASCADE,
                role VARCHAR(20) DEFAULT 'member',
                contributed DOUBLE PRECISION DEFAULT 0,
                last_attack_time INT8 DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("ALTER TABLE syndicate_members ADD COLUMN IF NOT EXISTS last_attack_time INT8 DEFAULT 0")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS district_owners (
                district_id INT PRIMARY KEY,
                syndicate_id INT REFERENCES syndicates(id) ON DELETE SET NULL,
                captured_at INT8 DEFAULT 0,
                last_income_time INT8 DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS syndicate_applications (
                id SERIAL PRIMARY KEY,
                syndicate_id INT REFERENCES syndicates(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(syndicate_id, user_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS syndicate_invites (
                id SERIAL PRIMARY KEY,
                syndicate_id INT REFERENCES syndicates(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(syndicate_id, user_id)
            )
        """)
        for district_id in DISTRICTS_DATA:
            cursor.execute(
                "INSERT INTO district_owners (district_id) VALUES (%s) ON CONFLICT (district_id) DO NOTHING",
                (district_id,),
            )
        conn.commit()
        logger.info("БД синдикатов инициализирована")
    except Exception:
        conn.rollback()
        logger.exception("Ошибка инициализации БД синдикатов")
        raise
    finally:
        cursor.close()
        conn.close()


def get_user_syndicate(user_id: int) -> Optional[dict]:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT s.id, s.name, s.boss_id, s.vault_balance, s.level,
                   s.rating_points, sm.role, sm.contributed, sm.last_attack_time
            FROM syndicate_members sm
            JOIN syndicates s ON sm.syndicate_id = s.id
            WHERE sm.user_id = %s
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "name": row[1], "boss_id": row[2],
            "vault_balance": float(row[3] or 0), "level": int(row[4] or 1),
            "rating_points": int(row[5] or 0), "user_role": row[6],
            "user_contributed": float(row[7] or 0), "last_attack_time": int(row[8] or 0),
        }
    finally:
        cursor.close()
        conn.close()


def get_syndicate_members_count(syndicate_id: int) -> int:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM syndicate_members WHERE syndicate_id = %s", (syndicate_id,))
        return int(cursor.fetchone()[0] or 0)
    finally:
        cursor.close()
        conn.close()


def get_syndicate_members_list(syndicate_id: int) -> list:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT sm.user_id, u.first_name, u.username, sm.role, sm.contributed
            FROM syndicate_members sm
            LEFT JOIN users u ON sm.user_id = u.user_id
            WHERE sm.syndicate_id = %s
            ORDER BY sm.role DESC, sm.contributed DESC
        """, (syndicate_id,))
        return [{
            "user_id": r[0], "first_name": r[1] or f"Воин {r[0]}",
            "username": r[2], "role": r[3], "contributed": float(r[4] or 0),
        } for r in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def collect_district_income() -> None:
    """Начисляет накопившийся доход по часам без двойных выплат."""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        now = int(time.time())
        cursor.execute("""
            SELECT district_id, syndicate_id, last_income_time
            FROM district_owners
            WHERE syndicate_id IS NOT NULL
            FOR UPDATE
        """)
        for district_id, syndicate_id, last_income in cursor.fetchall():
            last_income = int(last_income or now)
            hours = max(0, (now - last_income) // INCOME_INTERVAL)
            if hours <= 0:
                continue
            income = DISTRICTS_DATA[district_id]["income"] * hours
            cursor.execute(
                "UPDATE syndicates SET vault_balance = vault_balance + %s WHERE id = %s",
                (income, syndicate_id),
            )
            cursor.execute(
                "UPDATE district_owners SET last_income_time = %s WHERE district_id = %s",
                (last_income + hours * INCOME_INTERVAL, district_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Ошибка начисления дохода районов")
    finally:
        cursor.close()
        conn.close()


async def district_income_loop() -> None:
    while True:
        try:
            collect_district_income()
        except Exception:
            logger.exception("Ошибка фонового начисления дохода")
        await asyncio.sleep(300)


# ==============================================================================
# ОБЩИЕ ФУНКЦИИ И ИНТЕРФЕЙС
# ==============================================================================

def safe_name(value: str) -> str:
    return html.escape(str(value or "Пользователь"))


def build_ui_progress_bar(level: int, max_level: int = 10, length: int = 8) -> str:
    """Генерирует стильный визуальный прогресс-бар уровня синдиката"""
    filled_count = round((level / max_level) * length)
    filled_count = max(0, min(length, filled_count))
    return "🟩" * filled_count + "⬛" * (length - filled_count)


def main_keyboard(has_syndicate: bool, is_boss: bool = False) -> InlineKeyboardMarkup:
    # ТОЛЬКО СТАНДАРТНЫЕ ЭМОДЗИ В КНОПКАХ!
    rows = [
        [InlineKeyboardButton(text="🏙️ Карта районов", callback_data="syn_districts")],
        [InlineKeyboardButton(text="🏆 Топ синдикатов", callback_data="syn_top")],
    ]
    if has_syndicate:
        rows.extend([
            [InlineKeyboardButton(text="💰 Казна и взносы", callback_data="syn_vault")],
            [InlineKeyboardButton(text="👥 Состав", callback_data="syn_members")],
            [InlineKeyboardButton(text="🚪 Покинуть синдикат", callback_data="syn_leave_confirm")],
        ])
        if is_boss:
            rows.append([InlineKeyboardButton(text="⚙️ Панель босса", callback_data="syn_boss_panel")])
    else:
        rows.append([
            InlineKeyboardButton(text="➕ Создать синдикат", callback_data="syn_create"),
            InlineKeyboardButton(text="📨 Вступить", callback_data="syn_list")
        ])
    rows.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="back_to_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_main(event, state: FSMContext = None):
    if state:
        await state.clear()
    collect_district_income()
    user_id = event.from_user.id
    user = db.get_user(user_id)
    syn = get_user_syndicate(user_id)

    if syn:
        count = get_syndicate_members_count(syn["id"])
        limit = BASE_MEMBER_LIMIT + (syn["level"] - 1) * 5
        progress = build_ui_progress_bar(syn["level"], MAX_SYNDICATE_LEVEL)
        
        text = (
            f"<b>{pe('boss')} СИНДИКАТ «{safe_name(syn['name'].upper())}»</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Статус: <code>{'Босс' if syn['user_role'] == 'boss' else 'Участник'}</code>\n"
            f"📊 Уровень: <code>{syn['level']}/{MAX_SYNDICATE_LEVEL}</code> [{progress}]\n"
            f"👥 Состав: <code>{count}/{limit} чел.</code>\n"
            f"💎 Очки рейтинга: <code>{syn['rating_points']:,} RP</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{pe('vault')} Казна Клана: <b>{syn['vault_balance']:,.0f} nCoin</b>\n"
            f"💸 Ваш личный вклад: <b>{syn['user_contributed']:,.0f} nCoin</b>"
        )
    else:
        text = (
            f"<b>{pe('city')} СИНДИКАТЫ: ВОЙНА ЗА РАЙОНЫ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Вы стоите на пороге великих войн! Объединяйтесь с другими игроками, штурмуйте укрепленные районы города и получайте миллионные пассивные доходы каждый час!\n\n"
            f"{pe('card')} Ваш баланс: <b>{user['balance']:,.0f} nCoin</b>\n"
            f"{pe('point')} Вы можете основать свой Синдикат или подать заявку в существующий!"
        )

    kb = main_keyboard(bool(syn), bool(syn and syn["user_role"] == "boss"))
    if isinstance(event, Message):
        await event.answer_photo(photo=SYNDICATE_IMAGE, caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        try:
            await event.message.edit_media(
                media=InputMediaPhoto(media=SYNDICATE_IMAGE, caption=text, parse_mode="HTML"),
                reply_markup=kb,
            )
        except Exception:
            await event.message.answer_photo(photo=SYNDICATE_IMAGE, caption=text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("syndicate"))
@router.message(StateFilter(None), F.text.lower().in_(["синдикат", "клан", "районы", "война районов", "синдикаты"]))
async def open_syndicate_main(event, state: FSMContext):
    await render_main(event, state)


@router.callback_query(F.data == "syn_main_menu")
async def syn_main_menu_callback(call: CallbackQuery):
    await call.answer()
    await render_main(call)


# ==============================================================================
# СОЗДАНИЕ СИНДИКАТА
# ==============================================================================

@router.callback_query(F.data == "syn_create")
async def create_syndicate_start(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = db.get_user(user_id)
    if get_user_syndicate(user_id):
        await call.answer("❌ Вы уже состоите в синдикате.", show_alert=True)
        return
    if user["balance"] < CREATE_SYNDICATE_PRICE:
        await call.answer(f"❌ Нужно {CREATE_SYNDICATE_PRICE:,} nCoin.", show_alert=True)
        return
    await call.answer()
    await state.set_state(SyndicateState.waiting_for_name)
    kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="❌ Отмена", callback_data="syn_main_menu")]]])
    await call.message.answer(
        f"<b>{pe('boss')} ОСНОВАНИЕ СИНДИКАТА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Стоимость создания: <b>{CREATE_SYNDICATE_PRICE:,} nCoin</b>\n\n"
        f"{pe('point')} <b>Введите название от 3 до 20 символов:</b>\n"
        "<i>(Разрешены буквы, цифры, пробел и нижнее подчеркивание)</i>",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.message(SyndicateState.waiting_for_name)
async def process_syndicate_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not 3 <= len(name) <= 20 or not all(ch.isalnum() or ch in " _-" for ch in name):
        await message.answer("❌ Название: от 3 до 20 символов, без спецсимволов. Попробуйте ещё раз.")
        return

    user_id = message.from_user.id
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM syndicate_members WHERE user_id = %s", (user_id,))
        if cursor.fetchone():
            await message.answer("❌ Вы уже состоите в синдикате.")
            return

        cursor.execute("SELECT 1 FROM syndicates WHERE LOWER(name) = LOWER(%s)", (name,))
        if cursor.fetchone():
            await message.answer("❌ Такое название уже занято.")
            return

        cursor.execute("""
            UPDATE users SET balance = balance - %s
            WHERE user_id = %s AND balance >= %s
        """, (CREATE_SYNDICATE_PRICE, user_id, CREATE_SYNDICATE_PRICE))
        if cursor.rowcount != 1:
            await message.answer("❌ Недостаточно nCoin.")
            return

        cursor.execute(
            "INSERT INTO syndicates (name, boss_id) VALUES (%s, %s) RETURNING id",
            (name, user_id),
        )
        syndicate_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO syndicate_members (user_id, syndicate_id, role) VALUES (%s, %s, 'boss')",
            (user_id, syndicate_id),
        )
        conn.commit()
        await state.clear()
        await message.answer(
            f"{pe('win')} <b>Синдикат «{safe_name(name.upper())}» создан!</b>\n\n"
            "Вы стали боссом. Набирайте участников, удерживайте районы и выбивайтесь в ТОП!\n"
            "Откройте меню: /syndicate",
            parse_mode="HTML",
        )
    except Exception:
        conn.rollback()
        logger.exception("Ошибка создания синдиката")
        await message.answer("❌ Не удалось создать синдикат. Средства не списаны.")
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# СПИСОК КЛАНОВ И ЗАЯВКИ
# ==============================================================================

@router.callback_query(F.data == "syn_list")
async def show_syndicates_list(call: CallbackQuery):
    await call.answer()
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, name, level, rating_points
            FROM syndicates
            ORDER BY rating_points DESC, level DESC
            LIMIT 8
        """)
        syns = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    text = (
        f"<b>{pe('city')} ВСТУПЛЕНИЕ В СИНДИКАТ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите синдикат из списка лучших, чтобы подать заявку на вступление:\n\n"
    )
    
    buttons = []
    if syns:
        for s_id, name, lvl, rp in syns:
            text += f"⚜️ <b>{safe_name(name)}</b> [Lvl {lvl}] — Рейтинг: <code>{rp:,} RP</code>\n"
            buttons.append([InlineKeyboardButton(text=f"📨 Вступить в {name}", callback_data=f"syn_apply_req:{s_id}")])
    else:
        text += "<i>Активных синдикатов пока нет. Вы можете создать свой!</i>"

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="syn_main_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("syn_apply_req:"))
async def apply_to_syndicate_process(call: CallbackQuery):
    syn_id = int(call.data.split(":")[1])
    user_id = call.from_user.id
    
    if get_user_syndicate(user_id):
        await call.answer("❌ Вы уже состоите в синдикате!", show_alert=True)
        return

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM syndicate_applications WHERE syndicate_id = %s AND user_id = %s AND status = 'pending'",
            (syn_id, user_id)
        )
        if cursor.fetchone():
            await call.answer("⏳ Вы уже отправили заявку в этот синдикат, ожидайте решения Босса!", show_alert=True)
            return

        cursor.execute(
            "INSERT INTO syndicate_applications (syndicate_id, user_id, status) VALUES (%s, %s, 'pending')",
            (syn_id, user_id)
        )
        conn.commit()
        await call.answer("✅ Ваша заявка успешно отправлена Боссу синдиката!", show_alert=True)
    except Exception:
        conn.rollback()
        await call.answer("❌ Ошибка отправки заявки.", show_alert=True)
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# КАРТА И АТАКА
# ==============================================================================

@router.callback_query(F.data == "syn_districts")
async def show_districts_map(call: CallbackQuery):
    await call.answer()
    collect_district_income()
    syn = get_user_syndicate(call.from_user.id)

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT d.district_id, s.name, d.syndicate_id
            FROM district_owners d
            LEFT JOIN syndicates s ON d.syndicate_id = s.id
            ORDER BY d.district_id
        """)
        owners = {r[0]: {"name": r[1], "id": r[2]} for r in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()

    lines = [f"<b>{pe('city')} КАРТА РАЙОНОВ ГОРОДА</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━", ""]
    buttons = []
    for district_id, district in DISTRICTS_DATA.items():
        owner = owners.get(district_id, {})
        owner_name = safe_name(owner.get("name") or "Свободен")
        lines.append(
            f"<b>{pe('district')} {safe_name(district['name'])}</b>\n"
            f"├ Владелец: <b>{owner_name}</b>\n"
            f"├ {pe('chart')} Доход: <b>+{district['income']:,}/час</b>\n"
            f"└ Атака: <b>{district['cost']:,} nCoin</b> | Мин. Lvl {district['min_lvl']}\n"
        )
        if syn:
            buttons.append([InlineKeyboardButton(text=f"⚔️ Атаковать: {district['name']}", callback_data=f"syn_attack:{district_id}")])

    buttons.append([InlineKeyboardButton(text="🔙 В главное меню", callback_data="syn_main_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "\n".join(lines)
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("syn_attack:"))
async def attack_district_process(call: CallbackQuery, bot: Bot):
    district_id = int(call.data.split(":")[1])
    district = DISTRICTS_DATA.get(district_id)
    if not district:
        await call.answer("❌ Район не найден.", show_alert=True)
        return

    user_id = call.from_user.id
    syn = get_user_syndicate(user_id)
    if not syn:
        await call.answer("❌ Вы не состоите в синдикате.", show_alert=True)
        return
    if syn["level"] < district["min_lvl"]:
        await call.answer(f"❌ Нужен уровень {district['min_lvl']}.", show_alert=True)
        return

    now = int(time.time())
    remaining = ATTACK_COOLDOWN - (now - syn["last_attack_time"])
    if remaining > 0:
        await call.answer(f"⏳ Следующая атака через {remaining // 60} мин. {remaining % 60} sec.", show_alert=True)
        return

    nft = db.get_equipped_nft(user_id)
    nft_name = str((nft or {}).get("nft_name", "")).lower()
    nft_key = str((nft or {}).get("image_key", "")).lower()
    power_bonus = 1.5 if "car" in nft_name or "hypercar" in nft_name or "car" in nft_key else 1.25 if nft else 1.0
    power = int(random.randint(1000, 2500) * power_bonus * syn["level"])

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT vault_balance FROM syndicates WHERE id = %s FOR UPDATE", (syn["id"],))
        row = cursor.fetchone()
        if not row or float(row[0] or 0) < district["cost"]:
            await call.answer("❌ В казне недостаточно средств.", show_alert=True)
            return

        cursor.execute("SELECT syndicate_id FROM district_owners WHERE district_id = %s FOR UPDATE", (district_id,))
        owner_row = cursor.fetchone()
        if owner_row and owner_row[0] == syn["id"]:
            await call.answer("✅ Этот район уже принадлежит вашему синдикату.", show_alert=True)
            return

        cursor.execute("""
            UPDATE syndicates SET vault_balance = vault_balance - %s
            WHERE id = %s AND vault_balance >= %s
        """, (district["cost"], syn["id"], district["cost"]))
        if cursor.rowcount != 1:
            await call.answer("❌ Средства уже были потрачены или их недостаточно.", show_alert=True)
            return

        defense = district["defense"]
        if owner_row and owner_row[0]:
            cursor.execute("SELECT level FROM syndicates WHERE id = %s", (owner_row[0],))
            defender = cursor.fetchone()
            defense = int(defense * (1 + ((defender[0] if defender else 1) - 1) * 0.15))

        won = power >= defense
        cursor.execute("""
            UPDATE syndicate_members SET last_attack_time = %s
            WHERE user_id = %s AND syndicate_id = %s
        """, (now, user_id, syn["id"]))

        if won:
            cursor.execute("""
                UPDATE district_owners
                SET syndicate_id = %s, captured_at = %s, last_income_time = %s
                WHERE district_id = %s
            """, (syn["id"], now, now, district_id))
            cursor.execute("UPDATE syndicates SET rating_points = rating_points + %s WHERE id = %s", (district["income"], syn["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Ошибка атаки района")
        await call.answer("❌ Ошибка битвы. Средства возвращены.", show_alert=True)
        return
    finally:
        cursor.close()
        conn.close()

    if won:
        await call.answer("🎉 Район захвачен!", show_alert=True)
        result = (
            f"<b>{pe('war')} ПОБЕДА! РАЙОН ЗАХВАЧЕН! {pe('win')}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🏙️ Район: <b>{safe_name(district['name'])}</b>\n"
            f"👑 Владелец: <b>«{safe_name(syn['name'].upper())}»</b>\n"
            f"👤 Герой: <a href=\"tg://user?id={user_id}\">{safe_name(call.from_user.first_name)}</a>\n"
            f"💥 Ваша штурмовая сила: <b>{power:,} очков</b>\n"
            f"🛡️ Оборона района: <b>{defense:,} очков</b>\n\n"
            f"📈 Доход увеличен: <b>+{district['income']:,} nCoin/час</b> в казну!"
        )
    else:
        await call.answer("⚔️ Атака отбита!", show_alert=True)
        result = (
            f"<b>{pe('shield')} АТАКА ОТБИТА ОБОРОНОЙ!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🏙️ Район: <b>{safe_name(district['name'])}</b>\n"
            f"💥 Ваша сила: <b>{power:,} очков</b>\n"
            f"🛡️ Силы обороны: <b>{defense:,} очков</b>\n\n"
            "Район остался у прежнего владельца. Подготовьте более мощный штурм!"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏙️ Вернуться к карте", callback_data="syn_districts")]])
    try:
        await call.message.edit_caption(caption=result, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(result, reply_markup=kb, parse_mode="HTML")

    if won:
        for member in get_syndicate_members_list(syn["id"]):
            if member["user_id"] == user_id:
                continue
            try:
                await bot.send_message(
                    member["user_id"],
                    f"🎉 <b>Синдикат захватил район!</b>\n"
                    f"{safe_name(district['name'])}: +{district['income']:,} nCoin/час в казну.",
                    parse_mode="HTML",
                )
            except Exception:
                pass


# ==============================================================================
# КАЗНА
# ==============================================================================

@router.callback_query(F.data == "syn_vault")
async def show_vault_menu(call: CallbackQuery):
    await call.answer()
    collect_district_income()
    syn = get_user_syndicate(call.from_user.id)
    if not syn:
        await call.answer("❌ Вы не состоите в синдикате.", show_alert=True)
        return
    text = (
        f"<b>{pe('vault')} КАЗНА «{safe_name(syn['name'].upper())}»</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Казна: <b>{syn['vault_balance']:,.0f} nCoin</b>\n"
        f"💸 Ваш вклад: <b>{syn['user_contributed']:,.0f} nCoin</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Внести nCoin", callback_data="syn_deposit")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="syn_main_menu")],
    ])
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "syn_deposit")
async def deposit_start_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(SyndicateState.waiting_for_deposit)
    await call.message.answer(
        f"{pe('vault')} Введите сумму взноса в nCoin:\n"
        "Примеры: 100к, 1кк, 500000",
        parse_mode="HTML",
    )


@router.message(SyndicateState.waiting_for_deposit)
async def process_vault_deposit(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    syn = get_user_syndicate(user_id)
    if not syn:
        await state.clear()
        await message.answer("❌ Вы больше не состоите в синдикате.")
        return

    user = db.get_user(user_id)
    try:
        amount = float(utils.parse_bet_input(message.text.strip(), user["balance"]))
    except Exception:
        await message.answer("❌ Введите корректную сумму.")
        return
    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше нуля.")
        return

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE users SET balance = balance - %s
            WHERE user_id = %s AND balance >= %s
        """, (amount, user_id, amount))
        if cursor.rowcount != 1:
            await message.answer("❌ Недостаточно nCoin.")
            return
        cursor.execute("UPDATE syndicates SET vault_balance = vault_balance + %s WHERE id = %s", (amount, syn["id"]))
        cursor.execute("UPDATE syndicate_members SET contributed = contributed + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Ошибка взноса")
        await message.answer("❌ Взнос не выполнен. Средства не списаны.")
        return
    finally:
        cursor.close()
        conn.close()

    await state.clear()
    await message.answer(
        f"✅ В казну внесено <b>{amount:,.0f} nCoin</b>.",
        parse_mode="HTML",
    )
    if syn["boss_id"] != user_id:
        try:
            await bot.send_message(syn["boss_id"], f"🔔 Участник внёс {amount:,.0f} nCoin в казну.")
        except Exception:
            pass


# ==============================================================================
# СОСТАВ, ВЫХОД И ПАНЕЛЬ БОССА
# ==============================================================================

@router.callback_query(F.data == "syn_members")
async def show_members_list_cb(call: CallbackQuery):
    await call.answer()
    syn = get_user_syndicate(call.from_user.id)
    if not syn:
        return
    members = get_syndicate_members_list(syn["id"])
    text = f"<b>👥 СОСТАВ «{safe_name(syn['name'].upper())}»</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for index, member in enumerate(members, 1):
        role = "👑" if member["role"] == "boss" else "🪖"
        text += f"{index}. {role} <b>{safe_name(member['first_name'])}</b> — <code>{member['contributed']:,.0f}</code> nCoin\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="syn_main_menu")]])
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "syn_boss_panel")
async def show_boss_panel(call: CallbackQuery):
    await call.answer()
    syn = get_user_syndicate(call.from_user.id)
    if not syn or syn["user_role"] != "boss":
        await call.answer("❌ Доступ только для босса.", show_alert=True)
        return
        
    buttons = []
    
    # ПРОВЕРКА ЛИМИТА УРОВНЯ 10
    if syn["level"] >= MAX_SYNDICATE_LEVEL:
        lvl_info = "⭐ <b>Достигнут МАКСИМАЛЬНЫЙ уровень (Lvl 10)</b>. Прокачка закрыта!"
        buttons.append([InlineKeyboardButton(text="⭐ Максимальный уровень", callback_data="syn_lvl_max_alert")])
    else:
        cost = syn["level"] * 1_000_000
        lvl_info = f"⬆️ Улучшение до Lvl {syn['level'] + 1}: <b>{cost:,} nCoin</b>"
        buttons.append([InlineKeyboardButton(text=f"⬆️ Улучшить уровень (+1)", callback_data="syn_upgrade_lvl")])

    text = (
        f"<b>⚙️ ПАНЕЛЬ БОССА «{safe_name(syn['name'].upper())}»</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Уровень Синдиката: <b>Lvl {syn['level']}/{MAX_SYNDICATE_LEVEL}</b>\n"
        f"💰 Казна: <b>{syn['vault_balance']:,.0f} nCoin</b>\n"
        f"{lvl_info}\n"
    )
    
    buttons.append([InlineKeyboardButton(text="📨 Управление Заявками", callback_data="syn_boss_apps")])
    buttons.append([InlineKeyboardButton(text="🔙 В меню", callback_data="syn_main_menu")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "syn_lvl_max_alert")
async def lvl_max_alert(call: CallbackQuery):
    await call.answer(f"⭐ Синдикат уже достиг предельного {MAX_SYNDICATE_LEVEL}-го уровня!", show_alert=True)


# --- УПРАВЛЕНИЕ ЗАЯВКАМИ БОССОМ ---

@router.callback_query(F.data == "syn_boss_apps")
async def show_syndicate_applications(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    syn = get_user_syndicate(user_id)
    
    if not syn or syn["user_role"] != "boss":
        return

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT sa.id, sa.user_id, u.first_name, u.username
            FROM syndicate_applications sa
            JOIN users u ON sa.user_id = u.user_id
            WHERE sa.syndicate_id = %s AND sa.status = 'pending'
            LIMIT 5
        """, (syn["id"],))
        apps = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    text = (
        f"<b>📨 ЗАЯВКИ НА ВСТУПЛЕНИЕ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Здесь отображаются игроки, желающие пополнить ряды вашего Синдиката:\n\n"
    )
    
    buttons = []
    if apps:
        for app_id, u_id, f_name, u_name in apps:
            uname_str = f" (@{u_name})" if u_name and u_name != "none" else ""
            text += f"👤 <b>{safe_name(f_name)}</b> [ID: {u_id}]{uname_str}\n\n"
            buttons.append([
                InlineKeyboardButton(text=f"✅ Принять {f_name[:12]}", callback_data=f"syn_app_accept:{app_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"syn_app_reject:{app_id}")
            ])
    else:
        text += "<i>Новых заявок на вступление пока нет.</i>"

    buttons.append([InlineKeyboardButton(text="🔙 Панель Босса", callback_data="syn_boss_panel")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("syn_app_accept:"))
async def accept_application_process(call: CallbackQuery, bot: Bot):
    app_id = int(call.data.split(":")[1])
    boss_id = call.from_user.id
    syn = get_user_syndicate(boss_id)
    
    if not syn or syn["user_role"] != "boss":
        return

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id FROM syndicate_applications WHERE id = %s", (app_id,))
        app_user_row = cursor.fetchone()
        if not app_user_row:
            await call.answer("❌ Заявка не найдена.", show_alert=True)
            return
        applicant_id = app_user_row[0]

        count = get_syndicate_members_count(syn["id"])
        limit = BASE_MEMBER_LIMIT + (syn["level"] - 1) * 5
        if count >= limit:
            await call.answer("❌ Нет свободных мест! Прокачайте уровень Синдиката.", show_alert=True)
            return

        cursor.execute("SELECT 1 FROM syndicate_members WHERE user_id = %s", (applicant_id,))
        if cursor.fetchone():
            cursor.execute("DELETE FROM syndicate_applications WHERE user_id = %s", (applicant_id,))
            conn.commit()
            await call.answer("❌ Данный игрок уже состоит в другом Синдикате.", show_alert=True)
            return

        cursor.execute("INSERT INTO syndicate_members (user_id, syndicate_id, role) VALUES (%s, %s, 'member')", (applicant_id, syn["id"]))
        cursor.execute("DELETE FROM syndicate_applications WHERE user_id = %s", (applicant_id,))
        conn.commit()
        await call.answer("✅ Игрок успешно принят в Синдикат!", show_alert=True)
        
        try:
            await bot.send_message(
                applicant_id,
                f"<b>{pe('win')} Поздравляем!</b>\n"
                f"Босс принял вас в Синдикат <b>«{safe_name(syn['name'].upper())}»</b>!\n"
                f"Откройте меню: <code>/syndicate</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass
            
    except Exception:
        conn.rollback()
        await call.answer("❌ Ошибка при одобрении заявки.", show_alert=True)
    finally:
        cursor.close()
        conn.close()
        await show_syndicate_applications(call)


@router.callback_query(F.data.startswith("syn_app_reject:"))
async def reject_application_process(call: CallbackQuery):
    app_id = int(call.data.split(":")[1])
    boss_id = call.from_user.id
    syn = get_user_syndicate(boss_id)
    
    if not syn or syn["user_role"] != "boss":
        return

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM syndicate_applications WHERE id = %s", (app_id,))
        conn.commit()
        await call.answer("❌ Заявка отклонена.", show_alert=True)
    finally:
        cursor.close()
        conn.close()
        await show_syndicate_applications(call)


@router.callback_query(F.data == "syn_upgrade_lvl")
async def upgrade_level_cb(call: CallbackQuery):
    await call.answer()
    syn = get_user_syndicate(call.from_user.id)
    if not syn or syn["user_role"] != "boss":
        await call.answer("❌ Только для босса.", show_alert=True)
        return
    if syn["level"] >= MAX_SYNDICATE_LEVEL:
        await call.answer(f"⭐ Достигнут максимальный уровень ({MAX_SYNDICATE_LEVEL})!", show_alert=True)
        return

    cost = syn["level"] * 1_000_000
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE syndicates
            SET vault_balance = vault_balance - %s, level = level + 1
            WHERE id = %s AND vault_balance >= %s AND level < %s
        """, (cost, syn["id"], cost, MAX_SYNDICATE_LEVEL))
        if cursor.rowcount != 1:
            await call.answer("❌ Недостаточно средств или уровень уже максимальный.", show_alert=True)
            return
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Ошибка улучшения синдиката")
        await call.answer("❌ Ошибка улучшения.", show_alert=True)
        return
    finally:
        cursor.close()
        conn.close()
    await call.answer("🎉 Уровень повышен!", show_alert=True)
    await show_boss_panel(call)


# ==============================================================================
# СИСТЕМА ВЫХОДА И ПЕРЕДАЧИ КЛАНА С ВЫПАДАЮЩИМ СПИСКОМ (ПАГИНАЦИЯ ПО 5 УЧАСТНИКОВ)
# ==============================================================================

@router.callback_query(F.data == "syn_leave_confirm")
async def leave_confirm(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    syn = get_user_syndicate(user_id)
    if not syn:
        return

    # ЕСЛИ ВЫХОДИТ БОСС / СОЗДАТЕЛЬ
    if syn["user_role"] == "boss":
        members = get_syndicate_members_list(syn["id"])
        other_members = [m for m in members if m["user_id"] != user_id]

        # Если босс один в клане — клан распускается
        if not other_members:
            text = (
                f"<b>{pe('boss')} ВЫХОД СОЗДАТЕЛЯ КЛАНА</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"⚠️ В вашем Синдикате больше нет других участников.\n"
                f"Если вы покинете Синдикат, он будет <b>полностью распущен</b>, а казна аннулирована!\n\n"
                f"Вы уверены, что хотите распустить Синдикат?"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💥 Распустить синдикат", callback_data="syn_disband_do")],
                [InlineKeyboardButton(text="🔙 Отмена", callback_data="syn_main_menu")],
            ])
            try:
                await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return

        # Если есть другие участники — открываем постраничный выбор преемника
        await show_transfer_leadership_page(call, syn, other_members, page=1)
        return

    # ЕСЛИ ВЫХОДИТ ОБЫЧНЫЙ УЧАСТНИК
    text = (
        f"<b>{pe('point')} ВЫХОД ИЗ СИНДИКАТА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Вы действительно хотите покинуть Синдикат <b>«{safe_name(syn['name'])}»</b>?\n"
        f"<i>(Личные взносы в казну клана не возвращаются)</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Покинуть", callback_data="syn_leave_do")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="syn_main_menu")],
    ])
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")


async def show_transfer_leadership_page(call: CallbackQuery, syn: dict, members: list, page: int = 1):
    """Постраничный выпадающий список выбора нового босса (ровно по 5 участников)."""
    total_members = len(members)
    total_pages = max(1, math.ceil(total_members / MEMBERS_PER_PAGE))
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    start_idx = (page - 1) * MEMBERS_PER_PAGE
    end_idx = start_idx + MEMBERS_PER_PAGE
    page_members = members[start_idx:end_idx]

    text = (
        f"<b>{pe('boss')} ПЕРЕДАЧА ЛИДЕРСТВА КЛАНА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Вы являетесь Боссом синдиката. Чтобы покинуть клан, выберите нового лидера из списка ниже:\n\n"
        f"📄 Страница: <b>{page} из {total_pages}</b> | Всего воинов: <b>{total_members}</b>"
    )

    kb = []
    for m in page_members:
        name_str = m['first_name']
        if m.get('username') and m['username'] != 'none':
            name_str += f" (@{m['username']})"
        if len(name_str) > 28:
            name_str = name_str[:25] + "..."
            
        kb.append([InlineKeyboardButton(
            text=f"👑 Передать: {name_str}",
            callback_data=f"syn_transfer_boss:{m['user_id']}"
        )])

    # Кнопки пагинации
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"syn_trans_page:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"• {page}/{total_pages} •", callback_data="syn_trans_noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"syn_trans_page:{page + 1}"))

    if nav_row:
        kb.append(nav_row)

    kb.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="syn_main_menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=kb)

    try:
        await call.message.edit_caption(caption=text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "syn_trans_noop")
async def syn_trans_noop_cb(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("syn_trans_page:"))
async def syn_trans_page_cb(call: CallbackQuery):
    await call.answer()
    page = int(call.data.split(":")[1])
    syn = get_user_syndicate(call.from_user.id)
    if not syn or syn["user_role"] != "boss":
        return
    members = get_syndicate_members_list(syn["id"])
    other_members = [m for m in members if m["user_id"] != call.from_user.id]
    await show_transfer_leadership_page(call, syn, other_members, page)


@router.callback_query(F.data.startswith("syn_transfer_boss:"))
async def process_transfer_boss(call: CallbackQuery, bot: Bot):
    new_boss_id = int(call.data.split(":")[1])
    old_boss_id = call.from_user.id
    syn = get_user_syndicate(old_boss_id)

    if not syn or syn["user_role"] != "boss":
        await call.answer("❌ Доступно только действующему Боссу!", show_alert=True)
        return

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        # Проверяем, состоит ли преемник в синдикате
        cursor.execute("SELECT 1 FROM syndicate_members WHERE user_id = %s AND syndicate_id = %s", (new_boss_id, syn["id"]))
        if not cursor.fetchone():
            await call.answer("❌ Участник уже не состоит в синдикате!", show_alert=True)
            return

        # 1. Назначаем нового босса в синдикате
        cursor.execute("UPDATE syndicates SET boss_id = %s WHERE id = %s", (new_boss_id, syn["id"]))
        # 2. Повышаем нового босса в участниках
        cursor.execute("UPDATE syndicate_members SET role = 'boss' WHERE user_id = %s AND syndicate_id = %s", (new_boss_id, syn["id"]))
        # 3. Удаляем старого босса из синдиката
        cursor.execute("DELETE FROM syndicate_members WHERE user_id = %s AND syndicate_id = %s", (old_boss_id, syn["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Ошибка передачи лидерства клана")
        await call.answer("❌ Ошибка передачи полномочий.", show_alert=True)
        return
    finally:
        cursor.close()
        conn.close()

    await call.answer("👑 Полномочия Босса успешно переданы! Вы покинули синдикат.", show_alert=True)

    # Оповещаем нового босса
    try:
        await bot.send_message(
            new_boss_id,
            f"<b>{pe('boss')} ВЫ СТАЛИ БОССОМ СИНДИКАТА!</b>\n"
            f"Прежний создатель передал вам руководство синдикатом <b>«{safe_name(syn['name'].upper())}»</b>!\n"
            f"Вам открыт полный доступ к Панели Босса: <code>/syndicate</code>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await render_main(call)


@router.callback_query(F.data == "syn_disband_do")
async def disband_syndicate_process(call: CallbackQuery):
    boss_id = call.from_user.id
    syn = get_user_syndicate(boss_id)
    if not syn or syn["user_role"] != "boss":
        return

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM syndicates WHERE id = %s AND boss_id = %s", (syn["id"], boss_id))
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Ошибка роспуска синдиката")
        await call.answer("❌ Ошибка при роспуске синдиката.", show_alert=True)
        return
    finally:
        cursor.close()
        conn.close()

    await call.answer("💥 Синдикат был полностью распущен.", show_alert=True)
    await render_main(call)


@router.callback_query(F.data == "syn_leave_do")
async def leave_do(call: CallbackQuery):
    user_id = call.from_user.id
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM syndicate_members WHERE user_id = %s AND role = 'member'", (user_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    await call.answer("Вы покинули синдикат.", show_alert=True)
    await render_main(call)


# ==============================================================================
# ТОП СИНДИКАТОВ
# ==============================================================================

@router.callback_query(F.data == "syn_top")
async def show_top_syndicates_cb(call: CallbackQuery):
    await call.answer()
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT s.name, s.level, s.vault_balance, COUNT(sm.user_id)
            FROM syndicates s
            LEFT JOIN syndicate_members sm ON s.id = sm.syndicate_id
            GROUP BY s.id
            ORDER BY s.rating_points DESC, s.vault_balance DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    text = f"<b>{pe('chart')} ТОП-10 СИНДИКАТОВ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    if not rows:
        text += "Пока нет созданных синдикатов."
    else:
        for index, row in enumerate(rows, 1):
            medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"{index}."
            text += f"{medal} <b>{safe_name(row[0])}</b> · Lvl {row[1]}/{MAX_SYNDICATE_LEVEL} · {row[2]:,.0f} nCoin · {row[3]} чел.\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="syn_main_menu")]])
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
