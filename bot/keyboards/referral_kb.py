from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def referral_code_input_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ввести код", callback_data="ref:enter")
    builder.button(text="➡️ Пропустить", callback_data="ref:skip")
    builder.adjust(2)
    return builder.as_markup()


def referral_code_activate_kb(code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Активировать", callback_data=f"ref:activate:{code}")
    builder.button(text="➡️ Пропустить", callback_data="ref:skip")
    builder.adjust(2)
    return builder.as_markup()


def referral_share_kb(bot_username: str, code: str) -> InlineKeyboardMarkup:
    share_text = (
        f"🎓 Присоединяйся к боту для учёбы и получи 50 ₽ на баланс! "
        f"Мой код: {code} — t.me/{bot_username}?start={code}"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Поделиться ссылкой", switch_inline_query=share_text)
    builder.adjust(1)
    return builder.as_markup()
