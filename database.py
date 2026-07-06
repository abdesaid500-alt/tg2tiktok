import json
import os
import threading
from datetime import datetime, timedelta
from config import DATA_DIR, PLANS

DB_PATH = os.path.join(DATA_DIR, "users.json")
_lock = threading.Lock()


def _ensure_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)


def _read():
    _ensure_db()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(data):
    _ensure_db()
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user(user_id):
    user_id = str(user_id)
    with _lock:
        data = _read()
        return data.get(user_id)


def create_user(user_id, plan="trial"):
    user_id = str(user_id)
    now = datetime.now()
    plan_days = PLANS.get(plan, PLANS["trial"])["days"]
    expires = (now + timedelta(days=plan_days)).strftime("%Y-%m-%d")
    user = {
        "user_id": int(user_id),
        "plan": plan,
        "plan_expires": expires,
        "daily_count": 0,
        "last_reset": now.strftime("%Y-%m-%d"),
        "language": "ar",
        "active": True,
        "woopsocial_api_key": "",
        "woopsocial_project_id": "",
        "woopsocial_social_account_id": "",
        "speed": 1.1,
        "split_minutes": 10,
        "schedule_minutes": 15,
        "joined_at": now.strftime("%Y-%m-%d"),
    }
    with _lock:
        data = _read()
        data[user_id] = user
        _write(data)
    return user


def update_user(user_id, **kwargs):
    user_id = str(user_id)
    with _lock:
        data = _read()
        if user_id in data:
            data[user_id].update(kwargs)
            _write(data)
            return data[user_id]
    return None


def get_all_users():
    with _lock:
        data = _read()
        return list(data.values())


def is_active(user_id):
    user = get_user(user_id)
    if not user:
        return False
    if not user.get("active", False):
        return False
    expires = user.get("plan_expires", "")
    if not expires:
        return False
    try:
        exp_date = datetime.strptime(expires, "%Y-%m-%d")
        if exp_date < datetime.now():
            return False
    except ValueError:
        return False
    return True


def can_process(user_id):
    user = get_user(user_id)
    if not user:
        return False
    reset_daily_if_needed(user_id)
    user = get_user(user_id)
    limit = PLANS.get(user["plan"], PLANS["trial"])["daily_limit"]
    return user["daily_count"] < limit


def increment_daily(user_id):
    user_id = str(user_id)
    with _lock:
        data = _read()
        if user_id in data:
            data[user_id]["daily_count"] = data[user_id].get("daily_count", 0) + 1
            _write(data)


def reset_daily_if_needed(user_id):
    user = get_user(user_id)
    if not user:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    if user.get("last_reset") != today:
        update_user(user_id, daily_count=0, last_reset=today)


def get_plan_info(user_id):
    user = get_user(user_id)
    if not user:
        return None
    plan = user.get("plan", "trial")
    plan_config = PLANS.get(plan, PLANS["trial"])
    return {
        "plan": plan,
        "plan_name_ar": plan_config["name_ar"],
        "daily_limit": plan_config["daily_limit"],
        "max_queue": plan_config["max_queue"],
        "daily_count": user.get("daily_count", 0),
        "expires": user.get("plan_expires", ""),
        "active": is_active(user_id),
    }
