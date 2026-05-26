import logging
import traceback

from aiogram import Bot, Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)
errors_router = Router(name="errors")

_USER_ERROR_MSG = (
    "❌ Что-то пошло не так.\n"
    "Деньги <b>не списаны</b> или будут <b>автоматически возвращены</b> на баланс.\n\n"
    "Попробуйте снова или обратитесь в поддержку:"
)


@errors_router.error()
async def global_error_handler(event: ErrorEvent, bot: Bot) -> bool:
    from bot.keyboards.main_kb import get_support_button

    exc = event.exception
    update = event.update

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("Unhandled exception\nUpdate: %s\n%s", update.model_dump_json()[:500], tb)

    # Determine chat to notify
    chat_id: int | None = None
    try:
        if update.message:
            chat_id = update.message.chat.id
        elif update.callback_query:
            chat_id = update.callback_query.message.chat.id
        elif update.pre_checkout_query:
            chat_id = update.pre_checkout_query.from_user.id
    except Exception:
        pass

    if chat_id:
        try:
            await bot.send_message(
                chat_id, _USER_ERROR_MSG,
                parse_mode="HTML",
                reply_markup=get_support_button(),
            )
        except Exception:
            pass

    return True  # mark error as handled so aiogram doesn't re-raise
