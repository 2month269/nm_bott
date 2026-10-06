# hypercar.py
import random
import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import db
import utils

router = Router()

class HypercarStates(StatesGroup):
    playing = State()
    police_chase = State()

# Характеристики автомобилей (ПОДРЕЗАНЫ ШАНСЫ И ДОХОДНОСТЬ)
CARS = {
    "offroad": {
        "name": "🚙 Внедорожник (Танк)",
        "desc": "🛡️ Прочный и экономный. Медленнее рост иксов, но риск аварии минимален.",
        "gas_max": 5.0,
        "cond_max": 5.0,
        "growth": 0.0010,   # Урезано с 0.004
        "crash_mult": 1.2,  # Увеличено с 0.5
        "speed": "90 км/ч"
    },
    "sport": {
        "name": "🏎️ Спорткар (Баланс)",
        "desc": "⚖️ Оптимальное сочетание скорости, расхода и доходности.",
        "gas_max": 4.0,
        "cond_max": 4.0,
        "growth": 0.0015,   # Урезано с 0.006
        "crash_mult": 1.8,  # Увеличено с 1.0
        "speed": "120 км/ч"
    },
    "dragster": {
        "name": "🏎️💨 Драгстер (Монстр)",
        "desc": "🔥 Бешеный рост иксов! Но высокий износ и повышенная опасность.",
        "gas_max": 3.0,
        "cond_max": 3.0,
        "growth": 0.0030,   # Урезано с 0.012
        "crash_mult": 2.5,  # Увеличено с 1.4
        "speed": "200 км/ч"
    }
}

USER_CARS = {} # {user_id: car_key} -> по умолчанию "sport"

def get_user_car(user_id: int) -> str:
    return USER_CARS.get(user_id, "sport")

def get_bar(val: float, max_val: float = 5.0, length: int = 8) -> str:
    """Генерирует аккуратную графическую шкалу прогресса"""
    val = max(0.0, min(max_val, val))
    filled_chars = int(round((val / max_val) * length))
    filled_chars = max(0, min(length, filled_chars))
    return "🟩" * filled_chars + "⬜" * (length - filled_chars)

def get_game_kb(nitro_charges: int = 2) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🛑 СТОП (Забрать выигрыш)", callback_data="hc_stop")]
    ]
    if nitro_charges > 0:
        buttons[0].append(InlineKeyboardButton(text=f"🚀 НИТРО ({nitro_charges})", callback_data="hc_nitro"))
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_police_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛑 СДАТЬСЯ (Забрать куш)", callback_data="hc_police_surrender"),
            InlineKeyboardButton(text="🏎️ ОТРВАТЬСЯ (Риск!)", callback_data="hc_police_escape")
        ]
    ])

def get_garage_kb(current_car: str) -> InlineKeyboardMarkup:
    buttons = []
    for car_key, car_info in CARS.items():
        prefix = "✅ " if car_key == current_car else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{prefix}{car_info['name']}", 
                callback_data=f"hc_select_car:{car_key}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="hypercar_menu_inline")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡ 1k", callback_data="hc_quick:1000"),
            InlineKeyboardButton(text="⚡ 5k", callback_data="hc_quick:5000"),
            InlineKeyboardButton(text="⚡ 10k", callback_data="hc_quick:10000")
        ],
        [InlineKeyboardButton(text="🏎️ Гараж (Выбор машины)", callback_data="hc_garage")],
        [InlineKeyboardButton(text="🔙 В меню игр", callback_data="games_menu")]
    ])

# Menu inline
@router.callback_query(F.data == "hypercar_menu_inline")
async def hypercar_menu_inline_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = db.get_user(callback.from_user.id)
    car_key = get_user_car(callback.from_user.id)
    car_info = CARS[car_key]
    
    text = (
        "🏎️ *Игра ГИПЕРКАР (Hypercar)* 🏎️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Ваша задача — проехать как можно дальше на скоростном болиде!\n"
        f"🚘 *Выбранный болид:* {car_info['name']}\n"
        f"ℹ️ _{car_info['desc']}_\n\n"
        "🔥 *Фичи в заезде:*\n"
        "• 🚀 *Кнопка НИТРО:* мгновенный рывок вперед (высокий риск взрыва!)\n"
        "• 🚨 *Погоня полиции:* шанс оторваться с кушем!\n"
        "• 🎲 *События:* канистры, проколы шин, масло.\n\n"
        f"💳 Твой баланс: *{user['balance']:,} nCoin*\n\n"
        "✍️ *Команды для старта:* `гиперкар <ставка>` или `гмп <ставка>`\n"
        "Например: `гиперкар 10к` или `гмп все`"
    )
    
    msg = callback.message
    if msg.photo:
        try:
            await msg.edit_caption(caption=text, reply_markup=get_menu_kb(), parse_mode="Markdown")
        except Exception:
            await msg.answer(text, reply_markup=get_menu_kb(), parse_mode="Markdown")
    else:
        try:
            await msg.edit_text(text, reply_markup=get_menu_kb(), parse_mode="Markdown")
        except Exception:
            await msg.answer(text, reply_markup=get_menu_kb(), parse_mode="Markdown")

# Garage callback
@router.callback_query(F.data == "hc_garage")
async def hc_garage_callback(callback: CallbackQuery):
    await callback.answer()
    car_key = get_user_car(callback.from_user.id)
    
    text = (
        "🏎️ *ГАРАЖ ГИПЕРКАРОВ* 🏎️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Выберите болид для заездов:\n\n"
    )
    for k, v in CARS.items():
        text += f"• *{v['name']}*\n  _{v['desc']}_\n  🚀 Скорость: {v['speed']} | ⛽ Бак: {v['gas_max']}\n\n"
        
    await callback.message.edit_text(text, reply_markup=get_garage_kb(car_key), parse_mode="Markdown")

@router.callback_query(F.data.startswith("hc_select_car:"))
async def hc_select_car_callback(callback: CallbackQuery):
    car_key = callback.data.split(":")[1]
    if car_key in CARS:
        USER_CARS[callback.from_user.id] = car_key
        await callback.answer(f"Выбран: {CARS[car_key]['name']}", show_alert=True)
    await hc_garage_callback(callback)

@router.callback_query(F.data.startswith("hc_quick:"))
async def quick_start_hypercar(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bet = float(callback.data.split(":")[1])
    await start_hypercar_game(callback.message, state, callback.from_user.id, bet, is_callback=True)

@router.message(StateFilter(None), F.text, F.text.lower().startswith(("гиперкар", "гмп")))
async def handle_hypercar_commands(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    parts = message.text.strip().split()
    if len(parts) < 2:
        car_key = get_user_car(user_id)
        car_info = CARS[car_key]
        await message.answer(
            "🏎️ *Игра ГИПЕРКАР (Hypercar)* 🏎️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🚘 *Текущий болид:* {car_info['name']}\n"
            "⛽ Тратится бензин, а износ увеличивается.\n"
            "🚀 Используйте НИТРО и уходите от ПОЛИЦИИ!\n\n"
            f"💳 Ваш баланс: *{user['balance']:,} nCoin*\n\n"
            "✍️ *Для запуска напишите:* `гиперкар <ставка>` или `гмп <ставка>`\n"
            "Или выберите быстрый старт ниже:",
            reply_markup=get_menu_kb(),
            parse_mode="Markdown"
        )
        return

    bet_str = parts[1]
    
    try:
        bet = utils.parse_bet_input(bet_str, user["balance"])
    except Exception:
        try:
            bet = utils.parse_bet_input(bet_str)
        except Exception:
            await message.answer("❌ Ошибка распознавания ставки!")
            return

    await start_hypercar_game(message, state, user_id, bet, is_callback=False)

async def start_hypercar_game(message_obj: Message, state: FSMContext, user_id: int, bet: float, is_callback: bool = False):
    user = db.get_user(user_id)
    
    if bet <= 0:
        await message_obj.answer("❌ Ставка должна быть больше 0!")
        return

    if user["balance"] < bet:
        await message_obj.answer(f"❌ Недостаточно nCoin! Ваш баланс: *{user['balance']:,} nCoin*", parse_mode="Markdown")
        return

    db.update_balance(user_id, -bet)

    car_key = get_user_car(user_id)
    car_info = CARS[car_key]

    gas = car_info["gas_max"]
    condition = car_info["cond_max"]
    meters = 0.0

    await state.update_data(
        bet=bet,
        car_key=car_key,
        gas=gas,
        condition=condition,
        meters=meters,
        nitro_charges=2,
        police_triggered=False,
        status="running",
        is_processing=False
    )
    await state.set_state(HypercarStates.playing)

    gas_bar = get_bar(gas, car_info["gas_max"])
    cond_bar = get_bar(condition, car_info["cond_max"])

    text = (
        f"🏎️ *{car_info['name'].upper()} СТАРТУЕТ!* 🏎️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 Множитель: *x1.0000* (+0.00%)\n"
        f"📏 Дистанция: *0.0 метров*\n"
        f"🛑 Скорость: *{car_info['speed']}*\n\n"
        f"⛽ Бензин: `{gas_bar}` ({gas:.1f}/{car_info['gas_max']})\n"
        f"🔧 Состояние: `{cond_bar}` ({condition:.1f}/{car_info['cond_max']})\n"
        f"📢 *Событие:* 🚦 _Зеленый свет! Газ в пол!_\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛣️  |--🏎️-------🌲--|  🏁\n\n"
        f"⚠️ Жмите **СТОП** или используйте **НИТРО**!"
    )

    game_message = await message_obj.answer(text, reply_markup=get_game_kb(2), parse_mode="Markdown")

    tick_count = 0
    current_event_text = "🚦 _Старт заезда!_"

    # Игровой цикл
    while True:
        await asyncio.sleep(2.0)
        
        current_data = await state.get_data()
        if not current_data or current_data.get("status") != "running":
            break

        tick_count += 1
        car_key = current_data.get("car_key", "sport")
        car_info = CARS[car_key]

        if current_data.get("status") == "police":
            break

        tick_meters = round(random.uniform(15.0, 25.0), 1)
        meters = round(current_data.get("meters") + tick_meters, 1)
        # Увеличен расход топлива и износ
        gas = round(current_data.get("gas") - random.uniform(0.5, 0.9), 1)
        condition = round(current_data.get("condition") - random.uniform(0.3, 0.6), 1)
        nitro_charges = current_data.get("nitro_charges", 2)

        # --- СОБЫТИЕ: ПОЛИЦЕЙСКАЯ ПОГОНЯ (Шанс повышен до 35%) ---
        police_triggered = current_data.get("police_triggered", False)
        if not police_triggered and tick_count >= 2 and random.random() < 0.35:
            await state.update_data(
                meters=meters, gas=gas, condition=condition, 
                status="police", police_triggered=True
            )
            await state.set_state(HypercarStates.police_chase)
            
            multiplier = 1.0 + (meters * car_info["growth"])
            win_current = round(bet * multiplier, 2)
            
            police_text = (
                f"🚨 *ПОЛИЦЕЙСКАЯ ПОГОНЯ!* 🚨\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🚔 Сзади пристроился патрульный болид с мигалками!\n"
                f"📢 *«Прижмитесь к обочине или мы откроем огонь!»*\n\n"
                f"📏 Пройдено: *{meters:.1f} м* | 💰 Куш: *{win_current:,} nCoin*\n\n"
                f"🔥 *ВАШ ВЫБОР:* Сдаться с миром или попробовать оторваться?"
            )
            try:
                await game_message.edit_text(police_text, reply_markup=get_police_kb(), parse_mode="Markdown")
            except Exception: pass
            break

        # --- СЛУЧАЙНЫЕ СОБЫТИЯ (Перекос в сторону негатива) ---
        if random.random() < 0.40:
            event_type = random.choice([
                "flat_tire", "oil_slick", "flat_tire", "oil_slick", "fuel_canister"
            ])

            if event_type == "flat_tire":
                condition = round(max(0.1, condition - 1.2), 1)
                current_event_text = "🛞 *Прокол колеса!* Состояние *-1.2*"
            elif event_type == "fuel_canister":
                gas = round(min(car_info["gas_max"], gas + 0.4), 1)
                current_event_text = "⛽ *Маленькая канистра!* Топливо *+0.4*"
            elif event_type == "oil_slick":
                condition = round(max(0.1, condition - 1.0), 1)
                current_event_text = "⚠️ *Масляное пятно!* Состояние *-1.0*"
        else:
            current_event_text = "🟢 _Трасса чистая, болид мчится ровно_"

        # --- АВАРИЯ (Сильно повышен шанс краша) ---
        defect = max(0.0, (car_info["cond_max"] * 0.9) - condition)
        crash_chance = (0.18 + (defect * 0.25)) * car_info["crash_mult"]

        if random.random() < crash_chance:
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
            await state.clear()
            
            try:
                await game_message.edit_text(
                    f"💥 *КРАШ-ТЕСТ НА ТРАССЕ!* 💥\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏎️ {car_info['name']} потерял управление!\n\n"
                    f"📏 Пройдено: *{meters:.1f} метров*\n"
                    f"💸 Потеря ставки: *-{bet:,} nCoin*\n\n"
                    f"💳 Твой баланс: *{db.get_user(user_id)['balance']:,} nCoin*",
                    parse_mode="Markdown"
                )
            except Exception: pass
            break

        # Закончился бензин
        if gas <= 0:
            gas = 0.0
            multiplier = 1.0 + (meters * car_info["growth"])
            win_amount = round(bet * multiplier, 2)
            
            db.update_balance(user_id, win_amount)
            db.add_stats(user_id, is_lost=False, bet_amount=bet)
            await state.clear()
            
            try:
                await game_message.edit_text(
                    f"⛽ *БАК ПУСТ!* ⛽\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏎️ Ваш болид плавно докатился до обочины.\n\n"
                    f"📏 Дистанция: *{meters:.1f} метров*\n"
                    f"📈 Множитель: *x{multiplier:.4f}*\n"
                    f"💰 Выигрыш: *+{win_amount:,} nCoin*\n\n"
                    f"💳 Ваш баланс: *{db.get_user(user_id)['balance']:,} nCoin*",
                    parse_mode="Markdown"
                )
            except Exception: pass
            break

        await state.update_data(meters=meters, gas=gas, condition=condition)

        multiplier = 1.0 + (meters * car_info["growth"])
        gas_bar = get_bar(gas, car_info["gas_max"])
        cond_bar = get_bar(condition, car_info["cond_max"])

        road_animations = [
            "🛣️  |--🏎️----🌲--|  🏁",
            "🛣️  |---🏎️--🌲---|  🏁",
            "🛣️  |-🌲--🏎️-----|  🏁",
            "🛣️  |--🌲--🏎️----|  🏁",
            "🛣️  |-----🌲🏎️---|  🏁"
        ]
        road_frame = road_animations[tick_count % len(road_animations)]
        win_current = round(bet * multiplier, 2)

        text = (
            f"🏎️ *{car_info['name'].upper()} МЧИТСЯ!* 🏎️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Множитель: *x{multiplier:.4f}*\n"
            f"💰 Текущий куш: *{win_current:,} nCoin*\n"
            f"📏 Дистанция: *{meters:.1f} метров*\n\n"
            f"⛽ Бензин: `{gas_bar}` ({gas:.1f}/{car_info['gas_max']})\n"
            f"🔧 Состояние: `{cond_bar}` ({condition:.1f}/{car_info['cond_max']})\n"
            f"📢 *Событие:* {current_event_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{road_frame}\n\n"
            f"⚠️ Жмите **СТОП** или **НИТРО**!"
        )

        try:
            await game_message.edit_text(text, reply_markup=get_game_kb(nitro_charges), parse_mode="Markdown")
        except Exception: pass

# --- ОБРАБОТКА КНОПКИ НИТРО ---
@router.callback_query(HypercarStates.playing, F.data == "hc_nitro")
async def nitro_hypercar_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data or data.get("status") != "running" or data.get("is_processing"):
        await callback.answer()
        return

    await state.update_data(is_processing=True)

    try:
        nitro_charges = data.get("nitro_charges", 0)
        if nitro_charges <= 0:
            await state.update_data(is_processing=False)
            await callback.answer("❌ Заряды закиси азота закончились!", show_alert=True)
            return

        # Риск нитро: ШАНС ВЗРЫВА 70% (Было 20%)
        if random.random() < 0.70:
            user_id = callback.from_user.id
            bet = data.get("bet")
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
            await state.clear()
            
            await callback.answer("💥 ВЗРЫВ НИТРО!", show_alert=True)
            try:
                await callback.message.edit_text(
                    f"🔥 *ВЗРЫВ СИСТЕМЫ НИТРО!* 🔥\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Двигатель не выдержал максимальной нагрузки и взорвался!\n\n"
                    f"💸 Потеря ставки: *-{bet:,} nCoin*\n"
                    f"💳 Ваш баланс: *{db.get_user(callback.from_user.id)['balance']:,} nCoin*",
                    parse_mode="Markdown"
                )
            except Exception: pass
            return

        # Успешный впрыск азота: даёт всего +15..25 метров
        boost_meters = round(random.uniform(15.0, 25.0), 1)
        new_meters = round(data.get("meters") + boost_meters, 1)
        new_charges = nitro_charges - 1

        await state.update_data(meters=new_meters, nitro_charges=new_charges, is_processing=False)
        await callback.answer(f"🚀 ВПРЫСК НИТРО! +{boost_meters} м!", show_alert=False)

    except Exception as e:
        await state.update_data(is_processing=False)
        logging.error(f"Error in nitro_hypercar_callback: {e}", exc_info=True)

# --- ОБРАБОТКА ПОГОНИ ПОЛИЦИИ ---
@router.callback_query(HypercarStates.police_chase, F.data == "hc_police_surrender")
async def police_surrender_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data or data.get("status") != "police" or data.get("is_processing"):
        await callback.answer()
        return

    await state.update_data(is_processing=True)
    user_id = callback.from_user.id
    bet = data.get("bet")
    meters = data.get("meters")
    car_key = data.get("car_key", "sport")
    car_info = CARS[car_key]

    multiplier = 1.0 + (meters * car_info["growth"])
    win_amount = round(bet * multiplier, 2)

    db.update_balance(user_id, win_amount)
    db.add_stats(user_id, is_lost=False, bet_amount=bet)
    await state.clear()

    await callback.answer("Вы мирно припарковались.")
    try:
        await callback.message.edit_text(
            f"🤝 *МИРНОЕ СОГЛАШЕНИЕ С ПОЛИЦИЕЙ* 🤝\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Вы остановили болид по первому требованию. Инспектор выписал предупреждение за превышение.\n\n"
            f"📏 Пройдено: *{meters:.1f} метров*\n"
            f"📈 Множитель: *x{multiplier:.4f}*\n"
            f"💰 Забранный куш: *+{win_amount:,} nCoin*\n\n"
            f"💳 Ваш баланс: *{db.get_user(user_id)['balance']:,} nCoin*",
            parse_mode="Markdown"
        )
    except Exception: pass

@router.callback_query(HypercarStates.police_chase, F.data == "hc_police_escape")
async def police_escape_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data or data.get("status") != "police" or data.get("is_processing"):
        await callback.answer()
        return

    await state.update_data(is_processing=True)
    user_id = callback.from_user.id
    bet = data.get("bet")
    meters = data.get("meters")
    car_key = data.get("car_key", "sport")
    car_info = CARS[car_key]

    # ШАНС ПОБЕГА СНИЖЕН ДО 15% (85% ШАНС АРЕСТА)
    if random.random() < 0.15:
        multiplier = (1.0 + (meters * car_info["growth"])) * 1.1
        win_amount = round(bet * multiplier, 2)

        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)
        await state.clear()

        await callback.answer("🏎️💨 УСПЕШНЫЙ ПОБЕГ!")
        try:
            await callback.message.edit_text(
                f"🏁 *УСПЕШНО ОТРВАЛИСЬ ОТ ПОЛИЦИИ!* 🏎️💨\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Вы ушли от погони на узких виражах шоссе!\n\n"
                f"📏 Пройдено: *{meters:.1f} метров*\n"
                f"📈 Итоговый множитель: *x{multiplier:.4f}*\n"
                f"💰 Выигрыш: *+{win_amount:,} nCoin*\n\n"
                f"💳 Ваш баланс: *{db.get_user(user_id)['balance']:,} nCoin*",
                parse_mode="Markdown"
            )
        except Exception: pass
    else:
        db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)
        await state.clear()

        await callback.answer("🚔 АРЕСТ!", show_alert=True)
        try:
            await callback.message.edit_text(
                f"🚔 *ПОЛИЦИЯ ПЕРЕХВАТИЛА БОЛИД!* 🚨\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Вас зажали в тиски и отправили на штрафстоянку!\n\n"
                f"💸 Потеря ставки и штраф: *-{bet:,} nCoin*\n"
                f"💳 Ваш баланс: *{db.get_user(user_id)['balance']:,} nCoin*",
                parse_mode="Markdown"
            )
        except Exception: pass

@router.callback_query(HypercarStates.playing, F.data == "hc_stop")
async def stop_hypercar_callback(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        if not data or data.get("status") != "running" or data.get("is_processing"):
            await callback.answer("Заезд уже завершен!", show_alert=True)
            return

        await state.update_data(status="stopped", is_processing=True)

        user_id = callback.from_user.id
        bet = data.get("bet")
        meters = data.get("meters")
        car_key = data.get("car_key", "sport")
        car_info = CARS[car_key]
        
        multiplier = 1.0 + (meters * car_info["growth"])
        win_amount = round(bet * multiplier, 2)

        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)
        await state.clear()

        await callback.answer("🛑 Торможение успешно!")

        text = (
            f"🏎️ *УСПЕШНЫЙ ФИНИШ!* 🏎️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Вы вовремя затормозили и забрали выигрыш!\n\n"
            f"📏 Пройдено дистанции: *{meters:.1f} метров*\n"
            f"📈 Зафиксирован множитель: *x{multiplier:.4f}*\n"
            f"💰 Ваш выигрыш: *+{win_amount:,} nCoin*\n\n"
            f"💳 Ваш баланс: *{db.get_user(user_id)['balance']:,} nCoin*"
        )

        await callback.message.edit_text(text, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Error stopping hypercar: {e}", exc_info=True)
