import json
import random
import string
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg

from bot.db.connection import get_pool

# ─── Settings cache ───────────────────────────────────────────────────────────

_settings_cache: Dict[str, str] = {}
_settings_cache_ts: float = 0.0
_SETTINGS_TTL = 60.0


async def _load_settings_cache() -> None:
    global _settings_cache, _settings_cache_ts
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings")
        _settings_cache = {r["key"]: r["value"] for r in rows}
        _settings_cache_ts = time.monotonic()


async def get_setting(key: str, default: str = "") -> str:
    global _settings_cache_ts
    if time.monotonic() - _settings_cache_ts > _SETTINGS_TTL:
        await _load_settings_cache()
    return _settings_cache.get(key, default)


async def set_setting(key: str, value: str) -> None:
    global _settings_cache_ts
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
            """,
            key, value,
        )
    _settings_cache[key] = value


# ─── Users ────────────────────────────────────────────────────────────────────

async def get_or_create_user(
    user_id: int,
    username: Optional[str],
    full_name: str,
    referral_id: Optional[int] = None,
) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if row:
            await conn.execute(
                "UPDATE users SET username = $2, full_name = $3 WHERE user_id = $1",
                user_id, username, full_name,
            )
            return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return await conn.fetchrow(
            """
            INSERT INTO users (user_id, username, full_name, referral_id)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            user_id, username, full_name, referral_id,
        )


async def get_user(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)


async def set_user_agreed(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET agreed = TRUE WHERE user_id = $1", user_id
        )


async def get_user_balance(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
        return row["balance"] if row else 0


async def add_balance(user_id: int, amount_kopecks: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET balance = balance + $2 WHERE user_id = $1",
            user_id, amount_kopecks,
        )


async def deduct_balance(user_id: int, amount_kopecks: int) -> bool:
    """Returns False if balance insufficient."""
    if amount_kopecks == 0:
        return True
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE users SET balance = balance - $2
            WHERE user_id = $1 AND balance >= $2
            """,
            user_id, amount_kopecks,
        )
        return result == "UPDATE 1"


# ─── VIP ──────────────────────────────────────────────────────────────────────

async def add_vip(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_vip = TRUE WHERE user_id = $1", user_id
        )


async def remove_vip(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_vip = FALSE WHERE user_id = $1", user_id
        )


async def get_vip_usage_today(user_id: int) -> Dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT requests_used FROM vip_usage WHERE user_id = $1 AND date = CURRENT_DATE",
            user_id,
        )
        return {"requests_used": row["requests_used"] if row else 0}


async def increment_vip_usage(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO vip_usage (user_id, date, requests_used)
            VALUES ($1, CURRENT_DATE, 1)
            ON CONFLICT (user_id, date) DO UPDATE
            SET requests_used = vip_usage.requests_used + 1
            """,
            user_id,
        )


async def get_all_vip_users() -> List[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, username, full_name FROM users WHERE is_vip = TRUE ORDER BY user_id"
        )


async def get_vip_usage_stats_today() -> List[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT u.user_id, u.username, u.full_name, COALESCE(v.requests_used, 0) AS requests_used
            FROM users u
            JOIN vip_usage v ON v.user_id = u.user_id AND v.date = CURRENT_DATE
            WHERE u.is_vip = TRUE
            ORDER BY v.requests_used DESC
            """
        )


# ─── Orders ───────────────────────────────────────────────────────────────────

async def get_active_order_for_user(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM orders WHERE user_id = $1 AND status IN ('pending', 'processing')",
            user_id,
        )


async def create_order(
    user_id: int,
    order_type: str,
    input_data: Dict[str, Any],
    price_kopecks: int,
    is_trial: bool = False,
) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO orders (user_id, type, status, input_data, price_kopecks, is_trial)
            VALUES ($1, $2, 'pending', $3, $4, $5)
            RETURNING *
            """,
            user_id, order_type, json.dumps(input_data), price_kopecks, is_trial,
        )


async def update_order_status(order_id: int, status: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET status = $2, updated_at = NOW() WHERE id = $1",
            order_id, status,
        )


async def update_order_result(
    order_id: int,
    result_json: Dict[str, Any],
    tokens_input: int,
    tokens_output: int,
    cost_kopecks: int,
    result_file_id: Optional[str] = None,
    status: str = "done",
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE orders
            SET status = $2,
                result_json = $3,
                tokens_input = $4,
                tokens_output = $5,
                cost_kopecks = $6,
                result_file_id = $7,
                updated_at = NOW()
            WHERE id = $1
            """,
            order_id, status, json.dumps(result_json),
            tokens_input, tokens_output, cost_kopecks, result_file_id,
        )


async def set_free_edit_used(order_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET free_edit_used = TRUE, updated_at = NOW() WHERE id = $1",
            order_id,
        )


async def get_order_by_id(order_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)


async def get_user_orders(user_id: int, limit: int = 10) -> List[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM orders WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit,
        )


async def refund_order(order_id: int) -> Optional[asyncpg.Record]:
    """Refund order price to user balance. Returns order record or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        order = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
        if not order or order["status"] in ("refunded", "pending"):
            return None
        await conn.execute(
            "UPDATE orders SET status = 'refunded', updated_at = NOW() WHERE id = $1",
            order_id,
        )
        await conn.execute(
            "UPDATE users SET balance = balance + $2 WHERE user_id = $1",
            order["user_id"], order["price_kopecks"],
        )
        return order


# ─── Ozon card payments ───────────────────────────────────────────────────────

async def generate_payment_code() -> str:
    chars = string.ascii_uppercase + string.digits
    pool = await get_pool()
    async with pool.acquire() as conn:
        while True:
            suffix = "".join(random.choices(chars, k=4))
            code = f"UCH-{suffix}"
            exists = await conn.fetchval(
                "SELECT id FROM payments WHERE payment_code = $1", code
            )
            if not exists:
                return code


async def create_ozon_payment(
    user_id: int, amount_kopecks: int, code: str
) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            return await conn.fetchrow(
                """
                INSERT INTO payments (user_id, amount_kopecks, type, payment_code, expires_at, status)
                VALUES ($1, $2, 'ozon_card', $3, NOW() + INTERVAL '30 minutes', 'pending')
                RETURNING *
                """,
                user_id, amount_kopecks, code,
            )
        except asyncpg.UniqueViolationError:
            return None


async def get_payment_by_code(code: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM payments WHERE payment_code = $1", code
        )


async def confirm_ozon_payment(code: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        payment = await conn.fetchrow(
            "SELECT * FROM payments WHERE payment_code = $1 AND status = 'pending'", code
        )
        if not payment:
            return None
        async with conn.transaction():
            await conn.execute(
                "UPDATE payments SET status = 'success' WHERE id = $1", payment["id"]
            )
            await conn.execute(
                "UPDATE users SET balance = balance + $2 WHERE user_id = $1",
                payment["user_id"], payment["amount_kopecks"],
            )
        return payment


async def reject_ozon_payment(code: str, reason: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        payment = await conn.fetchrow(
            "SELECT * FROM payments WHERE payment_code = $1 AND status = 'pending'", code
        )
        if not payment:
            return None
        await conn.execute(
            "UPDATE payments SET status = 'rejected', reject_reason = $2 WHERE id = $1",
            payment["id"], reason,
        )
        return payment


async def get_expired_pending_payments() -> List[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM payments
            WHERE status = 'pending' AND type = 'ozon_card'
            AND expires_at IS NOT NULL AND expires_at < NOW()
            """
        )


async def get_all_pending_ozon_payments() -> List[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT p.*, u.username, u.full_name
            FROM payments p
            JOIN users u ON u.user_id = p.user_id
            WHERE p.status = 'pending' AND p.type = 'ozon_card'
            AND p.expires_at > NOW()
            ORDER BY p.created_at DESC
            """
        )


async def get_pending_ozon_payments_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            """
            SELECT COUNT(*) FROM payments
            WHERE status = 'pending' AND type = 'ozon_card' AND expires_at > NOW()
            """
        )
        return int(val or 0)


# ─── Payments ─────────────────────────────────────────────────────────────────

async def create_payment(
    user_id: int,
    amount_kopecks: int,
    payment_type: str,
    external_id: Optional[str] = None,
) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO payments (user_id, amount_kopecks, type, external_id, status)
            VALUES ($1, $2, $3, $4, 'pending')
            RETURNING *
            """,
            user_id, amount_kopecks, payment_type, external_id,
        )


async def update_payment_status(
    payment_id: int,
    status: str,
    external_id: Optional[str] = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if external_id:
            await conn.execute(
                "UPDATE payments SET status = $2, external_id = $3 WHERE id = $1",
                payment_id, status, external_id,
            )
        else:
            await conn.execute(
                "UPDATE payments SET status = $2 WHERE id = $1",
                payment_id, status,
            )


# ─── Edits ────────────────────────────────────────────────────────────────────

async def create_edit(
    order_id: int,
    user_id: int,
    edit_type: str,
    edit_instruction: str,
    tokens_used: int = 0,
    is_paid: bool = False,
    price_kopecks: int = 0,
) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        edit = await conn.fetchrow(
            """
            INSERT INTO edits
                (order_id, user_id, edit_type, edit_instruction, tokens_used, is_paid, price_kopecks)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            order_id, user_id, edit_type, edit_instruction, tokens_used, is_paid, price_kopecks,
        )
        await conn.execute(
            "UPDATE orders SET edit_count = edit_count + 1, updated_at = NOW() WHERE id = $1",
            order_id,
        )
        return edit


async def get_edit_count_for_order(order_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM edits WHERE order_id = $1", order_id
        )
        return row["cnt"] if row else 0


# ─── Admin ────────────────────────────────────────────────────────────────────

async def get_admin_stats() -> Dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        orders_today = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE created_at >= NOW() - INTERVAL '1 day'"
        )
        orders_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE created_at >= NOW() - INTERVAL '7 days'"
        )
        orders_total = await conn.fetchval("SELECT COUNT(*) FROM orders")
        revenue_today = await conn.fetchval(
            """SELECT COALESCE(SUM(amount_kopecks), 0) FROM payments
               WHERE status = 'success' AND created_at >= NOW() - INTERVAL '1 day'"""
        )
        revenue_7d = await conn.fetchval(
            """SELECT COALESCE(SUM(amount_kopecks), 0) FROM payments
               WHERE status = 'success' AND created_at >= NOW() - INTERVAL '7 days'"""
        )
        top_users = await conn.fetch(
            """
            SELECT u.user_id, u.username, u.full_name, COUNT(o.id) AS cnt
            FROM users u JOIN orders o ON o.user_id = u.user_id
            GROUP BY u.user_id, u.username, u.full_name
            ORDER BY cnt DESC
            LIMIT 5
            """
        )
        trials_today = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE is_trial = TRUE AND created_at >= NOW() - INTERVAL '1 day'"
        )
        trials_total = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE trial_used = TRUE"
        )
        conversion = await conn.fetchval(
            """
            SELECT
                COUNT(DISTINCT o.user_id) FILTER (
                    WHERE o.is_trial = FALSE AND o.status = 'done'
                ) * 100.0 / NULLIF(COUNT(DISTINCT u.user_id), 0)
            FROM users u
            LEFT JOIN orders o ON o.user_id = u.user_id
            WHERE u.trial_used = TRUE
            """
        )
        return {
            "total_users": total_users,
            "orders_today": orders_today,
            "orders_7d": orders_7d,
            "orders_total": orders_total,
            "revenue_today": revenue_today,
            "revenue_7d": revenue_7d,
            "top_users": list(top_users),
            "trials_today": trials_today or 0,
            "trials_total": trials_total or 0,
            "trial_conversion": float(conversion or 0),
        }


async def get_all_user_ids() -> List[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE agreed = TRUE")
        return [r["user_id"] for r in rows]


# ─── Rate limiting ────────────────────────────────────────────────────────────

async def count_user_orders_last_hour(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            """SELECT COUNT(*) FROM orders
               WHERE user_id = $1 AND created_at >= NOW() - INTERVAL '1 hour'""",
            user_id,
        )
        return int(val or 0)


async def has_active_subscription(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT subscription_until FROM users WHERE user_id = $1", user_id
        )
        if not row or not row["subscription_until"]:
            return False
        return row["subscription_until"] > datetime.now()


async def get_trial_status(user_id: int) -> bool:
    """Returns True if the user has already used their free trial."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT trial_used FROM users WHERE user_id = $1", user_id
        )
        return bool(val)


async def mark_trial_used(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET trial_used = TRUE WHERE user_id = $1", user_id
        )


async def purchase_subscription(user_id: int, price_kopecks: int) -> bool:
    """Deduct price from balance and extend subscription by 30 days. Returns False if insufficient."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            result = await conn.execute(
                "UPDATE users SET balance = balance - $2 WHERE user_id = $1 AND balance >= $2",
                user_id, price_kopecks,
            )
            if result != "UPDATE 1":
                return False
            await conn.execute(
                """UPDATE users
                   SET subscription_until =
                       GREATEST(COALESCE(subscription_until, NOW()), NOW()) + INTERVAL '30 days'
                   WHERE user_id = $1""",
                user_id,
            )
            return True


async def get_user_orders_with_pagination(
    user_id: int, limit: int = 5, offset: int = 0
) -> List[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM orders WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            user_id, limit, offset,
        )


# ─── Referral codes ───────────────────────────────────────────────────────────

async def create_referral_code(user_id: int) -> str:
    from bot.utils.helpers import generate_referral_code
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT code FROM referral_codes WHERE user_id = $1", user_id
        )
        if existing:
            return existing
        while True:
            code = generate_referral_code()
            collision = await conn.fetchval(
                "SELECT id FROM referral_codes WHERE code = $1", code
            )
            if not collision:
                break
        await conn.execute(
            "INSERT INTO referral_codes (user_id, code) VALUES ($1, $2)",
            user_id, code,
        )
        return code


async def get_referral_code(user_id: int) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        code = await conn.fetchval(
            "SELECT code FROM referral_codes WHERE user_id = $1", user_id
        )
    if code:
        return code
    return await create_referral_code(user_id)


async def get_referral_code_owner(code: str) -> Optional[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT user_id FROM referral_codes WHERE code = $1", code
        )


async def get_referral_stats(user_id: int) -> Dict[str, Any]:
    from bot.config import config as cfg
    pool = await get_pool()
    async with pool.acquire() as conn:
        invited_count = await conn.fetchval(
            "SELECT COUNT(*) FROM referral_uses WHERE inviter_id = $1", user_id
        )
        paid_count = await conn.fetchval(
            "SELECT COUNT(*) FROM referral_uses WHERE inviter_id = $1 AND bonus_inviter_paid = TRUE",
            user_id,
        )
        pending_count = await conn.fetchval(
            "SELECT COUNT(*) FROM referral_uses WHERE inviter_id = $1 AND bonus_inviter_paid = FALSE",
            user_id,
        )
    return {
        "invited_count": int(invited_count or 0),
        "earned_total": int(paid_count or 0) * cfg.referral_bonus_inviter,
        "pending_amount": int(pending_count or 0) * cfg.referral_bonus_inviter,
    }


async def use_referral_code(invitee_id: int, code: str) -> tuple:
    """Apply referral code. Returns (True, 'ok') or (False, reason_str)."""
    from bot.config import config as cfg
    pool = await get_pool()
    async with pool.acquire() as conn:
        already_used = await conn.fetchval(
            "SELECT id FROM referral_uses WHERE invitee_id = $1", invitee_id
        )
        if already_used:
            return False, "already_used"

        inviter_id = await conn.fetchval(
            "SELECT user_id FROM referral_codes WHERE code = $1", code
        )
        if not inviter_id:
            return False, "not_found"
        if inviter_id == invitee_id:
            return False, "own_code"

        async with conn.transaction():
            await conn.execute(
                """INSERT INTO referral_uses
                       (inviter_id, invitee_id, code, bonus_invitee_paid)
                   VALUES ($1, $2, $3, TRUE)""",
                inviter_id, invitee_id, code,
            )
            await conn.execute(
                "UPDATE users SET balance = balance + $2 WHERE user_id = $1",
                invitee_id, cfg.referral_bonus_invitee,
            )
        return True, "ok"


async def check_and_pay_referral_bonus(invitee_id: int, bot=None, is_trial: bool = False) -> None:
    """Pay the 75 ₽ bonus to the inviter after the invitee's first paid order."""
    if is_trial:
        return
    from bot.config import config as cfg
    pool = await get_pool()
    async with pool.acquire() as conn:
        paid_orders = await conn.fetchval(
            """SELECT COUNT(*) FROM orders
               WHERE user_id = $1
                 AND status NOT IN ('error', 'refunded', 'pending')
                 AND price_kopecks > 0""",
            invitee_id,
        )
        if int(paid_orders or 0) != 1:
            return

        row = await conn.fetchrow(
            "SELECT * FROM referral_uses WHERE invitee_id = $1 AND bonus_inviter_paid = FALSE",
            invitee_id,
        )
        if not row:
            return

        inviter_id = row["inviter_id"]
        async with conn.transaction():
            await conn.execute(
                "UPDATE referral_uses SET bonus_inviter_paid = TRUE WHERE id = $1",
                row["id"],
            )
            await conn.execute(
                "UPDATE users SET balance = balance + $2 WHERE user_id = $1",
                inviter_id, cfg.referral_bonus_inviter,
            )

    if bot:
        bonus_rubles = cfg.referral_bonus_inviter // 100
        try:
            await bot.send_message(
                inviter_id,
                f"🎉 Ваш друг сделал первый заказ!\n"
                f"+{bonus_rubles} ₽ зачислено на ваш баланс.",
            )
        except Exception:
            pass


# ─── Block / unblock ──────────────────────────────────────────────────────────

async def block_user(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked = TRUE WHERE user_id = $1", user_id)


async def unblock_user(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_blocked = FALSE WHERE user_id = $1", user_id)


# ─── Extended admin stats ─────────────────────────────────────────────────────

async def get_admin_stats_extended() -> Dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        new_today = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '1 day'"
        )
        new_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '7 days'"
        )
        subscribed = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE subscription_until > NOW()"
        )
        vip_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_vip = TRUE")

        orders_total = await conn.fetchval("SELECT COUNT(*) FROM orders")
        orders_today = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE created_at >= NOW() - INTERVAL '1 day'"
        )
        orders_7d = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE created_at >= NOW() - INTERVAL '7 days'"
        )
        trials_total = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE is_trial = TRUE"
        )
        conversion = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT o.user_id) FILTER (
                WHERE o.is_trial = FALSE AND o.status = 'done'
            ) * 100.0 / NULLIF(COUNT(DISTINCT u.user_id), 0)
            FROM users u
            LEFT JOIN orders o ON o.user_id = u.user_id
            WHERE u.trial_used = TRUE
            """
        )

        rev_today = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_kopecks),0) FROM payments WHERE status='success' AND created_at>=NOW()-INTERVAL '1 day'"
        )
        rev_7d = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_kopecks),0) FROM payments WHERE status='success' AND created_at>=NOW()-INTERVAL '7 days'"
        )
        rev_30d = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_kopecks),0) FROM payments WHERE status='success' AND created_at>=NOW()-INTERVAL '30 days'"
        )
        rev_total = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_kopecks),0) FROM payments WHERE status='success'"
        )

        ref_used = await conn.fetchval("SELECT COUNT(*) FROM referral_uses")
        ref_bonuses = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_kopecks),0) FROM payments WHERE type='referral_bonus'"
        )

    return {
        "total_users": total_users or 0,
        "new_today": new_today or 0,
        "new_7d": new_7d or 0,
        "subscribed": subscribed or 0,
        "vip_count": vip_count or 0,
        "orders_total": orders_total or 0,
        "orders_today": orders_today or 0,
        "orders_7d": orders_7d or 0,
        "trials_total": trials_total or 0,
        "trial_conversion": float(conversion or 0),
        "rev_today": rev_today or 0,
        "rev_7d": rev_7d or 0,
        "rev_30d": rev_30d or 0,
        "rev_total": rev_total or 0,
        "ref_used": ref_used or 0,
        "ref_bonuses": ref_bonuses or 0,
    }


async def get_finance_stats(period: str) -> Dict[str, Any]:
    """period: today | 7d | 30d | all"""
    interval_map = {"today": "1 day", "7d": "7 days", "30d": "30 days"}
    interval = interval_map.get(period)
    where = f"AND created_at >= NOW() - INTERVAL '{interval}'" if interval else ""

    pool = await get_pool()
    async with pool.acquire() as conn:
        revenue = await conn.fetchval(
            f"SELECT COALESCE(SUM(amount_kopecks),0) FROM payments WHERE status='success' {where}"
        )
        pay_count = await conn.fetchval(
            f"SELECT COUNT(*) FROM payments WHERE status='success' {where}"
        )
        refunds = await conn.fetchval(
            f"SELECT COUNT(*) FROM orders WHERE status='refunded' {where.replace('created_at','updated_at')}"
        )
        refund_amt = await conn.fetchval(
            f"SELECT COALESCE(SUM(price_kopecks),0) FROM orders WHERE status='refunded' {where.replace('created_at','updated_at')}"
        )

        type_stats = await conn.fetch(
            f"""
            SELECT type,
                   COUNT(*) AS cnt,
                   COALESCE(SUM(price_kopecks),0) AS total
            FROM orders
            WHERE status='done' AND is_trial=FALSE {where}
            GROUP BY type
            """
        )

    avg = (revenue // pay_count) if pay_count else 0
    return {
        "revenue": revenue or 0,
        "pay_count": pay_count or 0,
        "avg": avg,
        "refunds": refunds or 0,
        "refund_amt": refund_amt or 0,
        "net": (revenue or 0) - (refund_amt or 0),
        "by_type": {r["type"]: {"cnt": r["cnt"], "total": r["total"]} for r in type_stats},
    }


async def get_user_by_username(username: str) -> Optional[asyncpg.Record]:
    username = username.lstrip("@")
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE LOWER(username) = LOWER($1)", username
        )


async def get_user_full_stats(user_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if not user:
            return None
        orders_count = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE user_id = $1", user_id
        )
        spent = await conn.fetchval(
            "SELECT COALESCE(SUM(price_kopecks),0) FROM orders WHERE user_id=$1 AND status='done' AND is_trial=FALSE",
            user_id,
        )
        referrer = None
        if user["referral_id"]:
            referrer = await conn.fetchrow(
                "SELECT username, full_name FROM users WHERE user_id = $1", user["referral_id"]
            )
        return {
            "user": dict(user),
            "orders_count": orders_count or 0,
            "spent": spent or 0,
            "referrer": dict(referrer) if referrer else None,
        }
