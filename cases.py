# cases.py
import asyncio
import random
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import db
import utils

logger = logging.getLogger(__name__)
router = Router()

PREMIUM_EMOJIS = {
    "chest_bronze": '<tg-emoji emoji-id="5854908544712707500">📦</tg-emoji>',   # Бронзовый сундук
    "chest_silver": '<tg-emoji emoji-id="5445221832074483553">💼</tg-emoji>',   # Серебряный сундук
    "chest_gold":   '<tg-emoji emoji-id="5769547529993588669">👑</tg-emoji>',   # Золотой сундук
    "chest_nft":    '<tg-emoji emoji-id="5390922055199765568">🏎️</tg-emoji>',   # NFT кейс

    "drop_ncoin":   '<tg-emoji emoji-id="5375312095346704820">💰</tg-emoji>',   # Выпали nCoin
    "drop_nmp":     '<tg-emoji emoji-id="5767137507879685567">💎</tg-emoji>',   # Выпали NMP
    "drop_brick":   '<tg-emoji emoji-id="5391179937921117661">🧱</tg-emoji>',   # Выпал Кирпич
    "drop_lightning":'<tg-emoji emoji-id="5890847821728322055">⚡️</tg-emoji>',  # Выпала Молния
    "drop_nft":     '<tg-emoji emoji-id="5188344996356448758">🏆</tg-emoji>',   # Выпал NFT
    
    "spin_icon":    '<tg-emoji emoji-id="5969709082049779216">🎰</tg-emoji>',   # Иконка вращения
    "arrow_right":  '<tg-emoji emoji-id="5462881955911584183">➡️</tg-emoji>'# Стрелка
}

CASE_IMAGES = {
    "main": "https://i.ibb.co/TD0JmKdN/IMG-20260827-165506-895.jpg",
    "bronze": "https://i.ibb.co/ZRtd0LCs/IMG-20260826-171935-862.jpg",
    "silver": "https://i.ibb.co/JRbyj64X/IMG-20260826-172554-487.jpg",
    "gold": "https://i.ibb.co/5XjLY7xd/IMG-20260826-173005-576.jpg",
    "nft": "https://i.ibb.co/fdMC53J4/IMG-20260822-223936-172.jpg"
}

CASES = {
    "bronze": {
        "name": "Бронзовый Сундук",
        "price": 40000,
        "image": CASE_IMAGES["bronze"],
        "emoji": PREMIUM_EMOJIS["chest_bronze"],
        "drops": [
            {"type": "ncoin", "val": 10000, "weight": 40, "name": "10,000 nCoin"},
            {"type": "ncoin", "val": 30000, "weight": 35, "name": "30,000 nCoin"},
            {"type": "ncoin", "val": 75000, "weight": 15, "name": "75,000 nCoin"},
            {"type": "brick", "val": 1,     "weight": 8,  "name": "1х Кирпич 🧱"},
            {"type": "nmp",   "val": 5,     "weight": 2,  "name": "5 NMP Алмазов 💎"}
        ]
    },
    "silver": {
        "name": "Серебряный Сундук",
        "price": 100000,
        "image": CASE_IMAGES["silver"],
        "emoji": PREMIUM_EMOJIS["chest_silver"],
        "drops": [
            {"type": "ncoin", "val": 50000,  "weight": 35, "name": "50,000 nCoin"},
            {"type": "ncoin", "val": 150000, "weight": 35, "name": "150,000 nCoin"},
            {"type": "brick", "val": 2,      "weight": 15, "name": "2х Кирпича 🧱"},
            {"type": "lightning", "val": 1,  "weight": 10, "name": "1х Грозовой Разряд ⚡️"},
            {"type": "nmp",   "val": 25,     "weight": 5,  "name": "25 NMP Алмазов 💎"}
        ]
    },
    "gold": {
        "name": "Золотой Сундук",
        "price": 650000,
        "image": CASE_IMAGES["gold"],
        "emoji": PREMIUM_EMOJIS["chest_gold"],
        "drops": [
            {"type": "ncoin", "val": 250000, "weight": 30, "name": "250,000 nCoin"},
            {"type": "ncoin", "val": 750000, "weight": 30, "name": "750,000 nCoin"},
            {"type": "ncoin", "val": 2000000,"weight": 15, "name": "2,000,000 nCoin (Джекпот!)"},
            {"type": "lightning", "val": 3,  "weight": 15, "name": "3х Грозовых Разряда ⚡️"},
            {"type": "nmp",   "val": 100,    "weight": 10, "name": "100 NMP Алмазов 💎"}
        ]
    },
    "nft": {
        "name": "NFT Case",
        "price": 59000000,
        "image": CASE_IMAGES["nft"],
        "emoji": PREMIUM_EMOJIS["chest_nft"],
        "drops": [
            {"type": "ncoin", "val": 500000, "weight": 40, "name": "500,000 nCoin"},
            {"type": "ncoin", "val": 1500000,"weight": 30, "name": "1,500,000 nCoin"},
            {"type": "lightning", "val": 5,  "weight": 15, "name": "5х Грозовых Разрядов ⚡️"},
            {"type": "nft_drago", "val": 1,  "weight": 10, "name": "🦕 Редкий NFT «Драко»!"},
            {"type": "nft_car",   "val": 1,  "weight": 5,  "name": "🏎️ ЭКСКЛЮЗИВНЫЙ NFT «NM Hypercar»!"}
        ]
    }
}


def get_cases_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="🥉 Бронзовый (40k nCoin)", callback_data="case_view:bronze")],
        [InlineKeyboardButton(text="🥈 Серебряный (100k nCoin)", callback_data="case_view:silver")],
        [InlineKeyboardButton(text="🥇 Золотой (650k nCoin)", callback_data="case_view:gold")],
        [InlineKeyboardButton(text="🏎️ NFT Case (59.0M nCoin)", callback_data="case_view:nft")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="back_to_start")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- ГЛАВНОЕ МЕНЮ КЕЙСОВ ---

@router.message(Command("cases"))
@router.message(F.text.lower().in_(["кейсы", "сундуки", "кейс"]))
async def open_cases_menu(event):
    user_id = event.from_user.id
    user = db.get_user(user_id)
    
    text = (
        f"<b>{PREMIUM_EMOJIS['chest_gold']} ИГРОВЫЕ КЕЙСЫ И СУНДУКИ {PREMIUM_EMOJIS['chest_gold']}</b>\n"
        "➖➖➖➖➖➖➖➖➖➖➖\n"
        "Испытайте удачу и выбивайте ценные призы: монеты, алмазы, оборудование и <b>эксклюзивные NFT-экспонаты</b>!\n\n"
        f"💳 Ваш баланс: <b>{user['balance']:,} nCoin</b>\n\n"
        "👇 <b>Выберите кейс для просмотра дропа:</b>"
    )
    kb = get_cases_keyboard()
    
    if isinstance(event, Message):
        await event.answer_photo(photo=CASE_IMAGES["main"], caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.message.edit_media(
            media=InputMediaPhoto(media=CASE_IMAGES["main"], caption=text, parse_mode="HTML"),
            reply_markup=kb
        )


# --- ПРОСМОТР КОНКРЕТНОГО КЕЙСА ---

@router.callback_query(F.data.startswith("case_view:"))
async def view_case_callback(call: CallbackQuery):
    await call.answer()
    case_key = call.data.split(":")[1]
    case_info = CASES.get(case_key)
    if not case_info:
        return
        
    user = db.get_user(call.from_user.id)
    
    text = (
        f"<b>{case_info['emoji']} {case_info['name'].upper()}</b>\n"
        "➖➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 Стоимость открытия: <b>{case_info['price']:,} nCoin</b>\n\n"
        "🎁 <b>Возможный дроп из этого сундука:</b>\n"
    )
    
    for drop in case_info["drops"]:
        text += f" ├ {drop['name']} <i>(Шанс: {drop['weight']}%)</i>\n"
        
    text += f"\n💳 Ваш баланс: <b>{user['balance']:,} nCoin</b>"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎰 Открыть за {case_info['price']:,} nCoin", callback_data=f"case_open:{case_key}")],
        [InlineKeyboardButton(text="🔙 Назад к кейсам", callback_data="cases_back")]
    ])
    
    try:
        await call.message.edit_media(
            media=InputMediaPhoto(media=case_info["image"], caption=text, parse_mode="HTML"),
            reply_markup=kb
        )
    except Exception:
        await call.message.answer_photo(photo=case_info["image"], caption=text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "cases_back")
async def cases_back_callback(call: CallbackQuery):
    await call.answer()
    await open_cases_menu(call)


# --- ПРОЦЕСС АНИМАЦИИ И ОТКРЫТИЯ КЕЙСА ---

@router.callback_query(F.data.startswith("case_open:"))
async def open_case_process(call: CallbackQuery):
    user_id = call.from_user.id
    user = db.get_user(user_id)
    case_key = call.data.split(":")[1]
    case_info = CASES.get(case_key)
    
    if not case_info:
        await call.answer("❌ Кейс не найден!", show_alert=True)
        return
        
    if user["balance"] < case_info["price"]:
        await call.answer(f"❌ Недостаточно nCoin! Нужно: {case_info['price']:,} nCoin", show_alert=True)
        return
        
    # Списываем баланс за покупку
    db.update_balance(user_id, -case_info["price"])
    await call.answer("🎰 Открываем сундук...")
    
    # 1. Выбираем случайный выигрыш на основе шансов (weights)
    drops = case_info["drops"]
    weights = [d["weight"] for d in drops]
    win_drop = random.choices(drops, weights=weights, k=1)[0]
    
    # 2. Кадры анимации вращения (рулетка)
    animation_frames = [
        f"{PREMIUM_EMOJIS['spin_icon']} [ 💰 | 🧱 | 💎 | ⚡️ | 🏎️ ]",
        f"{PREMIUM_EMOJIS['spin_icon']} [ ⚡️ | 💰 | 🏎️ | 💎 | 🧱 ]",
        f"{PREMIUM_EMOJIS['spin_icon']} [ 💎 | ⚡️ | 💰 | 🧱 | 🏎️ ]",
        f"{PREMIUM_EMOJIS['spin_icon']} [ 🏎️ | 💎 | 🧱 | 💰 | ⚡️ ]"
    ]
    
    # Запуск динамической рулетки
    for frame in animation_frames:
        caption_spin = (
            f"<b>{case_info['emoji']} РУЛЕТКА КРУТИТСЯ...</b>\n"
            "➖➖➖➖➖➖➖➖➖➖➖\n\n"
            f"🎰 {frame}\n\n"
            "⏳ <i>Определяем случайный приз...</i>"
        )
        try:
            await call.message.edit_caption(caption=caption_spin, parse_mode="HTML")
        except Exception:
            pass
        await asyncio.sleep(0.6)
        
    # 3. Начисление награды в БД
    reward_type = win_drop["type"]
    reward_val = win_drop["val"]
    
    icon_win = PREMIUM_EMOJIS["drop_ncoin"]
    extra_msg = ""
    
    if reward_type == "ncoin":
        db.update_balance(user_id, reward_val)
        icon_win = PREMIUM_EMOJIS["drop_ncoin"]
    elif reward_type == "nmp":
        db.update_nmp_balance(user_id, reward_val)
        icon_win = PREMIUM_EMOJIS["drop_nmp"]
    elif reward_type == "brick":
        db.update_bricks(user_id, reward_val)
        icon_win = PREMIUM_EMOJIS["drop_brick"]
    elif reward_type == "lightning":
        if hasattr(db, "update_lightnings"):
            db.update_lightnings(user_id, reward_val)
        else:
            db.update_user_field(user_id, "lightnings", user.get("lightnings", 0) + reward_val)
        icon_win = PREMIUM_EMOJIS["drop_lightning"]
    elif reward_type == "nft_drago":
        nft_id = db.create_nft(user_id, "Драко")
        icon_win = PREMIUM_EMOJIS["drop_nft"]
        extra_msg = f"\n🎉 <b>Поздравляем! Вы получли редкий NFT Драко #{nft_id}!</b>"
    elif reward_type == "nft_car":
        nft_id = db.create_nft(user_id, "NM Hypercar", image_key="base_car")
        icon_win = PREMIUM_EMOJIS["drop_nft"]
        extra_msg = f"\n🎉 <b>УСПЕХ НА ТВОЕЙ СТОРОНЕ! Вы получили NFT NM Hypercar #{nft_id}!</b>"

    user_updated = db.get_user(user_id)

    # 4. Финальное сообщение с выпавшим призом
    final_text = (
        f"<b>{case_info['emoji']} СУНДУК УСПЕШНО ОТКРЫТ!</b>\n"
        "➖➖➖➖➖➖➖➖➖➖➖\n"
        f"🎁 <b>Ваш выигрыш:</b> {icon_win} <b>{win_drop['name']}</b>{extra_msg}\n\n"
        "➖➖➖➖➖➖➖➖➖➖➖\n"
        f"💳 Ваш баланс: <b>{user_updated['balance']:,} nCoin</b>"
    )
    
    kb_win = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Открыть ещё раз", callback_data=f"case_open:{case_key}")],
        [InlineKeyboardButton(text="🎒 Вернутся", callback_data="cases_back")]
    ])
    
    try:
        await call.message.edit_caption(caption=final_text, reply_markup=kb_win, parse_mode="HTML")
    except Exception:
        await call.message.answer(final_text, reply_markup=kb_win, parse_mode="HTML")
