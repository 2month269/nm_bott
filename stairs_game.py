import random
import logging
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

import db  # Модуль базы данных

logger = logging.getLogger(__name__)

router = Router()

# =====================================================================
# КОНФИГУРАЦИЯ БАННЕРОВ И УРОВНЕЙ
# =====================================================================

# URL-ссылки на стильные графические обложки для сообщений бота
GAME_BANNERS = {
    "welcome": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&q=80",
    "playing": "https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=800&q=80",
    "win": "https://images.unsplash.com/photo-1518609878373-06d740f60d8b?w=800&q=80",
    "lose": "https://images.unsplash.com/photo-1579373903781-fd5c0c30c4cd?w=800&q=80",
}

# Конфигурация уровней игры "Лесенка"
LEVEL_CONFIG = {
    1: {"total": 5, "mines": 1, "multiplier": 1.20},
    2: {"total": 4, "mines": 1, "multiplier": 1.55},
    3: {"total": 3, "mines": 1, "multiplier": 2.25},
    4: {"total": 3, "mines": 2, "multiplier": 6.50},
    5: {"total": 2, "mines": 1, "multiplier": 12.50},
}


class StairsState(StatesGroup):
    waiting_for_bet = State()
    playing = State()


# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================

def parse_bet_amount(text: str, user_balance: float) -> float:
    """Парсер текстовых ставок с поддержкой к,кк,ккк,k,kk,kkk,all"""
    text_clean = text.lower().strip().replace(" ", "").replace(",", ".")
    
    if text_clean in ["все", "все-ин", "ва-банк", "all", "allin", "all-in", "аллин"]:
        return user_balance

    multipliers = {
        'kkkk': 1_000_000_000_000,
        'кккк': 1_000_000_000_000,
        'kkk': 1_000_000_000,
        'ккк': 1_000_000_000,
        'kk': 1_000_000,
        'кк': 1_000_000,
        'k': 1_000,
        'к': 1_000,
    }

    for suffix, mult in multipliers.items():
        if text_clean.endswith(suffix):
            num_part = text_clean[:-len(suffix)]
            try:
                val = float(num_part)
                return val * mult
            except ValueError:
                pass

    try:
        return float(text_clean)
    except ValueError:
        return -1.0


def generate_mines() -> dict:
    """Предварительная генерация мин для всех 5 уровней"""
    mines = {}
    for lvl, cfg in LEVEL_CONFIG.items():
        mines[lvl] = random.sample(range(cfg["total"]), cfg["mines"])
    return mines


def render_progress_bar(current_level: int, total_levels: int = 5, is_game_over: bool = False, won: bool = False) -> str:
    """Генерирует наглядную шкалу прогресса подъема по лесенке"""
    if is_game_over:
        if won:
            return "📈 <b>Прогресс:</b> [🟩🟩🟩🟩🟩] <b>100%</b> 👑"
        else:
            passed = current_level - 1
            bar = "🟩" * passed + "💥" + "⬛️" * (total_levels - current_level)
            pct = int((passed / total_levels) * 100)
            return f"📈 <b>Прогресс:</b> [{bar}] <b>{pct}%</b>"
    else:
        passed = current_level - 1
        bar = "🟩" * passed + "🟡" + "⬛️" * (total_levels - current_level)
        pct = int((passed / total_levels) * 100)
        return f"📈 <b>Прогресс:</b> [{bar}] <b>{pct}%</b> (Шаг {current_level}/{total_levels})"


def render_game_text(bet: float, current_level: int, history: dict, mines_map: dict = None, is_game_over: bool = False, won: bool = False, win_amount: float = 0.0) -> str:
    """Формирует обновленный красивый текстовый интерфейс с прогресс-баром и подсказками"""
    current_multiplier = LEVEL_CONFIG[current_level - 1]["multiplier"] if current_level > 1 else 0.0
    current_win = round(bet * current_multiplier, 2) if current_level > 1 else 0.0

    text = "🪜 <b>ИГРА «ЛЕСЕНКА»</b>\n"
    text += f"💰 <b>Ставка:</b> <code>{bet:,.0f} n¢</code>\n"
    text += f"{render_progress_bar(current_level, 5, is_game_over, won)}\n"
    text += "✨ ━━━━━━━━━━━━━━━━━━━━ ✨\n"

    for lvl in range(5, 0, -1):
        cfg = LEVEL_CONFIG[lvl]
        multiplier = cfg["multiplier"]
        next_win = round(bet * multiplier, 2)
        
        prefix = "👑 " if lvl == 5 else "   "
        pointer = "▶️ " if lvl == current_level and not is_game_over else "   "

        if lvl in history:
            chosen, mines = history[lvl]
            cells = []
            for idx in range(cfg["total"]):
                if idx == chosen and idx in mines:
                    cells.append("[💥]")
                elif idx in mines:
                    cells.append("[💣]")
                elif idx == chosen:
                    cells.append("[🟩]")
                else:
                    cells.append("[⬜️]")
            row_str = " ".join(cells)
            text += f"{prefix}{pointer}<b>Уровень {lvl}</b>: {row_str} ── <b>x{multiplier:.2f}</b> ✅\n"
        
        elif lvl == current_level and not is_game_over:
            cells = ["[❓]"] * cfg["total"]
            row_str = " ".join(cells)
            text += f"{prefix}{pointer}<b>Уровень {lvl}</b>: {row_str} ── <b>x{multiplier:.2f}</b> (до <code>{next_win:,.0f}</code> n¢)\n"
            
        else:
            if is_game_over and mines_map and lvl in mines_map:
                mines = mines_map[lvl]
                cells = []
                for idx in range(cfg["total"]):
                    if idx in mines:
                        cells.append("[💣]")
                    else:
                        cells.append("[⬜️]")
                row_str = " ".join(cells)
            else:
                cells = ["[🔒]"] * cfg["total"]
                row_str = " ".join(cells)
            text += f"{prefix}{pointer}Уровень {lvl}: {row_str} ── x{multiplier:.2f}\n"

    text += "✨ ━━━━━━━━━━━━━━━━━━━━ ✨\n"

    if is_game_over:
        if won:
            profit = win_amount - bet
            text += f"🎉 <b>ПОБЕДА! Вы поднялись на вершину!</b>\n"
            text += f"💵 <b>Забрано:</b> <code>{win_amount:,.0f} n¢</code> (+<code>{profit:,.0f} n¢</code>)"
        else:
            text += f"💥 <b>БАБАХ! На Уровне {current_level} оказалась мина!</b>\n"
            text += f"💸 Ваша ставка <code>{bet:,.0f} n¢</code> сгорела."
    else:
        if current_level > 1:
            profit = current_win - bet
            profit_pct = int(((current_multiplier) - 1) * 100)
            text += f"💵 <b>Текущий куш:</b> <code>{current_win:,.0f} n¢</code> (+{profit_pct}% / +<code>{profit:,.0f}</code> n¢)\n"
        else:
            text += f"💵 <b>Текущий куш:</b> <code>0 n¢</code> (Сделайте первый шаг)\n"
            
        next_mult = LEVEL_CONFIG[current_level]["multiplier"]
        text += f"🎯 Выберите безопасную клетку на <b>Уровне {current_level}</b>! (Множитель: <b>x{next_mult:.2f}</b>)"

    return text


def build_game_keyboard(current_level: int, bet: float) -> InlineKeyboardMarkup:
    """Генерирует информативную клавиатуру кнопок"""
    buttons = []
    cfg = LEVEL_CONFIG[current_level]
    
    # Кнопки с шагами и нумерацией
    row_cells = []
    for i in range(cfg["total"]):
        row_cells.append(InlineKeyboardButton(
            text=f"📦 Клетка {i + 1}", 
            callback_data=f"stairs_step:{i}"
        ))
    buttons.append(row_cells)

    # Информативная кнопка забора денег
    if current_level > 1:
        current_multiplier = LEVEL_CONFIG[current_level - 1]["multiplier"]
        current_win = round(bet * current_multiplier, 2)
        profit = current_win - bet
        profit_pct = int((current_multiplier - 1.0) * 100)
        
        btn_text = f"💰 Забрать {current_win:,.0f} n¢ (📊 +{profit_pct}% | +{profit:,.0f} n¢)"
        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data="stairs_cashout")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =====================================================================
# ХЕНДЛЕРЫ И ЛОГИКА
# =====================================================================

@router.message(Command("stairs"))
@router.message(F.text.lower().startswith("лесенка"))
@router.message(F.text.lower().startswith("🪜 лесенка"))
async def cmd_stairs_start(message: Message, state: FSMContext):
    """Старт игры / запуск с аргументом ставки или вывод меню с баннером"""
    await state.clear()
    
    user = db.get_user(
        user_id=message.from_user.id,
        first_name=message.from_user.first_name,
        username=message.from_user.username
    )

    parts = message.text.strip().split()
    bet_arg = None
    if len(parts) > 1:
        bet_arg = parts[1]

    # Если ставка передана сразу: "лесенка 100к", "/stairs 500"
    if bet_arg:
        bet = parse_bet_amount(bet_arg, user["balance"])
        if bet > 0:
            return await start_stairs_game(message, state, bet)
        else:
            await message.answer("❌ Неверно указана сумма ставки. Попробуйте еще раз.")

    # Меню выбора ставки с красивой обложкой
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10к n¢", callback_data="stairs_preset:10k"),
            InlineKeyboardButton(text="100к n¢", callback_data="stairs_preset:100k"),
            InlineKeyboardButton(text="1кк n¢", callback_data="stairs_preset:1kk"),
        ],
        [
            InlineKeyboardButton(text="10кк n¢", callback_data="stairs_preset:10kk"),
            InlineKeyboardButton(text="100ккк n¢", callback_data="stairs_preset:100kkk"),
            InlineKeyboardButton(text="🔥 ALL-IN", callback_data="stairs_preset:allin"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="stairs_cancel")]
    ])

    caption_text = (
        f"🪜 <b>Добро пожаловать в игру «Лесенка»!</b>\n\n"
        f"💰 <b>Ваш баланс:</b> <code>{user['balance']:,.0f} n¢</code>\n"
        f"🏆 Поднимитесь по 5 ступеням и заберите куш до <b>x12.50</b> от ставки!\n\n"
        f"💡 <i>Вы можете запускать игру сразу командой:\n"
        f"<code>лесенка 100к</code> или <code>/stairs 1кк</code></i>\n\n"
        f"👇 Выберите сумму ставки ниже или введите числом в чат:"
    )

    try:
        await message.answer_photo(
            photo=GAME_BANNERS["welcome"],
            caption=caption_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        # Резервный текстовый вывод, если фото не загрузилось
        await message.answer(caption_text, reply_markup=kb, parse_mode="HTML")

    await state.set_state(StairsState.waiting_for_bet)


@router.callback_query(F.data.startswith("stairs_preset:"), StairsState.waiting_for_bet)
async def process_preset_bet(call: CallbackQuery, state: FSMContext):
    """Обработка выбора кнопки пресета ставки"""
    preset = call.data.split(":")[1]
    user = db.get_user(call.from_user.id)
    
    bet = parse_bet_amount(preset, user["balance"])
    await start_stairs_game(call, state, bet)


@router.message(StairsState.waiting_for_bet)
async def process_text_bet(message: Message, state: FSMContext):
    """Обработка текстового ввода суммы ставки"""
    user = db.get_user(message.from_user.id)
    bet = parse_bet_amount(message.text, user["balance"])
    
    if bet <= 0:
        return await message.answer("❌ Введите корректную сумму ставки (например: 10к, 100к, 1кк, 10кк, 100ккк).")

    await start_stairs_game(message, state, bet)


async def start_stairs_game(event, state: FSMContext, bet: float):
    """Инициализация и запуск нового игрового раунда"""
    user_id = event.from_user.id
    user = db.get_user(user_id)

    if bet < 10:
        text = "❌ Минимальная ставка: 10 n¢"
        return await event.answer(text) if isinstance(event, Message) else await event.answer(text, show_alert=True)

    if user["balance"] < bet:
        text = f"❌ Недостаточно средств! Ваш баланс: {user['balance']:,.0f} n¢"
        return await event.answer(text) if isinstance(event, Message) else await event.answer(text, show_alert=True)

    # Списываем ставку из БД
    db.update_balance(user_id, -bet)

    game_data = {
        "bet": bet,
        "current_level": 1,
        "mines": generate_mines(),
        "history": {}
    }

    await state.set_state(StairsState.playing)
    await state.update_data(game_data=game_data)

    text = render_game_text(bet=bet, current_level=1, history={})
    kb = build_game_keyboard(current_level=1, bet=bet)

    if isinstance(event, Message):
        try:
            await event.answer_photo(
                photo=GAME_BANNERS["playing"],
                caption=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        try:
            # Обновляем фото и текст медиа-сообщения
            media = InputMediaPhoto(media=GAME_BANNERS["playing"], caption=text, parse_mode="HTML")
            await event.message.edit_media(media=media, reply_markup=kb)
        except Exception:
            try:
                await event.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await event.message.answer_photo(
                    photo=GAME_BANNERS["playing"],
                    caption=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )


@router.callback_query(F.data.startswith("stairs_step:"), StairsState.playing)
async def process_step(call: CallbackQuery, state: FSMContext):
    """Обработка нажатия на клетку игроком"""
    chosen_idx = int(call.data.split(":")[1])
    data = await state.get_data()
    game = data.get("game_data")

    if not game:
        await call.answer("Игра завершена.", show_alert=True)
        return

    lvl = game["current_level"]
    bet = game["bet"]
    mines = game["mines"][lvl]

    game["history"][lvl] = (chosen_idx, mines)

    # Игрок наступил на мину -> ПОРАЖЕНИЕ
    if chosen_idx in mines:
        db.add_stats(
            uid=call.from_user.id,
            is_lost=True,
            lost_amount=bet,
            bet_amount=bet,
            game_name="stairs",
            win_amount=0.0
        )
        await state.clear()
        
        text = render_game_text(
            bet=bet,
            current_level=lvl,
            history=game["history"],
            mines_map=game["mines"],
            is_game_over=True,
            won=False
        )
        
        try:
            media = InputMediaPhoto(media=GAME_BANNERS["lose"], caption=text, parse_mode="HTML")
            await call.message.edit_media(media=media)
        except Exception:
            try:
                await call.message.edit_caption(caption=text, parse_mode="HTML")
            except TelegramBadRequest:
                pass

        await call.answer("💥 БАБАХ! Вы наступили на мину!", show_alert=True)
        return

    # Игрок дошел до 5 уровня -> МАКСИМАЛЬНАЯ ПОБЕДА
    if lvl == 5:
        multiplier = LEVEL_CONFIG[5]["multiplier"]
        win_amount = round(bet * multiplier, 2)
        
        db.update_balance(call.from_user.id, win_amount)
        db.add_stats(
            uid=call.from_user.id,
            is_lost=False,
            lost_amount=0.0,
            bet_amount=bet,
            game_name="stairs",
            win_amount=win_amount
        )
        await state.clear()

        text = render_game_text(
            bet=bet,
            current_level=lvl,
            history=game["history"],
            mines_map=game["mines"],
            is_game_over=True,
            won=True,
            win_amount=win_amount
        )
        
        try:
            media = InputMediaPhoto(media=GAME_BANNERS["win"], caption=text, parse_mode="HTML")
            await call.message.edit_media(media=media)
        except Exception:
            try:
                await call.message.edit_caption(caption=text, parse_mode="HTML")
            except TelegramBadRequest:
                pass

        await call.answer(f"🎉 Вершина покорена! Выигрыш: {win_amount:,.0f} n¢!", show_alert=True)
    else:
        # Успешный шаг -> Поднимаемся выше
        game["current_level"] += 1
        await state.update_data(game_data=game)

        text = render_game_text(bet=bet, current_level=game["current_level"], history=game["history"])
        kb = build_game_keyboard(current_level=game["current_level"], bet=bet)

        try:
            await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            pass

        await call.answer("Удачно! Поднимаемся выше!")


@router.callback_query(F.data == "stairs_cashout", StairsState.playing)
async def process_cashout(call: CallbackQuery, state: FSMContext):
    """Забор выигрыша досрочно"""
    data = await state.get_data()
    game = data.get("game_data")

    if not game:
        await call.answer("Игра завершена.", show_alert=True)
        return

    lvl = game["current_level"]
    bet = game["bet"]

    if lvl <= 1:
        await call.answer("Сначала пройдите хотя бы 1 уровень!", show_alert=True)
        return

    multiplier = LEVEL_CONFIG[lvl - 1]["multiplier"]
    win_amount = round(bet * multiplier, 2)

    db.update_balance(call.from_user.id, win_amount)
    db.add_stats(
        uid=call.from_user.id,
        is_lost=False,
        lost_amount=0.0,
        bet_amount=bet,
        game_name="stairs",
        win_amount=win_amount
    )
    await state.clear()

    text = render_game_text(
        bet=bet,
        current_level=lvl - 1,
        history=game["history"],
        mines_map=game["mines"],
        is_game_over=True,
        won=True,
        win_amount=win_amount
    )

    try:
        media = InputMediaPhoto(media=GAME_BANNERS["win"], caption=text, parse_mode="HTML")
        await call.message.edit_media(media=media)
    except Exception:
        try:
            await call.message.edit_caption(caption=text, parse_mode="HTML")
        except TelegramBadRequest:
            pass

    await call.answer(f"💰 Забрано {win_amount:,.0f} n¢!", show_alert=True)


@router.callback_query(F.data == "stairs_cancel")
async def process_cancel(call: CallbackQuery, state: FSMContext):
    """Отмена игры на этапе выбора ставки"""
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer("❌ Игра отменена.")
