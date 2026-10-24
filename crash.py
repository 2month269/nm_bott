import re
import random
import logging
from math import floor
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ParseMode,
)
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    CallbackContext,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# -----------------------
# Конфигурация (по скринам)
# -----------------------
COEFFICIENTS = [1.2, 2.0, 5.0, 9.0, 10.0, 15.0, 38.0, 100.0]
CURRENCY_SHORT = "m¢"      # в результатах, как на скриншотах
CURRENCY_FULL = "mCoin"    # в инфо‑блоке можно указывать mCoin
THOUSAND_DELIM = "’"       # апостроф U+2019
RTP = 97                   # отображаемый RTP (скриншот)
MAX_MULTIPLIER = 100_000
MAX_STAKE = 200_000_000    # 200кк
MIN_STAKE = 1

# Никнейм‑ссылка — ровно как ты просила
MENTION_HREF = "tg://user?id=0"

# -----------------------
# Хелперы
# -----------------------
def format_amount(amount: int) -> str:
    """Форматирует целое число с разделителем тысяч апострофом: 20000 -> 20'000"""
    s = str(int(amount))
    parts = []
    while s:
        parts.append(s[-3:])
        s = s[:-3]
    return THOUSAND_DELIM.join(reversed(parts))


def format_multiplier(mult: float) -> str:
    """Возвращает множитель в русском формате с запятой, два знака после запятой при необходимости."""
    # Оставляем минимум 2 знака, убираем лишние нули справа
    s = f"{mult:.2f}"
    s = s.rstrip('0').rstrip('.') if '.' in s else s
    s = s.replace('.', ',')
    return s


def mention_html(user_name: Optional[str]) -> str:
    """HTML-упоминание с href=MENTION_HREF и видимым текстом user_name или 'Ты'."""
    text = (user_name or "Ты").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="{MENTION_HREF}">{text}</a>'


def parse_number_token(token: str, user_balance: Optional[int] = None) -> Optional[int]:
    """
    Парсинг ставки:
    - "пол" -> floor(balance / 2)
    - "все" -> balance
    - 1к -> 1000, 1кк -> 1000000, 80кк -> 80000000
    - допускаем 1.5k, 1.5кк (переводим), апострофы, пробелы, запятые
    - возвращает None при ошибке
    """
    if not token:
        return None
    s = token.strip().lower()
    # Пол/все
    if s in ("пол", "половина", "полвины"):
        if user_balance is None:
            return None
        return max(1, user_balance // 2)
    if s in ("все", "всё", "весь", "вся"):
        if user_balance is None:
            return None
        return max(1, user_balance)

    # Убираем пробелы и разделители тысяч
    s_clean = s.replace(" ", "").replace(",", "").replace("’", "").replace("'", "")

    # Сопоставляем числовой + суффикс (к, кк, k, kk)
    m = re.match(r'^(\d+(?:[.,]\d+)?)(к{1,2}|kk|k|к|m{1,2})?$', s_clean, flags=re.IGNORECASE)
    if m:
        num_str = m.group(1).replace(',', '.')
        try:
            num = float(num_str)
        except ValueError:
            return None
        suf = (m.group(2) or "").lower()
        mult = 1
        if suf in ("к", "k"):
            mult = 1_000
        elif suf in ("кк", "kk", "m"):
            # "1кк" = 1_000_000; также допускаем "m" как миллион
            mult = 1_000_000
        elif suf in ("mm",):
            mult = 1_000_000_000
        amount = int(num * mult)
        return amount

    # Чистое число
    if re.match(r'^\d+$', s_clean):
        return int(s_clean)

    return None


def build_coefficient_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура коэффициентов — строго по скринам, 4 на ряд + последняя строка."""
    buttons = []
    row = []
    for idx, coef in enumerate(COEFFICIENTS):
        label = f"x{coef}"
        cb = f"coef:{coef}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if (idx + 1) % 4 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    # Последняя строка: ❌ Отменить и Честность 🗝️
    buttons.append([
        InlineKeyboardButton("❌ Отменить", callback_data="cancel"),
        InlineKeyboardButton("Честность 🗝️", callback_data="fairness"),
    ])
    return InlineKeyboardMarkup(buttons)


# -----------------------
# Логика игры (заглушки / места для интеграции)
# -----------------------
def get_user_balance(user_id: int) -> int:
    """
    Заглушка: вернуть баланс пользователя из БД.
    Заменить на реальную интеграцию.
    """
    # TODO: заменить на реальный запрос к БД
    return 100_000  # пример


def roll_random_multiplier() -> float:
    """
    Пример генерации множителя: чаще низкие множители.
    В продуктиве может быть заменено честным алгоритмом/seed.
    """
    x = random.random()
    max_m = min(1000, MAX_MULTIPLIER)
    m = 1.0 + (x ** 3) * (max_m - 1.0)
    return round(m, 2)


# -----------------------
# Формирование текстов (строго по скринам)
# -----------------------
def build_choice_message(user_id: int, user_name: Optional[str]) -> (str, InlineKeyboardMarkup):
    """
    Сообщение выбора коэффициента — заголовок, ставка (из БД) и инфоблок как на скрине.
    Возвращает (text, keyboard)
    """
    balance = get_user_balance(user_id)
    balance_fmt = format_amount(balance)
    title = "🚀 Краш · выбери коэфф."
    info = (
        f"🐾 Ставка: {balance_fmt} {CURRENCY_FULL}\n\n"
        f"ℹ️ Вы можете указать свой коэффициент (от 1.01 до {MAX_MULTIPLIER}), отправив число в ответ на это сообщение."
    )
    text = f"{title}\n\n{info}"
    keyboard = build_coefficient_keyboard()
    return text, keyboard


def build_result_message(user_name: Optional[str], stake: int, multiplier: float, win: Optional[int]) -> str:
    """
    Строит итоговое сообщение в точности по скрину:
    - при проигрыше: '🚀 Ракета упала на x1,69 🏳️\n❌ <mention> проиграл 20'000 m¢'
    - при выигрыше: '🚀 Ракета улетела на x1,05 📈\n✅ <mention> выиграл! Твой выигрыш составил 20'200 m¢'
    """
    name_html = mention_html(user_name)
    mul_s = format_multiplier(multiplier)
    stake_fmt = format_amount(stake)
    if win is None or win <= 0:
        # проигрыш
        text = f"🚀 Ракета упала на x{mul_s} 🏳️\n❌ {name_html} проиграл {stake_fmt} {CURRENCY_SHORT}"
    else:
        win_fmt = format_amount(win)
        text = f"🚀 Ракета улетела на x{mul_s} 📈\n✅ {name_html} выиграл! Твой выигрыш составил {win_fmt} {CURRENCY_SHORT}"
    return text


def build_info_message() -> str:
    """
    Информационный блок (правила/лимиты) — текст как в скрине.
    """
    max_stake_fmt = format_amount(MAX_STAKE)
    text = (
        "ℹ️ Краш — это игра, в которой нужно выбрать множитель и попытаться\n"
        "вывести ставку до того, как раунда упадёт ракета.\n\n"
        f"Лимиты:\n- RTP ~{RTP}%\n- Макс. множитель: x{MAX_MULTIPLIER}\n- Макс. ставка: {max_stake_fmt} {CURRENCY_SHORT}\n- Макс. выигрыш: {format_amount(MAX_STAKE * 10)} {CURRENCY_SHORT}\n\n"
        "Команды (пример):\n- /crash 100 1.1\n- краш 100 4\n\n"
        "Можно указывать суммы: 1к, 1кк, 80кк, 'пол', 'все'."
    )
    return text


# -----------------------
# Telegram-обработчики
# -----------------------
def start_handler(update: Update, context: CallbackContext):
    user = update.effective_user
    text = (
        f"Привет, {mention_html(user.first_name or user.username)}!\n\n"
        "Это игра «Краш» — интерфейс как на скриншотах.\n\n"
        f"{build_info_message()}"
    )
    update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def crash_command_handler(update: Update, context: CallbackContext):
    """
    Обработка команды /crash [ставка] [коэф?]
    Если ставка отсутствует — показать выбор коэффициента (кнопки).
    Если ставка есть — провести демо-раунд.
    """
    user = update.effective_user
    args = context.args or []
    balance = get_user_balance(user.id)
    stake = None
    coef_arg = None

    if len(args) >= 1:
        stake = parse_number_token(args[0], balance)
    if len(args) >= 2:
        # второй аргумент может быть множителем — заменить запятую на точку
        coef_arg = args[1].replace(',', '.')
        try:
            coef_arg = float(coef_arg)
        except Exception:
            coef_arg = None

    if stake is None:
        msg, keyboard = build_choice_message(user.id, user.first_name or user.username)
        update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
        return

    # проверка лимитов
    if stake < MIN_STAKE:
        update.message.reply_text(f"Минимальная ставка — {MIN_STAKE} {CURRENCY_SHORT}")
        return
    if stake > MAX_STAKE:
        update.message.reply_text(f"Максимальная ставка — {format_amount(MAX_STAKE)} {CURRENCY_SHORT}")
        return

    # демо-раунд: генерируем реальный multiplier
    multiplier = roll_random_multiplier()
    # если пользователь указал желаемый коэффициент как цель cashout, считаем выигрыш = stake * min(multiplier, goal)
    win = None
    # если пользователь указал целевой коэффициент и он <= multiplier -> выигрыш по цели
    if coef_arg:
        if multiplier >= coef_arg:
            win = int(stake * coef_arg)
        else:
            win = 0
    else:
        # без цели: считаем что игрок не зафиксировал cashout -> выигрыш только если multiplier > 1.0
        if multiplier > 1.0:
            win = int(stake * multiplier)
        else:
            win = 0

    if win == 0:
        win = None  # проигрыш

    text = build_result_message(user.first_name or user.username, stake, multiplier, win)
    update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def russian_crash_text_handler(update: Update, context: CallbackContext):
    """
    Обработка текстовых сообщений, начинающихся с 'краш' (без слеша), например:
    'краш 500 2' или 'краш 20к 1.01'
    """
    text = (update.message.text or "").strip()
    # матчим паттерн 'краш <arg1> <arg2?>'
    m = re.match(r'^(?i:краш)\b(?:\s+(.+?))?(?:\s+(.+))?$', text)
    if not m:
        # не наш случай — передаем дальше
        return
    arg1 = m.group(1)
    arg2 = m.group(2)
    user = update.effective_user
    balance = get_user_balance(user.id)

    if not arg1:
        # показываем выбор
        msg, keyboard = build_choice_message(user.id, user.first_name or user.username)
        update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
        return

    stake = parse_number_token(arg1, balance)
    coef_arg = None
    if arg2:
        try:
            coef_arg = float(arg2.replace(',', '.'))
        except Exception:
            coef_arg = None

    # в остальном поведение как в /crash
    if stake is None:
        update.message.reply_text("Не понял ставку. Можно: 1к, 1кк, 80кк, пол, все или число.")
        return
    if stake < MIN_STAKE:
        update.message.reply_text(f"Минимальная ставка — {MIN_STAKE} {CURRENCY_SHORT}")
        return
    if stake > MAX_STAKE:
        update.message.reply_text(f"Максимальная ставка — {format_amount(MAX_STAKE)} {CURRENCY_SHORT}")
        return

    multiplier = roll_random_multiplier()
    win = None
    if coef_arg:
        if multiplier >= coef_arg:
            win = int(stake * coef_arg)
        else:
            win = 0
    else:
        if multiplier > 1.0:
            win = int(stake * multiplier)
        else:
            win = 0
    if win == 0:
        win = None
    text = build_result_message(user.first_name or user.username, stake, multiplier, win)
    update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def callback_query_handler(update: Update, context: CallbackContext):
    """Обработка нажатий по кнопкам коэффициентов и других кнопок."""
    query = update.callback_query
    data = query.data or ""
    user = query.from_user

    if data.startswith("coef:"):
        try:
            coef = float(data.split(":", 1)[1])
        except Exception:
            coef = None
        if coef is None:
            query.answer("Ошибка коэффициента")
            return
        balance = get_user_balance(user.id)
        # для быстрого ответа берем автоматическую ставку (например 1/10 баланса) — в реальной интеграции можно хранить выбранную ставку
        stake = max(1, balance // 10)
        multiplier = roll_random_multiplier()
        # считаем выигрыш: если multiplier >= coef -> выигрыш stake * coef, иначе проигрыш
        if multiplier >= coef:
            win = int(stake * coef)
        else:
            win = None
        text = build_result_message(user.first_name or user.username, stake, multiplier, win)
        try:
            query.answer()
            query.edit_message_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            # если не получилось редактировать (например, сообщение уже изменено), просто отправим новое
            query.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return

    if data == "cancel":
        query.answer("Ставка отменена")
        try:
            query.edit_message_text("Ставка отменена ❌")
        except Exception:
            query.message.reply_text("Ставка отменена ❌")
        return

    if data == "fairness" or data == "Честность 🗝️":
        info = f"🔑 Честность: RTP ~{RTP}%"
        query.answer()
        try:
            query.edit_message_text(info)
        except Exception:
            query.message.reply_text(info)
        return

    # fallback
    query.answer()


# -----------------------
# Регистрация обработчиков
# -----------------------
def register_crash_handlers(dispatcher):
    """
    Регистрирует все обработчики в переданном dispatcher (python-telegram-bot).
    Вызови из main.py: register_crash_handlers(dp)
    """
    dispatcher.add_handler(CommandHandler("start", start_handler))
    dispatcher.add_handler(CommandHandler("crash", crash_command_handler))
    # Текстовые сообщения, начинающиеся с 'краш' (русский без слеша)
    dispatcher.add_handler(MessageHandler(Filters.regex(r'^(?i:краш)\b'), russian_crash_text_handler))
    # Обычные текстовые сообщения — если это просто число/ставка
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, russian_crash_text_handler))
    dispatcher.add_handler(CallbackQueryHandler(callback_query_handler))


# -----------------------
# Тестовая отправка (не выполняется автоматически)
# -----------------------
def send_test_message(bot, chat_id):
    """
    Отправляет тестовое сообщение (используй только если хочешь отослать вручную).
    bot — экземпляр telegram.Bot или dispatcher.bot
    chat_id — числовой chat_id или '@username'
    """
    text = "Тестовое сообщение от crash модуля."
    bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


# -----------------------
# Если модуль запускать напрямую (для локального теста)
# -----------------------
if __name__ == "__main__":
    print("Этот файл — модуль. Импортируй и вызывай register_crash_handlers(dispatcher) из main.py.")
