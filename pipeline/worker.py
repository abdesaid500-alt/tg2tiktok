import asyncio
import json
import logging
import os
import time
import uuid
import dataclasses
from datetime import datetime, timedelta
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.config import Settings
from core.models import User, QueueItem, PLANS
from core import storage as store
from core.notifier import Notifier
from pipeline.media import download_video, split_and_speed, cleanup_temp
from pipeline.publisher import GoogleDriveUploader, WoopSocialPublisher

logger = logging.getLogger(__name__)

_DRIVE_DELETE_DELAY_MINUTES = 30
_DELETIONS_FILE = "drive_deletions.json"
_QUEUE_FILE = "queue.json"


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
        self._pending_deletions: dict[str, float] = {}  # file_id -> delete_after_timestamp
        self._failed_items: dict[str, dict] = {}  # item_id -> {user_id, youtube_url}

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
        if not user.has_api_key() and not user.can_use_free_trial():
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
        self._save_queue()
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
        self._save_queue()
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

    def _load_pending_deletions(self):
        path = os.path.join(self._settings.data_dir, _DELETIONS_FILE)
        try:
            with open(path, "r") as f:
                self._pending_deletions = json.load(f)
            logger.info("Loaded %d pending deletions", len(self._pending_deletions))
        except (FileNotFoundError, json.JSONDecodeError):
            self._pending_deletions = {}

    def _save_pending_deletions(self):
        path = os.path.join(self._settings.data_dir, _DELETIONS_FILE)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(self._pending_deletions, f)
        except Exception as e:
            logger.warning("Failed to save pending deletions: %s", e)

    def _schedule_drive_deletion(self, drive_url: str):
        import re
        m = re.search(r'id=([^&\s]+)', drive_url)
        if not m:
            return
        file_id = m.group(1)
        delete_at = time.time() + _DRIVE_DELETE_DELAY_MINUTES * 60
        self._pending_deletions[file_id] = delete_at
        self._save_pending_deletions()
        logger.info("Scheduled Drive deletion for %s at %s", file_id,
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(delete_at)))

    def _cleanup_drive_files(self):
        now = time.time()
        expired = [fid for fid, ts in self._pending_deletions.items() if now >= ts]
        if not expired:
            return
        drive = self._get_drive()
        for fid in expired:
            ok = drive.delete(fid)
            if ok:
                del self._pending_deletions[fid]
        if expired:
            self._save_pending_deletions()

    @property
    def _queue_path(self):
        return os.path.join(self._settings.data_dir, _QUEUE_FILE)

    def _save_queue(self):
        path = self._queue_path
        items = []
        for item in list(self._queue._queue):
            items.append(dataclasses.asdict(item))
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("Failed to save queue: %s", e)

    def _load_queue(self):
        path = self._queue_path
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
            restored = 0
            for data in items:
                try:
                    data.pop("parts", None)
                    data.pop("error", None)
                    item = QueueItem(
                        id=data["id"],
                        user_id=data["user_id"],
                        youtube_url=data["youtube_url"],
                        video_title=data.get("video_title", ""),
                        duration_seconds=data.get("duration_seconds", 0),
                        status="queued",
                        created_at=data.get("created_at", time.time()),
                    )
                    self._queue.put_nowait(item)
                    restored += 1
                except Exception as e:
                    logger.warning("Failed to restore queue item: %s", e)
            if restored:
                logger.info("Restored %d items from saved queue", restored)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    async def run(self):
        logger.info("Worker started")
        os.makedirs(self._temp_dir, exist_ok=True)
        self._load_pending_deletions()
        self._load_queue()
        last_cleanup = time.time()

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
                pass

            if time.time() - last_cleanup > 60:
                self._cleanup_drive_files()
                last_cleanup = time.time()

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

            user.total_videos += 1
            user.total_parts += len(parts)
            user.free_parts_used += len(parts)
            today = time.strftime("%Y-%m-%d")
            user.daily_counts[today] = user.daily_counts.get(today, 0) + 1
            users[str(uid)] = user.__dict__
            await store.save("users")

            if user.has_api_key():
                drive = self._get_drive()
                publisher = self._get_publisher(user)

                # --- 0. Cleanup old WoopSocial media to free storage ---
                await asyncio.to_thread(publisher.cleanup_media_storage)

                # --- رفع + جدولة كل جزء على حدة (رفع → جدولة → التالي) ---
                interval = user.schedule_interval
                now = datetime.utcnow()
                buffer_minutes = 5
                success_count = 0
                failed_indices = []
                media_ids = []
                t0 = time.time()

                for i, p in enumerate(parts):
                    # 1. رفع إلى Drive
                    await self._notify.notify_user(
                        uid, f"☁️ ({i + 1}/{len(parts)}) جاري الرفع..."
                    )
                    dl_url = await asyncio.wait_for(
                        asyncio.to_thread(drive.upload, p), timeout=600,
                    )

                    # 2. رفع إلى WoopSocial
                    await self._notify.notify_user(
                        uid, f"📤 ({i + 1}/{len(parts)}) الرفع على ووب سوشل..."
                    )
                    mid = await asyncio.to_thread(publisher.upload_media, dl_url)
                    if not mid:
                        failed_indices.append(i)
                        media_ids.append(None)
                        logger.error("WoopSocial part %d FAILED after 5 retries", i + 1)
                        continue

                    media_ids.append(mid)
                    logger.info("Part %d WoopSocial OK: media_id=%s", i + 1, mid)

                    # 3. جدولة على TikTok فوراً
                    offset = buffer_minutes + (i * interval)
                    schedule_at = (now + timedelta(minutes=offset)).isoformat()
                    title_short = item.video_title[:50] if item.video_title else "فيديو"
                    caption = f"{title_short} | {i + 1}/{len(parts)}"
                    ok, err = await asyncio.to_thread(publisher.schedule_post, mid, schedule_at, caption)
                    if ok:
                        self._schedule_drive_deletion(dl_url)
                        success_count += 1
                        logger.info("Part %d scheduled OK — %d/%d", i + 1, success_count, len(parts))
                    else:
                        failed_indices.append(i)
                        logger.error("Schedule failed for part %d: %s", i + 1, err)

                logger.info("All parts done in %.1fs — %d/%d scheduled", time.time() - t0, success_count, len(parts))

                # --- إرسال النتيجة للمستخدم ---
                if not failed_indices:
                    msg = f"🎉 تم نشر {success_count} جزء — جزء كل {interval} دقيقة"
                    await self._notify.notify_user(uid, msg)
                else:
                    msg_parts = []
                    if success_count > 0:
                        msg_parts.append(f"✅ تم جدولة {success_count} أجزاء بنجاح.")
                    msg_parts.append(
                        f"⚠️ فشل رفع {len(failed_indices)} من {len(parts)} أجزاء."
                    )
                    msg_parts.append("اختر الإجراء المناسب:")
                    markup = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "🔄 إعادة معالجة الفيديو كاملاً",
                                callback_data=f"retry_{item.id}",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "⏭️ تخطي الأجزاء الفاشلة",
                                callback_data=f"skip_{item.id}",
                            ),
                        ],
                    ])
                    self._failed_items[item.id] = {
                        "user_id": uid,
                        "youtube_url": item.youtube_url,
                    }
                    # Cleanup orphaned media from WoopSocial
                    for i, mid in enumerate(media_ids):
                        if mid:
                            await asyncio.to_thread(publisher.delete_media, mid)
                    await self._notify.notify_user_markup(uid, "\n".join(msg_parts), markup)
            else:
                remaining = max(0, FREE_PARTS_LIMIT - user.free_parts_used)
                msg = f"✅ تم تجهيز {len(parts)} جزء من الفيديو!"
                plans_text = (
                    "\n\n━━━ 📋 خطط الاشتراك ━━━\n"
                )
                from core.models import PLANS
                for key, pp in PLANS.items():
                    name = {"trial": "تجريبي", "basic": "أساسي", "pro": "احترافي", "unlimited": "غير محدود"}.get(key, key)
                    plans_text += f"\n• {name}: {pp.daily_limit} فيديو/يوم | {pp.queue_limit} طابور | {pp.duration_days} يوم"
                msg += plans_text
                msg += "\n\n💬 تواصل مع الدعم للاشتراك"
                if remaining > 0:
                    msg += f"\n⚡ تبقى لك {remaining} من {FREE_PARTS_LIMIT} جزء مجاني للتجربة"
                else:
                    msg += "\n⚠️ انتهت الأجزاء المجانية"
                await self._notify.notify_user(uid, msg)

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
            self._save_queue()
            item_dir = os.path.join(self._temp_dir, f"{uid}_{item.id}")
            try:
                import shutil
                shutil.rmtree(item_dir, ignore_errors=True)
            except Exception:
                pass

    async def retry_failed(self, item_id: str) -> bool:
        state = self._failed_items.pop(item_id, None)
        if not state:
            return False
        ok, _, _ = await self.enqueue(state["user_id"], state["youtube_url"])
        return ok

    async def skip_failed(self, item_id: str) -> bool:
        state = self._failed_items.pop(item_id, None)
        return state is not None

    async def stop(self):
        self._stop.set()
