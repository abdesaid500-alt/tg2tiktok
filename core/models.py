from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class PlanParams:
    name: str
    duration_days: int
    daily_limit: int
    queue_limit: int


PLANS = {
    "trial": PlanParams("trial", 3, 10, 3),
    "basic": PlanParams("basic", 30, 25, 5),
    "pro": PlanParams("pro", 30, 50, 10),
    "unlimited": PlanParams("unlimited", 30, 999, 20),
}


@dataclass
class User:
    telegram_id: int
    plan: str
    expires_at: float
    created_at: float
    username: str = ""
    status: str = "active"
    woopsocial_api_key: str = ""
    woopsocial_project_id: str = ""
    woopsocial_account_id: str = ""
    language: str = "ar"
    speed: float = 1.1
    split_minutes: int = 10
    schedule_interval: int = 15
    total_videos: int = 0
    total_parts: int = 0
    last_active: float = 0.0
    last_scheduled_at: Optional[float] = None
    daily_counts: dict = field(default_factory=dict)

    def is_active(self) -> bool:
        if self.status != "active":
            return False
        if time.time() > self.expires_at:
            return False
        return True

    def plan_params(self) -> PlanParams:
        return PLANS.get(self.plan, PLANS["trial"])

    def today_count(self) -> int:
        today = time.strftime("%Y-%m-%d")
        return self.daily_counts.get(today, 0)

    def can_process(self) -> bool:
        pp = self.plan_params()
        return self.today_count() < pp.daily_limit


@dataclass
class QueueItem:
    id: str
    user_id: int
    youtube_url: str
    video_title: str
    duration_seconds: float
    status: str
    created_at: float
    parts: list = field(default_factory=list)
    error: Optional[str] = None
