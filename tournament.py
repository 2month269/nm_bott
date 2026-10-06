# tournament.py
import html
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import db
from admin import ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

class TournStates(StatesGroup):
    waiting_for_idea = State()

# --- АДМИН: ЗАПУСК ТУРНИРА ---
@router.callback_query(F.data == "adm_start_tournament")
async def start_tournament_broadcast(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.answer("Рассылка запущена...")
    
    user_ids = db.get_all_user_ids()
    text = (
        "🏆 <b>ЕЖЕНЕДЕЛЬНЫЙ ТУРНИР ИДЕЙ НА 1 000 000 nCoin!</b> 🏆\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Расскажи свою самую крутую идею, как стать успешным человеком в свободе и деньгах!\n\n"
        "Победитель получит <b>1,000,000 nCoin</b> на баланс!\n\n"
        "👇 Нажми кнопку ниже, чтобы подать заявку!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Участвовать", callback_data="tourn_join")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="tourn_close")]
    ])
    
    sent_count = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")
            sent_count += 1
        except Exception as e:
            logger.warning(f"Ошибка отправки турнира пользователю {uid}: {e}")
            
    await callback.message.answer(f"✅ Рассылка турнира успешно отправлена {sent_count} пользователям!", parse_mode="HTML")

@router.callback_query(F.data == "tourn_join")
async def join_tournament(callback: CallbackQuery, state: FSMContext):
    if db.has_user_submitted_idea(callback.from_user.id):
        await callback.answer("❌ Вы уже подали заявку на этот турнир!", show_alert=True)
        return
    await callback.message.answer("✍️ <b>Напиши свою идею в ответ на это сообщение:</b>", parse_mode="HTML")
    await state.set_state(TournStates.waiting_for_idea)

@router.callback_query(F.data == "tourn_close")
async def close_tournament_msg(callback: CallbackQuery):
    await callback.answer("Закрыто")
    try:
        await callback.message.delete()
    except Exception:
        pass

@router.message(TournStates.waiting_for_idea)
async def process_idea(message: Message, state: FSMContext):
    db.add_tournament_idea(
        message.from_user.id, 
        message.from_user.username or "none", 
        message.from_user.first_name, 
        message.text
    )
    await message.answer("🎉 <b>Твоя идея успешно принята на турнир!</b> Ожидай подведения итогов.", parse_mode="HTML")
    await state.clear()

# --- АДМИН: СПИСОК ИДЕЙ (ПОДДЕРЖКА /spisok, список, /spiski, списки) ---
@router.message(F.text.lower().in_(["/spisok", "список", "/spiski", "списки"]))
async def list_ideas(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    ideas = db.get_all_tournament_ideas()
    if not ideas:
        await message.answer("📭 Список идей турнира пуст!")
        return
    for i in ideas:
        username_str = f"@{html.escape(i[2])}" if i[2] and i[2] != "none" else "нет юзернейма"
        safe_name = html.escape(str(i[3]))
        safe_idea_text = html.escape(str(i[4]))
        
        text = (
            f"💡 <b>Идея ID:</b> <code>{i[0]}</code>\n"
            f"👤 <b>Автор:</b> {safe_name} ({username_str}) | ID: <code>{i[1]}</code>\n"
            f"📝 <b>Текст идеи:</b>\n{safe_idea_text}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🏆 Дать 1кк", callback_data=f"tourn_win:{i[0]}"), 
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"tourn_reject:{i[0]}")
            ]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("tourn_win:"))
async def win_tournament(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        return
    idea_id = int(callback.data.split(":")[1])
    idea = db.get_tournament_idea(idea_id)
    if not idea:
        await callback.answer("❌ Идея не найдена или уже обработана!", show_alert=True)
        return
    
    # 1. Выплата 1,000,000 nCoin
    db.update_balance(idea["user_id"], 1000000)
    
    # 2. Уведомление победителю
    try:
        await bot.send_message(
            idea["user_id"], 
            "🎉 <b>ПОЗДРАВЛЯЕМ!</b> Твоя идея победила в еженедельном турнире! Тебе начислено <b>+1,000,000 nCoin</b>!", 
            parse_mode="HTML"
        )
    except Exception:
        pass
    
    # 3. Рассылка анонса всем игрокам
    raw_username = f"@{idea['username']}" if idea['username'] and idea['username'] != "none" else idea['first_name']
    username_display = html.escape(str(raw_username))
    
    announcement_text = (
        f"🎉 <b>ИТОГИ ЕЖЕНЕДЕЛЬНОГО ТУРНИРА ИДЕЙ!</b> 🎉\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 Победитель: <b>{username_display}</b>!\n"
        f"💰 Он забрал главный приз: <b>1,000,000 nCoin</b>!\n\n"
        f"Спасибо всем за участие! Набор идей временно закрыт."
    )
    user_ids = db.get_all_user_ids()
    for uid in user_ids:
        try:
            await bot.send_message(uid, announcement_text, parse_mode="HTML")
        except Exception:
            pass
        
    # 4. Очистка списка идей после определения победителя
    db.clear_tournament_ideas()
    await callback.message.edit_text(f"✅ Победитель {username_display} выбран, 1,000,000 nCoin начислено! Список идей очищен.", parse_mode="HTML")

@router.callback_query(F.data.startswith("tourn_reject:"))
async def reject_idea(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    idea_id = int(callback.data.split(":")[1])
    db.delete_tournament_idea(idea_id)
    await callback.message.edit_text("❌ Идея отклонена.")
