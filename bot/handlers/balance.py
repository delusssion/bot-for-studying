import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message

from bot.config import OZON_CARD_NUMBER, OZON_CARD_OWNER, OZON_SBP_LINK, config
from bot.db.queries import (
    create_ozon_payment, generate_payment_code,
    get_user, get_user_balance,
)
from bot.keyboards.balance_kb import balance_main_kb, ozon_payment_kb, topup_amounts_kb
from bot.keyboards.admin_kb import payment_confirm_kb
from bot.utils.helpers import kopecks_to_rubles
from bot.utils.states import BalanceStates

logger = logging.getLogger(__name__)
router = Router()

_METHOD_NAMES = {
    "stars": "Telegram Stars",
    "card": "Карта Ozon",
    "sbp": "СБП",
}


async def _show_balance(target: Message | CallbackQuery) -> None:
    msg = target if isinstance(target, Message) else target.message
    user_id = target.from_user.id
    balance = await get_user_balance(user_id)
    await msg.answer(
        f"💰 <b>Ваш баланс: {kopecks_to_rubles(balance)}</b>\n\nПополнить баланс:",
        reply_markup=balance_main_kb(),
        parse_mode="HTML",
    )


@router.message(F.text.in_({"💰 Баланс", "💰 Баланс и оплата"}))
async def balance_menu(message: Message) -> None:
    await _show_balance(message)


@router.callback_query(F.data == "open_balance")
async def open_balance(callback: CallbackQuery) -> None:
    await _show_balance(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("topup_method:"))
async def topup_method_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    method = callback.data.split(":")[1]
    await state.update_data(topup_method=method)
    await callback.message.edit_text(
        "Выберите сумму пополнения:",
        reply_markup=topup_amounts_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_amount:"))
async def topup_amount_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    amount_kopecks = int(callback.data.split(":")[1])
    data = await state.get_data()
    method = data.get("topup_method", "stars")

    if method == "card":
        await _send_ozon_instructions(callback.message, amount_kopecks)
        await callback.answer()
        return

    if method != "stars":
        name = _METHOD_NAMES.get(method, method)
        await callback.message.edit_text(
            f"⏳ Способ оплаты «{name}» будет добавлен в ближайшее время.\n"
            "Сейчас доступны Telegram Stars и Карта Ozon."
        )
        await callback.answer()
        return

    await callback.answer()
    await _send_stars_invoice(callback.message, callback.from_user.id, amount_kopecks)


@router.callback_query(F.data == "topup_custom")
async def topup_custom(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    method = data.get("topup_method", "stars")

    if method not in ("stars", "card"):
        name = _METHOD_NAMES.get(method, method)
        await callback.message.edit_text(
            f"⏳ Способ оплаты «{name}» будет добавлен в ближайшее время.\n"
            "Сейчас доступны Telegram Stars и Карта Ozon."
        )
        await callback.answer()
        return

    await state.set_state(BalanceStates.entering_custom_amount)
    await callback.message.edit_text(
        "Введите сумму пополнения в рублях (минимум 50 ₽):"
    )
    await callback.answer()


@router.message(StateFilter(BalanceStates.entering_custom_amount), F.text)
async def topup_custom_input(message: Message, state: FSMContext) -> None:
    try:
        rubles = int(message.text.strip())
    except ValueError:
        await message.answer("Введите целое число, например: 150")
        return

    if rubles < 50:
        await message.answer("Минимальная сумма — 50 ₽.")
        return

    data = await state.get_data()
    method = data.get("topup_method", "stars")
    await state.clear()

    amount_kopecks = rubles * 100
    if method == "card":
        await _send_ozon_instructions(message, amount_kopecks)
    else:
        await _send_stars_invoice(message, message.from_user.id, amount_kopecks)


def _make_qr_bytes(data: str) -> bytes:
    import io
    import qrcode
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _send_ozon_instructions(target: Message, amount_kopecks: int) -> None:
    from aiogram.types import BufferedInputFile
    code = await generate_payment_code()
    rubles = amount_kopecks // 100
    caption = (
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"Переведите <b>{rubles} ₽</b> на карту:\n\n"
        f"🏦 Ozon банк\n"
        f"💳 <code>{OZON_CARD_NUMBER}</code>\n"
        f"👤 {OZON_CARD_OWNER}\n\n"
        f"⚠️ <b>ВАЖНО:</b> в комментарии к переводу\n"
        f"обязательно укажите код:\n\n"
        f"<code>{code}</code>\n\n"
        f"Без кода пополнение не будет засчитано!\n\n"
        f"⏱ Код действителен 30 минут."
    )
    qr_bytes = _make_qr_bytes(OZON_SBP_LINK)
    photo = BufferedInputFile(qr_bytes, filename="qr.png")
    await target.answer_photo(
        photo,
        caption=caption,
        reply_markup=ozon_payment_kb(code, amount_kopecks, sbp_link=OZON_SBP_LINK),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("ozon_copy:"))
async def ozon_copy_code(callback: CallbackQuery) -> None:
    code = callback.data.split(":", 1)[1]
    await callback.message.answer(code)
    await callback.answer("Код отправлен отдельным сообщением")


@router.callback_query(F.data.startswith("ozon_paid:"))
async def ozon_paid(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")  # ["ozon_paid", "UCH-XXXX", "amount"]
    code = parts[1]
    amount_kopecks = int(parts[2])
    user_id = callback.from_user.id

    payment = await create_ozon_payment(user_id, amount_kopecks, code)
    if not payment:
        await callback.answer(
            "⚠️ Ошибка при создании платежа. Попробуйте снова.", show_alert=True
        )
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "⏳ Ожидаем поступление платежа.\n"
        "Как только подтвердим — баланс пополнится\n"
        "и вы получите уведомление.\n\n"
        "Обычно это занимает до 15 минут."
    )
    await callback.answer()

    user = await get_user(user_id)
    uname = f"@{user['username']}" if user and user.get("username") else str(user_id)
    rubles = amount_kopecks // 100

    notify_text = (
        f"💳 <b>Новый платёж ожидает подтверждения!</b>\n\n"
        f"👤 {uname} (<code>{user_id}</code>)\n"
        f"💰 Сумма: <b>{rubles} ₽</b>\n"
        f"🔑 Код: <code>{code}</code>\n"
        f"⏱ Истекает через 30 минут\n\n"
        f"Найдите перевод с этим кодом в приложении Ozon\n"
        f"и подтвердите:"
    )
    for admin_id in config.admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                notify_text,
                reply_markup=payment_confirm_kb(code),
                parse_mode="HTML",
            )
        except Exception:
            pass


async def _send_stars_invoice(target: Message, user_id: int, amount_kopecks: int) -> None:
    stars = max(1, amount_kopecks // config.kopecks_per_star)
    rubles = amount_kopecks // 100
    await target.answer_invoice(
        title="Пополнение баланса",
        description=f"Зачислить {rubles} ₽ на баланс бота",
        payload=f"stars_topup:{user_id}:{amount_kopecks}",
        currency="XTR",
        prices=[LabeledPrice(label="Звёзды", amount=stars)],
    )
