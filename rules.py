# rules.py
import logging
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)
router = Router()

# Текст правил группы
RULES_TEXT = (
    "📜 *ПРАВИЛА ГРУППЫ* 📜\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "1. Оскорбления запрещены в любой форме\n"
    "2. Политика и война под полным запретом\n"
    "3. Ссылки и внешние ресурсы размещать нельзя\n"
    "4. Порнография запрещена полностью\n"
    "5. Интимный контент предлагать и распространять нельзя\n"
    "6. Флуд и спам не допускаются\n"
    "7. Реклама только с разрешения администрации\n"
    "8. Призывы в личные сообщения запрещены\n"
    "9. Мат допустим умеренно, без оскорблений\n"
    "10. Провокации и конфликты запрещены\n"
    "11. Экстремизм и запрещённые символы запрещены\n"
    "12. Незаконный контент (насилие, наркотики и т.п.) запрещён\n"
    "13. Ложные жалобы считаются нарушением\n"
    "14. Запрещён оффтоп.\n"
    "15. Запрещены рекламные теги и ссылки в нике.\n"
    "16. Нажимая /start, пользователь обязуется не распространять несанкционированную рекламу и спам. В случае нарушения администрация имеет право аннулировать внутренний баланс/аккаунт пользователя в боте и бессрочно заблокировать доступ к сервису без возврата средств.\n"
    "17. Угрозы, вымогательство и слив личной информации запрещены.\n\n"
    "📍 *НАКАЗАНИЯ:*\n"
    "• Лёгкое нарушение — предупреждение (варн)\n"
    "• Среднее — временный мут\n"
    "• Тяжёлое — бан без объяснений и права на восстановление"
)

def get_rules_kb() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой-ссылкой на правила бота"""
    # 🔗 Вставьте здесь вашу реальную ссылку на правила бота
    BOT_RULES_URL = "https://rules-nmines-bot.vercel.app/"  
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Правила бота", url=BOT_RULES_URL)]
    ])

# Обработчик текстовой команды "правила" и Telegram-команды "/regulation"
@router.message(StateFilter(None), Command("regulation"))
@router.message(StateFilter(None), F.text.lower() == "правила")
async def show_rules_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        RULES_TEXT,
        reply_markup=get_rules_kb(),
        parse_mode="Markdown"
    )
