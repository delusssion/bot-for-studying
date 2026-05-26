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


def ozon_payment_kb(code: str, amount_kopecks: int, sbp_link: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"📋 Скопировать код {code}", callback_data=f"ozon_copy:{code}")
    if sbp_link:
        builder.button(text="📲 Оплатить через СБП", url=sbp_link)
    builder.button(
        text="✅ Я перевёл, жду начисления",
        callback_data=f"ozon_paid:{code}:{amount_kopecks}",
    )
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
