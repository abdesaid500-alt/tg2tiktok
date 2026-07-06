import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from core.config import Settings
from core.models import User, QueueItem, PLANS
from core import storage as store
from core.notifier import Notifier
from pipeline.media import download_video, split_and_speed, cleanup_temp
from pipeline.publisher import GoogleDriveUploader, WoopSocialPublisher

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, settings: Settings, notify: Notifier):
        self._settings = settings
        self._notify = notify
        self._queue: asyncio.Queue = asyncio.Queue()
        self._processing: set[int] = set()
        self._stop = asyncio.Event()
        self._temp_dir = settings.temp_dir
        self._drive: Optional[GoogleDriveUploader] = None
        self._publishers: dict[int, WoopSocialPublisher] = {}

    def _get_drive(self) -> GoogleDriveUploader:
        if not self._drive:
            self._drive = GoogleDriveUploader(
                self._settings.google_credentials_b64,
                self._settings.token_pickle_b64,
                self._settings.drive_folder_id,
            )
        return self._drive

    def _get_publisher(self, user: User) -> WoopSocialPublisher:
        uid = user.telegram_id
        if uid not in self._publishers:
            self._publishers[uid] = WoopSocialPublisher(
                user.woopsocial_api_key,
                user.woopsocial_project_id,
                user.woopsocial_account_id,
            )
        return self._publishers[uid]

    async def enqueue(self, user_id: int, url: str) -> tuple[bool, str, Optional[str]]:
        users = await store.get("users")
        uid = str(user_id)
        u_data = users.get(uid)
        if not u_data:
            return False, "not_active", None

        user = User(**u_data)
        if not user.is_active():
            return False, "not_active", None
        if not user.woopsocial_api_key:
            return False, "no_api_key", None

        pp = user.plan_params()
        queue_size = self._queue.qsize()
        user_in_queue = sum(
            1 for i in list(self._queue._queue) if i.user_id == user_id
        )
        if user_in_queue >= pp.queue_limit:
            return False, "queue_full", None

        item_id = uuid.uuid4().hex[:8].upper()
        item = QueueItem(
            id=item_id,
            user_id=user_id,
            youtube_url=url,
            video_title="",
            duration_seconds=0,
            status="queued",
            created_at=time.time(),
        )
        await self._queue.put(item)
        return True, "queued", item_id

    async def cancel_queue(self, user_id: int) -> int:
        count = 0
        remaining = []
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if item.user_id == user_id and item.status == "queued":
                    count += 1
                else:
                    remaining.append(item)
            except asyncio.QueueEmpty:
                break
        for item in remaining:
            await self._queue.put(item)
        self._processing.discard(user_id)
        return count

    def get_user_queue(self, user_id: int) -> list[dict]:
        items = []
        for item in list(self._queue._queue):
            if item.user_id == user_id:
                items.append({
                    "id": item.id,
                    "title": item.video_title or "جاري التحميل...",
                    "status": item.status,
                })
        return items

    async def run(self):
        logger.info("Worker started")
        os.makedirs(self._temp_dir, exist_ok=True)

        while not self._stop.is_set():
            try:
                item = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                uid = item.user_id
                if uid in self._processing:
                    await self._queue.put(item)
                    await asyncio.sleep(0.5)
                    continue
                self._processing.add(uid)
                asyncio.create_task(self._process_item(item))
            except asyncio.TimeoutError:
                continue

        logger.info("Worker stopped")

    async def _process_item(self, item: QueueItem):
        uid = item.user_id
        try:
            users = await store.get("users")
            u_data = users.get(str(uid))
            if not u_data:
                return
            user = User(**u_data)

            await self._notify.notify_user(uid, "⏳ جاري التحميل...")

            item_dir = os.path.join(self._temp_dir, f"{uid}_{item.id}")
            os.makedirs(item_dir, exist_ok=True)

            info = await download_video(
                item.youtube_url,
                item_dir,
                self._settings.yt_cookies_b64,
                self._settings.yt_po_token,
                self._settings.yt_visitor_data,
            )
            item.video_title = info["title"]
            item.duration_seconds = info["duration"]
            video_path = info["path"]

            await self._notify.notify_user(uid, "✂️ جاري التقسيم والتسريع...")

            parts = await split_and_speed(
                video_path, item_dir,
                user.split_minutes, user.speed,
            )
            item.parts = parts

            await self._notify.notify_user(uid, f"☁️ جاري الرفع... ({len(parts)} أجزاء)")

            drive = self._get_drive()
            publisher = self._get_publisher(user)

            drive_urls = []
            for p in parts:
                url = drive.upload(p)
                drive_urls.append(url)

            await self._notify.notify_user(uid, "📤 جاري الجدولة على تيكتوك...")

            interval = user.schedule_interval
            now = datetime.utcnow()
            success_count = 0
            buffer_minutes = 5
            last_pub_error = ""

            for i, dl_url in enumerate(drive_urls):
                offset = buffer_minutes + (i * interval)
                schedule_at = (now + timedelta(minutes=offset)).isoformat()
                title_short = item.video_title[:50] if item.video_title else "فيديو"
                caption = f"{title_short} | {i + 1}/{len(parts)}"

                media_id = publisher.upload_media(dl_url)
                if not media_id:
                    continue

                ok, err = publisher.schedule_post(media_id, schedule_at, caption)
                if ok:
                    success_count += 1
                elif err:
                    last_pub_error = err

            if success_count > 0:
                user.total_videos += 1
                user.total_parts += success_count
                today = time.strftime("%Y-%m-%d")
                user.daily_counts[today] = user.daily_counts.get(today, 0) + 1
                user.last_scheduled_at = time.time()
                users[str(uid)] = user.__dict__
                await store.save("users")

                await self._notify.notify_user(
                    uid,
                    f"🎉 تم نشر {success_count} جزء — جزء كل {interval} دقيقة",
                )
            else:
                err_txt = last_pub_error or "تحقق من بيانات WoopSocial."
                await self._notify.notify_user(
                    uid, f"❌ فشل النشر على تيكتوك:\n{err_txt[:200]}"
                )

        except PermissionError:
            await self._notify.notify_user(
                uid,
                "⚠️ انتهت صلاحية ملف تعريف يوتيوب! تواصل مع الدعم لتجديد cookies.",
            )
        except Exception as e:
            logger.error("Processing failed for %d: %s", uid, e)
            await self._notify.notify_user(
                uid, f"❌ فشلت المعالجة: {str(e)[:200]}"
            )
        finally:
            self._processing.discard(uid)
            item_dir = os.path.join(self._temp_dir, f"{uid}_{item.id}")
            try:
                import shutil
                shutil.rmtree(item_dir, ignore_errors=True)
            except Exception:
                pass

    async def stop(self):
        self._stop.set()
