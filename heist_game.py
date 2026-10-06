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
# КОНФИГУРАЦИЯ ИГРЫ «ОГРАБЛЕНИЕ БАНКА»
# =====================================================================

# Тематические графические баннеры
HEIST_BANNERS = {
    "welcome": "https://images.unsplash.com/photo-1541354329998-f4d9a9f9297f?w=800&q=80",
    "playing": "https://images.unsplash.com/photo-1563986768609-322da13575f3?w=800&q=80",
    "win": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=800&q=80",
    "lose": "https://images.unsplash.com/photo-1510511459019-5dee997dd1db?w=800&q=80",
}

# Настройки уровней и инструментов взлома
HEIST_LEVELS = {
    1: {
        "title": "🚪 Уровень 1: Входные двери банка",
        "tools": {
            "safe": {
                "name": "🔑 Отмычка",
                "chance": 85,
                "mult": 1.25,
                "desc": "Высокая точность, низкая шумность."
            },
            "medium": {
                "name": "💻 Хакерский софт",
                "chance": 50,
                "mult": 2.00,
                "desc": "Взлом терминала охраны."
            },
            "risk": {
                "name": "💣 Динамит",
                "chance": 25,
                "mult": 4.00,
                "desc": "Мгновенный подрыв цепи!"
            }
        }
    },
    2: {
        "title": "🔒 Уровень 2: Тяжёлая дверь сейфа",
        "tools": {
            "safe": {
                "name": "🛠 Термитный резак",
                "chance": 80,
                "mult": 1.30,
                "desc": "Прожигает стальные задвижки."
            },
            "medium": {
                "name": "📡 Перехватчик кода",
                "chance": 50,
                "mult": 2.10,
                "desc": "Подбор комбинации замка."
            },
            "risk": {
                "name": "🧨 Направленный взрыв",
                "chance": 20,
                "mult": 5.00,
                "desc": "Пробитие центральной петли!"
            }
        }
    },
    3: {
        "title": "💎 Уровень 3: Главный депозитарий",
        "tools": {
            "safe": {
                "name": "🧰 Лазерный деструктор",
                "chance": 75,
                "mult": 1.40,
                "desc": "Отказ системы защиты ячеек."
            },
            "medium": {
                "name": "🤖 Вирус 'Apex'",
                "chance": 45,
                "mult": 2.50,
                "desc": "Отключение главного сервера."
            },
            "risk": {
                "name": "🚀 Плазменный бур",
                "chance": 15,
                "mult": 8.00,
                "desc": "Вскрытие золотого запаса!"
            }
        }
    }
}


class HeistState(StatesGroup):
    waiting_for_bet = State()
    playing = State()


# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =====================================================================

def parse_bet_amount(text: str, user_balance: float) -> float:
    """Парсер текстовых ставок (10к, 1кк, all, все)"""
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


def render_progress_bar(current_level: int, total_levels: int = 3, is_game_over: bool = False, won: bool = False) -> str:
    """Генерирует шкалу прогресса взлома банка"""
    if is_game_over:
        if won:
            return "📈 <b>Статус взлома:</b> [🟩🟩🟩] <b>100% (БАНК ОГРАБЛЕН!)</b> 💰"
        else:
            passed = current_level - 1
            bar = "🟩" * passed + "🚨" + "⬛️" * (total_levels - current_level)
            pct = int((passed / total_levels) * 100)
            return f"📈 <b>Статус взлома:</b> [{bar}] <b>{pct}% (СИГНАЛИЗАЦИЯ!)</b>"
    else:
        passed = current_level - 1
        bar = "🟩" * passed + "🕵️‍♂️" + "⬛️" * (total_levels - current_level)
        pct = int((passed / total_levels) * 100)
        return f"📈 <b>Статус взлома:</b> [{bar}] <b>Уровень {current_level}/{total_levels}</b>"


def render_heist_text(bet: float, current_level: int, current_mult: float, history: list, is_game_over: bool = False, won: bool = False, win_amount: float = 0.0, failed_tool: str = None) -> str:
    """Формирует текстовый интерфейс ограбления банка"""
    current_win = round(bet * current_mult, 2)

    text = "🕵️‍♂️ <b>ОГРАБЛЕНИЕ БАНКА «CENTRAL VAULT»</b>\n"
    text += f"💰 <b>Ставка:</b> <code>{bet:,.0f} n¢</code>\n"
    text += f"{render_progress_bar(current_level, 3, is_game_over, won)}\n"
    text += "✨ ━━━━━━━━━━━━━━━━━━━━ ✨\n"

    # История пройденных уровней
    if history:
        text += "<b>История операций:</b>\n"
        for idx, h in enumerate(history, 1):
            text += f"  • <b>Этап {idx}:</b> Использован {h['tool_name']} (Шанс {h['chance']}% | x{h['mult']:.2f}) ➔ ✅ <b>Успешно</b>\n"
        text += "───────────────────────\n"

    if is_game_over:
        if won:
            profit = win_amount - bet
            text += f"🎉 <b>ПОБЕДА! ВЫ ОЧИСТИЛИ ГЛАВНЫЙ ДЕПОЗИТАРИЙ!</b>\n"
            text += f"💵 <b>Забрано из сейфа:</b> <code>{win_amount:,.0f} n¢</code> (+<code>{profit:,.0f} n¢</code> / x{current_mult:.2f})\n"
            text += f"🚁 Вы успешно ушли от погони на вертолёте!"
        else:
            text += f"🚨 <b>СИГНАЛИЗАЦИЯ! ВАС ЗАПЕЛЕНГОВАЛА ОХРАНА!</b>\n"
            if failed_tool:
                text += f"⚠️ Инструмент <b>{failed_tool}</b> подвёл во время взлома!\n"
            text += f"👮‍♂️ ОМОН заблокировал выходы. Ставка <code>{bet:,.0f} n¢</code> конфискована."
    else:
        lvl_data = HEIST_LEVELS[current_level]
        text += f"📍 <b>{lvl_data['title']}</b>\n"
        text += f"💵 <b>Куш на кону:</b> <code>{current_win:,.0f} n¢</code> (Общий множитель: <b>x{current_mult:.2f}</b>)\n\n"
        text += "<b>Выберите инструмент для взлома:</b>\n"

        for key, tool in lvl_data["tools"].items():
            potential_mult = current_mult * tool["mult"]
            potential_win = round(bet * potential_mult, 2)
            text += (
                f"• {tool['name']} ➔ Шанс: <b>{tool['chance']}%</b> | Множитель: <b>x{tool['mult']:.2f}</b>\n"
                f"   <i>(При успехе: x{potential_mult:.2f} ➔ {potential_win:,.0f} n¢)</i>\n"
            )

    return text


def build_heist_keyboard(current_level: int, bet: float, current_mult: float) -> InlineKeyboardMarkup:
    """Генерирует кнопки выбора инструментов взлома и кнопку забора денег"""
    buttons = []
    lvl_data = HEIST_LEVELS[current_level]

    # Кнопки для каждого инструмента
    for key, tool in lvl_data["tools"].items():
        btn_text = f"{tool['name']} ({tool['chance']}% | x{tool['mult']:.2f})"
        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"heist_tool:{key}")
        ])

    # Кнопка «Забрать куш» доступна, начиная со 2-го уровня
    if current_level > 1:
        current_win = round(bet * current_mult, 2)
        profit = current_win - bet
        profit_pct = int((current_mult - 1.0) * 100)
        
        btn_text = f"💰 Забрать куш: {current_win:,.0f} n¢ (📊 +{profit_pct}% | +{profit:,.0f} n¢)"
        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data="heist_cashout")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# =====================================================================
# ХЕНДЛЕРЫ И ЛОГИКА
# =====================================================================

@router.message(Command("heist"))
@router.message(F.text.lower().startswith("ограбление"))
@router.message(F.text.lower().startswith("🏦 ограбление"))
async def cmd_heist_start(message: Message, state: FSMContext):
    """Старт игры / запрос ставки или запуск со ставкой из текста"""
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

    # Мгновенный запуск со ставкой из текста: "ограбление 100к", "/heist 50k"
    if bet_arg:
        bet = parse_bet_amount(bet_arg, user["balance"])
        if bet > 0:
            return await start_heist_game(message, state, bet)
        else:
            await message.answer("❌ Неверно указана сумма ставки. Попробуйте еще раз.")

    # Меню выбора пресетов ставки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10к n¢", callback_data="heist_preset:10k"),
            InlineKeyboardButton(text="100к n¢", callback_data="heist_preset:100k"),
            InlineKeyboardButton(text="1кк n¢", callback_data="heist_preset:1kk"),
        ],
        [
            InlineKeyboardButton(text="10кк n¢", callback_data="heist_preset:10kk"),
            InlineKeyboardButton(text="100ккк n¢", callback_data="heist_preset:100kkk"),
            InlineKeyboardButton(text="🔥 ALL-IN", callback_data="heist_preset:allin"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="heist_cancel")]
    ])

    caption_text = (
        f"🕵️‍♂️ <b>Добро пожаловать в «Ограбление Банка»!</b>\n\n"
        f"💰 <b>Ваш баланс:</b> <code>{user['balance']:,.0f} n¢</code>\n"
        f"🏆 Взломайте 3 уровня защиты хранилища и заберите куш до <b>x160.00</b>!\n\n"
        f"💡 <i>Вы можете запускать игру сразу командой:\n"
        f"<code>ограбление 100к</code> или <code>/heist 1кк</code></i>\n\n"
        f"👇 Выберите сумму ставки ниже или введите в чат:"
    )

    try:
        await message.answer_photo(
            photo=HEIST_BANNERS["welcome"],
            caption=caption_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        await message.answer(caption_text, reply_markup=kb, parse_mode="HTML")

    await state.set_state(HeistState.waiting_for_bet)


@router.callback_query(F.data.startswith("heist_preset:"), HeistState.waiting_for_bet)
async def process_preset_bet(call: CallbackQuery, state: FSMContext):
    """Обработка выбора кнопки пресета ставки"""
    preset = call.data.split(":")[1]
    user = db.get_user(call.from_user.id)

    bet = parse_bet_amount(preset, user["balance"])
    await start_heist_game(call, state, bet)


@router.message(HeistState.waiting_for_bet)
async def process_text_bet(message: Message, state: FSMContext):
    """Обработка текстового ввода суммы ставки"""
    user = db.get_user(message.from_user.id)
    bet = parse_bet_amount(message.text, user["balance"])

    if bet <= 0:
        return await message.answer("❌ Введите корректную сумму ставки (например: 10к, 100к, 1кк, 10кк, 100ккк).")

    await start_heist_game(message, state, bet)


async def start_heist_game(event, state: FSMContext, bet: float):
    """Инициализация и запуск нового ограбления"""
    user_id = event.from_user.id
    user = db.get_user(user_id)

    if bet < 10:
        text = "❌ Минимальная ставка: 10 n¢"
        return await event.answer(text) if isinstance(event, Message) else await event.answer(text, show_alert=True)

    if user["balance"] < bet:
        text = f"❌ Недостаточно средств! Ваш баланс: {user['balance']:,.0f} n¢"
        return await event.answer(text) if isinstance(event, Message) else await event.answer(text, show_alert=True)

    # Списываем баланс
    db.update_balance(user_id, -bet)

    game_data = {
        "bet": bet,
        "current_level": 1,
        "current_mult": 1.0,
        "history": []
    }

    await state.set_state(HeistState.playing)
    await state.update_data(game_data=game_data)

    text = render_heist_text(bet=bet, current_level=1, current_mult=1.0, history=[])
    kb = build_heist_keyboard(current_level=1, bet=bet, current_mult=1.0)

    if isinstance(event, Message):
        try:
            await event.answer_photo(
                photo=HEIST_BANNERS["playing"],
                caption=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        try:
            media = InputMediaPhoto(media=HEIST_BANNERS["playing"], caption=text, parse_mode="HTML")
            await event.message.edit_media(media=media, reply_markup=kb)
        except Exception:
            try:
                await event.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await event.message.answer_photo(
                    photo=HEIST_BANNERS["playing"],
                    caption=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )


@router.callback_query(F.data.startswith("heist_tool:"), HeistState.playing)
async def process_tool_choice(call: CallbackQuery, state: FSMContext):
    """Обработка выбора инструмента взлома"""
    tool_key = call.data.split(":")[1]
    data = await state.get_data()
    game = data.get("game_data")

    if not game:
        await call.answer("Игра завершена.", show_alert=True)
        return

    lvl = game["current_level"]
    bet = game["bet"]
    current_mult = game["current_mult"]
    
    lvl_info = HEIST_LEVELS[lvl]
    tool = lvl_info["tools"].get(tool_key)

    if not tool:
        await call.answer("Неверный инструмент!", show_alert=True)
        return

    # Проверка шанса взлома (генерация 1..100)
    roll = random.randint(1, 100)
    is_success = roll <= tool["chance"]

    if not is_success:
        # ПРОИГРЫШ: Сработала сигнализация
        db.add_stats(
            uid=call.from_user.id,
            is_lost=True,
            lost_amount=bet,
            bet_amount=bet,
            game_name="bank_heist",
            win_amount=0.0
        )
        await state.clear()

        text = render_heist_text(
            bet=bet,
            current_level=lvl,
            current_mult=current_mult,
            history=game["history"],
            is_game_over=True,
            won=False,
            failed_tool=tool["name"]
        )

        try:
            media = InputMediaPhoto(media=HEIST_BANNERS["lose"], caption=text, parse_mode="HTML")
            await call.message.edit_media(media=media)
        except Exception:
            try:
                await call.message.edit_caption(caption=text, parse_mode="HTML")
            except TelegramBadRequest:
                pass

        await call.answer(f"🚨 СИГНАЛИЗАЦИЯ! {tool['name']} подвел вас!", show_alert=True)
        return

    # УСПЕШНЫЙ ВЗЛОМ УРОВНЯ
    new_mult = current_mult * tool["mult"]
    game["current_mult"] = new_mult
    game["history"].append({
        "level": lvl,
        "tool_name": tool["name"],
        "chance": tool["chance"],
        "mult": tool["mult"]
    })

    # Если пройдён 3-й уровень -> ВЫИГРЫШ (ФИНАЛ)
    if lvl == 3:
        win_amount = round(bet * new_mult, 2)
        
        db.update_balance(call.from_user.id, win_amount)
        db.add_stats(
            uid=call.from_user.id,
            is_lost=False,
            lost_amount=0.0,
            bet_amount=bet,
            game_name="bank_heist",
            win_amount=win_amount
        )
        await state.clear()

        text = render_heist_text(
            bet=bet,
            current_level=3,
            current_mult=new_mult,
            history=game["history"],
            is_game_over=True,
            won=True,
            win_amount=win_amount
        )

        try:
            media = InputMediaPhoto(media=HEIST_BANNERS["win"], caption=text, parse_mode="HTML")
            await call.message.edit_media(media=media)
        except Exception:
            try:
                await call.message.edit_caption(caption=text, parse_mode="HTML")
            except TelegramBadRequest:
                pass

        await call.answer(f"🎉 БАНК ОГРАБЛЕН! Вы забираете {win_amount:,.0f} n¢!", show_alert=True)
    else:
        # Переход на следующий уровень
        game["current_level"] += 1
        await state.update_data(game_data=game)

        text = render_heist_text(
            bet=bet,
            current_level=game["current_level"],
            current_mult=new_mult,
            history=game["history"]
        )
        kb = build_heist_keyboard(
            current_level=game["current_level"],
            bet=bet,
            current_mult=new_mult
        )

        try:
            await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            pass

        await call.answer(f"Успех! {tool['name']} сработал! Переходим на Уровень {game['current_level']}!")


@router.callback_query(F.data == "heist_cashout", HeistState.playing)
async def process_cashout(call: CallbackQuery, state: FSMContext):
    """Игрок забирает куш и сбегает"""
    data = await state.get_data()
    game = data.get("game_data")

    if not game:
        await call.answer("Игра завершена.", show_alert=True)
        return

    lvl = game["current_level"]
    bet = game["bet"]

    if lvl <= 1:
        await call.answer("Сначала взломайте хотя бы 1 уровень!", show_alert=True)
        return

    current_mult = game["current_mult"]
    win_amount = round(bet * current_mult, 2)

    db.update_balance(call.from_user.id, win_amount)
    db.add_stats(
        uid=call.from_user.id,
        is_lost=False,
        lost_amount=0.0,
        bet_amount=bet,
        game_name="bank_heist",
        win_amount=win_amount
    )
    await state.clear()

    text = render_heist_text(
        bet=bet,
        current_level=lvl - 1,
        current_mult=current_mult,
        history=game["history"],
        is_game_over=True,
        won=True,
        win_amount=win_amount
    )

    try:
        media = InputMediaPhoto(media=HEIST_BANNERS["win"], caption=text, parse_mode="HTML")
        await call.message.edit_media(media=media)
    except Exception:
        try:
            await call.message.edit_caption(caption=text, parse_mode="HTML")
        except TelegramBadRequest:
            pass

    await call.answer(f"💰 Куш у вас! Забрано {win_amount:,.0f} n¢!", show_alert=True)


@router.callback_query(F.data == "heist_cancel")
async def process_cancel(call: CallbackQuery, state: FSMContext):
    """Отмена ограбления на этапе выбора ставки"""
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer("❌ Ограбление отменено.")
