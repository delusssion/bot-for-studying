import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db.queries import get_referral_code, get_referral_stats, use_referral_code
from bot.keyboards.main_kb import main_menu_kb
from bot.keyboards.order_kb import trial_offer_kb
from bot.keyboards.referral_kb import referral_share_kb
from bot.utils.helpers import kopecks_to_rubles
from bot.utils.states import ReferralStates

router = Router()

_REF_CODE_RE = re.compile(r'^[A-Z]+-[A-Z0-9]{4}$')

_ERROR_MSGS = {
    "already_used": "❌ Вы уже использовали реферальный код",
    "not_found": "❌ Такой код не найден",
    "own_code": "❌ Нельзя использовать собственный код",
}

_TRIAL_OFFER_TEXT = (
    "🎁 <b>Подарок для новых пользователей!</b>\n\n"
    "Попробуйте сервис бесплатно — один раз.\n"
    "Выберите что вам сейчас нужнее:"
)


async def _send_trial_offer(msg: Message) -> None:
    await msg.answer(_TRIAL_OFFER_TEXT, reply_markup=trial_offer_kb(), parse_mode="HTML")


# ─── Registration flow callbacks ─────────────────────────────────────────────

@router.callback_query(F.data == "ref:enter", StateFilter(ReferralStates.entering_code))
async def ref_enter(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите реферальный код (формат: UCH-XXXX):")
    await callback.answer()


@router.callback_query(F.data == "ref:skip")
async def ref_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _send_trial_offer(callback.message)


@router.callback_query(
    F.data.startswith("ref:activate:"),
    StateFilter(ReferralStates.entering_code),
)
async def ref_activate(callback: CallbackQuery, state: FSMContext) -> None:
    code = callback.data.split(":", 2)[2]
    ok, reason = await use_referral_code(callback.from_user.id, code)
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    if ok:
        await callback.message.answer("✅ Бонус 50 ₽ зачислен на ваш баланс!")
    else:
        await callback.message.answer(_ERROR_MSGS.get(reason, "❌ Ошибка при активации кода"))
    await callback.answer()
    await _send_trial_offer(callback.message)


@router.message(StateFilter(ReferralStates.entering_code), F.text)
async def ref_code_text(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    data = await state.get_data()
    attempts = int(data.get("ref_attempts", 0)) + 1

    if not _REF_CODE_RE.match(code):
        if attempts >= 3:
            await state.clear()
            await message.answer(
                "❌ Неверный формат кода. Пример: UCH-A3X9\n\n"
                "Шаг пропущен — лимит попыток исчерпан.",
            )
            await _send_trial_offer(message)
        else:
            await state.update_data(ref_attempts=attempts)
            await message.answer(
                f"❌ Неверный формат кода. Пример: UCH-A3X9\n"
                f"Попытка {attempts}/3"
            )
        return

    ok, reason = await use_referral_code(message.from_user.id, code)
    if ok:
        await state.clear()
        await message.answer("✅ Бонус 50 ₽ зачислен на ваш баланс!")
        await _send_trial_offer(message)
    else:
        if attempts >= 3:
            await state.clear()
            await message.answer(
                _ERROR_MSGS.get(reason, "❌ Ошибка") + "\n\nШаг пропущен — лимит попыток исчерпан."
            )
            await _send_trial_offer(message)
        else:
            await state.update_data(ref_attempts=attempts)
            await message.answer(_ERROR_MSGS.get(reason, "❌ Ошибка"))


# ─── Trial offer skip (handled here since referral.py sends the offer) ────────

@router.callback_query(F.data == "trial:skip")
async def trial_skip(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Хорошо! Попробуйте позже через «📝 Новый заказ»")


# ─── Referral menu ────────────────────────────────────────────────────────────

@router.message(F.text == "👥 Рефералы")
async def referral_menu(message: Message) -> None:
    user_id = message.from_user.id
    code = await get_referral_code(user_id)
    stats = await get_referral_stats(user_id)

    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    link = f"t.me/{bot_username}?start={code}"

    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        f"Ваш код: <code>{code}</code>\n"
        f"Ваша ссылка: {link}\n\n"
        f"Приглашено друзей: <b>{stats['invited_count']}</b>\n"
        f"Заработано всего: <b>{kopecks_to_rubles(stats['earned_total'])}</b>\n"
        f"Ожидает начисления: <b>{kopecks_to_rubles(stats['pending_amount'])}</b> "
        "(когда друг сделает первый заказ)\n\n"
        "<b>Как это работает:</b>\n"
        "• Друг вводит ваш код → получает 50 ₽\n"
        "• Друг делает первый заказ → вы получаете 75 ₽"
    )

    await message.answer(
        text,
        reply_markup=referral_share_kb(bot_username, code),
        parse_mode="HTML",
    )
