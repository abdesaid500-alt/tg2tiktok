import logging
import requests
from config import WOOPSOCIAL_BASE

logger = logging.getLogger("webhook")


def publish_video(api_key, project_id, social_account_id, video_url, caption):
    if not api_key or not project_id or not social_account_id:
        return {"success": False, "post_id": None, "error": "بيانات WoopSocial ناقصة"}
    url = f"{WOOPSOCIAL_BASE}/posts/schedule"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "project_id": project_id,
        "social_account_ids": [social_account_id],
        "content": caption,
        "media_urls": [video_url],
        "schedule_type": "immediate",
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=120)
        data = resp.json()
        if resp.status_code in (200, 201):
            post_id = data.get("data", {}).get("id") or data.get("id")
            logger.info(f"تم النشر بنجاح: {post_id}")
            return {"success": True, "post_id": post_id, "error": None}
        else:
            err = data.get("message", data.get("error", str(resp.text)))
            logger.error(f"فشل النشر على WoopSocial: {err}")
            return {"success": False, "post_id": None, "error": err}
    except requests.exceptions.Timeout:
        logger.error("انتهت مهلة طلب WoopSocial")
        return {"success": False, "post_id": None, "error": "انتهت المهلة"}
    except Exception as e:
        logger.error(f"خطأ في الاتصال بـ WoopSocial: {e}")
        return {"success": False, "post_id": None, "error": str(e)}
