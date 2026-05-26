from aiogram import F, Router
from aiogram.types import Message

from bot.config import config
from bot.keyboards.main_kb import get_support_button
from bot.utils.helpers import kopecks_to_rubles

router = Router()


@router.message(F.text == "❓ Помощь")
async def help_menu(message: Message) -> None:
    text = (
        "❓ <b>Помощь</b>\n\n"
        "<b>Как сделать заказ?</b>\n"
        "Нажмите «Новый заказ», выберите тип работы "
        "и следуйте инструкциям бота.\n\n"
        "<b>Что если результат не понравился?</b>\n"
        "После получения файла используйте кнопки "
        "правок под сообщением. Первый свободный "
        "комментарий — бесплатно.\n\n"
        "<b>Сколько стоит?</b>\n"
        f"• Лабораторная работа (.docx) — {kopecks_to_rubles(config.price_lab_docx)}\n"
        f"• Презентация (.pptx) — {kopecks_to_rubles(config.price_presentation)}\n"
        f"• Лаба + презентация — {kopecks_to_rubles(config.price_lab_plus_pres)}\n"
        f"• Контрольная / текст — {kopecks_to_rubles(config.price_text_answer)}\n"
        f"• Подписка PRO — {kopecks_to_rubles(config.price_subscription_30d)}/мес"
    )

    await message.answer(text, reply_markup=get_support_button(), parse_mode="HTML")
