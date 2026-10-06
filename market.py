# market.py
import time
import random
import hashlib
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db

logger = logging.getLogger(__name__)
router = Router()

# ==============================================================================
# ⚙️ НАСТРОЙКИ И ЦЕНЫ (ЛЕГКО РЕДАКТИРОВАТЬ)
# ==============================================================================
BRICK_PRICE = 50000            # Стоимость кирпича в nCoin
LIGHTNING_PRICE = 39000        # Стоимость Грозового Разряда в nCoin
LIGHTNING_COOLDOWN = 450       # Кулдаун 7 минут 30 секунд (450 сек)

# 🦕 ЦЕНЫ И ЛИМИТЫ ДЛЯ ДРАКО:
NFT_DRAGO_PRICE = 999000        # Покупка Драко (nCoin)
NFT_DRAGO_UPGRADE_FEE = 50000   # Улучшение Драко (nCoin)
NFT_DRAGO_MAX_SUPPLY = 100      # МАКСИМУМ 100 ШТУК ДРАКО

# 🏎️ ЦЕНЫ И ЛИМИТЫ ДЛЯ NM HYPERCAR (МАШИН):
NFT_CAR_PRICE = 149900000       # Покупка NM Hypercar (nCoin)
NFT_CAR_UPGRADE_FEE = 100000    # Улучшение NM Hypercar (nCoin)
NFT_CAR_MAX_SUPPLY = 5          # СТРОГО МАКСИМУМ 5 ШТУК HYPERCAR

NFT_TRANSFER_FEE_PERCENT = 0.06 # 6% комиссия от стоимости перевода
ITEMS_PER_PAGE = 5              # Ограничение: 5 NFT на 1 страницу инвентаря

# Хранилище кулдаунов молнии {user_id: timestamp} и активных кушей
LAST_LIGHTNING_TIME = {}
ACTIVE_LIGHTNING_LOOTS = {}

# ==============================================================================
# 🎨 ИЗОБРАЖЕНИЯ ВСЕХ NFT (ДРАКО + HYPERCAR)
# ==============================================================================
DRAGO_IMAGES = {
    # 0. БАЗОВЫЕ КАРТИНКИ (1 Уровень)
    "base_green": "https://i.ibb.co/p6kZ2PNh/IMG-20260822-175450-939.jpg",
    "base_car": "https://i.ibb.co/676cy1tp/IMG-20260826-231927-757.jpg",

    # --- 10 СТАРЫХ ВАРИАНТОВ ДРАКО ---
    "ruby_flame": "https://i.ibb.co/7JLvY8MQ/IMG-20260822-223933-193.jpg",
    "emerald_cyber": "https://i.ibb.co/wrLsPDR4/IMG-20260822-223954-936.jpg",
    "gold_royal": "https://i.ibb.co/fdMC53J4/IMG-20260822-223936-172.jpg",
    "cosmic_space": "https://i.ibb.co/N6xH5qx2/IMG-20260822-223930-983.jpg",
    "neon_grid": "https://i.ibb.co/NdZ9ZmYZ/IMG-20260822-223928-669.jpg",
    "shadow_ninja": "https://i.ibb.co/LzrFj8Fx/IMG-20260822-223925-723.jpg",
    "ice_crystal": "https://i.ibb.co/RMDPXQt/IMG-20260822-223924-042.jpg",
    "electric_lightning": "https://i.ibb.co/5hM1BXTp/IMG-20260822-223909-351.jpg",
    "magma_lava": "https://i.ibb.co/gLVxMygc/IMG-20260822-223922-869.jpg",
    "rainbow_beach": "https://i.ibb.co/WWBq1LD7/IMG-20260822-223920-350.jpg",

    # --- 5 ВАРИАНТОВ NM HYPERCAR (МАШИНЫ НА ПОДСТАВКЕ) ---
    "car_cyber_neon": "https://i.ibb.co/twx2r5kY/IMG-20260826-225349-589.jpg",     # 1. Cyber Neon
    "car_gold_royal": "https://i.ibb.co/fdYk8jsv/IMG-20260826-225351-568.jpg",     # 2. Gold Royal
    "car_inferno_flame": "https://i.ibb.co/6c3XJM36/IMG-20260826-225352-981.jpg",   # 3. Inferno Flame
    "car_toxic_emerald": "https://i.ibb.co/q3Rhwx84/IMG-20260826-225542-870.jpg",  # 4. Toxic Emerald
    "car_cosmic_galaxy": "https://i.ibb.co/R4McrdcF/IMG-20260826-225726-014.jpg"   # 5. Cosmic Galaxy
}

# ==============================================================================
# 💎 ПУЛЫ УЛУЧШЕНИЙ (ОТДЕЛЬНО ДЛЯ ДРАКО И ДЛЯ МАШИН)
# ==============================================================================
DRAGO_UPGRADES = [
    {"key": "ruby_flame", "color": "Рубиновый Драко", "pattern": "Огненный узор", "outfit": "Кожаная куртка и очки", "rarity": "🔥 Эпический", "estimated_price": "2,500,000 nCoin"},
    {"key": "emerald_cyber", "color": "Изумрудный Драко", "pattern": "Кибер-линии", "outfit": "Худи с капюшоном", "rarity": "⚡️ Редкий", "estimated_price": "1,800,000 nCoin"},
    {"key": "gold_royal", "color": "Золотой Драко", "pattern": "Королевский узор", "outfit": "Смокинг и корона", "rarity": "👑 Легендарный", "estimated_price": "5,000,000 nCoin"},
    {"key": "cosmic_space", "color": "Космический Драко", "pattern": "Галактика и звёзды", "outfit": "Космический скафандр", "rarity": "🌌 Мифический", "estimated_price": "4,000,000 nCoin"},
    {"key": "shadow_ninja", "color": "Теневой Драко", "pattern": "Дымчатый туман", "outfit": "Костюм ниндзя", "rarity": "🥷 Эпический", "estimated_price": "2,800,000 nCoin"},
    {"key": "ice_crystal", "color": "Ледяной Драко", "pattern": "Морозные кристаллы", "outfit": "Зимнее пальто и шапка", "rarity": "❄️ Редкий", "estimated_price": "1,900,000 nCoin"},
    {"key": "magma_lava", "color": "Магма Драко", "pattern": "Лавовые трещины", "outfit": "Рыцарские доспехи", "rarity": "🌋 Легендарный", "estimated_price": "3,800,000 nCoin"}
]

CAR_UPGRADES = [
    {"key": "car_cyber_neon", "color": "Неоново-Голубой Hypercar", "pattern": "Кибер-сетка и логотип NM", "outfit": "Тёмный поднос с гравировкой NM", "rarity": "⚡️ Эпический", "estimated_price": "3,500,000 nCoin"},
    {"key": "car_gold_royal", "color": "Золотой Hypercar", "pattern": "Королевский герб и винил NM", "outfit": "Мраморный пьедестал NM & Корона", "rarity": "👑 Легендарный", "estimated_price": "7,500,000 nCoin"},
    {"key": "car_inferno_flame", "color": "Огненно-Алый Hypercar", "pattern": "Языки пламени NMines", "outfit": "Угольный карбоновый стенд NM", "rarity": "🔥 Эпический", "estimated_price": "4,200,000 nCoin"},
    {"key": "car_toxic_emerald", "color": "Изумрудный Hypercar", "pattern": "Глитч-подтёки и слайм NM", "outfit": "Неоновый поднос NM", "rarity": "🧪 Редкий", "estimated_price": "2,900,000 nCoin"},
    {"key": "car_cosmic_galaxy", "color": "Обсидиановый Hypercar", "pattern": "Звёздная пыль и галактика NM", "outfit": "Кристальная подставка NM", "rarity": "🌌 Мифический", "estimated_price": "5,800,000 nCoin"}
]

class NFTState(StatesGroup):
    waiting_for_transfer_target = State()


def get_nft_counts() -> tuple[int, int]:
    """Подсчитывает количество выпущенных NFT из базы данных"""
    drago_count = 0
    car_count = 0
    if hasattr(db, "get_total_nfts_count"):
        try:
            drago_count = db.get_total_nfts_count("Драко") or 0
            car_count = db.get_total_nfts_count("NM Hypercar") or 0
            return drago_count, car_count
        except Exception:
            pass
    try:
        conn = db.get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT nft_name, COUNT(*) FROM user_nfts GROUP BY nft_name")
        rows = cursor.fetchall()
        for r in rows:
            name, count = r[0], r[1]
            if "car" in str(name).lower() or "hypercar" in str(name).lower():
                car_count = count
            else:
                drago_count = count
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка подсчета NFT: {e}")
    return drago_count, car_count


def get_market_kb(drago_count: int, car_count: int) -> InlineKeyboardMarkup:
    buttons = []
    
    # Показываем кнопки только при наличии нераспроданного остатка
    if drago_count < NFT_DRAGO_MAX_SUPPLY:
        buttons.append([
            InlineKeyboardButton(
                text=f"🦕 Купить NFT «Драко» ({NFT_DRAGO_PRICE:,} nCoin)", 
                callback_data="buy_nft_drago"
            )
        ])
        
    if car_count < NFT_CAR_MAX_SUPPLY:
        buttons.append([
            InlineKeyboardButton(
                text=f"🏎️ Купить NFT «NM Hypercar» ({NFT_CAR_PRICE:,} nCoin)", 
                callback_data="buy_nft_car"
            )
        ])
        
    buttons.append([InlineKeyboardButton(text=f"⚡️ Грозовой Разряд ({LIGHTNING_PRICE:,} nCoin)", callback_data="buy_lightning")])
    buttons.append([InlineKeyboardButton(text=f"🧱 Кирпич ({BRICK_PRICE:,} nCoin)", callback_data="buy_brick")])
    buttons.append([InlineKeyboardButton(text="🎒 Мой Инвентарь", callback_data="show_inventory:0:all")])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="back_to_start")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- МАРКЕТ ---

@router.callback_query(F.data == "open_market_cb")
@router.message(StateFilter(None), Command("market"))
@router.message(StateFilter(None), F.text.lower().in_(["маркет", "магазин"]))
async def open_market_cmd(event, state: FSMContext = None):
    if state:
        await state.clear()
    user_id = event.from_user.id
    user = db.get_user(user_id)
    nfts = db.get_user_nfts(user_id) if hasattr(db, "get_user_nfts") else []
    
    drago_count, car_count = get_nft_counts()

    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "│  🛒 *ОФИЦИАЛЬНЫЙ МАРКЕТ NCOIN* \n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "⚡️ *ГРОЗОВОЙ РАЗРЯД (МОЛНИЯ):*\n"
        f" ├ 🎯 *Эффект:* Мутит игрока на 3 мин + выбивает 5,000 nCoin куша в чат!\n"
        f" └ 💰 *Стоимость:* `{LIGHTNING_PRICE:,} nCoin`\n\n"
        "🧱 *КИРПИЧ:*\n"
        f" ├ 🎯 *Эффект:* Выдает мут игроку на 5 минут в чате\n"
        f" └ 💰 *Стоимость:* `{BRICK_PRICE:,} nCoin`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 *Ваш баланс:* `{user['balance']:,.0f} nCoin`\n"
        f"🎒 *В наличии:* `{user.get('lightnings', 0)} молний` | `{user.get('bricks', 0)} кирпичей` | `{len(nfts)} NFT`"
    )
    kb = get_market_kb(drago_count, car_count)
    
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        try:
            await event.answer()
        except Exception:
            pass
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode="Markdown")


# --- ИНВЕНТАРЬ ---

@router.message(StateFilter(None), Command("inventory"))
@router.message(StateFilter(None), F.text.lower().in_(["инвентарь", "рюкзак"]))
@router.callback_query(F.data.startswith("show_inventory"))
async def show_inventory_cmd(event, state: FSMContext = None):
    if state:
        await state.clear()
        
    user_id = event.from_user.id
    user = db.get_user(user_id)
    all_nfts = db.get_user_nfts(user_id) if hasattr(db, "get_user_nfts") else []
    
    page = 0
    filter_type = "all"
    
    if isinstance(event, CallbackQuery) and ":" in event.data:
        parts = event.data.split(":")
        if len(parts) >= 2:
            try: page = int(parts[1])
            except ValueError: page = 0
        if len(parts) >= 3:
            filter_type = parts[2]

    if filter_type == "eq":
        nfts = [n for n in all_nfts if n.get("is_equipped")]
        filter_label = "👁 Только видимые"
    elif filter_type == "upg":
        nfts = [n for n in all_nfts if n.get("level", 1) >= 2]
        filter_label = "⭐ Только Lvl 2"
    else:
        nfts = all_nfts
        filter_label = "🌐 Все NFT"

    total_nfts = len(nfts)
    total_pages = (total_nfts + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total_nfts > 0 else 1
    page = max(0, min(page, total_pages - 1))
    
    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "│  🎒 *ВАШ ЛИЧНЫЙ ИНВЕНТАРЬ* \n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"⚡️ *Грозовые Разряды:* `{user.get('lightnings', 0)} шт.`\n"
        f"🧱 *Кирпичи:* `{user.get('bricks', 0)} шт.`\n"
        f"🛍️ *NFT Экспонаты:* `{len(all_nfts)} шт.` (Фильтр: `{filter_label}`)\n\n"
    )
    
    kb_buttons = []
    
    btn_all = "✅ 🌐 Все" if filter_type == "all" else "🌐 Все"
    btn_eq = "✅ 👁 Видимые" if filter_type == "eq" else "👁 Видимые"
    btn_upg = "✅ ⭐ Lvl 2" if filter_type == "upg" else "⭐ Lvl 2"
    
    kb_buttons.append([
        InlineKeyboardButton(text=btn_all, callback_data="show_inventory:0:all"),
        InlineKeyboardButton(text=btn_eq, callback_data="show_inventory:0:eq"),
        InlineKeyboardButton(text=btn_upg, callback_data="show_inventory:0:upg")
    ])
    
    if nfts:
        text += f"📋 *Список NFT (Страница {page + 1}/{total_pages}):*\n"
        
        start_idx = page * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_nfts = nfts[start_idx:end_idx]
        
        for nft in page_nfts:
            status_tag = " [👁 Виден]" if nft.get("is_equipped") else ""
            lvl_tag = f" (Lvl {nft.get('level', 1)})"
            icon = "🏎️" if "car" in str(nft.get("image_key", "")).lower() or "car" in str(nft.get("nft_name", "")).lower() or "hypercar" in str(nft.get("nft_name", "")).lower() else "🦕"
            nft_id = nft.get("nft_id") or nft.get("id")
            kb_buttons.append([
                InlineKeyboardButton(
                    text=f"{icon} {nft['nft_name']} #{nft['serial_number']}{lvl_tag}{status_tag}", 
                    callback_data=f"nft_view:{nft_id}"
                )
            ])
            
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"show_inventory:{page - 1}:{filter_type}"))
            
            nav_row.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="nft_page_info"))
            
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"show_inventory:{page + 1}:{filter_type}"))
                
            kb_buttons.append(nav_row)
    else:
        text += "🕸 _По выбранному фильтру NFT не найдены!_"

    kb_buttons.append([InlineKeyboardButton(text="🛒 В Магазин", callback_data="open_market_cb")])
    kb_buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="back_to_start")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        try:
            await event.answer()
        except Exception:
            pass
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "nft_page_info")
async def nft_page_info_cb(call: CallbackQuery):
    await call.answer("📄 Переключайте страницы кнопками ⬅️ Назад и Вперёд ➡️!", show_alert=True)


# --- ПОКУПКА ДРАКО ИЛИ CAR ---

@router.callback_query(F.data == "buy_nft_drago")
async def buy_nft_drago_callback(call: CallbackQuery):
    user_id = call.from_user.id
    user = db.get_user(user_id)
    drago_count, _ = get_nft_counts()

    if drago_count >= NFT_DRAGO_MAX_SUPPLY:
        await call.answer("❌ Коллекция NFT «Драко» полностью распродана!", show_alert=True)
        await open_market_cmd(call)
        return

    if user.get("balance", 0) < NFT_DRAGO_PRICE:
        await call.answer(f"❌ Недостаточно nCoin! Нужно: {NFT_DRAGO_PRICE:,} nCoin", show_alert=True)
        return

    db.update_balance(user_id, -NFT_DRAGO_PRICE)
    nft_id = db.create_nft(user_id, "Драко") if hasattr(db, "create_nft") else None
    
    await call.answer("🎉 Вы успешно приобрели NFT «Драко»!", show_alert=True)
    if nft_id:
        await show_nft_card(call, nft_id)
    else:
        await open_market_cmd(call)


@router.callback_query(F.data == "buy_nft_car")
async def buy_nft_car_callback(call: CallbackQuery):
    user_id = call.from_user.id
    user = db.get_user(user_id)
    _, car_count = get_nft_counts()

    if car_count >= NFT_CAR_MAX_SUPPLY:
        await call.answer("❌ Коллекция NFT «NM Hypercar» полностью распродана!", show_alert=True)
        await open_market_cmd(call)
        return

    if user.get("balance", 0) < NFT_CAR_PRICE:
        await call.answer(f"❌ Недостаточно nCoin! Нужно: {NFT_CAR_PRICE:,} nCoin", show_alert=True)
        return

    db.update_balance(user_id, -NFT_CAR_PRICE)
    nft_id = db.create_nft(user_id, "NM Hypercar", image_key="base_car") if hasattr(db, "create_nft") else None
    
    await call.answer("🎉 Вы успешно приобрели NFT «NM Hypercar»!", show_alert=True)
    if nft_id:
        await show_nft_card(call, nft_id)
    else:
        await open_market_cmd(call)


@router.callback_query(F.data == "buy_lightning")
async def buy_lightning_callback(call: CallbackQuery):
    user_id = call.from_user.id
    user = db.get_user(user_id)

    if user.get("balance", 0) < LIGHTNING_PRICE:
        await call.answer(f"❌ Недостаточно nCoin! Нужно: {LIGHTNING_PRICE:,} nCoin", show_alert=True)
        return

    db.update_balance(user_id, -LIGHTNING_PRICE)
    
    if hasattr(db, "update_lightnings"):
        try:
            db.update_lightnings(user_id, 1)
        except Exception:
            cur_val = user.get("lightnings", 0) + 1
            db.update_user_field(user_id, "lightnings", cur_val)
    else:
        cur_val = user.get("lightnings", 0) + 1
        if hasattr(db, "update_user_field"):
            db.update_user_field(user_id, "lightnings", cur_val)
    
    await call.answer("⚡️ Вы успешно купили 1 Грозовой Разряд!", show_alert=True)
    await open_market_cmd(call)


@router.callback_query(F.data == "buy_brick")
async def buy_brick_callback(call: CallbackQuery):
    user_id = call.from_user.id
    user = db.get_user(user_id)

    if user.get("balance", 0) < BRICK_PRICE:
        await call.answer(f"❌ Недостаточно nCoin! Нужно: {BRICK_PRICE:,} nCoin", show_alert=True)
        return

    db.update_balance(user_id, -BRICK_PRICE)
    
    if hasattr(db, "update_bricks"):
        db.update_bricks(user_id, 1)
    else:
        cur_val = user.get("bricks", 0) + 1
        if hasattr(db, "update_user_field"):
            db.update_user_field(user_id, "bricks", cur_val)
    
    await call.answer("🧱 Вы успешно купили 1 кирпич!", show_alert=True)
    await open_market_cmd(call)


# --- КАРТОЧКА NFT И ДЕЙСТВИЯ ---

async def show_nft_card(call: CallbackQuery, nft_id: int):
    nft = db.get_nft_by_id(nft_id) if hasattr(db, "get_nft_by_id") else None
    if not nft:
        await call.answer("❌ NFT не найден!", show_alert=True)
        return
        
    owner = db.get_user(nft["owner_id"])
    owner_name = owner.get("first_name") or f"Игрок {nft['owner_id']}"
    
    is_car = "car" in str(nft.get("image_key", "")).lower() or "car" in str(nft.get("nft_name", "")).lower() or "hypercar" in str(nft.get("nft_name", "")).lower()
    upgrade_price = NFT_CAR_UPGRADE_FEE if is_car else NFT_DRAGO_UPGRADE_FEE
    icon = "🏎️" if is_car else "🦕"
    
    equip_btn_text = "🙈 Скрыть из профиля" if nft.get("is_equipped") else "👁 Сделать видным в профиле"
    
    if nft.get("level", 1) < 2:
        level_str = "1/2 (Базовый)"
        upgrade_btn_row = [InlineKeyboardButton(text=f"✨ Улучшить ({upgrade_price:,} nCoin)", callback_data=f"nft_upgrade:{nft_id}")]
        upgrade_hint = f"💡 _Вы можете улучшить предмет 1 раз за {upgrade_price:,} nCoin, чтобы открылся редкий стиль, обвес и винил!_"
    else:
        level_str = "2/2 (Максимальный ⭐️)"
        upgrade_btn_row = [InlineKeyboardButton(text="✅ Максимальный уровень (2/2)", callback_data="nft_max_lvl_info")]
        upgrade_hint = "✨ _Предмет полностью прокачан!_"

    text = (
        f"{icon} *NFT ЭКСПОНАТ: {nft['nft_name']} #{nft['serial_number']}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👑 *Владелец:* [{owner_name}](tg://user?id={nft['owner_id']})\n"
        f"📅 *Дата покупки:* `{nft['purchase_date']}`\n"
        f"👁 *Статус в профиле:* `{'Отображается' if nft.get('is_equipped') else 'Скрыт'}`\n\n"
        "📊 *ХАРАКТЕРИСТИКИ ПРЕДМЕТА:*\n"
        f" ├ ⚡️ *Уровень:* `{level_str}`\n"
        f" ├ 💎 *Редкость:* `{nft.get('rarity', 'Обычный')}`\n"
        f" ├ 💰 *Оценка рынка:* `{nft.get('estimated_price', '999,000 nCoin')}`\n"
        f" ├ 🎨 *Цвет/Стиль:* `{nft.get('color', 'Базовый')}`\n"
        f" ├ ✨ *Узор/Винил:* `{nft.get('pattern', 'Базовый')}`\n"
        f" └ 👕 *Обвес/Подставка:* `{nft.get('outfit', 'Без обвеса')}`\n\n"
        f"{upgrade_hint}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=equip_btn_text, callback_data=f"nft_toggle_equip:{nft_id}")],
        upgrade_btn_row,
        [InlineKeyboardButton(text="📜 Сертификат подлинности", callback_data=f"nft_cert:{nft_id}")],
        [InlineKeyboardButton(text="🎁 Передать NFT", callback_data=f"nft_transfer:{nft_id}")],
        [InlineKeyboardButton(text="🎒 В Инвентарь", callback_data="show_inventory:0:all")]
    ])
    
    default_img = DRAGO_IMAGES["base_car"] if is_car else DRAGO_IMAGES["base_green"]
    photo_url = DRAGO_IMAGES.get(nft.get("image_key"), default_img)
    
    try:
        if call.message and call.message.photo:
            await call.message.delete()
        await call.message.answer_photo(photo=photo_url, caption=text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="Markdown")


# --- СЕРТИФИКАТ ПОДЛИННОСТИ ---

@router.callback_query(F.data.startswith("nft_cert:"))
async def nft_certificate_callback(call: CallbackQuery):
    await call.answer()
    nft_id = int(call.data.split(":")[1])
    nft = db.get_nft_by_id(nft_id) if hasattr(db, "get_nft_by_id") else None
    if not nft:
        await call.answer("❌ NFT не найден!", show_alert=True)
        return

    raw_str = f"NCOIN_NFT_{nft['nft_id']}_{nft['serial_number']}_{nft['owner_id']}_{nft['purchase_date']}"
    cert_hash = hashlib.sha256(raw_str.encode()).hexdigest().upper()

    cert_text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "│  📜 *СЕРТИФИКАТ ПОДЛИННОСТИ NFT* \n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "🔹 *БЛОКЧЕЙН ВЕРИФИКАЦИЯ:* `nCoin TRC-721`\n"
        f"🔹 *УНИКАЛЬНЫЙ ID:* `#NFT-{nft['serial_number']:03d}`\n"
        f"🔹 *ХЕШ ТРАНЗАКЦИИ:* `0x{cert_hash[:16]}...{cert_hash[-8:]}`\n\n"
        "📊 *ТЕХНИЧЕСКИЕ ДАННЫЕ:* \n"
        f" ├ 🛍️ *Предмет:* `{nft['nft_name']} #{nft['serial_number']}`\n"
        f" ├ 👑 *Владелец ID:* `{nft['owner_id']}`\n"
        f" ├ 📅 *Дата чеканки (Mint):* `{nft['purchase_date']}`\n"
        f" ├ ⚡️ *Уровень:* `{nft.get('level', 1)}/2`\n"
        f" ├ 💎 *Статус редкости:* `{nft.get('rarity', 'Обычный')}`\n"
        f" └ 💰 *Оценка:* `{nft.get('estimated_price', '999,000 nCoin')}`\n\n"
        "🛡 _Данный документ подтверждает оригинальность и подлинность предмета в экосистеме nCoin._"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к NFT", callback_data=f"nft_view:{nft_id}")]
    ])

    try:
        if call.message and call.message.photo:
            await call.message.delete()
        await call.message.answer(cert_text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await call.message.answer(cert_text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "nft_max_lvl_info")
async def nft_max_lvl_info_callback(call: CallbackQuery):
    await call.answer("ℹ️ Этот NFT уже имеет максимальный 2 уровень!", show_alert=True)


@router.callback_query(F.data.startswith("nft_view:"))
async def nft_view_callback(call: CallbackQuery):
    await call.answer()
    nft_id = int(call.data.split(":")[1])
    await show_nft_card(call, nft_id)


@router.callback_query(F.data.startswith("nft_toggle_equip:"))
async def nft_toggle_equip_callback(call: CallbackQuery):
    nft_id = int(call.data.split(":")[1])
    user_id = call.from_user.id
    
    new_state = db.toggle_equip_nft(user_id, nft_id) if hasattr(db, "toggle_equip_nft") else False
    msg = "👁 NFT теперь отображается в вашем профиле!" if new_state else "🙈 NFT скрыт из профиля."
    await call.answer(msg, show_alert=True)
    await show_nft_card(call, nft_id)


# --- ПОКУПКА УЛУЧШЕНИЯ С УЧЕТОМ ТИПА (ДРАКО ИЛИ CAR) ---

@router.callback_query(F.data.startswith("nft_upgrade:"))
async def nft_upgrade_callback(call: CallbackQuery):
    nft_id = int(call.data.split(":")[1])
    user_id = call.from_user.id
    user = db.get_user(user_id)
    nft = db.get_nft_by_id(nft_id) if hasattr(db, "get_nft_by_id") else None
    
    if not nft or nft["owner_id"] != user_id:
        await call.answer("❌ Вы не являетесь владельцем этого NFT!", show_alert=True)
        return

    if nft.get("level", 1) >= 2:
        await call.answer("❌ Этот предмет уже улучшен до 2 уровня!", show_alert=True)
        return

    is_car = "car" in str(nft.get("image_key", "")).lower() or "car" in str(nft.get("nft_name", "")).lower() or "hypercar" in str(nft.get("nft_name", "")).lower()
    upgrade_fee = NFT_CAR_UPGRADE_FEE if is_car else NFT_DRAGO_UPGRADE_FEE
    upgrade_pool = CAR_UPGRADES if is_car else DRAGO_UPGRADES
        
    if user.get("balance", 0) < upgrade_fee:
        await call.answer(f"❌ Недостаточно nCoin! Нужно: {upgrade_fee:,} nCoin", show_alert=True)
        return
        
    db.update_balance(user_id, -upgrade_fee)
    selected_upg = random.choice(upgrade_pool)
    
    if hasattr(db, "update_nft_attrs"):
        db.update_nft_attrs(
            nft_id=nft_id,
            color=selected_upg["color"],
            pattern=selected_upg["pattern"],
            outfit=selected_upg["outfit"],
            rarity=selected_upg["rarity"],
            estimated_price=selected_upg["estimated_price"],
            level=2,
            image_key=selected_upg["key"]
        )
    
    await call.answer(
        f"🎉 УСПЕШНО УЛУЧШЕНО ДО 2 УРОВНЯ!\n\n"
        f"💎 Редкость: {selected_upg['rarity']}\n"
        f"💰 Оценка: {selected_upg['estimated_price']}\n"
        f"🎨 Стиль: {selected_upg['color']}\n"
        f"✨ Винил/Узор: {selected_upg['pattern']}", 
        show_alert=True
    )
    await show_nft_card(call, nft_id)


# --- ПЕРЕДАЧА NFT ---

@router.callback_query(F.data.startswith("nft_transfer:"))
async def nft_transfer_start_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    nft_id = int(call.data.split(":")[1])
    nft = db.get_nft_by_id(nft_id) if hasattr(db, "get_nft_by_id") else None
    
    if not nft or nft["owner_id"] != call.from_user.id:
        await call.answer("❌ Вы не являетесь владельцем этого NFT!", show_alert=True)
        return

    is_car = "car" in str(nft.get("image_key", "")).lower() or "car" in str(nft.get("nft_name", "")).lower() or "hypercar" in str(nft.get("nft_name", "")).lower()
    base_price = NFT_CAR_PRICE if is_car else NFT_DRAGO_PRICE
    fee_amount = int(base_price * NFT_TRANSFER_FEE_PERCENT)
    
    await state.update_data(transfer_nft_id=nft_id, transfer_fee=fee_amount)
    await state.set_state(NFTState.waiting_for_transfer_target)
    
    text = (
        f"🎁 *ПЕРЕДАЧА NFT {nft['nft_name']} #{nft['serial_number']}*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💸 Комиссия за перевод (6%): *{fee_amount:,} nCoin*\n"
        "_(Списывается с вашего баланса nCoin)_\n\n"
        "✍️ *Введите Telegram ID или @username игрока, которому хотите передать NFT:*"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"nft_view:{nft_id}")]
    ])
    try:
        if call.message.photo:
            await call.message.delete()
        await call.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.message(NFTState.waiting_for_transfer_target)
async def process_nft_transfer_target(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    nft_id = data.get("transfer_nft_id")
    fee_amount = data.get("transfer_fee", 50000)
    
    sender_id = message.from_user.id
    sender = db.get_user(sender_id)
    
    target_user = db.find_user_by_username_or_id(message.text.strip()) if hasattr(db, "find_user_by_username_or_id") else None
    
    if not target_user:
        await message.reply("❌ Пользователь не найден в базе данных! Проверьте ID или @username и введите снова.")
        return
        
    target_id = target_user["user_id"]
    if target_id == sender_id:
        await message.reply("❌ Вы не можете передать NFT самому себе!")
        return
        
    if sender.get("balance", 0) < fee_amount:
        await message.reply(f"❌ Недостаточно nCoin для оплаты комиссии перевода ({fee_amount:,} nCoin)!")
        await state.clear()
        return
        
    db.update_balance(sender_id, -fee_amount)
    if hasattr(db, "transfer_nft_owner"):
        db.transfer_nft_owner(nft_id, target_id)
    await state.clear()
    
    nft = db.get_nft_by_id(nft_id) if hasattr(db, "get_nft_by_id") else {"nft_name": "NFT", "serial_number": 0}
    target_name = target_user.get("first_name") or f"Игрок {target_id}"
    sender_name = message.from_user.first_name

    await message.answer(
        f"🎉 *NFT УСПЕШНО ПЕРЕДАН!*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛍️ Предмет: *{nft['nft_name']} #{nft['serial_number']}*\n"
        f"👤 Получатель: [{target_name}](tg://user?id={target_id})\n"
        f"💸 Комиссия (6%): *{fee_amount:,} nCoin*",
        parse_mode="Markdown"
    )
    
    try:
        await bot.send_message(
            target_id,
            f"🎁 Вам был передан NFT экспонат *{nft['nft_name']} #{nft['serial_number']}* от [{sender_name}](tg://user?id={sender_id})!\n"
            "Посмотреть его можно в меню `инвентарь`.",
            parse_mode="Markdown"
        )
    except Exception:
        pass


# --- ИСПОЛЬЗОВАНИЕ «ГРОЗОВОГО РАЗРЯДА» (МОЛНИИ ЗА 39к С КУЛДАУНОМ 7.5 МИН) ---

@router.message(
    StateFilter(None),
    F.chat.type.in_({"group", "supergroup"}),
    F.text.lower().in_(["молния", "разряд"])
)
async def use_lightning_in_group(message: Message, bot: Bot):
    if not message.reply_to_message:
        await message.reply("❌ Чтобы применить Грозовой Разряд, ответьте (reply) этой командой на сообщение игрока!")
        return

    sender_id = message.from_user.id
    target_user = message.reply_to_message.from_user

    if target_user.id == sender_id:
        await message.reply("❌ Нельзя ударить молнией самого себя!")
        return

    if target_user.is_bot:
        await message.reply("❌ Нельзя ударить молнией бота!")
        return

    now = time.time()
    last_use = LAST_LIGHTNING_TIME.get(sender_id, 0)
    time_passed = now - last_use

    if time_passed < LIGHTNING_COOLDOWN:
        remaining = int(LIGHTNING_COOLDOWN - time_passed)
        mins = remaining // 60
        secs = remaining % 60
        await message.reply(
            f"⏳ *Грозовой Разряд перезаряжается!*\n"
            f"Повторное использование будет доступно через: *{mins} мин {secs} сек*.",
            parse_mode="Markdown"
        )
        return

    sender = db.get_user(sender_id)
    sender_lightnings = sender.get("lightnings", 0)

    if sender_lightnings < 1:
        await message.reply(
            f"❌ *У вас нет Грозовых Разрядов в инвентаре!*\n"
            f"Купите разряд в магазине `маркет` (стоимость {LIGHTNING_PRICE:,} nCoin).",
            parse_mode="Markdown"
        )
        return

    until_date = int(time.time()) + 180  # Мут на 3 минуты (180 сек)
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
    except Exception as e:
        logger.error(f"Ошибка применения молнии: {e}")
        await message.reply("❌ Не удалось выдать мут! Убедитесь, что у бота есть права админа.")
        return

    LAST_LIGHTNING_TIME[sender_id] = now
    if hasattr(db, "update_lightnings"):
        try:
            db.update_lightnings(sender_id, -1)
        except Exception:
            db.update_user_field(sender_id, "lightnings", sender_lightnings - 1)
    else:
        if hasattr(db, "update_user_field"):
            db.update_user_field(sender_id, "lightnings", sender_lightnings - 1)

    sender_name = message.from_user.first_name
    target_name = target_user.first_name

    loot_id = f"loot_{int(now)}_{sender_id}"
    ACTIVE_LIGHTNING_LOOTS[loot_id] = {"amount": 5000, "claimed": False}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ Забрать 5,000 nCoin (Куш!)", callback_data=f"claim_lightning_loot:{loot_id}")]
    ])

    await message.answer(
        f"⚡️ *УДАР МОЛНИИ! В {target_name} ВОНЗИЛСЯ ГРОЗОВОЙ РАЗРЯД!* ⚡️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Разряд пустил: [{sender_name}](tg://user?id={sender_id})\n"
        f"🎯 Получил удар: [{target_name}](tg://user?id={target_user.id})\n"
        f"🤐 Мут: *на 3 минуты*\n"
        f"💰 *Осколки энергии:* Выбито *5,000 nCoin* в чат!\n\n"
        f"👇 _Кто быстрее нажмет на кнопку, тот и заберет куш!_",
        reply_markup=kb,
        parse_mode="Markdown"
    )


# --- ОБРАБОТЧИК КЛИКА НА КУШ 5,000 nCoin ---

@router.callback_query(F.data.startswith("claim_lightning_loot:"))
async def claim_lightning_loot_cb(call: CallbackQuery):
    loot_id = call.data.split(":")[1]
    loot = ACTIVE_LIGHTNING_LOOTS.get(loot_id)

    if not loot:
        await call.answer("❌ Энергия разряда уже угасла!", show_alert=True)
        return

    if loot["claimed"]:
        await call.answer("❌ Этот куш уже забрал другой игрок!", show_alert=True)
        return

    loot["claimed"] = True
    user_id = call.from_user.id
    db.update_balance(user_id, loot["amount"])
    claimer_name = call.from_user.first_name

    await call.answer(f"🎉 Вы молниеносно забрали +{loot['amount']:,} nCoin!", show_alert=True)

    try:
        await call.message.edit_text(
            f"{call.message.text}\n\n"
            f"✅ *КУШ ЗАБРАН!* ⚡️\n"
            f"👤 Победитель: [{claimer_name}](tg://user?id={user_id}) (+5,000 nCoin)",
            reply_markup=None,
            parse_mode="Markdown"
        )
    except Exception:
        pass


# --- ИСПОЛЬЗОВАНИЕ КИРПИЧА ---

@router.message(
    StateFilter(None),
    F.chat.type.in_({"group", "supergroup"}),
    F.text.lower() == "кирпич"
)
async def use_brick_in_group(message: Message, bot: Bot):
    if not message.reply_to_message:
        await message.reply("❌ Чтобы применить кирпич, ответьте (reply) на сообщение пользователя!")
        return

    sender_id = message.from_user.id
    target_user = message.reply_to_message.from_user

    if target_user.id == sender_id:
        await message.reply("❌ Нельзя кинуть кирпич в самого себя!")
        return

    if target_user.is_bot:
        await message.reply("❌ Нельзя кинуть кирпич в бота!")
        return

    sender = db.get_user(sender_id)
    sender_bricks = sender.get("bricks", 0)

    if sender_bricks < 1:
        await message.reply(
            "❌ *У вас нет кирпичей в инвентаре!*\n"
            "Купите кирпич в магазине `маркет` (стоимость 50,000 nCoin).",
            parse_mode="Markdown"
        )
        return

    until_date = int(time.time()) + 300
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
    except Exception as e:
        logger.error(f"Ошибка мута кирпичом: {e}")
        await message.reply("❌ Не удалось выдать мут! Убедитесь, что у бота есть права админа.")
        return

    if hasattr(db, "update_bricks"):
        db.update_bricks(sender_id, -1)
    else:
        if hasattr(db, "update_user_field"):
            db.update_user_field(sender_id, "bricks", sender_bricks - 1)

    sender_name = message.from_user.first_name
    target_name = target_user.first_name

    await message.answer(
        f"🧱 *БУМ! В {target_name} прилетел кирпич!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Кинул: [{sender_name}](tg://user?id={sender_id})\n"
        f"🎯 Получил: [{target_name}](tg://user?id={target_user.id})\n"
        f"🤐 Мут: *на 5 минут*\n"
        f"🎒 Осталось кирпичей: *{sender_bricks - 1} шт.*",
        parse_mode="Markdown"
    )
