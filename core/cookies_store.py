import time
import base64
from typing import Optional
from core import storage as store

_KEY = "yt_cookies"


async def get_cookies_b64(fallback: str = "") -> str:
    try:
        data = await store.get(_KEY)
    except Exception:
        data = {}
    if isinstance(data, dict) and data.get("value"):
        return data["value"]
    return fallback


async def set_cookies_b64(cookies_b64: str, admin_id: int) -> None:
    try:
        padding = "=" * (-len(cookies_b64) % 4)
        base64.b64decode(cookies_b64 + padding, validate=True)
    except Exception as e:
        raise ValueError(f"Base64 غير صالح: {e}")

    await store.set_field(_KEY, "value", cookies_b64)
    await store.set_field(_KEY, "updated_at", time.time())
    await store.set_field(_KEY, "updated_by", admin_id)


async def get_last_update_info() -> Optional[dict]:
    try:
        data = await store.get(_KEY)
    except Exception:
        return None
    if isinstance(data, dict) and data.get("value"):
        return {
            "updated_at": data.get("updated_at"),
            "updated_by": data.get("updated_by"),
        }
    return None
