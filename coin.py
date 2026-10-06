import asyncio
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import db
import utils

router = Router()
COIN_MULTIPLIER = 1.97

# Иконки для сторон монеты
SIDE_ICONS = {
    "орёл": "🦅 Орёл",
    "решка": "👑 Решка"
}

# Кадры анимации вращения монетки
FLIP_FRAMES = [
    "🪙 [ ◓ ] *Монета взлетает...*",
    "🪙 [ ◑ ] *Крутится в воздухе...*",
    "🪙 [ ◒ ] *Падает на стол...*"
]

async def start_coin_logic(message: Message, bet: int, choice: str):
    """Основная логика броска монетки с текстовой анимацией"""
    user_id = message.from_user.id
    user_data = db.get_user(user_id)

    if user_data['balance'] < bet:
        await message.answer(f"❌ Недостаточно nCoin! Баланс: {user_data['balance']:,} nCoin")
        return

    # Списание ставки
    db.update_balance(user_id, -bet)

    # 1. Отправляем начальное сообщение
    status_msg = await message.answer("🪙 *Бросаем монетку...*", parse_mode="Markdown")

    # 2. Анимация вращения монеты (смена кадров в одном сообщении)
    for frame in FLIP_FRAMES:
        await asyncio.sleep(0.35)
        try:
            await status_msg.edit_text(frame, parse_mode="Markdown")
        except Exception:
            pass

    await asyncio.sleep(0.3)

    # 3. Вычисление случайного результата (50/50)
    rolled_outcome = random.choice(["орёл", "решка"])
    win = (choice == rolled_outcome)

    outcome_icon = SIDE_ICONS[rolled_outcome]
    choice_icon = SIDE_ICONS[choice]

    if win:
        win_amount = round(bet * COIN_MULTIPLIER, 2)
        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)
        
        text = (
            f"🎉 *МОНЕТКА · ПОБЕДА!* ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡️ Выпало: *{outcome_icon}*\n"
            f"🎯 Твой выбор: *{choice_icon}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 Ставка: `{bet:,}` n¢\n"
            f"💰 Выигрыш (*x{COIN_MULTIPLIER}*): `+{win_amount:,}` n¢\n\n"
            f"💵 Баланс: *{db.get_user(user_id)['balance']:,}* nCoin"
        )
    else:
        db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
        
        text = (
            f"💥 *МОНЕТКА · ПРОИГРЫШ!* ❌\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡️ Выпало: *{outcome_icon}*\n"
            f"🎯 Твой выбор: *{choice_icon}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 Потеряно: `{bet:,}` n¢\n\n"
            f"💵 Баланс: *{db.get_user(user_id)['balance']:,}* nCoin"
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Играть снова", callback_data="coin_menu")]
    ])
    
    # 4. Обновляем сообщение с выигрышем/проигрышем
    await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(F.text.lower().startswith("монетка"))
async def coin_text_cmd(message: Message, state: FSMContext):
    await state.clear()
    parts = message.text.lower().split()
    
    if len(parts) != 3:
        await message.answer(
            "❌ *Неверный формат!*\n\n"
            "Используй: `монетка <ставка> <орёл/решка>`\n"
            "Например: `монетка 100 орёл` или `монетка 2кк решка`",
            parse_mode="Markdown"
        )
        return

    bet_str, choice = parts[1], parts[2].replace("орел", "орёл")
    
    if choice not in ["орёл", "решка"]:
        await message.answer("❌ Выбери сторону: *орёл* или *решка*!", parse_mode="Markdown")
        return
        
    bet = utils.parse_bet_input(bet_str)
    if bet <= 0:
        await message.answer("❌ Ставка должна быть больше 0!")
        return

    await start_coin_logic(message, bet, choice)

@router.callback_query(F.data == "coin_menu")
async def coin_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user_data = db.get_user(user_id)
    
    text = (
        "🪙 *ИГРА «МОНЕТКА» (Coin Flip)* 🪙\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Испытай удачу! Угадай сторону монеты и забери куш с множителем *x1.97*!\n\n"
        f"💵 Твой баланс: *{user_data['balance']:,} nCoin*\n\n"
        "✍️ *Быстрый запуск из чата:*\n"
        "`монетка <ставка> <орёл/решка>`\n"
        "Пример: `монетка 50к орёл`"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="games_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
