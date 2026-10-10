"""Local-disk store for citizen photos and voice notes, served at /media. Demo only: synthetic data, files are named with
an unguessable token and are readable by anyone holding the URL. Set PUBLIC_BASE_URL (your ngrok URL) so the URLs
are reachable from outside; locally they point at http://localhost:8000."""
import mimetypes
import os
import secrets
from pathlib import Path

from .llm import MediaFetchError, fetch_media

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", Path(__file__).resolve().parent.parent / "media"))
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "audio/ogg": ".ogg", "audio/mpeg": ".mp3",
       "audio/mp4": ".m4a", "audio/wav": ".wav", "audio/amr": ".amr"}


def public_base() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/") or "http://localhost:8000"


def save_media(data: bytes, mime: str) -> str:
    """Store bytes and return a URL the intake and verification agents (and the dashboard) can fetch without auth."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = secrets.token_urlsafe(18) + EXT.get(mime, mimetypes.guess_extension(mime) or ".bin")
    (MEDIA_DIR / name).write_bytes(data)
    return f"{public_base()}/media/{name}"


def fetch_any(url: str) -> tuple[bytes, str]:
    """fetch_media, but files in our own store are read from disk instead of over HTTP to ourselves."""
    prefix = f"{public_base()}/media/"
    if url.startswith(prefix):
        path = (MEDIA_DIR / url[len(prefix):]).resolve()
        if MEDIA_DIR.resolve() not in path.parents or not path.is_file():
            raise MediaFetchError(f"media not found: {url}")
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return fetch_media(url)
