from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👑 VIP")],
            [KeyboardButton(text="👤 Пользователи"), KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="💰 Финансы"), KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="🚪 Выйти из админки")],
        ],
        resize_keyboard=True,
    )


# ── Stats ─────────────────────────────────────────────────────────────────────

def stats_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Обновить", callback_data="adm:stats_refresh")
    b.adjust(1)
    return b.as_markup()


# ── VIP ───────────────────────────────────────────────────────────────────────

def vip_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Выдать VIP",            callback_data="adm:vip_add")
    b.button(text="➖ Забрать VIP",           callback_data="adm:vip_remove")
    b.button(text="📋 Список VIP",            callback_data="adm:vip_list")
    b.button(text="📊 Использование сегодня", callback_data="adm:vip_usage")
    b.adjust(1)
    return b.as_markup()


def adm_cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data="adm:cancel")
    b.adjust(1)
    return b.as_markup()


def vip_remove_confirm_kb(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Забрать", callback_data=f"adm:vip_remove_confirm:{user_id}")
    b.button(text="❌ Отмена",  callback_data="adm:cancel")
    b.adjust(2)
    return b.as_markup()


# ── Users ─────────────────────────────────────────────────────────────────────

def users_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔍 Найти пользователя", callback_data="adm:user_search")
    b.button(text="🚫 Заблокировать",      callback_data="adm:user_block")
    b.button(text="✅ Разблокировать",     callback_data="adm:user_unblock")
    b.button(text="💸 Возврат средств",    callback_data="adm:refund")
    b.adjust(1)
    return b.as_markup()


def user_card_kb(uid: int, is_vip: bool, is_blocked: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    vip_text = "👑 Забрать VIP" if is_vip else "👑 Выдать VIP"
    vip_cb   = f"adm:card_vip_remove:{uid}" if is_vip else f"adm:card_vip_add:{uid}"
    b.button(text=vip_text, callback_data=vip_cb)
    block_text = "✅ Разблокировать" if is_blocked else "🚫 Заблокировать"
    block_cb   = f"adm:card_unblock:{uid}" if is_blocked else f"adm:card_block:{uid}"
    b.button(text=block_text, callback_data=block_cb)
    b.button(text="💸 Сделать возврат",      callback_data=f"adm:card_refund:{uid}")
    b.button(text="📦 Заказы пользователя",  callback_data=f"adm:card_orders:{uid}")
    b.adjust(1)
    return b.as_markup()


def refund_confirm_kb(order_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Вернуть", callback_data=f"adm:refund_confirm:{order_id}")
    b.button(text="❌ Отмена",  callback_data="adm:cancel")
    b.adjust(2)
    return b.as_markup()


# ── Broadcast ─────────────────────────────────────────────────────────────────

def broadcast_audience_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📢 Всем пользователям", callback_data="adm:bc_all")
    b.button(text="👑 Только VIP",         callback_data="adm:bc_vip")
    b.button(text="⭐ Только подписчикам", callback_data="adm:bc_sub")
    b.adjust(1)
    return b.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Отправить", callback_data="adm:bc_send")
    b.button(text="❌ Отмена",    callback_data="adm:cancel")
    b.adjust(2)
    return b.as_markup()


# ── Finance ───────────────────────────────────────────────────────────────────

def finance_period_kb(pending_count: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📅 Сегодня",   callback_data="adm:fin_today")
    b.button(text="📅 7 дней",    callback_data="adm:fin_7d")
    b.button(text="📅 30 дней",   callback_data="adm:fin_30d")
    b.button(text="📅 Всё время", callback_data="adm:fin_all")
    pending_label = f"⏳ Ожидают подтверждения ({pending_count})" if pending_count else "⏳ Ожидают подтверждения"
    b.button(text=pending_label, callback_data="adm:pending_payments")
    b.adjust(2, 2, 1)
    return b.as_markup()


# ── Ozon Payment ──────────────────────────────────────────────────────────────

def payment_confirm_kb(payment_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=f"confirm_payment:{payment_id}")
    b.button(text="❌ Отклонить",   callback_data=f"reject_payment:{payment_id}")
    b.adjust(2)
    return b.as_markup()


# ── Settings ──────────────────────────────────────────────────────────────────

def settings_menu_kb(maintenance: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💲 Изменить цены",   callback_data="adm:prices")
    b.button(text="🎁 VIP дневной лимит", callback_data="adm:vip_limit")
    m_text = "▶️ Выключить обслуживание" if maintenance else "⏸ Включить обслуживание"
    b.button(text=m_text, callback_data="adm:toggle_maintenance")
    b.adjust(1)
    return b.as_markup()


def prices_kb(prices: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    items = [
        ("price_lab_docx",      "Лабораторная .docx"),
        ("price_presentation",  "Презентация .pptx"),
        ("price_lab_plus_pres", "Лаба + презентация"),
        ("price_text_answer",   "Контрольная / текст"),
        ("price_subscription",  "Подписка 30 дней"),
        ("price_extra_edit",    "Доп. правка"),
    ]
    for key, label in items:
        val_rub = int(prices.get(key, "0")) // 100
        b.button(text=f"{label} — {val_rub} ₽  ✏️", callback_data=f"adm:price_edit:{key}")
    b.adjust(1)
    return b.as_markup()
