import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Settings:
    user_bot_token: str
    admin_bot_token: str
    admin_id: int
    drive_folder_id: str
    google_credentials_b64: str
    token_pickle_b64: str
    yt_cookies_b64: str
    yt_po_token: Optional[str] = None
    yt_visitor_data: Optional[str] = None
    supabase_url: str = ""
    supabase_service_key: str = ""
    free_trial_api_key: str = ""
    free_trial_project_id: str = ""
    free_trial_account_id: str = ""
    data_dir: str = "data"
    temp_dir: str = "temp_videos"
    port: int = 8080

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            user_bot_token=os.environ["USER_BOT_TOKEN"],
            admin_bot_token=os.environ["ADMIN_BOT_TOKEN"],
            admin_id=int(os.environ["ADMIN_ID"]),
            drive_folder_id=os.environ["DRIVE_FOLDER_ID"],
            google_credentials_b64=os.environ["GOOGLE_CREDENTIALS_B64"],
            token_pickle_b64=os.environ["TOKEN_PICKLE_B64"],
            yt_cookies_b64=os.environ.get("YT_COOKIES_B64", ""),
            yt_po_token=os.environ.get("YT_PO_TOKEN"),
            yt_visitor_data=os.environ.get("YT_VISITOR_DATA"),
            supabase_url=os.environ.get("SUPABASE_URL", ""),
            supabase_service_key=os.environ.get("SUPABASE_SERVICE_KEY", ""),
            free_trial_api_key=os.environ.get("FREE_TRIAL_API_KEY", ""),
            free_trial_project_id=os.environ.get("FREE_TRIAL_PROJECT_ID", ""),
            free_trial_account_id=os.environ.get("FREE_TRIAL_ACCOUNT_ID", ""),
            data_dir=os.environ.get("DATA_DIR", "data"),
            temp_dir=os.environ.get("TEMP_DIR", "temp_videos"),
            port=int(os.environ.get("PORT", 8080)),
        )
