import os
import sys
import re
import logging
import subprocess
import shutil
from config import TEMP_DIR, YOUTUBE_COOKIES_B64, TIMEOUT

logger = logging.getLogger("downloader")

COOKIES_FILE = "youtube_cookies.txt"


def setup_cookies():
    if YOUTUBE_COOKIES_B64 and len(YOUTUBE_COOKIES_B64) > 50:
        try:
            import base64
            decoded = base64.b64decode(YOUTUBE_COOKIES_B64).decode("utf-8", errors="replace")
            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                f.write(decoded)
            logger.info("تم حفظ ملف cookies من المتغير البيئي")
            return True
        except Exception as e:
            logger.warning(f"فشل حفظ cookies: {e}")
    logger.info("لا يوجد ملف cookies في المتغيرات")
    return False


def _get_ytdlp_cmd():
    ytdlp = shutil.which("yt-dlp")
    if ytdlp:
        return ytdlp
    scripts = os.path.join(os.path.dirname(sys.executable), "Scripts", "yt-dlp.exe")
    if os.path.exists(scripts):
        return scripts
    scripts = os.path.join(os.path.dirname(sys.executable), "Scripts", "yt-dlp")
    if os.path.exists(scripts):
        return scripts
    return "yt-dlp"


def get_video_info(url):
    cmd = [
        _get_ytdlp_cmd(),
        "--dump-json",
        "--no-warnings",
        "--extractor-args", "youtube:client=ios",
        url,
    ]
    if os.path.exists(COOKIES_FILE):
        cmd.extend(["--cookies", COOKIES_FILE])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            cmd[4] = "youtube:client=android"
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
        if result.returncode != 0:
            cmd[4] = "youtube:client=web"
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
        if result.returncode != 0:
            logger.error(f"فشل الحصول على معلومات الفيديو: {result.stderr}")
            return None
        import json
        info = json.loads(result.stdout)
        return {
            "title": info.get("title", "video"),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", "unknown"),
        }
    except subprocess.TimeoutExpired:
        logger.error("انتهت مهلة الحصول على معلومات الفيديو")
        return None
    except Exception as e:
        logger.error(f"خطأ في get_video_info: {e}")
        return None


def download_video(url, file_key):
    os.makedirs(TEMP_DIR, exist_ok=True)
    output_template = os.path.join(TEMP_DIR, f"{file_key}.%(ext)s")
    cmd = [
        _get_ytdlp_cmd(),
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-warnings",
        "--extractor-args", "youtube:client=ios",
        "-o", output_template,
        "--no-playlist",
        url,
    ]
    if os.path.exists(COOKIES_FILE):
        cmd.extend(["--cookies", COOKIES_FILE])
    logger.info(f"بدء تحميل: {url}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT
        )
        if result.returncode != 0:
            cmd[7] = "youtube:client=android"
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=TIMEOUT
            )
        if result.returncode != 0:
            cmd[7] = "youtube:client=web"
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=TIMEOUT
            )
        if result.returncode != 0:
            logger.error(f"فشل التحميل: {result.stderr}")
            return None
        for f in os.listdir(TEMP_DIR):
            if f.startswith(file_key) and f.endswith(".mp4"):
                return os.path.join(TEMP_DIR, f)
        logger.error("لم يتم العثور على الملف المحمّل")
        return None
    except subprocess.TimeoutExpired:
        logger.error("انتهت مهلة التحميل")
        return None
    except Exception as e:
        logger.error(f"خطأ في التحميل: {e}")
        return None
