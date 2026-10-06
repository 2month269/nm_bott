import random
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import db
import utils

router = Router()
ACTIVE_FROG_GAMES = {}  # {user_id: game_state}
BYPASS_COMMANDS = ["профиль", "баланс", "б", "/start", "/profile", "бонус", "банк", "чеки", "башня", "квак"]

class FrogState(StatesGroup):
    waiting_for_bet = State()

# Коэффициенты по уровням (точно по ТЗ)
FROG_MULTIPLIERS = {
    0: 1.00,
    1: 1.21,
    2: 2.00,
    3: 5.05,
    4: 25.25
}

# Количество опасных кувшинок (водоворотов) на каждом уровне
LEVEL_HAZARDS = {
    1: 1, # 1 водоворот, 4 безопасных кувшинки (x1.21)
    2: 2, # 2 водоворота, 3 безопасных кувшинки (x2.00)
    3: 3, # 3 водоворота, 2 безопасных кувшинки (x5.05)
    4: 4  # 4 водоворота, 1 безопасная кувшинка (x25.25)
}

def generate_frog_level(hazards_count: int) -> list:
    """Генерирует уровень (5 кувшинок). True - водоворот, False - безопасный лист"""
    level = [False] * 5
    hazard_indices = random.sample(range(5), hazards_count)
    for idx in hazard_indices:
        level[idx] = True
    return level

def render_frog_text_board(game: dict) -> str:
    """Генерирует текстовое представление доски с кувшинками"""
    lines = []
    
    # Сверху вниз (от 4 уровня к 0)
    for level_num in reversed(range(5)):
        mult = FROG_MULTIPLIERS[level_num]
        
        if level_num == 0:
            # Стартовая линия (всегда статична)
            if game["current_level"] == 0:
                line = "⬛ | ⬛ | 🐸 | ⬛ | ⬛ |"
            else:
                line = "⬛ | ⬛ | 🍀 | ⬛ | ⬛ |"
        else:
            level_data = game["board"][level_num]
            columns = []
            
            for col_idx in range(5):
                is_hazard = level_data["cells"][col_idx]
                
                if level_num < game["current_level"]:
                    # Пройденные уровни
                    if level_data["opened_cell"] == col_idx:
                        columns.append("🍀" if not is_hazard else "🌀")
                    else:
                        columns.append("🍀")
                elif level_num == game["current_level"]:
                    # Текущее положение лягушки
                    if game["status"] == "lost" and is_hazard:
                        columns.append("🌀")
                    elif level_data["opened_cell"] == col_idx:
                        columns.append("🐸")
                    else:
                        columns.append("🍀")
                else:
                    # Уровни выше (еще не пройденные)
                    if game["status"] == "lost":
                        columns.append("🌀" if is_hazard else "🍀")
                    else:
                        columns.append("🍀")
                        
            # Если игрок проиграл на этом уровне, подменяем нажатую кнопку на всплеск 🔵
            if game["status"] == "lost" and level_num == game["failed_level"]:
                columns[level_data["opened_cell"]] = "🔵"
                
            line = " | ".join(columns) + " |"
            
        lines.append(f"{line} ({mult:.2f}x)")
        
    return "\n".join(lines)

def get_frog_keyboard(game: dict) -> InlineKeyboardMarkup:
    """Клавиатура управления прыжком"""
    keyboard = []
    
    if game["status"] == "playing":
        # 5 кувшинок для прыжка
        jump_buttons = []
        for idx in range(5):
            jump_buttons.append(InlineKeyboardButton(text="🍀", callback_data=f"frog_jump:{idx}"))
        keyboard.append(jump_buttons)
        
        # Кнопка Забрать выигрыш
        if game["current_level"] > 0:
            cashout_win = round(game["bet"] * game["current_multiplier"], 2)
            keyboard.append([InlineKeyboardButton(text=f"Забрать награду ✅", callback_data="frog_cashout")])
    else:
        keyboard.append([InlineKeyboardButton(text="🔄 Играть снова", callback_data="frog_menu")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.callback_query(F.data == "frog_menu")
async def frog_setup_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user_data = db.get_user(user_id)
    
    text = (
        "🐸 *Квак (Frog Jump)* 🐸\n\n"
        "Помоги лягушке перепрыгнуть болото по кувшинкам `🍀`. "
        "Каждый уровень содержит скрытые водовороты `🌀`. Доберись до вершины и получи выплату *x25.25*!\n\n"
        f"💵 Твой баланс: *{user_data['balance']:,} nCoin*\n\n"
        "✍️ *Чтобы сыграть, отправь команду в чат:*\n"
        "`квак <ставка>`\n"
        "Например: `квак 100` или `квак 10к`"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="games_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(FrogState.waiting_for_bet)

@router.message(F.text.lower().startswith("квак"))
async def frog_text_cmd(message: Message, state: FSMContext):
    await state.clear()
    parts = message.text.lower().split()
    
    if len(parts) != 2:
        await message.answer("❌ Используй: `квак <ставка>` (например: `квак 500`)", parse_mode="Markdown")
        return
        
    bet = utils.parse_bet_input(parts[1])
    if bet <= 0:
        await message.answer("❌ Неверный формат ставки!")
        return
        
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    if user_data['balance'] < bet:
        await message.answer(f"❌ Недостаточно nCoin! Баланс: {user_data['balance']:,} nCoin")
        return
        
    await start_frog_game_logic(message, bet)

async def start_frog_game_logic(message: Message, bet: int):
    user_id = message.from_user.id
    db.update_balance(user_id, -bet) # Списание ставки
    
    # Генерация поля кувшинок (4 игровых уровня)
    game_board = {0: {"cells": [False]*5, "opened_cell": 2}} # Старт на индексе 2
    for lvl in range(1, 5):
        hazards = LEVEL_HAZARDS[lvl]
        game_board[lvl] = {"cells": generate_frog_level(hazards), "opened_cell": None}
        
    ACTIVE_FROG_GAMES[user_id] = {
        "bet": bet,
        "board": game_board,
        "current_level": 0,
        "current_multiplier": 1.00,
        "failed_level": None,
        "status": "playing",
        "is_processing": False
    }
    game = ACTIVE_FROG_GAMES[user_id]
    
    next_mult = FROG_MULTIPLIERS[1]
    next_win = round(bet * next_mult, 2)
    
    text = (
        f"🐸 Frog · игра идёт.\n"
        f"·····················\n"
        f"💸 Ставка: {bet:,} n¢\n"
        f"🇮🇹 Выигрыш: 1.00x / {bet:,} n¢\n"
        f"🍀 Сл. кувшин: {next_mult}x / {next_win:,} n¢\n\n"
        f"{render_frog_text_board(game)}"
    )
    
    await message.answer(text, reply_markup=get_frog_keyboard(game))

@router.callback_query(F.data.startswith("frog_jump:"))
async def process_frog_jump(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ACTIVE_FROG_GAMES or ACTIVE_FROG_GAMES[user_id]["status"] != "playing":
        await callback.answer("❌ Активная игра не найдена.", show_alert=True)
        return
        
    game = ACTIVE_FROG_GAMES[user_id]
    if game.get("is_processing"):
        await callback.answer("❌ Активная игра не найдена.", show_alert=True)
        return

    game["is_processing"] = True
    clicked_cell = int(callback.data.split(":")[1])
    
    next_level = game["current_level"] + 1
    level_data = game["board"][next_level]
    level_data["opened_cell"] = clicked_cell
    
    # Попал в водоворот 🌀 (Проигрыш)
    if level_data["cells"][clicked_cell]:
        game["status"] = "lost"
        game["failed_level"] = next_level
        
        text = (
            f"🌀 Frog · Проигрыш!\n"
            f"·····················\n"
            f"💸 Ставка: {game['bet']:,} n¢\n"
            f"🍀 Пройдено: {game['current_level']} из 4\n\n"
            f"> ✔️ Мог забрать: x{game['current_multiplier']:.2f} / {round(game['bet'] * game['current_multiplier'], 2):,} n¢\n\n"
            f"{render_frog_text_board(game)}"
        )
        db.add_stats(user_id, is_lost=True, lost_amount=game['bet'], bet_amount=game['bet'])
        del ACTIVE_FROG_GAMES[user_id]
        
        await callback.message.edit_text(text, reply_markup=get_frog_keyboard(game))
        return
        
    # Прыжок успешный 🐸
    game["current_level"] = next_level
    game["current_multiplier"] = FROG_MULTIPLIERS[next_level]
    
    # 4 Уровень пройден (Максимальная победа)
    if next_level == 4:
        win_amount = round(game["bet"] * game["current_multiplier"], 2)
        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=game["bet"])
        game["status"] = "won"
        
        text = (
            f"👑 Frog · ПОЛНАЯ ПОБЕДА! 👑\n"
            f"·····················\n"
            f"💸 Ставка: {game['bet']:,} n¢\n"
            f"💰 Главный приз: *x{game['current_multiplier']}* / *{win_amount:,} n¢*\n\n"
            f"💰 Твой баланс: *{db.get_user(user_id)['balance']:,} nCoin*\n\n"
            f"{render_frog_text_board(game)}"
        )
        del ACTIVE_FROG_GAMES[user_id]
        await callback.message.edit_text(text, reply_markup=get_frog_keyboard(game), parse_mode="Markdown")
        return
        
    # Продолжение игры
    game["is_processing"] = False
    cashout_win = round(game["bet"] * game["current_multiplier"], 2)
    next_mult = FROG_MULTIPLIERS[next_level + 1]
    next_win = round(game["bet"] * next_mult, 2)
    
    text = (
        f"🐸 Frog · игра идёт.\n"
        f"·····················\n"
        f"💸 Ставка: {game['bet']:,} n¢\n"
        f"🇮🇹 Выигрыш: {game['current_multiplier']:.2f}x / {cashout_win:,} n¢\n"
        f"🍀 Сл. кувшин: {next_mult:.2f}x / {next_win:,} n¢\n\n"
        f"{render_frog_text_board(game)}"
    )
    await callback.message.edit_text(text, reply_markup=get_frog_keyboard(game))

@router.callback_query(F.data == "frog_cashout")
async def process_frog_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in ACTIVE_FROG_GAMES or ACTIVE_FROG_GAMES[user_id]["status"] != "playing":
        await callback.answer("❌ Активная игра не найдена.", show_alert=True)
        return
        
    # Мгновенно забираем и удаляем игру из словаря до выполнения асинхронных операций
    game = ACTIVE_FROG_GAMES.pop(user_id, None)
    if not game or game.get("status") != "playing":
        await callback.answer("❌ Активная игра не найдена.", show_alert=True)
        return
        
    game["status"] = "won"
    win_amount = round(game["bet"] * game["current_multiplier"], 2)
    
    db.update_balance(user_id, win_amount)
    db.add_stats(user_id, is_lost=False, bet_amount=game["bet"])
    
    text = (
        f"💰 Frog · Выигрыш забран! 💰\n"
        f"·····················\n"
        f"💸 Ставка: {game['bet']:,} n¢\n"
        f"📈 Забрали на: x{game['current_multiplier']:.2f}\n"
        f"🏆 Выигрыш: *{win_amount:,} n¢*\n\n"
        f"💰 Баланс: *{db.get_user(user_id)['balance']:,} nCoin*\n\n"
        f"{render_frog_text_board(game)}"
    )
    await callback.message.edit_text(text, reply_markup=get_frog_keyboard(game), parse_mode="Markdown")
