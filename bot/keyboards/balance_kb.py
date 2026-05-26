from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

PRESET_AMOUNTS = [
    (10000, "100 ₽"),
    (20000, "200 ₽"),
    (30000, "300 ₽"),
    (50000, "500 ₽"),
    (100000, "1000 ₽"),
]


def balance_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Карта", callback_data="topup_method:card")
    builder.button(text="⭐ Telegram Stars", callback_data="topup_method:stars")
    builder.adjust(1)
    return builder.as_markup()


def card_payment_kb(amount_kopecks: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Я перевёл", callback_data=f"card_paid:{amount_kopecks}")
    builder.button(text="❌ Отмена", callback_data="card_cancel")
    builder.adjust(1)
    return builder.as_markup()


def topup_amounts_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for kopecks, label in PRESET_AMOUNTS:
        builder.button(text=label, callback_data=f"topup_amount:{kopecks}")
    builder.button(text="✏️ Другая", callback_data="topup_custom")
    builder.adjust(3)
    return builder.as_markup()


def go_to_balance_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Пополнить баланс", callback_data="open_balance")
    builder.adjust(1)
    return builder.as_markup()
