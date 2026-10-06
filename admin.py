# admin.py
import aiohttp
import time
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    PreCheckoutQuery, LabeledPrice
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, StateFilter
import db
import utils

logger = logging.getLogger(__name__)
router = Router()
ADMIN_ID = 7727345054


class AdminStates(StatesGroup):
    waiting_for_block = State()
    waiting_for_unblock = State()
    waiting_for_give = State()
    waiting_for_take = State()
    waiting_for_search = State()
    waiting_for_promo = State()
    waiting_for_broadcast_msg = State()  # Ожидание сообщения для обычной рассылки
    confirm_broadcast = State()          # Подтверждение запуска обычной рассылки
    
    # --- Состояния для Донат-рассылки ---
    waiting_for_donate_reason = State()        # Шаг 1: Причина / Цель сбора
    waiting_for_donate_requisites = State()    # Шаг 2: Реквизиты и способ оплаты
    waiting_for_donate_stars_amount = State()  # Шаг 3а: Количество Stars для инвойса
    waiting_for_donate_crypto_link = State()   # Шаг 3б: Ссылка на CryptoBot / @send
    waiting_for_donate_pm_link = State()       # Шаг 3в: Ссылка на ЛС админа
    waiting_for_donate_custom_btn = State()    # Шаг 3г: Произвольная кнопка-ссылка
    confirm_donate_broadcast = State()         # Шаг 4: Предпросмотр и запуск


class AdminGiftState(StatesGroup):
    waiting_for_user_id = State()


def get_admin_kb() -> InlineKeyboardMarkup:
    """Создает меню администратора из кнопок в плиточном формате"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚫 Заблокировать", callback_data="adm_block"),
            InlineKeyboardButton(text="✅ Разблокировать", callback_data="adm_unblock")
        ],
        [
            InlineKeyboardButton(text="💰 Выдать", callback_data="adm_give"),
            InlineKeyboardButton(text="💸 Забрать", callback_data="adm_take")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats"),
            InlineKeyboardButton(text="🎁 Розыгрыш", callback_data="adm_draw")
        ],
        [
            InlineKeyboardButton(text="🔍 Поиск по ID", callback_data="adm_search"),
            InlineKeyboardButton(text="🎫 Создать Промо", callback_data="adm_promo")
        ],
        [
            InlineKeyboardButton(text="🏆 Сделать турнир", callback_data="adm_start_tournament"),
            InlineKeyboardButton(text="📋 Списки идей", callback_data="adm_spisok")
        ],
        [
            InlineKeyboardButton(text="Рассылка💄", callback_data="adm_broadcast"),
            InlineKeyboardButton(text="🌟 Донаты", callback_data="adm_donations")
        ],
        [
            InlineKeyboardButton(text="🎁 Подарить Telegram Подарок", callback_data="adm_send_tg_gift")
        ]
    ])


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer(
        "👑 *Панель Управления Проектом nCoin*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Вам доступны административные инструменты для полного контроля игровой экосистемы бота.",
        reply_markup=get_admin_kb(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin_main")
async def admin_main_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.answer()
    await state.clear()
    await call.message.edit_text(
        "👑 <b>Панель Управления Проектом nCoin</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Вам доступны административные инструменты для полного контроля игровой экосистемы бота.",
        reply_markup=get_admin_kb(),
        parse_mode="HTML"
    )


# --- 1. БЛОКИРОВКА ---
@router.callback_query(F.data == "adm_block")
async def block_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("👤 *Введите Telegram ID пользователя для БЛОКИРОВКИ:*", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_block)

@router.message(StateFilter(AdminStates.waiting_for_block))
async def process_block(message: Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        db.set_block_status(target_id, True)
        await message.answer(f"✅ Пользователь `{target_id}` успешно *заблокирован*!", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Ошибка: Введите корректный числовой ID пользователя!")
    finally:
        await state.clear()


# --- 2. РАЗБЛОКИРОВКА ---
@router.callback_query(F.data == "adm_unblock")
async def unblock_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("👤 *Введите Telegram ID пользователя для РАЗБЛОКИРОВКИ:*", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_unblock)

@router.message(StateFilter(AdminStates.waiting_for_unblock))
async def process_unblock(message: Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        db.set_block_status(target_id, False)
        await message.answer(f"✅ Пользователь `{target_id}` успешно *разблокирован*!", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Ошибка: Введите корректный числовой ID пользователя!")
    finally:
        await state.clear()


# 1. ПОЛУЧЕНИЕ СПИСКА ПОДАРКОВ ОТ TELEGRAM (Прямой API запрос)
@router.callback_query(F.data == "adm_send_tg_gift")
async def adm_start_gift_process(call: CallbackQuery, bot: Bot, state: FSMContext):
    await call.answer()
    
    try:
        url = f"https://api.telegram.org/bot{bot.token}/getAvailableGifts"
        async with aiohttp.ClientSession() as session:
            async with session.post(url) as resp:
                res = await resp.json()
        
        if not res.get("ok"):
            err_desc = res.get("description", "Неизвестная ошибка Telegram API")
            return await call.message.edit_text(f"❌ Ошибка Telegram API: <code>{err_desc}</code>", parse_mode="HTML")

        gifts_list = res.get("result", {}).get("gifts", [])
        
        if not gifts_list:
            return await call.message.edit_text("❌ В данный момент нет доступных подарков в Telegram API.")

        keyboard = []
        for gift in gifts_list[:10]: # Показываем первые 10 подарков
            gift_id = gift.get("id", "")
            star_count = gift.get("star_count", 0)
            btn_text = f"🎁 {star_count} Stars (ID: {gift_id[:8]}...)"
            keyboard.append([
                InlineKeyboardButton(
                    text=btn_text, 
                    callback_data=f"adm_select_gift:{gift_id}:{star_count}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin_main")])
        
        text = (
            "🎁 <b>ОТПРАВКА ОФИЦИАЛЬНОГО ПОДАРКА TELEGRAM</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Выберите подарок из официального каталога Telegram ниже:\n\n"
            "<i>⚠️ Убедитесь, что у бота достаточно Stars на балансе!</i>"
        )
        
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка получения списка подарков: {e}")
        await call.message.edit_text(f"❌ Не удалось загрузить подарки из Telegram: <code>{e}</code>", parse_mode="HTML")


# 2. ВЫБОР ПОДАРКА И ЗАПРОС USER_ID / USERNAME
@router.callback_query(F.data.startswith("adm_select_gift:"))
async def adm_select_gift_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    parts = call.data.split(":")
    gift_id = parts[1]
    star_count = parts[2]
    
    await state.update_data(gift_id=gift_id, gift_stars=star_count)
    await state.set_state(AdminGiftState.waiting_for_user_id)
    
    text = (
        f"🎁 <b>Выбран подарок за {star_count} Stars</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ <b>Введите Telegram ID или @username пользователя</b>, которому нужно отправить этот подарок:\n"
        "<i>Например:</i> <code>123456789</code> или <code>@username</code>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_main", style="danger")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# 3. ВВОД ID / @USERNAME И МОМЕНТАЛЬНАЯ ОТПРАВКА ПОДАРКА (Прямой API запрос)
@router.message(AdminGiftState.waiting_for_user_id)
async def adm_process_send_gift(message: Message, bot: Bot, state: FSMContext):
    raw_input = message.text.strip()
    clean_input = raw_input.lstrip("@").strip()
    
    target_user_id = None
    target_username = None

    # 1. Если введены только цифры (Telegram ID)
    if clean_input.isdigit():
        target_user_id = int(clean_input)
    else:
        # 2. Поиск по @username в базе данных
        conn = db.get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT user_id, username FROM users WHERE LOWER(username) = %s OR LOWER(username) = %s",
                (clean_input.lower(), f"@{clean_input.lower()}")
            )
            row = cursor.fetchone()
            if row:
                target_user_id = row[0]
                target_username = row[1]
        except Exception as e:
            logger.error(f"Ошибка поиска юзера по username {clean_input}: {e}")
        finally:
            cursor.close()
            conn.close()

    if not target_user_id:
        return await message.answer(
            "❌ <b>Пользователь не найден!</b>\n"
            "Убедитесь, что правильно ввели ID или @username игрока (пользователь должен быть зарегистрирован в боте):",
            parse_mode="HTML"
        )
        
    data = await state.get_data()
    gift_id = data["gift_id"]
    star_count = data["gift_stars"]
    await state.clear()
    
    loading_msg = await message.answer("⏳ Отправляем подарок через Telegram API...")
    
    try:
        url = f"https://api.telegram.org/bot{bot.token}/sendGift"
        payload = {
            "user_id": target_user_id,
            "gift_id": gift_id,
            "text": "🎁 Залетай к нам в игру!"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                res = await resp.json()
        
        user_info_str = f"@{target_username}" if target_username else f"ID: <code>{target_user_id}</code>"
        
        if res.get("ok"):
            await loading_msg.edit_text(
                f"✅ <b>ПОДАРОК УСПЕШНО ОТПРАВЛЕН!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 Получатель: {user_info_str}\n"
                f"⭐ Стоимость: <b>{star_count} Stars</b>\n\n"
                f"Подарок уже отображается в профиле пользователя!",
                parse_mode="HTML"
            )
        else:
            err_msg = res.get("description", "Неизвестная ошибка Telegram API")
            await loading_msg.edit_text(
                f"❌ <b>Ошибка отправки подарка!</b>\n\n"
                f"Причина: <code>{err_msg}</code>\n\n"
                f"<i>Проверьте, есть ли у бота нужные {star_count} Stars на балансе.</i>",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Ошибка отправки подарка Telegram: {e}")
        await loading_msg.edit_text(
            f"❌ <b>Ошибка отправки подарка!</b>\n\n"
            f"Причина: <code>{e}</code>",
            parse_mode="HTML"
    )

# --- 3. ВЫДАТЬ СРЕДСТВА ---
@router.callback_query(F.data == "adm_give")
async def give_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "✍️ *Введите данные для выдачи в формате:*\n"
        "`<ID пользователя> <валюта> <сумма>`\n\n"
        "Варианты валюты: `coin` / `nmp` (Пример: `7727345054 coin 10к` или `7727345054 nmp 50`)",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_give)

@router.message(StateFilter(AdminStates.waiting_for_give))
async def process_give(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        if len(parts) < 3:
            await message.answer("❌ Ошибка: Недостаточно параметров! Сделайте по шаблону.")
            return
            
        target_id = int(parts[0])
        currency = parts[1].lower().strip()
        amount_str = parts[2]
        
        try:
            amount = utils.parse_bet_input(amount_str, 999999999999)
        except TypeError:
            amount = utils.parse_bet_input(amount_str)
            
        if currency == "coin":
            db.update_balance(target_id, amount)
            await message.answer(f"✅ Выдано *{amount:,} nCoin* на баланс игрока `{target_id}`!", parse_mode="Markdown")
        elif currency == "nmp":
            db.update_nmp_balance(target_id, amount)
            await message.answer(f"✅ Выдано *{amount:,} NMP* на баланс игрока `{target_id}`!", parse_mode="Markdown")
        else:
            await message.answer("❌ Валюта указана неверно! Возможные: `coin` или `nmp`.")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка парсинга параметров: `{str(e)}`", parse_mode="Markdown")
    finally:
        await state.clear()


# --- 4. ЗАБРАТЬ СРЕДСТВА ---
@router.callback_query(F.data == "adm_take")
async def take_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "✍️ *Введите данные для списания в формате:*\n"
        "`<ID пользователя> <валюта> <сумма>`\n\n"
        "Варианты валюты: `coin` / `nmp` (Пример: `7727345054 coin 10к` или `7727345054 nmp 10`)",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_take)

@router.message(StateFilter(AdminStates.waiting_for_take))
async def process_take(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        if len(parts) < 3:
            await message.answer("❌ Ошибка: Мало аргументов!")
            return
            
        target_id = int(parts[0])
        currency = parts[1].lower().strip()
        amount_str = parts[2]
        
        try:
            amount = utils.parse_bet_input(amount_str, 999999999999)
        except TypeError:
            amount = utils.parse_bet_input(amount_str)
            
        if currency == "coin":
            db.update_balance(target_id, -amount)
            await message.answer(f"✅ Списано *{amount:,} nCoin* с баланса игрока `{target_id}`!", parse_mode="Markdown")
        elif currency == "nmp":
            db.update_nmp_balance(target_id, -amount)
            await message.answer(f"✅ Списано *{amount:,} NMP* с баланса игрока `{target_id}`!", parse_mode="Markdown")
        else:
            await message.answer("❌ Валюта указана неверно! Возможные: `coin` или `nmp`.")
    except Exception as e:
        await message.answer(f"❌ Ошибка списания: `{str(e)}`", parse_mode="Markdown")
    finally:
        await state.clear()


# --- 5. СТАТИСТИКА ---
@router.callback_query(F.data == "adm_stats")
async def stats_callback(callback: CallbackQuery):
    await callback.answer()
    stats = db.get_admin_stats()
    text = (
        "📊 *Статистика Бот-Проекта (за последние 24ч)*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Всего зарегистрировано игроков: *{stats['total_users']}*\n"
        f"🆕 Присоединилось за сутки: *{stats['new_users']}*\n"
        f"🎮 Сыграно игровых раундов: *{stats['games_played']}*\n"
        f"💸 Игровой оборот системы: *{stats['turnover']:,.2f} nCoin*"
    )
    await callback.message.answer(text, reply_markup=get_admin_kb(), parse_mode="Markdown")


# --- 6. РОЗЫГРЫШ ---
@router.callback_query(F.data == "adm_draw")
async def draw_callback(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer("🎰 Выбираем случайного победителя...")
    
    winner = db.get_random_winner()
    if not winner:
        await callback.message.answer("❌ Ошибка: В базе данных нет подходящих активных игроков!")
        return

    winner_id = winner[0]
    prize_amount = 100000
    db.update_balance(winner_id, prize_amount)

    winner_user = db.get_user(winner_id)
    first_name = winner_user.get("first_name") or "Игрок"
    username = winner_user.get("username")

    username_str = f"@{username.lstrip('@')}" if username and username != "none" else "отсутствует"
    display_name = first_name.replace("_", "\\_").replace("*", "")

    pm_status = "✅ Успешно доставлено"
    try:
        await bot.send_message(
            winner_id,
            f"🎉 *ПОЗДРАВЛЯЕМ! Вы победили в случайном розыгрыше от администрации!*\n\n"
            f"💰 На ваш баланс зачислено: *+{prize_amount:,} nCoin*!",
            parse_mode="Markdown"
        )
    except Exception as e:
        pm_status = "❌ Не удалось (Заблокировал бота)"
        logging.warning(f"Не удалось отправить личное сообщение победителю {winner_id}: {e}")

    status_msg = await callback.message.answer("📢 *Рассылка анонса об итогах розыгрыша всем игрокам...*", parse_mode="Markdown")

    announcement_text = (
        "🎉 *ГЛОБАЛЬНЫЙ РОЗЫГРЫШ МОНЕТ!* 🎉\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Система случайным образом выбрала победителя среди активных игроков!\n\n"
        f"🎁 Победитель: [{display_name}](tg://user?id={winner_id}) ({username_str})\n"
        f"💰 Выигрыш: *+{prize_amount:,} nCoin*!"
    )

    user_ids = db.get_all_user_ids()
    sent_success = 0
    sent_fail = 0

    for uid in user_ids:
        if uid != ADMIN_ID:
            try:
                await bot.send_message(uid, announcement_text, parse_mode="Markdown")
                sent_success += 1
                await asyncio.sleep(0.035)
            except Exception:
                sent_fail += 1

    admin_report = (
        "📊 *ИТОГИ И СТАТИСТИКА РОЗЫГРЫША* 📊\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Победитель:* [{display_name}](tg://user?id={winner_id})\n"
        f"🆔 *ID победителя:* `{winner_id}`\n"
        f"🏷 *Юзернейм:* {username_str}\n"
        f"💰 *Зачисленный приз:* `+{prize_amount:,} nCoin`\n"
        f"📬 *Уведомление победителю:* {pm_status}\n\n"
        "📈 *Статистика анонса для игроков:*\n"
        f"✅ Успешно получено: *{sent_success}*\n"
        f"❌ Не доставлено: *{sent_fail}*\n"
        f"👥 Всего пользователей: *{len(user_ids)}*"
    )

    await status_msg.edit_text(admin_report, reply_markup=get_admin_kb(), parse_mode="Markdown")


# --- 7. ПОИСК ПО ID С ПОЛНОЙ ИСТОРИЕЙ ИГР И ПЕРЕВОДОВ ЗА 72Ч ---
@router.callback_query(F.data == "adm_search")
async def search_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🔎 *Введите Telegram ID игрока для глубокого анализа профиля:*", parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_search)

@router.message(StateFilter(AdminStates.waiting_for_search))
async def process_search(message: Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        user = db.get_user(target_id)
        rank = db.get_user_rank(target_id)
        
        status = "🚫 Заблокирован" if user["is_blocked"] else "🟢 Активен"
        first_name = user.get("first_name") or "Игрок"
        username_str = f"@{user['username'].lstrip('@')}" if user.get("username") else "отсутствует"

        # 1. Основная информация о профиле
        text = (
            f"🔎 *ПОЛНЫЙ АНАЛИЗ ИГРОКА `{target_id}`*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Имя: *{first_name}* ({username_str})\n"
            f"├ Статус аккаунта: *{status}*\n"
            f"├ Место в топе: *{rank}*\n"
            f"├ Баланс кошелька: *{user['balance']:,.0f} nCoin*\n"
            f"├ Баланс алмазов NMP: *{user['nmp_balance']:,.0f} NMP*\n"
            f"├ Баланс в Копилке: *{user['savings_balance']:,.0f} nCoin*\n"
            f"├ Сыграно игр: *{user['games_played']}*\n"
            f"├ Проиграно монет: *{user['lost_coins']:,.0f} nCoin*\n"
            f"├ Игровой оборот: *{user['turnover']:,.0f} nCoin*\n"
            f"├ Приглашено рефералов: *{user['ref_count']}*\n"
            f"└ Регистрация в боте: *{user['created_at']}*\n\n"
        )

        # 2. Все игры за последние 72 часа
        games = db.get_user_game_history(target_id, hours=72)
        text += "🕹️ *ИГРЫ ЗА ПОСЛЕДНИЕ 72 ЧАСА:*\n"
        if games:
            for g in games[:15]:
                res_icon = "🟢 +" if g["is_win"] else "🔴 -"
                val = g["win"] if g["is_win"] else g["bet"]
                text += f"• `{g['date']}` | {g['game_name']} | Ставка: {g['bet']:,.0f} | {res_icon}{val:,.0f} nCoin\n"
            if len(games) > 15:
                text += f"_... и еще {len(games) - 15} раундов_\n"
        else:
            text += "_За последние 72 часа игр не найдено._\n"

        text += "\n"

        # 3. Все переводы и транзакции за последние 72 часа
        transfers = db.get_user_transfers_history(target_id, hours=72)
        text += "💸 *ПЕРЕВОДЫ И ОПЕРАЦИИ ЗА 72 ЧАСА:*\n"
        if transfers:
            for t in transfers[:15]:
                amt_str = f" ({t['amount']:,.0f} nCoin)" if t['amount'] > 0 else ""
                text += f"• `{t['date']}` | {t['action']}{amt_str}\n"
            if len(transfers) > 15:
                text += f"_... и еще {len(transfers) - 15} операций_\n"
        else:
            text += "_За последние 72 часа переводов не найдено._\n"

        await message.answer(text, reply_markup=get_admin_kb(), parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Ошибка: ID пользователя должен быть числом!")
    except Exception as e:
        await message.answer(f"❌ Игрок не найден или ошибка в системе: `{str(e)}`", parse_mode="Markdown")
    finally:
        await state.clear()


# --- 8. СОЗДАТЬ ПРОМОКОД ---
@router.callback_query(F.data == "adm_promo")
async def promo_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "🎫 *Введите параметры промокода в формате:*\n"
        "`<#код> <сумма> <активации>`\n\n"
        "Пример: `#10квчате 10000 50` или `#халява 50000 100`",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_promo)

@router.message(StateFilter(AdminStates.waiting_for_promo))
async def process_promo(message: Message, state: FSMContext):
    try:
        parts = message.text.strip().split()
        if len(parts) < 3:
            await message.answer("❌ Ошибка: Введите все параметры согласно шаблону!")
            return
            
        code = parts[0]
        if not code.startswith("#"):
            await message.answer("❌ Промокод должен обязательно начинаться с символа `#`!")
            return
            
        amount_str = parts[1]
        try:
            amount = utils.parse_bet_input(amount_str, 999999999999)
        except TypeError:
            amount = utils.parse_bet_input(amount_str)
            
        activations = int(parts[2])
        
        if amount <= 0 or activations <= 0:
            await message.answer("❌ Значения должны быть больше нуля!")
            return
            
        if db.create_promocode(code, amount, activations):
            await message.answer(
                f"✅ *Промокод успешно создан!* ✅\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎫 Промокод: `{code}`\n"
                f"💰 Сумма: *{amount:,} nCoin*\n"
                f"👥 Количество активаций: *{activations} шт.*",
                parse_mode="Markdown"
            )
        else:
            await message.answer("❌ Промокод с таким названием уже существует!")
    except Exception as e:
        await message.answer(f"❌ Ошибка генерации промокода: `{str(e)}`", parse_mode="Markdown")
    finally:
        await state.clear()


# --- 9. СПИСКИ ИДЕЙ ---
@router.callback_query(F.data == "adm_spisok")
async def adm_spisok_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer()
    ideas = db.get_all_tournament_ideas()
    if not ideas:
        await callback.message.answer("📭 Список идей турнира пуст!", reply_markup=get_admin_kb())
        return
    
    await callback.message.answer(f"📋 *Найдено идей:* `{len(ideas)} шт.`", parse_mode="Markdown")
    for i in ideas:
        username_str = f"@{i[2]}" if i[2] and i[2] != "none" else "нет юзернейма"
        text = (
            f"💡 *Идея ID:* `{i[0]}`\n"
            f"👤 *Автор:* {i[3]} ({username_str}) | ID: `{i[1]}`\n"
            f"📝 *Текст идеи:*\n{i[4]}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🏆 Дать 1кк", callback_data=f"tourn_win:{i[0]}"), 
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"tourn_reject:{i[0]}")
            ]
        ])
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")


# --- 10. ОБЫЧНАЯ РАССЫЛКА💄 ---
@router.callback_query(F.data == "adm_broadcast")
async def broadcast_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer()
    await callback.message.answer(
        "💄 *Подготовка массовой рассылки*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Отправьте сообщение (текст, фото, видео, гифку или пост с кнопками/ссылкой).\n\n"
        "📌 *Поддерживаются все типы форматирования!*",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_broadcast_msg)

@router.message(StateFilter(AdminStates.waiting_for_broadcast_msg))
async def receive_broadcast_msg(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    await state.update_data(
        broadcast_msg_id=message.message_id,
        broadcast_chat_id=message.chat.id
    )

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data="start_broadcast_now"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
        ]
    ])

    await message.answer("👆 *Вот так будет выглядеть ваше сообщение.* Подтвердите запуск рассылки:", parse_mode="Markdown")
    
    await message.bot.copy_message(
        chat_id=message.chat.id,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        reply_markup=confirm_kb
    )
    await state.set_state(AdminStates.confirm_broadcast)

@router.callback_query(F.data == "cancel_broadcast", StateFilter(AdminStates.confirm_broadcast))
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer("❌ *Рассылка отменена!*", reply_markup=get_admin_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "start_broadcast_now", StateFilter(AdminStates.confirm_broadcast))
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return

    await callback.answer()
    data = await state.get_data()
    msg_id = data.get("broadcast_msg_id")
    chat_id = data.get("broadcast_chat_id")
    await state.clear()

    status_msg = await callback.message.answer("🚀 *Рассылка запущена! Пожалуйста, подождите...*", parse_mode="Markdown")

    successful = 0
    failed = 0

    try:
        user_ids = db.get_all_user_ids()

        if not user_ids:
            await status_msg.edit_text("❌ *Ошибка:* В базе данных не найдено ни одного пользователя!", parse_mode="Markdown")
            return

        for user_id in user_ids:
            try:
                await callback.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=chat_id,
                    message_id=msg_id
                )
                successful += 1
                await asyncio.sleep(0.04)
            except Exception as send_err:
                logging.warning(f"Не удалось отправить пользователю {user_id}: {send_err}")
                failed += 1

        total = successful + failed

        report_text = (
            "📊 *Статистика рассылки завершена!*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Успешно отправлено: *{successful}*\n"
            f"❌ Не удалось отправить: *{failed}*\n"
            f"👥 Всего обработано пользователей: *{total}*"
        )

        await status_msg.edit_text(report_text, reply_markup=get_admin_kb(), parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Критическая ошибка рассылки: {e}")
        await status_msg.edit_text(f"❌ *Произошла ошибка при рассылке:*\n`{str(e)}`", reply_markup=get_admin_kb(), parse_mode="Markdown")


# ==============================================================================
# 🌟 11. ПОЭТАПНАЯ РАССЫЛКА ДОНАТОВ (STARS, CRYPTOBOT И ЛС)
# ==============================================================================

@router.callback_query(F.data == "adm_donations")
async def donate_start_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer()
    await state.clear()
    await state.update_data(donate_buttons=[])
    
    text = (
        "🌟 *ПОЭТАПНОЕ СОЗДАНИЕ ДОНАТ-РАССЫЛКИ (Шаг 1/3)*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ *Укажите причину или цель сбора средств:*\n"
        "_(Например: «Проверка», «На сервер» и т.д.)_"
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_donate_reason)


@router.message(StateFilter(AdminStates.waiting_for_donate_reason))
async def process_donate_reason(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
        
    reason_text = message.text.strip()
    await state.update_data(donate_reason=reason_text)
    
    text = (
        "🌟 *ПОЭТАПНОЕ СОЗДАНИЕ ДОНАТ-РАССЫЛКИ (Шаг 2/3)*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💳 *Укажите текстовое описание способов оплаты и реквизиты:*\n"
        "_(Например: `Stars`, `CryptoBot`, `СБП / Т-Банк`)_"
    )
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_donate_requisites)


async def show_donate_button_menu(message: Message, state: FSMContext):
    data = await state.get_data()
    buttons_list = data.get("donate_buttons", [])
    
    text = (
        "🌟 *ПОЭТАПНОЕ СОЗДАНИЕ ДОНАТ-РАССЫЛКИ (Шаг 3/3)*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔘 *Интерактивные инлайн-кнопки оплаты:*\n"
    )
    
    if buttons_list:
        for idx, btn in enumerate(buttons_list, 1):
            text += f"{idx}. `{btn['text']}` ➔ [Ссылка]({btn['url']})\n"
    else:
        text += "_Кнопки еще не добавлены_\n"
        
    text += "\n👇 *Выберите способ оплаты для добавления:* "
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ Сгенерировать Telegram Stars", callback_data="add_stars_btn")
        ],
        [
            InlineKeyboardButton(text="💎 Добавить CryptoBot / @send", callback_data="add_crypto_btn")
        ],
        [
            InlineKeyboardButton(text="👤 Указать свой аккаунт (ЛС)", callback_data="add_pm_btn")
        ],
        [
            InlineKeyboardButton(text="🔗 Добавить свою ссылку / Чек", callback_data="add_custom_btn")
        ],
        [
            InlineKeyboardButton(text="👁 Перейти к Предпросмотру", callback_data="go_to_donate_preview")
        ]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.message(StateFilter(AdminStates.waiting_for_donate_requisites))
async def process_donate_requisites(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
        
    requisites_text = message.text.strip()
    await state.update_data(donate_requisites=requisites_text)
    await show_donate_button_menu(message, state)


@router.callback_query(F.data == "add_stars_btn")
async def add_stars_btn_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "⭐ *ГЕНЕРАЦИЯ СЧЁТА TELEGRAM STARS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ *Введите количество Stars (Звёзд) для оплаты:*\n"
        "_(Например: `1`, `10`, `50` или `100`)_",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_donate_stars_amount)


@router.message(StateFilter(AdminStates.waiting_for_donate_stars_amount))
async def process_stars_amount(message: Message, state: FSMContext, bot: Bot):
    try:
        stars_amt = int(message.text.strip())
        if stars_amt <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число звёзд больше 0!")
        return

    try:
        stars_invoice_link = await bot.create_invoice_link(
            title="⭐ Поддержка проекта",
            description=f"Добровольное пожертвование ({stars_amt} Stars) на развитие проекта",
            payload=f"donate_stars_{stars_amt}_{int(time.time())}",
            currency="XTR",
            prices=[LabeledPrice(label="Telegram Stars", amount=stars_amt)]
        )

        btn_label = f"⭐ Поддержать ({stars_amt} Stars)"

        data = await state.get_data()
        current_btns = data.get("donate_buttons", [])
        current_btns.append({"text": btn_label, "url": stars_invoice_link})
        await state.update_data(donate_buttons=current_btns)

        await message.answer(f"✅ *Счёт на `{stars_amt} Stars` успешно сгенерирован и добавлен!*", parse_mode="Markdown")
        await show_donate_button_menu(message, state)

    except Exception as e:
        logging.error(f"Ошибка генерации Stars инвойса: {e}")
        await message.answer(f"❌ Произошла ошибка генерации счета Stars: `{str(e)}`", parse_mode="Markdown")


@router.callback_query(F.data == "add_crypto_btn")
async def add_crypto_btn_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "💎 *ОПЛАТА ЧЕРЕЗ CRYPTOBOT / @SEND*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ *Отправьте ссылку на ваш чек или счет в CryptoBot / @send:*\n"
        "_(Пример: `https://t.me/send?start=...` или `https://t.me/CryptoBot?start=...`)_",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_donate_crypto_link)


@router.message(StateFilter(AdminStates.waiting_for_donate_crypto_link))
async def process_crypto_link(message: Message, state: FSMContext):
    link = message.text.strip()
    if not (link.startswith("https://t.me/") or link.startswith("tg://")):
        await message.answer("❌ Введите корректную ссылку Telegram на чек/счет!")
        return

    data = await state.get_data()
    current_btns = data.get("donate_buttons", [])
    current_btns.append({"text": "💎 Оплатить через CryptoBot", "url": link})
    await state.update_data(donate_buttons=current_btns)

    await message.answer("✅ *Ссылка на CryptoBot успешно добавлена!*", parse_mode="Markdown")
    await show_donate_button_menu(message, state)


@router.callback_query(F.data == "add_pm_btn")
async def add_pm_btn_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "👤 *ПЕРЕХОД В ЛС ДЛЯ ОПЛАТЫ*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ *Введите юзернейм своего аккаунта или бота:*\n"
        "_(Пример: `@admin_username` или `@nmproda`)_",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_donate_pm_link)


@router.message(StateFilter(AdminStates.waiting_for_donate_pm_link))
async def process_pm_link(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    pm_url = f"https://t.me/{username}?start=donate"

    data = await state.get_data()
    current_btns = data.get("donate_buttons", [])
    current_btns.append({"text": "💬 Поддержать в ЛС", "url": pm_url})
    await state.update_data(donate_buttons=current_btns)

    await message.answer(f"✅ *Ссылка на ЛС `t.me/{username}` добавлена!*", parse_mode="Markdown")
    await show_donate_button_menu(message, state)


@router.callback_query(F.data == "add_custom_btn")
async def add_custom_btn_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "🔗 *ДОБАВЛЕНИЕ СВОЕЙ ССЫЛКИ / ЧЕКА*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✍️ *Отправьте название и ссылку в формате:*\n"
        "`<Текст кнопки> | <Ссылка>`\n\n"
        "Пример: `💳 Оплата картой | https://tbank.ru/...`",
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_donate_custom_btn)


@router.message(StateFilter(AdminStates.waiting_for_donate_custom_btn))
async def process_custom_btn(message: Message, state: FSMContext):
    if "|" not in message.text:
        await message.answer("❌ Ошибка шаблона! Введите через разделитель `|` (Например: `Оплатить | https://...`)!")
        return

    parts = message.text.split("|", 1)
    btn_text = parts[0].strip()
    btn_url = parts[1].strip()

    if not btn_url.startswith(("http://", "https://", "tg://")):
        await message.answer("❌ Ссылка должна начинаться с `https://`, `http://` или `tg://`!")
        return

    data = await state.get_data()
    current_btns = data.get("donate_buttons", [])
    current_btns.append({"text": btn_text, "url": btn_url})
    await state.update_data(donate_buttons=current_btns)

    await message.answer(f"✅ *Кнопка `{btn_text}` успешно добавлена!*", parse_mode="Markdown")
    await show_donate_button_menu(message, state)


@router.callback_query(F.data == "go_to_donate_preview")
async def go_to_donate_preview_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    
    reason_text = data.get("donate_reason", "Проверка")
    requisites_text = data.get("donate_requisites", "Stars")
    buttons_list = data.get("donate_buttons", [])

    full_donate_post = (
        "🌟 *ПОДДЕРЖКА ПРОЕКТА / ДОНАТЫ* 🌟\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Цель сбора:* {reason_text}\n\n"
        "💳 *АКТУАЛЬНЫЕ СПОСОБЫ ОПЛАТЫ И РЕКВИЗИТЫ:*\n"
        f"{requisites_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ *ВАЖНАЯ ИНФОРМАЦИЯ ДЛЯ ИГРОКОВ:*\n"
        "_Все переводы являются исключительно добровольным пожертвованием (donations) любой суммой на поддержку и развитие нашего проекта. Пожертвования не подлежат возврату, возмещению или обмену на игровые ценности и баланс._"
    )

    inline_kb_rows = []
    for btn in buttons_list:
        inline_kb_rows.append([InlineKeyboardButton(text=btn['text'], url=btn['url'])])

    inline_kb_rows.append([
        InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data="start_donate_broadcast_now"),
        InlineKeyboardButton(text="✏️ Изменить", callback_data="restart_donate_setup")
    ])
    inline_kb_rows.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_donate_broadcast")
    ])

    donate_markup = InlineKeyboardMarkup(inline_keyboard=inline_kb_rows)

    await callback.message.answer("👁 *ПРЕДПРОСМОТР ПОСТА ДЛЯ ИГРОКОВ:*", parse_mode="Markdown")
    await callback.message.answer(full_donate_post, reply_markup=donate_markup, parse_mode="Markdown")
    await state.set_state(AdminStates.confirm_donate_broadcast)


@router.callback_query(F.data == "restart_donate_setup", StateFilter(AdminStates.confirm_donate_broadcast))
async def restart_donate_setup_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await donate_start_callback(callback, state)


@router.callback_query(F.data == "cancel_donate_broadcast")
async def cancel_donate_broadcast_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer("❌ *Донат-рассылка отменена!*", reply_markup=get_admin_kb(), parse_mode="Markdown")


@router.callback_query(F.data == "start_donate_broadcast_now", StateFilter(AdminStates.confirm_donate_broadcast))
async def start_donate_broadcast_now_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        return

    await callback.answer()
    data = await state.get_data()
    
    reason_text = data.get("donate_reason", "Проверка")
    requisites_text = data.get("donate_requisites", "Stars")
    buttons_list = data.get("donate_buttons", [])
    await state.clear()

    full_post = (
        "🌟 *ПОДДЕРЖКА ПРОЕКТА / ДОНАТЫ* 🌟\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 *Цель сбора:* {reason_text}\n\n"
        "💳 *АКТУАЛЬНЫЕ СПОСОБЫ ОПЛАТЫ И РЕКВИЗИТЫ:*\n"
        f"{requisites_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ *ВАЖНАЯ ИНФОРМАЦИЯ ДЛЯ ИГРОКОВ:*\n"
        "_Все переводы являются исключительно добровольным пожертвованием (donations) любой суммой на поддержку и развитие нашего проекта. Пожертвования не подлежат возврату, возмещению или обмену на игровые ценности и баланс._"
    )

    user_kb_rows = []
    for btn in buttons_list:
        user_kb_rows.append([InlineKeyboardButton(text=btn['text'], url=btn['url'])])
    
    donate_user_markup = InlineKeyboardMarkup(inline_keyboard=user_kb_rows) if user_kb_rows else None

    status_msg = await callback.message.answer("🚀 *Рассылка донатов запущена! Выполняется отправка...*", parse_mode="Markdown")

    start_time = time.time()
    successful = 0
    failed = 0

    try:
        user_ids = db.get_all_user_ids()

        if not user_ids:
            await status_msg.edit_text("❌ *Ошибка:* В базе данных не найдено пользователей!", parse_mode="Markdown")
            return

        for user_id in user_ids:
            try:
                await bot.send_message(user_id, full_post, reply_markup=donate_user_markup, parse_mode="Markdown")
                successful += 1
                await asyncio.sleep(0.04)
            except Exception as send_err:
                logging.warning(f"Не удалось отправить пользователю {user_id}: {send_err}")
                failed += 1

        elapsed_time = round(time.time() - start_time, 2)
        total = successful + failed

        report_text = (
            "📊 *ОТЧЁТ О РАССЫЛКЕ ДОНАТОВ* 📊\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Всего пользователей в БД: *{total}*\n"
            f"✅ Успешно доставлено: *{successful}*\n"
            f"🔴 Ошибка / Бот заблокирован: *{failed}*\n"
            f"⏱ Затраченное время: *{elapsed_time} сек.*"
        )

        await status_msg.edit_text(report_text, reply_markup=get_admin_kb(), parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Критическая ошибка донат-рассылки: {e}")
        await status_msg.edit_text(f"❌ *Произошла ошибка при рассылке:*\n`{str(e)}`", reply_markup=get_admin_kb(), parse_mode="Markdown")


# ==============================================================================
# 💳 ОБРАБОТЧИКИ ОПЛАТЫ TELEGRAM STARS
# ==============================================================================

@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment, F.successful_payment.invoice_payload.startswith("donate_stars_"))
async def process_successful_payment(message: Message):
    stars_amount = message.successful_payment.total_amount
    await message.answer(
        f"🎉 *ОГРОМНОЕ СПАСИБО ЗА ПОДДЕРЖКУ!* 🎉\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Ваш добровольный донат в размере *{stars_amount} ⭐ Telegram Stars* успешно получен!\n"
        "Благодаря вашей поддержке наш проект становится лучше с каждым днём. ❤️",
        parse_mode="Markdown"
    )
