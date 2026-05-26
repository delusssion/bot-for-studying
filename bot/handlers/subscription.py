import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.db.queries import get_or_create_user, get_user_balance, purchase_subscription
from bot.keyboards.subscription_kb import renew_sub_kb, sub_no_balance_kb, subscribe_kb
from bot.utils.helpers import kopecks_to_rubles

logger = logging.getLogger(__name__)
router = Router()

_SUB_BASE = (
    "⭐ <b>Подписка Ученик PRO</b>\n\n"
    "Что входит:\n"
    "• Безлимитные заказы (без ограничения 3/час)\n"
    "• Приоритет в очереди генерации\n"
    "• Бесплатные правки без ограничений\n\n"
    "Стоимость: <b>{price}</b> / 30 дней"
)


@router.message(F.text == "⭐ Подписка")
async def subscription_menu(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    price_str = kopecks_to_rubles(config.price_subscription_30d)
    sub_until = user.get("subscription_until")
    is_active = bool(sub_until and sub_until > datetime.now())

    text = _SUB_BASE.format(price=price_str)
    if is_active:
        text += f"\n\n✅ <b>Подписка активна до: {sub_until.strftime('%d.%m.%Y')}</b>"
        kb = renew_sub_kb()
    else:
        kb = subscribe_kb()

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "sub:buy")
async def sub_buy(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    price = config.price_subscription_30d

    balance = await get_user_balance(user_id)
    if balance < price:
        shortage = price - balance
        await callback.message.answer(
            f"❌ Недостаточно средств. Нужно ещё <b>{kopecks_to_rubles(shortage)}</b>",
            reply_markup=sub_no_balance_kb(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    ok = await purchase_subscription(user_id, price)
    if ok:
        user = await get_or_create_user(
            user_id, callback.from_user.username, callback.from_user.full_name
        )
        sub_until = user["subscription_until"]
        date_str = sub_until.strftime("%d.%m.%Y") if sub_until else "?"
        await callback.message.answer(
            f"✅ <b>Подписка активирована до {date_str}!</b>\n"
            f"Списано: {kopecks_to_rubles(price)}",
            parse_mode="HTML",
        )
        logger.info("Subscription purchased user=%s price=%s", user_id, price)
    else:
        await callback.message.answer(
            "❌ Ошибка при оформлении подписки. Попробуйте снова."
        )

    await callback.answer()
