import asyncio
import logging
from datetime import datetime, timezone
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from config import DRIVE_FOLDER_ID, DRIVE_DELETE_AFTER_MINUTES

logger = logging.getLogger("drive_cleaner")


async def start_cleaner(service_getter):
    logger.info(f"بدء مهمة التنظيف (حذف بعد {DRIVE_DELETE_AFTER_MINUTES} دقيقة)")
    while True:
        try:
            service = service_getter()
            if service:
                _clean_old_files(service)
        except Exception as e:
            logger.warning(f"خطأ في التنظيف: {e}")
        await asyncio.sleep(600)


def _clean_old_files(service):
    if not DRIVE_FOLDER_ID:
        return
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - (DRIVE_DELETE_AFTER_MINUTES * 60)
        results = service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
            fields="files(id, name, createdTime)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = results.get("files", [])
        deleted = 0
        for f in files:
            try:
                created = datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00")).timestamp()
                if created < cutoff:
                    service.files().delete(
                        fileId=f["id"],
                        supportsAllDrives=True,
                    ).execute()
                    deleted += 1
                    logger.info(f"تم حذف {f['name']} من Drive (أقدم من {DRIVE_DELETE_AFTER_MINUTES} دقيقة)")
            except Exception as e:
                logger.warning(f"فشل حذف {f.get('name', 'unknown')}: {e}")
        if deleted:
            logger.info(f"تم حذف {deleted} ملف(ات) قديم(ة)")
    except Exception as e:
        logger.warning(f"فشل تنظيف Drive: {e}")
