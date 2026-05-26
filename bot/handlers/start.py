import re
from datetime import datetime, timedelta

import pytz
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import VIP_DAILY_LIMIT
from bot.db.queries import get_or_create_user, get_user, get_vip_usage_today, set_user_agreed
from bot.keyboards.main_kb import accept_terms_kb, get_support_button, main_menu_kb
from bot.keyboards.referral_kb import referral_code_activate_kb, referral_code_input_kb
from bot.utils.states import ReferralStates

router = Router()

_REF_CODE_RE = re.compile(r'^[A-Z]+-[A-Z0-9]{4}$')
_MSK = pytz.timezone("Europe/Moscow")

WELCOME_TEXT = (
    "👋 <b>Привет! Я StudyBot</b> — помогу тебе с учебными заданиями.\n\n"
    "<b>Что умею:</b>\n"
    "🔬 Лабораторные работы (.docx)\n"
    "📊 Презентации (.pptx)\n"
    "✍️ Контрольные и текстовые ответы\n"
    "📦 Лаба + презентация в одном заказе\n\n"
    "<b>Правила использования:</b>\n"
    "• Сгенерированные работы — основа для самостоятельной доработки.\n"
    "• Ответственность за сдачу работы лежит на пользователе.\n"
    "• Оплата невозвратна кроме технических сбоев.\n"
    "• Запрещено использование для причинения вреда.\n\n"
    "Нажимая «Принять и начать», вы соглашаетесь с правилами."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    # Parse deep-link parameter
    ref_code: str | None = None
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        param = args[1].strip()
        if _REF_CODE_RE.match(param):
            ref_code = param

    user = await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    if not user["agreed"]:
        if ref_code:
            await state.update_data(pending_ref_code=ref_code)
        await message.answer(WELCOME_TEXT, reply_markup=accept_terms_kb(), parse_mode="HTML")
        return

    is_vip = bool(user.get("is_vip"))
    await _show_main_menu(message, is_vip=is_vip)


@router.callback_query(F.data == "agree")
async def on_agree(callback: CallbackQuery, state: FSMContext) -> None:
    await set_user_agreed(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=None)

    # Show the persistent keyboard first
    await callback.message.answer(
        "✅ Добро пожаловать! Используйте меню внизу 👇",
        reply_markup=main_menu_kb(),
    )

    # Then show the referral step
    data = await state.get_data()
    pending_code = data.get("pending_ref_code")

    await state.set_state(ReferralStates.entering_code)
    await state.update_data(ref_attempts=0)

    if pending_code:
        await callback.message.answer(
            f"🎁 <b>Вас пригласил друг!</b>\n\n"
            f"Введите код <code>{pending_code}</code>, чтобы получить <b>+50 ₽</b> на баланс.",
            reply_markup=referral_code_activate_kb(pending_code),
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(
            "🎁 <b>У вас есть реферальный код?</b>\n\n"
            "Введите его и получите <b>+50 ₽</b> на баланс!",
            reply_markup=referral_code_input_kb(),
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await get_user(callback.from_user.id)
    is_vip = bool(user and user.get("is_vip"))
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb(is_vip=is_vip))
    await callback.answer()


@router.message(F.text == "👑 VIP статус")
async def vip_status(message: Message) -> None:
    user = await get_user(message.from_user.id)
    if not user or not user.get("is_vip"):
        await message.answer("У вас нет VIP статуса.")
        return

    usage = await get_vip_usage_today(message.from_user.id)
    used = usage.get("requests_used", 0)
    limit = user.get("vip_daily_limit") or VIP_DAILY_LIMIT

    now_msk = datetime.now(_MSK)
    midnight_msk = (now_msk + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    delta = midnight_msk - now_msk
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60

    await message.answer(
        f"👑 <b>VIP статус активен</b>\n\n"
        f"Использовано сегодня: <b>{used}/{limit}</b>\n"
        f"Лимит обновится через: <b>{hours}ч {minutes}мин</b> (00:00 МСК)\n\n"
        f"VIP заказы бесплатны и проходят вне очереди.",
        parse_mode="HTML",
    )


async def _show_main_menu(message: Message, is_vip: bool = False) -> None:
    await message.answer(
        f"Привет, <b>{message.from_user.first_name}</b>! Выберите действие 👇",
        reply_markup=main_menu_kb(is_vip=is_vip),
        parse_mode="HTML",
    )
