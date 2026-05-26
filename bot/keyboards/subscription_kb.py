from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def subscribe_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ Оплатить 999 ₽", callback_data="sub:buy")
    builder.adjust(1)
    return builder.as_markup()


def renew_sub_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Продлить на 30 дней", callback_data="sub:buy")
    builder.adjust(1)
    return builder.as_markup()


def sub_no_balance_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Пополнить баланс", callback_data="open_balance")
    builder.adjust(1)
    return builder.as_markup()
