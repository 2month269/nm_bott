# bonus.py
import time
import random
import html
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import db

logger = logging.getLogger(__name__)
router = Router()

class PrizeGameState(StatesGroup):
    playing = State()

AD_BONUS_IMAGE = "https://i.ibb.co/CsBr69hr/IMG-20260904-092502-134.jpg"

# Награды
REGULAR_REWARD_MIN, REGULAR_REWARD_MAX = 50, 150     # Раз в час
AD_REWARD_MIN, AD_REWARD_MAX = 200, 500             # Раз в сутки
PRIZE_CELL_REWARD_MIN, PRIZE_CELL_REWARD_MAX = 30, 120 # В игре 3х3

EMOJI_GIFT = "🎁"
EMOJI_INFO = "ℹ️"
EMOJI_MONEY = "💰"
EMOJI_CARD = "💳"
EMOJI_AD = "📢"
EMOJI_CROSS = "❌"
EMOJI_CHECK = "✅"
EMOJI_PLUS = "➕"
EMOJI_DARTS = "🎯"

# ==============================================================================
# 🛠 БЕЗОПАСНАЯ РАБОТА С БАЗОЙ ДАННЫХ ДЛЯ ПРИЗА 3х3
# ==============================================================================

def ensure_prize_column():
    """Создает колонку last_prize_time в таблице users, если она отсутствует"""
    try:
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_prize_time INT8 DEFAULT 0;")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка проверки колонки last_prize_time: {e}")

try:
    ensure_prize_column()
except Exception:
    pass

def get_user_last_prize_time(user_id: int) -> int:
    """Точное получение времени последнего приза 3х3 из БД"""
    try:
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(last_prize_time, 0) FROM users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception as e:
        logger.error(f"Ошибка get_user_last_prize_time: {e}")
        return 0

def update_user_prize_time(user_id: int, timestamp: int):
    """Обновление времени приза 3х3 в БД"""
    try:
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_prize_time = %s WHERE user_id = %s", (timestamp, user_id))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка update_user_prize_time: {e}")


def get_bonus_menu_text_and_kb(user_id: int, user_data: dict) -> tuple[str, InlineKeyboardMarkup]:
    current_time = int(time.time())

    # Обычный бонус (1 час)
    last_regular = user_data.get("last_bonus_time", 0) or 0
    reg_cd = max(0, 3600 - (current_time - last_regular))
    reg_btn = f"⏳ {reg_cd // 60}м {reg_cd % 60}с" if reg_cd > 0 else "➕ Обычный бонус (час)"

    # Бонус за рекламу (24 часа)
    last_daily = user_data.get("last_daily_bonus_time", 0) or 0
    ad_cd = max(0, 86400 - (current_time - last_daily))
    ad_btn = f"⏳ {ad_cd // 3600}ч {(ad_cd % 3600) // 60}м" if ad_cd > 0 else "📢 За рекламу (24ч)"

    # Приз 3х3 (24 часа) — получаем точное время из БД
    last_prize = get_user_last_prize_time(user_id)
    prize_cd = max(0, 86400 - (current_time - last_prize))
    prize_btn = f"⏳ {prize_cd // 3600}ч {(prize_cd % 3600) // 60}м" if prize_cd > 0 else "🎁 Приз 3х3 (24ч)"

    text = (
        f"{EMOJI_GIFT} <b>Центр бонусов</b>\n"
        "· · · · · · · · · · · · · · · · · · · · ·\n"
        f"{EMOJI_CARD} Ваш баланс: <b>{int(user_data.get('balance', 0)):,} nCoin</b>\n\n"
        f"{EMOJI_INFO} <b>Доступные награды:</b>\n"
        f"├ {EMOJI_PLUS} Обычный бонус\n"
        f"├ {EMOJI_AD} За рекламу бота\n"
        f"└ {EMOJI_GIFT} Мини-игра Приз 3х3\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=reg_btn, callback_data="claim_regular_bonus")],
        [InlineKeyboardButton(text=ad_btn, callback_data="claim_ad_bonus")],
        [InlineKeyboardButton(text=prize_btn, callback_data="claim_prize_game")]
    ])
    return text, kb

@router.message(F.text.lower().in_(["бонус", "/bonus"]))
async def bonus_menu(message: Message, state: FSMContext):
    await state.clear()
    user = db.get_user(message.from_user.id)
    text, kb = get_bonus_menu_text_and_kb(message.from_user.id, user)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "claim_regular_bonus")
async def claim_regular_bonus(callback: CallbackQuery):
    user_id = callback.from_user.id
    current_time = int(time.time())
    reward = random.randint(REGULAR_REWARD_MIN, REGULAR_REWARD_MAX)
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET balance = balance + %s, last_bonus_time = %s "
        "WHERE user_id = %s AND %s - last_bonus_time >= 3600",
        (reward, current_time, user_id, current_time)
    )
    conn.commit()
    success = cursor.rowcount > 0
    cursor.close()
    conn.close()

    if not success:
        await callback.answer("⏳ Бонус еще не готов!", show_alert=True)
        return

    await callback.answer(f"🎉 Бонус зачислен! Вы получили {reward} nCoin", show_alert=True)
    user_updated = db.get_user(user_id)
    text, kb = get_bonus_menu_text_and_kb(user_id, user_updated)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "claim_ad_bonus")
async def claim_ad_bonus(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    current_time = int(time.time())

    if current_time - (user.get("last_daily_bonus_time", 0) or 0) < 86400:
        await callback.answer("⏳ Приходите завтра!", show_alert=True)
        return

    has_bot_in_bio = False
    try:
        chat = await bot.get_chat(user_id)
        bio = getattr(chat, "bio", None) or ""
        if "@nmines_bot" in bio.lower():
            has_bot_in_bio = True
    except Exception:
        pass

    if has_bot_in_bio:
        reward = random.randint(AD_REWARD_MIN, AD_REWARD_MAX)
        db.update_balance(user_id, reward)
        db.update_user_field(user_id, "last_daily_bonus_time", current_time)

        await callback.answer(f"🎉 Начислено {reward} nCoin!", show_alert=True)
        user_updated = db.get_user(user_id)
        text, kb = get_bonus_menu_text_and_kb(user_id, user_updated)
        
        await callback.message.answer(
            f"🎉 Проверка успешна! Вы добавили бота в Bio, вам начислено <b>{reward} nCoin</b>!\n\nБаланс: {int(user_updated.get('balance', 0)):,} nCoin",
            parse_mode="HTML"
        )
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    text = (
        "📢 <b>Бонус за рекламу</b>\n\n"
        "Добавьте <b>@nmines_bot</b> в описание вашего профиля (Bio), "
        "чтобы получать ежедневный подарок!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я добавил!", callback_data="check_ad_bonus")]
    ])
    await callback.message.answer_photo(photo=AD_BONUS_IMAGE, caption=text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "check_ad_bonus")
async def check_ad_bonus(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    current_time = int(time.time())

    if current_time - (user.get("last_daily_bonus_time", 0) or 0) < 86400:
        await callback.answer("⏳ Приходите завтра!", show_alert=True)
        return

    try:
        chat = await bot.get_chat(user_id)
        bio = getattr(chat, "bio", None) or ""
        if "@nmines_bot" not in bio.lower():
            await callback.answer("❌ Бот не найден в вашем Bio! Добавьте @nmines_bot и попробуйте снова.", show_alert=True)
            return
    except Exception:
        await callback.answer("❌ Не удалось проверить профиль. Убедитесь, что описание открыто.", show_alert=True)
        return

    reward = random.randint(AD_REWARD_MIN, AD_REWARD_MAX)
    db.update_balance(user_id, reward)
    db.update_user_field(user_id, "last_daily_bonus_time", current_time)

    await callback.answer(f"🎉 Начислено {reward} nCoin!", show_alert=True)
    user_updated = db.get_user(user_id)
    text, kb = get_bonus_menu_text_and_kb(user_id, user_updated)
    
    await callback.message.answer(
        f"🎉 Проверка успешна! Вам начислено <b>{reward} nCoin</b>!\n\nБаланс: {int(user_updated.get('balance', 0)):,} nCoin",
        parse_mode="HTML"
    )
    await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- ИГРА 3х3 ---

def generate_prize_grid_kb(opened_indices: set, grid_values: dict, finished: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    opened_int = {int(x) for x in opened_indices}
    for row in range(3):
        row_buttons = []
        for col in range(3):
            idx = row * 3 + col
            if idx in opened_int or finished:
                val = grid_values.get(idx, grid_values.get(str(idx), 0))
                btn_text = f"💰 {val}" if val > 0 else "❌ 0"
                callback_data = "prize_noop"
            else:
                btn_text = "🎁"
                callback_data = f"prize_cell:{idx}"
            row_buttons.append(InlineKeyboardButton(text=btn_text, callback_data=callback_data))
        keyboard.append(row_buttons)
    if finished:
        keyboard.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_bonus_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.callback_query(F.data == "claim_prize_game")
async def start_prize_game(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    current_time = int(time.time())
    
    last_prize = get_user_last_prize_time(user_id)
    if current_time - last_prize < 86400:
        rem = 86400 - (current_time - last_prize)
        h = rem // 3600
        m = (rem % 3600) // 60
        await callback.answer(f"⏳ Приз 3х3 доступен через {h}ч {m}м!", show_alert=True)
        return

    grid = {i: (random.randint(PRIZE_CELL_REWARD_MIN, PRIZE_CELL_REWARD_MAX) if random.random() > 0.4 else 0) for i in range(9)}
    await state.set_state(PrizeGameState.playing)
    await state.update_data(opened=[], grid=grid, total=0)

    text = "🎁 <b>ПРИЗ 3х3</b>\n\nОткройте 3 любые коробки!"
    await callback.message.edit_text(text, reply_markup=generate_prize_grid_kb(set(), grid), parse_mode="HTML")

@router.callback_query(PrizeGameState.playing, F.data.startswith("prize_cell:"))
async def process_prize_cell(callback: CallbackQuery, state: FSMContext):
    try:
        idx = int(callback.data.split(":")[1])
        data = await state.get_data()
        
        # Если состояние по какой-то причине сбросилось (например, бот перезагружался)
        if not data or 'opened' not in data or 'grid' not in data:
            await callback.answer("⏳ Сессия игры истекла. Начните заново.", show_alert=True)
            await state.clear()
            return

        opened = set(data['opened'])
        grid = data['grid']
        total = data.get('total', 0)

        if idx in opened:
            await callback.answer()
            return
        
        # Безопасное получение числа (поддерживает и int, и str ключи)
        val = int(grid.get(idx, grid.get(str(idx), 0)))
        opened.add(idx)
        total += val
        
        if len(opened) < 3:
            # 1-я и 2-я коробки: обновляем состояние
            await state.update_data(opened=list(opened), total=total)
            await callback.answer(f"+{val} nCoin!", show_alert=False)
            await callback.message.edit_reply_markup(reply_markup=generate_prize_grid_kb(opened, grid))
        else:
            # 3-я коробка: завершение игры, начисление выигрыша и запись таймера
            await state.clear()
            db.update_balance(callback.from_user.id, total)
            update_user_prize_time(callback.from_user.id, int(time.time()))
            
            await callback.answer(f"+{val} nCoin!", show_alert=False)
            text = f"🏁 <b>Игра окончена!</b>\n\nВы выиграли: <b>{total} nCoin</b>"
            await callback.message.edit_text(text, reply_markup=generate_prize_grid_kb(opened, grid, True), parse_mode="HTML")
            
    except Exception as e:
        logger.exception("Ошибка в process_prize_cell: %s", e)
        await callback.answer("❌ Произошла ошибка. Попробуйте снова.", show_alert=True)
        await state.clear()

@router.callback_query(F.data == "back_to_bonus_menu")
async def back_to_bonus_menu(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    text, kb = get_bonus_menu_text_and_kb(callback.from_user.id, user)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "prize_noop")
async def prize_noop(callback: CallbackQuery):
    await callback.answer()
