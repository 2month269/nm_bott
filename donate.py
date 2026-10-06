# donate.py
import os
import html
import logging
import asyncio
import aiohttp
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, LinkPreviewOptions
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import db
import utils

logger = logging.getLogger(__name__)
router = Router()

CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")
ADMIN_IDS = [7727345054]  # Твой ID администратора

# Ссылки на картинки
IMG_TOP_DONATE = "https://i.ibb.co/mVDmJXth/IMG-20261003-105512-174.jpg"    # Картинка ТОП ДОНАТЕРОВ
IMG_DONATE_MENU = "https://i.ibb.co/Q72TkcLY/IMG-20261003-104722-851.jpg"  # Картинка ДОНАТ МЕНЮ

# Базовый курс: 1 Звезда = 1.25 NMP (т.е. 50 NMP = 40 Stars)
BASE_NMP_PER_STAR = 1.25

# Пакеты и оптовые скидки
PACKAGES = [
    {"nmp": 50, "stars": 40, "discount_lbl": ""},
    {"nmp": 100, "stars": 80, "discount_lbl": ""},
    {"nmp": 250, "stars": 200, "discount_lbl": ""},
    {"nmp": 1000, "stars": 400, "discount_lbl": "⚡(-50%) "},
    {"nmp": 3000, "stars": 800, "discount_lbl": "🔥(-67%) "},
    {"nmp": 20000, "stars": 4000, "discount_lbl": "💎(-75%) "}
]

class DonateState(StatesGroup):
    waiting_for_custom_amount = State()

def fnum(number: int | float) -> str:
    """Форматирует число с апострофом (1'000)"""
    return f"{int(number):,}".replace(",", "'")

def calc_stars_for_nmp(nmp: int) -> int:
    """Расчет стоимости в звездах с учетом оптовых скидок"""
    for pkg in reversed(PACKAGES):
        if nmp >= pkg["nmp"]:
            rate = pkg["stars"] / pkg["nmp"]
            return max(1, int(nmp * rate))
    return max(1, int(nmp / BASE_NMP_PER_STAR))

async def safe_edit_or_send(event: Message | CallbackQuery, text: str, reply_markup=None, photo_url: str = None):
    """Универсальная оптимизированная отправка/редактирование сообщений"""
    preview = LinkPreviewOptions(is_disabled=False, url=photo_url, prefer_large_media=True, show_above_text=True) if photo_url else None
    
    if isinstance(event, CallbackQuery):
        msg = event.message
        try:
            await msg.edit_text(text, reply_markup=reply_markup, parse_mode="HTML", link_preview_options=preview)
        except Exception:
            try:
                await msg.delete()
            except Exception:
                pass
            await msg.answer(text, reply_markup=reply_markup, parse_mode="HTML", link_preview_options=preview)
    else:
        await event.answer(text, reply_markup=reply_markup, parse_mode="HTML", link_preview_options=preview)

# --- КЛАВИАТУРЫ ---

def get_donate_menu_kb() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="50 NMP", callback_data="don_pkg:50"),
            InlineKeyboardButton(text="100 NMP", callback_data="don_pkg:100"),
            InlineKeyboardButton(text="250 NMP", callback_data="don_pkg:250")
        ],
        [
            InlineKeyboardButton(text="⚡(-50%) 1000 NMP", callback_data="don_pkg:1000"),
            InlineKeyboardButton(text="🔥(-67%) 3000 NMP", callback_data="don_pkg:3000")
        ],
        [
            InlineKeyboardButton(text="💎(-75%) 20'000 NMP", callback_data="don_pkg:20000")
        ],
        [
            InlineKeyboardButton(text="⬅️ назад", callback_data="don_top:month"),
            InlineKeyboardButton(text="Другое 🌍", callback_data="don_custom_choice")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_top_kb(current_period: str = "month") -> InlineKeyboardMarkup:
    btn_week = InlineKeyboardButton(text="🗓 За неделю", callback_data="don_top:week")
    btn_month = InlineKeyboardButton(text="🗓 За месяц", callback_data="don_top:month")
    btn_all = InlineKeyboardButton(text="🌐 За все время", callback_data="don_top:all")

    if current_period == "month":
        period_row = [btn_week, btn_all]
    elif current_period == "week":
        period_row = [btn_month, btn_all]
    else:
        period_row = [btn_week, btn_month]

    return InlineKeyboardMarkup(inline_keyboard=[
        period_row,
        [InlineKeyboardButton(text="История донатов 📜", callback_data="don_history:1")],
        [InlineKeyboardButton(text="🛍️ Донат меню", callback_data="don_menu")]
    ])

def get_payment_methods_kb(nmp: int, stars: int) -> InlineKeyboardMarkup:
    usd_val = round(stars * 0.02, 2)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🌟 Оплатить {stars} ⭐️ (Telegram Stars)", callback_data=f"don_pay_stars:{nmp}:{stars}")],
        [InlineKeyboardButton(text=f"💳 Crypto Bot (${usd_val})", callback_data=f"don_pay_crypto:{nmp}:{stars}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="don_menu")]
    ])

# --- ЭКРАН ТОП ДОНАТЕРОВ ---

@router.message(Command("donation", "donate"))
@router.message(F.text.lower().in_(["донат", "донейшн", "пожертвования", "/donation", "/donate"]))
async def show_donation_entry(message: Message, state: FSMContext):
    await state.clear()
    await send_or_edit_top(message, message.from_user.id, period="month", is_edit=False)

@router.callback_query(F.data.startswith("don_top:"))
async def top_period_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    period = call.data.split(":")[1]
    await send_or_edit_top(call, call.from_user.id, period=period, is_edit=True)

async def send_or_edit_top(event: Message | CallbackQuery, user_id: int, period: str = "month", is_edit: bool = True):
    # Оптимизация: асинхронный запуск запросов к БД без блокировок
    try:
        if asyncio.iscoroutinefunction(getattr(db, "get_top_donators", None)):
            top_list = await db.get_top_donators(period=period, limit=20)
            user_rank, user_stars = await db.get_user_donation_stats(user_id, period=period)
        else:
            top_list = await asyncio.to_thread(db.get_top_donators, period=period, limit=20)
            user_rank, user_stars = await asyncio.to_thread(db.get_user_donation_stats, user_id, period=period)
    except Exception as e:
        logger.error(f"Ошибка загрузки данных доната из БД: {e}")
        top_list = []
        user_rank, user_stars = None, 0

    period_title = "за месяц" if period == "month" else ("за неделю" if period == "week" else "за все время")
    
    lines = []
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    
    for i in range(1, 21):
        if i <= len(top_list):
            p = top_list[i-1]
            if isinstance(p, dict):
                p_uid = p.get("user_id", 0)
                p_stars = p.get("stars", p.get("total_stars", 0))
                p_fname = p.get("first_name", "")
                p_uname = p.get("username", "")
            else:
                p_uid, p_stars = p[0], p[1]
                p_fname = p[2] if len(p) > 2 else ""
                p_uname = p[3] if len(p) > 3 else ""

            p_name = html.escape((p_fname or (f"@{p_uname}" if p_uname else f"Игрок {p_uid}")).strip())
            if len(p_name) > 16:
                p_name = p_name[:14] + "..."
            
            icon = medals.get(i, "💎" if i <= 10 else "⚡")
            lines.append(f"{i}.  {icon}  <b>{p_name}</b> | {p_stars} ⭐️")
        else:
            lines.append(f"{i}.")
            
    top_text_body = "\n".join(lines)
    user_rank_str = f"{user_rank}" if user_rank else "20+"
    
    caption = (
        f"🏆 <b>ТОП ДОНАТЕРОВ</b> ⭐️\n"
        f"<i>лидеры по пожертвованиям\n{period_title}</i>\n"
        "· · · · · · · · · · · · · · · · · · · · ·\n"
        f"{top_text_body}\n\n"
        f"<blockquote>{user_rank_str}.  🎖  <b>Вы:</b> {user_stars} ⭐️ ❞</blockquote>"
    )

    hidden_link = f'<a href="{IMG_TOP_DONATE}">&#8203;</a>'
    full_text = f"{hidden_link}{caption}"
    kb = get_top_kb(period)

    await safe_edit_or_send(event, full_text, reply_markup=kb, photo_url=IMG_TOP_DONATE)

# --- ЭКРАН ДОНАТ МЕНЮ ---

@router.callback_query(F.data == "don_menu")
async def show_donate_menu_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    
    try:
        if asyncio.iscoroutinefunction(getattr(db, "get_donation_settings", None)):
            settings = await db.get_donation_settings()
        else:
            settings = await asyncio.to_thread(db.get_donation_settings)
    except Exception as e:
        logger.error(f"Ошибка получения настроек доната: {e}")
        settings = {"bonus": 0, "discount": 0, "custom_text": ""}

    bonus_str = f"\n🎁 <b>БОНУС К ДОНАТУ: +{settings.get('bonus', 0)}% NMP</b>" if settings.get("bonus", 0) > 0 else ""
    discount_str = f"\n🔥 <b>АКЦИЯ: Скидка {settings.get('discount', 0)}% на всё!</b>" if settings.get("discount", 0) > 0 else ""
    custom_msg = f"\n\n📢 <i>{settings.get('custom_text', '')}</i>" if settings.get("custom_text") else ""

    text = (
        f"💎 <b>ВВЕДИТЕ КОЛ-ВО NMP</b>\n\n"
        f"<blockquote>🪙 1 ⭐️ = {BASE_NMP_PER_STAR} NMPOINT ❞</blockquote>\n"
        f"<blockquote>ℹ️ Напишите в ответ на это сообщение сумму в NMP, которую вы хотите задонатить, или выберите один из предложенных вариантов ниже. ❞</blockquote>"
        f"{bonus_str}{discount_str}{custom_msg}\n\n"
        f"<i>*политика возврата*</i>"
    )

    hidden_link = f'<a href="{IMG_DONATE_MENU}">&#8203;</a>'
    full_text = f"{hidden_link}{text}"

    await safe_edit_or_send(call, full_text, reply_markup=get_donate_menu_kb(), photo_url=IMG_DONATE_MENU)

# --- ЭКРАН ИСТОРИИ ДОНАТОВ ---

@router.callback_query(F.data.startswith("don_history:"))
async def show_donate_history(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    try:
        if asyncio.iscoroutinefunction(getattr(db, "get_donations_history", None)):
            history = await db.get_donations_history(user_id, limit=5)
        else:
            history = await asyncio.to_thread(db.get_donations_history, user_id, limit=5)
    except Exception as e:
        logger.error(f"Ошибка получения истории донатов: {e}")
        history = []
    
    if not history:
        body = "*пусто*\nсделайте первый донат!"
    else:
        rows = []
        for h in history:
            # Безопасное извлечение независимо от формата (словарь, Row или кортеж)
            if isinstance(h, dict):
                stars_amt = h.get("stars_amt") or h.get("stars_eq") or h.get("stars", 0)
                nmp_amt = h.get("nmp") or h.get("nmp_amount", 0)
                date_val = h.get("created_at") or h.get("date") or h.get("timestamp") or ""
            else:
                stars_amt = h[0] if len(h) > 0 else 0
                nmp_amt = h[1] if len(h) > 1 else 0
                date_val = h[2] if len(h) > 2 else ""

            if isinstance(date_val, datetime):
                date_str = date_val.strftime("%d.%m.%Y %H:%M")
            else:
                date_str = str(date_val)[:16]
            rows.append(f"• +{fnum(nmp_amt)} NMP за {stars_amt} ⭐️ (<i>{date_str}</i>)")
        body = "\n".join(rows)

    text = (
        f"📜 <b>ИСТОРИЯ ДОНАТОВ</b>\n"
        "· · · · · · · · · · · · · · · · · · · · ·\n"
        f"{body}\n"
        "· · · · · · · · · · · · · · · · · · · · ·\n"
        "↗️ страница 1/1"
    )
    
    hidden_link = f'<a href="{IMG_DONATE_MENU}">&#8203;</a>'
    full_text = f"{hidden_link}{text}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍️ Донат меню", callback_data="don_menu")],
        [InlineKeyboardButton(text="⬅️ назад", callback_data="don_top:month")]
    ])

    await safe_edit_or_send(call, full_text, reply_markup=kb, photo_url=IMG_DONATE_MENU)

# --- ВЫБОР ПАКЕТА ИЛИ ВВОД СВОЕЙ СУММЫ ---

@router.callback_query(F.data.startswith("don_pkg:"))
async def select_pkg_callback(call: CallbackQuery):
    await call.answer()
    nmp = int(call.data.split(":")[1])
    
    try:
        if asyncio.iscoroutinefunction(getattr(db, "get_donation_settings", None)):
            settings = await db.get_donation_settings()
        else:
            settings = await asyncio.to_thread(db.get_donation_settings)
    except Exception:
        settings = {"bonus": 0, "discount": 0}
        
    stars = calc_stars_for_nmp(nmp)
    
    if settings.get("discount", 0) > 0:
        stars = max(1, int(stars * (1 - settings["discount"] / 100)))

    bonus_nmp = int(nmp * (settings.get("bonus", 0) / 100)) if settings.get("bonus", 0) > 0 else 0
    total_nmp = nmp + bonus_nmp
    bonus_note = f" (включая бонус +{bonus_nmp} NMP)" if bonus_nmp > 0 else ""

    text = (
        f"💎 <b>ОФОРМЛЕНИЕ ПОКУПКИ</b>\n\n"
        f"• Количество: <b>{fnum(total_nmp)} NMP</b>{bonus_note}\n"
        f"• К оплате: <b>{stars} ⭐️</b>\n"
        f"• Курс: <b>1 NMP ~ {round(stars / total_nmp, 3)} ⭐️</b>\n\n"
        f"Выберите способ оплаты:"
    )

    hidden_link = f'<a href="{IMG_DONATE_MENU}">&#8203;</a>'
    await safe_edit_or_send(call, f"{hidden_link}{text}", reply_markup=get_payment_methods_kb(total_nmp, stars), photo_url=IMG_DONATE_MENU)

@router.callback_query(F.data == "don_custom_choice")
async def custom_choice_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(DonateState.waiting_for_custom_amount)
    
    text = (
        "💎 <b>ВВЕДИТЕ ЖЕЛАЕМОЕ КОЛИЧЕСТВО NMP</b>\n\n"
        "Отправьте целое число в чат (минимум 10 NMP):"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="don_menu")]])
    await safe_edit_or_send(call, text, reply_markup=kb)

@router.message(DonateState.waiting_for_custom_amount, F.text)
async def process_custom_amount(message: Message, state: FSMContext):
    try:
        nmp = int(message.text.replace(" ", "").replace("k", "000").replace("к", "000"))
        if nmp < 10: raise ValueError
    except ValueError:
        await message.reply("❌ Введите корректное число от 10 NMP!")
        return

    await state.clear()
    try:
        if asyncio.iscoroutinefunction(getattr(db, "get_donation_settings", None)):
            settings = await db.get_donation_settings()
        else:
            settings = await asyncio.to_thread(db.get_donation_settings)
    except Exception:
        settings = {"bonus": 0, "discount": 0}
        
    stars = calc_stars_for_nmp(nmp)
    if settings.get("discount", 0) > 0:
        stars = max(1, int(stars * (1 - settings["discount"] / 100)))

    bonus_nmp = int(nmp * (settings.get("bonus", 0) / 100)) if settings.get("bonus", 0) > 0 else 0
    total_nmp = nmp + bonus_nmp
    bonus_note = f" (+{bonus_nmp} бонус)" if bonus_nmp > 0 else ""

    text = (
        f"💎 <b>ОФОРМЛЕНИЕ ПОКУПКИ</b>\n\n"
        f"• Количество: <b>{fnum(total_nmp)} NMP</b>{bonus_note}\n"
        f"• К оплате: <b>{stars} ⭐️</b>\n"
        f"• Примерный курс: <b>1 NMP ~ {round(stars / total_nmp, 3)} ⭐️</b>\n\n"
        f"Выберите способ оплаты:"
    )
    hidden_link = f'<a href="{IMG_DONATE_MENU}">&#8203;</a>'
    await safe_edit_or_send(message, f"{hidden_link}{text}", reply_markup=get_payment_methods_kb(total_nmp, stars), photo_url=IMG_DONATE_MENU)

# ==========================================
# 🌟 ОПЛАТА ЧЕРЕЗ TELEGRAM STARS
# ==========================================

@router.callback_query(F.data.startswith("don_pay_stars:"))
async def pay_stars_callback(call: CallbackQuery, bot: Bot):
    await call.answer()
    parts = call.data.split(":")
    nmp = int(parts[1])
    stars = int(parts[2])

    title = f"Покупка {fnum(nmp)} NMP"
    desc = f"Зачисление {fnum(nmp)} NMP в бота nCoin."
    payload = f"stars_donate:{call.from_user.id}:{nmp}:{stars}"

    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title=title,
        description=desc,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="NMP", amount=stars)]
    )

@router.pre_checkout_query()
async def process_stars_precheckout(pre_checkout: PreCheckoutQuery):
    await pre_checkout.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_stars_pay(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("stars_donate:"):
        _, uid_str, nmp_str, stars_str = payload.split(":")
        user_id = int(uid_str)
        nmp = int(nmp_str)
        stars = int(stars_str)

        try:
            db.update_nmp_balance(user_id, nmp)
            
            # Сохранение с поддержкой разных имен аргументов в db.py
            try:
                db.add_donation_record(user_id=user_id, stars_amt=stars, nmp=nmp, stars_eq=stars)
            except TypeError:
                try:
                    db.add_donation_record(user_id, stars, nmp)
                except Exception as e_inner:
                    logger.error(f"Не удалось записать донат в историю: {e_inner}")

        except Exception as e:
            logger.error(f"Ошибка фиксации платежа Stars: {e}")

        text = (
            f"🎉 <b>ОПЛАТА УСПЕШНО ЗАВЕРШЕНА!</b> 🎉\n"
            "· · · · · · · · · · · · · · · · · · · · ·\n"
            f"Вам моментально начислено: <b>+{fnum(nmp)} NMP</b>!\n"
            f"Ваш вклад <b>{stars} ⭐️</b> учтен в мировом топе донатеров!\n\n"
            f"Спасибо за поддержку проекта! 💖"
        )
        await message.answer(text, parse_mode="HTML")

# ==========================================
# 💳 ОПЛАТА ЧЕРЕЗ CRYPTO BOT
# ==========================================

@router.callback_query(F.data.startswith("don_pay_crypto:"))
async def pay_crypto_callback(call: CallbackQuery):
    await call.answer()
    parts = call.data.split(":")
    nmp = int(parts[1])
    stars = int(parts[2])
    user_id = call.from_user.id

    if not CRYPTO_BOT_TOKEN:
        await call.answer("❌ Crypto Bot временно недоступен!", show_alert=True)
        return

    usd_amount = round(stars * 0.02, 2)
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    payload = f"{user_id}:{nmp}:{stars}"
    data = {
        "currency_type": "fiat",
        "fiat": "USD",
        "amount": str(usd_amount),
        "payload": payload,
        "description": f"Покупка {nmp} NMP (ID: {user_id})"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                res = await resp.json()
                if not res.get("ok"):
                    await call.answer("Ошибка выписки счета!", show_alert=True)
                    return
                inv = res["result"]
    except Exception as e:
        logger.error(f"CryptoBot error: {e}")
        await call.answer("Ошибка связи с платежным сервисом!", show_alert=True)
        return

    invoice_id = inv["invoice_id"]
    pay_url = inv["bot_invoice_url"]

    text = (
        f"💳 <b>ОПЛАТА ЧЕРЕЗ CRYPTO BOT</b>\n\n"
        f"• Товар: <b>{fnum(nmp)} NMP</b>\n"
        f"• К оплате: <b>${usd_amount:.2f} USD</b>\n"
        f"• Номер счета: <code>#{invoice_id}</code>\n\n"
        "1. Перейдите по кнопке ниже и оплатите счет.\n"
        "2. После оплаты нажмите «✅ Проверить оплату»."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить в @CryptoBot", url=pay_url)],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"don_chk_crypto:{invoice_id}:{nmp}:{stars}")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="don_menu")]
    ])
    await safe_edit_or_send(call, text, reply_markup=kb)

@router.callback_query(F.data.startswith("don_chk_crypto:"))
async def check_crypto_callback(call: CallbackQuery):
    parts = call.data.split(":")
    invoice_id = int(parts[1])
    nmp = int(parts[2])
    stars = int(parts[3])
    user_id = call.from_user.id

    url = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                res = await resp.json()
                if res.get("ok") and res.get("result", {}).get("items"):
                    item = res["result"]["items"][0]
                    if item.get("status") == "paid":
                        db.update_nmp_balance(user_id, nmp)
                        
                        try:
                            db.add_donation_record(user_id=user_id, stars_amt=stars, nmp=nmp, stars_eq=stars, crypto_usd=float(item.get("amount", 0)))
                        except TypeError:
                            try:
                                db.add_donation_record(user_id, stars, nmp)
                            except Exception as e_inner:
                                logger.error(f"Ошибка сохранения истории CryptoBot: {e_inner}")

                        await call.answer("🎉 Оплата подтверждена!", show_alert=True)
                        text = (
                            f"🎉 <b>ОПЛАТА ПОДТВЕРЖДЕНА!</b>\n\n"
                            f"Вам успешно зачислено: <b>+{fnum(nmp)} NMP</b>!\n"
                            f"Ваш результат учтен в топе донатеров! 🚀"
                        )
                        await safe_edit_or_send(call, text)
                        return
    except Exception as e:
        logger.error(f"Error checking invoice: {e}")

    await call.answer("⏳ Оплата еще не поступила. Завершите перевод в боте!", show_alert=True)

# ==========================================
# 👑 АДМИН-КОМАНДА ДЛЯ НАСТРОЙКИ СКИДОК И БОНУСОВ
# ==========================================

@router.message(Command("set_donate"))
async def admin_set_donate_cmd(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await message.reply(
            "ℹ️ <b>Формат:</b> <code>/set_donate &lt;скидка %&gt; &lt;бонус %&gt; [текст]</code>\n"
            "Пример: <code>/set_donate 15 20 Скидки на выходные!</code>\n"
            "Сбросить: <code>/set_donate 0 0</code>",
            parse_mode="HTML"
        )
        return

    try:
        discount = int(parts[1])
        bonus = int(parts[2])
        text = parts[3] if len(parts) > 3 else ""
        
        if asyncio.iscoroutinefunction(getattr(db, "update_donation_settings", None)):
            await db.update_donation_settings(discount=discount, bonus=bonus, text=text)
        else:
            await asyncio.to_thread(db.update_donation_settings, discount=discount, bonus=bonus, text=text)
            
        await message.reply(f"✅ Настройки доната обновлены:\n• Скидка: {discount}%\n• Бонус: {bonus}%\n• Текст: {text or 'нет'}")
    except ValueError:
        await message.reply("❌ Числа скидки и бонуса должны быть целыми!")
