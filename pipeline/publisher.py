import os
import pickle
import base64
import tempfile
import logging
import time
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveUploader:
    def __init__(self, credentials_b64: str, token_pickle_b64: str, folder_id: str):
        self._creds_b64 = credentials_b64
        self._token_b64 = token_pickle_b64
        self._folder_id = folder_id
        self._service = None

    def _build_service(self):
        cache_dir = tempfile.gettempdir()
        pickle_path = os.path.join(cache_dir, "tg2tiktok_token.pickle")
        creds = None

        if self._token_b64:
            try:
                padding = "=" * (-len(self._token_b64) % 4)
                token_bytes = base64.b64decode(self._token_b64 + padding)
                with open(pickle_path, "wb") as f:
                    f.write(token_bytes)
            except Exception as e:
                logger.warning("Could not decode TOKEN_PICKLE_B64: %s", e)

        if os.path.exists(pickle_path):
            try:
                with open(pickle_path, "rb") as f:
                    creds = pickle.load(f)
            except Exception as e:
                logger.warning("token.pickle corrupt, will refresh: %s", e)
                creds = None

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(pickle_path, "wb") as f:
                    pickle.dump(creds, f)
                logger.info("token.pickle refreshed")
            except Exception as e:
                logger.error("Token refresh failed: %s", e)
                creds = None

        if not creds or not creds.valid:
            raise RuntimeError(
                "Google Drive: لا يوجد token صالح. "
                "تأكد من صحة TOKEN_PICKLE_B64 في Railway."
            )

        self._service = build("drive", "v3", credentials=creds)

    def upload(self, file_path: str, public: bool = True) -> str:
        if not self._service:
            self._build_service()

        name = os.path.basename(file_path)
        media = MediaFileUpload(file_path, resumable=True, chunksize=5 * 1024 * 1024)
        file_meta = {"name": name, "parents": [self._folder_id]}

        drive_file = (
            self._service.files()
            .create(body=file_meta, media_body=media, fields="id")
            .execute()
        )
        file_id = drive_file.get("id")

        if public:
            self._service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()

        return f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"

    def delete(self, file_id: str) -> bool:
        if not self._service:
            self._build_service()
        try:
            self._service.files().delete(fileId=file_id).execute()
            logger.info("Deleted file %s from Drive", file_id)
            return True
        except Exception as e:
            logger.warning("Failed to delete file %s: %s", file_id, e)
            return False


class WoopSocialPublisher:
    def __init__(self, api_key: str, project_id: str, account_id: str):
        self._api_key = api_key
        self._project_id = project_id
        self._account_id = account_id
        self._base = "https://api.woopsocial.com/v1"

    def upload_media(self, file_url: str) -> Optional[str]:
        import requests
        import os as _os

        tmp_path = None
        last_error = ""
        try:
            logger.info("Downloading from Drive: %s ...", file_url[:80])
            r = requests.get(file_url, stream=True, timeout=300)
            r.raise_for_status()
            total = 0
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                for chunk in r.iter_content(8192):
                    tmp.write(chunk)
                    total += len(chunk)
                tmp_path = tmp.name
            r.close()
            logger.info("Downloaded %d bytes to %s", total, tmp_path)

            for attempt in range(1, 4):
                try:
                    file_size = _os.path.getsize(tmp_path)
                    logger.info(
                        "WoopSocial upload attempt %d/3 — file=%s size=%d",
                        attempt, tmp_path, file_size,
                    )
                    with open(tmp_path, "rb") as vf:
                        resp = requests.post(
                            f"{self._base}/media",
                            params={"projectId": self._project_id},
                            headers={"Authorization": f"Bearer {self._api_key}"},
                            files={"file": ("video.mp4", vf, "video/mp4")},
                            timeout=300,
                        )
                    logger.info(
                        "WoopSocial attempt %d response: %s %s",
                        attempt, resp.status_code, resp.text[:200],
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        mid = (
                            data.get("id")
                            or data.get("mediaId")
                            or data.get("media_id")
                        )
                        if mid:
                            logger.info("WoopSocial upload OK: media_id=%s", mid)
                            return mid
                        logger.warning("WoopSocial OK but no media_id: %s", data)
                    last_error = f"{resp.status_code} {resp.text[:300]}"
                    logger.warning(
                        "WoopSocial media attempt %d: %s", attempt, last_error,
                    )
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "WoopSocial media attempt %d error: %s", attempt, e
                    )
                time.sleep(5)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

        logger.error("WoopSocial media upload failed: %s", last_error)
        return None

    def schedule_post(
        self, media_id: str, schedule_at: str, description: str = ""
    ) -> tuple[bool, str]:
        import requests

        if not schedule_at.endswith("Z"):
            schedule_at += "Z"

        payload = {
            "content": [
                {
                    "text": description,
                    "media": [{"type": "MEDIA_LIBRARY", "mediaId": media_id}],
                }
            ],
            "schedule": {
                "type": "SCHEDULE_FOR_LATER",
                "scheduledFor": schedule_at,
            },
            "autoDeleteMediaAfterPublish": True,
            "socialAccounts": [
                {
                    "platform": "TIKTOK",
                    "socialAccountId": self._account_id,
                    "postType": "VIDEO",
                    "postMode": "DIRECT_POST",
                    "privacyLevel": "PUBLIC_TO_EVERYONE",
                    "allowComment": True,
                    "allowDuet": False,
                    "allowStitch": False,
                    "isYourBrand": False,
                    "isBrandedContent": False,
                    "isAiGeneratedContent": True,
                    "autoAddMusic": True,
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        last_err = ""
        for attempt in range(1, 4):
            try:
                resp = requests.post(
                    f"{self._base}/posts",
                    headers=headers, json=payload, timeout=30,
                )
                if resp.status_code in (200, 201):
                    logger.info("WoopSocial post created: %s", resp.text[:200])
                    return True, ""
                try:
                    body = resp.json()
                    ve = body.get("validationErrors")
                    if ve:
                        last_err = f"validation failed: {ve}"
                    else:
                        last_err = body.get("message") or body.get("code") or resp.text[:400]
                except Exception:
                    last_err = resp.text[:400]
                logger.warning(
                    "WoopSocial post attempt %d: %s %s",
                    attempt, resp.status_code, last_err,
                )
            except Exception as e:
                last_err = str(e)
                logger.warning(
                    "WoopSocial post attempt %d error: %s", attempt, e
                )
            time.sleep(5)

        logger.error("WoopSocial schedule failed: %s", last_err)
        return False, last_err
