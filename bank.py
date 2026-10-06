import time
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, Command
import db
import utils

# ==============================================================================
# 🎭 НАСТРОЙКА ПРЕМИУМ-ЭМОДЗИ
# Укажите ID эмодзи в кавычках справа. Если оставите пустым "", будет обычный эмодзи.
# ==============================================================================
EMOJI_BANK      = "5201873447554145566"  # 🏦 Банк
EMOJI_WALLET    = "5417924076503062111"  # 💳 Кошелёк
EMOJI_PIGGY     = "5296355151743838259"  # 🐷 Копилка
EMOJI_SUITCASE  = "5246970161780498745"  # 💼 Портфель / Вклады
EMOJI_PIN       = "5397782960512444700"  # 📌 Булавка
EMOJI_WRITE     = "5395444784611480792"  # ✍️ Карандаш
EMOJI_CROSS     = "5210952531676504517"  # ❌ Ошибка / Крестик
EMOJI_CHECK     = "5805523262691611326"  # ✅ Успех / Галочка
EMOJI_CHART     = "5231200819986047254"  # 📈 График
EMOJI_LIST      = "5199750217586459631"  # 📋 Список
EMOJI_PARTY     = "5461151367559141950"  # 🎉 Праздник
EMOJI_GREEN     = "5805523262691611326"  # 🟢 Статус готов
EMOJI_HOURGLASS = "5454415424319931791"  # ⏳ Ожидание
EMOJI_MONEY     = "5990147899403539264"  # 💰 Мешок денег
EMOJI_GIFT      = "5463172695132745432"  # 🎁 Подарок


def e(symbol: str, emoji_id: str) -> str:
    """Универсальный хелпер для формирования премиум-эмодзи в HTML."""
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">{symbol}</tg-emoji>'
    return symbol


router = Router()

class BankStates(StatesGroup):
    waiting_for_savings_deposit = State()
    waiting_for_savings_withdraw = State()
    waiting_for_deposit_amount = State()

DAILY_SAVINGS_RATE = 0.01
MAX_TERM_DEPOSIT = 100_000_000  # Максимальный срочный депозит: 100kk nCoin
MAX_SAVINGS_BALANCE = 100_000_000  # Максимум на накопительном счёте: 100kk nCoin


def fmt_bank(value: float) -> str:
    """Форматирование банковских сумм с разделителем апострофом."""
    value = float(value or 0)
    if abs(value - round(value)) < 1e-9:
        return f"{int(value):,}".replace(",", "'")
    return f"{value:,.2f}".replace(",", "'")


def get_bank_snapshot(user_id: int) -> dict:
    """Возвращает актуальное состояние кошелька, копилки и вкладов."""
    user = db.get_user(user_id)
    savings_balance = float(user.get("savings_balance", 0) or 0)
    accrued = calculate_accrued_savings(user)
    deposits = db.get_user_deposits(user_id)

    return {
        "user": user,
        "savings_balance": savings_balance,
        "accrued": accrued,
        "deposits": deposits,
        "term_total": sum(float(d.get("amount", 0) or 0) for d in deposits),
        "term_payout": sum(float(d.get("payout", 0) or 0) for d in deposits),
    }


def render_bank_text(snapshot: dict) -> str:
    """Формирует экран состояния банковского счёта."""
    user = snapshot["user"]
    return (
        f'{e("🏦", EMOJI_BANK)} <b>Центральный Банк nCoin</b> {e("🏦", EMOJI_BANK)}\n'
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n"
        "Превратите ваши сбережения в надежный пассивный доход!\n\n"
        f'{e("💳", EMOJI_WALLET)} Кошелёк: <b>{fmt_bank(user.get("balance", 0))} nCoin</b>\n\n'
        f'{e("🐷", EMOJI_PIGGY)} <b>Накопительный счёт (Копилка):</b>\n'
        f'├ На счёте: <b>{fmt_bank(snapshot["savings_balance"])} nCoin</b>\n'
        f'├ Лимит счёта: <b>{fmt_bank(MAX_SAVINGS_BALANCE)} nCoin</b>\n'
        '├ Ставка: <b>1% в сутки</b>\n'
        f'└ Накоплено процентов: <b>+{fmt_bank(snapshot["accrued"])} nCoin</b>\n\n'
        f'{e("💼", EMOJI_SUITCASE)} <b>Срочные депозиты:</b>\n'
        f'├ Активных вкладов: <b>{len(snapshot["deposits"])} шт.</b>\n'
        f'├ Вложено всего: <b>{fmt_bank(snapshot["term_total"])} nCoin</b>\n'
        f'└ К выплате: <b>{fmt_bank(snapshot["term_payout"])} nCoin</b>\n\n'
        f'{e("📌", EMOJI_PIN)} Максимальная сумма одного депозита: <b>{fmt_bank(MAX_TERM_DEPOSIT)} nCoin</b>'
    )


# --- ИНЛАЙН КЛАВИАТУРЫ С ЦВЕТНЫМИ КНОПКАМИ ---

def get_bank_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Положить в банк", callback_data="bnk_sav_dep", style="success"),
            InlineKeyboardButton(text="📤 Снять из банка", callback_data="bnk_sav_wd", style="danger")
        ],
        [
            InlineKeyboardButton(text="🌾 Собрать проценты", callback_data="bnk_sav_claim", style="primary")
        ],
        [
            InlineKeyboardButton(text="📈 Открыть Вклад", callback_data="bnk_term_menu", style="success"),
            InlineKeyboardButton(text="💼 Мои вклады", callback_data="bnk_my_term", style="primary")
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="bnk_refresh")
        ]
    ])


def get_term_plans_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷 «Старт» — 1 день (+1.5% прибыль)", callback_data="bnk_term_select:1:1.015:10000")],
        [InlineKeyboardButton(text="💼 «Бизнес» — 3 дня (+5.0% прибыль)", callback_data="bnk_term_select:3:1.05:50000")],
        [InlineKeyboardButton(text="👑 «Инвестор» — 7 дней (+15.0% прибыль)", callback_data="bnk_term_select:7:1.15:200000")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="bnk_back_main")]
    ])


def get_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в Банк", callback_data="bnk_back_main")]
    ])


# --- РАСЧЁТ ПРОЦЕНТОВ ---

def calculate_accrued_savings(user: dict) -> float:
    savings_balance = float(user.get("savings_balance", 0) or 0)
    if savings_balance <= 0:
        return 0.0

    last_claim = user.get("savings_last_claim", 0) or 0
    if last_claim == 0:
        return 0.0

    seconds_passed = int(time.time()) - int(last_claim)
    if seconds_passed <= 0:
        return 0.0

    earned = savings_balance * DAILY_SAVINGS_RATE * (seconds_passed / 86400.0)
    return round(earned, 2)


# --- ГЛАВНЫЙ ЭКРАН БАНКА ---

@router.message(F.text.casefold().in_(["банк", "/bank", "bank"]))
@router.message(Command("bank"))
async def show_bank_main(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    await check_and_pay_term_deposits(message.bot, user_id)

    snapshot = get_bank_snapshot(user_id)
    await message.answer(
        render_bank_text(snapshot),
        reply_markup=get_bank_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "bnk_back_main")
@router.callback_query(F.data == "bnk_refresh")
async def bank_refresh_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Балансы обновлены!")
    await state.clear()
    user_id = callback.from_user.id
    await check_and_pay_term_deposits(callback.bot, user_id)

    snapshot = get_bank_snapshot(user_id)
    try:
        await callback.message.edit_text(
            render_bank_text(snapshot),
            reply_markup=get_bank_menu_kb(),
            parse_mode="HTML"
        )
    except Exception:
        pass


# --- НАКОПИТЕЛЬНЫЙ СЧЁТ ---

@router.callback_query(F.data == "bnk_sav_dep")
async def bnk_sav_dep_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(
        f'{e("💳", EMOJI_WALLET)} Баланс кошелька: <b>{fmt_bank(user.get("balance", 0))} nCoin</b>\n'
        f'{e("🐷", EMOJI_PIGGY)} В банке: <b>{fmt_bank(user.get("savings_balance", 0))} nCoin</b>\n'
        f'{e("📌", EMOJI_PIN)} Лимит банка: <b>{fmt_bank(MAX_SAVINGS_BALANCE)} nCoin</b>\n\n'
        f'{e("✍️", EMOJI_WRITE)} <b>Введите сумму nCoin для перевода в банк:</b>\n'
        '<i>(Принимаются сокращения: 10к, 50к, все)</i>',
        reply_markup=get_back_kb(),
        parse_mode="HTML"
    )
    await state.set_state(BankStates.waiting_for_savings_deposit)


@router.message(StateFilter(BankStates.waiting_for_savings_deposit))
async def bnk_sav_dep_process(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    amount = utils.parse_bet_input(message.text, user.get("balance", 0))

    if amount <= 0:
        await message.answer(
            f'{e("❌", EMOJI_CROSS)} Сумма пополнения должна быть больше 0!',
            parse_mode="HTML"
        )
        return

    if user.get("balance", 0) < amount:
        await message.answer(
            f'{e("❌", EMOJI_CROSS)} Недостаточно средств! Баланс: <b>{fmt_bank(user.get("balance", 0))} nCoin</b>',
            parse_mode="HTML"
        )
        return

    current_savings = float(user.get("savings_balance", 0) or 0)
    if current_savings + amount > MAX_SAVINGS_BALANCE:
        available = max(0, MAX_SAVINGS_BALANCE - current_savings)
        await message.answer(
            f'{e("❌", EMOJI_CROSS)} Превышен лимит копилки {fmt_bank(MAX_SAVINGS_BALANCE)} nCoin!\n'
            f'Можно положить максимум: <b>{fmt_bank(available)} nCoin</b>',
            parse_mode="HTML"
        )
        return

    accrued = calculate_accrued_savings(user)
    new_savings_balance = current_savings + amount
    current_time = int(time.time())

    db.update_balance(user_id, -amount + accrued)
    db.update_savings(user_id, new_savings_balance, current_time)

    await message.answer(
        f'{e("✅", EMOJI_CHECK)} Успешно переведено <b>{fmt_bank(amount)} nCoin</b> в копилку'
        + (f' и собрано <b>+{fmt_bank(accrued)} nCoin</b> процентов' if accrued > 0 else '')
        + '!',
        parse_mode="HTML"
    )
    await show_bank_main(message, state)


@router.callback_query(F.data == "bnk_sav_wd")
async def bnk_sav_wd_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(
        f'{e("🐷", EMOJI_PIGGY)} Баланс на счету: <b>{fmt_bank(user.get("savings_balance", 0))} nCoin</b>\n\n'
        f'{e("✍️", EMOJI_WRITE)} <b>Введите сумму nCoin для вывода из банка:</b>\n'
        '<i>(Принимаются сокращения: 10к, 50к, все)</i>',
        reply_markup=get_back_kb(),
        parse_mode="HTML"
    )
    await state.set_state(BankStates.waiting_for_savings_withdraw)


@router.message(StateFilter(BankStates.waiting_for_savings_withdraw))
async def bnk_sav_wd_process(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    savings_balance = float(user.get("savings_balance", 0) or 0)
    amount = utils.parse_bet_input(message.text, savings_balance)

    if amount <= 0:
        await message.answer(
            f'{e("❌", EMOJI_CROSS)} Сумма вывода должна быть больше 0!',
            parse_mode="HTML"
        )
        return

    if savings_balance < amount:
        await message.answer(
            f'{e("❌", EMOJI_CROSS)} В копилке нет столько nCoin!',
            parse_mode="HTML"
        )
        return

    accrued = calculate_accrued_savings(user)
    new_savings_balance = savings_balance - amount
    current_time = int(time.time())

    db.update_balance(user_id, amount + accrued)
    db.update_savings(user_id, new_savings_balance, current_time)

    await message.answer(
        f'{e("✅", EMOJI_CHECK)} Успешно выведено <b>{fmt_bank(amount)} nCoin</b> из банка'
        + (f' и собрано <b>+{fmt_bank(accrued)} nCoin</b> процентов' if accrued > 0 else '')
        + '!',
        parse_mode="HTML"
    )
    await show_bank_main(message, state)


@router.callback_query(F.data == "bnk_sav_claim")
async def bnk_sav_claim_cb(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    accrued = calculate_accrued_savings(user)

    if accrued <= 0:
        await callback.answer("❌ Проценты еще не накопились!", show_alert=True)
        return

    current_time = int(time.time())
    db.update_balance(user_id, accrued)
    db.update_savings(user_id, user.get("savings_balance", 0), current_time)

    await callback.answer(f"🎉 Вы собрали процентов на: +{fmt_bank(accrued)} nCoin!", show_alert=True)
    await bank_refresh_cb(callback, state)


# --- СРОЧНЫЕ ДЕПОЗИТЫ ---

@router.callback_query(F.data == "bnk_term_menu")
async def bnk_term_menu_cb(callback: CallbackQuery):
    await callback.answer()
    text = (
        f'{e("📈", EMOJI_CHART)} <b>Депозиты nCoin</b> {e("📈", EMOJI_CHART)}\n'
        "➖➖➖➖➖➖➖➖➖➖➖\n"
        "Заморозьте свои монеты под фиксированный процент.\n"
        f'Максимальная сумма одного депозита: <b>{fmt_bank(MAX_TERM_DEPOSIT)} nCoin</b>\n\n'
        f'{e("📋", EMOJI_LIST)} <b>Доступные тарифные планы:</b>'
    )
    await callback.message.edit_text(text, reply_markup=get_term_plans_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("bnk_term_select:"))
async def bnk_term_select_cb(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split(":")
    days = int(parts[1])
    multiplier = float(parts[2])
    min_amount = int(parts[3])

    await state.update_data(term_days=days, term_mult=multiplier, term_min=min_amount)

    user = db.get_user(callback.from_user.id)
    percent = round((multiplier - 1.0) * 100, 1)

    text = (
        f'{e("📈", EMOJI_CHART)} <b>Открытие вклада на {days} дней (+{percent}% прибыль)</b>\n'
        f'├ Минимальная сумма: <b>{fmt_bank(min_amount)} nCoin</b>\n'
        f'├ Максимальная сумма: <b>{fmt_bank(MAX_TERM_DEPOSIT)} nCoin</b>\n'
        f'└ Твой баланс: <b>{fmt_bank(user.get("balance", 0))} nCoin</b>\n\n'
        f'{e("✍️", EMOJI_WRITE)} <b>Введите сумму nCoin, которую вы хотите инвестировать:</b>'
    )
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")
    await state.set_state(BankStates.waiting_for_deposit_amount)


@router.message(StateFilter(BankStates.waiting_for_deposit_amount))
async def bnk_term_process(message: Message, state: FSMContext):
    data = await state.get_data()
    days = data["term_days"]
    multiplier = data["term_mult"]
    min_amount = data["term_min"]
    await state.clear()

    user_id = message.from_user.id
    user = db.get_user(user_id)
    amount = utils.parse_bet_input(message.text, user.get("balance", 0))

    if amount < min_amount:
        await message.answer(
            f'{e("❌", EMOJI_CROSS)} Минимальная сумма инвестиции для этого плана: <b>{fmt_bank(min_amount)} nCoin</b>!',
            parse_mode="HTML"
        )
        return

    if amount > MAX_TERM_DEPOSIT:
        await message.answer(
            f'{e("❌", EMOJI_CROSS)} Максимальная сумма одного депозита: <b>{fmt_bank(MAX_TERM_DEPOSIT)} nCoin</b>!',
            parse_mode="HTML"
        )
        return

    if user.get("balance", 0) < amount:
        await message.answer(
            f'{e("❌", EMOJI_CROSS)} Недостаточно средств! Баланс: <b>{fmt_bank(user.get("balance", 0))} nCoin</b>',
            parse_mode="HTML"
        )
        return

    payout = round(amount * multiplier, 2)
    db.update_balance(user_id, -amount)
    db.create_deposit(user_id, amount, days, payout)

    percent = round((multiplier - 1.0) * 100, 1)
    text = (
        f'{e("🎉", EMOJI_PARTY)} <b>Вклад успешно открыт!</b> {e("🎉", EMOJI_PARTY)}\n'
        "➖➖➖➖➖➖➖➖➖➖➖\n"
        f'├ Сумма инвестиции: <b>{fmt_bank(amount)} nCoin</b>\n'
        f'├ Срок заморозки: <b>{days} дней</b>\n'
        f'├ Процентная ставка: <b>+{percent}%</b>\n'
        f'└ Сумма к выплате в конце срока: <b>{fmt_bank(payout)} nCoin</b>'
    )
    await message.answer(text, reply_markup=get_back_kb(), parse_mode="HTML")


@router.callback_query(F.data == "bnk_my_term")
async def bnk_my_term_cb(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    deposits = db.get_user_deposits(user_id)

    text = f'{e("💼", EMOJI_SUITCASE)} <b>ТВОИ АКТИВНЫЕ ВКЛАДЫ</b> {e("💼", EMOJI_SUITCASE)}\n━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
    if not deposits:
        text += "У вас пока нет активных вкладов. Откройте новый вклад из меню, чтобы начать зарабатывать!"
    else:
        current_time = int(time.time())
        for idx, d in enumerate(deposits):
            time_left = d["end_time"] - current_time
            if time_left <= 0:
                status = f'{e("🟢", EMOJI_GREEN)} Готов к выплате'
            else:
                hours = time_left // 3600
                minutes = (time_left % 3600) // 60
                status = f'{e("⏳", EMOJI_HOURGLASS)} Осталось: {hours}ч {minutes}м'

            percent = round((d["payout"] / d["amount"] - 1.0) * 100, 1)
            text += (
                f"{idx + 1}. <b>Депозит на {d['days']} дн. (+{percent}%)</b>\n"
                f'   ├ Сумма вклада: <b>{fmt_bank(d["amount"])} nCoin</b>\n'
                f'   ├ К выплате: <b>{fmt_bank(d["payout"])} nCoin</b>\n'
                f'   └ Статус: <b>{status}</b>\n\n'
            )

    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")


# --- АВТОМАТИЧЕСКОЕ ЗАКРЫТИЕ ВКЛАДОВ ---

async def check_and_pay_term_deposits(bot: Bot, user_id: int):
    deposits = db.get_user_deposits(user_id)
    if not deposits:
        return

    current_time = int(time.time())
    for d in deposits:
        if d["end_time"] <= current_time:
            payout_amount = d["payout"]
            db.update_balance(user_id, payout_amount)
            db.close_deposit(d["id"])

            try:
                percent = round((d["payout"] / d["amount"] - 1.0) * 100, 1)
                text = (
                    f'{e("🎉", EMOJI_PARTY)} <b>Твой банковский вклад успешно закрыт!</b> {e("🎉", EMOJI_PARTY)}\n'
                    "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n"
                    "Монеты успешно разморожены и зачислены на баланс:\n\n"
                    f'{e("💰", EMOJI_MONEY)} Инвестировано: <b>{fmt_bank(d["amount"])} nCoin</b>\n'
                    f'{e("📈", EMOJI_CHART)} Доходность: <b>+{percent}%</b>\n'
                    f'{e("🎁", EMOJI_GIFT)} Итого зачислено: <b>+{fmt_bank(payout_amount)} nCoin</b>!'
                )
                await bot.send_message(user_id, text, parse_mode="HTML")
            except Exception:
                pass
