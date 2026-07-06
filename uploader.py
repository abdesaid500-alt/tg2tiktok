import os
import pickle
import base64
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import DRIVE_FOLDER_ID, GOOGLE_CREDENTIALS_B64, TOKEN_PICKLE_B64

logger = logging.getLogger("uploader")

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDS_FILE = "credentials.json"
TOKEN_FILE = "token.pickle"
_service = None


def _save_credentials_from_env():
    if GOOGLE_CREDENTIALS_B64 and not os.path.exists(CREDS_FILE):
        try:
            decoded = base64.b64decode(GOOGLE_CREDENTIALS_B64)
            with open(CREDS_FILE, "wb") as f:
                f.write(decoded)
            logger.info("تم حفظ credentials.json من المتغير البيئي")
        except Exception as e:
            logger.error(f"فشل حفظ credentials.json: {e}")
    if TOKEN_PICKLE_B64 and not os.path.exists(TOKEN_FILE):
        try:
            decoded = base64.b64decode(TOKEN_PICKLE_B64)
            with open(TOKEN_FILE, "wb") as f:
                f.write(decoded)
            logger.info("تم حفظ token.pickle من المتغير البيئي")
        except Exception as e:
            logger.error(f"فشل حفظ token.pickle: {e}")


def _get_service():
    global _service
    if _service:
        return _service
    _save_credentials_from_env()
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "rb") as f:
                creds = pickle.load(f)
        except Exception as e:
            logger.warning(f"فشل تحميل token.pickle: {e}")
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"فشل تحديث التوكن: {e}")
                creds = None
        if not creds and os.path.exists(CREDS_FILE):
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
                creds = flow.run_local_server(port=0, open_browser=False)
                with open(TOKEN_FILE, "wb") as f:
                    pickle.dump(creds, f)
            except Exception as e:
                logger.error(f"فشل مصادقة Google Drive: {e}")
                return None
    if not creds:
        logger.error("لا يوجد creds صالحة لمصادقة Google Drive")
        return None
    try:
        _service = build("drive", "v3", credentials=creds)
        return _service
    except Exception as e:
        logger.error(f"فشل بناء Google Drive service: {e}")
        return None


def upload_to_drive(file_path, folder_id=None):
    folder_id = folder_id or DRIVE_FOLDER_ID
    service = _get_service()
    if not service:
        return {"id": None, "url": None, "name": None}
    file_name = os.path.basename(file_path)
    try:
        media = MediaFileUpload(file_path, resumable=True, chunksize=50 * 1024 * 1024)
        file_metadata = {
            "name": file_name,
            "parents": [folder_id] if folder_id else [],
        }
        drive_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,name",
            supportsAllDrives=True,
        ).execute()
        file_id = drive_file.get("id")
        make_public(service, file_id)
        file_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        logger.info(f"تم رفع {file_name} → {file_url}")
        return {"id": file_id, "url": file_url, "name": file_name}
    except Exception as e:
        logger.error(f"فشل رفع {file_name}: {e}")
        return {"id": None, "url": None, "name": file_name}


def make_public(service, file_id):
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
        logger.info(f"تم جعل الملف {file_id} عاماً")
    except Exception as e:
        logger.warning(f"فشل جعل الملف عاماً: {e}")


def delete_from_drive(file_id):
    service = _get_service()
    if not service:
        return False
    try:
        service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        logger.info(f"تم حذف الملف {file_id} من Drive")
        return True
    except Exception as e:
        logger.warning(f"فشل حذف الملف {file_id}: {e}")
        return False
