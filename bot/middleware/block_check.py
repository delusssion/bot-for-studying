from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import config


class BlockCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        from bot.db.queries import get_setting, get_user
        from bot.keyboards.main_kb import get_support_button

        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return await handler(event, data)

        is_admin = int(user_id) in config.admin_ids

        if not is_admin:
            user = await get_user(user_id)

            # Blocked check
            if user and user.get("is_blocked"):
                msg = (
                    "🚫 Ваш аккаунт заблокирован.\n"
                    "Для разблокировки обратитесь в поддержку:"
                )
                try:
                    if isinstance(event, Message):
                        await event.answer(msg, reply_markup=get_support_button())
                    elif isinstance(event, CallbackQuery):
                        await event.message.answer(msg, reply_markup=get_support_button())
                        await event.answer()
                except Exception:
                    pass
                return

            # Maintenance mode check (skip for VIP too)
            is_vip = user and user.get("is_vip")
            if not is_vip:
                maintenance = (await get_setting("maintenance_mode", "false")).lower() == "true"
                if maintenance:
                    msg = "🔧 Бот на техническом обслуживании.\nСкоро вернёмся! Приносим извинения."
                    try:
                        if isinstance(event, Message):
                            await event.answer(msg)
                        elif isinstance(event, CallbackQuery):
                            await event.answer(msg, show_alert=True)
                    except Exception:
                        pass
                    return

        return await handler(event, data)
