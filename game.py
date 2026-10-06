# game.py
import random
import logging
import hashlib
import secrets
import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
import db
import utils

logger = logging.getLogger(__name__)
router = Router()

# ==============================================================================
# 🎨 ПРЕМИУМ ЭМОДЗИ ДЛЯ ИГРЫ «МИНЫ» (БЕЗ КАРТИНОК)
# ==============================================================================
EMOJI_BOOM_TAG = '<tg-emoji emoji-id="5226813248900187912">💥</tg-emoji>'       # Взрывная бомба
EMOJI_BOMB_TAG = '<tg-emoji emoji-id="5370692462882857093">💣</tg-emoji>'       # Бомба
EMOJI_DIAMOND_TAG = '<tg-emoji emoji-id="5767137507879685567">💎</tg-emoji>'    # Кристалл
EMOJI_QUESTION_TAG = '<tg-emoji emoji-id="5463139580934892960">❓</tg-emoji>'   # Вопрос

EMOJI_MONEY = '<tg-emoji emoji-id="5463046637842608206">💰</tg-emoji>'       # 💰
EMOJI_CHART = '<tg-emoji emoji-id="5429463966432643712">📈</tg-emoji>'       # 📈
EMOJI_PARTY = '<tg-emoji emoji-id="5226431245918942763">🎉</tg-emoji>'       # 🎉
EMOJI_CARD = '<tg-emoji emoji-id="5472250091332993630">💳</tg-emoji>'        # 💳
EMOJI_GAMEPAD = '<tg-emoji emoji-id="5350612670435313545">🕹</tg-emoji>'     # 🕹
EMOJI_POINT = '<tg-emoji emoji-id="5465198403573012261">👉</tg-emoji>'       # 👉
EMOJI_ARROW = '<tg-emoji emoji-id="5462881955911584183">➡️</tg-emoji>'       # ➡️
EMOJI_DOLLAR = '<tg-emoji emoji-id="5215706742645599766">💸</tg-emoji>'      # 💸

MAX_BET = 200_000_000  # Максимальный лимит ставки: 200кк

ACTIVE_GAMES = {}  # {user_id: {"bet": float, "mines_count": int, "mines": list, "revealed": list, "fair_id": str, "is_processing": bool}}
MINES_FAIR_CACHE: dict[str, dict] = {}  # Кэш раундов игры «Мины» для кнопки повтора


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def fmt_n(value: float) -> str:
    """Форматирование чисел с апострофом ' (10000 -> 10'000)"""
    value = float(value or 0)
    if value < 1:
        return "0"
    if abs(value - round(value)) < 1e-9:
        return f"{int(value):,}".replace(",", "'")
    return f"{value:,.2f}".replace(",", "'")


async def update_game_text(target, text: str, reply_markup=None):
    """Единая функция отправки или редактирования текстовых сообщений (без картинок)"""
    if isinstance(target, CallbackQuery):
        msg = target.message
        try:
            if msg:
                await msg.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            try:
                await msg.delete()
            except Exception:
                pass
            await msg.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    elif isinstance(target, Message):
        await target.answer(text, reply_markup=reply_markup, parse_mode="HTML")


def get_multiplier(mines_count: int, revealed_count: int) -> float:
    """Вычисляет множитель выигрыша"""
    if revealed_count == 0:
        return 1.0
    prob = 1.0
    for i in range(revealed_count):
        prob *= (25 - mines_count - i) / (25 - i)
    mult = 0.97 / prob
    return round(mult, 2)


def create_mines_fair_game(user_id: int, bet: float, mines_count: int, mines: list[int]) -> str:
    """Создаёт запись раунда (для работы повтора игры)"""
    salt = secrets.token_hex(16)
    mines_sorted = sorted(mines)
    mines_str = ",".join(map(str, mines_sorted))
    raw_str = f"mines:{mines_str}:{salt}"
    sha_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    fair_id = secrets.token_hex(8)

    MINES_FAIR_CACHE[fair_id] = {
        "user_id": int(user_id),
        "bet": float(bet),
        "mines_count": int(mines_count),
        "mines": list(mines),
        "salt": str(salt),
        "raw_str": str(raw_str),
        "sha_hash": str(sha_hash),
        "exploded_idx": None,
        "is_win": False,
        "win_amount": 0.0,
        "multiplier": 1.0,
        "revealed_count": 0
    }

    if len(MINES_FAIR_CACHE) > 1000:
        oldest_key = next(iter(MINES_FAIR_CACHE))
        MINES_FAIR_CACHE.pop(oldest_key, None)

    return fair_id


# --- КЛАВИАТУРЫ ИГРОВОГО ПОЛЯ (ИСПРАВЛЕНА ОШИБКА ИМПОРТА "style") ---

def get_mines_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Сетка во время игры: закрытые ячейки — знаки вопроса ❓, открытые — кристаллы 💎"""
    game = ACTIVE_GAMES.get(user_id)
    if not game:
        return None
        
    keyboard = []
    for r in range(5):
        row_buttons = []
        for c in range(5):
            idx = r * 5 + c
            if idx in game["revealed"]:
                row_buttons.append(InlineKeyboardButton(text="💎", callback_data=f"mine_cell:{idx}"))
            else:
                row_buttons.append(InlineKeyboardButton(text="❓", callback_data=f"mine_cell:{idx}"))
        keyboard.append(row_buttons)
        
    revealed_count = len(game["revealed"])
    if revealed_count > 0:
        mult = get_multiplier(game["mines_count"], revealed_count)
        cashout_amount = round(game["bet"] * mult, 2)
        keyboard.append([
            InlineKeyboardButton(text=f"💰 Забрать {fmt_n(cashout_amount)} n¢ (x{mult})", callback_data="mine_cashout")
        ])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_exploded_keyboard(user_id: int, exploded_idx: int, fair_id: str = None) -> InlineKeyboardMarkup:
    """Поле после проигрыша: раскрывается вся карта + кнопка повторить (кнопка честности убрана)"""
    game = ACTIVE_GAMES.get(user_id)
    mines = game["mines"] if game else MINES_FAIR_CACHE.get(fair_id, {}).get("mines", [])
    keyboard = []
    for r in range(5):
        row_buttons = []
        for c in range(5):
            idx = r * 5 + c
            if idx == exploded_idx:
                row_buttons.append(InlineKeyboardButton(text="💥", callback_data="mine_noop"))
            elif idx in mines:
                row_buttons.append(InlineKeyboardButton(text="💣", callback_data="mine_noop"))
            else:
                row_buttons.append(InlineKeyboardButton(text="💎", callback_data="mine_noop"))
        keyboard.append(row_buttons)

    if fair_id:
        keyboard.append([
            InlineKeyboardButton(text="🔄 Повторить раунд", callback_data=f"mine_repeat:{fair_id}")
        ])
    else:
        keyboard.append([InlineKeyboardButton(text="🔄 Играть снова", callback_data="mine_restart")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_won_keyboard(user_id: int, fair_id: str = None) -> InlineKeyboardMarkup:
    """Поле после победы/забора денег + кнопка повторить (кнопка честности убрана)"""
    game = ACTIVE_GAMES.get(user_id)
    mines = game["mines"] if game else MINES_FAIR_CACHE.get(fair_id, {}).get("mines", [])
    keyboard = []
    for r in range(5):
        row_buttons = []
        for c in range(5):
            idx = r * 5 + c
            if idx in mines:
                row_buttons.append(InlineKeyboardButton(text="💣", callback_data="mine_noop"))
            else:
                row_buttons.append(InlineKeyboardButton(text="💎", callback_data="mine_noop"))
        keyboard.append(row_buttons)

    if fair_id:
        keyboard.append([
            InlineKeyboardButton(text="🔄 Повторить раунд", callback_data=f"mine_repeat:{fair_id}")
        ])
    else:
        keyboard.append([InlineKeyboardButton(text="🔄 Играть снова", callback_data="mine_restart")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- СТАРТОВОЕ МЕНЮ И ЗАПУСК ИГРЫ ---

async def start_mines_round(event, state: FSMContext, bet: float, mines_count: int):
    """Единая функция запуска раунда с проверками и списанием баланса"""
    user_id = event.from_user.id if isinstance(event, (Message, CallbackQuery)) else event
    user = db.get_user(user_id)

    if bet <= 0:
        msg = "❌ <b>Ставка должна быть больше 0!</b> Примеры: <code>10к</code>, <code>50к</code>, <code>1кк</code>."
        if isinstance(event, CallbackQuery):
            return await event.answer(msg, show_alert=True)
        return await event.answer(msg, parse_mode="HTML")

    if bet > MAX_BET:
        msg = f"❌ <b>Максимальная ставка — {fmt_n(MAX_BET)} nCoin!</b>"
        if isinstance(event, CallbackQuery):
            return await event.answer(msg, show_alert=True)
        return await event.answer(msg, parse_mode="HTML")

    if user["balance"] < bet:
        msg = f"❌ <b>Недостаточно nCoin!</b> Ваш баланс: {EMOJI_CARD} <b>{fmt_n(user['balance'])} nCoin</b>"
        if isinstance(event, CallbackQuery):
            return await event.answer(msg, show_alert=True)
        return await event.answer(msg, parse_mode="HTML")

    if not (1 <= mines_count <= 24):
        msg = "❌ <b>Количество мин должно быть целым числом от 1 до 24!</b>"
        if isinstance(event, CallbackQuery):
            return await event.answer(msg, show_alert=True)
        return await event.answer(msg, parse_mode="HTML")

    if user_id in ACTIVE_GAMES:
        msg = "❌ <b>У вас уже запущена игра!</b> Завершите её или заберите баланс."
        if isinstance(event, CallbackQuery):
            return await event.answer(msg, show_alert=True)
        return await event.answer(msg, parse_mode="HTML")

    db.update_balance(user_id, -bet)
    mines = random.sample(range(25), mines_count)
    fair_id = create_mines_fair_game(user_id, bet, mines_count, mines)

    ACTIVE_GAMES[user_id] = {
        "bet": bet,
        "mines_count": mines_count,
        "mines": mines,
        "revealed": [],
        "fair_id": fair_id,
        "is_processing": False
    }

    next_mult = get_multiplier(mines_count, 1)
    text = (
        f"{EMOJI_GAMEPAD} <b>Игра началась!</b> ({EMOJI_DIAMOND_TAG} 0/25)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_MONEY} Ставка: <b>{fmt_n(bet)} nCoin</b> | {EMOJI_BOMB_TAG} Мины: <b>{mines_count}</b>\n"
        f"{EMOJI_CHART} Множитель: <b>x1.00</b> {EMOJI_ARROW} Следующий: <b>x{next_mult:.2f}</b>\n\n"
        f"{EMOJI_POINT} Открывайте ячейки игрового поля:"
    )
    await update_game_text(event, text, reply_markup=get_mines_keyboard(user_id))


@router.message(Command("mines", "miny", "mina"))
@router.message(F.text.lower().startswith(("мины", "мина", "мину")))
async def start_mines_game_cmd(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    parts = message.text.split()
    if len(parts) < 3:
        text = (
            f"<b>Игра МИНЫ (Mines)</b> {EMOJI_BOMB_TAG}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Находите скрытые алмазы {EMOJI_DIAMOND_TAG} и обходите мины {EMOJI_BOMB_TAG}!\n"
            f"Каждый открытый алмаз увеличивает ваш множитель выигрыша.\n\n"
            "✍️ <b>Формат команды:</b> <code>мины [ставка] [мины]</code>\n"
            "Пример: <code>мины 10к 3</code> или <code>мины 1кк 5</code>\n\n"
            f"{EMOJI_CARD} Твой баланс: <b>{fmt_n(user['balance'])} nCoin</b>\n"
            f"⚠️ Максимальная ставка: <b>{fmt_n(MAX_BET)} nCoin</b>"
        )
        await update_game_text(message, text)
        return
        
    try:
        bet = utils.parse_bet_input(parts[1], user["balance"])
    except Exception:
        await message.answer("❌ <b>Некорректная ставка!</b> Введите число или 'все'.", parse_mode="HTML")
        return
    
    if bet <= 0:
        await message.answer("❌ <b>Ставка должна быть больше 0!</b> Примеры: <code>100к</code>, <code>1кк</code>.", parse_mode="HTML")
        return

    if bet > MAX_BET:
        await message.answer(f"❌ <b>Максимальная ставка — {fmt_n(MAX_BET)} nCoin!</b>", parse_mode="HTML")
        return
        
    if user["balance"] < bet:
        await message.answer(f"❌ <b>Недостаточно средств!</b> Баланс: <b>{fmt_n(user['balance'])} nCoin</b>", parse_mode="HTML")
        return
        
    try:
        mines_count = int(parts[2])
        if not (1 <= mines_count <= 24):
            raise ValueError
    except ValueError:
        await message.answer("❌ <b>Количество мин должно быть целым числом от 1 до 24!</b>")
        return

    await start_mines_round(message, state, bet, mines_count)


# --- ОБРАБОТКА КЛИКА НА ЯЧЕЙКУ ПОЛЯ ---

@router.callback_query(F.data.startswith("mine_cell:"))
async def mine_cell_click(callback: CallbackQuery):
    user_id = callback.from_user.id
    game = ACTIVE_GAMES.get(user_id)
    
    # АНТИ-ФЛУД: Блокировка частых кликов во избежание багов
    if not game or game.get("is_processing"):
        return await callback.answer()
        
    idx = int(callback.data.split(":")[1])
    if idx in game["revealed"]:
        return await callback.answer()

    game["is_processing"] = True
    
    try:
        # --- ПОДРЫВ НА МИНЕ (ПРОИГРЫШ) ---
        if idx in game["mines"]:
            fair_id = game.get("fair_id")
            if fair_id and fair_id in MINES_FAIR_CACHE:
                MINES_FAIR_CACHE[fair_id].update({
                    "exploded_idx": idx,
                    "is_win": False,
                    "revealed_count": len(game["revealed"])
                })

            ACTIVE_GAMES.pop(user_id, None)
            
            bet = game["bet"]
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet, game_name="mines", win_amount=0)
            user_updated = db.get_user(user_id)
            
            text = (
                f"<b>{EMOJI_BOOM_TAG} БАБАХ! Вы подорвались на мине! {EMOJI_BOOM_TAG}</b>\n"
                f"💸 Проиграно: <b>{fmt_n(bet)} nCoin</b>\n\n"
                f"{EMOJI_CARD} Баланс: <b>{fmt_n(user_updated['balance'])} nCoin</b>"
            )
            await update_game_text(callback, text, reply_markup=get_exploded_keyboard(user_id, idx, fair_id))
            await callback.answer()
            return
            
        # --- БЕЗОПАСНАЯ КЛЕТКА ---
        game["revealed"].append(idx)
        revealed_count = len(game["revealed"])
        safe_cells_needed = 25 - game["mines_count"]
        
        # ПОЛНАЯ ПОБЕДА (Открыты все алмазы)
        if revealed_count == safe_cells_needed:
            fair_id = game.get("fair_id")
            mult = get_multiplier(game["mines_count"], revealed_count)
            win_amount = round(game["bet"] * mult, 2)

            if fair_id and fair_id in MINES_FAIR_CACHE:
                MINES_FAIR_CACHE[fair_id].update({
                    "is_win": True,
                    "win_amount": win_amount,
                    "multiplier": mult,
                    "revealed_count": revealed_count
                })

            ACTIVE_GAMES.pop(user_id, None)
            
            db.update_balance(user_id, win_amount)
            db.add_stats(user_id, is_lost=False, bet_amount=game["bet"], game_name="mines", win_amount=win_amount)
            user_updated = db.get_user(user_id)
            
            text = (
                f"🏆 <b>ПОБЕДА! Карта полностью зачищена!</b> {EMOJI_DIAMOND_TAG}\n"
                f"{EMOJI_MONEY} Выиграно: <b>+{fmt_n(win_amount)} nCoin</b> (x{mult})\n\n"
                f"{EMOJI_CARD} Баланс: <b>{fmt_n(user_updated['balance'])} nCoin</b>"
            )
            await update_game_text(callback, text, reply_markup=get_won_keyboard(user_id, fair_id))
            await callback.answer()
            return
            
        # ИГРА ПРОДОЛЖАЕТСЯ
        mult = get_multiplier(game["mines_count"], revealed_count)
        next_mult = get_multiplier(game["mines_count"], revealed_count + 1)
        
        text = (
            f"{EMOJI_GAMEPAD} <b>Отличный ход!</b> ({EMOJI_DIAMOND_TAG} {revealed_count}/{safe_cells_needed})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{EMOJI_MONEY} Ставка: <b>{fmt_n(game['bet'])} nCoin</b> | {EMOJI_BOMB_TAG} Мины: <b>{game['mines_count']}</b>\n"
            f"{EMOJI_CHART} Множитель: <b>x{mult:.2f}</b> {EMOJI_ARROW} Следующий: <b>x{next_mult:.2f}</b>\n\n"
            f"{EMOJI_POINT} Продолжайте открывать ячейки или заберите деньги!"
        )
        await update_game_text(callback, text, reply_markup=get_mines_keyboard(user_id))
        await callback.answer()
    
    finally:
        if user_id in ACTIVE_GAMES:
            ACTIVE_GAMES[user_id]["is_processing"] = False


# --- ЗАБОР ВЫИГРЫША (КЭШАУТ) ---

@router.callback_query(F.data == "mine_cashout")
async def mine_cashout(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    # Удаляем игру из памяти, исключая повторные запросы
    game = ACTIVE_GAMES.pop(user_id, None)
    if not game:
        await callback.answer("❌ Активная игра не найдена.", show_alert=True)
        return
        
    fair_id = game.get("fair_id")
    revealed_count = len(game["revealed"])
    mult = get_multiplier(game["mines_count"], revealed_count)
    win_amount = round(game["bet"] * mult, 2)
    
    if fair_id and fair_id in MINES_FAIR_CACHE:
        MINES_FAIR_CACHE[fair_id].update({
            "is_win": True,
            "win_amount": win_amount,
            "multiplier": mult,
            "revealed_count": revealed_count
        })

    db.update_balance(user_id, win_amount)
    db.add_stats(user_id, is_lost=False, bet_amount=game["bet"], game_name="mines", win_amount=win_amount)
    user_updated = db.get_user(user_id)
    
    text = (
        f"{EMOJI_MONEY} <b>Вы успешно забрали деньги!</b> {EMOJI_DIAMOND_TAG}\n"
        f"{EMOJI_CHART} Множитель: <b>x{mult:.2f}</b>\n"
        f"{EMOJI_PARTY} Выигрыш: <b>+{fmt_n(win_amount)} nCoin</b>\n\n"
        f"{EMOJI_CARD} Баланс: <b>{fmt_n(user_updated['balance'])} nCoin</b>"
    )
    await update_game_text(callback, text, reply_markup=get_won_keyboard(user_id, fair_id))
    await callback.answer()


# --- ОБРАБОТЧИК КНОПКИ «ПОВТОР» ---

@router.callback_query(F.data.startswith("mine_repeat:"), StateFilter("*"))
async def mine_repeat_callback(callback: CallbackQuery, state: FSMContext):
    """Повторяет игру с той же ставкой и количеством мин"""
    try:
        parts = callback.data.split(":", 1)
        if len(parts) != 2:
            return await callback.answer("❌ Ошибка вызова.", show_alert=True)

        fair_id = parts[1]
        previous_game = MINES_FAIR_CACHE.get(fair_id)

        if not previous_game:
            return await callback.answer("❌ Предыдущий раунд устарел или бот перезапускался.", show_alert=True)

        if int(previous_game["user_id"]) != int(callback.from_user.id):
            return await callback.answer("❌ Это не ваш раунд.", show_alert=True)

        bet = float(previous_game["bet"])
        mines_count = int(previous_game["mines_count"])

        await state.clear()
        await start_mines_round(event=callback, state=state, bet=bet, mines_count=mines_count)

    except Exception as error:
        logger.exception("Ошибка при повторе игры Мины: %s", error)
        try:
            await callback.answer("❌ Не удалось повторить игру.", show_alert=True)
        except Exception:
            pass


# --- СЕКРЕТНЫЙ ПРОСМОТР КАРТЫ (ТОЛЬКО ДЛЯ АДМИНА) ---

@router.message(Command("просмотр"))
@router.message(F.text == "/просмотр")
async def admin_view_mines(message: Message):
    if message.from_user.id != 7727345054:
        return
        
    game = ACTIVE_GAMES.get(message.from_user.id)
    if not game:
        await message.answer("🔍 <b>Активная игра в мины не найдена!</b>", parse_mode="HTML")
        return
        
    mines = game["mines"]
    grid_str = "🕵️‍♂️ <b>СЕКРЕТНЫЙ ПРОСМОТР КАРТЫ МИН</b> 🕵️‍♂️\n━━━━━━━━━━━━━━━━━━━━\n"
    for r in range(5):
        row_cells = []
        for c in range(5):
            idx = r * 5 + c
            if idx in mines:
                row_cells.append("💣")
            else:
                row_cells.append("💎")
        grid_str += " ".join(row_cells) + "\n"
    grid_str += "━━━━━━━━━━━━━━━━━━━━\n💎 — Алмаз | 💣 — Мина"
    await message.answer(grid_str, parse_mode="HTML")


# --- КНОПКИ НАВИГАЦИИ ---

@router.callback_query(F.data == "mine_restart")
async def mine_restart(callback: CallbackQuery):
    await callback.answer()
    text = (
        f"<b>Игра МИНЫ (Mines)</b> {EMOJI_BOMB_TAG}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Напишите в чат команду для старта:\n"
        "<code>мины [ставка] [мины]</code>\n"
        "Например: <code>мины 10к 3</code>"
    )
    await update_game_text(callback, text)


@router.callback_query(F.data == "mine_noop")
async def mine_noop(callback: CallbackQuery):
    await callback.answer()
