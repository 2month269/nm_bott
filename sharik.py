import random
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import db
import utils

router = Router()

class SharikStates(StatesGroup):
    waiting_for_bet = State()
    waiting_for_choice = State()


def get_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔴 Будет шарик", callback_data="sh_choice:yes"),
            InlineKeyboardButton(text="⚪️ Не будет шарика", callback_data="sh_choice:no")
        ],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="sh_cancel")]
    ])


# --- 1. ЕДИНЫЙ ОБРАБОТЧИК ТЕКСТОВЫХ ЗАПРОСОВ ---

@router.message(lambda msg: msg.text and msg.text.lower().strip().startswith("шарик"))
async def handle_sharik_text_commands(message: Message, state: FSMContext):
    try:
        text = message.text.strip()
        parts = text.split()
        
        # Сценарий А: Просто "шарик" (Пошаговый режим)
        if len(parts) == 1:
            await state.clear()
            user = db.get_user(message.from_user.id)
            
            info_text = (
                "🔮 *Мини-игра «ШАРИК»* 🔮\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Правила очень просты:\n"
                "Бот прячет (или не прячет) шарик под стакан.\n"
                "Угадайте, окажется ли шарик на месте!\n\n"
                "📈 *Коэффициент выигрыша:* `x2.027` (+2.7% бонуса сверху!)\n\n"
                f"💳 Твой баланс: *{user['balance']:,} nCoin*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "✍️ *Введите вашу ставку для начала игры:* \n"
                "_(Пример: 10к, 50000, все)_"
            )
            await message.answer(info_text, parse_mode="Markdown")
            await state.set_state(SharikStates.waiting_for_bet)
            return

        # Сценарий Б: Быстрая игра ("шарик 10к будет")
        await state.clear()
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        if len(parts) < 3:
            await message.answer("❌ Неверный формат! Используйте:\n`шарик <ставка> будет` или `шарик <ставка> не будет`")
            return
            
        bet_str = parts[1]
        
        try:
            bet = utils.parse_bet_input(bet_str, user["balance"])
        except TypeError:
            bet = utils.parse_bet_input(bet_str)
            
        if bet <= 0:
            await message.answer("❌ Ставка должна быть больше 0!")
            return
            
        if user["balance"] < bet:
            await message.answer(f"❌ Недостаточно nCoin! Ваш баланс: *{user['balance']:,} nCoin*")
            return
            
        choice_str = "".join(parts[2:]).lower().replace(" ", "")
        if choice_str in ["будет", "да", "yes"]:
            user_choice = True
        elif choice_str in ["небудет", "не", "нет", "no"]:
            user_choice = False
        else:
            await message.answer("❌ Выберите исход! В конце команды напишите `будет` или `не будет`.")
            return
            
        db.update_balance(user_id, -bet)
        has_ball = random.choice([True, False])
        
        if user_choice == has_ball:
            # Угадал!
            win_amount = round(bet * 2.027, 2)
            db.update_balance(user_id, win_amount)
            db.add_stats(user_id, is_lost=False, bet_amount=bet)
            
            ball_status = "🔴 Ого, шарик под стаканом!" if has_ball else "💨 Под стаканом пусто!"
            result_text = (
                f"✨ *Победа! Вы угадали!* ✨\n\n"
                f"🔮 Результат: {ball_status}\n\n"
                f"🎉 Выигрыш: *+{win_amount:,} nCoin* (x2.027)\n"
                f"💳 Баланс: *{db.get_user(user_id)['balance']:,} nCoin*"
            )
        else:
            # Не угадал
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
            ball_status = "🔴 Ого, под стаканом был шарик!" if has_ball else "💨 Под стаканом ничего нет!"
            result_text = (
                f"💥 *Увы, мимо! Вы проиграли!* 💥\n\n"
                f"🔮 Результат: {ball_status}\n\n"
                f"💸 Потеряно: *-{bet:,} nCoin*\n"
                f"💳 Баланс: *{db.get_user(user_id)['balance']:,} nCoin*"
            )
            
        await message.answer(result_text, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Error in unified sharik handler: {e}", exc_info=True)
        await message.answer(f"❌ Произошла внутренняя ошибка в коде Шарика: `{str(e)}`")


# --- 2. ПОЛУЧЕНИЕ СТАВКИ В ПОШАГОВОМ РЕЖИМЕ ---

@router.message(SharikStates.waiting_for_bet)
async def sharik_bet_received(message: Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        try:
            bet = utils.parse_bet_input(message.text, user["balance"])
        except TypeError:
            bet = utils.parse_bet_input(message.text)
            
        if bet <= 0:
            await message.answer("❌ Ставка должна быть больше 0!")
            return
            
        if user["balance"] < bet:
            await message.answer(f"❌ Недостаточно nCoin! Твой баланс: *{user['balance']:,} nCoin*")
            return
            
        await state.update_data(sharik_bet=bet)
        await state.set_state(SharikStates.waiting_for_choice)
        
        text = (
            f"💰 Ставка принята: *{bet:,} nCoin*\n"
            "Будет ли под стаканом шарик? Сделайте ваш выбор: 👇"
        )
        await message.answer(text, reply_markup=get_choice_kb(), parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Ошибка приема пошаговой ставки: `{str(e)}`")


# --- 3. ОБРАБОТКА ВЫБОРА ИГРОКА (ИНЛАЙН КНОПКИ) ---

@router.callback_query(SharikStates.waiting_for_choice, F.data.startswith("sh_choice:"))
async def sharik_choice_click(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.answer()
        data = await state.get_data()
        bet = data.get("sharik_bet")
        await state.clear()
        
        if not bet:
            await callback.message.edit_text("❌ Сессия игры устарела. Запустите заново, написав слово `шарик`.")
            return
            
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        
        if user["balance"] < bet:
            await callback.message.edit_text("❌ За время выбора ваш баланс изменился! Игра отменена.")
            return
            
        has_ball = random.choice([True, False])
        user_choice = callback.data.split(":")[1] == "yes"
        
        db.update_balance(user_id, -bet)
        
        if user_choice == has_ball:
            win_amount = round(bet * 2.027, 2)
            db.update_balance(user_id, win_amount)
            db.add_stats(user_id, is_lost=False, bet_amount=bet)
            
            ball_status = "🔴 Ого, шарик под стаканом!" if has_ball else "💨 Под стаканом пусто!"
            text = (
                f"✨ *Победа! Вы угадали!* ✨\n\n"
                f"🔮 Результат: {ball_status}\n\n"
                f"🎉 Выигрыш: *+{win_amount:,} nCoin* (x2.027)\n"
                f"💳 Баланс: *{db.get_user(user_id)['balance']:,} nCoin*"
            )
        else:
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
            ball_status = "🔴 Ого, под стаканом был шарик!" if has_ball else "💨 Под стаканом ничего нет!"
            text = (
                f"💥 *Увы, мимо! Вы проиграли!* 💥\n\n"
                f"🔮 Результат: {ball_status}\n\n"
                f"💸 Потеряно: *-{bet:,} nCoin*\n"
                f"💳 Баланс: *{db.get_user(user_id)['balance']:,} nCoin*"
            )
            
        await callback.message.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка обработки выбора игры: `{str(e)}`")


# --- ОТМЕНА ИГРЫ ---

@router.callback_query(F.data == "sh_cancel")
async def sharik_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Игра отменена.")
    await state.clear()
    await callback.message.edit_text("🔮 Игра в шарик отменена.")
