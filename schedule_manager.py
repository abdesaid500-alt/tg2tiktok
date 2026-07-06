import json
import os
import asyncio
import logging
from datetime import datetime
from config import DATA_DIR

logger = logging.getLogger("schedule_manager")

SCHEDULES_DIR = os.path.join(DATA_DIR, "schedules")


def _ensure_dir():
    os.makedirs(SCHEDULES_DIR, exist_ok=True)


def _schedule_path(user_id):
    return os.path.join(SCHEDULES_DIR, f"{user_id}.json")


def save_schedule(user_id, parts, interval_minutes):
    _ensure_dir()
    data = {
        "user_id": user_id,
        "parts": parts,
        "interval_minutes": interval_minutes,
        "next_index": 0,
        "created_at": datetime.now().isoformat(),
    }
    with open(_schedule_path(user_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"تم حفظ جدولة للمستخدم {user_id}: {len(parts)} أجزاء")


def load_schedule(user_id):
    path = _schedule_path(user_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"فشل تحميل جدولة {user_id}: {e}")
        return None


def delete_schedule(user_id):
    path = _schedule_path(user_id)
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"تم حذف جدولة المستخدم {user_id}")


async def execute_schedule(user_id, parts, interval_minutes, api_key, project_id, social_account_id, bot, chat_id):
    from webhook import publish_video
    total = len(parts)
    for i, part in enumerate(parts):
        if i > 0:
            logger.info(f"انتظار {interval_minutes} دقائق قبل الجزء {i + 1}/{total}")
            await asyncio.sleep(interval_minutes * 60)
        result = publish_video(
            api_key, project_id, social_account_id,
            part["drive_url"], part["caption"]
        )
        if result["success"]:
            msg = f"✅ الجزء {i + 1}/{total} نُشر بنجاح على TikTok"
            if bot and chat_id:
                try:
                    await bot.send_message(chat_id=chat_id, text=msg)
                except Exception as e:
                    logger.warning(f"فشل إرسال تأكيد: {e}")
            logger.info(f"نشر الجزء {i + 1}/{total}: {result['post_id']}")
        else:
            msg = f"❌ فشل نشر الجزء {i + 1}/{total}: {result['error']}"
            if bot and chat_id:
                try:
                    await bot.send_message(chat_id=chat_id, text=msg)
                except Exception as e:
                    logger.warning(f"فشل إرسال خطأ: {e}")
            logger.error(msg)
    delete_schedule(user_id)
    if bot and chat_id:
        await bot.send_message(
            chat_id=chat_id,
            text=f"🎉 تم نشر جميع الأجزاء ({total}) على TikTok بنجاح!"
        )
    logger.info(f"انتهت جدولة المستخدم {user_id}: {total} أجزاء")
