import os

USER_BOT_TOKEN  = os.environ.get("USER_BOT_TOKEN", "")
ADMIN_BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN", "")
ADMIN_ID        = int(os.environ.get("ADMIN_ID", "7019977550"))

DRIVE_FOLDER_ID            = os.environ.get("DRIVE_FOLDER_ID", "1orTPggd2mdecKNR1DNc5rVvp6UI9mrEA")
DRIVE_DELETE_AFTER_MINUTES = 30

WOOPSOCIAL_BASE = "https://api.woopsocial.com/v1"
WOOSOCIAL_PROJECT_ID   = os.environ.get("WOOSOCIAL_PROJECT_ID", "")
TIKTOK_ACCOUNT_ID      = os.environ.get("TIKTOK_ACCOUNT_ID", "")

DEFAULT_SPEED    = 1.1
DEFAULT_SPLIT    = 10
DEFAULT_SCHEDULE = 15

PLANS = {
    "trial":     {"name_ar": "تجريبي",    "days": 3,  "daily_limit": 10,  "max_queue": 3},
    "basic":     {"name_ar": "أساسي",     "days": 30, "daily_limit": 25,  "max_queue": 5},
    "pro":       {"name_ar": "احترافي",   "days": 30, "daily_limit": 50,  "max_queue": 10},
    "unlimited": {"name_ar": "غير محدود", "days": 30, "daily_limit": 999, "max_queue": 20},
}

GOOGLE_CREDENTIALS_B64 = os.environ.get("GOOGLE_CREDENTIALS_B64", "")
TOKEN_PICKLE_B64       = os.environ.get("TOKEN_PICKLE_B64", "")
YOUTUBE_COOKIES_B64    = os.environ.get("YOUTUBE_COOKIES_B64", "")

TEMP_DIR = "temp_videos"
DATA_DIR = "data"
TIMEOUT  = 1800
PORT     = int(os.environ.get("PORT", 8080))
