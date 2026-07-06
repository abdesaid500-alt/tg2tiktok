import os
import json
import asyncio
from typing import Any

_data_dir: str = "data"
_lock = asyncio.Lock()
_cache: dict = {}


def init(path: str) -> None:
    global _data_dir
    _data_dir = path
    os.makedirs(path, exist_ok=True)


def _path(name: str) -> str:
    return os.path.join(_data_dir, f"{name}.json")


async def _load(name: str) -> dict:
    p = _path(name)
    if os.path.exists(p):
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(
            None, lambda: json.loads(open(p, encoding="utf-8").read())
        )
        return raw
    return {}


async def _dump(name: str, data: dict) -> None:
    p = _path(name)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: open(p, "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, indent=2)
        ),
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
