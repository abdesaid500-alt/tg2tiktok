from typing import Protocol


class Notifier(Protocol):
    async def notify_user(self, user_id: int, message: str) -> None: ...
