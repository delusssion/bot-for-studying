import asyncio
import functools
import logging
from datetime import datetime

import pytz
from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import config
from bot.db.queries import (
    add_vip, block_user, confirm_card_payment, get_admin_stats_extended,
    get_all_pending_card_payments, get_all_vip_users, get_all_user_ids,
    get_finance_stats, get_order_by_id, get_pending_card_payments_count,
    get_setting, get_user, get_user_balance, get_user_by_username,
    get_user_full_stats, get_vip_usage_stats_today, refund_order,
    reject_card_payment, remove_vip, set_setting, unblock_user,
)
from bot.keyboards.admin_kb import (
    adm_cancel_kb, admin_menu_kb, broadcast_audience_kb,
    broadcast_confirm_kb, finance_period_kb, payment_confirm_kb,
    prices_kb, refund_confirm_kb, settings_menu_kb, stats_kb,
    user_card_kb, users_menu_kb, vip_menu_kb, vip_remove_confirm_kb,
)
from bot.keyboards.main_kb import get_support_button, main_menu_kb
from bot.utils.helpers import format_datetime, kopecks_to_rubles, order_type_label
from bot.utils.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()

_MSK = pytz.timezone("Europe/Moscow")

ORDER_TYPE_SHORT = {
    "lab_docx":          "Лабораторные",
    "presentation_pptx": "Презентации",
    "text_answer":       "Контрольные",
    "lab_plus_pres":     "Лаба+Презент.",
}


# ─── Access guard ─────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return int(user_id) in config.admin_ids


def admin_only(handler):
    @functools.wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if not _is_admin(message.from_user.id):
            await message.answer("⛔ Нет доступа.")
            return
        return await handler(message, *args, **kwargs)
    return wrapper


def admin_cb_only(handler):
    @functools.wraps(handler)
    async def wrapper(callback: CallbackQuery, *args, **kwargs):
        if not _is_admin(callback.from_user.id):
            await callback.answer("⛔ Нет доступа.", show_alert=True)
            return
        return await handler(callback, *args, **kwargs)
    return wrapper


# ─── /admin entry ─────────────────────────────────────────────────────────────

@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminStates.in_admin)
    await state.update_data(is_admin_mode=True)
    await message.answer(
        f"⚙️ <b>Админ панель</b>\n\nДобро пожаловать, {message.from_user.first_name}!",
        reply_markup=admin_menu_kb(),
        parse_mode="HTML",
    )


# ─── Exit admin ───────────────────────────────────────────────────────────────

@router.message(StateFilter(AdminStates), F.text == "🚪 Выйти из админки")
@admin_only
async def exit_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await get_user(message.from_user.id)
    is_vip = bool(user and user.get("is_vip"))
    await message.answer(
        "Вернулись в главное меню.",
        reply_markup=main_menu_kb(is_vip=is_vip),
    )


# ─── Cancel inline ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:cancel")
@admin_cb_only
async def adm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.in_admin)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Отменено.", reply_markup=admin_menu_kb())
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# STATISTICS
# ═══════════════════════════════════════════════════════════════════════════════

async def _send_stats(target) -> None:
    """target can be Message or CallbackQuery.message"""
    st = await get_admin_stats_extended()

    def r(k): return kopecks_to_rubles(st[k])

    text = (
        "📊 <b>Статистика</b>\n\n"
        "👥 <b>Пользователи:</b>\n"
        f"  Всего: {st['total_users']}\n"
        f"  Новых сегодня: {st['new_today']}\n"
        f"  Новых за 7 дней: {st['new_7d']}\n"
        f"  С подпиской: {st['subscribed']}\n"
        f"  VIP: {st['vip_count']}\n\n"
        "📦 <b>Заказы:</b>\n"
        f"  Всего: {st['orders_total']}\n"
        f"  Сегодня: {st['orders_today']}\n"
        f"  За 7 дней: {st['orders_7d']}\n"
        f"  Пробных всего: {st['trials_total']}\n"
        f"  Конверсия пробных в платные: {st['trial_conversion']:.1f}%\n\n"
        "💰 <b>Выручка:</b>\n"
        f"  Сегодня: {r('rev_today')}\n"
        f"  За 7 дней: {r('rev_7d')}\n"
        f"  За 30 дней: {r('rev_30d')}\n"
        f"  Всего: {r('rev_total')}\n\n"
        "🎁 <b>Рефералы:</b>\n"
        f"  Всего использовано кодов: {st['ref_used']}\n"
        f"  Выплачено бонусов: {r('ref_bonuses')}"
    )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=stats_kb(), parse_mode="HTML")
        await target.answer()
    else:
        await target.answer(text, reply_markup=stats_kb(), parse_mode="HTML")


@router.message(StateFilter(AdminStates), F.text == "📊 Статистика")
@admin_only
async def adm_stats(message: Message, state: FSMContext) -> None:
    await _send_stats(message)


@router.callback_query(F.data == "adm:stats_refresh")
@admin_cb_only
async def adm_stats_refresh(callback: CallbackQuery, state: FSMContext) -> None:
    await _send_stats(callback)


# ═══════════════════════════════════════════════════════════════════════════════
# VIP MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(StateFilter(AdminStates), F.text == "👑 VIP")
@admin_only
async def adm_vip_menu(message: Message, state: FSMContext) -> None:
    vips = await get_all_vip_users()
    await message.answer(
        f"👑 <b>Управление VIP</b>\n\nТекущих VIP пользователей: {len(vips)}",
        reply_markup=vip_menu_kb(),
        parse_mode="HTML",
    )


# ── Add VIP ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:vip_add")
@admin_cb_only
async def adm_vip_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.entering_vip_id)
    await callback.message.answer(
        "Введите Telegram ID пользователя:", reply_markup=adm_cancel_kb()
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.entering_vip_id), F.text)
@admin_only
async def adm_vip_add_id(message: Message, state: FSMContext) -> None:
    if not message.text.strip().lstrip("-").isdigit():
        await message.answer("❌ Введите числовой ID.", reply_markup=adm_cancel_kb())
        return
    uid = int(message.text.strip())
    user = await get_user(uid)
    if not user:
        await message.answer(f"❌ Пользователь с ID {uid} не найден в боте.")
        return
    if user.get("is_vip"):
        name = f"@{user['username']}" if user.get("username") else user.get("full_name", str(uid))
        await message.answer(f"⚠️ Пользователь {name} уже имеет VIP.")
        return
    await add_vip(uid)
    name = f"@{user['username']}" if user.get("username") else user.get("full_name", str(uid))
    await state.set_state(AdminStates.in_admin)
    await message.answer(
        f"✅ VIP выдан:\nID: {uid}\nUsername: {name}\nИмя: {user.get('full_name', '—')}",
        reply_markup=admin_menu_kb(),
    )
    try:
        await message.bot.send_message(
            uid,
            "👑 Вам выдан VIP доступ!\n"
            "3 бесплатных запроса в день.\n"
            "Нажмите /start чтобы увидеть изменения.",
        )
    except Exception:
        pass


# ── Remove VIP ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:vip_remove")
@admin_cb_only
async def adm_vip_remove_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.removing_vip_id)
    await callback.message.answer(
        "Введите Telegram ID пользователя:", reply_markup=adm_cancel_kb()
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.removing_vip_id), F.text)
@admin_only
async def adm_vip_remove_id(message: Message, state: FSMContext) -> None:
    if not message.text.strip().lstrip("-").isdigit():
        await message.answer("❌ Введите числовой ID.", reply_markup=adm_cancel_kb())
        return
    uid = int(message.text.strip())
    user = await get_user(uid)
    if not user:
        await message.answer(f"❌ Пользователь {uid} не найден.")
        return
    name = f"@{user['username']}" if user.get("username") else user.get("full_name", str(uid))
    await state.set_state(AdminStates.confirming_vip_remove)
    await state.update_data(vip_remove_uid=uid)
    await message.answer(
        f"Забрать VIP у пользователя?\nID: {uid}\nUsername: {name}",
        reply_markup=vip_remove_confirm_kb(uid),
    )


@router.callback_query(F.data.startswith("adm:vip_remove_confirm:"))
@admin_cb_only
async def adm_vip_remove_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    uid = int(callback.data.split(":")[-1])
    await remove_vip(uid)
    await state.set_state(AdminStates.in_admin)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ VIP снят с пользователя {uid}.", reply_markup=admin_menu_kb())
    await callback.answer()


# ── VIP List ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:vip_list")
@admin_cb_only
async def adm_vip_list(callback: CallbackQuery, state: FSMContext) -> None:
    users = await get_all_vip_users()
    if not users:
        await callback.message.answer("Нет VIP пользователей.")
        await callback.answer()
        return
    lines = [f"👑 <b>VIP пользователи ({len(users)}):</b>\n"]
    for i, u in enumerate(users, 1):
        name = f"@{u['username']}" if u.get("username") else u.get("full_name", "—")
        lines.append(f"{i}. {name} · {u['user_id']}")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


# ── VIP Usage Today ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:vip_usage")
@admin_cb_only
async def adm_vip_usage(callback: CallbackQuery, state: FSMContext) -> None:
    rows = await get_vip_usage_stats_today()
    date_str = datetime.now(_MSK).strftime("%d.%m.%Y")
    if not rows:
        await callback.message.answer(f"📊 VIP сегодня {date_str}:\nНет данных.")
        await callback.answer()
        return
    lines = [f"📊 <b>VIP сегодня {date_str}:</b>\n"]
    for r in rows:
        name = f"@{r['username']}" if r.get("username") else r.get("full_name", str(r["user_id"]))
        used = r["requests_used"]
        limit = 3
        marker = " ⛔️" if used >= limit else ""
        lines.append(f"{name} — {used}/{limit} запроса{marker}")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(StateFilter(AdminStates), F.text == "👤 Пользователи")
@admin_only
async def adm_users_menu(message: Message, state: FSMContext) -> None:
    await message.answer("👤 Пользователи:", reply_markup=users_menu_kb())


async def _send_user_card(target_message, user_stats: dict) -> None:
    u = user_stats["user"]
    uid = u["user_id"]
    name = f"@{u['username']}" if u.get("username") else "—"
    sub = format_datetime(u.get("subscription_until")) if u.get("subscription_until") else "нет"
    is_vip = bool(u.get("is_vip"))
    is_blocked = bool(u.get("is_blocked"))
    ref = user_stats.get("referrer")
    ref_str = f"@{ref['username']}" if ref and ref.get("username") else (ref.get("full_name") if ref else "нет")

    text = (
        f"👤 <b>Пользователь</b>\n\n"
        f"ID: <code>{uid}</code>\n"
        f"Username: {name}\n"
        f"Имя: {u.get('full_name', '—')}\n"
        f"Баланс: {kopecks_to_rubles(u.get('balance', 0))}\n"
        f"Подписка: {sub}\n"
        f"VIP: {'✅' if is_vip else '❌'}\n"
        f"Статус: {'🚫 заблокирован' if is_blocked else '✅ активен'}\n"
        f"Регистрация: {format_datetime(u.get('created_at'))}\n"
        f"Заказов всего: {user_stats['orders_count']}\n"
        f"Потрачено: {kopecks_to_rubles(user_stats['spent'])}\n"
        f"Реферал от: {ref_str}"
    )
    await target_message.answer(
        text,
        reply_markup=user_card_kb(uid, is_vip, is_blocked),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "adm:user_search")
@admin_cb_only
async def adm_user_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.searching_user)
    await callback.message.answer(
        "Введите Telegram ID или @username:", reply_markup=adm_cancel_kb()
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.searching_user), F.text)
@admin_only
async def adm_user_search(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    await state.set_state(AdminStates.in_admin)
    if query.startswith("@") or (not query.lstrip("-").isdigit()):
        user = await get_user_by_username(query.lstrip("@"))
    else:
        user = await get_user(int(query))

    if not user:
        await message.answer(f"❌ Пользователь не найден: {query}", reply_markup=admin_menu_kb())
        return
    stats = await get_user_full_stats(user["user_id"])
    await _send_user_card(message, stats)


# ── User card inline actions ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:card_vip_add:"))
@admin_cb_only
async def card_vip_add(callback: CallbackQuery, state: FSMContext) -> None:
    uid = int(callback.data.split(":")[-1])
    await add_vip(uid)
    await callback.answer("✅ VIP выдан", show_alert=True)
    stats = await get_user_full_stats(uid)
    u = stats["user"]
    await callback.message.edit_reply_markup(
        reply_markup=user_card_kb(uid, True, bool(u.get("is_blocked")))
    )
    try:
        await callback.message.bot.send_message(
            uid,
            "👑 Вам выдан VIP доступ!\n3 бесплатных запроса в день.\nНажмите /start.",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm:card_vip_remove:"))
@admin_cb_only
async def card_vip_remove(callback: CallbackQuery, state: FSMContext) -> None:
    uid = int(callback.data.split(":")[-1])
    await remove_vip(uid)
    await callback.answer("✅ VIP снят", show_alert=True)
    stats = await get_user_full_stats(uid)
    u = stats["user"]
    await callback.message.edit_reply_markup(
        reply_markup=user_card_kb(uid, False, bool(u.get("is_blocked")))
    )


@router.callback_query(F.data.startswith("adm:card_block:"))
@admin_cb_only
async def card_block(callback: CallbackQuery, state: FSMContext) -> None:
    uid = int(callback.data.split(":")[-1])
    await block_user(uid)
    await callback.answer("✅ Заблокирован", show_alert=True)
    stats = await get_user_full_stats(uid)
    u = stats["user"]
    await callback.message.edit_reply_markup(
        reply_markup=user_card_kb(uid, bool(u.get("is_vip")), True)
    )


@router.callback_query(F.data.startswith("adm:card_unblock:"))
@admin_cb_only
async def card_unblock(callback: CallbackQuery, state: FSMContext) -> None:
    uid = int(callback.data.split(":")[-1])
    await unblock_user(uid)
    await callback.answer("✅ Разблокирован", show_alert=True)
    stats = await get_user_full_stats(uid)
    u = stats["user"]
    await callback.message.edit_reply_markup(
        reply_markup=user_card_kb(uid, bool(u.get("is_vip")), False)
    )


@router.callback_query(F.data.startswith("adm:card_orders:"))
@admin_cb_only
async def card_orders(callback: CallbackQuery, state: FSMContext) -> None:
    uid = int(callback.data.split(":")[-1])
    from bot.db.queries import get_user_orders_with_pagination
    orders = await get_user_orders_with_pagination(uid, limit=5)
    if not orders:
        await callback.message.answer("Нет заказов.")
        await callback.answer()
        return
    lines = [f"📦 <b>Заказы пользователя {uid}:</b>\n"]
    for o in orders:
        lines.append(
            f"#{o['id']} {order_type_label(o['type'])} — "
            f"{kopecks_to_rubles(o['price_kopecks'] or 0)} · "
            f"{o['created_at'].strftime('%d.%m.%Y')}"
        )
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


# ── Block / Unblock via menu ──────────────────────────────────────────────────

@router.callback_query(F.data == "adm:user_block")
@admin_cb_only
async def adm_block_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.searching_user)
    await state.update_data(block_action="block")
    await callback.message.answer("Введите ID пользователя для блокировки:", reply_markup=adm_cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:user_unblock")
@admin_cb_only
async def adm_unblock_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.searching_user)
    await state.update_data(block_action="unblock")
    await callback.message.answer("Введите ID пользователя для разблокировки:", reply_markup=adm_cancel_kb())
    await callback.answer()


# ── Refund ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:refund")
@admin_cb_only
async def adm_refund_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.refunding)
    await callback.message.answer("Введите ID заказа для возврата:", reply_markup=adm_cancel_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("adm:card_refund:"))
@admin_cb_only
async def adm_card_refund_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.refunding)
    await callback.message.answer("Введите ID заказа для возврата:", reply_markup=adm_cancel_kb())
    await callback.answer()


@router.message(StateFilter(AdminStates.refunding), F.text)
@admin_only
async def adm_refund_id(message: Message, state: FSMContext) -> None:
    if not message.text.strip().isdigit():
        await message.answer("❌ Введите числовой ID заказа.", reply_markup=adm_cancel_kb())
        return
    order_id = int(message.text.strip())
    order = await get_order_by_id(order_id)
    if not order:
        await message.answer(f"❌ Заказ #{order_id} не найден.", reply_markup=adm_cancel_kb())
        return
    if order["status"] in ("refunded", "pending"):
        await message.answer(f"❌ Заказ #{order_id} уже возвращён или ещё не выполнен.")
        return

    user = await get_user(order["user_id"])
    uname = f"@{user['username']}" if user and user.get("username") else str(order["user_id"])
    await state.set_state(AdminStates.confirming_refund)
    await state.update_data(refund_order_id=order_id)
    await message.answer(
        f"Возврат по заказу #{order_id}\n"
        f"Тип: {order_type_label(order['type'])}\n"
        f"Сумма: {kopecks_to_rubles(order['price_kopecks'] or 0)}\n"
        f"Пользователь: {uname}\n\n"
        f"Вернуть {kopecks_to_rubles(order['price_kopecks'] or 0)} на баланс?",
        reply_markup=refund_confirm_kb(order_id),
    )


@router.callback_query(F.data.startswith("adm:refund_confirm:"))
@admin_cb_only
async def adm_refund_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[-1])
    order = await refund_order(order_id)
    await state.set_state(AdminStates.in_admin)
    await callback.message.edit_reply_markup(reply_markup=None)
    if not order:
        await callback.message.answer("❌ Не удалось выполнить возврат.", reply_markup=admin_menu_kb())
        await callback.answer()
        return
    await callback.message.answer(
        f"✅ Возврат выполнен. Пользователю {order['user_id']} зачислено "
        f"{kopecks_to_rubles(order['price_kopecks'] or 0)}.",
        reply_markup=admin_menu_kb(),
    )
    try:
        await callback.message.bot.send_message(
            order["user_id"],
            f"↩️ Возврат по заказу #{order_id}: "
            f"{kopecks_to_rubles(order['price_kopecks'] or 0)} зачислено на баланс.",
        )
    except Exception:
        pass
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# BROADCAST
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(StateFilter(AdminStates), F.text == "📢 Рассылка")
@admin_only
async def adm_broadcast_menu(message: Message, state: FSMContext) -> None:
    await message.answer("📢 Выберите аудиторию:", reply_markup=broadcast_audience_kb())


async def _get_audience(audience: str) -> tuple[list, str]:
    from bot.db.queries import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        if audience == "all":
            rows = await conn.fetch("SELECT user_id FROM users WHERE agreed=TRUE AND is_blocked=FALSE")
            label = "Все пользователи"
        elif audience == "vip":
            rows = await conn.fetch("SELECT user_id FROM users WHERE is_vip=TRUE AND is_blocked=FALSE")
            label = "VIP"
        else:
            rows = await conn.fetch(
                "SELECT user_id FROM users WHERE subscription_until > NOW() AND is_blocked=FALSE"
            )
            label = "Подписчики"
    return [r["user_id"] for r in rows], label


@router.callback_query(F.data.in_({"adm:bc_all", "adm:bc_vip", "adm:bc_sub"}))
@admin_cb_only
async def adm_bc_audience(callback: CallbackQuery, state: FSMContext) -> None:
    aud = callback.data.split("_", 1)[1]  # all | vip | sub
    ids, label = await _get_audience(aud)
    await state.set_state(AdminStates.broadcasting)
    await state.update_data(bc_audience=aud, bc_label=label, bc_ids=ids)
    await callback.message.answer(
        f"Введите текст рассылки.\n"
        f"Поддерживается Markdown.\n\n"
        f"Аудитория: <b>{label}</b> ({len(ids)} польз.)",
        reply_markup=adm_cancel_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.broadcasting), F.text)
@admin_only
async def adm_bc_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    ids = data.get("bc_ids", [])
    label = data.get("bc_label", "")
    await state.update_data(bc_text=message.text)
    await state.set_state(AdminStates.broadcast_preview)
    await message.answer(
        f"Предпросмотр рассылки:\n\n{message.text}\n\n"
        f"Отправить <b>{len(ids)}</b> пользователям ({label})?",
        reply_markup=broadcast_confirm_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "adm:bc_send", StateFilter(AdminStates.broadcast_preview))
@admin_cb_only
async def adm_bc_send(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ids: list = data.get("bc_ids", [])
    text: str = data.get("bc_text", "")
    await state.set_state(AdminStates.in_admin)

    status_msg = await callback.message.answer(
        f"📢 Рассылка запущена...\nОтправлено: 0 / {len(ids)}"
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()

    sent = failed = 0
    for i, uid in enumerate(ids, 1):
        try:
            await callback.message.bot.send_message(uid, text, parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
        if i % 10 == 0:
            try:
                await status_msg.edit_text(
                    f"📢 Рассылка...\nОтправлено: {sent} / {len(ids)}"
                )
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ Рассылка завершена\nОтправлено: {sent}\nОшибок: {failed}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FINANCE
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(StateFilter(AdminStates), F.text == "💰 Финансы")
@admin_only
async def adm_finance_menu(message: Message, state: FSMContext) -> None:
    pending_count = await get_pending_card_payments_count()
    await message.answer(
        "💰 <b>Финансы</b>\n\nВыберите период:",
        reply_markup=finance_period_kb(pending_count),
        parse_mode="HTML",
    )


PERIOD_LABELS = {"today": "сегодня", "7d": "7 дней", "30d": "30 дней", "all": "всё время"}


@router.callback_query(F.data.in_({"adm:fin_today", "adm:fin_7d", "adm:fin_30d", "adm:fin_all"}))
@admin_cb_only
async def adm_finance_period(callback: CallbackQuery, state: FSMContext) -> None:
    period = callback.data.split("_", 1)[1]  # today | 7d | 30d | all
    st = await get_finance_stats(period)
    label = PERIOD_LABELS.get(period, period)

    def r(v): return kopecks_to_rubles(v)

    type_lines = []
    for key, short in [
        ("lab_docx", "Лабораторные"),
        ("presentation_pptx", "Презентации"),
        ("text_answer", "Контрольные"),
        ("lab_plus_pres", "Лаба+Презент."),
    ]:
        if key in st["by_type"]:
            d = st["by_type"][key]
            type_lines.append(f"  {short}: {d['cnt']} шт · {r(d['total'])}")

    text = (
        f"💰 <b>Финансы за {label}</b>\n\n"
        f"Выручка: {r(st['revenue'])}\n"
        f"Количество платежей: {st['pay_count']}\n"
        f"Средний чек: {r(st['avg'])}\n\n"
        f"По типам заказов:\n"
        + ("\n".join(type_lines) if type_lines else "  Нет данных") +
        f"\n\nВозвраты: {st['refunds']} шт · {r(st['refund_amt'])}\n"
        f"Чистая выручка: {r(st['net'])}"
    )
    pending_count = await get_pending_card_payments_count()
    await callback.message.edit_text(text, reply_markup=finance_period_kb(pending_count), parse_mode="HTML")
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(StateFilter(AdminStates), F.text == "⚙️ Настройки")
@admin_only
async def adm_settings_menu(message: Message, state: FSMContext) -> None:
    maintenance = (await get_setting("maintenance_mode", "false")).lower() == "true"
    await message.answer(
        "⚙️ <b>Настройки бота</b>\n\nТекущие значения:",
        reply_markup=settings_menu_kb(maintenance),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "adm:toggle_maintenance")
@admin_cb_only
async def adm_toggle_maintenance(callback: CallbackQuery, state: FSMContext) -> None:
    current = (await get_setting("maintenance_mode", "false")).lower() == "true"
    new_val = "false" if current else "true"
    await set_setting("maintenance_mode", new_val)
    status = "включён" if new_val == "true" else "выключен"
    maintenance = new_val == "true"
    await callback.message.edit_reply_markup(reply_markup=settings_menu_kb(maintenance))
    await callback.answer(f"✅ Режим обслуживания {status}", show_alert=True)


@router.callback_query(F.data == "adm:vip_limit")
@admin_cb_only
async def adm_vip_limit_start(callback: CallbackQuery, state: FSMContext) -> None:
    current = await get_setting("vip_daily_limit", "3")
    await state.set_state(AdminStates.editing_price)
    await state.update_data(editing_key="vip_daily_limit", editing_label="VIP дневной лимит")
    await callback.message.answer(
        f"Текущий VIP дневной лимит: {current}\nВведите новое значение (число):",
        reply_markup=adm_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "adm:prices")
@admin_cb_only
async def adm_prices(callback: CallbackQuery, state: FSMContext) -> None:
    keys = [
        "price_lab_docx", "price_presentation", "price_lab_plus_pres",
        "price_text_answer", "price_subscription", "price_extra_edit",
    ]
    prices = {k: await get_setting(k, "0") for k in keys}
    await callback.message.answer(
        "💲 <b>Текущие цены:</b>",
        reply_markup=prices_kb(prices),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:price_edit:"))
@admin_cb_only
async def adm_price_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 2)[-1]
    label_map = {
        "price_lab_docx":      "Лабораторная .docx",
        "price_presentation":  "Презентация .pptx",
        "price_lab_plus_pres": "Лаба + презентация",
        "price_text_answer":   "Контрольная / текст",
        "price_subscription":  "Подписка 30 дней",
        "price_extra_edit":    "Доп. правка",
    }
    label = label_map.get(key, key)
    current = int(await get_setting(key, "0")) // 100
    await state.set_state(AdminStates.editing_price)
    await state.update_data(editing_key=key, editing_label=label)
    await callback.message.answer(
        f"Введите новую цену для «{label}» (в рублях).\nТекущая: {current} ₽",
        reply_markup=adm_cancel_kb(),
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.editing_price), F.text)
@admin_only
async def adm_price_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data.get("editing_key", "")
    label = data.get("editing_label", key)
    val = message.text.strip()
    if not val.isdigit():
        await message.answer("❌ Введите целое число.", reply_markup=adm_cancel_kb())
        return
    num = int(val)
    if key == "vip_daily_limit":
        await set_setting(key, str(num))
        await state.set_state(AdminStates.in_admin)
        await message.answer(
            f"✅ VIP дневной лимит обновлён: {num}",
            reply_markup=admin_menu_kb(),
        )
    else:
        kopecks = num * 100
        await set_setting(key, str(kopecks))
        await state.set_state(AdminStates.in_admin)
        await message.answer(
            f"✅ Цена «{label}» обновлена: {num} ₽",
            reply_markup=admin_menu_kb(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CARD PAYMENT CONFIRMATION
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm:pending_payments")
@admin_cb_only
async def adm_pending_payments(callback: CallbackQuery) -> None:
    payments = await get_all_pending_card_payments()
    if not payments:
        await callback.message.edit_text(
            "⏳ Нет ожидающих подтверждения платежей.",
            reply_markup=finance_period_kb(0),
        )
        await callback.answer()
        return
    await callback.answer()
    for p in payments:
        uname = f"@{p['username']}" if p.get("username") else p.get("full_name", str(p["user_id"]))
        rubles = p["amount_kopecks"] // 100
        paid_at = p["paid_at"]
        if paid_at:
            from datetime import timezone
            paid_msk = paid_at.replace(tzinfo=timezone.utc).astimezone(_MSK)
            time_str = paid_msk.strftime("%H:%M МСК %d.%m.%Y")
        else:
            time_str = "—"
        await callback.message.answer(
            f"💳 <b>Платёж #{p['id']}</b>\n"
            f"👤 {uname} (<code>{p['user_id']}</code>)\n"
            f"💰 {rubles} ₽\n"
            f"🕐 {time_str}",
            reply_markup=payment_confirm_kb(p["id"]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("confirm_payment:"))
@admin_cb_only
async def confirm_payment(callback: CallbackQuery) -> None:
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await confirm_card_payment(payment_id)
    if not payment:
        await callback.answer("❌ Платёж не найден или уже обработан", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    rubles = payment["amount_kopecks"] // 100
    user = await get_user(payment["user_id"])
    uname = f"@{user['username']}" if user and user.get("username") else str(payment["user_id"])

    try:
        await callback.message.edit_text(
            f"✅ Подтверждено\n{uname} — {rubles} ₽ зачислено",
            parse_mode="HTML",
        )
    except Exception:
        pass

    balance = await get_user_balance(payment["user_id"])
    try:
        await callback.bot.send_message(
            payment["user_id"],
            f"✅ <b>Баланс пополнен на {rubles} ₽!</b>\n"
            f"Текущий баланс: {kopecks_to_rubles(balance)}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("✅ Платёж подтверждён")


@router.callback_query(F.data.startswith("reject_payment:"))
@admin_cb_only
async def reject_payment(callback: CallbackQuery) -> None:
    payment_id = int(callback.data.split(":", 1)[1])
    payment = await reject_card_payment(payment_id)
    if not payment:
        await callback.answer("❌ Платёж не найден или уже обработан", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    rubles = payment["amount_kopecks"] // 100
    user = await get_user(payment["user_id"])
    uname = f"@{user['username']}" if user and user.get("username") else str(payment["user_id"])

    try:
        await callback.message.edit_text(
            f"❌ Отклонено — {uname} {rubles} ₽",
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        await callback.bot.send_message(
            payment["user_id"],
            "❌ <b>Пополнение не подтверждено.</b>\n"
            "Если вы уверены что перевод прошёл —\n"
            "напишите в поддержку.",
            reply_markup=get_support_button(),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await callback.answer("❌ Платёж отклонён")
