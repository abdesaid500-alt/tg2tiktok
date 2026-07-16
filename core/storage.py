import os
import json
import asyncio
from typing import Any, Optional
import httpx

_data_dir: str = "data"
_lock = asyncio.Lock()
_cache: dict = {}

_supabase_url: Optional[str] = None
_supabase_key: Optional[str] = None
_http: Optional[httpx.AsyncClient] = None


def init(path: str, supabase_url: str = "", supabase_key: str = "") -> None:
    global _data_dir, _supabase_url, _supabase_key
    _data_dir = path
    os.makedirs(path, exist_ok=True)
    if supabase_url and supabase_key:
        _supabase_url = supabase_url.rstrip("/")
        _supabase_key = supabase_key


async def close() -> None:
    global _http
    if _http:
        await _http.aclose()
        _http = None


def _path(name: str) -> str:
    return os.path.join(_data_dir, f"{name}.json")


async def _load(name: str) -> dict:
    if _supabase_url:
        if name == "users":
            return await _db_load_users()
        return await _db_load_kv(name)
    p = _path(name)
    if os.path.exists(p):
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(
            None, lambda: json.loads(open(p, encoding="utf-8").read())
        )
        return raw
    return {}


async def _dump(name: str, data: dict) -> None:
    if _supabase_url:
        if name == "users":
            await _db_save_users(data)
        else:
            await _db_save_kv(name, data)
        return
    p = _path(name)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: open(p, "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, indent=2)
        ),
    )


async def _supabase() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            base_url=f"{_supabase_url}/rest/v1",
            headers={
                "apikey": _supabase_key,
                "Authorization": f"Bearer {_supabase_key}",
            },
        )
    return _http


async def _db_load_users() -> dict:
    client = await _supabase()
    resp = await client.get("/users", params={"select": "telegram_id,data"})
    rows = resp.json()
    return {str(r["telegram_id"]): r["data"] for r in rows}


async def _db_save_users(data: dict) -> None:
    client = await _supabase()
    payload = [{"telegram_id": int(uid), "data": u} for uid, u in data.items()]
    if not payload:
        return
    await client.post(
        "/users",
        json=payload,
        headers={"Prefer": "resolution=merge-duplicates"},
    )


async def _db_load_kv(name: str) -> dict:
    client = await _supabase()
    resp = await client.get("/app_kv", params={"key": f"eq.{name}", "select": "value"})
    rows = resp.json()
    if rows and isinstance(rows, list) and rows[0].get("value") is not None:
        return rows[0]["value"]
    return {}


async def _db_save_kv(name: str, data: dict) -> None:
    client = await _supabase()
    payload = {"key": name, "value": data}
    await client.post(
        "/app_kv",
        json=payload,
        headers={"Prefer": "resolution=merge-duplicates"},
    )


async def get(name: str) -> dict:
    async with _lock:
        if name not in _cache:
            _cache[name] = await _load(name)
        return _cache[name]


async def save(name: str) -> None:
    async with _lock:
        await _dump(name, _cache.get(name, {}))


async def set_field(name: str, key: str, value: Any) -> None:
    async with _lock:
        data = await _load(name)
        data[key] = value
        await _dump(name, data)
        if name in _cache:
            _cache[name] = data


async def delete_field(name: str, key: str) -> None:
    async with _lock:
        data = await _load(name)
        data.pop(key, None)
        await _dump(name, data)
        if name in _cache:
            _cache[name] = data