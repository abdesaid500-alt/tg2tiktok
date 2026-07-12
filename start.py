import asyncio
import logging
import os
import sys

from telegram import InputFile

from core.config import Settings
from core import storage
from pipeline.worker import Worker
from bots.user import create_app as create_user_app
from bots.admin import create_app as create_admin_app

logger = logging.getLogger("start")


class _TgNotifier:
    def __init__(self):
        self.bot = None

    async def notify_user(self, user_id: int, message: str) -> None:
        if not self.bot:
            return
        try:
            await self.bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            logger.warning("Notify failed for %d: %s", user_id, e)

    async def notify_user_markup(self, user_id: int, message: str, markup=None) -> None:
        if not self.bot:
            return
        try:
            await self.bot.send_message(chat_id=user_id, text=message, reply_markup=markup)
        except Exception as e:
            logger.warning("Notify markup failed for %d: %s", user_id, e)

    async def send_video(self, user_id: int, video_path: str, caption: str = "") -> None:
        if not self.bot:
            return
        try:
            with open(video_path, "rb") as f:
                await self.bot.send_video(chat_id=user_id, video=InputFile(f, filename="part.mp4"), caption=caption)
        except Exception as e:
            logger.warning("Send video failed for %d: %s", user_id, e)


async def _health_server(port: int, stop: asyncio.Event):
    async def handle(reader, writer):
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: text/plain\r\n\r\nOK")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    async with server:
        logger.info("Health server on port %d", port)
        await stop.wait()


async def _run_bot(app, stop: asyncio.Event, name: str):
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("%s is running", name)
    await stop.wait()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        settings = Settings.from_env()
        logger.info("Settings loaded (data_dir=%s)", settings.data_dir)
    except KeyError as e:
        logger.error("Missing env var: %s", e)
        sys.exit(1)

    storage.init(
        settings.data_dir,
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_key,
    )
    os.makedirs(settings.temp_dir, exist_ok=True)

    notifier = _TgNotifier()
    worker = Worker(settings=settings, notify=notifier)
    user_app = create_user_app(settings.user_bot_token, worker)
    admin_app = create_admin_app(settings.admin_bot_token, settings.admin_id)
    notifier.bot = user_app.bot

    async def runner():
        stop = asyncio.Event()
        try:
            await asyncio.gather(
                _run_bot(user_app, stop, "user bot"),
                _run_bot(admin_app, stop, "admin bot"),
                worker.run(),
                _health_server(settings.port, stop),
            )
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("Shutting down...")
            await worker.stop()
            await user_app.stop()
            await admin_app.stop()
            await user_app.shutdown()
            await admin_app.shutdown()
            await storage.close()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
