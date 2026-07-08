import os
import pickle
import base64
import tempfile
import logging
import time
import json
from typing import Optional

import requests
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)


class GoogleDriveUploader:
    def __init__(self, credentials_b64: str, token_pickle_b64: str, folder_id: str):
        self._token_b64 = token_pickle_b64
        self._folder_id = folder_id

    def _get_credentials(self):
        cache_dir = tempfile.gettempdir()
        pickle_path = os.path.join(cache_dir, "tg2tiktok_token.pickle")

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
        else:
            creds = None

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(pickle_path, "wb") as f:
                    pickle.dump(creds, f)
                logger.info("Drive token refreshed")
            except Exception as e:
                logger.error("Token refresh failed: %s", e)
                creds = None

        if not creds or not creds.valid:
            raise RuntimeError(
                "Google Drive: لا يوجد token صالح. "
                "تأكد من صحة TOKEN_PICKLE_B64 في Railway."
            )

        return creds

    def upload(self, file_path: str, public: bool = True) -> str:
        last_error = ""
        for attempt in range(1, 6):
            try:
                creds = self._get_credentials()
                access_token = creds.token
                name = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)

                # --- 1. Create resumable upload session ---
                session_resp = requests.post(
                    "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json; charset=UTF-8",
                        "X-Upload-Content-Type": "video/mp4",
                        "X-Upload-Content-Length": str(file_size),
                    },
                    data=json.dumps({"name": name, "parents": [self._folder_id]}),
                    timeout=30,
                )
                if session_resp.status_code != 200:
                    last_error = f"session: {session_resp.status_code} {session_resp.text[:200]}"
                    logger.warning("Drive attempt %d: %s", attempt, last_error)
                    continue

                upload_url = session_resp.headers.get("Location")
                if not upload_url:
                    last_error = "no Location header"
                    logger.warning("Drive attempt %d: %s", attempt, last_error)
                    continue

                # --- 2. Upload file bytes (single PUT for resumable) ---
                with open(file_path, "rb") as f:
                    upload_resp = requests.put(
                        upload_url,
                        headers={
                            "Content-Length": str(file_size),
                            "Content-Type": "video/mp4",
                        },
                        data=f,
                        timeout=600,
                    )
                if upload_resp.status_code not in (200, 201):
                    last_error = f"upload: {upload_resp.status_code} {upload_resp.text[:300]}"
                    logger.warning("Drive attempt %d: %s", attempt, last_error)
                    continue

                file_id = upload_resp.json().get("id")
                if not file_id:
                    last_error = f"no id: {upload_resp.text[:200]}"
                    logger.warning("Drive attempt %d: %s", attempt, last_error)
                    continue

                # --- 3. Set public permission ---
                if public:
                    try:
                        requests.post(
                            f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Content-Type": "application/json",
                            },
                            data=json.dumps({"type": "anyone", "role": "reader"}),
                            timeout=30,
                        )
                    except Exception as e:
                        logger.warning("Drive set public failed (non-fatal): %s", e)

                logger.info("Drive upload OK: %s (attempt %d)", file_path, attempt)
                return f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"

            except requests.exceptions.Timeout:
                last_error = "timeout"
                logger.warning("Drive upload attempt %d/5 timeout", attempt)
            except Exception as e:
                last_error = str(e)
                logger.warning("Drive upload attempt %d/5 failed: %s", attempt, e)

            # Exponential backoff: 5, 10, 20, 40, 80 → capped at 60s
            sleep = min(5 * (2 ** (attempt - 1)), 60)
            time.sleep(sleep)

        raise RuntimeError(f"Drive upload failed after 5 attempts: {last_error}")

    def delete(self, file_id: str) -> bool:
        try:
            creds = self._get_credentials()
            resp = requests.delete(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=30,
            )
            if resp.status_code in (200, 204):
                logger.info("Deleted file %s from Drive", file_id)
                return True
            logger.warning("Failed to delete file %s: %s %s", file_id, resp.status_code, resp.text[:200])
            return False
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

            for attempt in range(1, 6):
                try:
                    file_size = _os.path.getsize(tmp_path)
                    logger.info(
                        "WoopSocial upload attempt %d/5 — file=%s size=%d",
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
        for attempt in range(1, 6):
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
