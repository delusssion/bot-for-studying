from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import config
from bot.utils.helpers import kopecks_to_rubles


def _free_edit_btn_text(free_available: bool) -> str:
    if free_available:
        return "💬 Свой комментарий (бесплатно)"
    return f"💬 Свой комментарий ({kopecks_to_rubles(config.price_extra_edit)})"


def lab_edit_kb(order_id: int, free_edit_available: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить данные измерений", callback_data=f"e:meas:{order_id}")
    builder.button(text="📝 Переписать вывод", callback_data=f"e:conc:{order_id}")
    builder.button(text="➕ Добавить раздел", callback_data=f"e:addsec:{order_id}")
    builder.button(text=_free_edit_btn_text(free_edit_available), callback_data=f"e:free:{order_id}")
    builder.button(text="✅ Всё отлично, спасибо", callback_data=f"e:done:{order_id}")
    builder.adjust(1)
    return builder.as_markup()


def pres_edit_kb(order_id: int, free_edit_available: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Изменить цветовую схему", callback_data=f"e:scheme:{order_id}")
    builder.button(text="📄 Переписать слайд", callback_data=f"e:slide:{order_id}")
    builder.button(text="➕ Добавить слайд", callback_data=f"e:addsl:{order_id}")
    builder.button(text=_free_edit_btn_text(free_edit_available), callback_data=f"e:free:{order_id}")
    builder.button(text="✅ Всё отлично, спасибо", callback_data=f"e:done:{order_id}")
    builder.adjust(1)
    return builder.as_markup()


def text_edit_kb(order_id: int, free_edit_available: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=_free_edit_btn_text(free_edit_available), callback_data=f"e:free:{order_id}")
    builder.button(text="✅ Всё отлично, спасибо", callback_data=f"e:done:{order_id}")
    builder.adjust(1)
    return builder.as_markup()


def color_scheme_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for scheme, label in [
        ("blue", "🔵 Blue"),
        ("green", "🟢 Green"),
        ("dark", "⚫ Dark"),
        ("minimal", "⬜ Minimal"),
    ]:
        builder.button(text=label, callback_data=f"scheme:{scheme}:{order_id}")
    builder.button(text="❌ Отмена", callback_data=f"edit_menu:{order_id}")
    builder.adjust(2)
    return builder.as_markup()


def cancel_edit_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена правки", callback_data=f"edit_menu:{order_id}")
    return builder.as_markup()


def paid_edit_confirm_kb(order_id: int) -> InlineKeyboardMarkup:
    price = config.price_extra_edit
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"💳 Оплатить правку ({kopecks_to_rubles(price)}) через Stars",
        callback_data=f"pay_edit:{order_id}",
    )
    builder.button(text="❌ Отмена", callback_data=f"edit_menu:{order_id}")
    builder.adjust(1)
    return builder.as_markup()
