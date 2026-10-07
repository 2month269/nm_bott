# main.py
import os
import html
import time
import asyncio
import logging
import math
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, TelegramObject, ReplyParameters, LinkPreviewOptions
from aiogram.filters import CommandStart, CommandObject, Command, StateFilter
from aiogram.fsm.context import FSMContext 
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- ИМПОРТЫ ВСЕХ ИГРОВЫХ И СИСТЕМНЫХ РОУТЕРОВ ---
from game import router as mines_router         # Игра "Мины"
from crash import router as crash_router       # Игра "Краш"
from dice import router as dice_router         # Игра "Кубик"
from darts import router as darts_router       # Игра "Дартс"
from profile import router as profile_router   # Модуль профиля пользователя
from slots import router as slots_router       # Игра "Слоты"
from admin import router as admin_router       # Модуль админ-панели
from coin import router as coin_router         # Игра "Монетка"
from bonus import router as bonus_router       # Модуль ежедневных бонусов
from basketball import router as basketball_router # Игра "Баскетбол"
from bank import router as bank_router         # Модуль банка/депозитов
from cheques import router as cheques_router, ChequeState # Модуль чеков
from tower import router as tower_router       # Игра "Башня"
from frog import router as frog_router         # Игра "Квак"
from exchange import router as exchange_router # Модуль P2P-обменника
from ref import router as ref_router           # Модуль реферальной системы
from sharik import router as sharik_router     # Игра "Шарик"
from hypercar import router as hypercar_router # Игра "Гиперкар"
from smart import router as smart_router       # Игра "Всезнайка"
from tournament import router as tournament_router # Модуль еженедельного турнира идей
from stairs_game import router as stairs_router, StairsState # Игра "Лесенка"
from ochko import router as ochko_router       # Игра "21 / Очко"
from roulette import router as roulette_router # Игра "Рулетка"
from duels import router as duels_router       # Модуль P2P Кибер-Дуэлей
from heist_game import router as heist_router, HeistState, HEIST_BANNERS # Игра "Ограбление Банка"
from artifact_game import router as artifact_router, ArtifactState, ARTIFACT_BANNERS # Игра "Древний Артефакт"
from market import router as market_router     # Модуль игрового Маркета и Кирпича
from p2p_nft import router as p2p_nft_router   # Модуль P2P NFT Маркетплейса
from rules import router as rules_router       # Модуль правил группы и бота
from gold_game import router as gold_router, GoldState # Игра "Золото"
from diamond import router as diamond_router # алмазы
from promote import router as promote_router   # Модуль Рекламы и Заработок NMP (Promote)
from cases import router as cases_router       # Модуль игровых кейсов и сундуков
from syndicates import router as syndicates_router, init_syndicate_db  # Модуль Синдикатов
from pyramid_game import router as pyramid_router # пирамида
from football import router as football_router # Игра "Футбол"
from lottery import router as lottery_router # Модуль Лотереи
from star_game import router as star_router # Игра "Звездная Башня"
from pvp_mines import router as pvp_mines_router #в чате игра
from donate import router as donate_router

import db          # Модуль для работы с базой данных
import utils       # Модуль вспомогательных утилит

EMOJI_KRES = '<tg-emoji emoji-id="5785177332595561481">❌</tg-emoji>'
EMOJI_ASD = '<tg-emoji emoji-id="5767137507879685567">💎</tg-emoji>'
EMOJI_ASE = '<tg-emoji emoji-id="6028477497518068483">🌟</tg-emoji>'
EMOJI_AQD = '<tg-emoji emoji-id="5201873447554145566">💵</tg-emoji>'
EMOJI_SSD = '<tg-emoji emoji-id="5348206131539885172">💣</tg-emoji>'
EMOJI_APD = '<tg-emoji emoji-id="5411474818035909166">⚔️</tg-emoji>'
EMOJI_AQSD = '<tg-emoji emoji-id="5363957533255937425">🗿</tg-emoji>'
EMOJI_ASVD = '<tg-emoji emoji-id="6035239240625820254">🆔</tg-emoji>'
EMOJI_AXSD = '<tg-emoji emoji-id="5339270838627625732">👤</tg-emoji>'
EMOJI_AXSAD = '<tg-emoji emoji-id="5456140674028019486">⚡️</tg-emoji>'
EMOJI_ARXSD = '<tg-emoji emoji-id="5350612670435313545">🕹</tg-emoji>'
EMOJI_AXZD = '<tg-emoji emoji-id="5278276646552503661">🏆</tg-emoji>'
EMOJI_D = '<tg-emoji emoji-id="5402186569006210455">💱</tg-emoji>'
EMOJI_APD_2 = '<tg-emoji emoji-id="5203993413346680064">📊</tg-emoji>'
EMOJI_ATTD = '<tg-emoji emoji-id="5251443675161976035">🗓</tg-emoji>'
EMOJI_AXWWSD_DOC = '<tg-emoji emoji-id="5199750217586459631">📄</tg-emoji>'
EMOJI_AXWWSD = '<tg-emoji emoji-id="5231200819986047254">📊</tg-emoji>'
EMOJI_AXQWSD = '<tg-emoji emoji-id="5017157809075127025">🕹️</tg-emoji>'
EMOJI_AXEWSD = '<tg-emoji emoji-id="5980930633298350051">✅</tg-emoji>'
EMOJI_AXRWSD = '<tg-emoji emoji-id="5785177332595561481">❌</tg-emoji>'
EMOJI_ATWWSD = '<tg-emoji emoji-id="5801004944211317728">🥇</tg-emoji>'
EMOJI_AXYWSD = '<tg-emoji emoji-id="5800934502452696630">🥈</tg-emoji>'
EMOJI_AXUWSD = '<tg-emoji emoji-id="5303470641242978062">🥉</tg-emoji>'
EMOJI_AXIWSD = '<tg-emoji emoji-id="5990147899403539264">💰</tg-emoji>'
EMOJI_AXWOSD = '<tg-emoji emoji-id="5463172695132745432">📦</tg-emoji>'
EMOJI_APWWSD = '<tg-emoji emoji-id="6084717714847306634">📌</tg-emoji>'
EMOJI_APXWSD = '<tg-emoji emoji-id="5785281906459283269">🎁</tg-emoji>'
EMOJI_APXWZD = '<tg-emoji emoji-id="5462910521739063094">👋</tg-emoji>'
EMOJI_APXWMD = '<tg-emoji emoji-id="5780773956030043338">🚀</tg-emoji>'
EMOJI_DT = '<tg-emoji emoji-id="5231102735817918643">👇</tg-emoji>'

# Дневной лимит переводов NMP
DAILY_NMP_LIMIT = 100.0

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logger.critical("Переменная окружения BOT_TOKEN не установлена! Бот не может быть запущен.")
    raise ValueError("Критическая ошибка: Переменная окружения BOT_TOKEN не установлена в настройках Railway!")

# Настраиваем у бота HTML-парсинг по умолчанию, чтобы эмодзи гарантированно отображались
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()


async def safe_edit_or_resend(callback: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML"):
    """Универсальная безопасная функция для сообщений (корректно работает и с фото, и с обычным текстом)"""
    try:
        if callback.message and callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"Ошибка редактирования сообщения, отправляем новое: {e}")
        try:
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass


def format_ncoin_display(value: float) -> str:
    """Округляет баланс до целого без копеек с разделителем запятой"""
    val_int = int(math.floor(float(value or 0)))
    return f"{val_int:,}"


# --- MIDDLEWARE: БЛОКИРОВКА ПОЛЬЗОВАТЕЛЕЙ И СБРОС СОСТОЯНИЙ FSM ---
class BlockAndFsmBypassMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        state = data.get("state")
        
        if user:
            if db.is_user_blocked(user.id):
                if isinstance(event, Message):
                    await event.answer(f"{EMOJI_KRES} <b>Ваш аккаунт заблокирован администрацией!</b>", parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ Ваш аккаунт заблокирован!", show_alert=True)
                return
            
            current_state = await state.get_state()
            if current_state is not None:
                # ИСКЛЮЧЕНИЯ ИЗ АВТОСБРОСА
                if any(st in str(current_state) for st in [
                    "ChequeState", "waiting_for_claim_password", "waiting_for_idea", 
                    "StairsState", "OchkoStates", "HeistState", "ArtifactState", 
                    "GoldState", "PromoteState", "P2PNFTState", "DonateState"
                ]):
                    return await handler(event, data)
                
                text_trigger_words = [
                    "мины", "краш", "кубик", "дартс", "слоты", "монетка", "реф", "рефералы", "шарик", "гиперкар", "гмп", "всезнайка", "телевизор",
                    "алмазы", "алмаз", "/diamond", "пирамида", "пирамид", "/pyramid",
                    "баскетбол", "бонус", "профиль", "баланс", "б", "банк", "чеки", "башня", "квак", "обменник", "история", "список",
                    "игры", "помощь", "синдикат", "синдикаты", "клан", "районы", "донат", "топ", "/cancel", "отмена", "лесенка", "очко", "21", "рулетка", "рул", "дуэль", "дуэлька", "duel",
                    "ограбление", "хейст", "heist", "артефакт", "artifact", "маркет", "инвентарь", "кирпич", "правила", "/regulation", "золото", "/gold",
                    "реклама", "продвижение", "раскрутка", "пиар", "задания", "promote", "p2p", "п2п", "/p2p", "поинт", "/point", "Поинт",
                    "/start", "/profile", "/admin", "/bonus", "/bank", "/syndicate", "/cheques", "/game", "/help", "/exchange", "/donate", "/ref", "/history", "/spisok", "/stairs", "/duel", "/heist", "/artifact", "/market", "/inventory", "/promote", "футбол", "фут", "/football", "лотерея", "лото", "/lottery", "звездная игра", "star game", "/star", "/star_game", "поинт", "/point"
                ]
                
                callback_trigger_phrases = [
                    "games_menu", "help_menu", "back_to_start", "mine_menu", "sharik_menu_inline", "hypercar_menu_inline", "smart_menu_inline", "pyramid_",
                    "adm_", "ex_", "syn_", "bonus", "claim", "deposit", "profile", "games_page_", "hist_", "tourn_", "roulette_", "duel_", "heist_", "artifact_", "buy_brick", "show_inventory", "open_market_cb", "gold_", "diamond_", "p2p_", "football_", "lottery", "donate_"
                ]

                if isinstance(event, Message) and event.text:
                    text_lower = event.text.lower().strip()
                    if any(text_lower.startswith(word) for word in text_trigger_words):
                        await state.clear()
                        
                elif isinstance(event, CallbackQuery) and event.data:
                    data_str = event.data.lower()
                    if any(phrase in data_str for phrase in callback_trigger_phrases):
                        await state.clear()
        
        return await handler(event, data)


# --- ФУНКЦИЯ АВТО-ОТМЕНЫ СЕССИЙ (КНОПКА /CANCEL) ---

@router.message(Command("cancel"))
@router.message(F.text.lower().in_(["отмена", "cancel"]))
@router.callback_query(F.data == "force_cancel_state")
async def process_cancel_command(event: TelegramObject, state: FSMContext):
    await state.clear()
    text = (
        "🔄 <b>Все активные игровые сессии и ожидания сброшены!</b>\n"
        "Вы можете свободно начать новую игру или воспользоваться меню."
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML")
    else:
        await event.answer("Отменено")
        await safe_edit_or_resend(event, text, reply_markup=get_games_keyboard_page1(), parse_mode="HTML")


# --- ОБРАБОТКА БАЛАНСА С ОТОБРАЖЕНИЕМ ФОТО NFT ---

def format_short_number(num: float) -> str:
    """Форматирует числа в вид k / kk / kkk, как на скриншоте."""
    num = float(num or 0)
    abs_num = abs(num)
    if abs_num >= 1_000_000_000:
        val = num / 1_000_000_000
        return f"{val:.2f}kkk".rstrip("0").rstrip(".") if val % 1 else f"{int(val)}kkk"
    elif abs_num >= 1_000_000:
        val = num / 1_000_000
        return f"{val:.2f}kk".rstrip("0").rstrip(".") if val % 1 else f"{int(val)}kk"
    elif abs_num >= 1_000:
        val = num / 1_000
        return f"{val:.2f}k".rstrip("0").rstrip(".") if val % 1 else f"{int(val)}k"
    return str(int(num))


def format_apostrophe(val: float) -> str:
    """Форматирует число с апострофом в виде разделителя (322'277)."""
    val = float(val or 0)
    return f"{int(val):,}".replace(",", "'")


@router.message(StateFilter(None), F.text.lower().in_(["б", "баланс"]))
async def show_balance(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_data = db.get_user(user_id) or {}
    
    equipped_nft = db.get_equipped_nft(user_id)
    
    balance_str = format_apostrophe(user_data.get("balance", 0))
    games_played = user_data.get("games_played", 0)
    duels_won = user_data.get("duels_won", 0)
    lost_coins_str = format_short_number(user_data.get("lost_coins", 0))

    caption_text = (
        f"{EMOJI_AQD} Баланс: {balance_str} nCoin\n"
        "· · · · · · · · · · · · · · · · · · · · ·\n"
        f"{EMOJI_SSD} Сыграно игр: {games_played}\n"
        f"{EMOJI_APD} Выиграно дуэлей: {duels_won}\n"
        f"{EMOJI_AQSD} Проиграно nCoin: {lost_coins_str}"
    )
    
    if equipped_nft:
        from market import DRAGO_IMAGES
        nft_photo_url = DRAGO_IMAGES.get(equipped_nft.get("image_key"), DRAGO_IMAGES["base_green"])
        
        hidden_link = f'<a href="{nft_photo_url}">&#8203;</a>'
        full_text = f"{hidden_link}{caption_text}"

        try:
            await message.answer(
                text=full_text,
                reply_to_message_id=message.message_id,
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(
                    is_disabled=False,
                    url=nft_photo_url,
                    prefer_large_media=True,
                    show_above_text=True
                )
            )
            return
        except Exception as e:
            logger.error(f"Ошибка при отправке превью NFT в балансе: {e}")

    await message.answer(
        caption_text,
        reply_to_message_id=message.message_id,
        parse_mode="HTML"
    )

# --- КОМАНДА /POINT ---

@router.message(StateFilter(None), Command("point", "поинт", "Поинт"))
async def show_point(message: Message, state: FSMContext):
    await state.clear()

    user = db.get_user(message.from_user.id)
    point_balance = int(user.get("nmp_balance", 0) or 0)

    text = (
        f"{EMOJI_ASD * 5}\n"
        f"Баланс: {point_balance} GMP\n"
        "· · · · · · · · · · · · · · · · · · · · ·\n"
        "<blockquote>"
        '<tg-emoji emoji-id="5472250091332993630">💳</tg-emoji> '
        "Лимит на перевод 100 GMP/д."
        "</blockquote>"
    )

    await message.answer(text, parse_mode="HTML")
    
# --- ОБРАБОТКА ПРОФИЛЯ С ОТОБРАЖЕНИЕМ ФОТО NFT ---
@router.message(StateFilter(None), Command("profile"))
@router.message(StateFilter(None), F.text.lower().in_(["профиль", "profile", "п", "проф"]))
async def show_profile(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id) or {}
    rank = db.get_user_rank(user_id)
    
    equipped_nft = db.get_equipped_nft(user_id)
    
    profile_photo_url = "https://i.ibb.co/p6kZ2PNh/IMG-20260822-175450-939.jpg"
    if equipped_nft:
        from market import DRAGO_IMAGES
        profile_photo_url = DRAGO_IMAGES.get(equipped_nft.get("image_key"), profile_photo_url)
    
    name = html.escape(message.from_user.first_name or "Игрок")
    balance_ncoin = format_apostrophe(user.get('balance', 0))
    balance_gmp = int(user.get('nmp_balance', 0) or 0)
    games = user.get('games_played', 0)
    turnover = format_short_number(user.get('turnover', 0))
    lost = format_short_number(user.get('lost_coins', 0))
    reg_date = user.get('created_at', '19-05-2025 12:21')
    rank_str = f"{rank:,}".replace(",", " ")
    
    hidden_link = f'<a href="{profile_photo_url}">&#8203;</a>'

    full_text = (
        f"{hidden_link}"
        f"{EMOJI_ASVD} Профиль: {user_id}\n"
        f"⠀\n"
        f' <a href="tg://user?id={user_id}"><b>{name}</b></a>\n'
        f"{EMOJI_AXSAD} Статус: Игрок\n"
        f"{EMOJI_ARXSD} Сыграно игр: {games}\n"
        f"{EMOJI_AXZD} Место в топе: {rank_str}\n"
        f"{EMOJI_D} Оборот: {turnover} n¢\n"
        f"{EMOJI_APD} Проиграно: {lost} n¢\n\n"
        f"<blockquote>{EMOJI_ATTD} Дата регистрации: {reg_date} ❞</blockquote>\n\n"
        f"{EMOJI_AQD} Баланс: {balance_ncoin} nCoin\n"
        f"{EMOJI_ASD} Баланс: {balance_gmp} NMPOINT"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="back_to_start", style="danger")]
    ])
    
    try:
        await message.answer(
            text=full_text,
            reply_markup=kb,
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(
                is_disabled=False,
                url=profile_photo_url,
                prefer_large_media=True,
                show_above_text=True
            )
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке профиля: {e}")
        await message.answer(full_text, reply_markup=kb, parse_mode="HTML")
        
# === ИСТОРИЯ И СТАТИСТИКА ИГР ===

def get_history_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 История игр", callback_data="hist_games_log", style="primary"),
            InlineKeyboardButton(text="Статистика 📊", callback_data="hist_stats_summary", style="primary")
        ]
    ])

@router.message(StateFilter(None), F.text.lower().in_(["история", "/history", "история игр"]))
async def show_history_menu(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "🕓 <b>НЕДАВНИЕ ИГРЫ</b>\n"
        "·····················\n"
        "ℹ️ Вы можете просмотреть свои недавние игры и продолжить запущенные. "
        "Если вы запускали игру более 12 часов назад, она завершилась, и ставка была возвращена на ваш баланс."
    )
    await message.answer(text, reply_markup=get_history_main_kb(), parse_mode="HTML")

@router.callback_query(F.data == "hist_games_log")
async def show_games_log_callback(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    try:
        history = db.get_user_game_history(user_id, hours=48)
    except Exception as e:
        logger.error(f"Ошибка загрузки истории игр: {e}")
        history = []

    text = (
        f"{EMOJI_AXWWSD} <b>ИСТОРИЯ ИГР ЗА ПОСЛЕДНИЕ 48 ЧАСОВ</b>\n"
        "·························\n\n"
    )

    if not history:
        text += (
            "За последние 48 часов игр не найдено.\n"
            "Сыграйте в любую игру из лобби!"
        )
    else:
        for item in history[:20]:
            game_name = item.get("game_name", "Игра")
            bet = float(item.get("bet", 0) or 0)
            is_win = bool(item.get("is_win", False))
            date_str = item.get("date", "")

            result = "🟢 выигрыш" if is_win else "🔴 проигрыш"

            text += (
                f"• <b>{game_name}</b> | "
                f"Ставка: <b>{format_ncoin_display(bet)}</b> | "
                f"{result} <i>{date_str}</i>\n"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="hist_stats_summary", style="primary")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start", style="danger")]
        ]
    )

    await safe_edit_or_resend(callback, text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "hist_stats_summary")
async def show_stats_summary_callback(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    try:
        stats = db.get_user_game_percentages(user_id, 48)

        total = int(stats.get("total", 0))
        wins = int(stats.get("wins", 0))
        losses = int(stats.get("losses", 0))
        win_percent = float(stats.get("win_percent", 0))
        loss_percent = float(stats.get("loss_percent", 0))

        win_blocks = round(win_percent / 25)
        loss_blocks = round(loss_percent / 25)

        win_blocks = max(0, min(4, win_blocks))
        loss_blocks = max(0, min(4, loss_blocks))

        win_bar = "🟩" * win_blocks + "⬜️" * (4 - win_blocks)
        loss_bar = "🟥" * loss_blocks + "⬜️" * (4 - loss_blocks)

        text = (
            f"{EMOJI_AXWWSD} <b>СТАТИСТИКА ИГРОКА</b>\n"
            "⠀\n\n"
            f"{EMOJI_AXQWSD} Всего игр за 48 часов: <b>{total}</b>\n"
            f"{EMOJI_AXEWSD} Побед: <b>{wins}</b>\n"
            f"{EMOJI_AXRWSD} Поражений: <b>{losses}</b>\n\n"
            f"Процент побед: {win_bar} <b>{win_percent:.1f}%</b>\n"
            f"Процент поражений: {loss_bar} <b>{loss_percent:.1f}%</b>"
        )

    except Exception as e:
        logger.exception("Ошибка при открытии статистики: %s", e)
        text = (
            "❌ <b>Не удалось загрузить статистику.</b>\n\n"
            "Попробуйте нажать кнопку ещё раз."
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 История игр", callback_data="hist_games_log")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
        ]
    )

    await safe_edit_or_resend(callback, text, reply_markup=keyboard, parse_mode="HTML")


@router.message(F.text.lower().in_({"топ", "/top"}))
async def show_world_top_msg(message: Message, state: FSMContext):
    await state.clear()
    db.get_user(
        user_id=message.from_user.id, 
        first_name=message.from_user.first_name, 
        username=message.from_user.username
    )
    await show_world_top(message)

def format_top_balance(val: float) -> str:
    val = float(val or 0)
    if val >= 1_000_000_000_000:
        return f"{val / 1_000_000_000_000:.2f}kkkk"
    elif val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.2f}kkk"
    elif val >= 1_000_000:
        return f"{val / 1_000_000:.2f}kk"
    elif val >= 1_000:
        return f"{val / 1_000:.2f}k"
    else:
        return f"{int(val):,}".replace(",", "'")

def format_user_balance(val: float) -> str:
    val = float(val or 0)
    return format_ncoin_display(val).replace(",", "'")

async def show_world_top(event: TelegramObject):
    try:
        top_players = db.get_top_players(10)

        title = f"{EMOJI_AXZD} <b>МИРОВОЙ ТОП ПО NCOIN</b>\n\n"

        if not top_players:
            top_text = "Пока в топе нет игроков."
        else:
            medals = [f"{EMOJI_ATWWSD}", f"{EMOJI_AXYWSD}", f"{EMOJI_AXUWSD}", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
            lines = []
            for i, player in enumerate(top_players):
                p_id, p_bal, p_nmp, p_fname, p_uname = player[0], player[1], player[2], player[3], player[4]
                
                p_name = (p_fname or "").strip()
                if not p_name and p_uname:
                    p_name = f"@{p_uname.strip()}"
                
                if not p_name:
                    try:
                        chat = await bot.get_chat(p_id)
                        if chat.first_name:
                            p_name = chat.first_name.strip()
                            db.update_user_field(p_id, "first_name", p_name)
                        if chat.username:
                            db.update_user_field(p_id, "username", chat.username.strip())
                            if not p_name:
                                p_name = f"@{chat.username.strip()}"
                    except Exception:
                        pass
                
                if not p_name:
                    p_name = f"Пользователь"

                if len(p_name) > 20:
                    p_name = p_name[:18] + "..."
                p_name_escaped = html.escape(p_name)
                bal_str = format_top_balance(p_bal)
                lines.append(f"{medals[i]} {p_name_escaped} | {bal_str} n¢")

            top_text = "\n".join(lines)

        user_id = event.from_user.id
        user_rank = db.get_user_rank(user_id)
        user_data = db.get_user(user_id)
        
        u_name = (
            user_data.get('first_name') or 
            getattr(event.from_user, 'first_name', '') or 
            user_data.get('username') or 
            getattr(event.from_user, 'username', '') or 
            "Пользователь"
        ).strip()

        if len(u_name) > 20:
            u_name = u_name[:18] + "..."
        u_name_escaped = html.escape(u_name)
        u_bal_str = format_user_balance(user_data.get('balance', 0))

        user_line = f"<blockquote>{user_rank}. 🎖️ {u_name_escaped} | {u_bal_str} nCoin</blockquote>"

        full_text = f"{title}{top_text}\n\n{user_line}"

        if isinstance(event, Message):
            await event.answer(full_text, parse_mode="HTML")
        elif isinstance(event, CallbackQuery) and event.message:
            await safe_edit_or_resend(event, full_text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Ошибка при выводе топа: %s", e)

        if isinstance(event, Message):
            await event.answer("❌ Не удалось загрузить мировой топ.")
        elif isinstance(event, CallbackQuery):
            await event.answer("❌ Не удалось загрузить мировой топ.", show_alert=True)
    
# --- СИСТЕМА ПЕРЕВОДОВ В ЧАТАХ (ОТВЕТОМ НА СООБЩЕНИЕ) ---

@router.message(StateFilter(None), F.chat.type.in_({"group", "supergroup"}), F.text.lower().startswith("дать"))
async def group_give_coins(message: Message):
    if not message.reply_to_message:
        await message.reply("❌ Эта команда должна быть ответом (reply) на сообщение пользователя, которому вы хотите передать nCoin!")
        return
    
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply("❌ Неверный формат! Используйте: `дать <кол-во>` (в ответ на сообщение)")
        return
        
    sender_id = message.from_user.id
    target_id = message.reply_to_message.from_user.id
    
    if sender_id == target_id:
        await message.reply("❌ Вы не можете переводить nCoin самому себе!")
        return
        
    sender = db.get_user(sender_id)
    amount_str = parts[1]
    
    try:
        amount = utils.parse_bet_input(amount_str, sender["balance"])
    except TypeError:
        amount = utils.parse_bet_input(amount_str)
        
    if amount <= 0:
        await message.reply("❌ Сумма перевода должна быть больше 0 nCoin!")
        return
        
    if sender["balance"] < amount:
        await message.reply(f"❌ Недостаточно nCoin! Твой баланс: *{format_ncoin_display(sender['balance'])} nCoin*")
        return
        
    fee = round(amount * 0.10, 2)
    received = round(amount - fee, 2)
    
    db.update_balance(sender_id, -amount)
    db.update_balance(target_id, received)
    
    sender_name = message.from_user.first_name
    target_name = message.reply_to_message.from_user.first_name
    
    await message.answer(
        f"{EMOJI_AXIWSD} <b>Успешный перевод nCoin!</b> {EMOJI_AXIWSD}\n"
        f"·························\n"
        f'{EMOJI_AXSD} Отправитель: <a href="tg://user?id={sender_id}">{sender_name}</a>\n'
        f'{EMOJI_AXSD} Получатель: <a href="tg://user?id={target_id}">{target_name}</a>\n'
        f"{EMOJI_AXIWSD} Отправлено: <b>{format_ncoin_display(amount)} nCoin</b>\n"
        f"{EMOJI_AQD} Комиссия (10%): <b>{format_ncoin_display(fee)} nCoin</b>\n"
        f"{EMOJI_AXWOSD} Получатель получил: <b>{format_ncoin_display(received)} nCoin</b>",
        parse_mode="HTML"
    )

@router.message(StateFilter(None), F.chat.type.in_({"group", "supergroup"}), F.text.lower().startswith("перевод"))
async def group_transfer_nmp(message: Message):
    if not message.reply_to_message:
        await message.reply("❌ Эта команда должна быть ответом (reply) на сообщение пользователя, которому вы хотите передать NMP!")
        return
    
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply("❌ Неверный формат! Используйте: `перевод <кол-во>` (в ответ на сообщение)")
        return
        
    sender_id = message.from_user.id
    target_id = message.reply_to_message.from_user.id
    
    if sender_id == target_id:
        await message.reply("❌ Вы не можете переводить NMP самому себе!")
        return
        
    sender = db.get_user(sender_id)
    amount_str = parts[1]
    
    try:
        amount = utils.parse_bet_input(amount_str, sender["nmp_balance"])
    except TypeError:
        amount = utils.parse_bet_input(amount_str)
        
    if amount <= 0:
        await message.reply("❌ Количество NMP для перевода должно быть больше 0!")
        return
        
    if sender["nmp_balance"] < amount:
        await message.reply(f"❌ Недостаточно NMP! Твой баланс: *{sender['nmp_balance']:,} NMP*")
        return
        
    db.update_nmp_balance(sender_id, -amount)
    db.update_nmp_balance(target_id, amount)
    
    sender_name = message.from_user.first_name
    target_name = message.reply_to_message.from_user.first_name

    await message.answer(
        f"{EMOJI_ASD} *Успешный перевод NMP!* {EMOJI_ASD}\n"
        f"·························\n"
        f"{EMOJI_AXSD} Отправитель: [{sender_name}](tg://user?id={sender_id})\n"
        f"{EMOJI_AXSD} Получатель: [{target_name}](tg://user?id={target_id})\n"
        f"{EMOJI_ASD} Количество: *{amount:,} NMP*",
        parse_mode="Markdown"
    )


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ПОИСКА ПОЛЬЗОВАТЕЛЯ ПО ID ИЛИ USERNAME ---
def get_target_user(identifier: str):
    """Ищет пользователя в БД по ID или @username"""
    clean_str = identifier.strip().lstrip("@").strip()
    
    if clean_str.isdigit():
        target_id = int(clean_str)
        conn = db.get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (target_id,))
            row = cursor.fetchone()
            if row:
                user = db.get_user(target_id)
                if user:
                    user["user_id"] = target_id
                    return user
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя по ID {target_id}: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        uname_lower = clean_str.lower()
        cursor.execute("""
            SELECT user_id FROM users 
            WHERE LOWER(username) = %s OR LOWER(username) = %s
        """, (uname_lower, f"@{uname_lower}"))
        
        row = cursor.fetchone()
        if row:
            target_id = row[0]
            user = db.get_user(target_id)
            if user:
                user["user_id"] = target_id
                return user
        return None
    except Exception as e:
        logger.error(f"Ошибка поиска пользователя по username {identifier}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def fmt_q(val: float) -> str:
    """Выводит баланс целым числом с апострофом без копеек"""
    val_int = int(math.floor(float(val or 0)))
    return f"{val_int:,}".replace(",", "'")


# --- ПЕРЕВОД nCoin ("Дать") ---
@router.message(StateFilter(None), F.chat.type == "private", F.text.lower().startswith("дать"))
async def private_give_coins(message: Message, bot: Bot):
    parts = message.text.strip().split(maxsplit=3)
    
    if len(parts) < 3:
        await message.reply(
            "❌ <b>Неверный формат!</b>\n\n"
            "📌 <b>Используйте:</b> <code>Дать &lt;кол-во&gt; &lt;ID или @username&gt; [сообщение]</code>\n"
            "• По ID: <code>дать 40к 7727345054</code>\n"
            "• По юзернейму: <code>дать 40к @nmproda</code>",
            parse_mode="HTML"
        )
        return

    sender_id = message.from_user.id
    amount_str = parts[1]
    target_input = parts[2]

    target = get_target_user(target_input)
    if not target:
        await message.reply("❌ <b>Пользователь с таким ID или Username не найден!</b>", parse_mode="HTML")
        return

    target_id = target["user_id"]
    if sender_id == target_id: 
        await message.reply("❌ <b>Вы не можете переводить nCoin самому себе!</b>", parse_mode="HTML")
        return

    sender = db.get_user(sender_id)
    try: 
        amount = utils.parse_bet_input(amount_str, sender["balance"])
    except (TypeError, ValueError):
        await message.reply("❌ <b>Некорректная сумма перевода!</b>", parse_mode="HTML")
        return

    if amount <= 0:
        await message.reply("❌ <b>Сумма перевода должна быть больше 0 nCoin!</b>", parse_mode="HTML")
        return

    old_balance = sender["balance"]
    if old_balance < amount:
        await message.reply(f"❌ <b>Недостаточно nCoin!</b> Ваш баланс: <b>{fmt_q(old_balance)} nCoin</b>", parse_mode="HTML")
        return

    fee = round(amount * 0.10, 2)
    received = round(amount - fee, 2)
    new_balance = old_balance - amount

    sender_first_name = html.escape(message.from_user.first_name or "Игрок")
    target_first_name = html.escape(target.get("first_name") or target.get("username") or f"Игрок {target_id}")

    db.update_balance(sender_id, -amount)
    db.update_balance(target_id, received)

    sender_msg = (
        f'<tg-emoji emoji-id="5462881955911584183">➡️</tg-emoji> <b>{sender_first_name}</b> передал(-а) <b>{fmt_q(amount)} n¢</b> игроку <b>{target_first_name}</b>.\n'
        f'<tg-emoji emoji-id="5472250091332993630">💸</tg-emoji> Комиссия: <b>{fmt_q(fee)} n¢</b>\n'
        '· · · · · · · · · · · · · · · · · · · · ·\n'
        f'<tg-emoji emoji-id="5463046637842608206">💰</tg-emoji> Баланс: <b>{fmt_q(old_balance)} → {fmt_q(new_balance)} n¢</b>'
    )
    await message.reply(sender_msg, parse_mode="HTML")

    try: 
        notify_msg = f'✅ Поступил перевод в размере <b>{fmt_q(received)} nCoin</b> от <b>{sender_first_name}</b>.'
        await bot.send_message(target_id, notify_msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление о переводе получателю {target_id}: {e}")


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С ДНЕВНЫМ ЛИМИТОМ В БД ---

def get_nmp_transferred_today(user_id: int) -> float:
    """Возвращает сумму NMP, переведённую пользователем за текущие сутки"""
    conn = db.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_nmp_limits (
                user_id BIGINT PRIMARY KEY,
                amount_transferred DOUBLE PRECISION DEFAULT 0,
                last_transfer_day VARCHAR(20)
            )
        """)
        conn.commit()

        today_str = time.strftime("%Y-%m-%d")
        cursor.execute("SELECT amount_transferred, last_transfer_day FROM daily_nmp_limits WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()

        if not row or row[1] != today_str:
            return 0.0
        return float(row[0] or 0)
    finally:
        cursor.close()
        conn.close()


def add_nmp_transferred_today(user_id: int, amount: float):
    """Фиксирует переведённую сумму NMP за сегодня"""
    conn = db.get_conn()
    cursor = conn.cursor()
    today_str = time.strftime("%Y-%m-%d")
    try:
        cursor.execute("""
            INSERT INTO daily_nmp_limits (user_id, amount_transferred, last_transfer_day)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                amount_transferred = CASE 
                    WHEN daily_nmp_limits.last_transfer_day = EXCLUDED.last_transfer_day 
                    THEN daily_nmp_limits.amount_transferred + EXCLUDED.amount_transferred
                    ELSE EXCLUDED.amount_transferred
                END,
                last_transfer_day = EXCLUDED.last_transfer_day
        """, (user_id, amount, today_str))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ==============================================================================
# 💎 ПЕРЕВОД NMP С ПОДТВЕРЖДЕНИЕМ И ДНЕВНЫМ ЛИМИТОМ
# ==============================================================================

@router.message(StateFilter(None), F.chat.type == "private", F.text.lower().startswith("перевод"))
async def private_transfer_nmp(message: Message):
    parts = message.text.strip().split(maxsplit=3)
    
    if len(parts) < 3:
        await message.reply(
            "❌ <b>Неверный формат!</b>\n\n"
            "📌 <b>Используйте:</b> <code>перевод &lt;кол-во&gt; &lt;ID или @username&gt;</code>\n"
            "• Пример 1: <code>перевод 1 @username</code>\n"
            "• Пример 2: <code>перевод @username 1</code>",
            parse_mode="HTML"
        )
        return

    sender_id = message.from_user.id
    arg1, arg2 = parts[1], parts[2]

    target = get_target_user(arg1)
    if target:
        amount_str = arg2
    else:
        target = get_target_user(arg2)
        amount_str = arg1

    if not target:
        await message.reply("❌ <b>Пользователь с таким ID или Username не найден!</b>", parse_mode="HTML")
        return

    target_id = target["user_id"]
    if sender_id == target_id: 
        await message.reply("❌ <b>Вы не можете переводить NMP самому себе!</b>", parse_mode="HTML")
        return

    sender = db.get_user(sender_id)
    try: 
        amount = utils.parse_bet_input(amount_str, sender["nmp_balance"])
    except (TypeError, ValueError):
        await message.reply("❌ <b>Некорректная сумма перевода!</b>", parse_mode="HTML")
        return

    if amount <= 0:
        await message.reply("❌ <b>Сумма перевода должна быть больше 0 NMP!</b>", parse_mode="HTML")
        return

    if sender["nmp_balance"] < amount:
        await message.reply(f"❌ <b>Недостаточно NMP!</b> Ваш баланс: <b>{fmt_q(sender['nmp_balance'])} NMP</b>", parse_mode="HTML")
        return

    transferred_today = get_nmp_transferred_today(sender_id)
    remaining_limit = DAILY_NMP_LIMIT - transferred_today

    if remaining_limit <= 0:
        await message.reply(f"❌ <b>Вы исчерпали дневной лимит переводов NMP!</b> (Лимит: {DAILY_NMP_LIMIT:.0f} NMP/сутки)", parse_mode="HTML")
        return

    if amount > remaining_limit:
        await message.reply(
            f"❌ <b>Превышен дневной лимит переводов NMP!</b>\n"
            f"📮 Доступный лимит на сегодня: <b>{fmt_q(remaining_limit)} NMP</b>",
            parse_mode="HTML"
        )
        return

    sender_name = html.escape(message.from_user.first_name or "Игрок")
    target_name = html.escape(target.get("first_name") or target.get("username") or f"Игрок {target_id}")

    confirm_text = (
        f'<tg-emoji emoji-id="5463139580934892960">❓</tg-emoji> <b>{sender_name}</b>, '
        f'точно хочешь перевести <b>{fmt_q(amount)} NMP</b> игроку <b>{target_name}</b>?'
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да ✅", callback_data=f"nmp_tr:yes:{sender_id}:{target_id}:{amount}"),
            InlineKeyboardButton(text="Нет ❌", callback_data=f"nmp_tr:no:{sender_id}")
        ]
    ])

    await message.reply(confirm_text, reply_markup=kb, parse_mode="HTML")


# --- ОБРАБОТЧИК КНОПОК ПОДТВЕРЖДЕНИЯ ПЕРЕВОДА NMP ---

@router.callback_query(F.data.startswith("nmp_tr:"))
async def process_nmp_transfer_callback(call: CallbackQuery, bot: Bot):
    try:
        parts = call.data.split(":")
        action = parts[1]
        sender_id = int(parts[2])

        if call.from_user.id != sender_id:
            await call.answer("❌ Это не ваша кнопка подтверждения!", show_alert=True)
            return

        if action == "no":
            await call.answer("Перевод отменён")
            try:
                await call.message.delete()
            except Exception:
                pass
            return

        if len(parts) < 5:
            await call.answer("❌ Ошибка данных перевода!", show_alert=True)
            return

        target_id = int(parts[3])
        amount = float(parts[4])

        sender = db.get_user(sender_id)
        target = db.get_user(target_id)

        if not sender or not target:
            await call.answer("❌ Ошибка получения данных пользователей!", show_alert=True)
            return

        old_balance = sender.get("nmp_balance", 0)
        if old_balance < amount:
            await call.answer("❌ У вас недостаточно NMP!", show_alert=True)
            try:
                await call.message.delete()
            except Exception:
                pass
            return

        limit_val = globals().get("DAILY_NMP_LIMIT", 5000.0)
        transferred_today = get_nmp_transferred_today(sender_id)
        remaining_limit = limit_val - transferred_today

        if amount > remaining_limit:
            await call.answer(f"❌ Превышен дневной лимит! Осталось: {max(0.0, remaining_limit):.0f} NMP", show_alert=True)
            try:
                await call.message.delete()
            except Exception:
                pass
            return

        new_balance = old_balance - amount

        db.update_nmp_balance(sender_id, -amount)
        db.update_nmp_balance(target_id, amount)

        add_nmp_transferred_today(sender_id, amount)
        
        new_remaining_limit = max(0.0, limit_val - (transferred_today + amount))

        sender_name = html.escape(call.from_user.first_name or "Игрок")
        target_name = html.escape(target.get("first_name") or target.get("username") or f"Игрок {target_id}")

        success_msg = (
            f'<tg-emoji emoji-id="5767137507879685567">💎</tg-emoji> <b>{sender_name}</b> перевел(-а) <b>{fmt_q(amount)} NMP</b> <b>{target_name}</b>.\n\n'
            f'📮 Лимит: <b>{fmt_q(new_remaining_limit)} NMP</b>\n'
            f'· · · · · · · · · · · · · · · · · · · · ·\n'
            f'<tg-emoji emoji-id="5767137507879685567">💎</tg-emoji> Баланс: <b>{fmt_q(old_balance)} → {fmt_q(new_balance)} NMP</b>'
        )
        
        try:
            await call.message.edit_text(success_msg, parse_mode="HTML")
        except Exception:
            await call.message.answer(success_msg, parse_mode="HTML")

        await call.answer("✅ Перевод выполнен!")

        try:
            notify_msg = f"✅ Поступил перевод в размере <b>{fmt_q(amount)} NMP</b> от <b>{sender_name}</b>."
            await bot.send_message(target_id, notify_msg, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление получателю {target_id}: {e}")

    except Exception as e:
        logger.error(f"Ошибка в process_nmp_transfer_callback: {e}", exc_info=True)
        await call.answer("❌ Произошла ошибка при проведении перевода!", show_alert=True)


# --- АКТИВАЦИЯ ПРОМОКОДОВ ПОЛЬЗОВАТЕЛЯМИ ---

@router.message(StateFilter(None), lambda msg: msg.text and (msg.text.strip().startswith("#") or msg.text.lower().strip().startswith("промо #")))
async def process_promo_claim(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    parts = text.split()
    code = parts[1] if text.lower().startswith("промо ") else parts[0]
    code = code.strip(".,!?\"')")
    user_id = message.from_user.id
    db.get_user(user_id)
    reward = db.claim_promocode_db(code, user_id)
    if reward > 0:
        await message.reply(f"🎁 *Промокод успешно активирован!*\n🎫 Код: `{code}`\n💰 Начислено: *+{format_ncoin_display(reward)} nCoin*", parse_mode="Markdown")
    elif reward == -1.0:
        await message.reply(f"❌ Вы уже активировали промокод `{code}` ранее!")
    else:
        if message.chat.type == "private":
            await message.reply(f"❌ Промокод `{code}` не существует или закончились активации!")


# --- ИГРЫ ПО КОМАНДАМ ---
@router.message(Command("game"))
@router.message(F.text.lower() == "игры")
async def game_cmd(message: Message, state: FSMContext):
    await state.clear()
    text = "🎮 *Игровое лобби, сегодня удача точно на вашей стороне* 🎮\n\nВыберите интересующую вас игру из меню ниже:"
    await message.answer(text, reply_markup=get_games_keyboard_page1(), parse_mode="Markdown")


# --- СТАРТ И ОБРАБОТКА РЕФЕРАЛОВ / ЧЕКОВ ---
@router.message(CommandStart())
async def start_cmd(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    user_id = message.from_user.id

    args = command.args
    if args:
        if args.startswith("ref_"):
            try:
                ref_id = int(args.split("_")[1])
                if ref_id != user_id:
                    user_before = db.get_user(user_id)
                    if not user_before.get("referrer_id"):
                        db.get_user(user_id, message.from_user.first_name, message.from_user.username)
                        
                        conn = db.get_conn()
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE users SET referrer_id = %s WHERE user_id = %s AND (referrer_id IS NULL OR referrer_id = 0)",
                            (ref_id, user_id)
                        )
                        conn.commit()
                        cursor.close()
                        conn.close()

                        try:
                            new_user_name = html.escape(message.from_user.first_name or f"Игрок {user_id}")
                            await bot.send_message(
                                ref_id, 
                                f"👥 Новый реферал <b>{new_user_name}</b> перешел по вашей ссылке!", 
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Не удалось отправить уведомление рефереру {ref_id}: {e}")
            except Exception as e:
                logger.error(f"Ошибка при обработке реферальной ссылки: {e}")
            
        elif args.startswith("c_"):
            cheque_id = args[2:]
            
            cheque = db.get_cheque(cheque_id)
            if not cheque:
                await message.answer("❌ Ошибка: Чек не найден или уже был удален!")
                return
            
            if cheque["creator_id"] == user_id:
                await message.answer("❌ Вы не можете активировать собственный чек!")
                return
                
            if cheque["activations_left"] <= 0:
                await message.answer("❌ Ошибка: Этот чек уже полностью активирован!")
                return
                
            if cheque["target_user_id"] and cheque["target_user_id"] != user_id:
                await message.answer("❌ Ошибка: Этот чек предназначен для другого пользователя!")
                return
                
            if cheque["password"]:
                await state.update_data(claim_cheque_id=cheque_id)
                await state.set_state(ChequeState.waiting_for_claim_password)
                await message.answer("🔑 *Чек защищен паролем!*\nВведи его, чтобы забрать кэш:", parse_mode="Markdown")
                return
                
            success = db.register_cheque_claim(cheque_id, user_id)
            if not success:
                await message.answer("❌ Ты уже забирал этот чек или в нем закончились монеты!")
                return
                
            reward = round(cheque["total_amount"] / cheque["activations_total"], 2)
            db.update_balance(user_id, reward)
            
            desc_str = f"\n\n📝 Описание: <i>{html.escape(cheque['description'])}</i>" if cheque.get("description") else ""
            
            creator_data = db.get_user(cheque["creator_id"])
            creator_name = (
                creator_data.get("first_name") or 
                (f"@{creator_data.get('username')}" if creator_data.get("username") else None) or 
                f"Игрок {cheque['creator_id']}"
            )
            
            activations_text = f"{cheque['activations_total'] - cheque['activations_left'] + 1} / {cheque['activations_total']}"
            reward_text = format_ncoin_display(reward)
            
            await message.answer(
                f"{EMOJI_AXEWSD} <b>Чек успешно обналичен!</b>\n\n"
                f'{EMOJI_AXSD} Создатель: <b>{creator_name}</b>\n'
                f'<tg-emoji emoji-id="5463046637842608206">💰</tg-emoji> Тебе начислено: <b>+{reward_text} nCoin</b>\n'
                f"{EMOJI_AXWWSD} Активации: <b>{activations_text}</b>\n"
                f"{EMOJI_AQD} Твой баланс: <b>{format_ncoin_display(db.get_user(user_id)['balance'])} nCoin</b>{desc_str}",
                parse_mode="HTML"
            )
            
            if cheque.get("notifications", True):
                try:
                    mention = f"@{message.from_user.username}" if message.from_user.username else f'<a href="tg://user?id={user_id}">{html.escape(message.from_user.first_name)}</a>'
                    activations_left = cheque['activations_left'] - 1
                    await bot.send_message(
                        cheque["creator_id"],
                        f"{EMOJI_AXEWSD} {mention}, активировал(а) твой чек и получил(а) <b>{reward_text} n¢</b>\n"
                        f"Осталось активаций: <b>{activations_left}</b>.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                
            if cheque["activations_left"] - 1 <= 0:
                db.delete_cheque(cheque_id)
            return

    # --- ПРИВЕТСТВЕННОЕ СООБЩЕНИЕ (START) ---
    db.get_user(user_id, message.from_user.first_name, message.from_user.username)
    
    text = (
        f"{EMOJI_APXWZD} <b>Привет, {message.from_user.first_name}! Ты в деле!</b>\n\n"
        f"Добро пожаловать в самый сочный азартный бот Telegram. {EMOJI_APXWMD}\n"
        "Забудь про скуку — здесь тебя ждут иксы и драйв!\n\n"
        f"{EMOJI_APXWSD} Твой стартовый бонус уже на базе:\n"
        f"{EMOJI_AXIWSD} <b>10.000 nCoin</b>\n"
        f"{EMOJI_ASD} <b>100 NMP</b>\n\n"
        f"Выбирай игру и покажи всем, кто здесь настоящий шейх! {EMOJI_DT}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Начать игру", callback_data="games_menu", style="success")],
        [InlineKeyboardButton(text="📖 Инфо & Помощь", callback_data="help_menu", style="danger")],
        [
            InlineKeyboardButton(text="📢 Канал", url="https://t.me/nm_minesvs", style="primary"),
            InlineKeyboardButton(text="💬 Чат", url="https://t.me/+m6igqqO396E0ZTQy", style="primary")
        ]
    ])
    
    await message.answer_photo(
        photo="https://i.ibb.co/dsVQLzGN/IMG-20260826-160940-663.jpg",
        caption=text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# --- ПОМОЩЬ И СПРАВОЧНИК ---

@router.callback_query(F.data == "help_menu")
async def help_menu_callback(callback: CallbackQuery):
    await callback.answer()
    await show_help(callback)


@router.message(Command("help"))
@router.message(StateFilter(None), F.text.lower().in_(["помощь", "help"]))
async def help_cmd(message: Message, state: FSMContext):
    await state.clear()
    await show_help(message)


async def show_help(event):
    text = (
        "📖 <b>МЕНЮ ПОМОЩИ</b>\n"
        "........................\n"
        "<blockquote>ℹ️ <i>Здесь собраны все команды и их обозначения, которые могут вам понадобиться:</i></blockquote>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💡 Основные", callback_data="help_main", style="primary"),
            InlineKeyboardButton(text="Игры 🎮", callback_data="games_menu", style="primary")
        ],
        [
            InlineKeyboardButton(text="🔘 Прочее", callback_data="help_other", style="primary"),
            InlineKeyboardButton(text="Правила 📕", callback_data="help_rules", style="primary")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_start", style="danger")
        ]
    ])
    
    try:
        if isinstance(event, CallbackQuery): 
            await safe_edit_or_resend(event, text, reply_markup=kb, parse_mode="HTML")
        else: 
            await event.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в show_help: {e}")


# --- КНОПКА: ОСНОВНЫЕ ---

@router.callback_query(F.data == "help_main")
async def help_main_callback(callback: CallbackQuery):
    await callback.answer()
    
    text = (
        '/start - начать <tg-emoji emoji-id="5780773956030043338">🚀</tg-emoji>\n'
        '/game - игры <tg-emoji emoji-id="5890847821728322055">⚡️</tg-emoji>\n'
        '/help - помощь <tg-emoji emoji-id="5238025132177369293">🆘</tg-emoji>\n'
        '/donate - донат <tg-emoji emoji-id="5767137507879685567">💎</tg-emoji>\n'
        '/bank - вклады <tg-emoji emoji-id="5373174941095050893">💸</tg-emoji>\n'
        '/profile - профиль <tg-emoji emoji-id="5346136537123801643">👤</tg-emoji>\n'
        '/exchange - обменник <tg-emoji emoji-id="5447410659077661506">🌐</tg-emoji>\n'
        '/ref - реф. ссылка <tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji>\n'
        '/history - история игр <tg-emoji emoji-id="5467583879948803288">🎮</tg-emoji>\n'
        '/top - мировой топ <tg-emoji emoji-id="5226431245918942763">🏆</tg-emoji>\n'
        '/market - маркет <tg-emoji emoji-id="5278702045883292456">🏪</tg-emoji>\n'
        '/inventory - инвентарь <tg-emoji emoji-id="5276219151059269866">🎒</tg-emoji>\n'
        '/regulation - правила <tg-emoji emoji-id="5769547529993588669">👑</tg-emoji>\n'
        '/cheques - чеки <tg-emoji emoji-id="5444856076954520455">🧾</tg-emoji>\n'
        '/p2p - p2p нфт <tg-emoji emoji-id="5334609970182765157">↔️</tg-emoji>\n'
        '/cases - кейсы <tg-emoji emoji-id="5463172695132745432">📦</tg-emoji>\n'
        '/trade - NMP маркет <tg-emoji emoji-id="5368324170671202286">🛒</tg-emoji>\n'
        '/promote - реклама <tg-emoji emoji-id="5424818078833715060">📣</tg-emoji>'
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="help_menu")]
    ])
    
    await safe_edit_or_resend(callback, text, reply_markup=kb, parse_mode="HTML")


# --- КНОПКА: ПРОЧЕЕ ---

@router.callback_query(F.data == "help_other")
async def help_other_callback(callback: CallbackQuery):
    await callback.answer()
    
    text = (
        '<tg-emoji emoji-id="5348084369217052513">🔘</tg-emoji> Меню помощи · прочее:\n\n'
        '<tg-emoji emoji-id="6332573220868196043">🕓</tg-emoji> /history – история игр\n'
        '<tg-emoji emoji-id="6334448145891592172">🧾</tg-emoji> /check – чековая книжка\n'
        '<tg-emoji emoji-id="5424818078833715060">📢</tg-emoji> /promote – продвижение\n'
        '<tg-emoji emoji-id="5235837920081887219">📸</tg-emoji> /inventory – витрина подарков'
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="help_menu")]
    ])
    
    await safe_edit_or_resend(callback, text, reply_markup=kb, parse_mode="HTML")


# --- КНОПКА: ПРАВИЛА ---

@router.callback_query(F.data == "help_rules")
async def help_rules_callback(callback: CallbackQuery):
    await callback.answer()
    
    text = (
        "📕 <b>Меню помощи · правила:</b>\n\n"
        "<b>*ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ*</b>\n\n"
        "💰 <b>Игровые валюты:</b>\n"
        "<blockquote>• nCoin — валюта для игр (сокращение: n¢)\n"
        "• NMPOINT — валюта для продвижения и обмена (сокращение: NMP)</blockquote>\n\n"
        "📕 <b>Правила:</b>\n"
        "<blockquote>📌 ПРАВИЛА МИНЫ БОТА\n"
        "🔗 ПРАВИЛА ПРОДВИЖЕНИЯ\n"
        "💰 ПРАВИЛА ЗАРАБОТКА\n"
        "💸 ПОЛИТИКА ВОЗВРАТА</blockquote>\n\n"
        "🛡 <b>Контакты:</b>\n"
        "<blockquote>Чат: @nmineschat\n"
        "Канал: @nm_minesvs\n"
        "Поддержка: @nmproda</blockquote>\n\n"
        "📗 <b>Примечание:</b>\n"
        "<blockquote>⚠️ Обратите внимание, что наш бот не пропагандирует азартные игры. У нас нет возможности вывода денежных средств, и любые донаты принимаются исключительно на добровольной основе. Они предназначены только для поддержки нашего проекта и улучшения сервиса! Спасибо за понимание! 😊</blockquote>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ назад", callback_data="help_menu")]
    ])
    
    await safe_edit_or_resend(callback, text, reply_markup=kb, parse_mode="HTML")


# --- ГЕНЕРАЦИЯ СТРАНИЦ КЛАВИАТУРЫ ИГР

def get_games_keyboard_page1() -> InlineKeyboardMarkup:
    """Страница 1 — Игры 1–4"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💣 Мины 💣",
                callback_data="mine_menu",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🚀 Краш 📈",
                callback_data="crash_menu",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔮 Шарик 🔮",
                callback_data="sharik_menu_inline",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🏎️ Гиперкар 🏎️",
                callback_data="hypercar_menu_inline",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="➡️ Следующая страница (2/6)",
                callback_data="games_page_2",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Сбросить игры",
                callback_data="force_cancel_state",
                style="danger"
            )
        ]
    ])


def get_games_keyboard_page2() -> InlineKeyboardMarkup:
    """Страница 2 — Игры 5–8"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎲 Кубик 🎲",
                callback_data="dice_menu",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🎯 Дартс 🎯",
                callback_data="darts_menu",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎰 Слоты 🎰",
                callback_data="slots_menu",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🪙 Монетка 🪙",
                callback_data="coin_menu",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад (1/6)",
                callback_data="games_page_1",
                style="primary"
            ),
            InlineKeyboardButton(
                text="Вперёд ➡️ (3/6)",
                callback_data="games_page_3",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Сбросить игры",
                callback_data="force_cancel_state",
                style="danger"
            )
        ]
    ])


def get_games_keyboard_page3() -> InlineKeyboardMarkup:
    """Страница 3 — Игры 9–12"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🗼 Башня 🗼",
                callback_data="tower_menu",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🪜 Лесенка 🪜",
                callback_data="stairs_menu_inline",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="🕵️‍♂️ Ограбление 🏦",
                callback_data="heist_menu_inline",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🏺 Артефакт NMP 🏺",
                callback_data="artifact_menu_inline",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад (2/6)",
                callback_data="games_page_2",
                style="primary"
            ),
            InlineKeyboardButton(
                text="Вперёд ➡️ (4/6)",
                callback_data="games_page_4",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Сбросить игры",
                callback_data="force_cancel_state",
                style="danger"
            )
        ]
    ])


def get_games_keyboard_page4() -> InlineKeyboardMarkup:
    """Страница 4 — Игры 13–16"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🐸 Квак 🐸",
                callback_data="frog_menu",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🏀 Баскетбол 🏀",
                callback_data="basketball_menu",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="📺 Всезнайка 📺",
                callback_data="smart_menu_inline",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🃏 21 / Очко 🃏",
                callback_data="ochko_menu_inline",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад (3/6)",
                callback_data="games_page_3",
                style="primary"
            ),
            InlineKeyboardButton(
                text="Вперёд ➡️ (5/6)",
                callback_data="games_page_5",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Сбросить игры",
                callback_data="force_cancel_state",
                style="danger"
            )
        ]
    ])


def get_games_keyboard_page5() -> InlineKeyboardMarkup:
    """Страница 5 — Игры 17–20"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎡 Рулетка 🎡",
                callback_data="roulette_menu_inline",
                style="primary"
            ),
            InlineKeyboardButton(
                text="⚔️ Дуэли ⚔️",
                callback_data="duel_menu_inline",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="🌼 Золото 🌼",
                callback_data="gold_menu_inline",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🔺 Пирамида 🔺",
                callback_data="pyramid_menu_inline",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад (4/6)",
                callback_data="games_page_4",
                style="primary"
            ),
            InlineKeyboardButton(
                text="Вперёд ➡️ (6/6)",
                callback_data="games_page_6",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Сбросить игры",
                callback_data="force_cancel_state",
                style="danger"
            )
        ]
    ])


def get_games_keyboard_page6() -> InlineKeyboardMarkup:
    """Страница 6 — Игры 21–22"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="💎 Алмазы 💎",
                callback_data="diamond_menu_inline",
                style="primary"
            ),
            InlineKeyboardButton(
                text="⚽ Футбол ⚽",
                callback_data="football_menu_inline",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Предыдущая страница (5/6)",
                callback_data="games_page_5",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Сбросить игры",
                callback_data="force_cancel_state",
                style="danger"
            )
        ]
    ])


# --- ОБРАБОТЧИКИ НАВИГАЦИИ СТРАНИЦ ---

@router.callback_query(F.data == "games_menu")
async def games_menu_callback(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_or_resend(callback, "Выберите игру, в которую хотите сыграть (Страница 1/6):", reply_markup=get_games_keyboard_page1(), parse_mode="HTML")

@router.callback_query(F.data == "games_page_1")
async def games_page1_callback(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_or_resend(callback, "Выберите игру, в которую хотите сыграть (Страница 1/6):", reply_markup=get_games_keyboard_page1(), parse_mode="HTML")

@router.callback_query(F.data == "games_page_2")
async def games_page2_callback(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_or_resend(callback, "Выберите игру, в которую хотите сыграть (Страница 2/6):", reply_markup=get_games_keyboard_page2(), parse_mode="HTML")

@router.callback_query(F.data == "games_page_3")
async def games_page3_callback(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_or_resend(callback, "Выберите игру, в которую хотите сыграть (Страница 3/6):", reply_markup=get_games_keyboard_page3(), parse_mode="HTML")

@router.callback_query(F.data == "games_page_4")
async def games_page4_callback(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_or_resend(callback, "Выберите игру, в которую хотите сыграть (Страница 4/6):", reply_markup=get_games_keyboard_page4(), parse_mode="HTML")

@router.callback_query(F.data == "games_page_5")
async def games_page5_callback(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_or_resend(callback, "Выберите игру, в которую хотите сыграть (Страница 5/6):", reply_markup=get_games_keyboard_page5(), parse_mode="HTML")

@router.callback_query(F.data == "games_page_6")
async def games_page6_callback(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_or_resend(callback, "Выберите игру, в которую хотите сыграть (Страница 6/6):", reply_markup=get_games_keyboard_page6(), parse_mode="HTML")


# --- ОБРАБОТЧИКИ ОПИСАНИЯ ДЛЯ ПИРАМИДЫ И АЛМАЗОВ ---

@router.callback_query(F.data == "pyramid_menu_inline")
async def pyramid_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "🔺 <b>Игра ПИРАМИДА (Pyramid)</b> 🔺\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Поднимайтесь по 12 уровням от развалюхи до священной вершины!\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>пирамида &lt;ставка&gt;</code> или <code>/pyramid &lt;ставка&gt;</code>\n"
        "Например: <code>пирамида 10к</code> или <code>пирамида 10к 1</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_5")]]), parse_mode="HTML")

@router.callback_query(F.data == "diamond_menu_inline")
async def diamond_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "💎 <b>Игра АЛМАЗЫ (Diamonds)</b> 💎\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Открывайте по одной ячейке на каждом из 16 уровней и находите алмазы!\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>алмазы &lt;ставка&gt;</code> или <code>/diamond &lt;ставка&gt;</code>\n"
        "Например: <code>алмазы 10к</code> или <code>алмазы 10к 2</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_6")]]), parse_mode="HTML")


# --- ОБРАБОТЧИКИ ОПИСАНИЯ ИГР ---

@router.callback_query(F.data == "mine_menu")
async def mine_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "💣 <b>Игра МИНЫ (Mines)</b> 💣\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Находите драгоценные алмазы 💎 и избегайте скрытых мин 💣!\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>мины &lt;ставка&gt; &lt;кол-во мин&gt;</code>\n"
        "Например: <code>мины 10к 3</code> или <code>мины 7ккк 5</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_1")]]), parse_mode="HTML")

@router.callback_query(F.data == "stairs_menu_inline")
async def stairs_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "🪜 <b>Игра ЛЕСЕНКА (Stairs)</b> 🪜\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Пройдите 5 ступеней и заберите до <b>x12.50</b> от ставки!\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>лесенка</code> или используйте команду <code>/stairs</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить Лесенку", callback_data="stairs_menu_launch")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_2")]
    ])
    await safe_edit_or_resend(callback, text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "stairs_menu_launch")
async def stairs_menu_launch_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    
    user = db.get_user(
        user_id=call.from_user.id,
        first_name=call.from_user.first_name,
        username=call.from_user.username
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10к n¢", callback_data="stairs_preset:10k"),
            InlineKeyboardButton(text="100к n¢", callback_data="stairs_preset:100k"),
            InlineKeyboardButton(text="1кк n¢", callback_data="stairs_preset:1kk"),
        ],
        [
            InlineKeyboardButton(text="10кк n¢", callback_data="stairs_preset:10kk"),
            InlineKeyboardButton(text="100ккк n¢", callback_data="stairs_preset:100kkk"),
            InlineKeyboardButton(text="ALL-IN 🔥", callback_data="stairs_preset:allin"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="stairs_cancel")]
    ])

    text = (
        f"🪜 <b>Добро пожаловать в игру «Лесенка»!</b>\n\n"
        f"💰 Ваш баланс: <code>{user['balance']:,.0f} n¢</code>\n"
        f"Пройдите 5 ступеней и заберите до <b>x12.50</b> от ставки!\n\n"
        f"👇 Выберите кнопку или введите ставку текстом (например: <code>10к</code>, <code>100к</code>, <code>1кк</code>, <code>10кк</code>, <code>100ккк</code>):"
    )
    await state.set_state(StairsState.waiting_for_bet)
    await safe_edit_or_resend(call, text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "heist_menu_inline")
async def heist_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "🕵️‍♂️ <b>Игра ОГРАБЛЕНИЕ БАНКА (Bank Heist)</b> 🕵️‍♂️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Взломайте 3 уровня защиты хранилища и заберите куш до <b>x160.00</b>!\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>ограбление &lt;ставка&gt;</code> или используйте команду <code>/heist &lt;ставка&gt;</code>\n"
        "Например: <code>ограбление 10к</code> или <code>ограбление all</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать Ограбление", callback_data="heist_menu_launch")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_2")]
    ])
    await safe_edit_or_resend(callback, text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "heist_menu_launch")
async def heist_menu_launch_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    
    user = db.get_user(
        user_id=call.from_user.id,
        first_name=call.from_user.first_name,
        username=call.from_user.username
    )

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

    await state.set_state(HeistState.waiting_for_bet)
    try:
        if call.message and call.message.photo:
            await call.message.delete()
        await call.message.answer_photo(
            photo=HEIST_BANNERS["welcome"],
            caption=caption_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        await safe_edit_or_resend(call, caption_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "artifact_menu_inline")
async def artifact_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    user_nmp = user.get("nmp_balance", 0)
    text = (
        "🏺 <b>Поход за Древним Артефактом (Artifact)</b> 🏺\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Сразитесь с 3 стражами гробницы подряд и заберите куш <b>x13.00 NMP</b>!\n\n"
        "⚠️ <b>Награда достаётся только тем, кто одолеет всех 3 боссов до конца!</b>\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>артефакт &lt;ставка&gt;</code> или используйте команду <code>/artifact &lt;ставка&gt;</code>\n"
        "Например: <code>артефакт 1000</code> или <code>артефакт 5к</code>\n\n"
        f"💎 Твой баланс NMP: <b>{user_nmp:,} NMP</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать Поход (NMP)", callback_data="artifact_menu_launch", style="success")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_2", style="danger")]
    ])
    await safe_edit_or_resend(callback, text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "artifact_menu_launch")
async def artifact_menu_launch_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    
    user = db.get_user(
        user_id=call.from_user.id,
        first_name=call.from_user.first_name,
        username=call.from_user.username
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="100 NMP", callback_data="artifact_preset:100"),
            InlineKeyboardButton(text="500 NMP", callback_data="artifact_preset:500"),
            InlineKeyboardButton(text="1к NMP", callback_data="artifact_preset:1k"),
        ],
        [
            InlineKeyboardButton(text="5к NMP", callback_data="artifact_preset:5k"),
            InlineKeyboardButton(text="10к NMP", callback_data="artifact_preset:10k"),
            InlineKeyboardButton(text="🔥 ALL-IN NMP", callback_data="artifact_preset:allin"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="artifact_cancel")]
    ])

    caption_text = (
        f"🏺 <b>ПОХОД ЗА ДРЕВНИМ АРТЕФАКТОМ (NMP)</b>\n\n"
        f"💎 <b>Ваш баланс NMP:</b> <code>{user.get('nmp_balance', 0):,} NMP</code>\n"
        f"🏆 Сразитесь с 3 стражами гробницы подряд и заберите куш <b>x13.00 NMP</b>!\n\n"
        f"⚠️ <i>Награда достаётся только тем, кто пройдёт все 3 испытания до самого конца!</i>\n\n"
        f"💡 <i>Вы можете запускать игру сразу командой:\n"
        f"<code>артефакт 1000</code> или <code>/artifact 5к</code></i>\n\n"
        f"👇 Выберите ставку ниже или введите числом в чат:"
    )

    await state.set_state(ArtifactState.waiting_for_bet)
    try:
        if call.message and call.message.photo:
            await call.message.delete()
        await call.message.answer_photo(
            photo=ARTIFACT_BANNERS["welcome"],
            caption=caption_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        await safe_edit_or_resend(call, caption_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "sharik_menu_inline")
async def sharik_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "🔮 <b>Игра ШАРИК</b> 🔮\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Угадайте, окажется ли шарик под стаканом!\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>шарик &lt;ставка&gt; будет</code> или <code>шарик &lt;ставка&gt; не будет</code>\n"
        "Например: <code>шарик 10к будет</code> или <code>шарик 5к не будет</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_1")]]), parse_mode="HTML")

@router.callback_query(F.data == "hypercar_menu_inline")
async def hypercar_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "🏎 <b>Игра ГИПЕРКАР</b> 🏎\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Ваша задача — проехать как можно дальше, вовремя нажав на СТОП!\n"
        "⚠️ Остерегайтесь аварий, шанс которых увеличивается с износом машины.\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>гиперкар &lt;ставка&gt;</code> или <code>гмп &lt;ставка&gt;</code>\n"
        "Например: <code>гиперкар 10к</code> или <code>гмп все</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_1")]]), parse_mode="HTML")

@router.callback_query(F.data == "smart_menu_inline")
async def smart_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "📺 <b>Игра ВСЕЗНАЙКА</b> 📺\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Соедините правильный провод на 5 усложняющихся уровнях!\n\n"
        "📈 <b>Рост множителя:</b> от <code>x1.50</code> до <code>x150.00</code>!\n"
        "⚠️ <b>Остановка:</b> доступна строго ПОСЛЕ 2 уровня!\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>всезнайка &lt;ставка&gt;</code> или <code>телевизор &lt;ставка&gt;</code>\n"
        "Например: <code>всезнайка 10к</code> или <code>телевизор все</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_2")]]), parse_mode="HTML")

@router.callback_query(F.data == "duel_menu_inline")
async def duel_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "⚔️ <b>P2P КИБЕР-ДУЭЛИ</b> ⚔️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Сражайтесь с другими игроками в реальном времени!\n\n"
        "🎮 <b>Режимы:</b> \n"
        "• 🪨✂️📄 <b>Камень, Ножницы, Бумага</b>\n"
        "• 🥊 <b>Бой (Голова / Корпус / Ноги)</b>\n\n"
        "✍️ <b>Для вызова напишите в чат:</b> \n"
        "<code>дуэль &lt;ставка&gt;</code> или <code>дуэль &lt;ставка&gt; кнб</code> / <code>дуэль &lt;ставка&gt; бой</code>\n"
        "Например: <code>дуэль 10к</code> или <code>дуэль 5000 кнб</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_2")]]), parse_mode="HTML")

@router.callback_query(F.data == "gold_menu_inline")
async def gold_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "🌼 <b>Игра ЗОЛОТО</b> 🌼\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Пройдите 12 ступеней и заберите куш до <b>4096x</b>!\n\n"
        "✍️ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>золото &lt;ставка&gt;</code> или <code>/gold &lt;ставка&gt;</code>\n"
        "Например: <code>золото 100</code> или <code>золото все</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_2")]]), parse_mode="HTML")

@router.callback_query(F.data == "football_menu_inline")
async def football_menu_inline_callback(callback: CallbackQuery):
    await callback.answer()
    user = db.get_user(callback.from_user.id)
    text = (
        "⚽ <b>Игра ФУТБОЛ</b> ⚽\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Предскажите, попадет ли мяч в ворота или пролетит мимо, чтобы получить выигрыш!\n\n"
        "✍ <b>Для запуска игры напишите в чат:</b> \n"
        "<code>футбол &lt;ставка&gt; гол</code> или <code>футбол &lt;ставка&gt; мимо</code>\n"
        "Например: <code>футбол 10к гол</code> или <code>футбол все мимо</code>\n\n"
        f"💳 Твой баланс: <b>{format_ncoin_display(user['balance'])} nCoin</b>"
    )
    await safe_edit_or_resend(
        callback, 
        text, 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="games_page_6")]]), 
        parse_mode="HTML"
    )


@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    await callback.answer()
    text = f"👋 <b>Привет, {callback.from_user.first_name}!</b>\n\nВыбери интересующее действие на кнопках ниже {EMOJI_DT}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", callback_data="games_menu")],
        [InlineKeyboardButton(text="📖 Справка & Помощь", callback_data="help_menu")],
        [
            InlineKeyboardButton(text="📢 Канал", url="https://t.me/nm_minesvs"),
            InlineKeyboardButton(text="💬 Чат", url="https://t.me/+m6igqqO396E0ZTQy")
        ]
    ])
    await safe_edit_or_resend(callback, text, reply_markup=keyboard, parse_mode="HTML")


async def main():
    db.init_db()
    init_syndicate_db()
    dp.message.outer_middleware(BlockAndFsmBypassMiddleware())
    dp.callback_query.outer_middleware(BlockAndFsmBypassMiddleware())
    
    dp.include_router(router)
    routers_list = [
        exchange_router,
        donate_router,
        star_router,
        mines_router, crash_router, dice_router, darts_router, profile_router, 
        slots_router, admin_router, coin_router, bonus_router, basketball_router, 
        bank_router, cheques_router, tower_router, frog_router,
        ref_router, sharik_router, hypercar_router, smart_router, tournament_router,
        stairs_router, ochko_router, roulette_router, duels_router, heist_router, artifact_router,
        market_router, p2p_nft_router, rules_router, gold_router, diamond_router, promote_router, 
        cases_router, syndicates_router, pyramid_router, football_router, lottery_router, pvp_mines_router
    ]
    for r_item in routers_list:
        dp.include_router(r_item)
        
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
