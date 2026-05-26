import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message

from bot.config import config
from bot.db.queries import get_user_balance
from bot.keyboards.balance_kb import balance_main_kb, topup_amounts_kb
from bot.utils.helpers import kopecks_to_rubles
from bot.utils.states import BalanceStates

logger = logging.getLogger(__name__)
router = Router()

_METHOD_NAMES = {
    "stars": "Telegram Stars",
    "card": "Банковская карта",
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

    if method != "stars":
        name = _METHOD_NAMES.get(method, method)
        await callback.message.edit_text(
            f"⏳ Способ оплаты «{name}» будет добавлен в ближайшее время.\n"
            "Сейчас доступны Telegram Stars."
        )
        await callback.answer()
        return

    await callback.answer()
    await _send_stars_invoice(callback.message, callback.from_user.id, amount_kopecks)


@router.callback_query(F.data == "topup_custom")
async def topup_custom(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    method = data.get("topup_method", "stars")

    if method != "stars":
        name = _METHOD_NAMES.get(method, method)
        await callback.message.edit_text(
            f"⏳ Способ оплаты «{name}» будет добавлен в ближайшее время.\n"
            "Сейчас доступны Telegram Stars."
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

    await state.clear()
    await _send_stars_invoice(message, message.from_user.id, rubles * 100)


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
