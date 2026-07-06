import asyncio
import logging
from database import get_plan_info
from config import PLANS

logger = logging.getLogger("queue_manager")

_queues = {}
_processing = {}


def _get_queue(user_id):
    if user_id not in _queues:
        _queues[user_id] = asyncio.Queue()
    return _queues[user_id]


def add_to_queue(user_id, url):
    plan_info = get_plan_info(user_id)
    if not plan_info or not plan_info["active"]:
        return False, "الحساب غير نشط"
    q = _get_queue(user_id)
    max_queue = plan_info["max_queue"]
    if q.qsize() >= max_queue:
        return False, f"الطابور ممتلئ (الحد: {max_queue})"
    q.put_nowait(url)
    return True, None


def get_queue_size(user_id):
    q = _get_queue(user_id)
    return q.qsize()


def cancel_queue(user_id):
    if user_id in _queues:
        q = _queues[user_id]
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except asyncio.QueueEmpty:
                break
    if user_id in _processing:
        _processing[user_id] = False


async def process_queue(user_id, bot):
    if user_id in _processing and _processing[user_id]:
        logger.info(f"المستخدم {user_id} قيد المعالجة حالياً")
        return
    _processing[user_id] = True
    q = _get_queue(user_id)
    try:
        while not q.empty() and _processing.get(user_id, False):
            url = await q.get()
            try:
                from processor import process_video
                await process_video(user_id, url, bot, None)
            except Exception as e:
                logger.error(f"خطأ في معالجة فيديو للمستخدم {user_id}: {e}")
            finally:
                q.task_done()
    finally:
        _processing[user_id] = False
