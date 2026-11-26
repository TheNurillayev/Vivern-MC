import asyncio
import logging
import uvicorn
from backend.app.core.config import settings
from backend.app.bot.bot import bot, dp
from backend.app.main import app
from backend.app.worker import order_worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vivern-runner")

async def run_bot():
    logger.info("Starting Telegram Bot polling for @VivernMC_Bot...")
    while True:
        try:
            # Delete webhook if any to allow polling
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot, handle_signals=False)
        except Exception as e:
            logger.error(f"Telegram Bot polling error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

async def run_fastapi():
    config = uvicorn.Config(
        app=app,
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    logger.info(f"Starting FastAPI server on {settings.SERVER_HOST}:{settings.SERVER_PORT}...")
    await server.serve()

async def main():
    while True:
        try:
            await asyncio.gather(
                run_fastapi(),
                run_bot(),
                order_worker_loop()
            )
        except Exception as e:
            logger.error(f"Main loop error: {e}. Restarting tasks in 5s...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
