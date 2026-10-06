# crash.py
import asyncio
import random
import hashlib
import secrets
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
import db
import utils

logger = logging.getLogger(__name__)
router = Router()

ACTIVE_CRASH_GAMES = {}  # {user_id: state}
RECENT_CRASHES = [1.12, 1.03, 1.40, 1.05, 1.20]  # История последних иксов (макс 10)
FAIR_CACHE = {}  # {fair_id: {"hash": str, "salt": str, "crash_point": float, "raw_str": str}}

# ==============================================================================
# 🎭 ТЕКСТОВЫЕ ЭМОДЗИ (Безопасны для всех пользователей)
# ==============================================================================
EMOJI_ROCKET = '<tg-emoji emoji-id="5780773956030043338">🚀</tg-emoji>'
EMOJI_SATELLITE = '<tg-emoji emoji-id="5467403607286502523">🛰</tg-emoji>'
E_PLANET = '<tg-emoji emoji-id="5453902218677739645">🪐</tg-emoji>'
EMOJI_GALAXY = '<tg-emoji emoji-id="6334445079284941997">🌌</tg-emoji>'
EMOJI_FIRE = '<tg-emoji emoji-id="5256047523620995497">🔥</tg-emoji>'
EMOJI_BOOM = '<tg-emoji emoji-id="5226813248900187912">💥</tg-emoji>'
EMOJI_SHIELD = '<tg-emoji emoji-id="5373173798633752502">🛡️</tg-emoji>'
EMOJI_MONEY = '<tg-emoji emoji-id="5990147899403539264">💰</tg-emoji>'
EMOJI_CARD = '<tg-emoji emoji-id="6280364500361155698">💳</tg-emoji>'
EMOJI_LIGHTNING = '<tg-emoji emoji-id="5989800724312101453">⚡</tg-emoji>'
EMOJI_STOP = '<tg-emoji emoji-id="5305381957524272531">🛑</tg-emoji>'
EMOJI_BACK = '<tg-emoji emoji-id="5253997076169115797">🔙</tg-emoji>'
EMOJI_CROSS = '<tg-emoji emoji-id="5454350746407419714">❌</tg-emoji>'
EMOJI_TADA = '<tg-emoji emoji-id="5989848973974704652">🎉</tg-emoji>'
EMOJI_GRAPH = '<tg-emoji emoji-id="5429463966432643712">📈</tg-emoji>'
EMOJI_BAR = '<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji>'
EMOJI_SCROLL = '<tg-emoji emoji-id="5388922215347534633">📜</tg-emoji>'
EMOJI_JOYSTICK = '<tg-emoji emoji-id="5350612670435313545">🕹️</tg-emoji>'
EMOJI_KEY = '<tg-emoji emoji-id="5469956488351025557">🔑</tg-emoji>'


def generate_crash_point() -> float:
    """
    Генерирует точку краша с повышенными шансами для обычных игроков.
    Чтобы исключить беспроигрышный абуз на x1.01, оставлен минимальный естественный 
    шанс мгновенного взрыва на x1.00 (всего 3%, как во всех классических Краш играх).
    Это математически предотвращает бесконечный фарм, но сохраняет игру честной и плавной.
    """
    global RECENT_CRASHES
    last_x = RECENT_CRASHES[-1] if RECENT_CRASHES else None

    # Защита от серий неудач: если прошлый раунд взорвался сразу, этот раунд гарантированно летит выше
    if last_x is not None and last_x <= 1.05:
        r = random.random()
        if r < 0.40:
            val = random.uniform(1.20, 1.60)
        elif r < 0.80:
            val = random.uniform(1.61, 3.00)
        else:
            val = random.uniform(3.01, 8.00)
        return round(val, 2)

    r = random.random()
    
    if r < 0.03:
        # Естественный моментальный краш 1.00x (3% шанс) - стандартная защита от 1.01-фермеров
        return 1.00
    elif r < 0.18:
        # Небольшие иксы (1.01 - 1.15)
        val = random.uniform(1.01, 1.15)
    elif r < 0.58:
        # Самая частая зона: отличный полет (1.16 - 2.00) - 40% шанс!
        val = random.uniform(1.16, 2.00)
    elif r < 0.83:
        # Крупный полет (2.01 - 4.50)
        val = random.uniform(2.01, 4.50)
    elif r < 0.95:
        # Мега-полет (4.51 - 10.00)
        val = random.uniform(4.51, 10.00)
    else:
        # Космический полет (10.01 - 30.00)
        val = random.uniform(10.01, 30.00)

    return round(val, 2)


def create_fair_game() -> tuple[float, str, str, str]:
    """Генерирует доказуемо честную игру SHA-256"""
    crash_point = generate_crash_point()
    salt = secrets.token_hex(16)
    raw_str = f"{crash_point:.2f}:{salt}"
    sha_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()
    fair_id = secrets.token_hex(8)

    FAIR_CACHE[fair_id] = {
        "hash": sha_hash,
        "salt": salt,
        "crash_point": crash_point,
        "raw_str": raw_str
    }

    if len(FAIR_CACHE) > 1000:
        oldest_key = next(iter(FAIR_CACHE))
        FAIR_CACHE.pop(oldest_key, None)

    return crash_point, sha_hash, salt, fair_id


def format_history() -> str:
    """Форматирует список последних коэффициентов взлета"""
    if not RECENT_CRASHES:
        return "История пуста"
    
    formatted = []
    for x in RECENT_CRASHES[-6:]:
        if x < 1.15:
            formatted.append(f"<code>[{x:.2f}x 🟥]</code>")
        elif x < 1.50:
            formatted.append(f"<code>[{x:.2f}x 🔴]</code>")
        elif x < 3.0:
            formatted.append(f"<code>[{x:.2f}x 🟢]</code>")
        elif x < 10.0:
            formatted.append(f"<code>[{x:.2f}x 🟨]</code>")
        else:
            formatted.append(f"<code>[{x:.2f}x 🟣]</code>")
    return " ".join(formatted)


def get_flight_visual(step: float, bet: float) -> str:
    """Генерирует динамический визуал полёта ракеты и прогресс-бар"""
    win_est = round(bet * step, 2)
    
    if step < 1.20:
        progress = int((step - 1.0) * 50)
        progress = min(10, max(0, progress))
        bar = "🟥" * progress + "⬜" * (10 - progress)
        status = f"{EMOJI_ROCKET} <b>Старт ракеты! Набор высоты...</b>"
    elif step < 2.0:
        progress = int((step - 1.2) * 12.5)
        progress = min(10, max(0, progress))
        bar = "🟩" * progress + "⬜" * (10 - progress)
        status = f"{EMOJI_ROCKET} <b>Ракета уверенно набирает высоту!</b>"
    elif step < 5.0:
        progress = int((step - 2.0) * 3.33)
        progress = min(10, max(0, progress))
        bar = "🟨" * progress + "⬜" * (10 - progress)
        status = f"{EMOJI_SATELLITE} <b>Выход в стратосферу!</b>"
    elif step < 10.0:
        progress = int((step - 5.0) * 2)
        progress = min(10, max(0, progress))
        bar = "🟦" * progress + "⬜" * (10 - progress)
        status = f"{E_PLANET} <b>ПРОЛЁТ МИМО ПЛАНЕТ! МЕГА-ИКС!</b>"
    else:
        bar = f"{EMOJI_FIRE}" * 10
        status = f"{EMOJI_GALAXY} <b>ГЛУБОКИЙ КОСМОС! СУПЕР ВЫИГРЫШ!</b>"

    return (
        f"{status}\n\n"
        f"{EMOJI_GRAPH} <b>Коэффициент:</b> <code>x{step:.2f}</code>\n"
        f"{EMOJI_BAR} <code>[{bar}]</code>\n\n"
        f"{EMOJI_MONEY} Выигрыш при остановке: <b>{win_est:,.0f} nCoin</b>"
    )


@router.callback_query(F.data == "crash_menu")
async def crash_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = db.get_user(callback.from_user.id)
    
    history_str = format_history()
    
    text = (
        f"{EMOJI_ROCKET} <b>ИГРА КРАШ (Crash)</b> {EMOJI_ROCKET}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите режим игры и сделайте ставку!\n\n"
        f"{EMOJI_SCROLL} <b>История иксов:</b> {history_str}\n"
        f"{EMOJI_CARD} <b>Ваш баланс:</b> <code>{user['balance']:,.0f} nCoin</code>\n\n"
        f"{EMOJI_JOYSTICK} <b>РЕЖИМЫ ИГРЫ:</b>\n"
        "1️⃣ <b>Реальный полет (с кнопкой СТОП):</b>\n"
        "   • <code>краш 1000</code> — ракета летит в реальном времени!\n\n"
        "2️⃣ <b>Мгновенный автовывод:</b>\n"
        "   • <code>краш 5000 1.15</code> — мгновенный расчет по иксу!\n"
        "   • <code>краш 5000 1.15 страховка</code> — мгновенно со страховкой\n\n"
        f"{EMOJI_LIGHTNING} <b>Быстрый запуск:</b> нажмите кнопку ниже"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🕹️ Полет: 1k", callback_data="quick_crash:1000:manual"),
            InlineKeyboardButton(text="🕹️ Полет: 5k", callback_data="quick_crash:5000:manual")
        ],
        [
            InlineKeyboardButton(text="⚡ Мгновенно: 1k (x1.10)", callback_data="quick_crash:1000:1.10"),
            InlineKeyboardButton(text="⚡ Мгновенно: 5k (x1.10)", callback_data="quick_crash:5000:1.10")
        ],
        [
            InlineKeyboardButton(text="🛡️ Мгновенно со страховкой (1k x1.10)", callback_data="quick_crash:1000:1.10:ins")
        ],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="games_menu")]
    ])
    
    msg = callback.message
    if msg.photo:
        try:
            await msg.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await msg.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        try:
            await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("quick_crash:"))
async def quick_crash_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    bet_val = float(parts[1])
    mode = parts[2]
    has_insurance = len(parts) > 3 and parts[3] == "ins"
    
    target_x = None if mode == "manual" else float(mode)
        
    await process_crash_start(
        event=callback,
        user_id=callback.from_user.id,
        bet=bet_val,
        target_x=target_x,
        has_insurance=has_insurance,
        chat_id=callback.message.chat.id
    )


@router.message(F.text.lower().startswith("краш"))
async def crash_text_cmd(message: Message, state: FSMContext):
    await state.clear()
    parts = message.text.lower().split()
    
    if len(parts) < 2 or len(parts) > 4:
        await message.answer(
            f"{EMOJI_CROSS} <b>Неверный формат!</b>\n\n"
            "• <code>краш 1000</code> — Полет в реальном времени с кнопкой СТОП\n"
            "• <code>краш 1000 1.15</code> — Мгновенный расчет на x1.15\n"
            "• <code>краш 1000 1.15 страховка</code> — Мгновенно со страховкой",
            parse_mode="HTML"
        )
        return
        
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    bet = utils.parse_bet_input(parts[1], user["balance"])
    if bet <= 0:
        await message.answer(f"{EMOJI_CROSS} Неверный формат ставки!", parse_mode="HTML")
        return
        
    target_x = None
    has_insurance = False
    
    if len(parts) >= 3:
        if parts[2] in ["страховка", "страх", "shield"]:
            has_insurance = True
        else:
            try:
                target_x = float(parts[2].replace(",", "."))
                if target_x <= 1.00:
                    raise ValueError
            except ValueError:
                await message.answer(f"{EMOJI_CROSS} Коэффициент автовывода должен быть больше 1.00!", parse_mode="HTML")
                return
                
    if len(parts) == 4 and parts[3] in ["страховка", "страх", "shield"]:
        has_insurance = True
        
    await process_crash_start(
        event=message,
        user_id=user_id,
        bet=bet,
        target_x=target_x,
        has_insurance=has_insurance,
        chat_id=message.chat.id
    )


async def process_crash_start(event, user_id: int, bet: float, target_x: float, has_insurance: bool, chat_id: int):
    user = db.get_user(user_id)
    
    insurance_cost = round(bet * 0.10, 2) if has_insurance else 0.0
    total_deduction = bet + insurance_cost
    
    if user["balance"] < total_deduction:
        cost_info = f" ({bet:,.0f} ставка + {insurance_cost:,.0f} страховка)" if has_insurance else ""
        msg_text = f"{EMOJI_CROSS} Недостаточно nCoin! Требуется: {total_deduction:,.0f}{cost_info}"
        if isinstance(event, CallbackQuery):
            await event.answer(msg_text, show_alert=True)
        else:
            await event.answer(msg_text)
        return

    if target_x is not None:
        await start_instant_crash(event, user_id, bet, target_x, has_insurance, insurance_cost, total_deduction)
    else:
        await start_manual_flight_crash(event, user_id, bet, has_insurance, insurance_cost, total_deduction, chat_id)


async def start_instant_crash(event, user_id: int, bet: float, target_x: float, has_insurance: bool, insurance_cost: float, total_deduction: float):
    db.update_balance(user_id, -total_deduction)
    
    crash_point, sha_hash, salt, fair_id = create_fair_game()

    RECENT_CRASHES.append(crash_point)
    if len(RECENT_CRASHES) > 10:
        RECENT_CRASHES.pop(0)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Честность", callback_data=f"crash_fair:{fair_id}")]
    ])

    if crash_point >= target_x:
        win_amount = round(bet * target_x, 2)
        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)
        user_updated = db.get_user(user_id)
        
        ins_str = f" {EMOJI_SHIELD} [Страховка]" if has_insurance else ""
        res_text = (
            f"{EMOJI_LIGHTNING} <b>БЫСТРЫЙ КРАШ</b> {EMOJI_LIGHTNING}{ins_str}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{EMOJI_TADA} <b>УСПЕШНЫЙ АВТОВЫВОД!</b>\n"
            f"{EMOJI_ROCKET} Ваша цель: <b>x{target_x:.2f}</b> (Взрыв произошел на x{crash_point:.2f})\n"
            f"{EMOJI_MONEY} Выигрыш: <b>+{win_amount:,.0f} nCoin</b>\n\n"
            f"{EMOJI_CARD} Ваш баланс: <b>{user_updated['balance']:,.0f} nCoin</b>"
        )
    else:
        ins_msg = ""
        if has_insurance and crash_point < 1.10:
            insurance_payout = bet
            db.update_balance(user_id, insurance_payout)
            ins_msg = f"\n{EMOJI_SHIELD} <b>Сработала страховка!</b> Вам возвращено <b>{insurance_payout:,.0f} nCoin</b>!"
            db.add_stats(user_id, is_lost=False, bet_amount=bet)
        else:
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
            
        user_updated = db.get_user(user_id)
        
        res_text = (
            f"{EMOJI_LIGHTNING} <b>БЫСТРЫЙ КРАШ</b> {EMOJI_LIGHTNING}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{EMOJI_BOOM} <b>РАКЕТА ВЗОРВАЛАСЬ!</b>\n"
            f"{EMOJI_BOOM} Взрыв произошел на: <b>x{crash_point:.2f}</b> (Цель была: x{target_x:.2f})\n"
            f"💸 Потеря ставки: <b>-{bet:,.0f} nCoin</b>{ins_msg}\n\n"
            f"{EMOJI_CARD} Ваш баланс: <b>{user_updated['balance']:,.0f} nCoin</b>"
        )

    if isinstance(event, CallbackQuery):
        await event.message.answer(res_text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(res_text, reply_markup=kb, parse_mode="HTML")


async def start_manual_flight_crash(event, user_id: int, bet: float, has_insurance: bool, insurance_cost: float, total_deduction: float, chat_id: int):
    if user_id in ACTIVE_CRASH_GAMES:
        msg = f"{EMOJI_CROSS} У вас уже запущена игра Краш!"
        if isinstance(event, CallbackQuery):
            await event.answer(msg, show_alert=True)
        else:
            await event.answer(msg)
        return
        
    db.update_balance(user_id, -total_deduction)
    
    crash_point, sha_hash, salt, fair_id = create_fair_game()
            
    ACTIVE_CRASH_GAMES[user_id] = {
        "bet": bet,
        "has_insurance": has_insurance,
        "insurance_cost": insurance_cost,
        "crash_point": crash_point,
        "fair_id": fair_id,
        "sha_hash": sha_hash,
        "current_x": 1.00,
        "status": "flying",
        "message_id": None
    }
    
    ins_badge = f" {EMOJI_SHIELD} [Страховка активна]" if has_insurance else ""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 СТОП! (Подготовка...)", callback_data=f"crash_stop:{user_id}")]
    ])
    
    start_text = f"{EMOJI_ROCKET} <b>Ракета готовится к взлёту...</b>{ins_badge}"
    
    if isinstance(event, CallbackQuery):
        start_msg = await event.message.answer(start_text, reply_markup=kb, parse_mode="HTML")
    else:
        start_msg = await event.answer(start_text, reply_markup=kb, parse_mode="HTML")
        
    ACTIVE_CRASH_GAMES[user_id]["message_id"] = start_msg.message_id
    
    asyncio.create_task(run_crash_flight(user_id, event.bot, chat_id))


async def run_crash_flight(user_id: int, bot: Bot, chat_id: int):
    game = ACTIVE_CRASH_GAMES.get(user_id)
    if not game:
        return
    
    message_id = game["message_id"]
    bet = game["bet"]
    has_insurance = game["has_insurance"]
    ins_text = f"\n{EMOJI_SHIELD} <b>Страховка активна</b>" if has_insurance else ""

    countdown_steps = [
        ("3️⃣", "⏳ <b>Готовность 3 секунды...</b>"),
        ("2️⃣", "⏳ <b>Готовность 2 секунды...</b>"),
        ("1️⃣", "🚀 <b>Запуск двигателей! 1...</b>")
    ]
    
    for badge, status_msg in countdown_steps:
        game = ACTIVE_CRASH_GAMES.get(user_id)
        if not game or game["status"] != "flying":
            return
            
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🛑 СТОП! {badge}", callback_data=f"crash_stop:{user_id}")]
        ])
        
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{EMOJI_ROCKET} {status_msg}{ins_text}",
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            pass
        await asyncio.sleep(0.5)

    current_x = 1.00
    crash_point = game["crash_point"]
    
    steps = []
    if crash_point > 1.00:
        while current_x < crash_point:
            if current_x < 1.15:
                inc = round(random.uniform(0.01, 0.03), 2)
            elif current_x < 2.00:
                inc = round(random.uniform(0.04, 0.10), 2)
            else:
                inc = round(random.uniform(0.12, 0.28), 2)

            current_x = round(current_x + inc, 2)
            if current_x >= crash_point:
                break
            steps.append(current_x)
        
    for step in steps:
        await asyncio.sleep(0.6)
        
        game = ACTIVE_CRASH_GAMES.get(user_id)
        if not game or game["status"] != "flying":
            return
            
        game["current_x"] = step
        win_est = round(bet * step, 2)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🛑 СТОП! Забрать {win_est:,.0f} n¢ (x{step:.2f})", callback_data=f"crash_stop:{user_id}")]
        ])
        
        visual_text = get_flight_visual(step, bet)
        
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{visual_text}{ins_text}",
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            pass
            
    # Взрыв ракеты в реальном времени 💥
    await asyncio.sleep(0.6)
    game = ACTIVE_CRASH_GAMES.get(user_id)
    if game and game["status"] == "flying":
        game["status"] = "crashed"
        
        RECENT_CRASHES.append(crash_point)
        if len(RECENT_CRASHES) > 10:
            RECENT_CRASHES.pop(0)
            
        ins_msg = ""
        if has_insurance and crash_point < 1.10:
            insurance_payout = bet
            db.update_balance(user_id, insurance_payout)
            ins_msg = f"\n\n{EMOJI_SHIELD} <b>Сработала страховка!</b> Вам возвращено <b>{insurance_payout:,.0f} nCoin</b>!"
            db.add_stats(user_id, is_lost=False, bet_amount=bet)
        else:
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
            
        user_updated = db.get_user(user_id)
        fair_id = game["fair_id"]

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Честность", callback_data=f"crash_fair:{fair_id}")]
        ])
        
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=(
                    f"{EMOJI_BOOM} <b>РАКЕТА ВЗОРВАЛАСЬ!</b> {EMOJI_BOOM}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{EMOJI_BOOM} Взрыв произошел на: <b>x{crash_point:.2f}</b>\n"
                    f"💸 Потеря ставки: <b>-{bet:,.0f} nCoin</b>{ins_msg}\n\n"
                    f"{EMOJI_CARD} Ваш баланс: <b>{user_updated['balance']:,.0f} nCoin</b>"
                ),
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            pass
            
        del ACTIVE_CRASH_GAMES[user_id]


@router.callback_query(F.data.startswith("crash_stop:"))
async def crash_stop_callback(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ Это не ваша игра!", show_alert=True)
        return
        
    game = ACTIVE_CRASH_GAMES.get(user_id)
    if not game or game["status"] != "flying":
        await callback.answer("❌ Игра уже завершена или обрабатывается!")
        return
        
    game["status"] = "won"
    await callback.answer("🎯 Остановка полета!")
    
    current_x = game["current_x"]
    bet = game["bet"]
    win_amount = round(bet * current_x, 2)
    fair_id = game["fair_id"]
    
    RECENT_CRASHES.append(game["crash_point"])
    if len(RECENT_CRASHES) > 10:
        RECENT_CRASHES.pop(0)
        
    db.update_balance(user_id, win_amount)
    db.add_stats(user_id, is_lost=False, bet_amount=bet)
    user_updated = db.get_user(user_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Честность", callback_data=f"crash_fair:{fair_id}")]
    ])

    text = (
        f"{EMOJI_TADA} <b>УСПЕШНЫЙ ВЫВОД!</b> {EMOJI_TADA}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 Вы остановили ракету на: <b>x{current_x:.2f}</b>\n"
        f"{EMOJI_BOOM} Взрыв произошел на: <b>x{game['crash_point']:.2f}</b>\n"
        f"{EMOJI_MONEY} Выигрыш: <b>+{win_amount:,.0f} nCoin</b>\n\n"
        f"{EMOJI_CARD} Ваш баланс: <b>{user_updated['balance']:,.0f} nCoin</b>"
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    
    if user_id in ACTIVE_CRASH_GAMES:
        del ACTIVE_CRASH_GAMES[user_id]


# ==============================================================================
# 🔑 ЧЕСТНОСТЬ РАУНДА — РЕДАКТИРОВАНИЕ ИСХОДНОГО СООБЩЕНИЯ
# ==============================================================================

import html
import logging
from aiogram.filters import StateFilter

logger = logging.getLogger(__name__)


@router.callback_query(
    F.data.startswith("crash_fair:"),
    StateFilter("*")
)
async def crash_fair_callback(callback: CallbackQuery):
    try:
        await callback.answer()

        parts = callback.data.split(":", 1)

        if len(parts) != 2 or not parts[1]:
            await callback.answer("❌ Некорректный ID раунда.", show_alert=True)
            return

        fair_id = parts[1]
        fair_data = FAIR_CACHE.get(fair_id)

        if not fair_data:
            await callback.answer("❌ Данные раунда устарели или были удалены.", show_alert=True)
            return

        raw_str = str(fair_data["raw_str"])
        sha_hash = str(fair_data["hash"])
        crash_point = float(fair_data["crash_point"])

        safe_raw_str = html.escape(raw_str)
        safe_hash = html.escape(sha_hash)

        text = (
            "🚀 <b>Краш · Честность</b> 🔑\n"
            "· · · · · · · · · · · ·\n\n"
            "🔢 <b>SHA-256 Хэш:</b>\n"
            f"<code>{safe_hash}</code>\n\n"
            f"🔑 <b>Результат:</b> <code>{safe_raw_str}</code>\n\n"
            "<blockquote>"
            f"Число перед двоеточием указывает на результат ракеты "
            f"(x{crash_point:.2f}). Скопируйте строку результата и вставьте "
            "её на любом сайте, поддерживающем SHA-256. Полученный хэш должен "
            "совпасть с указанным выше."
            "</blockquote>"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data=f"crash_fair_back:{fair_id}"
                    ),
                    InlineKeyboardButton(
                        text="Честность 🔑",
                        url="https://emn178.github.io/online-tools/"
                    )
                ]
            ]
        )

        message = callback.message

        if not message:
            await callback.answer("❌ Сообщение недоступно.", show_alert=True)
            return

        if message.photo:
            await message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as error:
        logger.exception("Ошибка при открытии честности раунда: %s", error)


# ==============================================================================
# ◀️ ВОЗВРАТ К РЕЗУЛЬТАТУ ИГРЫ
# ==============================================================================

@router.callback_query(
    F.data.startswith("crash_fair_back:"),
    StateFilter("*")
)
async def crash_fair_back_callback(callback: CallbackQuery):
    try:
        await callback.answer()

        parts = callback.data.split(":", 1)

        if len(parts) != 2 or not parts[1]:
            await callback.answer("❌ Некорректный ID раунда.", show_alert=True)
            return

        fair_id = parts[1]
        fair_data = FAIR_CACHE.get(fair_id)

        if not fair_data:
            await callback.answer("❌ Данные раунда устарели.", show_alert=True)
            return

        crash_point = float(fair_data["crash_point"])
        message = callback.message

        if not message:
            await callback.answer("❌ Сообщение недоступно.", show_alert=True)
            return

        text = (
            "💥 <b>РАКЕТА ВЗОРВАЛАСЬ!</b> 💥\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💥 Взрыв произошёл на: <b>x{crash_point:.2f}</b>\n\n"
            "Нажмите кнопку «Честность», чтобы проверить SHA-256 раунда."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔑 Честность",
                        callback_data=f"crash_fair:{fair_id}"
                    )
                ]
            ]
        )

        if message.photo:
            await message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as error:
        logger.exception("Ошибка возврата из честности: %s", error)
