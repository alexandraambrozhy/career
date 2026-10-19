"""Точка входа: запускает веб-панель и Telegram-бота в одном процессе."""
import asyncio
import logging

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot import build_dispatcher
from app.config import settings
from app.db import Store
from app.web import create_app

log = logging.getLogger("recruiter")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    store = Store(settings.db_path)

    bot = None
    bot_username = None
    if settings.telegram_token:
        bot = Bot(settings.telegram_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        bot_username = (await bot.get_me()).username
        log.info("Telegram bot: @%s", bot_username)
    else:
        log.warning("TELEGRAM_BOT_TOKEN не задан — запускается только веб-панель")
    if settings.demo_mode:
        log.warning("ANTHROPIC_API_KEY не задан — демо-режим скоринга")

    app = create_app(store, bot_username)
    server = uvicorn.Server(uvicorn.Config(app, host=settings.web_host, port=settings.web_port))
    tasks = [server.serve()]
    if bot:
        tasks.append(build_dispatcher(store).start_polling(bot))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
