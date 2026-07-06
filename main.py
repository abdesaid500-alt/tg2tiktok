import os
import sys
import base64
import asyncio
import logging
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

from config import (
    USER_BOT_TOKEN,
    ADMIN_BOT_TOKEN,
    GOOGLE_CREDENTIALS_B64,
    TOKEN_PICKLE_B64,
    YOUTUBE_COOKIES_B64,
    TEMP_DIR,
    DATA_DIR,
    PORT,
)


def _setup_dirs():
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "schedules"), exist_ok=True)


def _restore_files():
    if GOOGLE_CREDENTIALS_B64:
        try:
            decoded = base64.b64decode(GOOGLE_CREDENTIALS_B64)
            with open("credentials.json", "wb") as f:
                f.write(decoded)
            logger.info("تم استعادة credentials.json من المتغير البيئي")
        except Exception as e:
            logger.error(f"فشل استعادة credentials.json: {e}")
    if TOKEN_PICKLE_B64:
        try:
            decoded = base64.b64decode(TOKEN_PICKLE_B64)
            with open("token.pickle", "wb") as f:
                f.write(decoded)
            logger.info("تم استعادة token.pickle من المتغير البيئي")
        except Exception as e:
            logger.error(f"فشل استعادة token.pickle: {e}")
    if YOUTUBE_COOKIES_B64:
        try:
            decoded = base64.b64decode(YOUTUBE_COOKIES_B64)
            with open("youtube_cookies.txt", "wb") as f:
                f.write(decoded)
            logger.info("تم استعادة youtube_cookies.txt من المتغير البيئي")
        except Exception as e:
            logger.error(f"فشل استعادة cookies: {e}")


async def health_server():
    app = web.Application()

    async def health(request):
        return web.Response(text="OK", status=200)

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Health server يعمل على المنفذ {PORT}")


async def run_bot(app, name="bot"):
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
        )
        logger.info(f"✅ {name} يعمل بنجاح")
    except Exception as e:
        logger.error(f"❌ فشل تشغيل {name}: {e}")
        raise


async def main():
    logger.info("🚀 بدء تشغيل TG2TikTok Bot...")
    _setup_dirs()
    _restore_files()
    if not USER_BOT_TOKEN or USER_BOT_TOKEN == "YOUR_USER_BOT_TOKEN":
        logger.error("❌ USER_BOT_TOKEN غير مضبوط")
        return
    if not ADMIN_BOT_TOKEN or ADMIN_BOT_TOKEN == "YOUR_ADMIN_BOT_TOKEN":
        logger.error("❌ ADMIN_BOT_TOKEN غير مضبوط")
        return
    from user_bot import build_user_app
    from admin_bot import build_admin_app
    user_app = build_user_app()
    admin_app = build_admin_app()
    await health_server()
    from uploader import _get_service
    from drive_cleaner import start_cleaner
    asyncio.create_task(start_cleaner(_get_service))
    await asyncio.gather(
        run_bot(user_app, "User Bot"),
        run_bot(admin_app, "Admin Bot"),
    )
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("🛑 إيقاف التشغيل...")


if __name__ == "__main__":
    asyncio.run(main())
