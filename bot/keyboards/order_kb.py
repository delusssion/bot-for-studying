from datetime import datetime, timedelta


from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import config
from bot.utils.helpers import kopecks_to_rubles


def order_type_kb(trial_available: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if trial_available:
        builder.button(text="🎁 Попробовать бесплатно", callback_data="ot:trial")
    builder.button(
        text=f"🔬 Лабораторная работа (.docx) — {kopecks_to_rubles(config.price_lab_docx)}",
        callback_data="ot:lab_docx",
    )
    builder.button(
        text=f"📊 Презентация (.pptx) — {kopecks_to_rubles(config.price_presentation)}",
        callback_data="ot:presentation_pptx",
    )
    builder.button(
        text=f"✍️ Контрольная / текст — {kopecks_to_rubles(config.price_text_answer)}",
        callback_data="ot:text_answer",
    )
    builder.button(
        text=f"📦 Лаба + презентация — {kopecks_to_rubles(config.price_lab_plus_pres)}",
        callback_data="ot:lab_plus_pres",
    )
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def trial_offer_kb() -> InlineKeyboardMarkup:
    """Shown after referral step for first-time users."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔬 Лабораторная работа .docx", callback_data="trial:lab_docx")
    builder.button(text="✍️ Контрольная / текст", callback_data="trial:text_answer")
    builder.button(text="➡️ Пропустить — воспользуюсь позже", callback_data="trial:skip")
    builder.adjust(1)
    return builder.as_markup()


def trial_type_kb() -> InlineKeyboardMarkup:
    """Shown when user taps 'Попробовать бесплатно' from the order type menu."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔬 Лабораторная работа .docx", callback_data="trial:lab_docx")
    builder.button(text="✍️ Контрольная / текст", callback_data="trial:text_answer")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def trial_confirm_kb(has_style_step: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать", callback_data="confirm_trial_order")
    back_label = "стиль" if has_style_step else "требования"
    back_step = "style" if has_style_step else "requirements"
    builder.button(text=f"⬅️ Назад ({back_label})", callback_data=f"back:{back_step}")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def style_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔵 Классический синий", callback_data="style:blue")
    builder.button(text="🟢 Академический зелёный", callback_data="style:green")
    builder.button(text="⚫ Тёмная тема", callback_data="style:dark")
    builder.button(text="⚪ Минималистичный", callback_data="style:minimal")
    builder.button(text="✏️ Свой вариант", callback_data="style:custom")
    builder.button(text="⬅️ Назад (требования)", callback_data="back:requirements")
    builder.adjust(1)
    return builder.as_markup()


def custom_style_back_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад (стиль)", callback_data="back:style")
    builder.adjust(1)
    return builder.as_markup()


def trial_cta_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Пополнить баланс", callback_data="open_balance")
    builder.adjust(1)
    return builder.as_markup()


def subject_input_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад (тип заказа)", callback_data="back:type")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def topic_input_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад (предмет)", callback_data="back:subject")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def description_input_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад (тема)", callback_data="back:topic")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def measurements_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Есть данные — введу", callback_data="meas:enter")
    builder.button(text="🔢 Нет — использовать типовые", callback_data="meas:typical")
    builder.button(text="⬅️ Назад (условие)", callback_data="back:description")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def requirements_kb(is_lab: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Есть требования — введу", callback_data="req:enter")
    builder.button(text="✅ Нет — стандартно", callback_data="req:standard")
    if is_lab:
        builder.button(text="⬅️ Назад (данные измерений)", callback_data="back:measurements")
    else:
        builder.button(text="⬅️ Назад (условие)", callback_data="back:description")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def confirm_order_kb(price: int, has_style_step: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"✅ Создать заказ — {kopecks_to_rubles(price)}",
        callback_data="confirm_order",
    )
    back_label = "стиль" if has_style_step else "требования"
    back_step = "style" if has_style_step else "requirements"
    builder.button(text=f"⬅️ Назад ({back_label})", callback_data=f"back:{back_step}")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def no_balance_kb(shortage_kopecks: int) -> InlineKeyboardMarkup:
    """Shown when user has insufficient balance at confirmation step."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"💳 Пополнить +{kopecks_to_rubles(shortage_kopecks)} через Stars",
        callback_data=f"topup_order:{shortage_kopecks}",
    )
    builder.button(text="🔄 Я пополнил — попробовать снова", callback_data="retry_confirm")
    builder.button(text="❌ Отменить заказ", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def topup_kb(amount_kopecks: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"💳 Пополнить на {kopecks_to_rubles(amount_kopecks)} через Stars",
        callback_data=f"topup:{amount_kopecks}",
    )
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def vip_confirm_kb(has_style_step: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Создать (VIP — бесплатно)", callback_data="confirm_order")
    back_label = "стиль" if has_style_step else "требования"
    back_step = "style" if has_style_step else "requirements"
    builder.button(text=f"⬅️ Назад ({back_label})", callback_data=f"back:{back_step}")
    builder.button(text="❌ Отмена", callback_data="cancel_order")
    builder.adjust(1)
    return builder.as_markup()


def more_photos_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, это все страницы", callback_data="photos:done")
    builder.button(text="➕ Загрузить ещё", callback_data="photos:more")
    builder.adjust(1)
    return builder.as_markup()


def orders_list_kb(orders: list) -> InlineKeyboardMarkup:
    from bot.utils.helpers import order_type_label, order_status_label
    builder = InlineKeyboardBuilder()
    for o in orders:
        label = f"#{o['id']} {order_type_label(o['type'])} — {order_status_label(o['status'])}"
        builder.button(text=label[:60], callback_data=f"od:{o['id']}")
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def order_detail_kb(order_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "done":
        builder.button(text="✏️ Правка", callback_data=f"edit_menu:{order_id}")
    builder.button(text="◀️ Назад к списку", callback_data="my_orders")
    builder.adjust(1)
    return builder.as_markup()


def orders_rich_kb(orders: list) -> InlineKeyboardMarkup:
    """Per-order Download + Edit buttons, one row per order."""
    cutoff = datetime.now() - timedelta(days=config.order_edit_days_limit)
    builder = InlineKeyboardBuilder()
    for o in orders:
        order_id = o["id"]
        status = o["status"]
        has_file = bool(o.get("result_file_id"))
        edit_ok = (
            status == "done"
            and o.get("updated_at") is not None
            and o["updated_at"] > cutoff
        )
        row: list[InlineKeyboardButton] = []
        if has_file and status == "done":
            row.append(
                InlineKeyboardButton(text="📥 Скачать", callback_data=f"dl:{order_id}")
            )
        if edit_ok:
            row.append(
                InlineKeyboardButton(text="✏️ Правка", callback_data=f"edit_menu:{order_id}")
            )
        if row:
            builder.row(*row)
    builder.row(
        InlineKeyboardButton(text="📝 Новый заказ", callback_data="new_order_btn")
    )
    return builder.as_markup()


def no_orders_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Новый заказ", callback_data="new_order_btn")
    builder.adjust(1)
    return builder.as_markup()
