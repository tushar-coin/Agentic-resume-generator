from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


DEFAULT_DRIVE_FOLDER_URL = (
    "https://drive.google.com/drive/folders/"
    "13BSF9gvZwAt8WW42nqVL9WoKZDdkgQlT?usp=drive_link"
)
DEFAULT_DRIVE_FOLDER_LINK = (
    "https://drive.google.com/drive/folders/"
    "13BSF9gvZwAt8WW42nqVL9WoKZDdkgQlT"
)
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _drive_folder_id(folder: str) -> str:
    folder = folder.strip()
    if not folder:
        return ""

    parsed = urlparse(folder)
    if not parsed.netloc:
        return folder

    parts = [part for part in parsed.path.split("/") if part]
    if "folders" in parts:
        index = parts.index("folders")
        if index + 1 < len(parts):
            return parts[index + 1]

    query = parse_qs(parsed.query)
    return (query.get("id") or [""])[0]


def _build_drive_service() -> Any:
    oauth_client_secrets = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "")
    oauth_token_file = Path(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", ".google_drive_token.json"))

    if oauth_client_secrets:
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(f"missing_oauth_dependencies: {exc}") from exc

        credentials = None
        if oauth_token_file.exists():
            credentials = Credentials.from_authorized_user_file(
                str(oauth_token_file),
                DRIVE_SCOPES,
            )

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(GoogleAuthRequest())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    oauth_client_secrets,
                    DRIVE_SCOPES,
                )
                credentials = flow.run_local_server(port=0)
            oauth_token_file.write_text(credentials.to_json(), encoding="utf-8")

        return build("drive", "v3", credentials=credentials)

    credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE", ""
    )
    if not credentials_file:
        raise RuntimeError("missing_google_credentials")

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(f"missing_google_dependencies: {exc}") from exc

    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=credentials)


def upload_resume_to_drive(path: Path) -> dict[str, str] | None:
    """Upload a generated resume to Google Drive."""
    folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID") or os.getenv(
        "GOOGLE_DRIVE_FOLDER_URL", DEFAULT_DRIVE_FOLDER_URL
    )
    folder_id = _drive_folder_id(folder)

    if not folder_id:
        print("DEBUG post_generation: Google Drive folder not configured; skipping upload")
        return {"status": "skipped", "reason": "missing_google_drive_folder"}

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        print(f"DEBUG post_generation: Google Drive dependencies missing: {exc}")
        return {"status": "skipped", "reason": f"missing_google_dependencies: {exc}"}

    try:
        service = _build_drive_service()
        metadata = {"name": path.name, "parents": [folder_id]}
        media = MediaFileUpload(str(path), mimetype="application/x-tex", resumable=False)
        file_data = (
            service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

        if os.getenv("GOOGLE_DRIVE_SHARE_ANYONE", "1") != "0":
            service.permissions().create(
                fileId=file_data["id"],
                body={"type": "anyone", "role": "reader"},
                fields="id",
                supportsAllDrives=True,
            ).execute()

        print(f"DEBUG post_generation: uploaded resume to Drive: {file_data.get('webViewLink')}")
        return {
            "status": "uploaded",
            "id": str(file_data.get("id", "")),
            "name": str(file_data.get("name", path.name)),
            "webViewLink": str(file_data.get("webViewLink", "")),
        }
    except Exception as exc:
        print(f"DEBUG post_generation: Google Drive upload failed: {exc}")
        return {"status": "failed", "reason": str(exc)}


def send_whatsapp_message(body: str) -> dict[str, Any] | None:
    """Send a WhatsApp message through Twilio."""
    load_env_file()
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    to_number = os.getenv("TWILIO_WHATSAPP_TO", "whatsapp:+919267990207")

    if not account_sid or not auth_token:
        print("DEBUG post_generation: Twilio credentials not configured; skipping WhatsApp")
        return {"status": "skipped", "reason": "missing_twilio_credentials"}

    form = urlencode({"From": from_number, "To": to_number, "Body": body}).encode("utf-8")
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    request = Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data=form,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
        print("DEBUG post_generation: queued WhatsApp notification")
        return {"status": "queued", "status_code": response.status, "response": payload}
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"DEBUG post_generation: WhatsApp notification failed: {exc} {error_body}")
        return {"status": "failed", "reason": str(exc), "response": error_body}
    except URLError as exc:
        print(f"DEBUG post_generation: WhatsApp notification failed: {exc}")
        return {"status": "failed", "reason": str(exc)}


def send_resume_whatsapp(resume_name: str, drive_link: str) -> dict[str, Any] | None:
    """Send the generated resume name and Drive link through Twilio WhatsApp."""
    body = f"Resume generated: {resume_name}\nGoogle Drive: {drive_link}"
    return send_whatsapp_message(body)


def send_generation_failure_whatsapp(resume_name: str, error: str) -> dict[str, Any] | None:
    """Send a failure notification when resume generation does not complete."""
    trimmed_error = " ".join(error.split())[:500]
    body = f"Resume generation failed: {resume_name}\nError: {trimmed_error}"
    return send_whatsapp_message(body)


def post_process_resume(path: Path) -> dict[str, Any]:
    load_env_file()
    drive_file = upload_resume_to_drive(path)
    notification = None
    if drive_file and drive_file.get("webViewLink"):
        notification = send_resume_whatsapp(path.name, drive_file["webViewLink"])
    elif drive_file:
        folder_link = os.getenv("GOOGLE_DRIVE_FOLDER_LINK", DEFAULT_DRIVE_FOLDER_LINK)
        notification = send_whatsapp_message(
            f"Resume generated locally: {path.name}\n"
            f"Google Drive folder: {folder_link}"
        )
    return {"drive_file": drive_file, "notification": notification}
