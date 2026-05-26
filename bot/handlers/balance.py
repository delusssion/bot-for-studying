import logging

import pytz
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message

from bot.config import OZON_CARD_NUMBER, OZON_CARD_OWNER, config
from bot.db.queries import create_card_payment, get_user, get_user_balance
from bot.keyboards.balance_kb import balance_main_kb, card_payment_kb, topup_amounts_kb
from bot.keyboards.admin_kb import payment_confirm_kb
from bot.utils.helpers import kopecks_to_rubles
from bot.utils.states import BalanceStates

logger = logging.getLogger(__name__)
router = Router()
_MSK = pytz.timezone("Europe/Moscow")


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
        await _send_card_instructions(callback.message, amount_kopecks)
        await callback.answer()
        return

    await callback.answer()
    await _send_stars_invoice(callback.message, callback.from_user.id, amount_kopecks)


@router.callback_query(F.data == "topup_custom")
async def topup_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BalanceStates.entering_custom_amount)
    await callback.message.edit_text("Введите сумму пополнения в рублях (минимум 50 ₽):")
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
        await _send_card_instructions(message, amount_kopecks)
    else:
        await _send_stars_invoice(message, message.from_user.id, amount_kopecks)


async def _send_card_instructions(target: Message, amount_kopecks: int) -> None:
    rubles = amount_kopecks // 100
    text = (
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"Переведите ровно <b>{rubles} ₽</b> на карту:\n\n"
        f"💳 <code>{OZON_CARD_NUMBER}</code>\n"
        f"🏦 Ozon банк\n"
        f"👤 {OZON_CARD_OWNER}\n\n"
        f"После перевода нажмите кнопку ниже."
    )
    await target.answer(text, reply_markup=card_payment_kb(amount_kopecks), parse_mode="HTML")


@router.callback_query(F.data == "card_cancel")
async def card_cancel(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отменено")


@router.callback_query(F.data.startswith("card_paid:"))
async def card_paid(callback: CallbackQuery) -> None:
    amount_kopecks = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    payment = await create_card_payment(user_id, amount_kopecks)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "⏳ Ожидаем подтверждения.\n"
        "Обычно занимает до 15 минут.\n"
        "Как только проверим — получите уведомление."
    )
    await callback.answer()

    from datetime import timezone
    paid_at_msk = payment["paid_at"].replace(tzinfo=timezone.utc).astimezone(_MSK)
    time_str = paid_at_msk.strftime("%H:%M")
    date_str = paid_at_msk.strftime("%d.%m.%Y")
    rubles = amount_kopecks // 100

    user = await get_user(user_id)
    uname = f"@{user['username']}" if user and user.get("username") else str(user_id)

    notify_text = (
        f"💳 <b>Новое пополнение!</b>\n\n"
        f"👤 Пользователь: {uname} (<code>{user_id}</code>)\n"
        f"💰 Сумма: <b>{rubles} ₽</b>\n"
        f"🕐 Время оплаты: <b>{time_str} МСК</b> {date_str}\n\n"
        f"Проверьте входящий перевод на {rubles} ₽\n"
        f"в приложении Ozon около {time_str}"
    )
    for admin_id in config.admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                notify_text,
                reply_markup=payment_confirm_kb(payment["id"]),
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
