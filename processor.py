import os
import shutil
import logging
import asyncio
from datetime import datetime
from config import TEMP_DIR, PLANS
from database import get_user, get_plan_info, increment_daily, can_process, is_active
from downloader import get_video_info, download_video
from splitter import split_video
from uploader import upload_to_drive
from schedule_manager import save_schedule, execute_schedule

logger = logging.getLogger("processor")


async def process_video(user_id, url, bot, message_id):
    user = get_user(user_id)
    if not user:
        await _update_message(bot, user_id, message_id, "❌ المستخدم غير موجود")
        return
    if not is_active(user_id):
        await _update_message(bot, user_id, message_id, "⚠️ اشتراكك منتهٍ")
        return
    if not can_process(user_id):
        plan_info = get_plan_info(user_id)
        limit = plan_info.get("daily_limit", 10)
        await _update_message(bot, user_id, message_id, f"⚠️ وصلت للحد اليومي ({limit})")
        return
    lang = user.get("language", "ar")
    status_msg = await _update_message(bot, user_id, message_id, "⬇️ جاري التحميل من يوتيوب...")
    info = get_video_info(url)
    if not info:
        await _update_message(bot, user_id, status_msg, "❌ فشل الحصول على معلومات الفيديو")
        return
    video_title = info.get("title", "video")
    duration = info.get("duration", 0)
    logger.info(f"فيديو: {video_title} ({duration} ث)")
    file_key = f"vid_{user_id}_{int(datetime.now().timestamp())}"
    file_path = download_video(url, file_key)
    if not file_path:
        await _update_message(bot, user_id, status_msg, "❌ فشل تحميل الفيديو")
        return
    await _update_message(bot, user_id, status_msg, "✂️ جاري تقطيع الفيديو...")
    speed = user.get("speed", 1.1)
    split_minutes = user.get("split_minutes", 10)
    segment_seconds = split_minutes * 60
    parts = split_video(file_path, file_key, speed, segment_seconds, video_title, user_id)
    if not parts or len(parts) == 0:
        await _update_message(bot, user_id, status_msg, "❌ فشل تقطيع الفيديو")
        _cleanup(file_path, file_key)
        return
    total = len(parts)
    uploaded_parts = []
    for i, part in enumerate(parts):
        await _update_message(bot, user_id, status_msg, f"☁️ جاري رفع الجزء {i+1}/{total} على Drive...")
        result = upload_to_drive(part["path"])
        if not result or not result.get("id"):
            await _update_message(bot, user_id, status_msg, f"❌ فشل رفع الجزء {i+1}/{total}")
            _cleanup(file_path, file_key)
            return
        uploaded_parts.append({
            "drive_url": result["url"],
            "drive_id": result["id"],
            "caption": part["caption"],
            "part": part["part"],
        })
    await _update_message(bot, user_id, status_msg, "📤 جاري جدولة النشر على TikTok...")
    schedule_minutes = user.get("schedule_minutes", 15)
    api_key = user.get("woopsocial_api_key", "")
    project_id = user.get("woopsocial_project_id", "")
    social_account_id = user.get("woopsocial_social_account_id", "")
    save_schedule(user_id, uploaded_parts, schedule_minutes)
    _cleanup(file_path, file_key)
    increment_daily(user_id)
    await _update_message(bot, user_id, status_msg, f"✅ تم رفع {total} أجزاء على Drive. سيتم النشر على TikTok بفاصل {schedule_minutes} دقيقة بين كل جزء.")
    asyncio.create_task(
        execute_schedule(
            user_id, uploaded_parts, schedule_minutes,
            api_key, project_id, social_account_id,
            bot, user_id
        )
    )


async def _update_message(bot, user_id, message_id, text):
    if not bot or not message_id:
        return message_id
    try:
        msg = await bot.send_message(chat_id=user_id, text=text)
        return msg.message_id
    except Exception as e:
        logger.warning(f"فشل إرسال التحديث: {e}")
        return message_id


def _cleanup(file_path, file_key):
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        seg_dir = os.path.join(TEMP_DIR, f"{file_key}_parts")
        if os.path.exists(seg_dir):
            shutil.rmtree(seg_dir)
    except Exception as e:
        logger.warning(f"فشل التنظيف: {e}")
