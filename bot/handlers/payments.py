import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, PreCheckoutQuery

from bot.config import config
from bot.db.queries import add_balance, create_payment, get_user_balance, update_payment_status
from bot.keyboards.main_kb import main_menu_kb
from bot.utils.helpers import kopecks_to_rubles
from bot.utils.states import EditStates

logger = logging.getLogger(__name__)
router = Router()


# ─── Pre-checkout ─────────────────────────────────────────────────────────────

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


# ─── Successful payment ───────────────────────────────────────────────────────

@router.message(F.successful_payment)
async def successful_payment(message: Message, state: FSMContext) -> None:
    sp = message.successful_payment
    payload = sp.invoice_payload
    user_id = message.from_user.id
    parts = payload.split(":")
    purpose = parts[0]

    # Resolve kopecks amount from payload
    if purpose in ("manual_topup", "order_topup", "stars_topup"):
        amount_kopecks = int(parts[2])
    elif purpose == "paid_edit":
        amount_kopecks = config.price_extra_edit
    else:
        amount_kopecks = sp.total_amount * config.kopecks_per_star

    payment = await create_payment(
        user_id=user_id,
        amount_kopecks=amount_kopecks,
        payment_type="stars",
        external_id=sp.telegram_payment_charge_id,
    )
    await add_balance(user_id, amount_kopecks)
    await update_payment_status(payment["id"], "success")

    logger.info(
        "Payment success user=%s amount=%s purpose=%s", user_id, amount_kopecks, purpose
    )

    current_state = await state.get_state()
    fsm_data = await state.get_data()
    payment_purpose = fsm_data.get("payment_purpose")

    # Balance top-up (all topup variants)
    if purpose in ("stars_topup", "manual_topup"):
        balance = await get_user_balance(user_id)
        await message.answer(
            f"✅ <b>Баланс пополнен на {kopecks_to_rubles(amount_kopecks)}!</b>\n"
            f"Текущий баланс: {kopecks_to_rubles(balance)}",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
        return

    # Top-up for a pending order (inline Stars invoice from no_balance_kb)
    if purpose == "order_topup":
        await message.answer(
            f"✅ Баланс пополнен на {kopecks_to_rubles(amount_kopecks)}!\n"
            "Попробуйте снова подтвердить заказ — теперь средств должно хватить."
        )
        await state.clear()
        return

    # Paid edit via Stars invoice
    if purpose == "paid_edit" or (
        current_state == EditStates.confirming_paid_edit
        and payment_purpose == "paid_edit"
    ):
        instruction = fsm_data.get("pending_edit_instruction", "")
        edit_order_id = fsm_data.get("edit_order_id") or (
            int(parts[2]) if purpose == "paid_edit" else None
        )
        await state.clear()

        if instruction and edit_order_id:
            from bot.db.queries import get_order_by_id
            from bot.handlers.orders import _apply_edit_and_send

            order = await get_order_by_id(edit_order_id)
            if order:
                await message.answer("⏳ Применяю платную правку...")
                await _apply_edit_and_send(
                    message.bot, user_id, order,
                    instruction, "free_text", True, config.price_extra_edit,
                )
                return

    # Fallback
    await message.answer(
        f"✅ Баланс пополнен на <b>{kopecks_to_rubles(amount_kopecks)}</b>!",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
