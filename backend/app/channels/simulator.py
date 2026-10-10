"""SIMULATOR, NOT WhatsApp. A stand-in provider for demos and tests when no Twilio sandbox is available. It accepts the same
payload shape as Twilio's webhook, skips the signature check, downloads media from plain URLs, and records outgoing messages
instead of sending them. Everything it produces is labelled simulated. Enabled only with WHATSAPP_SIMULATOR=1."""
import uuid

from ..llm import MediaFetchError, fetch_media
from .base import InboundMessage, MediaDownloadError, MediaRef, parse_inbound_params


class SimulatorProvider:
    name = "simulator"

    def __init__(self):
        self.sent: list[dict] = []

    def verify_signature(self, url: str, params: dict[str, str], signature: str | None) -> bool:
        return True  # nothing to verify: the simulator endpoint is only reachable when explicitly enabled

    def parse_inbound(self, params: dict[str, str]) -> InboundMessage:
        msg = parse_inbound_params(params)
        if not msg.message_id:
            msg.message_id = f"SIM{uuid.uuid4().hex[:16]}"
        return msg

    def download_media(self, media: MediaRef) -> tuple[bytes, str]:
        try:
            data, mime = fetch_media(media.url)
        except MediaFetchError as e:
            raise MediaDownloadError(str(e)) from e
        return data, (media.content_type or mime)

    def send(self, phone: str, text: str, media_urls: list[str] | None = None) -> str:
        sid = f"SIMOUT{uuid.uuid4().hex[:12]}"
        self.sent.append({"to": phone, "body": text, "media": media_urls or [], "id": sid, "simulated": True})
        return sid
