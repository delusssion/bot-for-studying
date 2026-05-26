import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import config
from bot.db import close_pool, create_tables, get_pool
from bot.handlers import admin, orders, payments, start
from bot.handlers import balance, help, referral, subscription
from bot.middleware.block_check import BlockCheckMiddleware
from bot.middleware.error_handler import errors_router
from bot.utils.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Block check + maintenance middleware (runs before every handler)
    dp.message.middleware(BlockCheckMiddleware())
    dp.callback_query.middleware(BlockCheckMiddleware())

    # Error router must be included FIRST so it catches errors from all others
    dp.include_router(errors_router)
    dp.include_router(admin.router)      # admin before everything so /commands are not shadowed

    dp.include_router(start.router)
    dp.include_router(referral.router)   # referral after start (handles ReferralStates)
    dp.include_router(balance.router)
    dp.include_router(subscription.router)
    dp.include_router(help.router)
    dp.include_router(payments.router)
    dp.include_router(orders.router)

    # DB init
    pool = await get_pool()
    await create_tables(pool)
    logger.info("Database tables ensured.")

    try:
        logger.info("Bot polling started (drop_pending_updates=True).")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
    finally:
        logger.info("Shutting down — closing DB pool and bot session.")
        await close_pool()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
