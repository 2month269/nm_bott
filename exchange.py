import os
import time
import html
import logging
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
from aiogram.filters import Command, CommandStart, StateFilter
import db
import utils

logger = logging.getLogger(__name__)
router = Router()

CURRENCY_NAME = "NMPOINT"
CURRENCY_SHORT = "NMP"

# Базовые курсы и лимиты для здоровой экономики
OFFICIAL_SELL_RATE = 2000    # Официальный выкуп ботом (чуть ниже рыночного ~2100)
MIN_BUY_NCOIN = 100          # Минимальная сумма сделки: 100 nCoin
MIN_RATE_LIMIT = 100         # Минимально допустимый курс в стакане
MAX_RATE_LIMIT = 500_000     # Максимально допустимый курс в стакане

def pe(emoji_id: str, fallback: str) -> str:
    if emoji_id and emoji_id.isdigit():
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback

PE_EXCHANGE = pe("5382239087321172481", "💱")
PE_INFO = pe("5469956488351025557", "ℹ️")
PE_HAND_DOWN = pe("5350612670435313545", "👇")
PE_ROCKET = pe("5780773956030043338", "🚀")
PE_USER = pe("5350612670435313545", "👤")
PE_HEART = pe("5467403607286502523", "💖")
PE_SPARKLES = pe("5429463966432643712", "✨")
PE_MONEY = pe("5990147899403539264", "💰")
PE_ATM = pe("6280364500361155698", "🏧")
PE_GREEN = pe("5805523262691611326", "🟢")
PE_RED = pe("5465665476971471368", "🔴")
PE_STAR = pe("5429463966432643712", "⭐")
PE_FIRE = pe("5429463966432643712", "🔥")
PE_PARTY = pe("5989848973974704652", "🎉")
PE_GEM = pe("5467403607286502523", "💎")
PE_CIRCLE = pe("5469956488351025557", "⚪")
PE_WARN = pe("5454350746407419714", "⚠️")
PE_GEAR = pe("5350612670435313545", "⚙️")
PE_CARD = pe("6280364500361155698", "💳")
PE_CHART = pe("5231200819986047254", "📊")
PE_BOX = pe("5989848973974704652", "📦")
PE_LIGHTNING = pe("5429463966432643712", "⚡")
PE_TEMPLE = pe("5231200819986047254", "🏛")
PE_WRITE = pe("5350612670435313545", "✍️")
PE_INBOX = pe("5469956488351025557", "📥")
PE_OUTBOX = pe("5469956488351025557", "📤")
PE_CROSS = pe("5465665476971471368", "❌")
PE_CHECK = pe("5805523262691611326", "✅")
PE_PIN = pe("5469956488351025557", "📌")
PE_COIN = pe("5990147899403539264", "🪙")
PE_GIFT = pe("5989848973974704652", "🎁")
PE_BELL = pe("5429463966432643712", "🔔")

def fnum(number: int | float) -> str:
    """Форматирует число с апострофом: 551070 -> 551'070"""
    return f"{int(number):,}".replace(",", "'")

async def safe_edit_message(target_message, text: str, reply_markup=None):
    """Безопасное редактирование: если Telegram отклоняет премиум-эмодзи, отправляет без них."""
    try:
        await target_message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as exc:
        logger.warning(f"Ошибка при edit_text: {exc}. Применяем очистку от кастомных эмодзи.")
        clean_text = re.sub(r'<[^>]*tg-emoji[^>]*>', '', text).replace('</tg-emoji>', '')
        try:
            await target_message.edit_text(clean_text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            await target_message.edit_text(clean_text, reply_markup=reply_markup)

async def safe_answer_message(message: Message, text: str, reply_markup=None):
    """Безопасный ответ (метод answer): если Telegram отклоняет премиум-эмодзи, отправляет без них."""
    try:
        return await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as exc:
        logger.warning(f"Ошибка при answer: {exc}. Применяем очистку от кастомных эмодзи.")
        clean_text = re.sub(r'<[^>]*tg-emoji[^>]*>', '', text).replace('</tg-emoji>', '')
        try:
            return await message.answer(clean_text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            return await message.answer(clean_text, reply_markup=reply_markup)

async def safe_send_message(bot: Bot, chat_id: int, text: str, reply_markup=None):
    """Безопасная прямая отправка сообщений (send_message) через инстанс бота."""
    try:
        return await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as exc:
        logger.warning(f"Ошибка при send_message: {exc}. Применяем очистку от кастомных эмодзи.")
        clean_text = re.sub(r'<[^>]*tg-emoji[^>]*>', '', text).replace('</tg-emoji>', '')
        try:
            return await bot.send_message(chat_id, clean_text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            return await bot.send_message(chat_id, clean_text, reply_markup)

def get_notify_kb(notify_type: str, is_enabled: bool) -> InlineKeyboardMarkup:
    status_icon = "✅" if is_enabled else "❌"
    action_text = "покупках" if notify_type == "buy" else "продажах"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Уведомления о {action_text} {status_icon}",
                callback_data=f"ex_toggle_notify:{notify_type}",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(text="P2P Обменник", callback_data="ex_back_main", style="primary")
        ]
    ])

@router.callback_query(F.data.startswith("ex_toggle_notify:"))
async def process_toggle_notify_styled(callback: CallbackQuery):
    notify_type = callback.data.split(":")[1]
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    new_status = int(not user.get("exchange_notifications", True))
    db.update_user_field(user_id, "exchange_notifications", new_status)
    
    await callback.message.edit_reply_markup(reply_markup=get_notify_kb(notify_type, bool(new_status)))
    status_text = "включены" if new_status else "выключены"
    await callback.answer(f"Уведомления {status_text}!")

async def notify_seller_success(bot: Bot, seller_id: int, amount: int, cost: int, rate: int):
    user = db.get_user(seller_id)
    if not user.get("exchange_notifications", True):
        return

    text = (
        f"{PE_CHECK} <b>NMP УСПЕШНО ПРОДАН</b>\n"
        "· · · · · · · · · · · · · · · · · · · · · · · · ·\n"
        f"{PE_GEM} <b>Продано:</b> {fnum(amount)} NMP\n"
        f"{PE_CHART} <b>Курс:</b> {fnum(rate)} nCoin за 1 NMP\n"
        "· · · · · · · · · · · · · · · · · · · · · · · · ·\n"
        f"<blockquote>{PE_MONEY} <b>Получено:</b> {fnum(cost)} nCoin</blockquote>"
    )
    kb = get_notify_kb("sell", True)
    try:
        await safe_send_message(bot, seller_id, text, reply_markup=kb)
    except Exception: pass

async def notify_buyer_success(bot: Bot, buyer_id: int, amount: int, cost: int, rate: int):
    user = db.get_user(buyer_id)
    if not user.get("exchange_notifications", True):
        return

    text = (
        f"{PE_CHECK} <b>NMP УСПЕШНО КУПЛЕН</b>\n"
        "· · · · · · · · · · · · · · · · · · · · · · · · ·\n"
        f"{PE_GEM} <b>Куплено:</b> {fnum(amount)} NMP\n"
        f"{PE_CHART} <b>Курс:</b> 1 NMP за {fnum(rate)} nCoin\n"
        "· · · · · · · · · · · · · · · · · · · · · · · · ·\n"
        f"<blockquote>{PE_MONEY} <b>Потрачено:</b> {fnum(cost)} nCoin</blockquote>"
    )
    kb = get_notify_kb("buy", True)
    try:
        await safe_send_message(bot, buyer_id, text, reply_markup=kb)
    except Exception: pass

class ExchangeState(StatesGroup):
    waiting_for_deposit_ncoin = State()
    waiting_for_withdraw_ncoin = State()
    waiting_for_deposit_nmp = State()
    waiting_for_withdraw_nmp = State()
    waiting_for_buy_rate = State()
    waiting_for_sell_rate = State()
    waiting_for_buy_amount_text = State()
    waiting_for_sell_amount_text = State()
    waiting_for_off_sell_amount = State()

def ensure_default_rates(user_id: int, user: dict):
    updated = False
    if user.get("buy_rate", 0) in (0, 121000.0, 3000.0, 75000.0):
        db.update_user_field(user_id, "buy_rate", 2100.0)
        updated = True
    if user.get("sell_rate", 0) in (0, 195950.0, 4200.0, 75000.0):
        db.update_user_field(user_id, "sell_rate", 2100.0)
        updated = True
    if updated:
        return db.get_user(user_id)
    return user

# --- КЛАВИАТУРЫ ГЛАВНОГО МЕНЮ ---

def get_main_exchange_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 КУПИТЬ", callback_data="ex_list_buy:0", style="success")
        ],
        [
            InlineKeyboardButton(text="💳 ПРОДАТЬ", callback_data="ex_list_sell:0", style="danger")
        ],
        [
            InlineKeyboardButton(text="📝", callback_data="ex_control_panel", style="primary"),
            InlineKeyboardButton(text="🧾", callback_data="ex_history_page:0", style="primary")
        ]
    ])

def get_control_panel_kb(user_id: int) -> InlineKeyboardMarkup:
    user = db.get_user(user_id)
    notif_status = "🔔 ВКЛ" if user.get("exchange_notifications", True) else "🔕 ВЫКЛ"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🏛 Продать скупщику (по {OFFICIAL_SELL_RATE:,})", callback_data="ex_off_sell", style="success")
        ],
        [
            InlineKeyboardButton(text="📥 Пополнить биржу", callback_data="ex_deposit_menu", style="primary"),
            InlineKeyboardButton(text="📤 Вывести в кошелек", callback_data="ex_withdraw_menu", style="primary")
        ],
        [
            InlineKeyboardButton(text=f"📈 Курс покупки {CURRENCY_SHORT}", callback_data="ex_rate_buy", style="primary"),
            InlineKeyboardButton(text=f"📉 Курс продажи {CURRENCY_SHORT}", callback_data="ex_rate_sell", style="primary")
        ],
        [
            InlineKeyboardButton(text=f"Уведомления: {notif_status}", callback_data="ex_toggle_notif", style="primary")
        ],
        [
            InlineKeyboardButton(text="⬅️ назад", callback_data="ex_back_main", style="primary")
        ]
    ])

def get_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="ex_back_main", style="primary")]
    ])

def get_back_to_control_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="ex_control_panel", style="primary")]
    ])

# --- ГЛАВНЫЙ ЭКРАН P2P ОБМЕННИКА ---

@router.message(CommandStart())
async def start_command_handler(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    
    if len(args) > 1 and args[1].strip() == "exchange":
        await show_exchange_main(message, state)
        return
        
def is_exchange_command(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    return t in ["/exchange", "обменник", "📊 обменник", "p2p обменник"] or t.startswith("/start exchange")

@router.message(F.text.startswith("/start exchange"))
@router.message(Command("exchange"))
@router.message(F.text.lower().in_({"обменник", "/exchange", "📊 обменник", "p2p обменник"}))
async def show_exchange_main(message: Message, state: FSMContext):
    if message.chat.type != "private":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Перейти в ЛС", url="https://t.me/nmines_bot?start=exchange", style="primary")]
        ])
        await safe_answer_message(message, f"{PE_INFO} Данная функция доступна только в лс с ботом", reply_markup=kb)
        return

    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id)
    user = ensure_default_rates(user_id, user)
    
    user_name = html.escape(message.from_user.first_name or message.from_user.username or f"{user_id}")

    text = (
        f"{PE_EXCHANGE} <b>P2P ОБМЕННИК</b>\n"
        f"..................................................\n\n"
        f"<blockquote>{PE_INFO} Здесь ты можешь вручную покупать и продавать {CURRENCY_NAME} без скрытых авто-сделок.</blockquote>\n\n"
        f"{PE_HAND_DOWN} <i>{user_name}</i>, что ты хочешь?"
    )
    await safe_answer_message(message, text, reply_markup=get_main_exchange_kb())
    
@router.callback_query(F.data == "ex_back_main")
async def back_main_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    user = ensure_default_rates(user_id, user)
    
    user_name = html.escape(callback.from_user.first_name or callback.from_user.username or f"{user_id}")

    text = (
        f"{PE_EXCHANGE} <b>P2P ОБМЕННИК</b>\n"
        f"..................................................\n\n"
        f"<blockquote>{PE_INFO} Здесь ты можешь вручную покупать и продавать {CURRENCY_NAME} без скрытых авто-сделок.</blockquote>\n\n"
        f"{PE_HAND_DOWN} <i>{user_name}</i>, что ты хочешь?"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_main_exchange_kb())

@router.callback_query(F.data.startswith("ex_list_buy:"))
async def show_buy_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    per_page = 7
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, exchange_nmp_balance, sell_rate 
        FROM users 
        WHERE exchange_nmp_balance > 0 AND user_id != %s 
        ORDER BY sell_rate ASC
    """, (user_id,))
    all_raw_orders = cursor.fetchall()
    cursor.close()
    conn.close()

    all_orders = []
    for order in all_raw_orders:
        s_id, s_vol, s_rate = order
        if s_rate >= MIN_RATE_LIMIT and (s_vol * s_rate) >= MIN_BUY_NCOIN:
            all_orders.append(order)
    
    total_orders = len(all_orders)
    total_pages = max(1, (total_orders + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    
    current_orders = all_orders[page * per_page : (page + 1) * per_page]
    
    text = (
        f"{PE_ROCKET} <b>КУПИТЬ {CURRENCY_NAME}</b>\n"
        "..................................................\n\n"
        f"<blockquote>{PE_INFO} {CURRENCY_NAME} можно приобрести у других игроков. "
        f"Минимальная сумма покупки: <b>{MIN_BUY_NCOIN} nCoin</b>. Выгодные предложения находятся вверху.</blockquote>"
    )
    
    kb_buttons = []
    if not current_orders:
        kb_buttons.append([InlineKeyboardButton(text="🕸 Нет доступных ордеров", callback_data="ex_back_main", style="primary")])
    else:
        for order in current_orders:
            seller_id, volume, rate = order
            seller_user = db.get_user(seller_id)
            raw_name = seller_user.get("first_name") or seller_user.get("username") or f"{seller_id}"
            seller_name = html.escape(raw_name)
            rate_formatted = f"{int(rate):,}".replace(",", "'")
            
            btn_text = f"{seller_name} • {rate_formatted} n¢ за {CURRENCY_SHORT}"
            kb_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"ex_buy_item:{seller_id}", style="success")])
            
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"ex_list_buy:{page-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="🚫", callback_data="ex_noop", style="primary"))
        
    nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ex_noop", style="primary"))
    
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"ex_list_buy:{page+1}", style="primary"))
        nav_row.append(InlineKeyboardButton(text=f"⏩ {total_pages}", callback_data=f"ex_list_buy:{total_pages-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="🚫", callback_data="ex_noop", style="primary"))
        
    kb_buttons.append(nav_row)
    kb_buttons.append([InlineKeyboardButton(text="⬅️ назад", callback_data="ex_back_main", style="primary")])
    
    await safe_edit_message(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))

@router.callback_query(F.data == "ex_noop")
async def noop_cb(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith("ex_buy_item:"))
async def show_buy_item_detail(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    seller_id = int(callback.data.split(":")[1])
    
    if seller_id == callback.from_user.id:
        await callback.answer("❌ Нельзя покупать у самого себя!", show_alert=True)
        return

    seller_user = db.get_user(seller_id)
    if not seller_user:
        await safe_answer_message(callback.message, f"{PE_CROSS} Продавец не найден!")
        return
        
    rate = int(seller_user.get("sell_rate", 0))
    available = int(seller_user.get("exchange_nmp_balance", 0))
    
    if available <= 0 or rate < MIN_RATE_LIMIT or (available * rate) < MIN_BUY_NCOIN:
        await safe_answer_message(callback.message, f"{PE_CROSS} Этот лот уже недействителен!")
        return
        
    seller_name = html.escape(seller_user.get("first_name") or seller_user.get("username") or f"{seller_id}")
    rating_str = db.get_user_rating(seller_id)
    rate_fmt = f"{rate:,}".replace(",", "'")
    
    user = db.get_user(callback.from_user.id)
    user_max = int(user["balance"] / rate) if rate > 0 else 0
    max_buyable = max(0, min(available, user_max))
    
    min_nmp_required = (MIN_BUY_NCOIN + rate - 1) // rate
    
    await state.update_data(buy_seller_id=seller_id, buy_rate=rate, buy_available=available)
    
    text = (
        f"{PE_ROCKET} <b>КУПИТЬ {CURRENCY_NAME}</b>\n"
        "..................................................\n\n"
        f"{PE_USER} Продавец: <b>{seller_name}</b>\n"
        f"{PE_HEART} Рейтинг: {rating_str}\n"
        f"{PE_SPARKLES} Доступно: {available:,} {CURRENCY_SHORT}\n"
        f"{PE_MONEY} Курс: {rate_fmt} nCoin = 1 {CURRENCY_SHORT}\n"
        f"{PE_CROSS} Минимальная покупка: <b>{MIN_BUY_NCOIN} nCoin</b> (от {min_nmp_required} {CURRENCY_SHORT})\n"
        "..................................................\n"
        f"{PE_CIRCLE} Комиссия: 0%\n\n"
        f"<blockquote>{PE_INFO} Напишите количество {CURRENCY_SHORT}, которое хотите купить (минимум на {MIN_BUY_NCOIN} nCoin), либо нажмите кнопку.</blockquote>"
    )
    
    buttons = []
    if max_buyable >= min_nmp_required:
        buttons.append([InlineKeyboardButton(text=f"Все • {max_buyable} {CURRENCY_SHORT}", callback_data=f"ex_confirm_buy:{seller_id}:{max_buyable}", style="success")])
    if available >= min_nmp_required:
        buttons.append([InlineKeyboardButton(text=f"Мин • {min_nmp_required} {CURRENCY_SHORT}", callback_data=f"ex_confirm_buy:{seller_id}:{min_nmp_required}", style="primary")])
    buttons.append([InlineKeyboardButton(text="⬅️ назад", callback_data="ex_list_buy:0", style="primary")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_edit_message(callback.message, text, reply_markup=kb)
    await state.set_state(ExchangeState.waiting_for_buy_amount_text)

@router.message(ExchangeState.waiting_for_buy_amount_text, F.text)
async def process_buy_amount_text(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    data = await state.get_data()
    seller_id = data.get("buy_seller_id")
    seller_rate = data.get("buy_rate", 0)
    if not seller_id:
        await state.clear()
        return
        
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0 or not val.is_integer(): raise ValueError
        amount = int(val)
    except ValueError:
        await safe_answer_message(message, f"{PE_CROSS} <b>Введите корректное целое число!</b>")
        return

    if (amount * seller_rate) < MIN_BUY_NCOIN:
        await safe_answer_message(
            message,
            f"{PE_CROSS} <b>Минимальная сумма покупки — {MIN_BUY_NCOIN} nCoin!</b>\n"
            f"При текущем курсе вам необходимо купить минимум: <b>{(MIN_BUY_NCOIN + seller_rate - 1) // seller_rate} {CURRENCY_SHORT}</b>"
        )
        return
        
    await show_buy_confirm_screen(message, state, seller_id, amount)

@router.callback_query(F.data.startswith("ex_confirm_buy:"))
async def process_buy_confirm_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    seller_id = int(parts[1])
    amount = int(parts[2])
    
    if seller_id == callback.from_user.id:
        await callback.answer("❌ Нельзя совершать сделки с собой!", show_alert=True)
        return

    seller = db.get_user(seller_id)
    rate = int(seller.get("sell_rate", 0)) if seller else 0
    if (amount * rate) < MIN_BUY_NCOIN:
        await safe_answer_message(callback.message, f"{PE_CROSS} Минимальная сумма покупки: {MIN_BUY_NCOIN} nCoin!")
        return
        
    await show_buy_confirm_screen(callback.message, state, seller_id, amount, is_edit=True)

async def show_buy_confirm_screen(message_or_cb, state: FSMContext, seller_id: int, amount: int, is_edit: bool = False):
    seller = db.get_user(seller_id)
    if not seller: return
    
    rate = int(seller.get("sell_rate", 0))
    available = int(seller.get("exchange_nmp_balance", 0))
    
    buyer_id = message_or_cb.chat.id if isinstance(message_or_cb, Message) else message_or_cb.from_user.id
    buyer = db.get_user(buyer_id)
    buyer_name = html.escape(buyer.get("first_name") or buyer.get("username") or f"{buyer_id}")
    
    total_cost = amount * rate
    if total_cost < MIN_BUY_NCOIN:
        text_err = f"{PE_CROSS} Минимальная сумма покупки — {MIN_BUY_NCOIN} nCoin!"
        if is_edit: await safe_edit_message(message_or_cb, text_err)
        else: await safe_answer_message(message_or_cb, text_err)
        return

    if amount > available:
        text_err = f"{PE_CROSS} Продавец продает максимум {available:,} {CURRENCY_SHORT}!"
        if is_edit: await safe_edit_message(message_or_cb, text_err)
        else: await safe_answer_message(message_or_cb, text_err)
        return

    rate_fmt = f"{rate:,}".replace(",", "'")
    cost_fmt = f"{total_cost:,}".replace(",", "'")
    
    text = (
        f"{PE_ATM} <b>ПОДТВЕРЖДЕНИЕ СДЕЛКИ</b>\n"
        "..................................................\n\n"
        f"<b>{buyer_name}</b>, ты точно хочешь купить <b>{amount} {CURRENCY_NAME}</b> за <b>{cost_fmt} nCoin</b>?\n\n"
        f"<blockquote>{PE_MONEY} Курс: {rate_fmt} nCoin</blockquote>\n"
        f"<blockquote>{PE_CIRCLE} Комиссия: 0% = 0 nCoin</blockquote>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да ✅", callback_data=f"ex_exec_buy:{seller_id}:{amount}", style="success")],
        [InlineKeyboardButton(text="Отмена 💢", callback_data="ex_list_buy:0", style="danger")]
    ])
    
    await state.clear()
    
    if is_edit:
        await safe_edit_message(message_or_cb, text, reply_markup=kb)
    else:
        await safe_answer_message(message_or_cb, text, reply_markup=kb)

# ==============================================================================
# 🟢 ИСПОЛНЕНИЕ СДЕЛКИ ПОКУПКИ
# ==============================================================================

@router.callback_query(F.data.startswith("ex_exec_buy:"))
async def execute_buy(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await state.clear()
    
    parts = callback.data.split(":")
    seller_id = int(parts[1])
    amount = int(parts[2])
    buyer_id = callback.from_user.id

    if seller_id == buyer_id:
        await safe_edit_message(callback.message, f"{PE_CROSS} <b>Сделка отклонена: нельзя покупать у себя!</b>")
        return
    
    seller = db.get_user(seller_id)
    buyer = db.get_user(buyer_id)
    
    if not seller or seller.get("exchange_nmp_balance", 0) < amount:
        await safe_edit_message(callback.message, f"{PE_CROSS} <b>Сделка отклонена! Лот продавца уже выкуплен или изменен.</b>")
        return
        
    rate = int(seller.get("sell_rate", 0))
    cost = amount * rate
    
    if cost < MIN_BUY_NCOIN:
        await safe_edit_message(callback.message, f"{PE_CROSS} <b>Минимальная сумма сделки: {MIN_BUY_NCOIN} nCoin!</b>")
        return

    if buyer.get("balance", 0) < cost:
        await safe_edit_message(callback.message, f"{PE_CROSS} <b>Недостаточно nCoin на балансе!</b>")
        return

    # Атомарно проводим транзакцию
    db.update_balance(buyer_id, -cost)
    db.update_nmp_balance(buyer_id, amount)
    db.update_exchange_nmp_balance(seller_id, -amount)
    db.update_balance(seller_id, cost)
    
    buyer_name = html.escape(callback.from_user.first_name or callback.from_user.username or f"{buyer_id}")
    seller_name = html.escape(seller.get("first_name") or seller.get("username") or f"{seller_id}")
    
    deal_id = db.add_exchange_history(buyer_id, f"Купил у {seller_name}", amount, cost, "BUY")
    db.add_exchange_history(seller_id, f"Продал {buyer_name}", amount, cost, "SELL")
    
    cost_fmt = f"{cost:,}".replace(",", "'")
    rate_fmt = f"{rate:,}".replace(",", "'")
    
    text = (
        f"{PE_GREEN} <b>УСПЕШНАЯ ПОКУПКА</b>\n"
        "..................................................\n\n"
        f"<b>{buyer_name}</b>, ты купил <b>{amount} {CURRENCY_NAME}</b> за <b>{cost_fmt} nCoin</b>!\n\n"
        f"<blockquote>{PE_MONEY} По курсу: {rate_fmt} nCoin</blockquote>\n"
        f"<blockquote>{PE_INFO} Вы можете оценить сделку с <b>{seller_name}</b>.</blockquote>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✔️ Рейтинг +1", callback_data=f"ex_rate:{deal_id}:{seller_id}:1", style="success"),
            InlineKeyboardButton(text="🔻 Рейтинг -1", callback_data=f"ex_rate:{deal_id}:{seller_id}:-1", style="danger")
        ]
    ])
    
    await safe_edit_message(callback.message, text, reply_markup=kb)
    await notify_seller_success(bot, seller_id, amount, cost, rate)

# ==============================================================================
# 🚀 СПИСОК ОРДЕРОВ ПРОДАЖИ
# ==============================================================================

@router.callback_query(F.data.startswith("ex_list_sell:"))
async def show_sell_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    per_page = 7
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, exchange_balance, buy_rate 
        FROM users 
        WHERE exchange_balance >= %s AND user_id != %s 
        ORDER BY buy_rate DESC
    """, (MIN_BUY_NCOIN, user_id))
    all_orders = cursor.fetchall()
    cursor.close()
    conn.close()
    
    valid_orders = []
    for o in all_orders:
        b_id, ex_bal, r = o
        if r >= MIN_RATE_LIMIT and int(ex_bal / r) > 0 and ex_bal >= MIN_BUY_NCOIN:
            valid_orders.append((b_id, int(ex_bal / r), int(r)))
            
    total_orders = len(valid_orders)
    total_pages = max(1, (total_orders + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    
    current_orders = valid_orders[page * per_page : (page + 1) * per_page]
    
    text = (
        f"{PE_ROCKET} <b>ПРОДАТЬ {CURRENCY_NAME}</b>\n"
        "..................................................\n\n"
        f"<blockquote>{PE_INFO} Продавайте свои {CURRENCY_NAME} покупателям вручную. "
        f"Минимальная заявка в стакане: <b>{MIN_BUY_NCOIN} nCoin</b>.</blockquote>"
    )
    
    kb_buttons = []
    if not current_orders:
        kb_buttons.append([InlineKeyboardButton(text="🕸 Нет ордеров на покупку", callback_data="ex_back_main", style="primary")])
    else:
        for order in current_orders:
            buyer_id, volume, rate = order
            buyer_user = db.get_user(buyer_id)
            raw_name = buyer_user.get("first_name") or buyer_user.get("username") or f"{buyer_id}"
            buyer_name = html.escape(raw_name)
            rate_formatted = f"{rate:,}".replace(",", "'")
            
            btn_text = f"{buyer_name} • {rate_formatted} n¢ за {CURRENCY_SHORT}"
            kb_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"ex_sell_item:{buyer_id}", style="danger")])
            
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"ex_list_sell:{page-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="🚫", callback_data="ex_noop", style="primary"))
        
    nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ex_noop", style="primary"))
    
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"ex_list_sell:{page+1}", style="primary"))
        nav_row.append(InlineKeyboardButton(text=f"⏩ {total_pages}", callback_data=f"ex_list_sell:{total_pages-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="🚫", callback_data="ex_noop", style="primary"))
        
    kb_buttons.append(nav_row)
    kb_buttons.append([InlineKeyboardButton(text="⬅️ назад", callback_data="ex_back_main", style="primary")])
    
    await safe_edit_message(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))

@router.callback_query(F.data.startswith("ex_sell_item:"))
async def show_sell_item_detail(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    buyer_id = int(callback.data.split(":")[1])
    
    if buyer_id == callback.from_user.id:
        await callback.answer("❌ Нельзя продавать самому себе!", show_alert=True)
        return

    buyer_user = db.get_user(buyer_id)
    if not buyer_user:
        await safe_answer_message(callback.message, f"{PE_CROSS} Покупатель не найден!")
        return
        
    rate = int(buyer_user.get("buy_rate", 0))
    buyer_ncoin_bal = int(buyer_user.get("exchange_balance", 0))
    max_needed = int(buyer_ncoin_bal / rate) if rate > 0 else 0
    
    if max_needed <= 0 or rate < MIN_RATE_LIMIT or buyer_ncoin_bal < MIN_BUY_NCOIN:
        await safe_answer_message(callback.message, f"{PE_CROSS} Этот ордер уже недействителен!")
        return
        
    buyer_name = html.escape(buyer_user.get("first_name") or buyer_user.get("username") or f"{buyer_id}")
    rating_str = db.get_user_rating(buyer_id)
    rate_fmt = f"{rate:,}".replace(",", "'")
    
    user = db.get_user(callback.from_user.id)
    user_nmp = int(user["nmp_balance"])
    max_sellable = max(0, min(max_needed, user_nmp))
    
    min_nmp_required = (MIN_BUY_NCOIN + rate - 1) // rate

    await state.update_data(sell_buyer_id=buyer_id, sell_rate=rate, sell_needed=max_needed)
    
    text = (
        f"{PE_ROCKET} <b>ПРОДАТЬ {CURRENCY_NAME}</b>\n"
        "..................................................\n\n"
        f"{PE_USER} Покупатель: <b>{buyer_name}</b>\n"
        f"{PE_HEART} Рейтинг: {rating_str}\n"
        f"{PE_SPARKLES} Готов купить до: {max_needed:,} {CURRENCY_SHORT}\n"
        f"{PE_MONEY} Курс: {rate_fmt} nCoin = 1 {CURRENCY_SHORT}\n"
        f"{PE_CROSS} Мин. сумма сделки: <b>{MIN_BUY_NCOIN} nCoin</b> (от {min_nmp_required} {CURRENCY_SHORT})\n"
        "..................................................\n"
        f"{PE_CIRCLE} Комиссия: 0%\n\n"
        f"<blockquote>{PE_INFO} Напишите количество {CURRENCY_SHORT}, которое хотите продать покупателю (минимум на {MIN_BUY_NCOIN} nCoin).</blockquote>"
    )
    
    buttons = []
    if max_sellable >= min_nmp_required:
        buttons.append([InlineKeyboardButton(text=f"Все • {max_sellable} {CURRENCY_SHORT}", callback_data=f"ex_confirm_sell:{buyer_id}:{max_sellable}", style="danger")])
    if max_needed >= min_nmp_required:
        buttons.append([InlineKeyboardButton(text=f"Мин • {min_nmp_required} {CURRENCY_SHORT}", callback_data=f"ex_confirm_sell:{buyer_id}:{min_nmp_required}", style="primary")])
    buttons.append([InlineKeyboardButton(text="⬅️ назад", callback_data="ex_list_sell:0", style="primary")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_edit_message(callback.message, text, reply_markup=kb)
    await state.set_state(ExchangeState.waiting_for_sell_amount_text)

@router.message(ExchangeState.waiting_for_sell_amount_text, F.text)
async def process_sell_amount_text(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    data = await state.get_data()
    buyer_id = data.get("sell_buyer_id")
    buyer_rate = data.get("sell_rate", 0)
    if not buyer_id:
        await state.clear()
        return
        
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0 or not val.is_integer(): raise ValueError
        amount = int(val)
    except ValueError:
        await safe_answer_message(message, f"{PE_CROSS} <b>Введите корректное целое число!</b>")
        return

    if (amount * buyer_rate) < MIN_BUY_NCOIN:
        await safe_answer_message(
            message,
            f"{PE_CROSS} <b>Минимальная сумма сделки — {MIN_BUY_NCOIN} nCoin!</b>\n"
            f"Вам необходимо продать минимум: <b>{(MIN_BUY_NCOIN + buyer_rate - 1) // buyer_rate} {CURRENCY_SHORT}</b>"
        )
        return
        
    await show_sell_confirm_screen(message, state, buyer_id, amount)

@router.callback_query(F.data.startswith("ex_confirm_sell:"))
async def process_sell_confirm_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    buyer_id = int(parts[1])
    amount = int(parts[2])
    
    if buyer_id == callback.from_user.id:
        await callback.answer("❌ Нельзя продавать самому себе!", show_alert=True)
        return

    buyer = db.get_user(buyer_id)
    rate = int(buyer.get("buy_rate", 0)) if buyer else 0
    if (amount * rate) < MIN_BUY_NCOIN:
        await safe_answer_message(callback.message, f"{PE_CROSS} Минимальная сумма сделки: {MIN_BUY_NCOIN} nCoin!")
        return
        
    await show_sell_confirm_screen(callback.message, state, buyer_id, amount, is_edit=True)

async def show_sell_confirm_screen(message_or_cb, state: FSMContext, buyer_id: int, amount: int, is_edit: bool = False):
    buyer = db.get_user(buyer_id)
    if not buyer: return
    
    rate = int(buyer.get("buy_rate", 0))
    seller_id = message_or_cb.chat.id if isinstance(message_or_cb, Message) else message_or_cb.from_user.id
    seller = db.get_user(seller_id)
    seller_name = html.escape(seller.get("first_name") or seller.get("username") or f"{seller_id}")
    
    total_reward = amount * rate
    if total_reward < MIN_BUY_NCOIN:
        text_err = f"{PE_CROSS} Минимальная сумма сделки — {MIN_BUY_NCOIN} nCoin!"
        if is_edit: await safe_edit_message(message_or_cb, text_err)
        else: await safe_answer_message(message_or_cb, text_err)
        return

    if seller.get("nmp_balance", 0) < amount:
        text_err = f"{PE_CROSS} У вас недостаточно {CURRENCY_NAME} для продажи!"
        if is_edit: await safe_edit_message(message_or_cb, text_err)
        else: await safe_answer_message(message_or_cb, text_err)
        return

    rate_fmt = f"{rate:,}".replace(",", "'")
    reward_fmt = f"{total_reward:,}".replace(",", "'")
    
    text = (
        f"{PE_ATM} <b>ПОДТВЕРЖДЕНИЕ СДЕЛКИ</b>\n"
        "..................................................\n\n"
        f"<b>{seller_name}</b>, ты точно хочешь продать <b>{amount} {CURRENCY_NAME}</b> за <b>{reward_fmt} nCoin</b>?\n\n"
        f"<blockquote>{PE_MONEY} Курс: {rate_fmt} nCoin</blockquote>\n"
        f"<blockquote>{PE_CIRCLE} Комиссия: 0% = 0 nCoin</blockquote>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да ✅", callback_data=f"ex_exec_sell:{buyer_id}:{amount}", style="success")],
        [InlineKeyboardButton(text="Отмена 💢", callback_data="ex_list_sell:0", style="danger")]
    ])
    
    await state.clear()
    
    if is_edit:
        await safe_edit_message(message_or_cb, text, reply_markup=kb)
    else:
        await safe_answer_message(message_or_cb, text, reply_markup=kb)

@router.callback_query(F.data.startswith("ex_exec_sell:"))
async def execute_sell(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await state.clear()
    
    parts = callback.data.split(":")
    buyer_id = int(parts[1])
    amount = int(parts[2])
    seller_id = callback.from_user.id

    if seller_id == buyer_id:
        await safe_edit_message(callback.message, f"{PE_CROSS} <b>Сделка отклонена: нельзя торговать с собой!</b>")
        return
    
    seller = db.get_user(seller_id)
    buyer = db.get_user(buyer_id)
    
    if not buyer or not seller: return
    rate = int(buyer.get("buy_rate", 0))
    reward = amount * rate
    
    if reward < MIN_BUY_NCOIN:
        await safe_edit_message(callback.message, f"{PE_CROSS} <b>Минимальная сумма сделки: {MIN_BUY_NCOIN} nCoin!</b>")
        return

    if seller.get("nmp_balance", 0) < amount:
        await safe_edit_message(callback.message, f"{PE_CROSS} <b>У вас недостаточно {CURRENCY_NAME} для продажи!</b>")
        return
        
    if buyer.get("exchange_balance", 0) < reward:
        await safe_edit_message(callback.message, f"{PE_CROSS} <b>Сделка отклонена! Покупатель изменил депозит.</b>")
        return

    # Атомарно проводим транзакцию
    db.update_nmp_balance(seller_id, -amount)
    db.update_balance(seller_id, reward)
    db.update_exchange_balance(buyer_id, -reward)
    db.update_nmp_balance(buyer_id, amount)
    
    seller_name = html.escape(callback.from_user.first_name or callback.from_user.username or f"{seller_id}")
    buyer_name = html.escape(buyer.get("first_name") or buyer.get("username") or f"{buyer_id}")
    
    deal_id = db.add_exchange_history(buyer_id, f"Купил у {seller_name}", amount, reward, "BUY")
    db.add_exchange_history(seller_id, f"Продал {buyer_name}", amount, reward, "SELL")
    
    reward_fmt = f"{reward:,}".replace(",", "'")
    rate_fmt = f"{rate:,}".replace(",", "'")
    
    text = (
        f"{PE_GREEN} <b>УСПЕШНАЯ ПРОДАЖА</b>\n"
        "..................................................\n\n"
        f"<b>{seller_name}</b>, ты продал <b>{amount} {CURRENCY_NAME}</b> за <b>{reward_fmt} nCoin</b>!\n\n"
        f"<blockquote>{PE_MONEY} По курсу: {rate_fmt} nCoin</blockquote>\n"
        f"<blockquote>{PE_INFO} Вы можете оценить сделку с <b>{buyer_name}</b>.</blockquote>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✔️ Рейтинг +1", callback_data=f"ex_rate:{deal_id}:{buyer_id}:1", style="success"),
            InlineKeyboardButton(text="🔻 Рейтинг -1", callback_data=f"ex_rate:{deal_id}:{buyer_id}:-1", style="danger")
        ]
    ])
    
    await safe_edit_message(callback.message, text, reply_markup=kb)
    await notify_buyer_success(bot, buyer_id, amount, reward, rate)

# ==============================================================================
# 🌟 ОЦЕНКА ПОСЛЕ СДЕЛКИ
# ==============================================================================

@router.callback_query(F.data.startswith("ex_rate:"))
async def process_rating_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    deal_id = int(parts[1])
    target_user_id = int(parts[2])
    stars = 5 if int(parts[3]) > 0 else 1
    from_user_id = callback.from_user.id

    if from_user_id == target_user_id:
        await callback.answer("❌ Нельзя оценивать самого себя!", show_alert=True)
        return

    db.add_rating(deal_id, from_user_id, target_user_id, stars)
    await callback.answer("Сделка успешно оценена! 😊", show_alert=False)
    
    text = f"{PE_CHECK} <b>Сделка успешно оценена!</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="ex_back_main", style="primary")]
    ])
    await safe_edit_message(callback.message, text, reply_markup=kb)

# --- 🏛 ОФИЦИАЛЬНАЯ ПРОДАЖА СКУПЩИКУ ---

@router.callback_query(F.data == "ex_off_sell")
async def official_sell_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    text = (
        f"{PE_TEMPLE} <b>ОФИЦИАЛЬНАЯ ПРОДАЖА {CURRENCY_NAME}</b>\n"
        "⠀\n"
        f"<i>{PE_LIGHTNING} Мгновенная скупка ботом в один клик</i>\n\n"
        f"{PE_CHART} <b>УСЛОВИЯ ОБМЕНА</b>\n"
        f" ├ 🏷 <b>Курс скупки:</b> <code>{OFFICIAL_SELL_RATE:,} nCoin / 1 {CURRENCY_NAME}</code>\n"
        f" └ {PE_GEM} <b>Ваш баланс:</b> <code>{int(user['nmp_balance']):,} {CURRENCY_NAME}</code>\n\n"
        f"{PE_WRITE} <b>Введите количество {CURRENCY_NAME}, которое хотите продать (целое число):</b>"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_back_kb())
    await state.set_state(ExchangeState.waiting_for_off_sell_amount)

@router.message(ExchangeState.waiting_for_off_sell_amount, F.text)
async def official_sell_process(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0 or not val.is_integer(): raise ValueError
        amount = int(val)
    except ValueError:
        await safe_answer_message(message, f"{PE_CROSS} <b>Введите корректное целое число больше 0!</b>")
        return
        
    if user.get("nmp_balance", 0) < amount:
        await safe_answer_message(
            message,
            f"{PE_CROSS} <b>Недостаточно {CURRENCY_NAME}!</b>\n\n"
            f"У вас в наличии: <code>{int(user.get('nmp_balance', 0)):,} {CURRENCY_NAME}</code>"
        )
        await state.clear()
        return

    reward = amount * OFFICIAL_SELL_RATE
    db.update_nmp_balance(user_id, -amount)
    db.update_balance(user_id, reward)
    db.add_exchange_history(user_id, "Официальный скупщик", amount, reward, "SELL")
    
    await state.clear()
    
    text = (
        f"{PE_PARTY} <b>МГНОВЕННЫЙ ОБМЕН УСПЕШНО СОВЕРШЕН!</b>\n"
        "⠀\n"
        f" ├ {PE_OUTBOX} <b>Продано:</b> <code>{amount:,} {CURRENCY_NAME}</code>\n"
        f" ├ {PE_MONEY} <b>Зачислено:</b> <code>+{reward:,} nCoin</code>\n"
        f" └ {PE_CARD} <b>Новый баланс nCoin:</b> <code>{int(db.get_user(user_id)['balance']):,}</code>"
    )
    await safe_answer_message(message, text)
    await show_exchange_main(message, state)

# --- ПАНЕЛЬ УПРАВЛЕНИЯ И ДЕПОЗИТЫ ---

@router.callback_query(F.data == "ex_control_panel")
async def show_control_panel(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    rating_str = db.get_user_rating(user_id)
    
    text = (
        f"{PE_GEAR} <b>ПАНЕЛЬ УПРАВЛЕНИЯ БИРЖЕЙ</b>\n"
        f"{PE_MONEY * 7}\n"
        f"{PE_STAR} <b>Ваш рейтинг:</b> <code>{rating_str}</code>\n\n"
        f"{PE_CARD} <b>ЛИЧНЫЙ КОШЕЛЕК</b>\n"
        f" ├ {PE_MONEY} nCoin: <code>{int(user.get('balance', 0)):,}</code>\n"
        f" └ {PE_GEM} {CURRENCY_NAME}: <code>{int(user.get('nmp_balance', 0)):,}</code>\n\n"
        f"{PE_BOX} <b>ДЕПОЗИТЫ НА БИРЖЕ (ОРДЕРА В СТАКАНЕ)</b>\n"
        f" ├ {PE_MONEY} nCoin: <code>{int(user.get('exchange_balance', 0)):,}</code>\n"
        f" └ {PE_GEM} {CURRENCY_NAME}: <code>{int(user.get('exchange_nmp_balance', 0)):,}</code>\n\n"
        f"{PE_GEAR} <b>КУРСЫ В СТАКАНЕ</b>\n"
        f" ├ {PE_CHART} Покупка {CURRENCY_NAME} по: <code>{int(user.get('buy_rate', 2100)):,} nCoin</code>\n"
        f" └ {PE_CHART} Продажа {CURRENCY_NAME} по: <code>{int(user.get('sell_rate', 2100)):,} nCoin</code>"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_control_panel_kb(user_id))

@router.callback_query(F.data == "ex_deposit_menu")
async def deposit_menu(callback: CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Депозит nCoin на биржу", callback_data="ex_dep_ncoin", style="primary")],
        [InlineKeyboardButton(text=f"💎 Депозит {CURRENCY_NAME} на биржу", callback_data="ex_dep_nmp", style="primary")],
        [InlineKeyboardButton(text="⬅️ назад в панель", callback_data="ex_control_panel", style="primary")]
    ])
    await safe_edit_message(callback.message, f"{PE_INBOX} <b>Выберите валюту для депозита:</b>", reply_markup=kb)

@router.callback_query(F.data == "ex_dep_ncoin")
async def dep_ncoin_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        f"{PE_INBOX} <b>ДЕПОЗИТ nCoin НА БИРЖУ</b>\n"
        "⠀\n"
        f"{PE_CARD} Твой баланс кошелька: <code>{int(user.get('balance', 0)):,} nCoin</code>\n"
        f"{PE_CROSS} Минимальный депозит: <code>{MIN_BUY_NCOIN:,} nCoin</code>\n\n"
        f"{PE_WRITE} <b>Введите сумму nCoin для перевода на биржу (целое число):</b>"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_back_to_control_kb())
    await state.set_state(ExchangeState.waiting_for_deposit_ncoin)

@router.message(ExchangeState.waiting_for_deposit_ncoin, F.text)
async def dep_ncoin_process(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)
    try:
        amount = utils.parse_bet_input(message.text, user.get("balance", 0))
    except Exception:
        await safe_answer_message(message, f"{PE_CROSS} <b>Неверный ввод суммы!</b>")
        return
    
    if amount <= 0 or not float(amount).is_integer():
        await safe_answer_message(message, f"{PE_CROSS} <b>Сумма перевода должна быть целым числом больше нуля!</b>")
        return
    amount = int(amount)

    if amount < MIN_BUY_NCOIN:
        await safe_answer_message(message, f"{PE_CROSS} <b>Минимальная сумма депозита на биржу: {MIN_BUY_NCOIN} nCoin!</b>")
        return
        
    if user.get("balance", 0) < amount:
        await safe_answer_message(message, f"{PE_CROSS} <b>Недостаточно nCoin в кошельке!</b>")
        await state.clear()
        return
        
    db.update_balance(user_id, -amount)
    db.update_exchange_balance(user_id, amount)
    
    await safe_answer_message(message, f"{PE_CHECK} <b>Успешно пополнено +{amount:,} nCoin на биржевой счет!</b>")
    await show_exchange_main(message, state)

@router.callback_query(F.data == "ex_dep_nmp")
async def dep_nmp_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        f"{PE_INBOX} <b>ДЕПОЗИТ {CURRENCY_NAME} НА БИРЖУ</b>\n"
        "⠀\n"
        f"{PE_GEM} Твой баланс {CURRENCY_NAME}: <code>{int(user.get('nmp_balance', 0)):,} {CURRENCY_NAME}</code>\n\n"
        f"{PE_WRITE} <b>Введите сумму {CURRENCY_NAME} для перевода на биржу (целое число):</b>"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_back_to_control_kb())
    await state.set_state(ExchangeState.waiting_for_deposit_nmp)

@router.message(ExchangeState.waiting_for_deposit_nmp, F.text)
async def dep_nmp_process(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)
    try:
        amount = utils.parse_bet_input(message.text, user.get("nmp_balance", 0))
    except Exception:
        await safe_answer_message(message, f"{PE_CROSS} <b>Неверный ввод суммы!</b>")
        return
    
    if amount <= 0 or not float(amount).is_integer():
        await safe_answer_message(message, f"{PE_CROSS} <b>Сумма перевода должна быть целым числом больше нуля!</b>")
        return
    amount = int(amount)
        
    if user.get("nmp_balance", 0) < amount:
        await safe_answer_message(message, f"{PE_CROSS} <b>Недостаточно {CURRENCY_NAME} в кошельке!</b>")
        await state.clear()
        return
        
    db.update_nmp_balance(user_id, -amount)
    db.update_exchange_nmp_balance(user_id, amount)
    
    await safe_answer_message(message, f"{PE_CHECK} <b>Успешно пополнено +{amount:,} {CURRENCY_NAME} на биржевой счет!</b>")
    await show_exchange_main(message, state)

@router.callback_query(F.data == "ex_withdraw_menu")
async def withdraw_menu(callback: CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Вывод nCoin в кошелек", callback_data="ex_wd_ncoin", style="primary")],
        [InlineKeyboardButton(text=f"💎 Вывод {CURRENCY_NAME} в кошелек", callback_data="ex_wd_nmp", style="primary")],
        [InlineKeyboardButton(text="⬅️ назад в панель", callback_data="ex_control_panel", style="primary")]
    ])
    await safe_edit_message(callback.message, f"{PE_OUTBOX} <b>Выберите валюту для вывода:&lt;/b&gt;", reply_markup=kb)

@router.callback_query(F.data == "ex_wd_ncoin")
async def wd_ncoin_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        f"{PE_OUTBOX} <b>ВЫВОД nCoin В КОШЕЛЕК</b>\n"
        "⠀\n"
        f"{PE_CARD} На биржевом счете: <code>{int(user.get('exchange_balance', 0)):,} nCoin</code>\n\n"
        f"{PE_WRITE} <b>Введите сумму nCoin для вывода (целое число):</b>"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_back_to_control_kb())
    await state.set_state(ExchangeState.waiting_for_withdraw_ncoin)

@router.message(ExchangeState.waiting_for_withdraw_ncoin, F.text)
async def wd_ncoin_process(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)
    try:
        amount = utils.parse_bet_input(message.text, user.get("exchange_balance", 0))
    except Exception:
        await safe_answer_message(message, f"{PE_CROSS} <b>Неверный ввод суммы!</b>")
        return
    
    if amount <= 0 or not float(amount).is_integer():
        await safe_answer_message(message, f"{PE_CROSS} <b>Введите целое положительное число!</b>")
        return
    amount = int(amount)
        
    if user.get("exchange_balance", 0) < amount:
        await safe_answer_message(message, f"{PE_CROSS} <b>Недостаточно nCoin на биржевом счете!</b>")
        return
        
    db.update_exchange_balance(user_id, -amount)
    db.update_balance(user_id, amount)
    
    await safe_answer_message(message, f"{PE_CHECK} <b>Успешно выведено {amount:,} nCoin на ваш основной кошелек!</b>")
    await show_exchange_main(message, state)

@router.callback_query(F.data == "ex_wd_nmp")
async def wd_nmp_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        f"{PE_OUTBOX} <b>ВЫВОД {CURRENCY_NAME} В КОШЕЛЕК</b>\n"
        "⠀\n"
        f"{PE_GEM} На биржевом счете: <code>{int(user.get('exchange_nmp_balance', 0)):,} {CURRENCY_NAME}</code>\n\n"
        f"{PE_WRITE} <b>Введите количество {CURRENCY_NAME} для вывода (целое число):</b>"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_back_to_control_kb())
    await state.set_state(ExchangeState.waiting_for_withdraw_nmp)

@router.message(ExchangeState.waiting_for_withdraw_nmp, F.text)
async def wd_nmp_process(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    user_id = message.from_user.id
    user = db.get_user(user_id)
    try:
        amount = utils.parse_bet_input(message.text, user.get("exchange_nmp_balance", 0))
    except Exception:
        await safe_answer_message(message, f"{PE_CROSS} <b>Неверный ввод суммы!</b>")
        return
    
    if amount <= 0 or not float(amount).is_integer():
        await safe_answer_message(message, f"{PE_CROSS} <b>Введите целое положительное число!</b>")
        return
    amount = int(amount)
        
    if user.get("exchange_nmp_balance", 0) < amount:
        await safe_answer_message(message, f"{PE_CROSS} <b>Недостаточно {CURRENCY_NAME} на биржевом счете!</b>")
        return
        
    db.update_exchange_nmp_balance(user_id, -amount)
    db.update_nmp_balance(user_id, amount)
    
    await safe_answer_message(message, f"{PE_CHECK} <b>Успешно выведено {amount:,} {CURRENCY_NAME} на ваш основной кошелек!</b>")
    await show_exchange_main(message, state)

@router.callback_query(F.data == "ex_rate_buy")
async def rate_buy_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        f"{PE_CHART} <b>НАСТРОЙКА КУРСА ПОКУПКИ {CURRENCY_NAME}</b>\n"
        "⠀\n"
        f"{PE_CHART} Твой текущий курс: <code>{int(user.get('buy_rate', 2100)):,} nCoin</code>\n"
        f"{PE_INFO} Допустимый диапазон: <code>{MIN_RATE_LIMIT:,} - {MAX_RATE_LIMIT:,} nCoin</code>\n\n"
        f"{PE_WRITE} <b>Введите новый курс покупки за 1 {CURRENCY_NAME} (целое число):</b>"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_back_to_control_kb())
    await state.set_state(ExchangeState.waiting_for_buy_rate)

@router.message(ExchangeState.waiting_for_buy_rate, F.text)
async def rate_buy_process(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    user_id = message.from_user.id
    try:
        val = float(message.text.replace(",", "."))
        if val < MIN_RATE_LIMIT or val > MAX_RATE_LIMIT or not val.is_integer(): raise ValueError
        new_rate = int(val)
    except ValueError:
        await safe_answer_message(
            message,
            f"{PE_CROSS} <b>Введите целое число в диапазоне от {MIN_RATE_LIMIT:,} до {MAX_RATE_LIMIT:,} nCoin!</b>"
        )
        return
        
    db.update_user_field(user_id, "buy_rate", float(new_rate))
    await safe_answer_message(message, f"{PE_CHECK} <b>Курс покупки {CURRENCY_NAME} успешно изменен на {new_rate:,} nCoin!</b>")
    await show_exchange_main(message, state)

@router.callback_query(F.data == "ex_rate_sell")
async def rate_sell_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        f"{PE_CHART} <b>НАСТРОЙКА КУРСА ПРОДАЖИ {CURRENCY_NAME}</b>\n"
        "⠀\n"
        f"{PE_CHART} Твой текущий курс: <code>{int(user.get('sell_rate', 2100)):,} nCoin</code>\n"
        f"{PE_INFO} Допустимый диапазон: <code>{MIN_RATE_LIMIT:,} - {MAX_RATE_LIMIT:,} nCoin</code>\n\n"
        f"{PE_WRITE} <b>Введите новый курс продажи 1 {CURRENCY_NAME} (целое число):</b>"
    )
    await safe_edit_message(callback.message, text, reply_markup=get_back_to_control_kb())
    await state.set_state(ExchangeState.waiting_for_sell_rate)

@router.message(ExchangeState.waiting_for_sell_rate, F.text)
async def rate_sell_process(message: Message, state: FSMContext):
    if is_exchange_command(message.text):
        await show_exchange_main(message, state)
        return

    user_id = message.from_user.id
    try:
        val = float(message.text.replace(",", "."))
        if val < MIN_RATE_LIMIT or val > MAX_RATE_LIMIT or not val.is_integer(): raise ValueError
        new_rate = int(val)
    except ValueError:
        await safe_answer_message(
            message,
            f"{PE_CROSS} <b>Введите целое число в диапазоне от {MIN_RATE_LIMIT:,} до {MAX_RATE_LIMIT:,} nCoin!</b>"
        )
        return
        
    db.update_user_field(user_id, "sell_rate", float(new_rate))
    await safe_answer_message(message, f"{PE_CHECK} <b>Курс продажи {CURRENCY_NAME} успешно изменен на {new_rate:,} nCoin!</b>")
    await show_exchange_main(message, state)

@router.callback_query(F.data == "ex_toggle_notif")
async def toggle_notifications(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    new_status = int(not user.get("exchange_notifications", True))
    db.update_user_field(user_id, "exchange_notifications", new_status)
    
    notif_word = "ВКЛЮЧЕНЫ" if new_status else "ВЫКЛЮЧЕНЫ"
    await callback.answer(f"🔔 Уведомления об обменах {notif_word}!", show_alert=True)
    await show_control_panel(callback)

@router.callback_query(F.data.startswith("ex_history_page:"))
async def show_exchange_history(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.split(":")[1])
    per_page = 5
    
    rows, total = db.get_exchange_history(page, per_page)
    
    text = f"{PE_CHART} <b>ИСТОРИЯ СДЕЛОК</b>\n"
    if not rows:
        text += "🕸 <i>Здесь пока нет совершенных сделок.</i>"
    else:
        for r in rows:
            username, nmp_amount, ncoin_amount, tx_type, timestamp = r
            emoji = PE_GREEN if tx_type == "BUY" else PE_RED
            date_str = time.strftime('%d-%m %H:%M', time.localtime(timestamp))
            u_clean = html.escape(str(username))
            text += (
                f"{emoji} <b>{tx_type}</b> | <code>{int(nmp_amount):,} {CURRENCY_NAME}</code> на <code>{int(ncoin_amount):,} nCoin</code>\n"
                f" └ {PE_USER} <i>Партнер: {u_clean} ({date_str})</i>\n\n"
            )
            
    kb_list = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"ex_history_page:{page-1}", style="primary"))
    if (page + 1) * per_page < total:
        nav_buttons.append(InlineKeyboardButton(text="След. ➡️", callback_data=f"ex_history_page:{page+1}", style="primary"))
        
    if nav_buttons:
        kb_list.append(nav_buttons)
    kb_list.append([InlineKeyboardButton(text="⬅️ назад", callback_data="ex_back_main", style="primary")])
    
    await safe_edit_message(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))
