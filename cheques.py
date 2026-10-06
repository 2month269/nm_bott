# cheques.py
import logging
import uuid
import math
from urllib.parse import quote
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import db
import utils

router = Router()
logger = logging.getLogger(__name__)

CHEQUES_PER_PAGE = 5

class ChequeState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_activations = State()
    waiting_for_password = State()
    waiting_for_description = State()
    waiting_for_target = State()
    waiting_for_claim_password = State()


def cheque_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ 🧾 Создать чек", callback_data="cheque_create")],
        [InlineKeyboardButton(text="📂 💳 Мои созданные чеки", callback_data="cheque_my_page:1")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="force_cancel_state")]
    ])

def cancel_creation_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить создание", callback_data="cheque_cancel")]
    ])


@router.message(F.text.lower().in_(["чеки", "чек", "/cheques"]))
async def show_cheques_menu(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "🧾 <b>ЦЕНТР УПРАВЛЕНИЯ ЧЕКАМИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 <i>Создавайте денежные чеки и дарите nCoin друзьям или подписчикам в каналах!</i>\n\n"
        "👇 <b>Выберите желаемое действие в меню ниже:</b>"
    )
    await message.answer(text, reply_markup=cheque_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "cheque_cancel")
async def cancel_cheque_creation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Создание чека отменено")
    text = (
        "🧾 <b>ЦЕНТР УПРАВЛЕНИЯ ЧЕКАМИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "❌ <i>Создание чека отменено.</i>\n\n"
        "👇 <b>Выберите действие:</b>"
    )
    await callback.message.edit_text(text, reply_markup=cheque_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "cheque_create")
async def start_create_cheque(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    await state.set_state(ChequeState.waiting_for_amount)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10к n¢", callback_data="cheque_preset_amount:10k"),
            InlineKeyboardButton(text="100к n¢", callback_data="cheque_preset_amount:100k"),
            InlineKeyboardButton(text="1кк n¢", callback_data="cheque_preset_amount:1kk")
        ],
        [
            InlineKeyboardButton(text="10кк n¢", callback_data="cheque_preset_amount:10kk"),
            InlineKeyboardButton(text="ALL-IN 🔥", callback_data="cheque_preset_amount:allin")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cheque_cancel")]
    ])

    text = (
        "🧾 <b>СОЗДАНИЕ ЧЕКА — ШАГ 1/4</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💵 <b>Введите сумму чека:</b>\n"
        f"💳 Ваш баланс: <code>{user['balance']:,.0f} nCoin</code>\n\n"
        "👇 <i>Нажмите на кнопку с быстрой ставкой или введите сумму текстом в чат (например: 10к, 500k, 2.5kk):</i>"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(ChequeState.waiting_for_amount, F.data.startswith("cheque_preset_amount:"))
async def cheque_amount_preset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    preset = callback.data.split(":")[1]
    user = db.get_user(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    
    try:
        if preset == "allin":
            amount = float(user["balance"])
        else:
            amount = float(utils.parse_bet_input(preset, user["balance"]))
            
        if amount <= 0 or amount > float(user["balance"]):
            await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)
            return

        await state.update_data(amount=amount)
        await state.set_state(ChequeState.waiting_for_activations)
        await ask_activations_step(callback.message, amount, is_edit=True)
    except Exception as e:
        logger.error(f"Ошибка выбора быстрой суммы чека: {e}")
        await callback.answer("❌ Ошибка ввода суммы", show_alert=True)


@router.message(ChequeState.waiting_for_amount)
async def cheque_amount(message: Message, state: FSMContext):
    try:
        user = db.get_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
        amount = float(utils.parse_bet_input(message.text.strip(), user["balance"]))
        if amount <= 0 or amount > float(user["balance"]):
            await message.answer("❌ <b>Некорректная сумма или недостаточно средств на балансе!</b>", parse_mode="HTML", reply_markup=cancel_creation_kb())
            return
        await state.update_data(amount=amount)
        await state.set_state(ChequeState.waiting_for_activations)
        await ask_activations_step(message, amount, is_edit=False)
    except Exception:
        await message.answer("❌ <b>Пожалуйста, введите корректную сумму чека.</b>", parse_mode="HTML", reply_markup=cancel_creation_kb())


async def ask_activations_step(target_msg: Message, amount: float, is_edit: bool = False):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 чел 👤", callback_data="cheque_preset_act:1"),
            InlineKeyboardButton(text="5 чел 👥", callback_data="cheque_preset_act:5"),
            InlineKeyboardButton(text="10 чел 👥", callback_data="cheque_preset_act:10")
        ],
        [
            InlineKeyboardButton(text="25 чел 💥", callback_data="cheque_preset_act:25"),
            InlineKeyboardButton(text="50 чел 🚀", callback_data="cheque_preset_act:50"),
            InlineKeyboardButton(text="100 чел ⚡", callback_data="cheque_preset_act:100")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cheque_cancel")]
    ])
    
    text = (
        "👥 <b>СОЗДАНИЕ ЧЕКА — ШАГ 2/4</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Выбранная сумма: <b>{amount:,.0f} nCoin</b>\n\n"
        "⚡ <b>Укажите число активаций чека (от 1 до 100):</b>\n"
        "👇 <i>Нажмите быструю кнопку или введите число вручную:</i>"
    )
    if is_edit:
        await target_msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target_msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(ChequeState.waiting_for_activations, F.data.startswith("cheque_preset_act:"))
async def cheque_activations_preset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    act_val = int(callback.data.split(":")[1])
    await state.update_data(activations=act_val)
    await state.set_state(ChequeState.waiting_for_password)
    await ask_password_step(callback.message, is_edit=True)


@router.message(ChequeState.waiting_for_activations)
async def cheque_activations(message: Message, state: FSMContext):
    try:
        activations = int(message.text.strip())
        if not 1 <= activations <= 100:
            raise ValueError
        await state.update_data(activations=activations)
        await state.set_state(ChequeState.waiting_for_password)
        await ask_password_step(message, is_edit=False)
    except ValueError:
        await message.answer("❌ <b>Введите целое число от 1 до 100.</b>", parse_mode="HTML", reply_markup=cancel_creation_kb())


async def ask_password_step(target_msg: Message, is_edit: bool = False):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔓 Без пароля", callback_data="cheque_skip_password", style="primary")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cheque_cancel", style="danger")]
    ])
    text = (
        "🔐 <b>СОЗДАНИЕ ЧЕКА — ШАГ 3/4</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🗝️ <b>Введите пароль для чека:</b>\n\n"
        "💡 <i>Если пароль не нужен, нажмите кнопку «🔓 Без пароля» ниже или отправьте символ <code>-</code>:</i>"
    )
    if is_edit:
        await target_msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target_msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(ChequeState.waiting_for_password, F.data == "cheque_skip_password")
async def cheque_skip_password_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(password=None)
    await state.set_state(ChequeState.waiting_for_description)
    await ask_description_step(callback.message, is_edit=True)


@router.message(ChequeState.waiting_for_password)
async def cheque_password(message: Message, state: FSMContext):
    password = message.text.strip()
    await state.update_data(password=None if password == "-" else password)
    await state.set_state(ChequeState.waiting_for_description)
    await ask_description_step(message, is_edit=False)


async def ask_description_step(target_msg: Message, is_edit: bool = False):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Без описания", callback_data="cheque_skip_desc", style="primary")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cheque_cancel", style="danger")]
    ])
    text = (
        "📝 <b>СОЗДАНИЕ ЧЕКА — ШАГ 4/4</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 <b>Введите текстовое описание/пожелание к чеку:</b>\n\n"
        "💡 <i>Если описание не требуется, нажмите кнопку ниже или отправьте символ <code>-</code>:</i>"
    )
    if is_edit:
        await target_msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target_msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(ChequeState.waiting_for_description, F.data == "cheque_skip_desc")
async def cheque_skip_desc_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await finalize_cheque_creation(callback.message, state, description="-", user_obj=callback.from_user, is_callback=True)


@router.message(ChequeState.waiting_for_description)
async def cheque_description(message: Message, state: FSMContext):
    await finalize_cheque_creation(message, state, description=message.text.strip(), user_obj=message.from_user, is_callback=False)


async def finalize_cheque_creation(event_msg: Message, state: FSMContext, description: str, user_obj, is_callback: bool = False):
    data = await state.get_data()
    
    if not data or "amount" not in data or "activations" not in data:
        await state.clear()
        err_msg = "❌ <b>Сессия создания чека истекла. Начните заново из меню /cheques</b>"
        if is_callback:
            await event_msg.edit_text(err_msg, parse_mode="HTML", reply_markup=cheque_menu_kb())
        else:
            await event_msg.answer(err_msg, parse_mode="HTML", reply_markup=cheque_menu_kb())
        return

    await state.clear()

    amount = float(data["amount"])
    activations = int(data["activations"])
    password = data.get("password")
    description = None if description == "-" else description
    
    user_id = user_obj.id
    user = db.get_user(user_id, user_obj.first_name, user_obj.username)

    if float(user["balance"]) < amount:
        text_err = "❌ <b>Недостаточно средств: ваш баланс изменился за время создания.</b>"
        if is_callback:
            await event_msg.edit_text(text_err, parse_mode="HTML")
        else:
            await event_msg.answer(text_err, parse_mode="HTML")
        return

    cheque_id = uuid.uuid4().hex[:10].lower()
    db.update_balance(user_id, -amount)
    success = db.create_cheque_db(
        cheque_id=cheque_id,
        creator_id=user_id,
        total_amount=amount,
        activations_total=activations,
        password=password,
        description=description,
        notifications=True
    )

    if not success:
        db.update_balance(user_id, amount)
        text_fail = "❌ <b>Не удалось создать чек из-за сбоя системы. Средства возвращены на баланс.</b>"
        if is_callback:
            await event_msg.edit_text(text_fail, parse_mode="HTML")
        else:
            await event_msg.answer(text_fail, parse_mode="HTML")
        return

    bot_info = await event_msg.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=c_{cheque_id}"
    share_text = quote(f"🎁 Я создал денежный чек на {amount:,.0f} nCoin! Успей забрать по ссылке:")
    share_url = f"https://t.me/share/url?url={quote(link)}&text={share_text}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Поделиться чеком", url=share_url, style="success")],
        [InlineKeyboardButton(text="📂 Мои чеки", callback_data="cheque_my_page:1", style="primary")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="force_cancel_state", style="danger")]
    ])

    text_success = (
        "🎉 <b>ЧЕК УСПЕШНО СОЗДАН!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID чека: <code>{cheque_id}</code>\n"
        f"💰 Общая сумма: <b>{amount:,.0f} nCoin</b>\n"
        f"👥 Активаций: <b>{activations}</b> (по {amount/activations:,.0f} nCoin)\n"
        f"🔐 Пароль: <b>{'🔐 Да' if password else '🔓 Нет'}</b>\n"
        f"📝 Описание: <i>{description or 'Без описания'}</i>\n\n"
        f"🔗 <b>Прямая ссылка для активации:</b>\n"
        f"<code>{link}</code>"
    )

    if is_callback:
        await event_msg.edit_text(text_success, reply_markup=kb, parse_mode="HTML")
    else:
        await event_msg.answer(text_success, reply_markup=kb, parse_mode="HTML")


# --- ОБРАБОТКА И ПОСТРАНИЧНАЯ НАВИГАЦИЯ СОЗДАННЫХ ЧЕКОВ (ПО 5 НА СТРАНИЦУ) ---

@router.callback_query(F.data.startswith("cheque_my_page:") | (F.data == "cheque_my"))
async def my_cheques(callback: CallbackQuery):
    await callback.answer()
    
    page = 1
    if ":" in callback.data:
        try:
            page = int(callback.data.split(":")[1])
        except ValueError:
            page = 1

    cheques = db.get_user_created_cheques(callback.from_user.id)
    bot_info = await callback.bot.get_me()

    if not cheques:
        text_empty = (
            "📂 <b>МОИ СОЗДАННЫЕ ЧЕКИ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "ℹ️ <i>У вас пока нет активных созданных чеков.</i>"
        )
        await callback.message.edit_text(text_empty, reply_markup=cheque_menu_kb(), parse_mode="HTML")
        return

    total_cheques = len(cheques)
    total_pages = math.ceil(total_cheques / CHEQUES_PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * CHEQUES_PER_PAGE
    end_idx = start_idx + CHEQUES_PER_PAGE
    page_cheques = cheques[start_idx:end_idx]

    text = f"📂 <b>ВАШИ АКТИВНЫЕ ЧЕКИ (Страница {page}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    inline_buttons = []

    for i, c in enumerate(page_cheques, start=start_idx + 1):
        link = f"https://t.me/{bot_info.username}?start=c_{c['cheque_id']}"
        share_text = quote(f"🎁 Чек на {c['total_amount']:,.0f} nCoin!")
        share_url = f"https://t.me/share/url?url={quote(link)}&text={share_text}"

        text += (
            f"<b>{i}. Чек:</b> <code>{c['cheque_id']}</code>\n"
            f"💰 Сумма: <b>{c['total_amount']:,.0f} nCoin</b> | 👥 Осталось: <b>{c['activations_left']}/{c['activations_total']}</b>\n"
            f"🔐 Пароль: <b>{'🔐 Да' if c['has_password'] else '🔓 Нет'}</b>\n"
            f"🔗 <code>{link}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        inline_buttons.append([InlineKeyboardButton(text=f"🚀 Поделиться чеком #{i}", url=share_url, style="success")])

    # Кнопки пагинации
    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cheque_my_page:{page - 1}", style="danger"))
    
    pagination_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="cheque_ignore"))

    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"cheque_my_page:{page + 1}", style="success"))

    if pagination_row:
        inline_buttons.append(pagination_row)

    inline_buttons.append([InlineKeyboardButton(text="✨ Создать новый чек", callback_data="cheque_create", style="success")])
    inline_buttons.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="force_cancel_state", style="danger")])

    kb = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "cheque_ignore")
async def cheque_ignore_cb(callback: CallbackQuery):
    await callback.answer()


@router.message(ChequeState.waiting_for_claim_password)
async def claim_with_password(message: Message, state: FSMContext):
    data = await state.get_data()
    cheque_id = data.get("claim_cheque_id")
    cheque = db.get_cheque(cheque_id) if cheque_id else None
    if not cheque:
        await state.clear()
        await message.answer("❌ <b>Чек не найден или удален.</b>", parse_mode="HTML")
        return
    if cheque["password"] != message.text.strip():
        await message.answer("🔐 <b>Неверный пароль. Попробуйте ещё раз:</b>", parse_mode="HTML")
        return
    await state.clear()
    await claim_cheque(message, cheque)


async def claim_cheque(message: Message, cheque: dict):
    user_id = message.from_user.id
    db.get_user(user_id, message.from_user.first_name, message.from_user.username)
    
    if cheque["creator_id"] == user_id:
        await message.answer("❌ <b>Вы не можете активировать собственный чек!</b>", parse_mode="HTML")
        return
    if cheque["activations_left"] <= 0:
        await message.answer("❌ <b>У этого чека закончились активации!</b>", parse_mode="HTML")
        return
        
    status = db.register_cheque_claim(cheque["cheque_id"], user_id)
    if not status:
        await message.answer("❌ <b>Вы уже активировали этот чек ранее или он уже полностью раздан.</b>", parse_mode="HTML")
        return
        
    reward = round(cheque["total_amount"] / cheque["activations_total"], 2)
    db.update_balance(user_id, reward)
    
    desc_str = f"\n📝 Описание: <i>{cheque['description']}</i>" if cheque.get("description") else ""
    user_data = db.get_user(user_id)

    await message.answer(
        f"🎉 <b>ЧЕК УСПЕШНО АКТИВИРОВАН!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Вам начислено: <b>+{reward:,.2f} nCoin</b>\n"
        f"💳 Ваш баланс: <b>{user_data['balance']:,.2f} nCoin</b>{desc_str}",
        parse_mode="HTML"
    )
    
    if cheque.get("notifications", True):
        try:
            mention = f"@{message.from_user.username}" if message.from_user.username else f"[{message.from_user.first_name}](tg://user?id={user_id})"
            await message.bot.send_message(
                cheque["creator_id"],
                f"🔔 <b>Ваш чек <code>{cheque['cheque_id']}</code> активирован!</b>\n"
                f"👤 Пользователь: {mention}\n"
                f"💸 Активаций осталось: <b>{cheque['activations_left'] - 1}/{cheque['activations_total']}</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    if cheque["activations_left"] - 1 <= 0:
        db.delete_cheque(cheque["cheque_id"])
