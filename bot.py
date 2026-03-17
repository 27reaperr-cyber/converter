"""
bot.py — точка входа. Инициализирует БД, собирает роутеры, запускает поллинг.
"""

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

from config import BOT_TOKEN, ADMIN_IDS, TEMP_DIR, FONTS_DIR
from database import init_db, db_get_global

# ── Handlers ─────────────────────────────────────────────────────────────────
from handlers.start import router as start_router
from handlers.settings import router as settings_router
from handlers.watermark import router as watermark_router
from handlers.media_handler import router as media_router
from handlers.payment import router as payment_router
from handlers.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Команды ───────────────────────────────────────────────────────────────────

USER_COMMANDS = [
    BotCommand(command="start",    description="🚀 Запустить бота"),
    BotCommand(command="help",     description="ℹ️ Помощь"),
    BotCommand(command="settings", description="⚙️ Настройки"),
    BotCommand(command="profile",  description="👤 Мой профиль"),
    BotCommand(command="topup",    description="💳 Пополнить баланс"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="admin", description="🔑 Админ-панель"),
]


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                ADMIN_COMMANDS,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:
            pass


# ── Периодическая очистка temp/ ───────────────────────────────────────────────

async def cleanup_temp(interval_seconds: int = 3600) -> None:
    """Удаляет файлы из temp/, старше TEMP_TTL_HOURS часов."""
    ttl_hours = float(os.getenv("TEMP_TTL_HOURS", "2"))
    ttl_seconds = ttl_hours * 3600
    temp_path = Path(TEMP_DIR)

    while True:
        try:
            now = asyncio.get_event_loop().time()
            for f in temp_path.iterdir():
                if f.is_file():
                    age = now - f.stat().st_mtime
                    if age > ttl_seconds:
                        f.unlink(missing_ok=True)
                        logger.debug("Deleted temp file: %s", f.name)
        except Exception as e:
            logger.warning("Cleanup error: %s", e)
        await asyncio.sleep(interval_seconds)


# ── Динамическая цена ─────────────────────────────────────────────────────────

async def refresh_conversion_price(interval_seconds: int = 60) -> None:
    """
    Обновляет CONVERSION_PRICE из БД каждую минуту,
    чтобы изменение цены через админку вступало в силу без перезапуска.
    """
    import config
    while True:
        try:
            val = db_get_global("conversion_price")
            if val is not None:
                config.CONVERSION_PRICE = float(val)
        except Exception as e:
            logger.warning("Price refresh error: %s", e)
        await asyncio.sleep(interval_seconds)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    # Подготовка директорий
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)
    Path(FONTS_DIR).mkdir(parents=True, exist_ok=True)

    # Инициализация БД
    init_db()
    logger.info("Database initialized.")

    # Бот + диспетчер
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация роутеров (порядок важен: более специфичные — раньше)
    dp.include_router(admin_router)
    dp.include_router(payment_router)
    dp.include_router(settings_router)
    dp.include_router(watermark_router)
    dp.include_router(media_router)
    dp.include_router(start_router)

    # Команды
    await set_commands(bot)
    logger.info("Bot commands set.")

    # Фоновые задачи
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_temp())
    loop.create_task(refresh_conversion_price())

    # Сброс вебхука и старт поллинга
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting polling…")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
