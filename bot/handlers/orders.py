import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import List, Optional

import pytz
from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery, FSInputFile, Message,
)

from bot.config import VIP_DAILY_LIMIT, config
from bot.db.queries import (
    add_balance, count_user_orders_last_hour, create_edit, create_order,
    deduct_balance, get_active_order_for_user, get_order_by_id,
    get_trial_status, get_user, get_user_orders, get_vip_usage_today,
    has_active_subscription, increment_vip_usage,
    mark_trial_used, set_free_edit_used, update_order_result, update_order_status,
)
from bot.keyboards.edit_kb import (
    cancel_edit_kb, color_scheme_kb, lab_edit_kb,
    paid_edit_confirm_kb, pres_edit_kb, text_edit_kb,
)
from bot.keyboards.main_kb import main_menu_kb
from bot.keyboards.order_kb import (
    confirm_order_kb, custom_style_back_kb, description_input_kb,
    measurements_kb, more_photos_kb,
    no_balance_kb, no_orders_kb, order_detail_kb,
    orders_rich_kb, order_type_kb, requirements_kb,
    style_kb, subject_input_kb, topic_input_kb,
    trial_confirm_kb, trial_cta_kb, trial_type_kb, vip_confirm_kb,
)
from bot.services.ai_service import (
    apply_edit, generate_lab, generate_presentation, generate_text_answer,
)
from bot.services.file_generator import (
    create_lab_docx, create_presentation_pptx, format_text_answer,
)
from bot.utils.helpers import (
    format_datetime, kopecks_to_rubles, order_status_label, order_type_label,
)
from bot.utils.media_collector import (
    MAX_PHOTOS, MediaCollector, convert_pdf_to_images,
    pop_pdf_cache, store_pdf_cache,
)
from bot.utils.queue_manager import generation_queue
from bot.utils.states import EditStates, OrderStates

logger = logging.getLogger(__name__)
router = Router()
media_collector = MediaCollector()

MAX_TEXT_LEN = 3000
MAX_PDF_MB = 10

ORDER_PRICES = {
    "lab_docx": lambda: config.price_lab_docx,
    "presentation_pptx": lambda: config.price_presentation,
    "text_answer": lambda: config.price_text_answer,
    "lab_plus_pres": lambda: config.price_lab_plus_pres,
}

LAB_TYPES = {"lab_docx", "lab_plus_pres"}
PRES_TYPES = {"presentation_pptx", "lab_plus_pres"}

_STYLE_LABELS = {
    "blue":    "🔵 Классический синий",
    "green":   "🟢 Академический зелёный",
    "dark":    "⚫ Тёмная тема",
    "minimal": "⚪ Минималистичный",
}


def _style_display(data: dict) -> str:
    cs = data.get("color_scheme", "blue")
    if cs == "custom":
        return f"✏️ Свой: {data.get('color_scheme_custom', '')[:50]}"
    return _STYLE_LABELS.get(cs, "🔵 Классический синий")


# ─── Guards ───────────────────────────────────────────────────────────────────

async def _check_agreed(from_user, message: Message) -> bool:
    from bot.db.queries import get_or_create_user
    user = await get_or_create_user(
        from_user.id, from_user.username, from_user.full_name
    )
    if not user["agreed"]:
        await message.answer("Сначала примите правила — нажмите /start")
        return False
    return True


async def _check_no_active_order(from_user, message: Message) -> bool:
    active = await get_active_order_for_user(from_user.id)
    if active:
        await message.answer(
            f"⚠️ У вас уже есть активный заказ #{active['id']} (статус: {order_status_label(active['status'])}).\n"
            "Дождитесь его завершения."
        )
        return False
    return True


# ─── Step 1: New order / type selection ───────────────────────────────────────

_MSK = pytz.timezone("Europe/Moscow")


def _vip_reset_countdown() -> str:
    now_msk = datetime.now(_MSK)
    midnight = (now_msk + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = midnight - now_msk
    h = delta.seconds // 3600
    m = (delta.seconds % 3600) // 60
    return f"{h}ч {m}мин"


@router.message(F.text == "📝 Новый заказ")
async def new_order(message: Message, state: FSMContext) -> None:
    if not await _check_agreed(message.from_user, message):
        return
    if not await _check_no_active_order(message.from_user, message):
        return

    user_id = message.from_user.id
    user = await get_user(user_id)
    is_vip = bool(user and user.get("is_vip"))

    if is_vip:
        usage = await get_vip_usage_today(user_id)
        daily_limit = (user.get("vip_daily_limit") or VIP_DAILY_LIMIT)
        if usage.get("requests_used", 0) >= daily_limit:
            await message.answer(
                f"👑 VIP лимит исчерпан на сегодня "
                f"({usage['requests_used']}/{daily_limit}).\n"
                f"Лимит обновится через {_vip_reset_countdown()} (00:00 МСК)."
            )
            return
    else:
        # Anti-spam: 3 orders/hour (subscribed users unlimited)
        is_subscribed = await has_active_subscription(user_id)
        if not is_subscribed:
            recent = await count_user_orders_last_hour(user_id)
            if recent >= 3:
                await message.answer(
                    "⏱ Лимит заказов: не более 3 в час.\n"
                    "Подождите немного или оформите подписку — нажмите «⭐ Подписка»."
                )
                return

    await state.clear()
    await state.update_data(is_vip_order=is_vip)
    trial_available = (not is_vip) and (not await get_trial_status(user_id))
    await message.answer(
        "Выберите тип задания:",
        reply_markup=order_type_kb(trial_available=trial_available),
    )
    await state.set_state(OrderStates.choosing_type)


@router.callback_query(F.data == "ot:trial", StateFilter(OrderStates.choosing_type))
async def order_type_trial(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🎁 <b>Выберите тип бесплатного заказа:</b>",
        reply_markup=trial_type_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "trial:skip", StateFilter(OrderStates.choosing_type))
async def trial_skip_in_order(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Хорошо! Можете воспользоваться позже")


@router.callback_query(F.data.in_({"trial:lab_docx", "trial:text_answer"}))
async def trial_type_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    part = callback.data.split(":")[1]
    if not await _check_agreed(callback.from_user, callback.message):
        await callback.answer()
        return
    if not await _check_no_active_order(callback.from_user, callback.message):
        await callback.answer()
        return
    if await get_trial_status(callback.from_user.id):
        await callback.message.answer(
            "🎁 Бесплатный заказ уже использован.\n"
            "Выберите обычный тип заказа через «📝 Новый заказ»."
        )
        await callback.answer()
        return

    await state.clear()
    await state.update_data(order_type=part, is_trial_order=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    sent = await callback.message.answer(
        f"Тип: <b>{order_type_label(part)}</b> (пробный — бесплатно)\n\n"
        "Введите <b>предмет</b> (например: Физика, Программирование):",
        reply_markup=subject_input_kb(),
        parse_mode="HTML",
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(OrderStates.entering_subject)
    await callback.answer()


@router.callback_query(F.data.startswith("ot:"), StateFilter(OrderStates.choosing_type))
async def order_type_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    order_type = callback.data.split(":")[1]
    await state.update_data(order_type=order_type)
    await callback.message.edit_reply_markup(reply_markup=None)
    sent = await callback.message.answer(
        f"Тип: <b>{order_type_label(order_type)}</b>\n\n"
        "Введите <b>предмет</b> (например: Физика, Программирование):",
        reply_markup=subject_input_kb(),
        parse_mode="HTML",
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(OrderStates.entering_subject)
    await callback.answer()


# ─── Step 2: Subject ──────────────────────────────────────────────────────────

@router.message(StateFilter(OrderStates.entering_subject))
async def enter_subject(message: Message, state: FSMContext) -> None:
    await state.update_data(subject=message.text.strip())
    sent = await message.answer(
        "Введите <b>тему / название работы</b>:",
        reply_markup=topic_input_kb(),
        parse_mode="HTML",
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(OrderStates.entering_topic)


# ─── Step 3: Topic ────────────────────────────────────────────────────────────

@router.message(StateFilter(OrderStates.entering_topic))
async def enter_topic(message: Message, state: FSMContext) -> None:
    await state.update_data(topic=message.text.strip())
    sent = await message.answer(
        "Отправьте <b>условие / задание</b>:\n\n"
        "• Текстом (до 3 000 символов)\n"
        "• Фотографиями задания (до 20 шт.)\n"
        "• PDF-файлом (до 10 МБ, до 10 стр.)",
        reply_markup=description_input_kb(),
        parse_mode="HTML",
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(OrderStates.entering_description)


# ─── Step 4: Description — text ───────────────────────────────────────────────

@router.message(
    StateFilter(OrderStates.entering_description),
    F.text,
)
async def description_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) > MAX_TEXT_LEN:
        await message.answer(
            f"❌ Текст слишком длинный: {len(text)} символов. Максимум {MAX_TEXT_LEN}."
        )
        return
    await state.update_data(description=text, photo_ids=[], pdf_photos=False)
    await _go_to_measurements_or_requirements(message, state)


# ─── Step 4b: Description — photos ───────────────────────────────────────────

@router.message(
    StateFilter(OrderStates.entering_description, OrderStates.waiting_photos),
    F.photo,
)
async def description_photo(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current == OrderStates.entering_description:
        await state.update_data(description="[фото задания]", pdf_photos=False)
        await message.answer(
            "📸 Получил фото! Отправляйте все страницы сразу (до 10 за раз, до 20 всего).\n"
            "Когда загрузите все — нажмите кнопку ниже."
        )
        await state.set_state(OrderStates.waiting_photos)

    data = await state.get_data()
    existing: List[str] = data.get("photo_ids", [])
    if len(existing) >= MAX_PHOTOS:
        await message.answer(f"❌ Достигнут лимит {MAX_PHOTOS} фото.")
        return

    async def on_finalize(group_id: str, file_ids: List[str], msg: Message) -> None:
        d = await state.get_data()
        acc: List[str] = d.get("photo_ids", [])
        new_total = acc + [fid for fid in file_ids if fid not in acc]

        if len(new_total) > MAX_PHOTOS:
            await msg.answer(f"❌ Превышен лимит {MAX_PHOTOS} фото. Принято {len(acc)}.")
            return

        await state.update_data(photo_ids=new_total)
        await msg.answer(
            f"✅ Загружено страниц: <b>{len(new_total)}/{MAX_PHOTOS}</b>\n\n"
            "Это все страницы задания?",
            reply_markup=more_photos_kb(),
            parse_mode="HTML",
        )
        await state.set_state(OrderStates.waiting_more_photos)

    await media_collector.add_photo(message, on_finalize)


@router.callback_query(F.data == "photos:done", StateFilter(OrderStates.waiting_more_photos))
async def photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _go_to_measurements_or_requirements(callback.message, state)


@router.callback_query(F.data == "photos:more", StateFilter(OrderStates.waiting_more_photos))
async def photos_more(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "📸 Отправьте следующие фото (первые 10 страниц за раз):"
    )
    await state.set_state(OrderStates.waiting_photos)
    await callback.answer()


# ─── Step 4c: Description — PDF ───────────────────────────────────────────────

@router.message(
    StateFilter(OrderStates.entering_description),
    F.document,
)
async def description_pdf(message: Message, state: FSMContext) -> None:
    doc = message.document
    if not doc.mime_type == "application/pdf":
        await message.answer("❌ Пожалуйста, отправьте файл в формате PDF.")
        return

    size_mb = (doc.file_size or 0) / 1024 / 1024
    if size_mb > MAX_PDF_MB:
        await message.answer(
            f"❌ Файл слишком большой: {size_mb:.1f} МБ. Максимум {MAX_PDF_MB} МБ."
        )
        return

    await state.set_state(OrderStates.waiting_pdf)
    processing_msg = await message.answer("⏳ Обрабатываю PDF...")

    try:
        buf = await message.bot.download(doc.file_id)
        pdf_bytes = buf.read()
        images = await convert_pdf_to_images(pdf_bytes, max_pages=10)
        store_pdf_cache(message.from_user.id, images)
        await state.update_data(description="[PDF задание]", pdf_photos=True, photo_ids=[])
        await processing_msg.edit_text(
            f"✅ PDF обработан: {len(images)} страниц. Продолжаем..."
        )
        await _go_to_measurements_or_requirements(message, state)
    except Exception as e:
        logger.exception("PDF conversion error: %s", e)
        await processing_msg.edit_text(
            "❌ Ошибка при обработке PDF. Попробуйте отправить фотографии страниц."
        )
        await state.set_state(OrderStates.entering_description)


# ─── Step 5: Measurements ─────────────────────────────────────────────────────

async def _go_to_measurements_or_requirements(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_type = data.get("order_type", "")
    if order_type in LAB_TYPES:
        sent = await message.answer(
            "📐 <b>Данные измерений / вычислений:</b>",
            reply_markup=measurements_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.entering_measurements)
    else:
        sent = await message.answer(
            "📋 <b>Дополнительные требования:</b>",
            reply_markup=requirements_kb(is_lab=False),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.entering_requirements)


@router.callback_query(F.data == "meas:enter", StateFilter(OrderStates.entering_measurements))
async def meas_enter(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите данные измерений:")
    await state.update_data(_awaiting_meas_text=True)
    await callback.answer()


@router.callback_query(F.data == "meas:typical", StateFilter(OrderStates.entering_measurements))
async def meas_typical(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(measurements=None)
    await callback.message.edit_reply_markup(reply_markup=None)
    sent = await callback.message.answer(
        "📋 <b>Дополнительные требования:</b>",
        reply_markup=requirements_kb(is_lab=True),
        parse_mode="HTML",
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(OrderStates.entering_requirements)
    await callback.answer()


@router.message(StateFilter(OrderStates.entering_measurements), F.text)
async def meas_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("_awaiting_meas_text"):
        return
    await state.update_data(measurements=message.text.strip(), _awaiting_meas_text=False)
    sent = await message.answer(
        "📋 <b>Дополнительные требования:</b>",
        reply_markup=requirements_kb(is_lab=True),
        parse_mode="HTML",
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(OrderStates.entering_requirements)


# ─── Step 6: Requirements ─────────────────────────────────────────────────────

@router.callback_query(F.data == "req:enter", StateFilter(OrderStates.entering_requirements))
async def req_enter(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите дополнительные требования:")
    await state.update_data(_awaiting_req_text=True)
    await callback.answer()


@router.callback_query(F.data == "req:standard", StateFilter(OrderStates.entering_requirements))
async def req_standard(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(requirements=None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await _go_to_style_or_confirmation(callback.message, state)
    await callback.answer()


@router.message(StateFilter(OrderStates.entering_requirements), F.text)
async def req_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("_awaiting_req_text"):
        return
    await state.update_data(requirements=message.text.strip(), _awaiting_req_text=False)
    await _go_to_style_or_confirmation(message, state)


# ─── Step 6.5: Style selection (presentations only) ───────────────────────────

async def _go_to_style_or_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("order_type", "") in PRES_TYPES:
        sent = await message.answer(
            "🎨 <b>Выберите стиль презентации:</b>\n"
            "<i>(влияет на цветовую схему и оформление)</i>",
            reply_markup=style_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.entering_style)
    else:
        await _show_confirmation(message, state)


@router.callback_query(F.data.startswith("style:"), StateFilter(OrderStates.entering_style))
async def style_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    scheme = callback.data.split(":", 1)[1]
    await callback.message.edit_reply_markup(reply_markup=None)

    if scheme == "custom":
        sent = await callback.message.answer(
            "✏️ <b>Опишите желаемый стиль:</b>\n\n"
            "Например:\n"
            "— красный и белый, строгий деловой стиль\n"
            "— фиолетовый градиент, современный\n"
            "— оранжевый акцент на белом фоне\n"
            "— корпоративный стиль в серых тонах\n\n"
            "Или просто напишите основной цвет:",
            reply_markup=custom_style_back_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id, color_scheme="custom")
        await state.set_state(OrderStates.entering_custom_style)
    else:
        await state.update_data(color_scheme=scheme, color_scheme_custom=None)
        await _show_confirmation(callback.message, state)

    await callback.answer()


@router.message(StateFilter(OrderStates.entering_custom_style), F.text)
async def custom_style_text(message: Message, state: FSMContext) -> None:
    await state.update_data(color_scheme="custom", color_scheme_custom=message.text.strip())
    await _show_confirmation(message, state)


# ─── Step 7: Confirmation ─────────────────────────────────────────────────────

async def _show_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_type = data["order_type"]
    is_trial = data.get("is_trial_order", False)
    is_vip = data.get("is_vip_order", False)
    has_style = order_type in PRES_TYPES

    if is_vip:
        price = 0
        header = "👑 VIP заказ — бесплатно!"
    elif is_trial:
        price = 0
        header = "✅ Пробный заказ — бесплатно!"
    else:
        price = ORDER_PRICES[order_type]()
        header = "📋 <b>Подтверждение заказа</b>"

    lines = [f"{header}\n"]
    lines += [
        f"Тип: {order_type_label(order_type)}",
        f"Предмет: {data.get('subject', '—')}",
        f"Тема: {data.get('topic', '—')}",
        f"Задание: {data.get('description', '—')[:100]}",
    ]
    if data.get("photo_ids"):
        lines.append(f"Фото: {len(data['photo_ids'])} стр.")
    if data.get("pdf_photos"):
        lines.append("PDF: ✅")
    if data.get("measurements"):
        lines.append("Данные измерений: есть")
    if data.get("requirements"):
        lines.append(f"Требования: {data['requirements'][:80]}")
    if has_style:
        lines.append(f"Стиль: {_style_display(data)}")
    lines.append(f"\n💰 <b>Спишем: {kopecks_to_rubles(price)}</b>")

    if is_vip:
        kb = vip_confirm_kb(has_style)
    elif is_trial:
        kb = trial_confirm_kb(has_style)
    else:
        kb = confirm_order_kb(price, has_style)

    sent = await message.answer(
        "\n".join(lines),
        reply_markup=kb,
        parse_mode="HTML",
    )
    await state.update_data(last_bot_message_id=sent.message_id)
    await state.set_state(OrderStates.confirming_order)


@router.callback_query(F.data == "confirm_order", StateFilter(OrderStates.confirming_order))
async def confirm_order(callback: CallbackQuery, state: FSMContext) -> None:
    await _try_confirm(callback, state)


@router.callback_query(F.data == "retry_confirm", StateFilter(OrderStates.confirming_order))
async def retry_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _try_confirm(callback, state)


@router.callback_query(F.data == "confirm_trial_order", StateFilter(OrderStates.confirming_order))
async def confirm_trial_order(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id

    if await get_trial_status(user_id):
        await callback.message.answer(
            "🎁 Бесплатный заказ уже использован.\n"
            "Выберите обычный тип через «📝 Новый заказ»."
        )
        await state.clear()
        await callback.answer()
        return

    await mark_trial_used(user_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await _create_and_generate(
        callback.message, state, data,
        order_type=data["order_type"],
        price=0,
        user_id=user_id,
        is_trial=True,
    )
    await callback.answer()


async def _try_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id
    order_type = data["order_type"]
    is_vip = data.get("is_vip_order", False)

    if is_vip:
        price = 0
    else:
        price = ORDER_PRICES[order_type]()
        ok = await deduct_balance(user_id, price)
        if not ok:
            from bot.db.queries import get_user_balance
            balance = await get_user_balance(user_id)
            shortage = price - balance

            # Stay in confirming_order so user can retry without re-entering data
            await state.set_state(OrderStates.confirming_order)

            await callback.message.answer(
                f"💳 <b>Недостаточно средств на балансе</b>\n\n"
                f"Стоимость заказа: {kopecks_to_rubles(price)}\n"
                f"Ваш баланс: {kopecks_to_rubles(balance)}\n"
                f"Нужно пополнить: <b>{kopecks_to_rubles(shortage)}</b>\n\n"
                "Пополните баланс и нажмите «Попробовать снова» — данные заказа сохранены.",
                reply_markup=no_balance_kb(shortage),
                parse_mode="HTML",
            )
            await callback.answer()
            return

    await callback.message.edit_reply_markup(reply_markup=None)
    await _create_and_generate(
        callback.message, state, data, order_type, price, user_id, is_vip=is_vip
    )
    await callback.answer()


@router.callback_query(F.data.startswith("topup_order:"), StateFilter(OrderStates.confirming_order))
async def topup_for_order(callback: CallbackQuery, state: FSMContext) -> None:
    amount_kopecks = int(callback.data.split(":")[1])
    stars = max(1, amount_kopecks // config.kopecks_per_star)
    await callback.message.answer_invoice(
        title="Пополнение баланса",
        description=f"Для оплаты заказа: {kopecks_to_rubles(amount_kopecks)}",
        payload=f"order_topup:{callback.from_user.id}:{amount_kopecks}",
        currency="XTR",
        prices=[{"label": "Звёзды", "amount": stars}],
    )
    await callback.answer()


# ─── Generation ───────────────────────────────────────────────────────────────

async def _create_and_generate(
    message: Message,
    state: FSMContext,
    data: dict,
    order_type: str,
    price: int,
    user_id: int,
    is_trial: bool = False,
    is_vip: bool = False,
) -> None:
    input_data = {
        "subject": data.get("subject"),
        "topic": data.get("topic"),
        "description": data.get("description"),
        "measurements": data.get("measurements"),
        "requirements": data.get("requirements"),
        "color_scheme": data.get("color_scheme", "blue"),
        "color_scheme_custom": data.get("color_scheme_custom"),
    }

    order = await create_order(user_id, order_type, input_data, price, is_trial=is_trial)
    await state.clear()

    # Download photos before showing status message
    photos: List[bytes] | None = None
    photo_ids: List[str] = data.get("photo_ids", [])
    if photo_ids:
        photos = []
        for fid in photo_ids:
            photos.append(await MediaCollector.get_photo_bytes(fid, message.bot))
    elif data.get("pdf_photos"):
        photos = pop_pdf_cache(user_id)

    # Notify user — different message if queue is busy or for presentations
    if generation_queue.is_full:
        wait_min = generation_queue.estimate_wait_minutes()
        await message.answer(
            f"⏳ Небольшая очередь — ваш заказ будет готов примерно через ~{wait_min} мин.\n"
            "Пришлю файл как только будет готово."
        )
    elif order_type in PRES_TYPES:
        await message.answer(
            "⏳ <b>Генерирую презентацию...</b>\n"
            "Используем мощную модель и проверку качества — "
            "обычно занимает 2–3 минуты. Пожалуйста, подождите.",
            parse_mode="HTML",
        )
    else:
        await message.answer("⏳ Генерирую работу, обычно занимает 30–60 секунд...")

    try:
        await generation_queue.submit(
            _generate_for_order(message, order["id"], order_type, input_data, photos, user_id, is_vip=is_vip),
            is_trial=is_trial,
            is_vip=is_vip,
            timeout=240 if order_type in PRES_TYPES else None,
        )
    except asyncio.TimeoutError:
        logger.error("Generation timed out for order #%s user=%s", order["id"], user_id)
        await update_order_status(order["id"], "error")
        await add_balance(user_id, price)
        await message.answer(
            "❌ Время генерации превышено (120 сек).\n"
            "Средства возвращены на баланс. Попробуйте повторить заказ."
        )
    except Exception as e:
        logger.exception("Generation error order #%s: %s", order["id"], e)
        await update_order_status(order["id"], "error")
        await add_balance(user_id, price)
        await message.answer(
            "❌ Ошибка при генерации. Средства возвращены на баланс.\n"
            "Попробуйте повторить или обратитесь в поддержку."
        )


async def _generate_for_order(
    message: Message,
    order_id: int,
    order_type: str,
    input_data: dict,
    photos: Optional[List[bytes]],
    user_id: int = 0,
    is_vip: bool = False,
) -> None:
    await update_order_status(order_id, "processing")
    bot: Bot = message.bot
    if not user_id:
        user_id = message.chat.id

    order_info = await get_order_by_id(order_id)
    is_trial = bool(order_info and order_info["is_trial"])
    if not is_trial and not is_vip:
        try:
            from bot.db.queries import check_and_pay_referral_bonus
            await check_and_pay_referral_bonus(user_id, bot, is_trial=False)
        except Exception as e:
            logger.error("Referral bonus error order #%s: %s", order_id, e)

    if order_type == "lab_docx":
        await _gen_lab(bot, user_id, order_id, input_data, photos)
        if is_vip:
            try:
                await increment_vip_usage(user_id)
            except Exception as e:
                logger.error("VIP usage increment error order #%s: %s", order_id, e)

    elif order_type == "presentation_pptx":
        await _gen_pres(bot, user_id, order_id, input_data, photos)
        if is_vip:
            try:
                await increment_vip_usage(user_id)
            except Exception as e:
                logger.error("VIP usage increment error order #%s: %s", order_id, e)

    elif order_type == "text_answer":
        await _gen_text(bot, user_id, order_id, input_data)
        if is_vip:
            try:
                await increment_vip_usage(user_id)
            except Exception as e:
                logger.error("VIP usage increment error order #%s: %s", order_id, e)

    elif order_type == "lab_plus_pres":
        # Generate both; reuse same AI data
        lab_result = await generate_lab(input_data, photos=photos, user_id=user_id)
        pres_result = await generate_presentation(input_data, photos=photos, user_id=user_id)

        combined_json = {"lab": lab_result["json_data"], "presentation": pres_result["json_data"]}
        tokens_in = lab_result["tokens_input"] + pres_result["tokens_input"]
        tokens_out = lab_result["tokens_output"] + pres_result["tokens_output"]
        cost = int((tokens_in * 0.003 + tokens_out * 0.015) * 100)

        lab_file_id = await _send_docx(
            bot, user_id, order_id, lab_result["json_data"], is_combo=True
        )
        pres_file_id = await _send_pptx(
            bot, user_id, order_id, pres_result["json_data"], is_combo=True
        )
        file_id = f"{lab_file_id}|{pres_file_id}"

        try:
            await update_order_result(
                order_id, combined_json, tokens_in, tokens_out, cost, file_id
            )
            order = await get_order_by_id(order_id)
            kb = lab_edit_kb(order_id, free_edit_available=not order["free_edit_used"])
            await bot.send_message(user_id, f"✅ Заказ #{order_id} готов!", reply_markup=kb)
        except Exception as e:
            logger.error("Post-send DB error combo order #%s: %s", order_id, e)
        if is_vip:
            try:
                await increment_vip_usage(user_id)
            except Exception as e:
                logger.error("VIP usage increment error order #%s: %s", order_id, e)


async def _gen_lab(
    bot: Bot, user_id: int, order_id: int, data: dict, photos: Optional[List[bytes]]
) -> None:
    result = await generate_lab(data, photos=photos, user_id=user_id)
    file_id = await _send_docx(bot, user_id, order_id, result["json_data"])
    cost = int((result["tokens_input"] * 0.003 + result["tokens_output"] * 0.015) * 100)
    try:
        await update_order_result(
            order_id, result["json_data"],
            result["tokens_input"], result["tokens_output"], cost, file_id,
        )
        order = await get_order_by_id(order_id)
        kb = lab_edit_kb(order_id, free_edit_available=not order["free_edit_used"])
        await bot.send_message(user_id, f"✅ Готово! Заказ #{order_id}", reply_markup=kb)
        if order["is_trial"]:
            await _send_trial_cta(bot, user_id)
    except Exception as e:
        logger.error("Post-send DB error lab order #%s: %s", order_id, e)


async def _gen_pres(
    bot: Bot, user_id: int, order_id: int, data: dict, photos: Optional[List[bytes]]
) -> None:
    result = await generate_presentation(data, photos=photos, user_id=user_id)
    file_id = await _send_pptx(bot, user_id, order_id, result["json_data"])
    cost = int((result["tokens_input"] * 0.003 + result["tokens_output"] * 0.015) * 100)
    try:
        await update_order_result(
            order_id, result["json_data"],
            result["tokens_input"], result["tokens_output"], cost, file_id,
        )
        order = await get_order_by_id(order_id)
        kb = pres_edit_kb(order_id, free_edit_available=not order["free_edit_used"])
        await bot.send_message(user_id, f"✅ Готово! Заказ #{order_id}", reply_markup=kb)
    except Exception as e:
        logger.error("Post-send DB error pres order #%s: %s", order_id, e)


async def _gen_text(bot: Bot, user_id: int, order_id: int, data: dict) -> None:
    result = await generate_text_answer(data, user_id=user_id)
    cost = int((result["tokens_input"] * 0.003 + result["tokens_output"] * 0.015) * 100)
    try:
        await update_order_result(
            order_id, result["json_data"],
            result["tokens_input"], result["tokens_output"], cost,
        )
        order = await get_order_by_id(order_id)
        parts = format_text_answer(result["json_data"])
        kb = text_edit_kb(order_id, free_edit_available=not order["free_edit_used"])
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                await bot.send_message(user_id, part, reply_markup=kb, parse_mode="Markdown")
            else:
                await bot.send_message(user_id, part, parse_mode="Markdown")
        if order["is_trial"]:
            await _send_trial_cta(bot, user_id)
    except Exception as e:
        logger.error("Post-generate error text order #%s: %s", order_id, e)


async def _send_trial_cta(bot: Bot, user_id: int) -> None:
    await bot.send_message(
        user_id,
        "💡 <b>Понравилось качество?</b>\nПополните баланс и заказывайте сколько нужно.",
        reply_markup=trial_cta_kb(),
        parse_mode="HTML",
    )


async def _send_docx(
    bot: Bot, user_id: int, order_id: int, data: dict, is_combo: bool = False
) -> str:
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        tmp = f.name
    try:
        create_lab_docx(data, tmp)
        fname = f"lab_{order_id}.docx" if not is_combo else f"lab_combo_{order_id}.docx"
        doc = FSInputFile(tmp, filename=fname)
        sent = await bot.send_document(user_id, doc, caption=f"📄 Лабораторная работа — заказ #{order_id}")
        return sent.document.file_id
    finally:
        os.unlink(tmp)


async def _send_pptx(
    bot: Bot, user_id: int, order_id: int, data: dict, is_combo: bool = False
) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        tmp = f.name
    try:
        await create_presentation_pptx(data, tmp)
        fname = f"pres_{order_id}.pptx" if not is_combo else f"pres_combo_{order_id}.pptx"
        doc = FSInputFile(tmp, filename=fname)
        sent = await bot.send_document(user_id, doc, caption=f"📊 Презентация — заказ #{order_id}")
        return sent.document.file_id
    finally:
        os.unlink(tmp)


# ─── Edit flow ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("edit_menu:"))
async def edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    free_available = not order["free_edit_used"]
    otype = order["type"]
    if otype in ("lab_docx", "lab_plus_pres"):
        kb = lab_edit_kb(order_id, free_available)
    elif otype == "presentation_pptx":
        kb = pres_edit_kb(order_id, free_available)
    else:
        kb = text_edit_kb(order_id, free_available)

    await callback.message.answer(f"✏️ Выберите правку для заказа #{order_id}:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "e:done:{order_id}" if False else F.data.startswith("e:done:"))
async def edit_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Отлично! Рады помочь.", reply_markup=main_menu_kb())
    await callback.answer()


# Button edits that don't need extra input
@router.callback_query(F.data.startswith("e:meas:"))
async def edit_measurements(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[2])
    await state.update_data(edit_order_id=order_id, edit_action="meas")
    await callback.message.answer(
        "Введите новые данные измерений:",
        reply_markup=cancel_edit_kb(order_id),
    )
    await state.set_state(EditStates.entering_free_edit)
    await callback.answer()


@router.callback_query(F.data.startswith("e:conc:"))
async def edit_conclusion(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])
    instruction = "Полностью перепиши раздел «Вывод» — сделай его более подробным и обоснованным."
    await _run_edit(callback, order_id, instruction, edit_type="button", is_paid=False)


@router.callback_query(F.data.startswith("e:addsec:"))
async def edit_add_section(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[2])
    await state.update_data(edit_order_id=order_id, edit_action="addsec")
    await callback.message.answer(
        "Введите название и краткое содержание нового раздела:",
        reply_markup=cancel_edit_kb(order_id),
    )
    await state.set_state(EditStates.entering_section_content)
    await callback.answer()


@router.callback_query(F.data.startswith("e:scheme:"))
async def edit_scheme(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])
    await callback.message.answer(
        "Выберите цветовую схему:", reply_markup=color_scheme_kb(order_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("scheme:"))
async def scheme_chosen(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    scheme, order_id = parts[1], int(parts[2])
    instruction = f"Измени color_scheme на '{scheme}'. Остальное не трогай."
    await _run_edit(callback, order_id, instruction, edit_type="button", is_paid=False)


@router.callback_query(F.data.startswith("e:slide:"))
async def edit_slide(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[2])
    await state.update_data(edit_order_id=order_id, edit_action="slide")
    await callback.message.answer(
        "Введите номер слайда и что нужно изменить (например: «Слайд 3 — добавь примеры»):",
        reply_markup=cancel_edit_kb(order_id),
    )
    await state.set_state(EditStates.entering_slide_number)
    await callback.answer()


@router.callback_query(F.data.startswith("e:addsl:"))
async def edit_add_slide(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[2])
    await state.update_data(edit_order_id=order_id, edit_action="addsl")
    await callback.message.answer(
        "Опишите новый слайд (заголовок и содержание):",
        reply_markup=cancel_edit_kb(order_id),
    )
    await state.set_state(EditStates.entering_section_content)
    await callback.answer()


# FSM handlers for edit inputs
@router.message(StateFilter(EditStates.entering_slide_number), F.text)
async def edit_slide_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = data["edit_order_id"]
    instruction = f"Правка слайда: {message.text.strip()}"
    await state.clear()
    await _run_edit_from_message(message, order_id, instruction, "button", False)


@router.message(StateFilter(EditStates.entering_section_content), F.text)
async def edit_section_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = data["edit_order_id"]
    action = data.get("edit_action", "addsec")
    if action == "addsec":
        instruction = f"Добавь новый раздел: {message.text.strip()}"
    else:
        instruction = f"Добавь новый слайд: {message.text.strip()}"
    await state.clear()
    await _run_edit_from_message(message, order_id, instruction, "button", False)


# ─── Free text edit ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("e:free:"))
async def edit_free_start(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[2])
    await state.update_data(edit_order_id=order_id, edit_action="free")
    await callback.message.answer(
        "✍️ Напишите инструкцию по правке (что именно нужно изменить):",
        reply_markup=cancel_edit_kb(order_id),
    )
    await state.set_state(EditStates.entering_free_edit)
    await callback.answer()


@router.message(StateFilter(EditStates.entering_free_edit), F.text)
async def edit_free_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = data["edit_order_id"]
    instruction = message.text.strip()
    order = await get_order_by_id(order_id)

    if not order or order["user_id"] != message.from_user.id:
        await state.clear()
        return

    if not order["free_edit_used"]:
        # Free first edit
        await state.clear()
        await set_free_edit_used(order_id)
        await _run_edit_from_message(message, order_id, instruction, "free_text", False, 0)
    else:
        # Paid edit
        await state.update_data(
            pending_edit_instruction=instruction,
            payment_purpose="paid_edit",
        )
        await state.set_state(EditStates.confirming_paid_edit)
        await message.answer(
            f"Эта правка платная — {kopecks_to_rubles(config.price_extra_edit)}.",
            reply_markup=paid_edit_confirm_kb(order_id),
        )


@router.callback_query(F.data.startswith("pay_edit:"), StateFilter(EditStates.confirming_paid_edit))
async def pay_edit_invoice(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[1])
    price = config.price_extra_edit
    stars = max(1, price // config.kopecks_per_star)
    await state.update_data(edit_order_id=order_id)
    await callback.message.answer_invoice(
        title="Платная правка",
        description=f"Применить правку к заказу #{order_id}",
        payload=f"paid_edit:{callback.from_user.id}:{order_id}",
        currency="XTR",
        prices=[{"label": "Звёзды", "amount": stars}],
    )
    await callback.answer()


# ─── Edit runner helpers ───────────────────────────────────────────────────────

async def _run_edit(
    callback: CallbackQuery,
    order_id: int,
    instruction: str,
    edit_type: str,
    is_paid: bool,
    price_kopecks: int = 0,
) -> None:
    order = await get_order_by_id(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    await callback.message.answer("⏳ Применяю правку...")
    await callback.answer()
    await _apply_edit_and_send(
        callback.message.bot, callback.from_user.id,
        order, instruction, edit_type, is_paid, price_kopecks,
    )


async def _run_edit_from_message(
    message: Message,
    order_id: int,
    instruction: str,
    edit_type: str,
    is_paid: bool,
    price_kopecks: int = 0,
) -> None:
    order = await get_order_by_id(order_id)
    if not order or order["user_id"] != message.from_user.id:
        return
    await message.answer("⏳ Применяю правку...")
    await _apply_edit_and_send(
        message.bot, message.from_user.id,
        order, instruction, edit_type, is_paid, price_kopecks,
    )


async def _apply_edit_and_send(
    bot: Bot,
    user_id: int,
    order,
    instruction: str,
    edit_type: str,
    is_paid: bool,
    price_kopecks: int,
) -> None:
    order_id = order["id"]
    order_type = order["type"]

    raw_json = order["result_json"]
    if isinstance(raw_json, str):
        original_json = json.loads(raw_json)
    else:
        original_json = raw_json or {}

    # For combo orders, edit the lab part
    if order_type == "lab_plus_pres":
        original_json = original_json.get("lab", original_json)
        effective_type = "lab_docx"
    else:
        effective_type = order_type

    try:
        result = await apply_edit(original_json, instruction, effective_type)
        new_json = result["json_data"]

        if effective_type == "lab_docx":
            file_id = await _send_docx(bot, user_id, order_id, new_json)
        elif effective_type == "presentation_pptx":
            file_id = await _send_pptx(bot, user_id, order_id, new_json)
        else:
            parts = format_text_answer(new_json)
            for part in parts:
                await bot.send_message(user_id, part, parse_mode="Markdown")
            file_id = None

        cost = int((result["tokens_input"] * 0.003 + result["tokens_output"] * 0.015) * 100)
        await update_order_result(order_id, new_json, result["tokens_input"], result["tokens_output"], cost, file_id)

        await create_edit(
            order_id=order_id, user_id=user_id, edit_type=edit_type,
            edit_instruction=instruction, tokens_used=result["tokens_output"],
            is_paid=is_paid, price_kopecks=price_kopecks,
        )

        updated_order = await get_order_by_id(order_id)
        free_available = not updated_order["free_edit_used"]

        if effective_type == "lab_docx":
            kb = lab_edit_kb(order_id, free_available)
        elif effective_type == "presentation_pptx":
            kb = pres_edit_kb(order_id, free_available)
        else:
            kb = text_edit_kb(order_id, free_available)

        await bot.send_message(user_id, "✅ Правка применена! Продолжить?", reply_markup=kb)

    except Exception as e:
        logger.exception("Edit error order #%s: %s", order_id, e)
        await bot.send_message(user_id, f"❌ Ошибка при применении правки: {e}")


# ─── My orders ────────────────────────────────────────────────────────────────

@router.message(F.text == "📦 Мои заказы")
@router.callback_query(F.data == "my_orders")
async def my_orders(update: Message | CallbackQuery, state: FSMContext) -> None:
    is_cb = isinstance(update, CallbackQuery)
    user_id = update.from_user.id
    message = update.message if is_cb else update

    from bot.db.queries import get_user_orders_with_pagination
    orders = await get_user_orders_with_pagination(user_id, limit=5)

    if not orders:
        await message.answer(
            "📦 <b>У вас пока нет заказов.</b>\nСоздайте первый!",
            reply_markup=no_orders_kb(),
            parse_mode="HTML",
        )
    else:
        lines = ["📦 <b>Ваши последние заказы:</b>\n"]
        for i, o in enumerate(orders, 1):
            raw_input = o["input_data"]
            inp = json.loads(raw_input) if isinstance(raw_input, str) else (raw_input or {})
            subject = inp.get("subject") or inp.get("topic") or "—"
            date_str = o["created_at"].strftime("%d.%m.%Y") if o.get("created_at") else "—"
            lines.append(
                f"<b>{i}. {order_type_label(o['type'])} — {subject}</b>\n"
                f"   {order_status_label(o['status'])} · "
                f"{kopecks_to_rubles(o['price_kopecks'] or 0)} · {date_str}"
            )
        await message.answer(
            "\n".join(lines),
            reply_markup=orders_rich_kb(orders),
            parse_mode="HTML",
        )
    if is_cb:
        await update.answer()


@router.callback_query(F.data == "new_order_btn")
async def new_order_btn(callback: CallbackQuery, state: FSMContext) -> None:
    """Inline button shortcut — same checks as the reply keyboard "📝 Новый заказ"."""
    if not await _check_agreed(callback.from_user, callback.message):
        await callback.answer()
        return
    if not await _check_no_active_order(callback.from_user, callback.message):
        await callback.answer()
        return

    user_id = callback.from_user.id
    user = await get_user(user_id)
    is_vip = bool(user and user.get("is_vip"))

    if is_vip:
        usage = await get_vip_usage_today(user_id)
        daily_limit = (user.get("vip_daily_limit") or VIP_DAILY_LIMIT)
        if usage.get("requests_used", 0) >= daily_limit:
            await callback.message.answer(
                f"👑 VIP лимит исчерпан на сегодня "
                f"({usage['requests_used']}/{daily_limit}).\n"
                f"Лимит обновится через {_vip_reset_countdown()} (00:00 МСК)."
            )
            await callback.answer()
            return
    else:
        is_subscribed = await has_active_subscription(user_id)
        if not is_subscribed:
            recent = await count_user_orders_last_hour(user_id)
            if recent >= 3:
                await callback.message.answer(
                    "⏱ Лимит заказов: не более 3 в час.\n"
                    "Подождите немного или оформите подписку."
                )
                await callback.answer()
                return

    await state.clear()
    await state.update_data(is_vip_order=is_vip)
    trial_available = (not is_vip) and (not await get_trial_status(user_id))
    await callback.message.answer(
        "Выберите тип задания:",
        reply_markup=order_type_kb(trial_available=trial_available),
    )
    await state.set_state(OrderStates.choosing_type)
    await callback.answer()


@router.callback_query(F.data.startswith("dl:"))
async def download_order(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    file_id = order.get("result_file_id")
    if not file_id:
        await callback.answer("Файл недоступен.", show_alert=True)
        return

    await callback.answer()
    if "|" in file_id:
        lab_fid, pres_fid = file_id.split("|", 1)
        await callback.message.answer_document(
            lab_fid, caption=f"📄 Лабораторная — заказ #{order_id}"
        )
        await callback.message.answer_document(
            pres_fid, caption=f"📊 Презентация — заказ #{order_id}"
        )
    else:
        otype = order["type"]
        caption = {
            "lab_docx": f"📄 Лабораторная работа — заказ #{order_id}",
            "presentation_pptx": f"📊 Презентация — заказ #{order_id}",
            "lab_plus_pres": f"📄 Файл — заказ #{order_id}",
        }.get(otype, f"📎 Заказ #{order_id}")
        await callback.message.answer_document(file_id, caption=caption)


@router.callback_query(F.data.startswith("od:"))
async def order_detail(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    raw_input = order["input_data"]
    inp = json.loads(raw_input) if isinstance(raw_input, str) else (raw_input or {})

    text = (
        f"<b>Заказ #{order['id']}</b>\n"
        f"Тип: {order_type_label(order['type'])}\n"
        f"Статус: {order_status_label(order['status'])}\n"
        f"Тема: {inp.get('topic', '—')}\n"
        f"Стоимость: {kopecks_to_rubles(order['price_kopecks'])}\n"
        f"Правок: {order['edit_count']}\n"
        f"Создан: {format_datetime(order['created_at'])}\n"
    )
    await callback.message.answer(
        text,
        reply_markup=order_detail_kb(order_id, order["status"]),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Back navigation ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("back:"))
async def go_back(callback: CallbackQuery, state: FSMContext) -> None:
    step = callback.data.split(":", 1)[1]
    data = await state.get_data()

    try:
        await callback.message.delete()
    except Exception:
        pass

    if step == "type":
        trial_available = not await get_trial_status(callback.from_user.id)
        sent = await callback.message.answer(
            "Выберите тип задания:",
            reply_markup=order_type_kb(trial_available=trial_available),
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.choosing_type)

    elif step == "subject":
        prev = data.get("subject", "")
        hint = f"\n<i>Ранее: {prev}</i>" if prev else ""
        sent = await callback.message.answer(
            f"Введите <b>предмет</b> (например: Физика, Программирование):{hint}",
            reply_markup=subject_input_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.entering_subject)

    elif step == "topic":
        prev = data.get("topic", "")
        hint = f"\n<i>Ранее: {prev}</i>" if prev else ""
        sent = await callback.message.answer(
            f"Введите <b>тему / название работы</b>:{hint}",
            reply_markup=topic_input_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.entering_topic)

    elif step == "description":
        prev = data.get("description", "")
        plain_desc = prev not in ("[фото задания]", "[PDF задание]")
        hint = f"\n<i>Ранее: {prev[:60]}</i>" if prev and plain_desc else ""
        sent = await callback.message.answer(
            f"Отправьте <b>условие / задание</b>:{hint}\n\n"
            "• Текстом (до 3 000 символов)\n"
            "• Фотографиями задания (до 20 шт.)\n"
            "• PDF-файлом (до 10 МБ, до 10 стр.)",
            reply_markup=description_input_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.entering_description)

    elif step == "measurements":
        sent = await callback.message.answer(
            "📐 <b>Данные измерений / вычислений:</b>",
            reply_markup=measurements_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id, _awaiting_meas_text=False)
        await state.set_state(OrderStates.entering_measurements)

    elif step == "requirements":
        order_type = data.get("order_type", "")
        is_lab = order_type in LAB_TYPES
        sent = await callback.message.answer(
            "📋 <b>Дополнительные требования:</b>",
            reply_markup=requirements_kb(is_lab=is_lab),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id, _awaiting_req_text=False)
        await state.set_state(OrderStates.entering_requirements)

    elif step == "style":
        sent = await callback.message.answer(
            "🎨 <b>Выберите стиль презентации:</b>\n"
            "<i>(влияет на цветовую схему и оформление)</i>",
            reply_markup=style_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.entering_style)

    elif step == "custom_style":
        sent = await callback.message.answer(
            "✏️ <b>Опишите желаемый стиль:</b>\n\n"
            "Например:\n"
            "— красный и белый, строгий деловой стиль\n"
            "— фиолетовый градиент, современный\n\n"
            "Или просто напишите основной цвет:",
            reply_markup=custom_style_back_kb(),
            parse_mode="HTML",
        )
        await state.update_data(last_bot_message_id=sent.message_id)
        await state.set_state(OrderStates.entering_custom_style)

    await callback.answer()


# ─── Cancel ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отменено.", reply_markup=main_menu_kb())
    await callback.answer()
