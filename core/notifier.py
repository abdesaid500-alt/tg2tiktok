from typing import Protocol, Optional

from telegram import InlineKeyboardMarkup


class Notifier(Protocol):
    async def notify_user(self, user_id: int, message: str) -> None: ...
    async def notify_user_markup(self, user_id: int, message: str, markup: Optional[InlineKeyboardMarkup] = None) -> None: ...
