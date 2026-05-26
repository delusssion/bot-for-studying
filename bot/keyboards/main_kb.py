from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import SUPPORT_USERNAME


def main_menu_kb(is_vip: bool = False) -> ReplyKeyboardMarkup:
    keyboard = []
    if is_vip:
        keyboard.append([KeyboardButton(text="👑 VIP статус")])
    keyboard.extend([
        [KeyboardButton(text="📝 Новый заказ"), KeyboardButton(text="📦 Мои заказы")],
        [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="⭐ Подписка")],
        [KeyboardButton(text="👥 Рефералы"), KeyboardButton(text="❓ Помощь")],
    ])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def accept_terms_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Принять и начать", callback_data="agree")
    return builder.as_markup()


def get_support_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📩 Написать в поддержку",
            url=f"https://t.me/{SUPPORT_USERNAME}",
        )
    ]])
