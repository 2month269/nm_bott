# smart.py
import random
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import db
import utils

logger = logging.getLogger(__name__)

router = Router()

class SmartStates(StatesGroup):
    playing = State()

# ==============================================================================
# 🎯 СПИСОК ВСЕХ ПРЕМИУМ-ЭМОДЗИ (CUSTOM EMOJI ID)
# Просто подставьте Ваши ID эмодзи вместо значений "ВАШ_EMOJI_ID" в кавычках ниже:
# ==============================================================================
EMOJI_IDS = {
    "TOOLS": "5462921117423384478",       # 🛠️ Инструменты
    "TV": "5339439291539925427",          # 📺 Телевизор
    "BOOM": "5276032951342088188",        # 💥 Взрыв
    "FIRE": "5256047523620995497",        # 🔥 Огонь
    "WIND": "5996850556646199666",        # 💨 Дым / Ветер
    "SPARK": "5990073381720953601",       # ✨ Искры
    "LIGHTNING": "5900140601948507995",   # ⚡ Молния
    "CONTROL": "5350612670435313545",     # 🎛️ Пульт / Панель
    "DISH": "5413337163100083587",        # 📡 Антенна
    "STAR": "6028477497518068483",        # 🌟 Звезда
    "GREEN_SQ": "5390869523454767152",    # 🟩 Зеленый квадрат
    "ORANGE_SQ": "5388649897241096590",   # 🟧 Оранжевый квадрат
    "WHITE_SQ": "5388782847953744845",    # ⬜ Белый квадрат
    "RED_CIR": "5818665600624365278",     # 🔴 Красный круг
    "BLUE_CIR": "5787543653417225686",    # 🔵 Синий круг
    "GREEN_CIR": "5447464938874348535",   # 🟢 Зеленый круг
    "YELLOW_CIR": "5393551318214257273",  # 🟡 Желтый круг
    "PURPLE_CIR": "5350512473143273043",  # 🟣 Фиолетовый круг
    "ORANGE_CIR": "5399819243162188641",  # 🟠 Оранжевый круг
    "WARNING": "5463358164705489689",     # ⚠️ Предупреждение
    "PENCIL": "5837003105228558796",      # ✍️ Карандаш
    "CROSS": "5454350746407419714",       # ❌ Крестик
    "PIN": "5789388797137392193",         # 📍 Метка
    "BARS": "5429463966432643712",        # 📊 График
    "MONEY": "5990147899403539264",       # 💰 Мешок денег
    "CHART": "5246749129878561406",       # 📈 Рост
    "GEAR": "5462921117423384478",        # ⚙️ Шестеренка
    "CHECK": "5805523262691611326",       # ✅ Галочка
    "PARTY": "5989848973974704652",       # 🎉 Праздник
    "CASH": "5879991085001871624",        # 💵 Купюра
    "TROPHY": "5226431245918942763",      # 🏆 Кубок
    "LOSS": "5235951397412805805",        # 💸 Улетающие деньги
    "CARD": "5370871279551258810",        # 💳 Карта / Баланс
}

def e(key: str, fallback_emoji: str) -> str:
    """Генерирует HTML-тег премиум-эмодзи с подстановкой ID из словаря EMOJI_IDS"""
    emoji_id = EMOJI_IDS.get(key, "")
    if emoji_id and emoji_id != "ВАШ_EMOJI_ID":
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback_emoji}</tg-emoji>'
    return fallback_emoji


# Все доступные провода для кнопок
WIRES_DATA = {
    "red": "🔴 Красный",
    "blue": "🔵 Синий",
    "green": "🟢 Зелёный",
    "yellow": "🟡 Жёлтый",
    "purple": "🟣 Фиолетовый",
    "orange": "🟠 Оранжевый"
}

# Конфигурация 5 уровней усложнения
STAGES_CONFIG = [
    {
        "stage": 1,
        "name": "Кабель питания",
        "mult": 1.50,
        "wires": ["red", "blue"],
        "desc": "2 провода (Шанс 50%)"
    },
    {
        "stage": 2,
        "name": "Трансформатор",
        "mult": 3.50,
        "wires": ["red", "blue", "green"],
        "desc": "3 провода (Шанс 33%)"
    },
    {
        "stage": 3,
        "name": "Звуковая плата",
        "mult": 10.00,
        "wires": ["red", "blue", "green", "yellow"],
        "desc": "4 провода (Шанс 25%) — Остановка доступна!"
    },
    {
        "stage": 4,
        "name": "ЭЛТ-Кинескоп",
        "mult": 35.00,
        "wires": ["red", "blue", "green", "yellow", "purple"],
        "desc": "5 проводов (Шанс 20%)"
    },
    {
        "stage": 5,
        "name": "Золотой микрочип",
        "mult": 150.00,
        "wires": ["red", "blue", "green", "yellow", "purple", "orange"],
        "desc": "6 проводов (Шанс 16.6%) — ДЖЕКПОТ!"
    }
]


def get_tv_screen_art(stage: int, status: str = "playing") -> str:
    """Генерирует визуальный экран телевизора"""
    tv = e("TV", "📺")
    if status == "exploded":
        b = e("BOOM", "💥")
        f = e("FIRE", "🔥")
        w = e("WIND", "💨")
        return (
            f"{tv} ╔════════════════════╗\n"
            f"{tv} ║ {b}{b} БА-БАХ! {b}{b} ║\n"
            f"{tv} ║ {w}{f} ВЗРЫВ! {f}{w} ║\n"
            f"{tv} ╚════════════════════╝"
        )
    elif status == "repaired":
        sp = e("SPARK", "✨")
        return (
            f"{tv} ╔════════════════════╗\n"
            f"{tv} ║  {sp} 100% РАБОТАЕТ! ║\n"
            f"{tv} ║  {tv} ░▒▓4K ULTRA▓▒░ ║\n"
            f"{tv} ╚════════════════════╝"
        )

    l = e("LIGHTNING", "⚡")
    c = e("CONTROL", "🎛️")
    d = e("DISH", "📡")
    s = e("STAR", "🌟")

    noise_frames = [
        f"{tv} ║ ░░▒▒▓▓ 2 ПРОВОДА ▓▓▒▒░░ ║",
        f"{tv} ║ {l}░▒▓ 3 ПРОВОДА ▓▒░{l} ║",
        f"{tv} ║ {c} ▒▓ 4 ПРОВОДА ▓▒ {c} ║",
        f"{tv} ║ {d} ▓▒ 5 ПРОВОДОВ ▒▓ {d} ║",
        f"{tv} ║ {s} ▒▓ 6 ПРОВОДОВ ▓▒ {s} ║"
    ]
    frame = noise_frames[min(stage - 1, len(noise_frames) - 1)]

    return (
        f"{tv} ╔════════════════════╗\n"
        f"{frame}\n"
        f"{tv} ╚════════════════════╝"
    )


def get_progress_bar(current_stage: int, max_stages: int = 5) -> str:
    """Генерирует шкалу прогресса ремонта с премиум-эмодзи"""
    g = e("GREEN_SQ", "🟩")
    o = e("ORANGE_SQ", "🟧")
    w = e("WHITE_SQ", "⬜")
    filled = g * (current_stage - 1) + o
    empty = w * (max_stages - current_stage)
    return f"[{filled}{empty}] ({current_stage}/{max_stages})"


def get_playing_kb(stage: int, bet: float, current_win: float) -> InlineKeyboardMarkup:
    """Клавиатура с динамическим числом проводов и кнопкой забора выигрыша"""
    stage_info = STAGES_CONFIG[stage - 1]
    available_wires = stage_info["wires"]
    
    keyboard = []
    row = []

    for wire_key in available_wires:
        wire_name = WIRES_DATA[wire_key]
        row.append(InlineKeyboardButton(text=wire_name, callback_data=f"smart_wire_{wire_key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if stage > 2:
        prev_mult = STAGES_CONFIG[stage - 2]["mult"]
        keyboard.append([
            InlineKeyboardButton(
                text=f"💰 ЗАБРАТЬ {current_win:,.0f} nCoin (x{prev_mult})", 
                callback_data="smart_cashout"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_game_over_kb(bet: float) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой повтора игры"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Играть снова (та же ставка)", callback_data=f"smart_again:{bet}")
        ]
    ])


@router.message(StateFilter(None), F.text, F.text.lower().startswith(("всезнайка", "телевизор", "смарт")))
async def handle_smart_commands(message: Message, state: FSMContext):
    try:
        await state.clear()
        user_id = message.from_user.id
        user = db.get_user(user_id)

        parts = message.text.strip().split()
        if len(parts) < 2:
            tools = e("TOOLS", "🛠️")
            red = e("RED_CIR", "🔴")
            blue = e("BLUE_CIR", "🔵")
            green = e("GREEN_CIR", "🟢")
            yellow = e("YELLOW_CIR", "🟡")
            purple = e("PURPLE_CIR", "🟣")
            orange = e("ORANGE_CIR", "🟠")
            fire = e("FIRE", "🔥")
            warn = e("WARNING", "⚠️")
            pencil = e("PENCIL", "✍️")
            cross = e("CROSS", "❌")

            text = (
                f"{tools} <b>Игра ВСЕЗНАЙКА: Усложняющийся Ремонт ТВ</b> {tools}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Пройдите 5 уровней усложнения! С каждым уровнем число проводов растет:\n\n"
                f"• <b>Уровень 1:</b> 2 провода ({red}{blue}) ➔ <code>x1.50</code>\n"
                f"• <b>Уровень 2:</b> 3 провода ({red}{blue}{green}) ➔ <code>x3.50</code>\n"
                f"• <b>Уровень 3:</b> 4 провода ({red}{blue}{green}{yellow}) ➔ <code>x10.00</code> <i>(Остановка открыта!)</i>\n"
                f"• <b>Уровень 4:</b> 5 проводов ({red}{blue}{green}{yellow}{purple}) ➔ <code>x35.00</code>\n"
                f"• <b>Уровень 5:</b> 6 проводов ({red}{blue}{green}{yellow}{purple}{orange}) ➔ <code>x150.00</code> {fire}\n\n"
                f"{warn} <b>Правило:</b> Забрать выигрыш можно <b>ТОЛЬКО после прохождения 2 уровня</b>!\n\n"
                f"{pencil} <b>Для запуска напишите:</b> <code>всезнайка [ставка]</code> или <code>телевизор [ставка]</code>\n"
                f"Например: <code>всезнайка 10к</code> или <code>телевизор все</code>"
            )
            await message.answer(text, parse_mode="HTML")
            return

        bet_str = parts[1]
        try:
            bet = utils.parse_bet_input(bet_str, user["balance"])
        except Exception:
            try:
                bet = utils.parse_bet_input(bet_str)
            except Exception:
                await message.answer(f'{e("CROSS", "❌")} <b>Ошибка распознавания ставки!</b>', parse_mode="HTML")
                return

        if bet <= 0:
            await message.answer(f'{e("CROSS", "❌")} <b>Ставка должна быть больше 0!</b>', parse_mode="HTML")
            return

        if user["balance"] < bet:
            await message.answer(f'{e("CROSS", "❌")} <b>Недостаточно nCoin! Ваш баланс:</b> <code>{user["balance"]:,} nCoin</code>', parse_mode="HTML")
            return

        await start_smart_game(message, user_id, bet, state)

    except Exception as e_err:
        logger.error(f"Error in handle_smart_commands: {e_err}")
        await message.answer(f'{e("CROSS", "❌")} <b>Произошла ошибка при запуске игры.</b>', parse_mode="HTML")


async def start_smart_game(message_obj: Message, user_id: int, bet: float, state: FSMContext):
    user = db.get_user(user_id)
    if user["balance"] < bet:
        await message_obj.answer(f'{e("CROSS", "❌")} <b>Недостаточно nCoin на балансе!</b>', parse_mode="HTML")
        return

    # Списание ставки
    db.update_balance(user_id, -bet)

    stage = 1
    winning_wire = random.choice(STAGES_CONFIG[0]["wires"])

    await state.update_data(
        bet=bet,
        stage=stage,
        winning_wire=winning_wire,
        status="playing"
    )
    await state.set_state(SmartStates.playing)

    tv_art = get_tv_screen_art(stage)
    progress = get_progress_bar(stage)
    stage_info = STAGES_CONFIG[0]

    tools = e("TOOLS", "🛠️")
    pin = e("PIN", "📍")
    bars = e("BARS", "📊")
    money = e("MONEY", "💰")
    chart = e("CHART", "📈")
    gear = e("GEAR", "⚙️")
    warn = e("WARNING", "⚠️")

    text = (
        f"{tv_art}\n\n"
        f"{tools} <b>РЕМОНТ ТЕЛЕВИЗОРА — УРОВЕНЬ 1</b> {tools}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{pin} Узел: <b>{stage_info['name']}</b>\n"
        f"{bars} Прогресс: {progress}\n"
        f"{money} Ставка: <b>{bet:,} nCoin</b>\n"
        f"{chart} Целевой множитель: <b>x{stage_info['mult']}</b>\n"
        f"{gear} Сложность: <b>2 провода</b>\n\n"
        f"{warn} <b>Забрать выигрыш можно будет только ПОСЛЕ прохождения 2 уровня!</b>\n\n"
        f"Какой провод вы решите соединить?"
    )

    await message_obj.answer(text, reply_markup=get_playing_kb(1, bet, 0), parse_mode="HTML")


@router.callback_query(SmartStates.playing, F.data.startswith("smart_wire_"))
async def handle_wire_choice(callback: CallbackQuery, state: FSMContext):
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        if not data or data.get("status") != "playing":
            await callback.answer("Игра не найдена или завершена!", show_alert=True)
            return

        bet = data.get("bet")
        stage = data.get("stage")
        winning_wire = data.get("winning_wire")
        chosen_wire = callback.data.split("_")[-1]

        chosen_name = WIRES_DATA.get(chosen_wire, chosen_wire)

        # УСПЕШНЫЙ ВЫБОР ПРОВОДА
        if chosen_wire == winning_wire:
            current_stage_info = STAGES_CONFIG[stage - 1]
            current_mult = current_stage_info["mult"]
            current_win = round(bet * current_mult, 2)

            if stage < 5:
                next_stage = stage + 1
                next_stage_info = STAGES_CONFIG[next_stage - 1]
                next_winning_wire = random.choice(next_stage_info["wires"])

                await state.update_data(
                    stage=next_stage,
                    winning_wire=next_winning_wire
                )

                tv_art = get_tv_screen_art(next_stage)
                progress = get_progress_bar(next_stage)

                check = e("CHECK", "✅")
                party = e("PARTY", "🎉")
                pin = e("PIN", "📍")
                bars = e("BARS", "📊")
                cash = e("CASH", "💵")
                gear = e("GEAR", "⚙️")
                warn = e("WARNING", "⚠️")

                if next_stage == 2:
                    stop_note = f'{warn} <b>Забрать выигрыш пока нельзя! Вы должны пройти Уровень 2!</b>'
                else:
                    stop_note = f'{party} <b>Кнопка ЗАБРАТЬ ВЫИГРЫШ открыта! Вы можете забрать куш или рисковать дальше!</b>'

                text = (
                    f"{tv_art}\n\n"
                    f"{check} <b>УРОВЕНЬ {stage} УСПЕШНО ПРОЙДЕН!</b> {party}\n"
                    f"Вы верно соединили {chosen_name} провод!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{pin} Следующий узел: <b>{next_stage_info['name']}</b>\n"
                    f"{bars} Прогресс: {progress}\n"
                    f"{cash} Накопленный куш: <b>{current_win:,} nCoin</b> (x{current_mult})\n"
                    f"{gear} Новая сложность: <b>{len(next_stage_info['wires'])} проводов</b> (x{next_stage_info['mult']})\n\n"
                    f"{stop_note}\n\n"
                    f"Выберите провод:"
                )

                await callback.message.edit_text(
                    text, 
                    reply_markup=get_playing_kb(next_stage, bet, current_win), 
                    parse_mode="HTML"
                )

            else:
                # ПОЛНАЯ ПОБЕДА (ВСЕ 5 УРОВНЕЙ ПРОЙДЕНЫ)
                await state.clear()
                db.update_balance(user_id, current_win)
                db.add_stats(user_id, is_lost=False, bet_amount=bet)

                tv_art = get_tv_screen_art(5, status="repaired")
                trophy = e("TROPHY", "🏆")
                money = e("MONEY", "💰")
                chart = e("CHART", "📈")
                fire = e("FIRE", "🔥")
                card = e("CARD", "💳")

                text = (
                    f"{tv_art}\n\n"
                    f"{trophy} <b>ПОЛНЫЙ РЕМОНТ ЗАВЕРШЕН! ДЖЕКПОТ x150.00!</b> {trophy}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Невероятно! Вы успешно прошли все 5 уровней сложности!\n\n"
                    f"{money} Ваша ставка: <b>{bet:,} nCoin</b>\n"
                    f"{chart} Финальный множитель: <b>x{current_mult}</b>\n"
                    f"{fire} ДЖЕКПОТ ВЫИГРЫШ: <b>+{current_win:,} nCoin</b>\n"
                    f"{card} Твой баланс: <b>{db.get_user(user_id)['balance']:,} nCoin</b>"
                )

                await callback.message.edit_text(text, reply_markup=get_game_over_kb(bet), parse_mode="HTML")

        else:
            # ПРОИГРЫШ (ВЗРЫВ)
            await state.clear()
            db.add_stats(user_id, is_lost=True, lost_amount=bet, bet_amount=bet)

            tv_art = get_tv_screen_art(stage, status="exploded")
            boom = e("BOOM", "💥")
            tv = e("TV", "📺")
            fire = e("FIRE", "🔥")
            wind = e("WIND", "💨")
            loss = e("LOSS", "💸")
            card = e("CARD", "💳")

            text = (
                f"{tv_art}\n\n"
                f"{boom} <b>БА-БАХ! КОРОТКОЕ ЗАМЫКАНИЕ!</b> {boom}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Вы соединили {chosen_name} провод на {stage} уровне...\n"
                f"Телевизор не выдержал нагрузки и взорвался! {tv}{fire}{wind}\n\n"
                f"{loss} Потеря ставки: <b>-{bet:,} nCoin</b>\n"
                f"{card} Твой баланс: <b>{db.get_user(user_id)['balance']:,} nCoin</b>"
            )

            await callback.message.edit_text(text, reply_markup=get_game_over_kb(bet), parse_mode="HTML")

    except Exception as e_err:
        logger.error(f"Error in handle_wire_choice: {e_err}")
        await callback.message.edit_text(f'{e("CROSS", "❌")} <b>Произошла ошибка в процессе игры. Попробуйте снова.</b>', parse_mode="HTML")


@router.callback_query(SmartStates.playing, F.data == "smart_cashout")
async def handle_cashout(callback: CallbackQuery, state: FSMContext):
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        if not data or data.get("status") != "playing":
            await callback.answer("Игра не найдена!", show_alert=True)
            return

        bet = data.get("bet")
        stage = data.get("stage")

        if stage <= 2:
            await callback.answer("Забрать выигрыш можно будет только ПОСЛЕ прохождения 2 уровня!", show_alert=True)
            return

        passed_stage = stage - 1
        current_stage_info = STAGES_CONFIG[passed_stage - 1]
        mult = current_stage_info["mult"]
        win_amount = round(bet * mult, 2)

        await state.clear()

        db.update_balance(user_id, win_amount)
        db.add_stats(user_id, is_lost=False, bet_amount=bet)

        tv_art = get_tv_screen_art(passed_stage, status="repaired")
        money = e("MONEY", "💰")
        chart = e("CHART", "📈")
        party = e("PARTY", "🎉")
        card = e("CARD", "💳")

        text = (
            f"{tv_art}\n\n"
            f"{money} <b>ВЫИГРЫШ УСПЕШНО ЗАБРАН!</b> {money}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Вы остановились после {passed_stage} уровня и забрали куш!\n\n"
            f"{money} Ставка: <b>{bet:,} nCoin</b>\n"
            f"{chart} Зафиксированный множитель: <b>x{mult}</b>\n"
            f"{party} Полученный выигрыш: <b>+{win_amount:,} nCoin</b>\n"
            f"{card} Твой баланс: <b>{db.get_user(user_id)['balance']:,} nCoin</b>"
        )

        await callback.message.edit_text(text, reply_markup=get_game_over_kb(bet), parse_mode="HTML")

    except Exception as e_err:
        logger.error(f"Error in handle_cashout: {e_err}")
        await callback.message.edit_text(f'{e("CROSS", "❌")} <b>Произошла ошибка при получении выигрыша.</b>', parse_mode="HTML")


@router.callback_query(F.data.startswith("smart_again:"))
async def handle_smart_again(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    bet = float(parts[1])
    user_id = callback.from_user.id
    
    await start_smart_game(callback.message, user_id, bet, state)
