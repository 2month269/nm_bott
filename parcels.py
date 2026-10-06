# parcels.py
import logging
import uuid
import time
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import db
import utils

router = Router()
logger = logging.getLogger(__name__)

class ParcelState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_activations = State()
    waiting_for_password = State()
    waiting_for_description = State()
    waiting_for_target = State()
    waiting_for_claim_password = State()

def get_parcel_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 Отправить посылку", callback_data="parcel_create"),
            InlineKeyboardButton(text="🗄️ Мои посылки", callback_data="parcel_my")
        ],
        [InlineKeyboardButton(text="❌ Сбросить", callback_data="force_cancel_state")]
    ])

@router.message(F.text.lower().in_(["посылка", "посылки", "/parcel", "/parcels"]))
async def show_parcels_menu(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    db.get_user(user_id)
    
    text = (
        "📦 *СЛУЖБА СЕКРЕТНЫХ ПОСЫЛОК* 📦\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Здесь вы можете упаковать nCoin в секретную посылку и отправить её игроку или в общий чат!\n\n"
        "ℹ️ *Особенности посылок:*\n"
        "├ Можно установить 🔑 *пароль* для вскрытия\n"
        "├ Можно отправить конкретному игроку по его 🆔 ID\n"
        "└ Комиссия за упаковку посылки составляет *10%*\n\n"
        "Выберите действие на кнопках ниже 👇"
    )
    await message.answer(text, reply_markup=get_parcel_main_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "parcel_create")
async def start_parcel_creation(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    
    await state.set_state(ParcelState.waiting_for_amount)
    await callback.message.edit_text(
        "📦 *Шаг 1: Сумма посылки*\n"
        "Введите сумму nCoin, которую вы хотите положить в посылку:\n"
        f"(Минимум: 100 nCoin, Твой баланс: *{user['balance']:,} nCoin*)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="force_cancel_state")]]),
        parse_mode="Markdown"
    )

@router.message(ParcelState.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    try:
        amount = utils.parse_bet_input(message.text.strip(), user["balance"])
    except Exception:
        await message.reply("❌ Введите число (например, `50к` или `10000`):")
        return
        
    if amount < 100:
        await message.reply("❌ Минимальная сумма посылки — *100 nCoin*!")
        return
        
    total_cost = amount * 1.10
    if user["balance"] < total_cost:
        await message.reply(f"❌ Недостаточно средств! Требуется с комиссией: *{total_cost:,} nCoin*")
        return
        
    await state.update_data(amount=amount, total_cost=total_cost)
    await state.set_state(ParcelState.waiting_for_activations)
    
    await message.reply("📦 *Шаг 2: Количество получателей*\nНа сколько человек разделить эту посылку? (от 1 до 100):")

@router.message(ParcelState.waiting_for_activations)
async def process_activations(message: Message, state: FSMContext):
    try:
        activations = int(message.text.strip())
    except ValueError:
        await message.reply("❌ Введите корректное число:")
        return
        
    if activations < 1 or activations > 100:
        await message.reply("❌ Количество получателей должно быть от 1 до 100!")
        return
        
    await state.update_data(activations=activations)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Установить пароль", callback_data="parcel_set_pass_yes")],
        [InlineKeyboardButton(text="🔓 Без пароля", callback_data="parcel_set_pass_no")]
    ])
    await message.reply("📦 *Шаг 3: Безопасность*\nХотите защитить посылку паролем?", reply_markup=kb)

@router.callback_query(F.data == "parcel_set_pass_yes")
async def ask_password(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ParcelState.waiting_for_password)
    await callback.message.edit_text("🔑 Введите пароль для посылки:")

@router.callback_query(F.data == "parcel_set_pass_no")
async def skip_password(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(password=None)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Указать ID получателя", callback_data="parcel_set_target_yes")],
        [InlineKeyboardButton(text="🌍 Для всех", callback_data="parcel_set_target_no")]
    ])
    await callback.message.edit_text("📦 *Шаг 4: Адресат*\nЭта посылка для конкретного человека?", reply_markup=kb)

@router.message(ParcelState.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    password = message.text.strip()
    await state.update_data(password=password)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Указать ID получателя", callback_data="parcel_set_target_yes")],
        [InlineKeyboardButton(text="🌍 Для всех", callback_data="parcel_set_target_no")]
    ])
    await message.reply("📦 *Шаг 4: Адресат*\nЭта посылка для конкретного человека?", reply_markup=kb)

@router.callback_query(F.data == "parcel_set_target_yes")
async def ask_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ParcelState.waiting_for_target)
    await callback.message.edit_text("👤 Введите Telegram ID получателя посылки:")

@router.callback_query(F.data == "parcel_set_target_no")
async def skip_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(target_user_id=None)
    await state.set_state(ParcelState.waiting_for_description)
    await callback.message.edit_text("📝 Добавьте записку к посылке (или отправьте `-` для пропуска):")

@router.message(ParcelState.waiting_for_target)
async def process_target(message: Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.reply("❌ Введите корректный числовой ID:")
        return
        
    await state.update_data(target_user_id=target_id)
    await state.set_state(ParcelState.waiting_for_description)
    await message.reply("📝 Добавьте записку к посылке (или отправьте `-` для пропуска):")

@router.message(ParcelState.waiting_for_description)
async def process_description_and_finish(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    desc_raw = message.text.strip()
    desc = None if desc_raw in ["-", "—", "нет"] else desc_raw
        
    data = await state.get_data()
    await state.clear()
    
    amount = data.get("amount")
    total_cost = data.get("total_cost")
    activations = data.get("activations")
    password = data.get("password")
    target_user_id = data.get("target_user_id")
    
    user = db.get_user(user_id)
    if not user or user["balance"] < total_cost:
        await message.reply("❌ Ошибка: недостаточно средств.")
        return
        
    db.update_balance(user_id, -total_cost)
    parcel_id = str(uuid.uuid4())[:8].upper()
    
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO parcels (parcel_id, creator_id, total_amount, activations_total, activations_left, password, description, target_user_id, notifications, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (parcel_id, user_id, amount, activations, activations, password, desc, target_user_id, True, int(time.time()))
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error creating parcel: {e}")
        conn.rollback()
        db.update_balance(user_id, total_cost)
        await message.reply("❌ Ошибка записи посылки в базу. Средства возвращены на баланс!")
        return
    finally:
        cursor.close()
        conn.close()
        
    bot_info = await bot.get_me()
    parcel_link = f"https://t.me/{bot_info.username}?start=p_{parcel_id}"
    
    text = (
        f"📦 *СЕКРЕТНАЯ ПОСЫЛКА #{parcel_id} СОЗДАНА!* 📦\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 *Ссылка для получения:*\n`{parcel_link}`\n\n"
        f"💰 Содержимое: *{amount:,} nCoin*\n"
        f"👥 Кол-во получателей: *{activations}*\n"
        f"🔑 Пароль: *{'Да' if password else 'Нет'}*\n"
        f"📝 Записка: _{desc if desc else 'Отсутствует'}_"
    )
    
    await message.reply(text, parse_mode="Markdown")

@router.message(ParcelState.waiting_for_claim_password)
async def process_parcel_password_claim(message: Message, state: FSMContext, bot: Bot):
    try:
        user_id = message.from_user.id
        user_data = await state.get_data()
        parcel_id = user_data.get("claim_parcel_id")
        
        if not parcel_id:
            await state.clear()
            await message.reply("❌ Сессия истекла.")
            return
            
        entered_password = message.text.strip()
        parcel = db.get_parcel(parcel_id)
        
        if not parcel:
            await state.clear()
            await message.reply("❌ Посылка не найдена.")
            return
            
        if parcel["password"] != entered_password:
            await message.reply("🔑 *Неверный пароль!* Попробуйте снова:", parse_mode="Markdown")
            return
            
        await state.clear()
        success = db.register_parcel_claim(parcel_id, user_id)
        if not success:
            await message.reply("❌ Вы уже забирали эту посылку ранее!")
            return
            
        reward = round(parcel["total_amount"] / parcel["activations_total"], 2)
        db.update_balance(user_id, reward)
        
        await message.reply(f"🎉 Вы успешно вскрыли посылку и получили: *+{reward:,} nCoin*!", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error claim parcel: {e}")
        await state.clear()
