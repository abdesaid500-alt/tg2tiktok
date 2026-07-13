import logging
import os
import sys
import asyncio
import threading
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("start")
logger.info("PORT='%s', PID=%d", os.environ.get("PORT", ""), os.getpid())

from http.server import HTTPServer, BaseHTTPRequestHandler

state = {"step": "booting"}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(state).encode())
    def log_message(self, *a): pass

PORT = int(os.environ.get("PORT", 10000))
logger.info("Starting health server on %d", PORT)
t = threading.Thread(target=lambda: HTTPServer(("0.0.0.0", PORT), H).serve_forever(), daemon=True)
t.start()

# Install deps at runtime if not already installed (build-time pip may fail on Render)
state["step"] = "check_deps"
import subprocess
r = subprocess.run([sys.executable, "-c", "import telegram, httpx, google.auth, yt_dlp, PIL"], capture_output=True, text=True)
if r.returncode != 0:
    state["step"] = "pip_install"
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        logger.error("pip install failed (exit=%d): %s", r.returncode, r.stderr[-1000:])
        state["step"] = "pip_failed"
        sys.exit(1)
    logger.info("pip install done")
state["step"] = "deps_ok"

from core.config import Settings
from core import storage

try:
    settings = Settings.from_env()
    logger.info("Config OK: port=%d, data_dir=%s", settings.port, settings.data_dir)
except Exception as e:
    logger.error("Config failed: %s", e)
    sys.exit(1)

storage.init(settings.data_dir)
os.makedirs(settings.temp_dir, exist_ok=True)

from pipeline.worker import Worker
from bots.user import create_app as create_user_app
from bots.admin import create_app as create_admin_app
from telegram import InputFile

class _TgNotifier:
    def __init__(self):
        self.bot = None
    async def notify_user(self, user_id: int, message: str) -> None:
        if not self.bot: return
        try: await self.bot.send_message(chat_id=user_id, text=message)
        except Exception as e: logger.warning("notify fail: %s", e)
    async def notify_user_markup(self, user_id: int, message: str, markup=None) -> None:
        if not self.bot: return
        try: await self.bot.send_message(chat_id=user_id, text=message, reply_markup=markup)
        except Exception as e: logger.warning("notify markup fail: %s", e)
    async def send_video(self, user_id: int, video_path: str, caption: str = "") -> None:
        if not self.bot: return
        try:
            with open(video_path, "rb") as f:
                await self.bot.send_video(chat_id=user_id, video=InputFile(f, filename="part.mp4"), caption=caption)
        except Exception as e: logger.warning("send_video fail: %s", e)

async def _run_bot(app, stop: asyncio.Event, name: str):
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logger.info("%s running", name)
    await stop.wait()

logger.info("Initializing bots...")
notifier = _TgNotifier()
worker = Worker(settings=settings, notify=notifier)
user_app = create_user_app(settings.user_bot_token, worker)
admin_app = create_admin_app(settings.admin_bot_token, settings.admin_id)
notifier.bot = user_app.bot
logger.info("Bots ready")

async def runner():
    stop = asyncio.Event()
    try:
        await asyncio.gather(
            _run_bot(user_app, stop, "user bot"),
            _run_bot(admin_app, stop, "admin bot"),
            worker.run(),
        )
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutdown...")
        await worker.stop()
        await user_app.stop()
        await admin_app.stop()
        await user_app.shutdown()
        await admin_app.shutdown()
        await storage.close()

asyncio.run(runner())
