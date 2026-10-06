# p2p_nft.py
import time
import html
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import db

logger = logging.getLogger(__name__)
router = Router()

EMOJI_AQ = '<tg-emoji emoji-id="5780560530515171033">🛍</tg-emoji>'

P2P_FEE_PERCENT = 0.05    # Комиссия маркетплейса 5% для вывода излишков валюты из экономики
LISTINGS_PER_PAGE = 5     # Количество лотов на 1 страницу
SELL_NFTS_PER_PAGE = 5    # Количество NFT на 1 страницу при выборе

# Ограничения цен для предотвращения взломов/переливов баланса
MIN_PRICE_NCOIN = 100_000
MAX_PRICE_NCOIN = 500_000_000
MIN_PRICE_NMP = 10
MAX_PRICE_NMP = 200_000

DRAGO_IMAGES = {
    # 0. БАЗОВЫЕ КАРТИНКИ
    "base_green": "https://i.ibb.co/p6kZ2PNh/IMG-20260822-175450-939.jpg",
    "base_car": "https://i.ibb.co/676cy1tp/IMG-20260826-231927-757.jpg",

    # --- ВАРИАНТЫ ДРАКО ---
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

    # --- ВАРИАНТЫ NM HYPERCAR ---
    "car_cyber_neon": "https://i.ibb.co/twx2r5kY/IMG-20260826-225349-589.jpg",
    "car_gold_royal": "https://i.ibb.co/fdYk8jsv/IMG-20260826-225351-568.jpg",
    "car_inferno_flame": "https://i.ibb.co/6c3XJM36/IMG-20260826-225352-981.jpg",
    "car_toxic_emerald": "https://i.ibb.co/q3Rhwx84/IMG-20260826-225542-870.jpg",
    "car_cosmic_galaxy": "https://i.ibb.co/R4McrdcF/IMG-20260826-225726-014.jpg"
}

_DB_INITIALIZED = False

def get_nft_icon(name: str = "", img_key: str = "") -> str:
    name_l = str(name).lower()
    key_l = str(img_key).lower()
    if "car" in name_l or "hypercar" in name_l or "car" in key_l:
        return "🏎️"
    return "🦕"

def get_nft_image(img_key: str = "", name: str = "") -> str:
    if img_key in DRAGO_IMAGES:
        return DRAGO_IMAGES[img_key]
    name_l = str(name).lower()
    key_l = str(img_key).lower()
    if "car" in name_l or "hypercar" in name_l or "car" in key_l:
        return DRAGO_IMAGES.get("base_car", DRAGO_IMAGES["base_green"])
    return DRAGO_IMAGES["base_green"]

class P2PNFTState(StatesGroup):
    waiting_for_price = State()
    waiting_for_page_input = State()


# === ИНИЦИАЛИЗАЦИЯ ТАБЛИЦЫ ЛОТОВ В БАЗЕ ДАННЫХ ===

def init_p2p_nft_db():
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS p2p_nft_listings (
                listing_id SERIAL PRIMARY KEY,
                nft_id INT NOT NULL,
                seller_id BIGINT NOT NULL,
                currency VARCHAR(10) NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        _DB_INITIALIZED = True
    except Exception as e:
        logger.error(f"Ошибка создания таблицы P2P NFT: {e}")
    finally:
        cursor.close()
        conn.close()


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ ===

def get_active_listings(currency_filter: str = "all"):
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        if currency_filter in ("ncoin", "nmp"):
            cursor.execute("""
                SELECT l.listing_id, l.nft_id, l.seller_id, l.currency, l.price,
                       COALESCE(n.nft_name, 'Драко'), COALESCE(n.serial_number, 0),
                       COALESCE(n.level, 1), COALESCE(n.rarity, 'Обычный'), COALESCE(n.image_key, 'base_green')
                FROM p2p_nft_listings l
                JOIN user_nfts n ON l.nft_id = n.nft_id
                WHERE l.status = 'active' AND l.currency = %s
                ORDER BY l.created_at DESC
            """, (currency_filter,))
        else:
            cursor.execute("""
                SELECT l.listing_id, l.nft_id, l.seller_id, l.currency, l.price,
                       COALESCE(n.nft_name, 'Драко'), COALESCE(n.serial_number, 0),
                       COALESCE(n.level, 1), COALESCE(n.rarity, 'Обычный'), COALESCE(n.image_key, 'base_green')
                FROM p2p_nft_listings l
                JOIN user_nfts n ON l.nft_id = n.nft_id
                WHERE l.status = 'active'
                ORDER BY l.created_at DESC
            """)
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка получения лотов P2P: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_listing_by_id(listing_id: int):
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT l.listing_id, l.nft_id, l.seller_id, l.currency, l.price, l.status,
                   COALESCE(n.nft_name, 'Драко'), COALESCE(n.serial_number, 0), COALESCE(n.level, 1),
                   COALESCE(n.color, 'Зеленый'), COALESCE(n.pattern, 'Обычный'), COALESCE(n.outfit, 'Без одежды'),
                   COALESCE(n.rarity, 'Обычный'), COALESCE(n.estimated_price, '999,000 nCoin'),
                   COALESCE(n.purchase_date, 'Неизвестно'), COALESCE(n.image_key, 'base_green')
            FROM p2p_nft_listings l
            JOIN user_nfts n ON l.nft_id = n.nft_id
            WHERE l.listing_id = %s
        """, (listing_id,))
        row = cursor.fetchone()
        return row if row else None
    except Exception as e:
        logger.error(f"Ошибка получения лота #{listing_id}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_user_active_listings(user_id: int):
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT l.listing_id, l.nft_id, l.currency, l.price,
                   COALESCE(n.nft_name, 'Драко'), COALESCE(n.serial_number, 0),
                   COALESCE(n.level, 1), COALESCE(n.image_key, 'base_green')
            FROM p2p_nft_listings l
            JOIN user_nfts n ON l.nft_id = n.nft_id
            WHERE l.seller_id = %s AND l.status = 'active'
            ORDER BY l.created_at DESC
        """, (user_id,))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка получения объявлений пользователя {user_id}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_listed_nft_ids_for_user(user_id: int) -> set:
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT nft_id FROM p2p_nft_listings WHERE seller_id = %s AND status = 'active'", (user_id,))
        rows = cursor.fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()
    finally:
        cursor.close()
        conn.close()


# === ГЛАВНЫЙ ЭКРАН P2P МАРКЕТПЛЕЙСА ===

@router.message(F.text.casefold().in_(["/p2p", "п2п", "p2p", "p2p маркет", "p2p nft"]))
@router.message(Command("p2p"))
async def show_p2p_main(event, state: FSMContext = None):
    if state:
        await state.clear()
    init_p2p_nft_db()
    
    user_id = event.from_user.id
    user = db.get_user(user_id)
    active_listings = get_active_listings("all")
    user_listings = get_user_active_listings(user_id)
    
    bal_ncoin = int(user.get("balance", 0) or 0)
    bal_nmp = int(user.get("nmp_balance", 0) or 0)

    text = (
        "💎 <b>P2P NFT МАРКЕТПЛЕЙС</b>\n"
        "⠀\n"
        "<i>⚡️ Безопасная торговля NFT экспонатами между игроками</i>\n\n"
        "💳 <b>ВАШ БАЛАНС:</b>\n"
        f" ├ 💰 nCoin: <code>{bal_ncoin:,}</code>\n"
        f" └ 💎 NMP: <code>{bal_nmp:,}</code>\n\n"
        "📊 <b>СТАТИСТИКА РЫНКА:</b>\n"
        f" ├ {EMOJI_AQ} Активных лотов в продаже: <code>{len(active_listings)} шт.</code>\n"
        f" └ 📦 Ваших объявлений: <code>{len(user_listings)} шт.</code>\n\n"
        "👇 <b>Выберите раздел рынка:</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛒 Каталог лотов", callback_data="p2p_browse:0:all"),
            InlineKeyboardButton(text="➕ Продать NFT", callback_data="p2p_sell_page:0")
        ],
        [
            InlineKeyboardButton(text="📦 Мои объявления", callback_data="p2p_my_listings"),
            InlineKeyboardButton(text="🎒 Мой Инвентарь", callback_data="show_inventory:0:all")
        ],
        [
            InlineKeyboardButton(text="❌ Закрыть", callback_data="back_to_start")
        ]
    ])
    
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer()
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode="HTML")


# === ПРОСМОТР КАТАЛОГА ЛОТОВ ===

@router.callback_query(F.data.startswith("p2p_browse:"))
async def browse_p2p_listings(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    page = int(parts[1])
    curr_filter = parts[2]
    
    listings = get_active_listings(curr_filter)
    total_items = len(listings)
    total_pages = (total_items + LISTINGS_PER_PAGE - 1) // LISTINGS_PER_PAGE if total_items > 0 else 1
    page = max(0, min(page, total_pages - 1))
    
    text = (
        "⠀\n"
        "🛒 <b>КАТАЛОГ P2P NFT ЛОТОВ</b>\n"
        "⠀\n\n"
    )
    
    kb_buttons = []
    
    f_all = "✅ Все" if curr_filter == "all" else "🌐 Все"
    f_ncoin = "✅ 💰 nCoin" if curr_filter == "ncoin" else "💰 nCoin"
    f_nmp = "✅ 💎 NMP" if curr_filter == "nmp" else "💎 NMP"
    
    kb_buttons.append([
        InlineKeyboardButton(text=f_all, callback_data="p2p_browse:0:all"),
        InlineKeyboardButton(text=f_ncoin, callback_data="p2p_browse:0:ncoin"),
        InlineKeyboardButton(text=f_nmp, callback_data="p2p_browse:0:nmp")
    ])
    
    if listings:
        text += f"📋 <b>Лоты в продаже (Страница {page + 1}/{total_pages}):</b>\n\n"
        start_idx = page * LISTINGS_PER_PAGE
        end_idx = start_idx + LISTINGS_PER_PAGE
        page_items = listings[start_idx:end_idx]
        
        for item in page_items:
            l_id, nft_id, seller_id, curr, price, name, serial, lvl, rarity, img_key = item
            curr_symbol = "nCoin" if curr == "ncoin" else "NMP"
            curr_icon = "💰" if curr == "ncoin" else "💎"
            icon = get_nft_icon(name, img_key)
            
            kb_buttons.append([
                InlineKeyboardButton(
                    text=f"{icon} {name} #{serial} (Lvl {lvl}) — {curr_icon} {int(price):,} {curr_symbol}",
                    callback_data=f"p2p_view_card:{l_id}"
                )
            ])
            
        if total_pages > 1:
            nav_row = []
            if page > 0:
                nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"p2p_browse:{page-1}:{curr_filter}"))
            nav_row.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="p2p_noop"))
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"p2p_browse:{page+1}:{curr_filter}"))
            kb_buttons.append(nav_row)
    else:
        text += "🕸 <i>По выбранному фильтру нет активных объявлений. Выставите свой NFT первым!</i>"

    kb_buttons.append([InlineKeyboardButton(text="🔙 В главное меню P2P", callback_data="p2p_main_cb")])
    
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")
        else:
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")


@router.callback_query(F.data == "p2p_main_cb")
async def p2p_main_callback(callback: CallbackQuery, state: FSMContext):
    if callback.message.photo:
        await callback.message.delete()
    await show_p2p_main(callback, state)


# === ИНСПЕКЦИЯ КАРТОЧКИ NFT И ПОКУПКА ===

@router.callback_query(F.data.startswith("p2p_view_card:"))
async def view_p2p_listing_card(callback: CallbackQuery):
    await callback.answer()
    listing_id = int(callback.data.split(":")[1])
    item = get_listing_by_id(listing_id)
    
    if not item or item[5] != "active":
        await callback.message.answer("❌ Лот не найден или уже выкуплен!")
        return

    l_id, nft_id, seller_id, curr, price, status, name, serial, lvl, color, pattern, outfit, rarity, est_price, p_date, img_key = item
    
    seller = db.get_user(seller_id)
    seller_name = html.escape(seller.get("first_name") or f"Игрок {seller_id}")
    
    curr_symbol = "nCoin" if curr == "ncoin" else "NMP"
    curr_icon = "💰" if curr == "ncoin" else "💎"
    icon = get_nft_icon(name, img_key)
    
    user_id = callback.from_user.id
    is_owner = (user_id == seller_id)
    
    text = (
        f"{icon} <b>ЛОТ #{l_id}: {name} #{serial}</b>\n"
        f"\n\n"
        f"💵 <b>ЦЕНА ПРОДАЖИ:</b> <code>{int(price):,} {curr_symbol}</code> {curr_icon}\n"
        f"👤 <b>Продавец:</b> <a href=\"tg://user?id={seller_id}\"><b>{seller_name}</b></a>\n\n"
        f"📊 <b>ХАРАКТЕРИСТИКИ NFT:</b>\n"
        f" ├ ⚡️ <b>Уровень:</b> <code>{lvl}/2</code>\n"
        f" ├ 💎 <b>Редкость:</b> <code>{rarity or 'Обычный'}</code>\n"
        f" ├ 🎨 <b>Цвет:</b> <code>{color}</code>\n"
        f" ├ ✨ <b>Узор:</b> <code>{pattern}</code>\n"
        f" ├ 👕 <b>Одежда/Подставка:</b> <code>{outfit or 'Без одежды'}</code>\n"
        f" ├ 📅 <b>Чеканка:</b> <code>{p_date}</code>\n"
        f" └ 💰 <b>Оценка стоимости:</b> <code>{est_price}</code>\n"
    )

    kb_buttons = []
    if is_owner:
        kb_buttons.append([InlineKeyboardButton(text="❌ Снять с продажи", callback_data=f"p2p_cancel:{l_id}")])
    else:
        kb_buttons.append([InlineKeyboardButton(text=f"🛒 Купить за {int(price):,} {curr_symbol}", callback_data=f"p2p_buy:{l_id}")])
        
    kb_buttons.append([InlineKeyboardButton(text="🔙 В Каталог", callback_data="p2p_browse:0:all")])
    
    photo_url = get_nft_image(img_key, name)
    
    try:
        if callback.message.photo:
            await callback.message.delete()
        await callback.message.answer_photo(photo=photo_url, caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")


# === ПОКУПКА ЛОТА С АТОМАРНОЙ БЛОКИРОВКОЙ ОТ ДВОЙНОГО ВЫКУПА ===

@router.callback_query(F.data.startswith("p2p_buy:"))
async def process_p2p_buy(callback: CallbackQuery, bot: Bot):
    listing_id = int(callback.data.split(":")[1])
    buyer_id = callback.from_user.id
    
    item = get_listing_by_id(listing_id)
    if not item or item[5] != "active":
        await callback.answer("❌ Этот лот уже недоступен или снят с продажи!", show_alert=True)
        return

    l_id, nft_id, seller_id, curr, price, status, name, serial, lvl, color, pattern, outfit, rarity, est_price, p_date, img_key = item
    icon = get_nft_icon(name, img_key)
    
    if buyer_id == seller_id:
        await callback.answer("❌ Вы не можете купить собственный лот!", show_alert=True)
        return

    # Дополнительная проверка: действительно ли продавец всё ещё владеет этим NFT
    current_nft = db.get_nft_by_id(nft_id)
    if not current_nft or current_nft.get("owner_id") != seller_id:
        await callback.answer("❌ Владелец предмета изменился!", show_alert=True)
        return

    buyer = db.get_user(buyer_id)
    price_int = int(price)
    
    if curr == "ncoin":
        if (buyer.get("balance", 0) or 0) < price_int:
            await callback.answer(f"❌ Недостаточно nCoin! Нужно: {price_int:,} nCoin", show_alert=True)
            return
    else:
        if (buyer.get("nmp_balance", 0) or 0) < price_int:
            await callback.answer(f"❌ Недостаточно NMP! Нужно: {price_int:,} NMP", show_alert=True)
            return

    payout = int(price_int * (1 - P2P_FEE_PERCENT))

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        # Атомарный UPDATE: статус меняется только если он ещё 'active'
        cursor.execute("UPDATE p2p_nft_listings SET status = 'sold' WHERE listing_id = %s AND status = 'active'", (listing_id,))
        if cursor.rowcount == 0:
            await callback.answer("❌ Этот лот уже успели купить вперед вас!", show_alert=True)
            cursor.close()
            conn.close()
            return

        if curr == "ncoin":
            db.update_balance(buyer_id, -price_int)
            db.update_balance(seller_id, payout)
            curr_str = "nCoin"
        else:
            db.update_nmp_balance(buyer_id, -price_int)
            db.update_nmp_balance(seller_id, payout)
            curr_str = "NMP"

        db.transfer_nft_owner(nft_id, buyer_id)
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка проведения P2P сделки: {e}")
        await callback.answer("❌ Произошла ошибка при покупке!", show_alert=True)
        cursor.close()
        conn.close()
        return
    finally:
        cursor.close()
        conn.close()

    buyer_name = html.escape(callback.from_user.first_name)
    await callback.answer("🎉 Вы успешно приобрели NFT!", show_alert=True)
    
    text = (
        "🎉 <b>ПОЗДРАВЛЯЕМ С УСПЕШНОЙ ПОКУПКОЙ!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon} Вы приобрели: <b>{name} #{serial}</b>\n"
        f"💸 Списано: <code>{price_int:,} {curr_str}</code>\n"
        "📦 Предмет зачислен в ваш <b>Инвентарь</b>!"
    )
    
    if callback.message.photo:
        await callback.message.delete()
    await callback.message.answer(text, parse_mode="HTML")

    try:
        await bot.send_message(
            seller_id,
            "⚡ <b>ВАШ NFT БЫЛ ВЫКУПЛЕН НА P2P МАРКЕТЕ!</b>\n"
            ". . . . . . . . . . . . . . . . . . . . . . . . . . .\n"
            f"{icon} Предмет: <b>{name} #{serial}</b>\n"
            f"👤 Покупатель: {buyer_name}\n"
            f"💰 Зачислено на счет (комиссия 5%): <code>+{payout:,} {curr_str}</code>",
            parse_mode="HTML"
        )
    except Exception:
        pass


# === ВЫСТАВЛЕНИЕ NFT НА ПРОДАЖУ ===

async def render_sell_nfts_page(target_msg, user_id: int, page: int = 0, is_edit: bool = False):
    user_nfts = db.get_user_nfts(user_id)
    listed_ids = get_listed_nft_ids_for_user(user_id)
    
    available_nfts = []
    for n in user_nfts:
        nft_id = n.get("nft_id") or n.get("id")
        if nft_id and nft_id not in listed_ids:
            n["valid_id"] = nft_id
            available_nfts.append(n)
            
    if not available_nfts:
        text = (
            "❌ <b>У вас нет доступных NFT для продажи!</b>\n"
            "Все ваши предметы либо уже продаются на P2P, либо отсутствуют в инвентаре."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="p2p_main_cb")]])
        if is_edit:
            try:
                await target_msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
                return
            except Exception:
                pass
        await target_msg.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    total_items = len(available_nfts)
    total_pages = (total_items + SELL_NFTS_PER_PAGE - 1) // SELL_NFTS_PER_PAGE if total_items > 0 else 1
    page = max(0, min(page, total_pages - 1))
    
    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "│  ➕ <b>ВЫСТАВЛЕНИЕ NFT НА ПРОДАЖУ</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"📋 <b>Выберите NFT (Страница {page + 1}/{total_pages}):</b>"
    )
    
    kb_buttons = []
    start_idx = page * SELL_NFTS_PER_PAGE
    end_idx = start_idx + SELL_NFTS_PER_PAGE
    page_nfts = available_nfts[start_idx:end_idx]
    
    for nft in page_nfts:
        icon = get_nft_icon(nft.get('nft_name', ''), nft.get('image_key', ''))
        kb_buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {nft['nft_name']} #{nft['serial_number']} (Lvl {nft['level']})",
                callback_data=f"p2p_select_nft:{nft['valid_id']}"
            )
        ])
        
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"p2p_sell_page:{page - 1}"))
        
        nav_row.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages} (Ввести)", callback_data="p2p_ask_page"))
        
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"p2p_sell_page:{page + 1}"))
            
        kb_buttons.append(nav_row)
        
    kb_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="p2p_main_cb")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    
    if is_edit:
        try:
            await target_msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
            
    await target_msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "p2p_sell_start")
async def p2p_sell_start_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await render_sell_nfts_page(callback.message, callback.from_user.id, page=0, is_edit=True)
    await callback.answer()

@router.callback_query(F.data.startswith("p2p_sell_page:"))
async def p2p_sell_page_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    page = int(callback.data.split(":")[1])
    await render_sell_nfts_page(callback.message, callback.from_user.id, page=page, is_edit=True)
    await callback.answer()

@router.callback_query(F.data == "p2p_ask_page")
async def p2p_ask_page_cb(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_nfts = db.get_user_nfts(user_id)
    listed_ids = get_listed_nft_ids_for_user(user_id)
    available_nfts = [n for n in user_nfts if (n.get("nft_id") or n.get("id")) not in listed_ids]
    
    total_items = len(available_nfts)
    total_pages = (total_items + SELL_NFTS_PER_PAGE - 1) // SELL_NFTS_PER_PAGE if total_items > 0 else 1
    
    await state.set_state(P2PNFTState.waiting_for_page_input)
    await callback.answer()
    
    text_prompt = f"✍️ <b>Введите номер страницы (от 1 до {total_pages}):</b>"
    kb_cancel = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="p2p_sell_page:0")]])
    
    if callback.message.photo:
        await callback.message.delete()
        sent_msg = await callback.message.answer(text_prompt, reply_markup=kb_cancel, parse_mode="HTML")
    else:
        sent_msg = await callback.message.edit_text(text_prompt, reply_markup=kb_cancel, parse_mode="HTML")
    
    await state.update_data(prompt_msg_id=sent_msg.message_id)

@router.message(StateFilter(P2PNFTState.waiting_for_page_input))
async def p2p_process_page_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_nfts = db.get_user_nfts(user_id)
    listed_ids = get_listed_nft_ids_for_user(user_id)
    available_nfts = [n for n in user_nfts if (n.get("nft_id") or n.get("id")) not in listed_ids]
    
    total_items = len(available_nfts)
    total_pages = (total_items + SELL_NFTS_PER_PAGE - 1) // SELL_NFTS_PER_PAGE if total_items > 0 else 1
    
    try: await message.delete()
    except Exception: pass
        
    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    await state.clear()
    
    try:
        val = int(message.text.strip())
        target_page = val - 1
        if target_page < 0: target_page = 0
        if target_page >= total_pages: target_page = total_pages - 1
    except ValueError:
        target_page = 0
        
    if prompt_msg_id:
        try:
            fake_msg = type('obj', (object,), {
                'chat': message.chat,
                'message_id': prompt_msg_id,
                'edit_text': lambda txt, reply_markup=None, parse_mode=None: message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=txt, reply_markup=reply_markup, parse_mode=parse_mode)
            })()
            await render_sell_nfts_page(fake_msg, user_id, page=target_page, is_edit=True)
            return
        except Exception: pass
            
    await render_sell_nfts_page(message, user_id, page=target_page, is_edit=False)


@router.callback_query(F.data.startswith("p2p_select_nft:"))
async def p2p_select_currency(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    nft_id = int(callback.data.split(":")[1])
    nft = db.get_nft_by_id(nft_id)
    
    if not nft or nft.get("owner_id") != callback.from_user.id:
        await callback.message.answer("❌ NFT не найден или не принадлежит вам!")
        return

    # Проверяем, не выставлен ли он уже на продажу
    listed_ids = get_listed_nft_ids_for_user(callback.from_user.id)
    if nft_id in listed_ids:
        await callback.message.answer("❌ Этот NFT уже выставлен на продажу!")
        return

    await state.update_data(sell_nft_id=nft_id)
    
    name = nft.get("nft_name", "Драко")
    serial = nft.get("serial_number", 0)
    lvl = nft.get("level", 1)
    color = nft.get("color", "Зеленый")
    pattern = nft.get("pattern", "Обычный")
    outfit = nft.get("outfit", "Без одежды")
    rarity = nft.get("rarity", "Обычный")
    est_price = nft.get("estimated_price", "999,000 nCoin")
    p_date = nft.get("purchase_date", "Неизвестно")
    img_key = nft.get("image_key", "base_green")
    
    photo_url = get_nft_image(img_key, name)
    icon = get_nft_icon(name, img_key)
    
    text = (
        f"╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"│  {icon} <b>ВЫБРАН ПРЕДМЕТ: {name} #{serial}</b>\n"
        f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"📊 <b>ХАРАКТЕРИСТИКИ NFT:</b>\n"
        f" ├ ⚡️ <b>Уровень:</b> <code>{lvl}/2</code>\n"
        f" ├ 💎 <b>Редкость:</b> <code>{rarity}</code>\n"
        f" ├ 🎨 <b>Цвет:</b> <code>{color}</code>\n"
        f" ├ ✨ <b>Узор:</b> <code>{pattern}</code>\n"
        f" ├ 👕 <b>Одежда/Подставка:</b> <code>{outfit}</code>\n"
        f" ├ 📅 <b>Чеканка:</b> <code>{p_date}</code>\n"
        f" └ 💰 <b>Оценка стоимости:</b> <code>{est_price}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>Выберите валюту, в которой вы хотите получить оплату:</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Продать за nCoin", callback_data="p2p_set_curr:ncoin"),
            InlineKeyboardButton(text="💎 Продать за NMP", callback_data="p2p_set_curr:nmp")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="p2p_main_cb")]
    ])
    
    try:
        if callback.message.photo:
            await callback.message.delete()
        await callback.message.answer_photo(photo=photo_url, caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("p2p_set_curr:"))
async def p2p_ask_price(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    currency = callback.data.split(":")[1]
    await state.update_data(sell_currency=currency)
    await state.set_state(P2PNFTState.waiting_for_price)
    
    data = await state.get_data()
    nft_id = data.get("sell_nft_id")
    nft = db.get_nft_by_id(nft_id) if nft_id else None
    
    curr_str = "nCoin" if currency == "ncoin" else "NMP"
    curr_icon = "💰" if currency == "ncoin" else "💎"
    min_lim = f"{MIN_PRICE_NCOIN:,}" if currency == "ncoin" else f"{MIN_PRICE_NMP:,}"
    max_lim = f"{MAX_PRICE_NCOIN:,}" if currency == "ncoin" else f"{MAX_PRICE_NMP:,}"
    
    if nft:
        name = nft.get("nft_name", "Драко")
        img_key = nft.get("image_key", "base_green")
        photo_url = get_nft_image(img_key, name)
        icon = get_nft_icon(name, img_key)
        
        text = (
            f"╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            f"│  💵 <b>УКАЖИТЕ ЦЕНУ ПРОДАЖИ</b>\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"{icon} <b>Предмет:</b> {name} #{nft.get('serial_number', 0)} (Lvl {nft.get('level', 1)})\n"
            f"💎 <b>Редкость:</b> {nft.get('rarity', 'Обычный')}\n"
            f"💳 <b>Валюта оплаты:</b> {curr_str} {curr_icon}\n"
            f"⚠️ <b>Лимит цены:</b> <code>от {min_lim} до {max_lim} {curr_str}</code>\n\n"
            "✍️ <b>Введите желаемую цену (целое число):</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="p2p_main_cb")]])
        
        try:
            if callback.message.photo:
                await callback.message.delete()
            await callback.message.answer_photo(photo=photo_url, caption=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(StateFilter(P2PNFTState.waiting_for_price))
async def p2p_process_price(message: Message, state: FSMContext):
    data = await state.get_data()
    nft_id = data.get("sell_nft_id")
    currency = data.get("sell_currency")
    await state.clear()
    
    user_id = message.from_user.id
    nft = db.get_nft_by_id(nft_id)
    
    if not nft or nft.get("owner_id") != user_id:
        await message.answer("❌ Ошибка доступа к NFT!")
        return

    # Защита от дублирования объявления
    listed_ids = get_listed_nft_ids_for_user(user_id)
    if nft_id in listed_ids:
        await message.answer("❌ Этот NFT уже выставлен на продажу!")
        return

    try:
        val = float(message.text.replace(",", "."))
        if val <= 0 or not val.is_integer(): raise ValueError
        price = int(val)
    except ValueError:
        await message.answer("❌ <b>Введите корректное целое число больше 0!</b>", parse_mode="HTML")
        return

    # Проверка лимитов
    if currency == "ncoin":
        if price < MIN_PRICE_NCOIN or price > MAX_PRICE_NCOIN:
            await message.answer(f"❌ Цена в nCoin должна быть в диапазоне от <b>{MIN_PRICE_NCOIN:,}</b> до <b>{MAX_PRICE_NCOIN:,}</b>!", parse_mode="HTML")
            return
    else:
        if price < MIN_PRICE_NMP or price > MAX_PRICE_NMP:
            await message.answer(f"❌ Цена в NMP должна быть в диапазоне от <b>{MIN_PRICE_NMP:,}</b> до <b>{MAX_PRICE_NMP:,}</b>!", parse_mode="HTML")
            return

    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO p2p_nft_listings (nft_id, seller_id, currency, price, status)
        VALUES (%s, %s, %s, %s, 'active')
    """, (nft_id, user_id, currency, price))
    conn.commit()
    cursor.close()
    conn.close()

    curr_str = "nCoin" if currency == "ncoin" else "NMP"
    icon = get_nft_icon(nft.get("nft_name", ""), nft.get("image_key", ""))
    
    text = (
        "🎉 <b>ОБЪЯВЛЕНИЕ УСПЕШНО РАЗМЕЩЕНО!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon} Предмет: <b>{nft['nft_name']} #{nft['serial_number']}</b>\n"
        f"⚡️ Уровень: <code>{nft.get('level', 1)}/2</code> | 💎 <code>{nft.get('rarity', 'Обычный')}</code>\n"
        f"💵 Цена: <code>{price:,} {curr_str}</code>\n\n"
        "Ваш NFT появился в общем каталоге и доступен для покупки игроками!"
    )
    await message.answer(text, parse_mode="HTML")


# === МОИ ОБЪЯВЛЕНИЯ И СНЯТИЕ С ПРОДАЖИ ===

@router.callback_query(F.data == "p2p_my_listings")
async def show_my_p2p_listings(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user_listings = get_user_active_listings(user_id)
    
    text = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "│  📦 <b>МОИ АКТИВНЫЕ ОБЪЯВЛЕНИЯ</b>\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
    )
    
    kb_buttons = []
    if user_listings:
        for item in user_listings:
            l_id, nft_id, curr, price, name, serial, lvl, img_key = item
            icon = get_nft_icon(name, img_key)
            curr_str = "nCoin" if curr == "ncoin" else "NMP"
            
            text += (
                f"{icon} <b>{name} #{serial}</b> (Lvl {lvl})\n"
                f" └ 🏷 Цена: <code>{int(price):,} {curr_str}</code>\n\n"
            )
            kb_buttons.append([
                InlineKeyboardButton(
                    text=f"❌ Снять с продажи {name} #{serial}",
                    callback_data=f"p2p_cancel:{l_id}"
                )
            ])
    else:
        text += "🕸 <i>У вас нет активных объявлений на P2P рынке.</i>"

    kb_buttons.append([InlineKeyboardButton(text="🔙 Назад в P2P", callback_data="p2p_main_cb")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")


@router.callback_query(F.data.startswith("p2p_cancel:"))
async def cancel_p2p_listing(callback: CallbackQuery):
    listing_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    conn = db.get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE p2p_nft_listings SET status = 'cancelled' WHERE listing_id = %s AND seller_id = %s AND status = 'active'", (listing_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    await callback.answer("✅ Объявление снято с продажи!", show_alert=True)
    if callback.message.photo:
        await callback.message.delete()
        await show_p2p_main(callback)
    else:
        await show_my_p2p_listings(callback)


@router.callback_query(F.data == "p2p_noop")
async def p2p_noop(callback: CallbackQuery):
    await callback.answer()
