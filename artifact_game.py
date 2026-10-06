# artifact_game.py
import hashlib
import html
import logging
import random
import secrets
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

import db  # Модуль базы данных
import utils

logger = logging.getLogger(__name__)

router = Router()

# =====================================================================
# КОНФИГУРАЦИЯ БАННЕРОВ И ИСПЫТАНИЙ ИГРЫ «ДРЕВНИЙ АРТЕФАКТ»
# =====================================================================

ARTIFACT_BANNERS = {
    "welcome": "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&q=80",
    "boss1": "https://i.ibb.co/XZcRZ6TC/IMG-20260822-152933-672.jpg",
    "boss2": "https://i.ibb.co/spQkq64c/IMG-20260822-153628-223.jpg",
    "boss3": "https://images.unsplash.com/photo-1514539079130-25950c84af65?w=800&q=80",
    "win": "https://i.ibb.co/qMyX6J89/IMG-20260822-155108-245.jpg",
    "lose": "https://i.ibb.co/Df4mfhdB/IMG-20260822-154641-776.jpg",
}

# 3 этапа сражений с боссами
BOSS_STAGES = {
    1: {
        "title": "🗿 ЭТАП 1: Каменный Страж Гробницы",
        "banner": ARTIFACT_BANNERS["boss1"],
        "desc": "Древний голем из темного гранита преграждает путь к первому печатному залу.",
        "chance": 70,  # 70%
        "tactics": [
            {"id": "t1", "name": "⚔️ Удар по уязвимым рунам", "icon": "🗡️"},
            {"id": "t2", "name": "🛡️ Блокировать каменный молот", "icon": "🛡️"},
            {"id": "t3", "name": "🔮 Развеять магию оживления", "icon": "✨"},
        ],
    },
    2: {
        "title": "🐉 ЭТАП 2: Теневой Дракон Бездны",
        "banner": ARTIFACT_BANNERS["boss2"],
        "desc": "Страж второго уровня одолеет синим пламенем и защитит подземную сокровищницу.",
        "chance": 40,  # 40%
        "tactics": [
            {"id": "t1", "name": "🏹 Стрела в крыльевую суставку", "icon": "🎯"},
            {"id": "t2", "name": "⚡️ Заклятие молнии в сердце", "icon": "⚡️"},
            {"id": "t3", "name": "🗡️ Внезапный выпад из тени", "icon": "🥷"},
        ],
    },
    3: {
        "title": "👑 ЭТАП 3: ФИНАЛ — Древний Владыка",
        "banner": ARTIFACT_BANNERS["boss3"],
        "desc": "Повелитель гробницы призывает всю древнюю магию! Победите его, чтобы забрать приз!",
        "chance": 25,  # 25%
        "tactics": [
            {"id": "t1", "name": "👑 Сокрушить корону власти", "icon": "💥"},
            {"id": "t2", "name": "🔮 Прервать ритуал бессмертия", "icon": "🌌"},
            {"id": "t3", "name": "⚔️ Финальный клинок в сердце", "icon": "⚔️"},
        ],
    },
}

WIN_MULTIPLIER = 13.00  # Финальный коэффициент награды

# Кэш честности раундов в оперативной памяти процесса
ARTIFACT_FAIR_CACHE: dict[str, dict] = {}


class ArtifactState(StatesGroup):
    waiting_for_bet = State()
    playing = State()


# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ЧЕСТНОСТЬ (SHA-256)
# =====================================================================

def parse_nmp_bet_amount(text: str, user_nmp_balance: float) -> float:
    """Парсер текстовых ставок NMP с поддержкой к, кк, all"""
    text_clean = text.lower().strip().replace(" ", "").replace(",", ".")

    if text_clean in ["все", "все-ин", "ва-банк", "all", "allin", "all-in", "аллин"]:
        return user_nmp_balance

    multipliers = {
        "kkkk": 1_000_000_000_000,
        "кккк": 1_000_000_000_000,
        "kkk": 1_000_000_000,
        "ккк": 1_000_000_000,
        "kk": 1_000_000,
        "кк": 1_000_000,
        "k": 1_000,
        "к": 1_000,
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


def create_artifact_fair_game(user_id: int, bet: float, rolls: list[int]) -> str:
    """Генерирует уникальные доказательства честности для раунда (SHA-256)."""
    salt = secrets.token_hex(16)
    rolls_str = ",".join(map(str, rolls))
    raw_string = f"rolls:{rolls_str}:{salt}"
    sha_hash = hashlib.sha256(raw_string.encode("utf-8")).hexdigest()
    fair_id = secrets.token_hex(8)

    ARTIFACT_FAIR_CACHE[fair_id] = {
        "user_id": int(user_id),
        "bet": float(bet),
        "rolls": list(rolls),
        "salt": salt,
        "raw_string": raw_string,
        "hash": sha_hash,
        "won": False,
        "is_finished": False,
        "win_amount": 0.0,
        "failed_stage": None,
        "failed_tactic": None,
        "history": [],
    }

    if len(ARTIFACT_FAIR_CACHE) > 1000:
        oldest_key = next(iter(ARTIFACT_FAIR_CACHE))
        ARTIFACT_FAIR_CACHE.pop(oldest_key, None)

    return fair_id


def render_progress_bar(current_stage: int, total_stages: int = 3, is_game_over: bool = False, won: bool = False) -> str:
    """Генерирует шкалу прогресса похода за Артефактом"""
    if is_game_over:
        if won:
            return "📈 <b>Путь в Гробницу:</b> [🟩🟩🟩] <b>100% (АРТЕФАКТ ЗАХВАЧЕН!)</b> 🏺"
        else:
            passed = max(0, current_stage - 1)
            bar = "🟩" * passed + "💀" + "⬛️" * (total_stages - current_stage)
            return f"📈 <b>Путь в Гробницу:</b> [{bar}] <b>(ПОРАЖЕНИЕ В БОЮ!)</b>"
    else:
        passed = max(0, current_stage - 1)
        bar = "🟩" * passed + "⚔️" + "⬛️" * (total_stages - current_stage)
        return f"📈 <b>Путь в Гробницу:</b> [{bar}] <b>Босс {current_stage}/{total_stages}</b>"


def render_artifact_text(
    bet: float,
    current_stage: int,
    history: list = None,
    is_game_over: bool = False,
    won: bool = False,
    win_amount: float = 0.0,
    failed_tactic: str = None,
) -> str:
    """Формирует художественное текстовое игровое поле"""
    text = "🏺 <b>ПОХОД ЗА ДРЕВНИМ АРТЕФАКТОМ</b>\n"
    text += f"💎 <b>Ставка:</b> <code>{bet:,.0f} NMP</code>\n"
    text += f"{render_progress_bar(current_stage, 3, is_game_over, won)}\n"
    text += "✨ ━━━━━━━━━━━━━━━━━━━━ ✨\n"

    # История сражений
    if history:
        text += "<b>История битвы:</b>\n"
        for idx, h in enumerate(history, 1):
            text += f"  • <b>Босс {idx}:</b> Повержен тактикой «{html.escape(h['tactic_name'])}» ✅\n"
        text += "➖➖➖➖➖➖➖➖➖➖➖\n"

    if is_game_over:
        if won:
            profit = win_amount - bet
            text += "🏆 <b>ПОБЕДА! ВСЕ 3 БОССА ПОВЕРЖЕНЫ!</b>\n"
            text += f"💎 <b>Вы добыли Древний Артефакт и забрали:</b> <code>{win_amount:,.0f} NMP</code> (+<code>{profit:,.0f} NMP</code> | x{WIN_MULTIPLIER:.2f})\n"
            text += "✨ Ваше имя вписано в легенды гробницы!"
        else:
            text += "💀 <b>ВЫ ПАЛИ В БОЮ!</b>\n"
            if failed_tactic:
                text += f"⚠️ Тактика «<b>{html.escape(failed_tactic)}</b>» оказалась неэффективна против <b>Босса {current_stage}</b>!\n"
            text += f"🥀 Ваш отряд разбит. Ставка <code>{bet:,.0f} NMP</code> осталась в гробнице."
    else:
        stage_data = BOSS_STAGES[current_stage]
        potential_win = round(bet * WIN_MULTIPLIER, 2)
        text += f"⚔️ <b>{stage_data['title']}</b>\n"
        text += f"📜 <i>{stage_data['desc']}</i>\n\n"
        text += f"🎁 <b>Главная награда:</b> <code>{potential_win:,.0f} NMP</code> (x{WIN_MULTIPLIER:.2f})\n\n"
        text += "⚠️ <i>Забрать награду можно только одолев всех 3-х боссов!</i>\n\n"
        text += "🎯 <b>Выберите боевую тактику для удара по Боссу:</b>"

    return text


def build_artifact_keyboard(current_stage: int) -> InlineKeyboardMarkup:
    """Генерирует кнопки выбора боевых тактик"""
    buttons = []
    stage_data = BOSS_STAGES[current_stage]

    for tactic in stage_data["tactics"]:
        btn_text = f"{tactic['icon']} {tactic['name']}"
        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"artifact_tactic:{tactic['id']}")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_finished_artifact_kb(fair_id: str) -> InlineKeyboardMarkup:
    """Генерирует финальные кнопки: 🔄 Повторить и 🔑 Честность"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Повторить", callback_data=f"artifact_repeat:{fair_id}"),
                InlineKeyboardButton(text="🔑 Честность", callback_data=f"artifact_fair:{fair_id}"),
            ]
        ]
    )


# =====================================================================
# ХЕНДЛЕРЫ И ЛОГИКА
# =====================================================================

@router.message(Command("artifact"))
@router.message(F.text.lower().startswith("артефакт"))
@router.message(F.text.lower().startswith("🏺 артефакт"))
async def cmd_artifact_start(message: Message, state: FSMContext):
    """Старт похода / запуск со ставкой из текста"""
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

    if bet_arg:
        bet = parse_nmp_bet_amount(bet_arg, user.get("nmp_balance", 0))
        if bet > 0:
            return await start_artifact_game(message, state, bet)
        else:
            await message.answer("❌ Неверно указана сумма ставки NMP. Попробуйте еще раз.")

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
        f"🏆 Сразитесь с 3 стражами гробницы подряд и заберите куш <b>x{WIN_MULTIPLIER:.2f} NMP</b>!\n\n"
        f"⚠️ <i>Награда достаётся только тем, кто пройдёт все 3 испытания до самого конца!</i>\n\n"
        f"💡 <i>Вы можете запускать игру сразу командой:\n"
        f"<code>артефакт 13</code> или <code>/artifact 20</code></i>\n\n"
        f"👇 Выберите ставку ниже или введите числом в чат:"
    )

    try:
        await message.answer_photo(
            photo=ARTIFACT_BANNERS["welcome"],
            caption=caption_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        await message.answer(caption_text, reply_markup=kb, parse_mode="HTML")

    await state.set_state(ArtifactState.waiting_for_bet)


@router.callback_query(F.data.startswith("artifact_preset:"), ArtifactState.waiting_for_bet)
async def process_preset_bet(call: CallbackQuery, state: FSMContext):
    """Обработка нажатия пресетов ставки NMP"""
    preset = call.data.split(":")[1]
    user = db.get_user(call.from_user.id)

    bet = parse_nmp_bet_amount(preset, user.get("nmp_balance", 0))
    await start_artifact_game(call, state, bet)


@router.message(ArtifactState.waiting_for_bet)
async def process_text_bet(message: Message, state: FSMContext):
    """Обработка текстового ввода суммы ставки NMP"""
    user = db.get_user(message.from_user.id)
    bet = parse_nmp_bet_amount(message.text, user.get("nmp_balance", 0))

    if bet <= 0:
        return await message.answer("❌ Введите корректную сумму ставки NMP (например: 10, 20, 25, all).")

    await start_artifact_game(message, state, bet)


async def start_artifact_game(event, state: FSMContext, bet: float):
    """Инициализация и запуск похода со списанием баланса и созданием SHA-256"""
    user_id = event.from_user.id
    user = db.get_user(user_id)
    user_nmp = user.get("nmp_balance", 0)

    if bet < 10:
        text = "❌ Минимальная ставка: 10 NMP"
        return await event.answer(text) if isinstance(event, Message) else await event.answer(text, show_alert=True)

    if user_nmp < bet:
        text = f"❌ Недостаточно NMP! Ваш баланс NMP: {user_nmp:,} NMP"
        return await event.answer(text) if isinstance(event, Message) else await event.answer(text, show_alert=True)

    # Списываем NMP
    db.update_nmp_balance(user_id, -bet)

    # Генерируем броски кубика (1-100)
    rolls = [random.randint(1, 100) for _ in range(3)]

    # Создаем данные честности раунда
    fair_id = create_artifact_fair_game(user_id, bet, rolls)

    game_data = {
        "bet": bet,
        "current_stage": 1,
        "history": [],
        "fair_id": fair_id,
        "rolls": rolls,
        "is_processing": False
    }

    await state.set_state(ArtifactState.playing)
    await state.update_data(game_data=game_data)

    text = render_artifact_text(bet=bet, current_stage=1, history=[])
    kb = build_artifact_keyboard(current_stage=1)

    stage_banner = BOSS_STAGES[1]["banner"]

    if isinstance(event, Message):
        try:
            await event.answer_photo(
                photo=stage_banner,
                caption=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            await event.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        try:
            media = InputMediaPhoto(media=stage_banner, caption=text, parse_mode="HTML")
            await event.message.edit_media(media=media, reply_markup=kb)
        except Exception:
            try:
                await event.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await event.message.answer_photo(
                    photo=stage_banner,
                    caption=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )


@router.callback_query(F.data.startswith("artifact_tactic:"), StateFilter("*"))
async def process_tactic_choice(call: CallbackQuery, state: FSMContext):
    """Обработка выбора тактики в бою с боссом с защитой от мульти-кликов/дюпов"""
    current_state = await state.get_state()
    if current_state != ArtifactState.playing:
        await call.answer("❌ Активная игра не найдена.", show_alert=True)
        return

    data = await state.get_data()
    game = data.get("game_data")

    # Проверка на наличие игры и блокировка при повторном клике
    if not game or game.get("is_processing"):
        await call.answer("❌ Активная игра не найдена.", show_alert=True)
        return

    # Устанавливаем флаг обработки запроса
    game["is_processing"] = True
    await state.update_data(game_data=game)

    tactic_id = call.data.split(":")[1]

    stage_num = game["current_stage"]
    bet = game["bet"]
    fair_id = game["fair_id"]
    rolls = game.get("rolls")
    stage_info = BOSS_STAGES[stage_num]

    chosen_tactic = None
    for t in stage_info["tactics"]:
        if t["id"] == tactic_id:
            chosen_tactic = t
            break

    if not chosen_tactic:
        game["is_processing"] = False
        await state.update_data(game_data=game)
        await call.answer("❌ Активная игра не найдена.", show_alert=True)
        return

    roll = rolls[stage_num - 1] if rolls and len(rolls) >= stage_num else random.randint(1, 100)
    is_success = roll <= stage_info["chance"]

    if not is_success:
        # ПОРАЖЕНИЕ В БОЮ С БОССОМ
        db.add_stats(
            uid=call.from_user.id,
            is_lost=True,
            lost_amount=bet,
            bet_amount=bet,
            game_name="ancient_artifact",
            win_amount=0.0
        )
        await state.clear()

        if fair_id in ARTIFACT_FAIR_CACHE:
            ARTIFACT_FAIR_CACHE[fair_id].update({
                "is_finished": True,
                "won": False,
                "failed_stage": stage_num,
                "failed_tactic": chosen_tactic["name"],
                "history": list(game["history"]),
            })

        text = render_artifact_text(
            bet=bet,
            current_stage=stage_num,
            history=game["history"],
            is_game_over=True,
            won=False,
            failed_tactic=chosen_tactic["name"]
        )

        kb_finished = get_finished_artifact_kb(fair_id)

        try:
            media = InputMediaPhoto(media=ARTIFACT_BANNERS["lose"], caption=text, parse_mode="HTML")
            await call.message.edit_media(media=media, reply_markup=kb_finished)
        except Exception:
            try:
                await call.message.edit_caption(caption=text, reply_markup=kb_finished, parse_mode="HTML")
            except TelegramBadRequest:
                pass

        await call.answer(f"💀 ПОРАЖЕНИЕ! Босс {stage_num} разбил ваш отряд!", show_alert=True)
        return

    # УСПЕШНАЯ ПОБЕДА НАД БОССОМ
    game["history"].append({
        "stage": stage_num,
        "tactic_name": chosen_tactic["name"]
    })

    if stage_num == 3:
        win_amount = round(bet * WIN_MULTIPLIER, 2)

        db.update_nmp_balance(call.from_user.id, win_amount)
        db.add_stats(
            uid=call.from_user.id,
            is_lost=False,
            lost_amount=0.0,
            bet_amount=bet,
            game_name="ancient_artifact",
            win_amount=win_amount
        )
        await state.clear()

        if fair_id in ARTIFACT_FAIR_CACHE:
            ARTIFACT_FAIR_CACHE[fair_id].update({
                "is_finished": True,
                "won": True,
                "win_amount": win_amount,
                "history": list(game["history"]),
            })

        text = render_artifact_text(
            bet=bet,
            current_stage=3,
            history=game["history"],
            is_game_over=True,
            won=True,
            win_amount=win_amount
        )

        kb_finished = get_finished_artifact_kb(fair_id)

        try:
            media = InputMediaPhoto(media=ARTIFACT_BANNERS["win"], caption=text, parse_mode="HTML")
            await call.message.edit_media(media=media, reply_markup=kb_finished)
        except Exception:
            try:
                await call.message.edit_caption(caption=text, reply_markup=kb_finished, parse_mode="HTML")
            except TelegramBadRequest:
                pass

        await call.answer(f"🎉 АРТЕФАКТ ВАШ! Вы забираете {win_amount:,.0f} NMP!", show_alert=True)
    else:
        game["current_stage"] += 1
        game["is_processing"] = False  # Снимаем блокировку для следующего шага
        await state.update_data(game_data=game)

        next_stage_num = game["current_stage"]
        next_banner = BOSS_STAGES[next_stage_num]["banner"]

        text = render_artifact_text(
            bet=bet,
            current_stage=next_stage_num,
            history=game["history"]
        )
        kb = build_artifact_keyboard(current_stage=next_stage_num)

        try:
            media = InputMediaPhoto(media=next_banner, caption=text, parse_mode="HTML")
            await call.message.edit_media(media=media, reply_markup=kb)
        except Exception:
            try:
                await call.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            except TelegramBadRequest:
                pass

        await call.answer(f"⚔️ Босс {stage_num} повержен! Переходим к Боссу {next_stage_num}!")


@router.callback_query(F.data == "artifact_cancel")
async def process_cancel(call: CallbackQuery, state: FSMContext):
    """Отмена игры на этапе выбора ставки"""
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer("❌ Поход отменен.")


@router.callback_query(F.data.startswith("artifact_repeat:"), StateFilter("*"))
async def artifact_repeat_callback(call: CallbackQuery, state: FSMContext):
    """Повторяет игру с той же ставкой NMP с проверкой активного состояния"""
    current_state = await state.get_state()
    if current_state == ArtifactState.playing:
        return await call.answer("❌ У вас уже запущен активный поход!", show_alert=True)

    parts = call.data.split(":", 1)
    if len(parts) != 2:
        return await call.answer("❌ Неверные данные.", show_alert=True)

    fair_id = parts[1]
    previous_game = ARTIFACT_FAIR_CACHE.get(fair_id)

    if not previous_game:
        return await call.answer("❌ Данные предыдущей игры устарели.", show_alert=True)

    if int(previous_game["user_id"]) != int(call.from_user.id):
        return await call.answer("❌ Это не ваша игра.", show_alert=True)

    bet = float(previous_game["bet"])
    await state.clear()

    await start_artifact_game(event=call, state=state, bet=bet)


@router.callback_query(F.data.startswith("artifact_fair:"), StateFilter("*"))
async def artifact_fair_callback(call: CallbackQuery):
    """Отображает данные доказательства честности (SHA-256) в том же сообщении."""
    parts = call.data.split(":", 1)
    if len(parts) != 2:
        return await call.answer("❌ Неверный вызов.", show_alert=True)

    fair_id = parts[1]
    fair_data = ARTIFACT_FAIR_CACHE.get(fair_id)

    if not fair_data:
        return await call.answer("❌ Данные этого раунда устарели или бот был перезапущен.", show_alert=True)

    if int(fair_data["user_id"]) != int(call.from_user.id):
        return await call.answer("❌ Это не ваша игра.", show_alert=True)

    # Отвечаем на Callback один раз
    await call.answer()

    raw_string = html.escape(str(fair_data["raw_string"]))
    sha_hash = html.escape(str(fair_data["hash"]))
    rolls = fair_data.get("rolls", [0, 0, 0])

    r1, r2, r3 = rolls[0], rolls[1], rolls[2]
    res1 = "✅ Успех" if r1 <= 70 else "❌ Поражение"
    res2 = "✅ Успех" if r2 <= 40 else "❌ Поражение"
    res3 = "✅ Успех" if r3 <= 25 else "❌ Поражение"

    text = (
        "🏺 <b>Артефакт · Честность</b> 🔑\n"
        "➖➖➖➖➖➖➖➖➖➖➖\n\n"
        "🔢 <b>SHA-256 Хэш раунда:</b>\n"
        f"<code>{sha_hash}</code>\n\n"
        "🔑 <b>Результат (Raw):</b>\n"
        f"<code>{raw_string}</code>\n\n"
        "🎯 <b>Скрытые броски кубика (1-100):</b>\n"
        f"  • <b>Босс 1 (70%):</b> {r1} ({res1})\n"
        f"  • <b>Босс 2 (40%):</b> {r2} ({res2})\n"
        f"  • <b>Босс 3 (25%):</b> {r3} ({res3})\n\n"
        "<blockquote>"
        "Числа броска генерируются до старта битвы."
        "Скопируйте строку Результата и вставьте её на любом онлайн-сканере SHA-256. "
        "Сгенерированный хэш точно совпадёт с Хэшем раунда!"
        "</blockquote>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"artifact_fair_back:{fair_id}"),
                InlineKeyboardButton(text="Проверить SHA-256 🔑", url="https://emn178.github.io/online-tools/"),
            ]
        ]
    )

    msg = call.message
    if msg:
        try:
            if msg.photo:
                await msg.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                await msg.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка изменения сообщения в artifact_fair: {e}")


@router.callback_query(F.data.startswith("artifact_fair_back:"), StateFilter("*"))
async def artifact_fair_back_callback(call: CallbackQuery):
    """Возвращает экран с итогами завершенной игры"""
    parts = call.data.split(":", 1)
    if len(parts) != 2:
        return await call.answer("❌ Неверный запрос.", show_alert=True)

    fair_id = parts[1]
    fair_data = ARTIFACT_FAIR_CACHE.get(fair_id)

    if not fair_data:
        return await call.answer("❌ Данные игры устарели.", show_alert=True)

    if int(fair_data["user_id"]) != int(call.from_user.id):
        return await call.answer("❌ Это не ваша игра.", show_alert=True)

    await call.answer()

    bet = fair_data["bet"]
    won = fair_data["won"]
    win_amount = fair_data.get("win_amount", 0.0)
    failed_stage = fair_data.get("failed_stage", 1)
    failed_tactic = fair_data.get("failed_tactic", None)
    history = fair_data.get("history", [])

    current_stage = 3 if won else (failed_stage or 1)

    text = render_artifact_text(
        bet=bet,
        current_stage=current_stage,
        history=history,
        is_game_over=True,
        won=won,
        win_amount=win_amount,
        failed_tactic=failed_tactic,
    )

    kb_finished = get_finished_artifact_kb(fair_id)
    msg = call.message

    if msg:
        try:
            if msg.photo:
                await msg.edit_caption(caption=text, reply_markup=kb_finished, parse_mode="HTML")
            else:
                await msg.edit_text(text=text, reply_markup=kb_finished, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка изменения сообщения в artifact_fair_back: {e}")
