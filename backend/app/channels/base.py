"""The seam between the WhatsApp conversation logic and a messaging provider. Twilio is one implementation; the simulator
is another. A new provider (Meta Cloud API, ...) needs only these four methods."""
from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """Sending failed. `retryable` is True for timeouts, 429 and 5xx, False for errors a retry cannot fix."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class MediaDownloadError(Exception):
    """A photo or voice note could not be downloaded from the provider."""


@dataclass
class MediaRef:
    url: str
    content_type: str


@dataclass
class InboundMessage:
    message_id: str
    phone: str  # E.164, e.g. +919876543210
    text: str = ""
    lat: float | None = None
    lng: float | None = None
    media: list[MediaRef] = field(default_factory=list)
    profile_name: str | None = None


def normalize_phone(raw: str) -> str:
    """'whatsapp:+91 98765 43210' -> '+919876543210'."""
    p = (raw or "").strip().removeprefix("whatsapp:").replace(" ", "")
    return p if p.startswith("+") else f"+{p}"


def parse_inbound_params(params: dict[str, str]) -> InboundMessage:
    """Twilio's webhook fields (the simulator uses the same shape): MessageSid, From, Body, NumMedia, MediaUrl{i},
    MediaContentType{i}, Latitude, Longitude."""
    media = []
    for i in range(int(params.get("NumMedia") or 0)):
        url = params.get(f"MediaUrl{i}")
        if url:
            media.append(MediaRef(url=url, content_type=(params.get(f"MediaContentType{i}") or "").lower()))

    def num(key: str) -> float | None:
        try:
            return float(params[key])
        except (KeyError, ValueError):
            return None

    return InboundMessage(
        message_id=params.get("MessageSid") or params.get("SmsMessageSid") or "", phone=normalize_phone(params.get("From", "")),
        text=(params.get("Body") or "").strip(), lat=num("Latitude"), lng=num("Longitude"), media=media,
        profile_name=params.get("ProfileName"),
    )


class WhatsAppProvider(Protocol):
    name: str

    def verify_signature(self, url: str, params: dict[str, str], signature: str | None) -> bool: ...

    def parse_inbound(self, params: dict[str, str]) -> InboundMessage: ...

    def download_media(self, media: MediaRef) -> tuple[bytes, str]:
        """Bytes and content type, using the provider's own credentials. Raises MediaDownloadError."""

    def send(self, phone: str, text: str, media_urls: list[str] | None = None) -> str:
        """Send one message; returns the provider's message id. Raises ProviderError."""
